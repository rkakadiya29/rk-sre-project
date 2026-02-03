import kopf
import kubernetes.client as k8s
from kubernetes import config
from utils import scale_gke_nodepool
from select import POLLIN
from kubernetes.client.rest import ApiException 
import logging
import asyncio
import pendulum
import datetime
import time
from datetime import datetime, timezone
from croniter import croniter
from values import Un_evictable_namespaces, GROUP, VERSION, PLURAL
from utils import perform_safe_drain, check_cluster_health, pre_drain_pod_health_check
import google.api_core.exceptions

try:
    config.load_kube_config()
    print("Kubeconfig pre-loaded successfully for GKE.")
except Exception as e:
    print(f"Failed to pre-load config: {e}")

@kopf.on.login()
def login_fn(**kwargs):
    return kopf.login_via_client(**kwargs)  

@kopf.on.resume(GROUP, VERSION, PLURAL)
@kopf.on.create(GROUP, VERSION, PLURAL)
def operator_startup(spec, status, name, namespace, logger, patch, **kwargs):
    logger.info(f"Operator RK.AI node-refresher operator started for {name}")
    patch.status['phase'] = 'Running' 
    patch.status['message'] = 'Monitoring nodes for 3-day refresh cycle' 
    return {'lastAction': 'Initialization'} 
     
 
@kopf.timer(GROUP, VERSION, PLURAL, interval=120.0) 
def reconcile_loop(spec, name, status, logger, patch, **kwargs): 
    v1 = k8s.CoreV1Api()
    # ---  GKE CONFIG ---
    gke_conf = spec.get('gkeConfig', {})
    project = gke_conf.get('projectId')
    zone = gke_conf.get('zone')
    cluster_id = gke_conf.get('clusterId')
    pool = gke_conf.get('nodePoolId')
    # --- Circuit Breaker Check ---
    # Stop if we've crashed too many times to prevent infinite surging
    fail_count = status.get('failureCount', 0)
    if fail_count >= 3:
        logger.error(f"Migration HALTED for {name}. Max retries exceeded. Check PDBs or Quota.")
        patch.status['phase'] = 'Halted-Error'
        return {'message': 'Max retrie exceeded. Halted due to repeated failures'}

    # --- AUTOMATED SCHEDULING ---
    schedule = spec.get('refreshSchedule', '0 2 * * *')
    now = datetime.now(timezone.utc)
    last_run_str = status.get('lastRefreshTime')  # Get the last run string. Fallback to a very old date (Unix Epoch)
    if last_run_str:
        last_run = datetime.fromisoformat(last_run_str)
    else:
        last_run = datetime(1970, 1, 1, tzinfo=timezone.utc)   # Use 1970 UTC as a safe "never run before" starting point

    # Calculate the previous scheduled window
    it = croniter(schedule, now)
    prev_window = it.get_prev(datetime)
    # Ensure prev_window is UTC-aware for comparison
    if prev_window.tzinfo is None:
        prev_window = prev_window.replace(tzinfo=timezone.utc)

    if last_run >= prev_window and status.get('phase') == 'Completed':
        logger.info("Refresh already completed for the current schedule window.")
        return {'phase': 'Healthy', 'message': 'No refresh needed'}
    # We automate the 'target' by incrementing the last known successful generation
    current_gen = status.get('activeGeneration', 0)
    current_gen_label = f"gen-{current_gen}"
    target_gen_label = f"gen-{current_gen + 1}"

    logger.info("Proceeding with node-pool refresh...")
    patch.status['phase'] = 'Migrating'

    node_selector = spec.get('targetNodeLabels') or {}
    selector_str = ",".join([f"{k}={v}" for k, v in node_selector.items()])
    print(f"Selector string: {selector_str}")
    all_nodes = v1.list_node(label_selector=selector_str).items
    # if nodes have NO generation label yet 
    new_nodes = [n for n in all_nodes if 'rk.ai/generation' not in n.metadata.labels]
    for n in new_nodes:
        new_node_name = n.metadata.name
        body = {
            "metadata": {
                "labels": {
                    "rk.ai/generation": current_gen_label
                }
            }
        }
        logger.info(f"Patched new node {new_node_name} with {current_gen_label}")
        v1.patch_node(new_node_name, body)
    baseline_count = len(all_nodes)
    # Identify 'Blue' nodes (those that don't have the NEXT generation label)
    blue_nodes = [n for n in all_nodes if n.metadata.labels.get('rk.ai/generation') != target_gen_label]
    
    #--- COMPLETION CHECK ---
    if not blue_nodes:
        logger.info(f"All nodes successfully reached {target_gen_label}")
        patch.status.update({'activeGeneration': current_gen + 1,
        'lastRefreshTime': now.isoformat(),
        'phase': 'Completed',
        'failureCount': 0,
        'message' : f"Successfully rotated nodes to {target_gen_label}",
        'lastError': None })
        return f"Full Migration Done: {target_gen_label}"

    target_node_name = blue_nodes[0].metadata.name
    # check if the node isnt marked as unschedulable, if so, kill it (node-refresh pod itself could have drained it)
    # if v1.read_node(target_node_name).spec.unschedulable:
    #     if not check_cluster_health(v1, spec.get('minHealthyPercent', 90), logger):
    #         raise kopf.TemporaryError("Cluster unhealthy. Backing off.", delay=120)
    #     logger.info(f"Node {target_node_name} is marked as unschedulable. Killing it.")
    #     v1.delete_node(target_node_name)
    #     scale_gke_nodepool(project, zone, cluster_id, pool, baseline_count, logger)
    #     return 

    try:
        # Pre-flight Health Check
        if not check_cluster_health(v1, spec.get('minHealthyPercent', 90), logger):
            raise kopf.TemporaryError("Cluster unhealthy. Backing off.", delay=120)
        patch.status['phase'] = 'Migrating'
        # SURGE 
        logger.info(f"Surge: Adding replacement for {target_node_name}")
        try:
            scale_gke_nodepool(project, zone, cluster_id, pool, baseline_count + 1, logger)
        except google.api_core.exceptions.PermissionDenied as e:
            if "INSUFFICIENT_QUOTA" in str(e):
                logger.error("SRE ALERT: Cloud quota exceeded.")
                raise kopf.TemporaryError("Cloud Quota Exceeded", delay=600)
            raise

        # --- VALIDATE POD HEALTH ON NEW NODES BEFORE CONTINUING ---
        pre_drain_pod_health_check(v1, target_gen_label, logger)

        # --- DRAIN (HONOR PDBs) ---
        logger.info(f"Node validated. Draining {target_node_name}...")
        drain_successful = perform_safe_drain(v1, target_node_name, logger)
        if drain_successful:
            # EXPLICIT DELETE (DECOMMISSION)
            logger.info(f"Explicitly deleting K8s node object: {target_node_name}")
            v1.delete_node(target_node_name)
            # RESIZE
            scale_gke_nodepool(project, zone, cluster_id, pool, baseline_count, logger)
            patch.status['phase'] = 'Completed'

        # Post-operation check: Ensure cluster is still healthy CHECK PODS HEALTH AND NOT CLUSTER HEALTH
        if not check_cluster_health(v1, spec.get('minHealthyPercent', 90), logger):
            raise kopf.TemporaryError("Post-op health check failed.", delay=60)
        # Reset failure on success
        patch.status['failureCount'] = 0

    except Exception as e:
        logger.error(f"MIGRATION FAILED for {target_node_name}: {e}")
        # ROLLBACK 
        # Restore Capacity: Uncordon the Blue node immediately so it can take traffic
        try:
            v1.patch_node(target_node_name, {"spec": {"unschedulable": False}})
            logger.info(f"Rollback: Node {target_node_name} uncordoned.")
        except: pass

        # Scale Down: Restore original count to remove unnecessary surge nodes
        try:
            scale_gke_nodepool(project, zone, cluster_id, pool, baseline_count, logger)
            logger.info("Rollback: Cluster scaled back to baseline.")
        except: pass

        patch.status['failureCount'] = fail_count + 1
        patch.status['phase'] = 'Failing-Retrying'
        patch.status['lastError'] = str(e)
        raise kopf.TemporaryError(f"Retry {fail_count+1}/3: {e}", delay=300)



