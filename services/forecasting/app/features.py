"""Feature extraction from raw MetricSamples.

Transforms simulation metric data into Prophet-ready training DataFrames.
Also computes optional regressors and uncertainty scores.
"""

from __future__ import annotations

import pandas as pd

from shared.metrics import MetricSample


def extract_training_data(
    metric_samples: list[MetricSample],
    target_deployment_id: str,
    window_minutes: int = 60,
    metric_field: str = "requests_per_second",
) -> pd.DataFrame:
    """Transform raw MetricSamples into a Prophet-ready DataFrame.

    Steps:
    1. Filter samples for the target deployment.
    2. Sort by simulated_time_utc.
    3. Resample to 1-minute buckets (mean aggregation).
    4. Create ds (datetime) and y (requests_per_second) columns.
    5. Return pd.DataFrame with ds and y.

    The y column represents the primary metric being forecast —
    typically requests_per_second, but configurable via metric_field.

    Args:
        metric_samples: Raw MetricSample records from the simulation.
            Each sample contains deployment_id, simulated_time_utc,
            and various metric fields (cpu, memory, rps, gpu, etc.).
        target_deployment_id: Which deployment to extract data for.
            Samples with non-matching deployment_id are discarded.
        window_minutes: How many minutes of history to include.
            Samples older than (max_time - window_minutes) are dropped.
            Default: 60 minutes.
        metric_field: Which MetricSample field to use as the y variable.
            Default: "requests_per_second". Must be a valid field name
            on MetricSample that returns a float.

    Returns:
        pd.DataFrame with columns:
            - ds (datetime): UTC timestamps at 1-minute intervals.
            - y (float): Aggregated metric value for each interval.

    Raises:
        ValueError: If no samples exist for the target deployment.
        ValueError: If the resulting DataFrame has fewer than 2 rows
            after resampling (insufficient data for Prophet).
        ValueError: If metric_field is not a valid MetricSample field.

    TODO:
        - Support multiple metric_field targets in one call
        - Add interpolation for missing timestamps
        - Handle timezone-aware vs naive datetime edge cases
    """
    ...


def add_optional_regressors(
    df: pd.DataFrame,
    metric_samples: list[MetricSample],
) -> pd.DataFrame:
    """Add extra regressors to the training DataFrame.

    Augments the ds/y DataFrame with additional columns that
    Prophet can use as extra regressors. These correlate with
    the primary metric and improve forecast accuracy.

    Currently supported regressors:
    - cpu_utilization_pct: CPU usage as percentage.
    - memory_usage_mb: Memory consumption in megabytes.
    - gpu_utilization_pct: GPU usage as percentage (if available).

    Args:
        df: The base training DataFrame with 'ds' and 'y' columns.
            Must already have datetime-indexed rows.
        metric_samples: The same raw MetricSamples used for
            extract_training_data(). Used to align additional metrics
            to the resampled timestamps.

    Returns:
        pd.DataFrame with the original ds/y columns plus any
        successfully aligned regressor columns.

    Raises:
        ValueError: If df does not contain a 'ds' column.

    TODO:
            - Implement CPU, memory, and GPU utilization as extra regressors
              to improve forecast accuracy for correlated metrics.
            - Handle missing values in regressor columns (forward-fill)
            - Validate regressor correlation before adding
        """
    ...


def compute_forecast_uncertainty(forecast_df: pd.DataFrame) -> float:
    """Compute the aggregate uncertainty of a forecast.

    Returns a normalised score (0.0 = very certain, 1.0 = very uncertain)
    based on the average width of confidence intervals across all
    forecast points.

    The score is computed as:
        mean_width = mean(yhat_upper - yhat_lower)
        normalised = min(1.0, mean_width / mean(yhat))

    This normalisation ensures the score is comparable across
    different scales (e.g., 10 rps vs 1000 rps).

    Args:
        forecast_df: DataFrame with columns 'yhat', 'yhat_lower',
            and 'yhat_upper' — the output of ForecastingModel.predict().

    Returns:
        float between 0.0 and 1.0 inclusive.

    Raises:
        ValueError: If forecast_df is empty or missing required columns.
        ValueError: If mean(yhat) is zero or negative (division safety).

    TODO:
            - Add per-point uncertainty scores (not just aggregate)
            - Support configurable confidence interval level
            - Return uncertainty breakdown by time horizon
        """
    ...
