"""Deployment & config anomaly handlers (6 types).

These misconfigure deployments, block scheduling via policies,
or cause version/configuration drift.
"""

from app.anomalies import AnomalyType
from app.anomalies.base import AnomalyEffect


def _rollout_fail(state, defn, severity):
    """Bad deployment — new pods fail probe, rollout stuck."""
    effect = AnomalyEffect()
    dep = state.deployments.get(defn.target)
    if dep:
        for p in dep.pods:
            if "rollout" in p.pod_id:
                effect.blocked_pods.add(p.pod_id)
    return effect


def _config_drift(state, defn, severity):
    """ConfigMap/Secret updated — all pods need restart."""
    effect = AnomalyEffect()
    dep = state.deployments.get(defn.target)
    if dep:
        running = [p for p in dep.pods if p.status.name == "RUNNING"]
        for p in running[:max(1, int(len(running) * severity * 0.3))]:
            state.remove_pod(p.pod_id)
            effect.blocked_pods.add(p.pod_id)
    return effect


def _resource_mismatch(state, defn, severity):
    """CPU/memory requests set too large — pods can't schedule."""
    effect = AnomalyEffect()
    dep = state.deployments.get(defn.target)
    if dep:
        for p in dep.pods:
            if p.status.name == "PENDING":
                effect.blocked_pods.add(p.pod_id)
    return effect


def _affinity_violation(state, defn, severity):
    """PodAntiAffinity prevents >1 pod per node."""
    effect = AnomalyEffect()
    dep = state.deployments.get(defn.target)
    if dep:
        # Only keep first 2 pods, block rest
        running = [p for p in dep.pods if p.status.name == "RUNNING"]
        for p in running[2:]:
            effect.blocked_pods.add(p.pod_id)
    return effect


def _toleration_miss(state, defn, severity):
    """Node tainted but pods lack toleration — can't schedule."""
    effect = AnomalyEffect()
    dep = state.deployments.get(defn.target)
    if dep:
        for p in dep.pods:
            if p.status.name == "PENDING":
                effect.blocked_pods.add(p.pod_id)
    return effect


def _namespace_quota(state, defn, severity):
    """Namespace resource quota hit — new pods rejected."""
    effect = AnomalyEffect()
    dep = state.deployments.get(defn.target)
    if dep:
        for p in dep.pods:
            if p.status.name == "PENDING":
                effect.blocked_pods.add(p.pod_id)
    return effect


CONFIG_HANDLERS = {}

for _args in [
    (AnomalyType.ROLLOUT_FAIL, _rollout_fail, None),
    (AnomalyType.CONFIG_DRIFT, _config_drift, None),
    (AnomalyType.RESOURCE_MISMATCH, _resource_mismatch, None),
    (AnomalyType.AFFINITY_VIOLATION, _affinity_violation, None),
    (AnomalyType.TOLERATION_MISS, _toleration_miss, None),
    (AnomalyType.NAMESPACE_QUOTA, _namespace_quota, None),
]:
    CONFIG_HANDLERS[_args[0]] = (_args[1], _args[2])
