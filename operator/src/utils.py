from google.cloud import container_v1
import time

def scale_gke_nodepool(project_id, location, cluster_id, pool_id, new_count):
    client = container_v1.ClusterManagerClient()
    
    # Format the pool name: projects/{project}/locations/{location}/clusters/{cluster}/nodePools/{pool}
    name = f"projects/{project_id}/locations/{location}/clusters/{cluster_id}/nodePools/{pool_id}"
    
    print(f"Requesting GKE to scale {pool_id} to {new_count} nodes...")
    
    request = container_v1.SetNodePoolSizeRequest(
        name=name,
        node_count=new_count
    )

    operation = client.set_node_pool_size(request=request)
    
    # GKE operations are asynchronous. We must wait for the cloud to finish.
    print(f"Operation started: {operation.name}. Waiting for provisioning...")
    return operation

project = "project-c668633a-e9a8-4b7e-8a0"
zone = "us-central1-a"
cluster = "k8s-cluster1"
pool = "default-pool"
try:
    scale_gke_nodepool(project, zone, cluster, pool, new_count=2)
    print("Scaling operation triggered successfully.")
except Exception as e:
    print(f"Failed to scale: {e}")