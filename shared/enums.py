"""Shared enumerations used across all HPA++ services.

Every enum is defined here — no service defines its own.
This prevents drift and ensures consistent serialization across boundaries.
"""

from enum import Enum


class PodStatus(str, Enum):
    """Lifecycle status of a simulated or real Kubernetes pod.

    Maps to the Kubernetes PodPhase values:
    https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-phase
    """

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    EVICTED = "evicted"
    UNKNOWN = "unknown"


class NodeStatus(str, Enum):
    """Readiness status of a cluster node."""

    READY = "ready"
    NOT_READY = "not_ready"
    CORDONED = "cordoned"
    DISK_PRESSURE = "disk_pressure"
    MEM_PRESSURE = "mem_pressure"
    UNKNOWN = "unknown"


class GpuStatus(str, Enum):
    """Allocation status of a GPU device."""

    FREE = "free"
    ALLOCATED = "allocated"
    OVERCOMMITTED = "overcommitted"
    DEGRADED = "degraded"
    OFFLINE = "offline"


class TrafficPattern(str, Enum):
    """Named traffic shape for the simulation metric generator.

    Each pattern produces a distinct requests_per_second profile over time.
    Used to test the forecasting engine under different conditions.
    """

    STEADY = "steady"
    SINE_WAVE = "sine_wave"
    STEP_SPIKE = "step_spike"
    FLASH_SALE = "flash_sale"
    EXAM_START = "exam_start"
    RANDOM_WALK = "random_walk"
    CUSTOM = "custom"


class RiskLevel(str, Enum):
    """Qualitative risk level for scaling decisions."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ScalingAction(str, Enum):
    """Action taken or recommended by the predictive controller."""

    SCALE_UP = "scale_up"
    SCALE_DOWN = "scale_down"
    HOLD = "hold"
    EMERGENCY_SCALE_UP = "emergency_scale_up"


class SimulatorStatus(str, Enum):
    """Runtime state of the simulation engine."""

    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    COMPLETED = "completed"
