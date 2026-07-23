"""Traffic & load anomaly handlers (6 types).

These modify metrics at the RPS layer — the existing CPU/memory/latency
physics naturally responds to changed traffic.
No cluster state mutations needed for most handlers.
"""

from app.anomalies import AnomalyType
from app.anomalies.base import AnomalyEffect


def _traffic_spike(state, defn, severity):
    """Sudden 5-20x RPS increase (DDoS-like)."""
    effect = AnomalyEffect()
    effect.rps_multiplier[defn.target] = 1.0 + severity * 19.0
    return effect


def _traffic_drop(state, defn, severity):
    """Traffic drops to near-zero (upstream failure)."""
    effect = AnomalyEffect()
    effect.rps_multiplier[defn.target] = max(0.01, 1.0 - severity * 0.99)
    return effect


def _traffic_shift(state, defn, severity):
    """80% of traffic moves from deployment A to B."""
    effect = AnomalyEffect()
    deps = list(state.deployments.keys())
    if len(deps) >= 2:
        source = deps[0]
        target = deps[1]
        effect.rps_multiplier[source] = 1.0 - severity * 0.8
        effect.rps_multiplier[target] = 1.0 + severity * 3.0
    return effect


def _slow_loris(state, defn, severity):
    """Slow HTTP — connections held open, pool exhausted."""
    effect = AnomalyEffect()
    effect.latency_multiplier[defn.target] = 1.0 + severity * 10.0
    effect.cpu_offset_pp[defn.target] = severity * 5.0  # keep-alive cost
    return effect


def _thundering_herd(state, defn, severity):
    """Cache invalidated — all requests hit backend."""
    effect = AnomalyEffect()
    effect.rps_multiplier[defn.target] = 1.0 + severity * 9.0
    effect.cpu_offset_pp[defn.target] = severity * 10.0
    return effect


def _load_imbalance(state, defn, severity):
    """Sticky sessions cause uneven load — some pods at 90% CPU, others at 10%."""
    effect = AnomalyEffect()
    effect.jitter = severity * 0.25
    effect.cpu_offset_pp[defn.target] = severity * 15.0
    return effect


TRAFFIC_HANDLERS = {}

for _args in [
    (AnomalyType.TRAFFIC_SPIKE, _traffic_spike, None),
    (AnomalyType.TRAFFIC_DROP, _traffic_drop, None),
    (AnomalyType.TRAFFIC_SHIFT, _traffic_shift, None),
    (AnomalyType.SLOW_LORIS, _slow_loris, None),
    (AnomalyType.THUNDERING_HERD, _thundering_herd, None),
    (AnomalyType.LOAD_IMBALANCE, _load_imbalance, None),
]:
    TRAFFIC_HANDLERS[_args[0]] = (_args[1], _args[2])
