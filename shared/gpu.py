"""GPU scheduling data models — assignments, specs, and rebalance events.

The GPU scheduler reads GPU specs and pod requirements, produces
assignments, and logs rebalancing events. These models define
the GPU resource management contract.
"""

from pydantic import Field

from shared.base import AuditModel, TimestampedModel
from shared.enums import GpuStatus


class GpuSpec(TimestampedModel):
    """Specification of a single GPU device in the simulated cluster.

    Each GPU has fixed capacity and tracks which deployment
    (if any) it is currently assigned to.
    """

    gpu_id: str = Field(
        ...,
        description="Unique GPU device identifier",
        examples=["gpu-0", "nvidia-tesla-t4-01"],
    )
    node_id: str = Field(
        ...,
        description="Node this GPU is attached to",
    )
    gpu_model: str = Field(
        default="NVIDIA-T4",
        description="GPU model name for display purposes",
    )
    total_memory_mb: int = Field(
        ...,
        ge=1,
        description="Total GPU memory in megabytes",
    )
    allocated_memory_mb: int = Field(
        default=0,
        ge=0,
        description="Currently allocated GPU memory in megabytes",
    )
    compute_units_total: float = Field(
        ...,
        ge=0.0,
        description="Abstract compute capacity units",
    )
    compute_units_used: float = Field(
        default=0.0,
        ge=0.0,
        description="Compute units currently in use",
    )
    status: GpuStatus = Field(
        default=GpuStatus.FREE,
        description="Current allocation status of this GPU",
    )
    assigned_deployment_id: str | None = Field(
        default=None,
        description="Deployment currently assigned to this GPU (None if free)",
    )


class GpuAssignment(AuditModel):
    """Assignment of a specific pod to a specific GPU device.

    Created by the GPU scheduler and consumed by the dashboard
    for visualizing GPU allocation.
    """

    assignment_id: str = Field(
        ...,
        description="Unique assignment record identifier (UUID)",
    )
    gpu_id: str = Field(
        ...,
        description="GPU device identifier",
    )
    pod_id: str = Field(
        ...,
        description="Pod identifier assigned to this GPU",
    )
    deployment_id: str = Field(
        ...,
        description="Deployment that owns this pod",
    )
    memory_allocated_mb: int = Field(
        ...,
        ge=1,
        description="GPU memory allocated to this pod in megabytes",
    )
    compute_allocated_pct: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Compute capacity allocated to this pod as percentage of GPU total",
    )
    effective_utilization_pct: float | None = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Actual utilisation observed (None if newly assigned and no data yet)",
    )


class GpuRebalanceEvent(AuditModel):
    """Record of a GPU rebalancing action.

    Triggered when contention is detected or when pod assignments
    change significantly. Logged for auditability.
    """

    event_id: str = Field(
        ...,
        description="Unique rebalance event identifier (UUID)",
    )
    trigger_reason: str = Field(
        ...,
        description="Why the rebalance was triggered",
        examples=[
            "gpu_overcommitted",
            "pod_terminated",
            "new_deployment",
            "scheduled_rebalance",
        ],
    )
    assignments_before: int = Field(
        ...,
        ge=0,
        description="Number of GPU assignments before rebalancing",
    )
    assignments_after: int = Field(
        ...,
        ge=0,
        description="Number of GPU assignments after rebalancing",
    )
    gpus_involved: list[str] = Field(
        default_factory=list,
        description="List of GPU IDs that were affected by the rebalance",
    )
    duration_ms: float = Field(
        default=0.0,
        ge=0.0,
        description="How long the rebalancing computation took in milliseconds",
    )
