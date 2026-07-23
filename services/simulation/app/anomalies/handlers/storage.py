"""Storage anomaly handlers (5 types).

Persistent volume and IO failures that affect pod startup,
read/write latency, and application reliability.
"""

from app.anomalies import AnomalyType
from app.anomalies.base import AnomalyEffect


def _pv_failure(state, defn, severity):
    """PVC backend unavailable — pods can't mount volumes."""
    effect = AnomalyEffect()
    dep = state.deployments.get(defn.target)
    if dep:
        running = [p for p in dep.pods if p.status.name == "RUNNING"]
        for p in running[:max(1, int(len(running) * severity * 0.5))]:
            state.remove_pod(p.pod_id)
            effect.blocked_pods.add(p.pod_id)
    return effect


def _iops_throttle(state, defn, severity):
    """Cloud volume hits IOPS cap — read/write latency 20x."""
    effect = AnomalyEffect()
    effect.latency_multiplier[defn.target] = 1.0 + severity * 19.0
    effect.cpu_offset_pp[defn.target] = severity * 5.0  # IO wait
    return effect


def _storage_latency(state, defn, severity):
    """Backend storage node slow — all disk ops 10x."""
    effect = AnomalyEffect()
    for dep_id in state.deployments:
        effect.latency_multiplier[dep_id] = 1.0 + severity * 9.0
    return effect


def _disk_full(state, defn, severity):
    """Node disk at 100% — container runtime fails, pods evicted."""
    effect = AnomalyEffect()
    node = state.nodes.get(defn.target)
    if node:
        for p in list(node.pods):
            state.remove_pod(p.pod_id)
            effect.blocked_pods.add(p.pod_id)
    return effect


def _quota_exceeded(state, defn, severity):
    """Namespace PVC quota hit — new claims fail."""
    # Existing pods OK, new scheduling blocked
    effect = AnomalyEffect()
    for dep_id in state.deployments:
        dep = state.deployments[dep_id]
        pending = [p for p in dep.pods if p.status.name == "PENDING"]
        for p in pending:
            effect.blocked_pods.add(p.pod_id)
    return effect


STORAGE_HANDLERS = {}

for _args in [
    (AnomalyType.PV_FAILURE, _pv_failure, None),
    (AnomalyType.IOPS_THROTTLE, _iops_throttle, None),
    (AnomalyType.STORAGE_LATENCY, _storage_latency, None),
    (AnomalyType.DISK_FULL, _disk_full, None),
    (AnomalyType.QUOTA_EXCEEDED, _quota_exceeded, None),
]:
    STORAGE_HANDLERS[_args[0]] = (_args[1], _args[2])
