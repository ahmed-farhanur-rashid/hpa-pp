"""Fallback strategies when Prophet is unavailable or insufficient.

Provides naive forecasting and baseline metrics so the pipeline
never crashes — it degrades gracefully to simple heuristics.
"""

from __future__ import annotations

import pandas as pd

from shared.metrics import MetricSample


def generate_naive_forecast(
    last_value: float,
    horizon_minutes: int = 30,
    confidence_interval_pct: float = 20.0,
) -> pd.DataFrame:
    """Generate a naive forecast when Prophet is unavailable.

    Uses the last known value as the prediction for all future points,
    with a flat confidence interval based on historical variance.

    This ensures the pipeline never crashes — it degrades gracefully.

    Args:
        last_value: The most recent observed metric value (e.g., rps).
            Must be non-negative.
        horizon_minutes: How many minutes to forecast ahead.
            Default: 30. Must be between 1 and 1440.
        confidence_interval_pct: Width of confidence band as a percentage
            of last_value. Default: 20.0 (±10% around the point forecast).

    Returns:
        pd.DataFrame with columns matching ForecastingModel.predict():
            - ds (datetime): UTC timestamps at 1-minute intervals
                starting from now.
            - yhat (float): Constant value equal to last_value.
            - yhat_lower (float): last_value * (1 - ci_pct/200).
            - yhat_upper (float): last_value * (1 + ci_pct/200).

    Raises:
        ValueError: If last_value is negative.
        ValueError: If horizon_minutes is outside [1, 1440].
        ValueError: If confidence_interval_pct is negative or > 100.

    TODO:
        - Add trend detection (rising/falling last_value)
        - Support seasonal naive (last value from same time yesterday)
        - Add noise proportional to historical standard deviation
        """
    ...


def detect_insufficient_data(
    samples: list[MetricSample],
    min_samples: int = 10,
) -> bool:
    """Check if there is enough data for Prophet training.

    Evaluates whether the provided samples meet the minimum
    requirements for a meaningful Prophet fit. If False, the
    pipeline should fall back to naive forecasting.

    Args:
        samples: The raw MetricSample records available for training.
        min_samples: Minimum number of samples required. Default: 10.
            Prophet needs at least a few points to detect seasonality
            and changepoints.

    Returns:
        True if data is sufficient for Prophet, False if fallback
        should be used.

    TODO:
        - Add check for minimum time span (not just count)
        - Detect flat/constant series (variance == 0)
        - Check for large gaps in timestamps
        """
    ...


def compute_baseline_metrics(
    samples: list[MetricSample],
) -> dict[str, float]:
    """Compute baseline statistics when no forecast is possible.

    Provides simple descriptive statistics for the "insufficient data"
    state. The dashboard uses these to display current conditions
    when no forecast is available.

    Args:
        samples: The raw MetricSample records available.
            Each must have a requests_per_second field.

    Returns:
        dict[str, float] with keys:
            - 'mean_rps': Mean requests per second.
            - 'median_rps': Median requests per second.
            - 'min_rps': Minimum requests per second.
            - 'max_rps': Maximum requests per second.
            - 'std_rps': Standard deviation of requests per second.
            - 'sample_count': Number of samples processed.

    Raises:
        ValueError: If samples is empty.

    TODO:
        - Add percentile calculations (p50, p95, p99)
        - Compute baseline for cpu and memory as well
        - Return TrendDirection enum (rising/falling/stable)
        """
    ...
