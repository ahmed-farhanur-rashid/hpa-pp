"""Anomaly injection system for the cluster simulation.

Defines 61 anomaly types across 9 failure domains, a trigger system
(SCHEDULED / CONDITIONAL / RANDOM), and the AnomalyEffect data class
that carries per-tick metric modifiers.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────

class AnomalyType(str, Enum):
    # Node-level hardware (10)
    NODE_CRASH = "node_crash"
    NODE_HANG = "node_hang"
    DISK_FAILURE = "disk_failure"
    DISK_SLOW = "disk_slow"
    MEMORY_LEAK = "memory_leak"
    CPU_THROTTLE = "cpu_throttle"
    RAM_CORRUPTION = "ram_corruption"
    NIC_FAILURE = "nic_failure"
    POWER_FAILURE = "power_failure"
    FAN_FAILURE = "fan_failure"

    # GPU-specific (10)
    GPU_XID_ERROR = "gpu_xid_error"
    GPU_OOM = "gpu_oom"
    GPU_ECC_CASCADE = "gpu_ecc_cascade"
    GPU_HBM_FAILURE = "gpu_hbm_failure"
    GPU_PCIE_ERROR = "gpu_pcie_error"
    GPU_THERMAL_THROTTLE = "gpu_thermal_throttle"
    GPU_TIMEOUT = "gpu_timeout"
    GPU_MIG_FAILURE = "gpu_mig_failure"
    GPU_NVLINK_FAILURE = "gpu_nvlink_failure"
    GPU_PMEM_LEAK = "gpu_pmem_leak"

    # Network (8)
    NETWORK_PARTITION = "network_partition"
    LATENCY_SPIKE = "latency_spike"
    PACKET_LOSS = "packet_loss"
    DNS_FAILURE = "dns_failure"
    LB_FAILURE = "lb_failure"
    BANDWIDTH_SAT = "bandwidth_sat"
    CONNECTION_RESET = "connection_reset"
    MTU_MISMATCH = "mtu_mismatch"

    # Storage (5)
    PV_FAILURE = "pv_failure"
    IOPS_THROTTLE = "iops_throttle"
    STORAGE_LATENCY = "storage_latency"
    DISK_FULL = "disk_full"
    QUOTA_EXCEEDED = "quota_exceeded"

    # Pod / Container (8)
    CRASH_LOOP = "crash_loop"
    OOM_KILL = "oom_kill"
    LIVENESS_FAIL = "liveness_fail"
    READINESS_FAIL = "readiness_fail"
    INIT_FAILURE = "init_failure"
    STARTUP_SLOW = "startup_slow"
    POD_EVICTION = "pod_eviction"
    SIDECAR_CRASH = "sidecar_crash"

    # Deployment & Config (6)
    ROLLOUT_FAIL = "rollout_fail"
    CONFIG_DRIFT = "config_drift"
    RESOURCE_MISMATCH = "resource_mismatch"
    AFFINITY_VIOLATION = "affinity_violation"
    TOLERATION_MISS = "toleration_miss"
    NAMESPACE_QUOTA = "namespace_quota"

    # Traffic & Load (6)
    TRAFFIC_SPIKE = "traffic_spike"
    TRAFFIC_DROP = "traffic_drop"
    TRAFFIC_SHIFT = "traffic_shift"
    SLOW_LORIS = "slow_loris"
    THUNDERING_HERD = "thundering_herd"
    LOAD_IMBALANCE = "load_imbalance"

    # Control Plane (4)
    API_SERVER_SLOW = "api_server_slow"
    SCHEDULER_FAIL = "scheduler_fail"
    CM_FAILURE = "cm_failure"
    ETCD_SLOW = "etcd_slow"

    # Security (4)
    CRYPTO_MINER = "crypto_miner"
    DATA_EXFIL = "data_exfil"
    RBAC_BREAK = "rbac_break"
    CERT_EXPIRY = "cert_expiry"


class TriggerType(str, Enum):
    SCHEDULED = "scheduled"
    CONDITIONAL = "conditional"
    RANDOM = "random"


class AnomalyStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    EXPIRED = "expired"


# ── Models ─────────────────────────────────────────────────────

class AnomalyDefinition(BaseModel):
    """Definition of a single anomaly event to inject into the simulation.

    Fields:
        anomaly_id: Unique identifier for this anomaly.
        anomaly_type: Which type of failure to simulate.
        target: The affected entity — node_id, deployment_id, or gpu_id.
        trigger_type: How the anomaly is activated.
        trigger_value: Activation parameter:
            - SCHEDULED: float (simulated minute to fire at).
            - CONDITIONAL: dict with keys ``metric``, ``threshold``, ``window_ticks``.
            - RANDOM: dict with keys ``probability_per_tick`` and optionally
              ``window_start`` / ``window_end`` (simulated minutes).
        severity: How severe — 0.0 (mild) to 1.0 (total failure).
        duration_minutes: How long the anomaly lasts in simulated time.
    """

    anomaly_id: str = Field(..., description="Unique anomaly identifier")
    anomaly_type: AnomalyType = Field(..., description="Type of failure to simulate")
    target: str = Field(..., description="Target entity (node, deployment, or GPU ID)")
    trigger_type: TriggerType = Field(..., description="How this anomaly activates")
    trigger_value: Any = Field(..., description="Trigger parameter (float, dict, etc.)")
    severity: float = Field(default=1.0, ge=0.0, le=1.0, description="Severity 0.0–1.0")
    duration_minutes: float = Field(default=5.0, gt=0.0, description="Duration in simulated minutes")


class ActiveAnomaly(BaseModel):
    """Runtime state of a currently active anomaly."""

    definition: AnomalyDefinition
    started_at_minute: float = Field(..., description="Simulated minute when activated")
    remaining_minutes: float = Field(..., description="Time left before expiry")



