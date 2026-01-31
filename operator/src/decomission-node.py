from kubernetes import client, config
from kubernetes.client.rest import ApiException

def decommission_node(node_name):
    config.load_kube_config()
    v1 = client.CoreV1Api()

    try:
        # Cordon the Node
        print(f"Cordoning node: {node_name}...")
        body = {
            "spec": {
                "unschedulable": True
            }
        }
        v1.patch_node(node_name, body)
        print(f"Node {node_name} is now unschedulable.")

        # DRAIN (eviction) here 
    
        # DELETE the node  
        print(f"Deleting node object: {node_name}...")
        v1.delete_node(node_name)
        print(f"Node {node_name} successfully deleted from Kubernetes API.")

    except ApiException as e:
        print(f"Exception when calling Kubernetes API: {e}")

decommission_node("gke-k8s-cluster1-default-pool-c6374114-mnbf")