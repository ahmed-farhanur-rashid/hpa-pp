"""Metric data models — the common observability language.

Every service that reads or writes metrics uses these models.
All quantity field names explicitly state their units per RULE 1.2.
"""

from datetime import datetime

from pydantic import Field

from shared.base import AuditModel, TimestampedModel


class MetricSample(AuditModel):
    """Single metric observation from one deployment at one simulated time.

    This is the fundamental observability unit. Every other service
    either produces, consumes, or visualises MetricSamples.

    TODO: Consider adding a 'source' field to distinguish between
          simulated and real-cluster metrics.
    """

    deployment_id: str = Field(
        ...,
        description="Unique deployment identifier (e.g., 'web-app', 'api-gateway')",
        examples=["web-app-v2"],
        min_length=1,
        max_length=128,
    )
    simulated_time_utc: datetime = Field(
        ...,
        description="Simulation clock time when this sample was generated (UTC)",
    )

    # ── Resource Utilization (units explicitly stated per RULE 1.2) ──
    cpu_utilization_pct: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="CPU utilization as percentage of requested CPU",
    )
    memory_usage_mb: float = Field(
        ...,
        ge=0.0,
        description="Memory usage in megabytes",
    )
    requests_per_second: float = Field(
        ...,
        ge=0.0,
        description="Incoming request rate (requests per second)",
    )

    # ── Optional / GPU metrics ──
    gpu_utilization_pct: float | None = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="GPU utilization percentage (None if deployment has no GPU)",
    )
    gpu_memory_used_mb: float | None = Field(
        default=None,
        ge=0.0,
        description="GPU memory used in megabytes",
    )
    latency_ms: float | None = Field(
        default=None,
        ge=0.0,
        description="Request p99 latency in milliseconds",
    )
    pod_count: int = Field(
        default=1,
        ge=0,
        description="Number of running pods at the time of this sample",
    )


class MetricBatch(TimestampedModel):
    """Batch of metric samples for bulk insert or transport.

    Used when the simulation emits multiple samples at once
    (e.g., one per deployment per tick).
    """

    samples: list[MetricSample] = Field(
        ...,
        min_length=1,
        description="Collection of metric samples in this batch",
    )
    source_id: str = Field(
        ...,
        description="Source identifier (e.g., 'cluster_sim', 'prometheus_scraper')",
    )
    batch_sequence: int = Field(
        default=0,
        ge=0,
        description="Monotonic batch sequence number for ordering",
    )
