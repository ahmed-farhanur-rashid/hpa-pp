"""Network anomaly handlers (8 types).

These affect latency, availability, and connectivity between
services without mutating cluster state.
"""

from app.anomalies import AnomalyType
from app.anomalies.base import AnomalyEffect, register_handler


def _network_partition(state, defn, severity):
    """Nodes split — some deployments can't reach each other."""
    return AnomalyEffect(
        latency_multiplier={d: 1.0 + severity * 10.0 for d in state.deployments},
        jitter=severity * 0.15,
    )


def _latency_spike(state, defn, severity):
    """Switch congestion — cluster-wide RTT increase."""
    return AnomalyEffect(
        latency_multiplier={d: 1.0 + severity * 20.0 for d in state.deployments},
    )


def _packet_loss(state, defn, severity):
    """Intermittent packet drops — TCP retransmits."""
    return AnomalyEffect(
        latency_multiplier={d: 1.0 + severity * 3.0 for d in state.deployments},
        jitter=severity * 0.12,
    )


def _dns_failure(state, defn, severity):
    """DNS resolution intermittent."""
    return AnomalyEffect(
        latency_multiplier={d: 1.0 + severity * 2.0 for d in state.deployments},
        jitter=severity * 0.08,
    )


def _lb_failure(state, defn, severity):
    """Load balancer misroutes — some pods get 10x traffic."""
    eff = AnomalyEffect()
    deps = list(state.deployments.keys())
    if deps:
        target = deps[0]
        eff.rps_multiplier[target] = 1.0 + severity * 9.0
    return eff


def _bandwidth_sat(state, defn, severity):
    """Link saturated — queuing delays."""
    return AnomalyEffect(
        latency_multiplier={d: 1.0 + severity * 5.0 for d in state.deployments},
        latency_ms_absolute=severity * 500.0,
    )


def _connection_reset(state, defn, severity):
    """TCP RST injected randomly — retry storms."""
    return AnomalyEffect(
        latency_multiplier={d: 1.0 + severity * 2.0 for d in state.deployments},
        jitter=severity * 0.20,
    )


def _mtu_mismatch(state, defn, severity):
    """Jumbo frames silently dropped — large payloads fail."""
    effect = AnomalyEffect(jitter=severity * 0.10)
    for dep_id in state.deployments:
        effect.latency_multiplier[dep_id] = 1.0 + severity * 3.0
    return effect


NETWORK_HANDLERS = {}

for _args in [
    (AnomalyType.NETWORK_PARTITION, _network_partition, None),
    (AnomalyType.LATENCY_SPIKE, _latency_spike, None),
    (AnomalyType.PACKET_LOSS, _packet_loss, None),
    (AnomalyType.DNS_FAILURE, _dns_failure, None),
    (AnomalyType.LB_FAILURE, _lb_failure, None),
    (AnomalyType.BANDWIDTH_SAT, _bandwidth_sat, None),
    (AnomalyType.CONNECTION_RESET, _connection_reset, None),
    (AnomalyType.MTU_MISMATCH, _mtu_mismatch, None),
]:
    NETWORK_HANDLERS[_args[0]] = (_args[1], _args[2])
