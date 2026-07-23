"""Security anomaly handlers (4 types).

These compromise pods, break auth, or cause suspicious behaviour
visible in metrics.
"""

from app.anomalies import AnomalyType
from app.anomalies.base import AnomalyEffect


def _crypto_miner(state, defn, severity):
    """Pod compromised — CPU pinned at 100% on one core."""
    effect = AnomalyEffect()
    dep = state.deployments.get(defn.target)
    if dep:
        running = [p for p in dep.pods if p.status.name == "RUNNING"]
        if running:
            # One pod has abnormally high CPU but normal RPS
            effect.cpu_offset_pp[defn.target] = severity * 60.0
    return effect


def _data_exfil(state, defn, severity):
    """Pod sending data externally — bandwidth consumed."""
    # Higher latency for all deployments, CPU bump on target
    effect = AnomalyEffect(
        latency_multiplier={d: 1.0 + severity * 2.0 for d in state.deployments},
    )
    effect.cpu_offset_pp[defn.target] = severity * 10.0
    return effect


def _rbac_break(state, defn, severity):
    """Service account permissions removed — pod can't register/discover."""
    effect = AnomalyEffect()
    dep = state.deployments.get(defn.target)
    if dep:
        running = [p for p in dep.pods if p.status.name == "RUNNING"]
        for p in running[:max(1, int(len(running) * severity * 0.3))]:
            effect.blocked_pods.add(p.pod_id)
    return effect


def _cert_expiry(state, defn, severity):
    """mTLS cert expired — service mesh communication fails."""
    return AnomalyEffect(
        latency_multiplier={defn.target: 1.0 + severity * 10.0},
    )


SECURITY_HANDLERS = {}

for _args in [
    (AnomalyType.CRYPTO_MINER, _crypto_miner, None),
    (AnomalyType.DATA_EXFIL, _data_exfil, None),
    (AnomalyType.RBAC_BREAK, _rbac_break, None),
    (AnomalyType.CERT_EXPIRY, _cert_expiry, None),
]:
    SECURITY_HANDLERS[_args[0]] = (_args[1], _args[2])
