"""Tests for feature extraction (app/features.py).

Stubs only — TODO: implement test cases with MetricSample fixtures.
"""

import pytest


class TestExtractTrainingData:
    """Tests for extract_training_data."""

    def test_valid_samples(self) -> None:
        """Should return DataFrame with ds and y columns.

        TODO: create 20 MetricSamples for one deployment, verify output shape.
        """
        ...

    def test_filters_by_deployment_id(self) -> None:
        """Should only include samples matching target_deployment_id.

        TODO: mix samples from two deployments, verify filtering.
        """
        ...

    def test_resamples_to_1_minute(self) -> None:
        """Should resample to 1-minute buckets with mean aggregation.

        TODO: create sub-minute samples, verify bucket count.
        """
        ...

    def test_respects_window_minutes(self) -> None:
        """Should exclude samples older than the window.

        TODO: create samples spanning 120 minutes, window=60, verify count.
        """
        ...

    def test_no_samples_for_deployment(self) -> None:
        """Should raise ValueError if no samples match.

        TODO: pass empty list and non-matching deployment_id.
        """
        ...

    def test_insufficient_after_resample(self) -> None:
        """Should raise ValueError if fewer than 2 rows after resampling.

        TODO: create only 1 sample within the window.
        """
        ...

    def test_invalid_metric_field(self) -> None:
        """Should raise ValueError for non-existent metric_field.

        TODO: pass "nonexistent_field".
        """
        ...


class TestAddOptionalRegressors:
    """Tests for add_optional_regressors."""

    def test_adds_cpu_regressor(self) -> None:
        """Should add cpu_utilization_pct column.

        TODO: verify column exists and values align with ds timestamps.
        """
        ...

    def test_handles_missing_ds_column(self) -> None:
        """Should raise ValueError if df lacks 'ds' column.

        TODO: pass DataFrame with only 'y' column.
        """
        ...

    def test_preserves_original_columns(self) -> None:
        """Should not modify existing ds/y columns.

        TODO: verify original values unchanged.
        """
        ...


class TestComputeForecastUncertainty:
    """Tests for compute_forecast_uncertainty."""

    def test_narrow_interval(self) -> None:
        """Should return low uncertainty for narrow intervals.

        TODO: create forecast_df where yhat_upper ≈ yhat_lower.
        """
        ...

    def test_wide_interval(self) -> None:
        """Should return high uncertainty for wide intervals.

        TODO: create forecast_df where yhat_upper >> yhat_lower.
        """
        ...

    def test_empty_forecast(self) -> None:
        """Should raise ValueError for empty DataFrame.

        TODO: pass pd.DataFrame().
        """
        ...

    def test_zero_mean_yhat(self) -> None:
        """Should raise ValueError when mean(yhat) is zero.

        TODO: create forecast_df with all-zero yhat values.
        """
        ...

    def test_score_range(self) -> None:
        """Score should always be between 0.0 and 1.0.

        TODO: test with various interval widths.
        """
        ...
