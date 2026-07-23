"""GPU-specific anomaly handlers (10 types).

Most GPU anomalies block individual GPU devices and cause GPU-required
pods to lose their accelerator, forcing CPU fallback or Pending state.
"""

from app.anomalies import AnomalyType
from app.anomalies.base import AnomalyEffect, register_handler


def _gpu_xid(state, defn, severity):
    """Fatal XID error — GPU resets, kernels lost."""
    state.block_gpu(defn.target)
    gpu_deps = {d for d in state.deployments if state.deployments[d].requires_gpu}
    return AnomalyEffect(blocked_gpus={defn.target}, force_gpu_off=gpu_deps)


def _gpu_xid_revert(state, defn):
    state.unblock_gpu(defn.target)


def _gpu_oom(state, defn, severity):
    """cudaMalloc fails — GPU memory exhausted."""
    gpu_deps = {d for d in state.deployments if state.deployments[d].requires_gpu}
    return AnomalyEffect(force_gpu_off=gpu_deps)


def _gpu_ecc(state, defn, severity):
    """ECC errors accumulate — bandwidth degrades."""
    return AnomalyEffect(
        cpu_offset_pp={d: severity * 8.0 for d in state.deployments},
        jitter=severity * 0.04,
    )


def _gpu_hbm(state, defn, severity):
    """HBM channel lost — effective GPU memory halved."""
    gpu_deps = {d for d in state.deployments if state.deployments[d].requires_gpu}
    return AnomalyEffect(
        force_gpu_off=gpu_deps if severity > 0.6 else set(),
        cpu_offset_pp={d: severity * 12.0 for d in gpu_deps},
    )


def _gpu_pcie(state, defn, severity):
    """PCIe bus error — GPU–CPU transfers fail."""
    return AnomalyEffect(
        latency_multiplier={d: 1.0 + severity * 5.0 for d in state.deployments},
        cpu_offset_pp={d: severity * 10.0 for d in state.deployments},
    )


def _gpu_thermal(state, defn, severity):
    """Temperature threshold — GPU clock reduced 30–60%."""
    return AnomalyEffect(
        cpu_offset_pp={d: severity * 20.0 for d in state.deployments},
        jitter=severity * 0.06,
    )


def _gpu_timeout(state, defn, severity):
    """TDR watchdog reset — GPU contexts lost."""
    gpu_deps = {d for d in state.deployments if state.deployments[d].requires_gpu}
    return AnomalyEffect(
        blocked_gpus={defn.target} if severity > 0.4 else set(),
        force_gpu_off=gpu_deps,
    )


def _gpu_timeout_revert(state, defn):
    state.unblock_gpu(defn.target)


def _gpu_mig(state, defn, severity):
    """MIG partition corrupt — GPU instance lost."""
    state.block_gpu(defn.target)
    return AnomalyEffect(
        blocked_gpus={defn.target},
        force_gpu_off={d for d in state.deployments if state.deployments[d].requires_gpu},
    )


def _gpu_mig_revert(state, defn):
    state.unblock_gpu(defn.target)


def _gpu_nvlink(state, defn, severity):
    """NVLink failure — GPU-to-GPU bandwidth drops to PCIe."""
    return AnomalyEffect(
        cpu_offset_pp={d: severity * 15.0 for d in state.deployments},
        latency_multiplier={d: 1.0 + severity * 2.0 for d in state.deployments},
    )


def _gpu_pmem_leak(state, defn, severity):
    """Process leaks GPU memory, fragmentation grows."""
    gpu_deps = {d for d in state.deployments if state.deployments[d].requires_gpu}
    return AnomalyEffect(
        force_gpu_off=gpu_deps if severity > 0.8 else set(),
        cpu_offset_pp={d: severity * 5.0 for d in gpu_deps},
    )


GPU_HANDLERS = {}

for _args in [
    (AnomalyType.GPU_XID_ERROR, _gpu_xid, _gpu_xid_revert),
    (AnomalyType.GPU_OOM, _gpu_oom, None),
    (AnomalyType.GPU_ECC_CASCADE, _gpu_ecc, None),
    (AnomalyType.GPU_HBM_FAILURE, _gpu_hbm, None),
    (AnomalyType.GPU_PCIE_ERROR, _gpu_pcie, None),
    (AnomalyType.GPU_THERMAL_THROTTLE, _gpu_thermal, None),
    (AnomalyType.GPU_TIMEOUT, _gpu_timeout, _gpu_timeout_revert),
    (AnomalyType.GPU_MIG_FAILURE, _gpu_mig, _gpu_mig_revert),
    (AnomalyType.GPU_NVLINK_FAILURE, _gpu_nvlink, None),
    (AnomalyType.GPU_PMEM_LEAK, _gpu_pmem_leak, None),
]:
    GPU_HANDLERS[_args[0]] = (_args[1], _args[2])
