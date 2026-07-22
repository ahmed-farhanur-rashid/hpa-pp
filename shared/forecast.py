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
