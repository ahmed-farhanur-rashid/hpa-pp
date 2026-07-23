"""Node-level hardware anomaly handlers (10 types).

Each handler mutates cluster state (blocks nodes, evicts pods) and
returns an AnomalyEffect to drive metric distortion during the tick.
"""

from app.anomalies import AnomalyType
from app.anomalies.base import AnomalyEffect, register_handler


def _node_crash(state, defn, severity):
    evicted = state.block_node(defn.target)
    effect = AnomalyEffect(blocked_nodes={defn.target})
    for p in evicted:
        effect.blocked_pods.add(p.pod_id)
    return effect


def _node_crash_revert(state, defn):
    state.unblock_node(defn.target)


def _node_hang(state, defn, severity):
    state.block_node(defn.target)
    return AnomalyEffect(blocked_nodes={defn.target})


def _node_hang_revert(state, defn):
    state.unblock_node(defn.target)


def _disk_failure(state, defn, severity):
    evicted = []
    node = state.nodes.get(defn.target)
    if node:
        for p in list(node.pods):
            state.remove_pod(p.pod_id)
            evicted.append(p.pod_id)
    state.blocked_nodes.add(defn.target)
    return AnomalyEffect(blocked_pods=set(evicted), blocked_nodes={defn.target})


def _disk_failure_revert(state, defn):
    state.blocked_nodes.discard(defn.target)


def _disk_slow(state, defn, severity):
    return AnomalyEffect(latency_multiplier={
        d: 1.0 + severity * 9.0 for d in state.deployments
    }, jitter=severity * 0.05)


def _memory_leak(state, defn, severity):
    """Gradually reduce effective node memory."""
    node = state.nodes.get(defn.target)
    if node:
        cap = max(256, int(node.total_memory_mb * (1.0 - severity * 0.6)))
        node.total_memory_mb = cap
    return AnomalyEffect(memory_multiplier={
        d: 1.0 + severity * 0.4 for d in state.deployments
    })


def _memory_leak_revert(state, defn):
    pass  # memory restored on next initialize


def _cpu_throttle(state, defn, severity):
    """CPU capped by thermal/power throttle."""
    node = state.nodes.get(defn.target)
    if node:
        node.total_cpu_millicores = int(node.total_cpu_millicores * (1.0 - severity * 0.4))
    return AnomalyEffect(cpu_offset_pp={
        d: severity * 15.0 for d in state.deployments
    })


def _cpu_throttle_revert(state, defn):
    pass


def _ram_corruption(state, defn, severity):
    """Random pods crash due to ECC errors."""
    import random
    rng = random.Random(defn.anomaly_id)
    killed = []
    for dep in list(state.deployments.values()):
        running = [p for p in dep.pods if p.status.name == "RUNNING"]
        if running and rng.random() < severity:
            pod = rng.choice(running)
            state.remove_pod(pod.pod_id)
            killed.append(pod.pod_id)
    return AnomalyEffect(blocked_pods=set(killed))


def _nic_failure(state, defn, severity):
    """Network interface degrades — inject latency + packet loss."""
    return AnomalyEffect(
        latency_multiplier={d: 1.0 + severity * 4.0 for d in state.deployments},
        jitter=severity * 0.1,
    )


def _power_failure(state, defn, severity):
    """PSU fails — node at risk, may crash any tick."""
    if severity > 0.7:
        evicted = state.block_node(defn.target)
        return AnomalyEffect(blocked_nodes={defn.target})
    return AnomalyEffect(latency_multiplier={
        d: 1.0 + severity * 0.5 for d in state.deployments
    })


def _power_failure_revert(state, defn):
    state.unblock_node(defn.target)


def _fan_failure(state, defn, severity):
    """Cooling fails — gradual thermal throttle."""
    return AnomalyEffect(
        cpu_offset_pp={d: severity * 10.0 for d in state.deployments},
        jitter=severity * 0.03,
    )


# ── Register all node handlers ────────────────────────────────

NODE_HANDLERS = {}

for _args in [
    (AnomalyType.NODE_CRASH, _node_crash, _node_crash_revert),
    (AnomalyType.NODE_HANG, _node_hang, _node_hang_revert),
    (AnomalyType.DISK_FAILURE, _disk_failure, _disk_failure_revert),
    (AnomalyType.DISK_SLOW, _disk_slow, None),
    (AnomalyType.MEMORY_LEAK, _memory_leak, _memory_leak_revert),
    (AnomalyType.CPU_THROTTLE, _cpu_throttle, _cpu_throttle_revert),
    (AnomalyType.RAM_CORRUPTION, _ram_corruption, None),
    (AnomalyType.NIC_FAILURE, _nic_failure, None),
    (AnomalyType.POWER_FAILURE, _power_failure, _power_failure_revert),
    (AnomalyType.FAN_FAILURE, _fan_failure, None),
]:
    NODE_HANDLERS[_args[0]] = (_args[1], _args[2])
