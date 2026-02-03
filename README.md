# Node-Refresh Operator

This is a Python-based Kubernetes Operator that performs automated node refresh cycles on GKE cluster every 3 days while maintaining zero downtime for running applications. It implements surge-based strategy, facilitated by labels to identify  Generation of the cycle. 

## Deployement instructions for Demo
1. You need Python 3.10 and above to use kopf. Install the necessary libraries:
    ```bash
    pip3 install kopf kubernetes pendulum
    pip3 install pykube-ng (client lib for k8s)
    pip3 install kubecrd
    ```
2. Create GCP account, a GKE cluster and add node-pool with atleast one node.
3. Install gcloud SDK to access GKE via your local terminal 
4. Deploy applications on the cluster to test the node-refresh operator 
ex: kubectl apply -f test_apps/app1/app1.yaml
    kubectl apply -k test_apps/app2/bookinfo-example/kustomize/
5. Create CRD and CR. ex:
     ```bash
    kubectl apply -f operator/deploy/crd.yaml
    kubectl apply -f operator/deploy/cr.yaml
    ```
6. Run the operator
   kopf run operator/src/operator.py --verbose 

## Program Logic Flow (The "Refresher" Algorithm)
The program follows a Surge-and-Drain pattern to ensure the cluster never loses capacity during the 3-day refresh cycle.
### Phase I: Pre-Flight Validation
Wake Up: The operator triggers every 120 seconds via a kopf.timer.
Schedule Check: Using croniter, the program checks if the current time is within the "3-day" window and compares it against status.lastRefreshTime.
Cluster Health Check: Before touching any infrastructure, the program calculates the ratio of Ready pods. If health is below the minHealthyPercent (e.g., 90%), it aborts to prevent cascading failures.

### Phase II: Surge (Provisioning)
Identity Target: The operator selects nodes matching the nodeSelector (e.g., tier: worker).
Scale Up: The program calls the GKE API to increase the node pool size by N+1.
Capacity Validation: The program enters a retry loop, waiting for the new node to reach the Ready state in Kubernetes. This ensures replacement capacity exists before any pods are evicted.

### Phase III: Drain & Migrate (Zero Downtime)
Cordon: The target "old" node is marked unschedulable to prevent new pods from landing on it.
Safe Eviction: The operator sends Eviction requests for each pod.
PDB Awareness: If the Kubernetes API returns a 429 error (Pod Disruption Budget violation), the operator waits and retries, ensuring at least one replica remains alive elsewhere.
Termination Wait: The operator waits until the target node is completely empty of application pods.

### Phase IV: Decommission & Cleanup
Node Deletion: The "old" node object is explicitly deleted from the Kubernetes API.
Scale Down: The GKE node pool is resized back to its original baseline count.
State Update: The status.activeGeneration is incremented, and lastRefreshTime is updated to the current timestamp.


## Component Interaction
Custom Resource (CR): Acts as the "Desired State" (e.g., "Refresh every 3 days").
Operator (Kopf): The brain that monitors the CR and executes the Python logic.
Kubernetes API: Used to Cordon nodes, Evict pods, and check health.
GKE API (Cluster Manager): Used to physically add or remove VMs from the project.


## RECONCILIATION LOGIC AND FAILURE SCENARIOS
### Reconciliation logic:
    1. Schedule Check: Determines if the 3-day window has arrived.
    2. Pre-flight Health: Checks the global ratio of Ready pods.
    3. Increment 'Active Generation' from CR's status.activeGeneration. Select 1st pods that whose label has previous generation.
    4. Surge: Calls GKE API to increase node count.
    5. Wait: Polls the GKE Operation until node is ready before timeout.
    6. Drain: Starts evicting pods from the old node. Validate pod health on new nodes before continuing. Honors Pod Disruption Budgets (PDBs) during migrations.
    7. Decommission: Deletes the old node and resizes the pool back.
    8. Repeat until all nodes arent at the current version.

### Error Handling & Rollback Logic:

| Failure Point | Rollback Action | Purpose |
| :--- | :--- | :--- |
| **GKE Surge Fails** (e.g., Quota) | **Alert and Abort**: Logs a "PermissionDenied" or "Insufficient Quota" error and triggers a 600s backoff. | Prevents the operator from starting a drain when no replacement capacity exists, protecting application availability. |
| **Drain Timeout / PDB Violation** | **Un-cordon & Scale Down**: The target node is patched to `unschedulable: False` and the surge node is removed. | Restores the cluster to its original "Known Good" state if pods are stuck due to Pod Disruption Budgets or local issues. |
| **Post-Op Health Drop** | **Pause & Backoff**: Triggers a `TemporaryError` with a 120s delay if `minHealthyPercent` is not met. | Acts as a circuit breaker to stop the operator from rotating more nodes if the first migration caused cluster instability. |


### Operator design considerations when deployed in the cluster:
- ≥2 replicas → operator survives node loss
- Anti-affinity → replicas on different nodes
- Cluster-critical priority → evicted last
- Operator does NOT pin itself to protected nodes
Leader Election: Use the Kubernetes Lease API (supported by the Python client and Kopf). Only one pod acts as the "Leader" and executes logic, while the other stands by. If the leader's node is drained, the standby pod becomes the leader and continues the rotation.


