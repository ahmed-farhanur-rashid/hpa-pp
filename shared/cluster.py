"""Cluster state models — nodes, pods, deployments, and full snapshots.

These models represent the simulated Kubernetes cluster state.
The simulation owns building them, the controller reads them,
and the dashboard renders them.
"""

from pydantic import Field

from shared.base import AuditModel, TimestampedModel
from shared.enums import PodStatus, NodeStatus


class PodState(TimestampedModel):
    """Represents a single pod in the simulated cluster.

    Tracks resource requests, current usage, node assignment,
    and GPU attachment.
    """

    pod_id: str = Field(
        ...,
        description="Unique pod identifier (e.g., 'web-app-6b4f9c7d8f-abc12')",
    )
    deployment_id: str = Field(
        ...,
        description="Deployment that owns this pod",
    )
    status: PodStatus = Field(
        ...,
        description="Current pod lifecycle status",
    )
    node_id: str | None = Field(
        default=None,
        description="Node the pod is scheduled on (None if pending/unscheduled)",
    )

    # ── Resource requests ──
    cpu_request_millicores: int = Field(
        ...,
        ge=0,
        description="CPU resource request in millicores (1000 = 1 core)",
    )
    memory_request_mb: int = Field(
        ...,
        ge=0,
        description="Memory resource request in megabytes",
    )

    # ── GPU ──
    gpu_id: str | None = Field(
        default=None,
        description="GPU device assigned to this pod (None if no GPU needed)",
    )
    gpu_memory_request_mb: int = Field(
        default=0,
        ge=0,
        description="GPU memory request in megabytes (0 if no GPU)",
    )

    # ── Current usage (updated each tick) ──
    current_cpu_util_pct: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Current CPU usage as percentage of requested CPU",
    )
    current_memory_mb: float = Field(
        default=0.0,
        ge=0.0,
        description="Current memory usage in megabytes",
    )
    current_gpu_util_pct: float | None = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Current GPU usage as percentage of allocated GPU (None if no GPU)",
    )
    age_seconds: float = Field(
        default=0.0,
        ge=0.0,
        description="How long the pod has been running in simulated seconds",
    )


class NodeState(TimestampedModel):
    """Represents a single node (worker machine) in the simulated cluster.

    Tracks total and allocated resources, attached GPUs,
    and all pods scheduled on this node.
    """

    node_id: str = Field(
        ...,
        description="Unique node identifier",
        examples=["node-0", "worker-3"],
    )
    status: NodeStatus = Field(
        default=NodeStatus.READY,
        description="Node readiness status",
    )

    # ── Capacity ──
    total_cpu_millicores: int = Field(
        ...,
        ge=1,
        description="Total CPU capacity in millicores",
    )
    total_memory_mb: int = Field(
        ...,
        ge=1,
        description="Total memory capacity in megabytes",
    )

    # ── Allocation ──
    allocated_cpu_millicores: int = Field(
        default=0,
        ge=0,
        description="Sum of CPU requests from all pods on this node",
    )
    allocated_memory_mb: int = Field(
        default=0,
        ge=0,
        description="Sum of memory requests from all pods on this node",
    )
    allocated_gpu_memory_mb: int = Field(
        default=0,
        ge=0,
        description="Sum of GPU memory allocated on this node",
    )

    # ── GPIO ──
    gpu_ids: list[str] = Field(
        default_factory=list,
        description="GPU device IDs attached to this node",
    )
    total_gpu_memory_mb: int = Field(
        default=0,
        ge=0,
        description="Total GPU memory across all GPUs on this node",
    )

    # ── Pods ──
    pods: list[PodState] = Field(
        default_factory=list,
        description="All pods scheduled on this node",
    )

    @property
    def cpu_utilization_pct(self) -> float:
        """Overall CPU utilisation percentage on this node."""
        if self.total_cpu_millicores == 0:
            return 0.0
        return (self.allocated_cpu_millicores / self.total_cpu_millicores) * 100.0


class DeploymentState(TimestampedModel):
    """Represents a Kubernetes Deployment and its current state.

    The controller reads this to know current replica counts.
    The dashboard renders it for the cluster overview.
    """

    deployment_id: str = Field(
        ...,
        description="Deployment name",
    )
    current_replicas: int = Field(
        ...,
        ge=0,
        description="Number of currently running replicas",
    )
    target_replicas: int | None = Field(
        default=None,
        ge=0,
        description="Target replica count from latest scaling decision (None if no pending change)",
    )
    available_replicas: int = Field(
        default=0,
        ge=0,
        description="Number of replicas that are Ready and accepting traffic",
    )
    pods: list[PodState] = Field(
        default_factory=list,
        description="All pods belonging to this deployment",
    )
    cpu_request_millicores: int = Field(
        default=0,
        ge=0,
        description="CPU request per pod in millicores",
    )
    memory_request_mb: int = Field(
        default=0,
        ge=0,
        description="Memory request per pod in megabytes",
    )
    requires_gpu: bool = Field(
        default=False,
        description="Whether pods in this deployment require GPU resources",
    )


class ClusterSnapshot(AuditModel):
    """Point-in-time snapshot of the entire simulated cluster.

    Produced periodically by the simulation and consumed by
    the dashboard for the cluster overview panel.
    """

    snapshot_id: str = Field(
        ...,
        description="Unique snapshot identifier (UUID)",
    )
    simulated_time_utc: str = Field(
        ...,
        description="Simulation time when this snapshot was taken (ISO 8601 UTC)",
    )

    # ── Topology ──
    nodes: list[NodeState] = Field(
        ...,
        description="All nodes in the cluster",
    )
    deployments: list[DeploymentState] = Field(
        ...,
        description="All deployments in the cluster",
    )

    # ── Aggregate counts ──
    total_pods: int = Field(
        ...,
        ge=0,
        description="Total pod count across all deployments",
    )
    running_pods: int = Field(
        ...,
        ge=0,
        description="Pods in Running status",
    )
    pending_pods: int = Field(
        ...,
        ge=0,
        description="Pods in Pending status",
    )
    gpu_count: int = Field(
        ...,
        ge=0,
        description="Total GPU devices across all nodes",
    )
    gpu_utilization_avg_pct: float | None = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Average GPU utilisation across all GPUs",
    )

    # ── Resource summary ──
    total_cpu_millicores: int = Field(
        ...,
        ge=0,
        description="Total CPU capacity across all nodes",
    )
    allocated_cpu_millicores: int = Field(
        ...,
        ge=0,
        description="Total allocated CPU across all nodes",
    )
    total_memory_mb: int = Field(
        ...,
        ge=0,
        description="Total memory capacity across all nodes",
    )
    allocated_memory_mb: int = Field(
        ...,
        ge=0,
        description="Total allocated memory across all nodes",
    )
