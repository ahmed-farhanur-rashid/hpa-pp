"""Tests for ForecastingModel (app/model.py).

Stubs only — TODO: implement test cases with Prophet mock/fixture.
"""

import pytest


class TestForecastingModelInit:
    """Tests for ForecastingModel.__init__."""

    def test_default_construction(self) -> None:
        """Model should construct with default parameters.

        TODO: verify default seasonality and changepoint values.
        """
        ...

    def test_custom_construction(self) -> None:
        """Model should accept custom configuration.

        TODO: verify seasonality_weekly=True and custom changepoint.
        """
        ...

    def test_invalid_changepoint_prior_scale(self) -> None:
        """Should raise ValueError for changepoint_prior_scale outside [0.001, 1.0].

        TODO: test both too-low and too-high values.
        """
        ...


class TestForecastingModelTrain:
    """Tests for ForecastingModel.train."""

    def test_train_valid_data(self) -> None:
        """Model should train on valid ds/y DataFrame.

        TODO: mock Prophet.fit() and verify it was called.
        """
        ...

    def test_train_insufficient_rows(self) -> None:
        """Should raise ValueError if df has fewer than 10 rows.

        TODO: test with 0, 5, 9 rows.
        """
        ...

    def test_train_missing_columns(self) -> None:
        """Should raise ValueError if df is missing 'ds' or 'y'.

        TODO: test with various missing column combinations.
        """
        ...

    def test_train_prophet_failure(self) -> None:
        """Should raise RuntimeError if Prophet fails to converge.

        TODO: mock Prophet.fit() to raise an exception.
        """
        ...


class TestForecastingModelPredict:
    """Tests for ForecastingModel.predict."""

    def test_predict_default_horizon(self) -> None:
        """Should return DataFrame with default 30-minute horizon.

        TODO: verify column names and types.
        """
        ...

    def test_predict_custom_horizon(self) -> None:
        """Should respect custom horizon_minutes parameter.

        TODO: verify row count matches horizon.
        """
        ...

    def test_predict_untrained(self) -> None:
        """Should raise RuntimeError if called before training.

        TODO: verify error message is informative.
        """
        ...

    def test_predict_invalid_horizon(self) -> None:
        """Should raise ValueError for horizon outside [1, 1440].

        TODO: test 0 and 1441.
        """
        ...


class TestForecastingModelEvaluate:
    """Tests for ForecastingModel.evaluate."""

    def test_evaluate_returns_metrics(self) -> None:
        """Should return dict with rmse, mae, mape_pct.

        TODO: verify all three keys exist and are non-negative.
        """
        ...

    def test_evaluate_insufficient_test_data(self) -> None:
        """Should raise ValueError if test_df has fewer than 5 rows.

        TODO: test with 0, 3 rows.
        """
        ...


class TestForecastingModelSaveLoad:
    """Tests for ForecastingModel.save and .load."""

    def test_save_load_roundtrip(self) -> None:
        """Saved model should load back with same configuration.

        TODO: use tmp_path fixture, verify model_version matches.
        """
        ...

    def test_load_nonexistent(self) -> None:
        """Should raise FileNotFoundError for missing model file.

        TODO: verify error message.
        """
        ...
