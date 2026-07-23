"""Pod / Container anomaly handlers (8 types).

These affect individual pod lifecycle without changing node state.
Most handlers remove pods directly via ClusterStateManager.remove_pod.
"""

from app.anomalies import AnomalyType
from app.anomalies.base import AnomalyEffect


def _crash_loop(state, defn, severity):
    """Container crashes immediately — pod in CrashLoopBackOff."""
    dep = state.deployments.get(defn.target)
    if dep:
        running = [p for p in dep.pods if p.status.name == "RUNNING"]
        for p in running[:max(1, int(len(running) * severity * 0.5))]:
            state.remove_pod(p.pod_id)
    return AnomalyEffect()


def _oom_kill(state, defn, severity):
    """Container OOMKilled — removed, restarted with backoff."""
    dep = state.deployments.get(defn.target)
    if dep:
        # Kill the most memory-intensive pod
        candidates = sorted(
            [p for p in dep.pods if p.status.name == "RUNNING"],
            key=lambda p: p.current_memory_mb, reverse=True,
        )
        if candidates and severity > 0:
            state.remove_pod(candidates[0].pod_id)
    return AnomalyEffect()


def _liveness_fail(state, defn, severity):
    """Health check fails — container restarted by kubelet."""
    # Simulate by removing and recreating 1 pod
    dep = state.deployments.get(defn.target)
    if dep:
        running = [p for p in dep.pods if p.status.name == "RUNNING"]
        if running:
            state.remove_pod(running[0].pod_id)
    return AnomalyEffect()


def _readiness_fail(state, defn, severity):
    """Readiness probe fails — pod Running but removed from endpoints."""
    # Pod exists but doesn't serve traffic — effect: no metrics produced
    effect = AnomalyEffect()
    dep = state.deployments.get(defn.target)
    if dep:
        running = [p for p in dep.pods if p.status.name == "RUNNING"]
        for p in running[:1]:
            effect.blocked_pods.add(p.pod_id)
    return effect


def _init_failure(state, defn, severity):
    """Init container hangs — pod stuck Init:CrashLoopBackoff."""
    effect = AnomalyEffect()
    dep = state.deployments.get(defn.target)
    if dep:
        pending = [p for p in dep.pods if p.status.name == "PENDING"]
        for p in pending[:max(1, int(len(pending) * severity * 0.3))]:
            effect.blocked_pods.add(p.pod_id)
    return effect


def _startup_slow(state, defn, severity):
    """Image pull / mount takes 10x longer — pod slow to start."""
    # No state mutation — metrics generator handles slow start via latency bump
    return AnomalyEffect(
        latency_multiplier={defn.target: 1.0 + severity * 5.0},
    )


def _pod_eviction(state, defn, severity):
    """Node pressure causes pod eviction — pod removed from node."""
    dep = state.deployments.get(defn.target)
    if dep:
        running = [p for p in dep.pods if p.status.name == "RUNNING"]
        for p in running[:max(1, int(len(running) * severity * 0.4))]:
            state.remove_pod(p.pod_id)
    return AnomalyEffect()


def _sidecar_crash(state, defn, severity):
    """Envoy/Istio sidecar dies — pod Running but traffic can't reach it."""
    effect = AnomalyEffect()
    dep = state.deployments.get(defn.target)
    if dep:
        running = [p for p in dep.pods if p.status.name == "RUNNING"]
        # All traffic to this deployment fails
        effect.blocked_deployments.add(defn.target)
    return effect


POD_HANDLERS = {}

for _args in [
    (AnomalyType.CRASH_LOOP, _crash_loop, None),
    (AnomalyType.OOM_KILL, _oom_kill, None),
    (AnomalyType.LIVENESS_FAIL, _liveness_fail, None),
    (AnomalyType.READINESS_FAIL, _readiness_fail, None),
    (AnomalyType.INIT_FAILURE, _init_failure, None),
    (AnomalyType.STARTUP_SLOW, _startup_slow, None),
    (AnomalyType.POD_EVICTION, _pod_eviction, None),
    (AnomalyType.SIDECAR_CRASH, _sidecar_crash, None),
]:
    POD_HANDLERS[_args[0]] = (_args[1], _args[2])
