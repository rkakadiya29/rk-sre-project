Node refresh depends on:
    Pod readiness transitions
    Eviction success/failure
    Node condition changes
    Autoscaler reactions

Remote operators rely on:
    Long-lived watch connections
    Higher latency
    Network partitions

Result:
    Missed events
    Stale state
    More polling
    Harder retries
    Inside the cluster:
    Watches are cheap and stable
    Latency is negligible

This operator implements a rolling node refresh strategy with generation-based labeling to approximate blue-green safety guarantees while maintaining Kubernetes-native behavior. Nodes are cordoned and drained in bounded batches, with health validation between batches. Rollback is achieved by halting further drains and preserving existing nodes.