from google.cloud import container_v1
import time
import kopf
import kubernetes.client as k8s
from kubernetes.client.rest import ApiException 
import logging
import asyncio
import pendulum
import datetime
import time
from datetime import datetime, timezone
from values import Un_evictable_namespaces

def scale_gke_nodepool(project_id, location, cluster_id, pool_id, new_count, logger):
    client = container_v1.ClusterManagerClient()
    name = f"projects/{project_id}/locations/{location}/clusters/{cluster_id}/nodePools/{pool_id}"
    
    request = container_v1.SetNodePoolSizeRequest(
        name=name,
        node_count=new_count
    )
    try:
        operation = client.set_node_pool_size(request=request)
        op_path = f"projects/{project_id}/locations/{location}/operations/{operation.name}"
        while True:
            current_op = client.get_operation(name=op_path)
            
            # Check for success (DONE is the terminal state)
            if current_op.status == container_v1.Operation.Status.DONE:
                # Check for status_message to catch errors that happened during the op
                if hasattr(current_op, 'status_message') and current_op.status_message:
                    logger.error(f"GKE Operation finished but with errors: {current_op.status_message}")
                    raise Exception(f"GKE Resize failed: {current_op.status_message}")
                    
                logger.info(f"Successfully scaled {pool_id} to {new_count} nodes.")
                return True
            if current_op.status == container_v1.Operation.Status.ABORTING:
                raise Exception(f"GKE Resize was aborted: {current_op.status_message}")
            # If still RUNNING or PENDING, wait and poll again
            logger.info("Waiting for GKE nodes to provision... (20s)")
            time.sleep(20)
    except Exception as e:
        logger.error(f"Error during GKE scaling: {e}")
        raise

def is_daemonset(pod):
    if pod.metadata.owner_references:
        for owner in pod.metadata.owner_references:
            if owner.kind == "DaemonSet":
                return True
    return False

def perform_safe_drain(v1, node_name, logger, timeout=600):
    # Retries internally for PDBs (429) but relies on operator for total failure.
    start_time = time.time()
    # CORDON
    v1.patch_node(node_name, {"spec": {"unschedulable": True}})
    
    pods = v1.list_pod_for_all_namespaces(field_selector=f"spec.nodeName={node_name}").items
    for pod in pods:
        # Skip DaemonSets and System Namespaces
        if is_daemonset(pod) or pod.metadata.namespace in Un_evictable_namespaces:
            continue
        eviction = k8s.V1Eviction(
            api_version="policy/v1",
            kind="Eviction",
            metadata=k8s.V1ObjectMeta(name=pod.metadata.name, namespace=pod.metadata.namespace)
        )
        while True:
            if time.time() - start_time > timeout:
                raise Exception(f"Drain timeout on {node_name}")
            try:
                v1.create_namespaced_pod_eviction(pod.metadata.name, pod.metadata.namespace, eviction)
                break 
            except k8s.ApiException as e:
                if e.status == 429: # PDB Violation
                    time.sleep(15)
                    continue
                raise e
    while time.time() - start_time < timeout:
        remaining = v1.list_pod_for_all_namespaces(field_selector=f"spec.nodeName={node_name}").items
        app_pods = [p for p in remaining if not is_daemonset(p) and p.metadata.namespace not in Un_evictable_namespaces]
        
        if not app_pods:
            logger.info(f"Node {node_name} is now empty.")
            return True # Success!
        logger.info(f"Waiting for {len(app_pods)} pods to finish terminating...")
        time.sleep(10)
    raise Exception(f"Node {node_name} failed to empty before timeout.")

def check_cluster_health(v1, threshold, logger):
    # Returns True if health percentage >= threshold
    pods = v1.list_pod_for_all_namespaces(field_selector=f"status.phase=Running").items 
    active_pods = [p for p in pods if p.status.phase in ['Running', 'Pending']] 
    if not active_pods:  
        return True
    ready_count = 0
    for p in active_pods:
        if p.status.container_statuses and all(c.ready for c in p.status.container_statuses): 
            ready_count += 1
    return (ready_count / len(active_pods))*100 >= threshold 

def pre_drain_pod_health_check(v1, target_gen, logger, timeout=120):
    # Ensures replacement nodes are Ready before we start draining.
    start_time = time.time()
    logger.info(f"Pre-drain check: Validating generation {target_gen}")

    while time.time() - start_time < timeout:
        nodes = v1.list_node(label_selector=f"rk.ai/generation={target_gen}").items   
        # Check if they are all 'Ready'
        node_ready = nodes and all(
            any(c.type == 'Ready' and c.status == 'True' for c in n.status.conditions) 
            for n in nodes
        )
        if node_ready:
            all_pods = v1.list_pod_for_all_namespaces().items
            critical_errors = []
            for p in all_pods:
                # We only care about pods that are supposed to be running
                if p.status.phase == 'Failed':
                    critical_errors.append(p.metadata.name)
                if p.status.container_statuses:
                    for s in p.status.container_statuses:
                        if s.waiting and s.waiting.reason in ['ImagePullBackOff', 'CrashLoopBackOff', 'ErrImagePull']:
                            critical_errors.append(f"{p.metadata.name} ({s.waiting.reason})")
            if not critical_errors:
                logger.info(f"Pre-drain check passed for {target_gen}")
                return True
            else:
                logger.warning(f"Blocking errors detected: {critical_errors}. Waiting for stabilization...")
        else:
            logger.info(f"Waiting for system pods on nodes in {target_gen} to reach Ready state...")
        time.sleep(20)
    raise Exception(f"Pre-drain health check timed out for {target_gen}. Replacement capacity is not healthy.")