"""Simulation configuration models — traffic profiles and cluster setup.

These models define what the cluster simulation will look like:
which deployments exist, how traffic behaves, and the simulation
clock parameters. They are consumed by the SimulationEngine.
"""

from pydantic import Field

from shared.base import TimestampedModel
from shared.enums import TrafficPattern, SimulatorStatus
from shared.decisions import ScalingConfig


class TrafficProfile(TimestampedModel):
    """Configuration for a traffic generation pattern.

    Each pattern type produces a different timeseries shape.
    The simulation uses this to generate realistic metric samples.
    """

    pattern: TrafficPattern = Field(
        ...,
        description="The traffic shape to generate",
    )
    base_load_rps: float = Field(
        default=50.0,
        ge=0.0,
        description="Baseline load in requests per second",
    )
    spike_multiplier: float = Field(
        default=5.0,
        ge=1.0,
        description="Peak multiplier for spike patterns (e.g., 5x base load)",
    )
    noise_std_pct: float = Field(
        default=5.0,
        ge=0.0,
        le=50.0,
        description="Gaussian noise standard deviation as percentage of base load",
    )
    period_minutes: int | None = Field(
        default=None,
        ge=1,
        description="Period for sine/cyclic patterns in simulated minutes",
    )
    spike_minute: int | None = Field(
        default=None,
        ge=0,
        description="Simulated minute when step/flash spike should occur",
    )
    spike_duration_minutes: int | None = Field(
        default=None,
        ge=1,
        description="Duration of the spike in simulated minutes",
    )
    trend_gradient: float = Field(
        default=0.0,
        description="Linear trend added per minute (e.g., 0.5 = +0.5 rps per minute)",
    )


class DeploymentSpec(TimestampedModel):
    """Complete specification for one deployment in the simulation.

    Combines resource requirements, traffic profile, and scaling config
    into a single spec that the simulation uses to create and manage
    a deployment over time.
    """

    deployment_id: str = Field(
        ...,
        description="Unique deployment name",
        examples=["web-app", "api-gateway", "worker-service"],
    )
    initial_replicas: int = Field(
        default=2,
        ge=1,
        description="Number of pods to start with",
    )

    # ── Resource requests per pod ──
    cpu_request_millicores: int = Field(
        default=500,
        ge=1,
        description="CPU request per pod in millicores",
    )
    memory_request_mb: int = Field(
        default=512,
        ge=1,
        description="Memory request per pod in megabytes",
    )
    gpu_required: bool = Field(
        default=False,
        description="Whether pods in this deployment require GPU resources",
    )
    gpu_memory_request_mb: int = Field(
        default=0,
        ge=0,
        description="GPU memory request per pod in megabytes (0 if no GPU)",
    )

    # ── Behaviour ──
    traffic_profile: TrafficProfile = Field(
        default_factory=lambda: TrafficProfile(pattern=TrafficPattern.STEADY),
        description="Traffic pattern for this deployment",
    )
    scaling_config: ScalingConfig | None = Field(
        default=None,
        description="Per-deployment scaling config (falls back to defaults if None)",
    )

    # ── Metadata ──
    labels: dict[str, str] = Field(
        default_factory=dict,
        description="Kubernetes-style labels for filtering and grouping",
    )


class SimulationConfig(TimestampedModel):
    """Top-level configuration for an entire simulation run.

    Defines the cluster topology, all deployments, simulation speed,
    and total duration. Passed to SimulationEngine at startup.
    """

    sim_name: str = Field(
        default="hpa_plus_plus_demo",
        description="Human-readable name for this simulation run",
    )

    # ── Timing ──
    tick_interval_real_seconds: float = Field(
        default=0.5,
        ge=0.1,
        le=10.0,
        description="Wall-clock seconds between simulation ticks",
    )
    seconds_per_simulated_minute: float = Field(
        default=0.5,
        ge=0.1,
        description="How many real seconds equal one simulated minute (controls speed)",
    )
    total_simulated_minutes: int = Field(
        default=120,
        ge=1,
        le=1440,
        description="Total simulation duration in simulated minutes",
    )

    # ── Cluster topology ──
    node_count: int = Field(
        default=3,
        ge=1,
        le=100,
        description="Number of worker nodes in the simulated cluster",
    )
    cpu_per_node_millicores: int = Field(
        default=4000,
        ge=100,
        description="CPU capacity per node in millicores",
    )
    memory_per_node_mb: int = Field(
        default=8192,
        ge=128,
        description="Memory capacity per node in megabytes",
    )
    gpus_per_node: int = Field(
        default=1,
        ge=0,
        le=8,
        description="GPU devices per node (0 = no GPUs)",
    )
    gpu_memory_per_device_mb: int = Field(
        default=16384,
        ge=0,
        description="Memory per GPU device in megabytes",
    )

    # ── Workload ──
    deployments: list[DeploymentSpec] = Field(
        default_factory=list,
        min_length=1,
        description="Deployments to simulate",
    )

    # ── Reproducibility ──
    seed: int | None = Field(
        default=None,
        description="Random seed for deterministic simulation output",
    )
