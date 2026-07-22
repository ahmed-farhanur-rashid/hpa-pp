"""Scaling decision data models — the audit trail.

Every scaling action is fully logged with its forecast values,
risk score, confidence bounds, and the exact formula that triggered it.
This makes HPA++ fully explainable and debuggable.
"""

from pydantic import Field

from shared.base import AuditModel, TimestampedModel
from shared.enums import ScalingAction


class ScalingConfig(TimestampedModel):
    """Per-deployment configuration that governs scaling behaviour.

    Each deployment has its own scaling bounds, risk tolerance,
    and capacity baseline. These are loaded from the database or
    API at startup and can be updated at runtime.
    """

    deployment_id: str = Field(
        ...,
        description="Deployment this configuration applies to",
    )
    min_replicas: int = Field(
        default=1,
        ge=1,
        description="Minimum number of replicas (hard floor)",
    )
    max_replicas: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of replicas (hard ceiling)",
    )
    baseline_per_pod: float = Field(
        default=100.0,
        ge=1.0,
        description="Estimated requests per second one pod can handle at target load",
    )
    risk_asymmetry_factor: float = Field(
        default=5.0,
        ge=1.0,
        description="Cost ratio: how much more expensive under-provisioning is vs over-provisioning",
    )
    cooldown_seconds: int = Field(
        default=60,
        ge=0,
        description="Minimum seconds between consecutive scaling actions",
    )
    upscale_cpu_threshold_pct: float = Field(
        default=70.0,
        ge=0.0,
        le=100.0,
        description="CPU threshold that triggers emergency reactive scale-up",
    )


class ScalingDecision(AuditModel):
    """Complete record of one scaling decision.

    Contains every input, intermediate value, and output so that
    any scaling action can be audited and explained. This is the
    core explainability contract of HPA++.
    """

    decision_id: str = Field(
        ...,
        description="Unique decision identifier (UUID)",
    )
    deployment_id: str = Field(
        ...,
        description="Deployment this decision applies to",
    )
    simulated_time_utc: str = Field(
        ...,
        description="Simulation clock time when the decision was made (ISO 8601 UTC)",
    )

    # ── State at decision time ──
    current_pod_count: int = Field(
        ...,
        ge=0,
        description="Number of running pods when the decision was made",
    )
    target_pod_count: int = Field(
        ...,
        ge=0,
        description="Recommended number of pods after scaling logic",
    )
    action: ScalingAction = Field(
        ...,
        description="The scaling action taken or recommended",
    )

    # ── Forecast inputs ──
    forecast_id: str | None = Field(
        default=None,
        description="ForecastWindow.forecast_id that drove this decision",
    )
    forecast_yhat: float = Field(
        ...,
        description="Point forecast from Prophet (requests per second)",
    )
    forecast_lower: float = Field(
        ...,
        description="Lower bound of forecast confidence interval (requests per second)",
    )
    forecast_upper: float = Field(
        ...,
        description="Upper bound of forecast confidence interval (requests per second)",
    )

    # ── Risk awareness ──
    risk_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Aggregate risk score (0 = no risk, 1 = maximum risk)",
    )
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Forecast confidence (1 = Prophet is very certain, 0 = very uncertain)",
    )
    risk_level: str = Field(
        default="medium",
        description="Qualitative risk level derived from risk_score",
    )

    # ── Formula breakdown (full explainability) ──
    formula_raw_target: float = Field(
        ...,
        description="Step 1: raw_target = ceil(forecast_yhat / baseline_per_pod)",
    )
    formula_confidence_factor: float = Field(
        ...,
        description="Step 2: how forecast uncertainty scaled the decision (0 = conservative, 1 = aggressive)",
    )
    formula_risk_bias: float = Field(
        ...,
        description="Step 3: how risk_score * asymmetry_factor biased the target",
    )
    formula_final_before_clamp: float = Field(
        ...,
        description="Step 4: target before min/max replica clamping",
    )

    # ── Outcome ──
    executed: bool = Field(
        default=False,
        description="Whether the scaling action was actually applied (True) or just logged (False / dry-run)",
    )
    execution_source: str = Field(
        default="predictive",
        description="Source: 'predictive' — HPA++ decision, 'reactive' — fallback HPA safety net, 'manual' — user override",
    )
    reason: str = Field(
        default="",
        description="Human-readable explanation of the decision for the audit log",
    )
