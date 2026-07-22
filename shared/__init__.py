# ═══════════════════════════════════════════════════════════════════════
# HPA++ Shared Schema Registry
# ═══════════════════════════════════════════════════════════════════════
# RULE 1.1: Single Schema Registry
# No domain team may define top-level data models locally.
# Every shared object, event, or payload MUST be pulled from this package.
# ═══════════════════════════════════════════════════════════════════════

from shared.base import TimestampedModel, AuditModel
from shared.enums import (
    PodStatus,
    TrafficPattern,
    RiskLevel,
    ScalingAction,
    NodeStatus,
    GpuStatus,
)
from shared.metrics import MetricSample, MetricBatch
from shared.forecast import ForecastWindow, ForecastMetadata
from shared.decisions import ScalingDecision, ScalingConfig
from shared.gpu import GpuSpec, GpuAssignment, GpuRebalanceEvent
from shared.cluster import (
    PodState,
    NodeState,
    DeploymentState,
    ClusterSnapshot,
)
from shared.simulation import (
    TrafficProfile,
    DeploymentSpec,
    SimulationConfig,
    SimulatorStatus,
)
from shared.api import ApiResponse, ErrorResponse, PaginatedResponse

__all__ = [
    # Base
    "TimestampedModel",
    "AuditModel",
    # Enums
    "PodStatus",
    "TrafficPattern",
    "RiskLevel",
    "ScalingAction",
    "NodeStatus",
    "GpuStatus",
    # Metrics
    "MetricSample",
    "MetricBatch",
    # Forecast
    "ForecastWindow",
    "ForecastMetadata",
    # Decisions
    "ScalingDecision",
    "ScalingConfig",
    # GPU
    "GpuSpec",
    "GpuAssignment",
    "GpuRebalanceEvent",
    # Cluster
    "PodState",
    "NodeState",
    "DeploymentState",
    "ClusterSnapshot",
    # Simulation
    "TrafficProfile",
    "DeploymentSpec",
    "SimulationConfig",
    "SimulatorStatus",
    # API
    "ApiResponse",
    "ErrorResponse",
    "PaginatedResponse",
]
