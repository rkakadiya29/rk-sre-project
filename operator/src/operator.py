import kopf
import kubernetes.client
from kubernetes import config
from utils import scale_gke_nodepool

try:
    config.load_kube_config()
    print("Kubeconfig pre-loaded successfully for GKE.")
except Exception as e:
    print(f"Failed to pre-load config: {e}")

@kopf.on.login()
def login_fn(**kwargs):
    return kopf.login_via_client(**kwargs)  

@kopf.on.resume('stable.rk.ai', 'v1', 'noderefreshes')
@kopf.on.create('stable.rk.ai', 'v1', 'noderefreshes')
def hello_world(spec, name, namespace, logger, **kwargs):
    logger.info(f"Hello! I detected a NodeRefresh named '{name}' in namespace '{namespace}'")
    
    # Just printing values from the spec to prove we can read it
    target_tier = spec.get('tier', 'not-specified')
    logger.info(f"The requested tier is: {target_tier}")
    # For a refresh, we scale up by 1 first
    project = "project-c668633a-e9a8-4b7e-8a0"
    zone = "us-central1-a"
    cluster = "k8s-cluster1"
    pool = "default-pool"
    try:
        scale_gke_nodepool(project, zone, cluster, pool, new_count=2)
        logger.info("Scaling operation triggered successfully.")
    except Exception as e:
        logger.error(f"Failed to scale: {e}")

# from select import POLLIN
# import kopf
# import kubernetes.client as k8s
# from kubernetes.client.rest import ApiException 
# import logging
# import asyncio
# import pendulum
# import datetime
# import time
# from datetime import datetime, timezone

# # Configuration constants
# GROUP = "stable.rk.ai"
# VERSION = "v1"
# PLURAL = "noderefreshes"

# @kopf.on.create(GROUP, VERSION, PLURAL)  # triggers only once
# @kopf.on.resume(GROUP, VERSION, PLURAL)  # to "catch up" and sync after restart
# def operator_startup(spec, name, logger, patch, body, **kwargs):  
#     logger.info(f"Operator RK.AI node-refresher operator started for {name}")
#     patch.status['phase'] = 'Running' 
#     patch.status['message'] = 'Monitoring nodes for 3-minute refresh cycle' 
#     return {'lastAction': 'Initialization'} 

# def get_node_age_seconds(node): 
#     try: 
#         creation_ts = node.metadata.creation_timestamp 
#         return (datetime.now(timezone.utc) - creation_ts).total_seconds() 
#     except k8s.ApiException as e: 
#         logging.error(f"Error getting node refresh object {name}: {e}")
#         return None 

# def check_cluster_health(v1, threshold, logger):
#     # Returns True if health percentage >= threshold
#     pods = v1.list_pod_for_all_namespaces(field_selector=f"status.phase=Running").items 
#     active_pods = [p for p in pods if p.status.phase in ['Running', 'Pending']] 
#     if not active_pods:  
#         return True
#     ready_count = 0
#     for p in active_pods:
#         if p.status.container_statuses and all(c.ready for c in p.status.container_statuses): 
#             ready_count += 1
#     return (ready_count / len(active_pods))*100 >= threshold  

# def perform_safe_drain(v1, node, spec, logger):  
#     # CORDON: Mark node as unschedulable
#     v1.patch_node(node, {"spec": {"unschedulable": True}}) 
#     logger.info(f"Node {node} cordoned successfully") 
#     # Get pods on this node (excluding kube-system)
#     pods = v1.list_pod_for_all_namespaces(field_selector=f"spec.nodeName={node}").items  
#     max_at_once = spec.get('maxConcurrentRefreshes', 1) 
#     for i in range(0, len(pods), max_at_once):  
#         batch = pods[i: i+max_at_once]  
#         for pod in batch: 
#             if pod.metadata.namespace == 'kube-system': continue
#             eviction = k8s.V1Eviction(metadata=k8s.V1ObjectMeta(name=pod.metadata.name, namespace=pod.metadata.namespace))
#             v1.create_namespaced_pod_eviction(pod.metadata.name, pod.metadata.namespace, eviction) 
#             time.sleep(5)
 

# @kopf.timer(GROUP, VERSION, PLURAL, interval=45.0) 
# def reconcile_loop(spec, name, status, logger, **kwargs):  
#     v1 = k8s.CoreV1Api()
#     policy_api = k8s.PolicyV1Api()   
#     # Identify Target nodes
#     target_labels = spec.get('targetNodeLabels', {}) 
#     label_selector = ','.join([f"{k}={v}" for k, v in target_labels.items()]) 
     
#     nodes = v1.list_node(label_selector=label_selector).items  
#     if not nodes:
#         logger.warning(f"No nodes found matching: {label_selector}")
#         return {'phase': 'Warning', 'message': 'No matching nodes found'}
#     print(f"[DEBUG] API returned {len(nodes)} nodes")  #####

#     nodes_to_refresh = []  
#     for node in nodes: 
#         if get_node_age_seconds(node) > 180 and not node.spec.unschedulable: 
#             nodes_to_refresh.append(node.metadata.name) 
#     if not nodes_to_refresh: 
#         return {'phase': 'Healthy', 
#                 'nodesRefreshed': 0, 
#                 'currentNodes': [], 
#                 'message': 'All nodes within age limit' } 

#     target_node_name = nodes_to_refresh[0]
#     logger.info(f"Refreshing node: {target_node_name}")

#     # Check threshold before proceeding  
#     min_health = spec.get('minHealthThreshold', 90)  
#     if not check_cluster_health(v1, min_health, logger):  
#         raise kopf.TemporaryError(f"Cluster health below threshold {min_health}, delaying refresh", delay=60)  
  
#     perform_safe_drain(v1, target_node_name, spec, logger)

#     return {
#         'phase': 'InProgress',
#         'currentNodes': [target_node_name],
#         'nodesRefreshed': status.get('nodesRefreshed', 0) + 1,
#         'message': f"Actively refreshing node {target_node_name}"
#     }



# """Helper to update the Status subresource"""
# def update_status(custom_api, name, status_update):
#     body = {"status": status_update}
#     custom_api.patch_namespaced_custom_object(GROUP, VERSION, PLURAL, name, body)



