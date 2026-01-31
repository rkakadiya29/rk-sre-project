


operator design considerations:
- ≥2 replicas → operator survives node loss
- Anti-affinity → replicas on different nodes
- Cluster-critical priority → evicted last
- Operator does NOT pin itself to protected nodes
Leader Election: Use the Kubernetes Lease API (supported by the Python client and Kopf). Only one pod acts as the "Leader" and executes logic, while the other stands by. If the leader's node is drained, the standby pod becomes the leader and continues the rotation.

The Rotation Workflow (Reconciliation Loop)
- provision new nodes by Integrating with with (Cluster Autoscaler/Managed Node Groups :GKE)
- 
- wait until a pods sucessfully runs on the new node. Service endpoints ≥ threshold.

- lastly, Evict pods using Eviction API