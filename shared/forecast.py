"""Forecasting data models — Prophet predictions with confidence intervals.

The forecasting engine produces ForecastWindows and the metadata
about each training run. The controller consumes ForecastWindows.
"""

from datetime import datetime

from pydantic import Field

from shared.base import AuditModel, TimestampedModel


class ForecastWindow(AuditModel):
    """A single future prediction point produced by Prophet.

    Each record represents the forecast for ONE deployment at ONE
    future point in simulated time. The controller reads these to
    decide whether to scale.

    The confidence interval (yhat_lower, yhat_upper) is the key
    innovation — it enables risk-aware scaling.
    """

    forecast_id: str = Field(
        ...,
        description="Unique forecast record identifier (UUID)",
        examples=["f47ac10b-58cc-4372-a567-0e02b2c3d479"],
    )
    deployment_id: str = Field(
        ...,
        description="Target deployment for this forecast point",
    )
    forecast_time_utc: datetime = Field(
        ...,
        description="The future simulated time being predicted (UTC)",
    )
    generation_time_utc: datetime = Field(
        ...,
        description="When this forecast was generated (UTC)",
    )

    # ── Prophet output ──
    yhat: float = Field(
        ...,
        description="Point forecast value (requests per second)",
    )
    yhat_lower: float = Field(
        ...,
        description="Lower bound of the prediction interval (requests per second)",
    )
    yhat_upper: float = Field(
        ...,
        description="Upper bound of the prediction interval (requests per second)",
    )

    # ── Model provenance ──
    model_version: str = Field(
        ...,
        description="Model version identifier (timestamp-based: 'prophet_YYYYMMDD_HHMMSS')",
    )
    training_window_minutes: int = Field(
        ...,
        ge=1,
        description="Number of minutes of historical data used for training",
    )
    training_end_time_utc: datetime = Field(
        ...,
        description="End of the training data window (UTC)",
    )

    # ── Quality signals ──
    forecast_horizon_minutes: int = Field(
        default=30,
        ge=1,
        description="How many minutes ahead this forecast extends",
    )
    uncertainty_pct: float | None = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Normalized uncertainty: ((yhat_upper - yhat_lower) / yhat) * 100",
    )


# ── Multivariate forecast models (model-agnostic) ────────────────


class FeatureValue(TimestampedModel):
    """Predicted value of a single feature at one future time point.

    Supports any model type:
    - Prophet: sets value, lower, upper for yhat
    - CTGAN/Transformer: sets value only (or value + lower/upper
      from ensemble sampling)
    - Naive fallback: value = last observed, no confidence

    When `lower` and `upper` are absent, the controller defaults
    to neutral confidence (0.5) for risk-aware scaling.
    """

    value: float = Field(
        ...,
        description="Predicted value of this feature",
    )
    lower: float | None = Field(
        default=None,
        description="Lower bound of prediction interval (optional)",
    )
    upper: float | None = Field(
        default=None,
        description="Upper bound of prediction interval (optional)",
    )


class TrajectoryPoint(TimestampedModel):
    """Predicted system state at one future minute.

    Each point models the full multivariate outcome — a complete row
    of what CTGAN or a transformer would generate for a single
    future timestep.

    Example (CTGAN output):
        minute=21
        features={
            "requests_per_second": FeatureValue(value=145.2),
            "cpu_utilization_pct": FeatureValue(value=45.0),
            "gpu_utilization_pct": FeatureValue(value=24.5),
            "active_pods": FeatureValue(value=5),
            "is_flash_event_spike": FeatureValue(value=0.0),
        }
    """

    minute: int = Field(
        ...,
        ge=0,
        description="Simulated minute this prediction is for",
    )
    features: dict[str, FeatureValue] = Field(
        ...,
        description=(
            "Predicted feature values at this point. "
            "Keys are column names from the training data "
            "(requests_per_second, cpu_utilization_pct, "
            "gpu_utilization_pct, active_pods, …). "
            "Controller minimally requires 'requests_per_second'; "
            "GPU scheduler additionally reads 'gpu_utilization_pct'."
        ),
    )


class TrajectorySummary(TimestampedModel):
    """Aggregate statistics derived from the full trajectory.

    Computed once per forecast call so the controller and dashboard
    can read peak values without iterating through every point.
    """

    peak_requests_per_second: FeatureValue | None = Field(
        default=None,
        description="Maximum predicted RPS across all trajectory points",
    )
    peak_gpu_utilization_pct: FeatureValue | None = Field(
        default=None,
        description="Maximum predicted GPU util across all trajectory points",
    )
    peak_cpu_utilization_pct: FeatureValue | None = Field(
        default=None,
        description="Maximum predicted CPU util across all trajectory points",
    )
    peak_at_minute: int | None = Field(
        default=None,
        description="Simulated minute when the peak RPS occurs",
    )
    trend: str = Field(
        default="stable",
        pattern=r"^(rising|falling|stable)$",
        description=(
            "Overall trajectory direction. "
            "Controller uses 'rising' to apply urgency bias."
        ),
    )
    volatility: float = Field(
        default=0.0,
        ge=0.0,
        description=(
            "Coefficient of variation of yhat across all points. "
            "Higher values mean spikier predicted load → "
            "controller holds more buffer capacity."
        ),
    )
    uncertainty_pct: float | None = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description=(
            "Average normalised confidence interval width "
            "across all points. Higher = less certain forecast."
        ),
    )


class TrajectoryQuality(TimestampedModel):
    """Quality / accuracy metrics for the forecast trajectory.

    Metrics are keyed by feature name so each predicted column
    can carry its own error score.
    """

    status: str = Field(
        default="success",
        pattern=r"^(success|fallback|failed)$",
        description=(
            "'success' — real model used. "
            "'fallback' — naive forecast (insufficient data). "
            "'failed' — prediction unavailable, controller must "
            "rely on reactive scaling only."
        ),
    )
    rmse: dict[str, float] = Field(
        default_factory=dict,
        description="Root mean squared error per feature (e.g., {'requests_per_second': 12.3})",
    )
    mae: dict[str, float] = Field(
        default_factory=dict,
        description="Mean absolute error per feature",
    )
    mape_pct: dict[str, float] = Field(
        default_factory=dict,
        description="Mean absolute percentage error per feature (0–100%)",
    )


class ForecastTrajectory(TimestampedModel):
    """Complete multivariate forecast output.

    This is the PRIMARY output contract for the prediction engine.
    Every model type (Prophet, CTGAN, transformer, naive fallback)
    produces this shape. The controller and dashboard never touch
    the underlying model — they only read ForecastTrajectory.

    The `features_predicted` field tells consumers which features
    are available in each point. A Prophet model might only predict
    `requests_per_second`. A CTGAN might predict all 17 columns
    from the training dataset.
    """

    forecast_id: str = Field(
        ...,
        description="Unique forecast identifier (UUID)",
    )
    deployment_id: str = Field(
        ...,
        description="Target deployment for this forecast run",
    )
    generation_time_utc: datetime = Field(
        ...,
        description="When this forecast was generated (UTC)",
    )
    model_version: str = Field(
        ...,
        description=(
            "Model version identifier. Examples: "
            "'prophet_20260723_122000', 'ctgan_v2', 'naive_fallback'"
        ),
    )
    model_type: str = Field(
        default="prophet",
        pattern=r"^(prophet|transformer|ctgan|naive_fallback)$",
        description="Which model architecture produced this forecast",
    )
    training_window_minutes: int = Field(
        default=60,
        ge=1,
        description="Minutes of historical data used for training",
    )
    horizon_minutes: int = Field(
        default=30,
        ge=1,
        description="How many minutes into the future this forecast extends",
    )
    features_predicted: list[str] = Field(
        default_factory=list,
        description=(
            "List of feature names present in each trajectory point. "
            "E.g., ['requests_per_second', 'cpu_utilization_pct', …]. "
            "Controller checks 'requests_per_second' ∈ features_predicted."
        ),
    )
    points: list[TrajectoryPoint] = Field(
        ...,
        min_length=1,
        description=(
            "Time-ordered list of predicted system states, "
            "one per future minute."
        ),
    )
    summary: TrajectorySummary = Field(
        default_factory=TrajectorySummary,
        description="Aggregate statistics computed from all trajectory points",
    )
    quality: TrajectoryQuality = Field(
        default_factory=TrajectoryQuality,
        description="Model quality and accuracy metrics",
    )


class ForecastMetadata(TimestampedModel):
    """Metadata about a single Prophet model training run.

    Stored alongside forecast data to track model health and
    enable debugging of poor predictions.
    """

    model_version: str = Field(
        ...,
        description="Unique model version identifier (primary key-like)",
    )
    deployment_id: str = Field(
        ...,
        description="Deployment this model was trained for",
    )
    training_start_utc: datetime = Field(
        ...,
        description="Timestamp when training began (UTC)",
    )
    training_end_utc: datetime = Field(
        ...,
        description="Timestamp when training completed (UTC)",
    )
    data_window_minutes: int = Field(
        ...,
        ge=1,
        description="Duration of training data window in minutes",
    )
    data_points_count: int = Field(
        default=0,
        ge=0,
        description="Number of data points in the training window",
    )

    # ── Fit quality ──
    rmse: float | None = Field(
        default=None,
        ge=0.0,
        description="Root mean squared error on training data",
    )
    mae: float | None = Field(
        default=None,
        ge=0.0,
        description="Mean absolute error on training data",
    )
    mape_pct: float | None = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Mean absolute percentage error on training data",
    )

    # ── Seasonality configuration ──
    seasonality_daily: bool = Field(
        default=True,
        description="Whether daily seasonality was enabled",
    )
    seasonality_weekly: bool = Field(
        default=False,
        description="Whether weekly seasonality was enabled",
    )
    changepoint_prior_scale: float = Field(
        default=0.05,
        ge=0.001,
        le=1.0,
        description="Prophet changepoint prior scale (flexibility parameter)",
    )

    # ── Outcome ──
    status: str = Field(
        default="success",
        pattern=r"^(success|failed|fallback)$",
        description="Outcome: 'success' — normal, 'failed' — error, 'fallback' — naive model used",
    )
    error_message: str | None = Field(
        default=None,
        description="Error message if status is 'failed'",
    )
