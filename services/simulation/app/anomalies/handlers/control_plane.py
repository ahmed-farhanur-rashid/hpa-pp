"""Control plane anomaly handlers (4 types).

These affect the cluster's ability to schedule, reconcile, and
respond to changes — without directly touching pods or nodes.
"""

from app.anomalies import AnomalyType
from app.anomalies.base import AnomalyEffect


def _api_server_slow(state, defn, severity):
    """kube-apiserver response time 5s+ — all ops delayed."""
    return AnomalyEffect(
        latency_multiplier={d: 1.0 + severity * 5.0 for d in state.deployments},
        jitter=severity * 0.08,
    )


def _scheduler_fail(state, defn, severity):
    """Scheduler not assigning pods — Pending pods stay pending."""
    effect = AnomalyEffect()
    for dep_id in state.deployments:
        dep = state.deployments[dep_id]
        for p in dep.pods:
            if p.status.name == "PENDING":
                effect.blocked_pods.add(p.pod_id)
    return effect


def _cm_failure(state, defn, severity):
    """Controller-manager stops reconciling ReplicaSets."""
    # State shows current_replicas ≠ target_replicas but no action taken
    effect = AnomalyEffect()
    return effect


def _etcd_slow(state, defn, severity):
    """etcd fsync slow — writes fail, cluster in read-only mode."""
    return AnomalyEffect(
        latency_multiplier={d: 1.0 + severity * 8.0 for d in state.deployments},
        jitter=severity * 0.12,
    )


CP_HANDLERS = {}

for _args in [
    (AnomalyType.API_SERVER_SLOW, _api_server_slow, None),
    (AnomalyType.SCHEDULER_FAIL, _scheduler_fail, None),
    (AnomalyType.CM_FAILURE, _cm_failure, None),
    (AnomalyType.ETCD_SLOW, _etcd_slow, None),
]:
    CP_HANDLERS[_args[0]] = (_args[1], _args[2])
