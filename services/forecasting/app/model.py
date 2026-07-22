"""Prophet model wrapper — encapsulates all Prophet-specific logic.

The ForecastingModel class is the single interface between the
pipeline and Facebook Prophet. This isolation means:
- The pipeline never imports prophet directly
- Prophet version upgrades are local to this module
- Alternative models (e.g., NeuralProphet) can be swapped in
"""

from __future__ import annotations

from typing import Any

import pandas as pd


class ForecastingModel:
    """Wrapper around Facebook Prophet for time-series forecasting.

    Handles model creation, training, prediction, and serialization.
    Uses Prophet's native confidence intervals for risk-aware scaling.

    SOLID: Single responsibility — only Prophet operations.
    Open for extension via configuration, closed for modification.
    """

    def __init__(
        self,
        model_version: str,
        seasonality_daily: bool = True,
        seasonality_weekly: bool = False,
        changepoint_prior_scale: float = 0.05,
    ) -> None:
        """Initialise the Prophet model wrapper.

        Creates a Prophet instance with the given configuration.
        Does NOT train — call `.train()` after construction.

        Args:
            model_version: Version identifier for this model instance
                (e.g., "prophet_20260722_143000"). Used as a primary key
                in ForecastMetadata.
            seasonality_daily: Whether to enable Prophet's built-in
                daily Fourier seasonality. Useful for workload patterns
                that repeat every 24 hours.
            seasonality_weekly: Whether to enable Prophet's built-in
                weekly Fourier seasonality. Rarely needed for simulation
                timescales, but useful for long-running production data.
            changepoint_prior_scale: Prophet's flexibility parameter.
                Higher values (e.g., 0.1) allow more changepoints and
                tighter fits; lower values (e.g., 0.01) smooth over
                sudden shifts. Range: [0.001, 1.0].

        Returns:
            None. The model is stored as an internal attribute.

        Raises:
            ValueError: If changepoint_prior_scale is outside [0.001, 1.0].

        TODO:
            - Store configuration as a dataclass for serialisation
            - Add additional_seasonality parameter list
            - Support custom holiday events for production use
        """
        ...

    def train(self, df: pd.DataFrame) -> None:
        """Train the Prophet model on historical metric data.

        Fits the internal Prophet model to the provided time series.
        The DataFrame must have columns 'ds' (datetime) and 'y' (float).

        Args:
            df: Training data with columns:
                - 'ds' (datetime): Timestamps in UTC, monotonically increasing.
                - 'y' (float): The metric value to forecast (e.g., requests_per_second).
                Must contain at least 10 rows for a meaningful fit.

        Returns:
            None. The trained model is stored internally and can be
            called via `.predict()`.

        Raises:
            ValueError: If df has fewer than 10 rows.
            ValueError: If df is missing required columns 'ds' or 'y'.
            RuntimeError: If Prophet fails to converge during fitting.

        TODO:
            - Handle irregular time spacing (resample before training)
            - Detect and warn about flat/constant series
            - Log changepoint detection results
        """
        ...

    def predict(self, horizon_minutes: int = 30) -> pd.DataFrame:
        """Generate forecast for the specified horizon.

        Uses the trained model to predict future values. Returns a
        DataFrame with point forecasts and confidence intervals.

        The confidence interval width (yhat_upper - yhat_lower) is the
        key signal for risk-aware scaling — wider intervals mean less
        certainty, which should bias the controller toward conservative
        (scaled-up) decisions.

        Args:
            horizon_minutes: How many minutes into the future to forecast.
                Must be between 1 and 1440 (24 hours). Default: 30.

        Returns:
            pd.DataFrame with columns:
                - ds (datetime): The predicted future timestamps.
                - yhat (float): Point forecast value.
                - yhat_lower (float): Lower bound of 80% confidence interval.
                - yhat_upper (float): Upper bound of 80% confidence interval.

        Raises:
            RuntimeError: If the model has not been trained yet.
            ValueError: If horizon_minutes is outside [1, 1440].

        TODO:
            - Make confidence interval level configurable (default 80%)
            - Support multi-step ahead uncertainty that widens over time
        """
        ...

    def retrain(self, new_df: pd.DataFrame) -> None:
        """Incremental retrain on a rolling window of new data.

        Retrains the model using only the most recent data, rather
        than fitting from scratch. This is faster and preserves
        learned patterns from the previous training window.

        Args:
            new_df: New training data with the same schema as `.train()`.
                Should be a subset of the full history (rolling window).

        Returns:
            None. The internal model is updated in place.

        Raises:
            ValueError: If new_df has fewer than 10 rows.
            RuntimeError: If Prophet fails to converge.

        TODO:
            - Implement warm-start retraining rather than full refit
            - Compare new vs old model accuracy before accepting
            - Log retrain duration for performance monitoring
        """
        ...

    def evaluate(self, test_df: pd.DataFrame) -> dict[str, float]:
        """Evaluate model accuracy on held-out test data.

        Generates predictions for the test period and computes
        standard regression metrics against actual values.

        Args:
            test_df: Held-out data with the same schema as training data.
                Must have at least 5 rows for meaningful evaluation.

        Returns:
            dict[str, float] with keys:
                - 'rmse': Root Mean Squared Error (requests per second).
                - 'mae': Mean Absolute Error (requests per second).
                - 'mape_pct': Mean Absolute Percentage Error (0-100%).

        Raises:
            RuntimeError: If the model has not been trained yet.
            ValueError: If test_df has fewer than 5 rows.

        TODO:
            - Add MAPE handling for zero/near-zero actual values
            - Return additional metrics (smape, mdape)
        """
        ...

    def save(self, path: str) -> None:
        """Serialise the trained model to disk.

        Uses Prophet's built-in serialisation (pickle-based) to
        save the model for later loading without retraining.

        Args:
            path: Filesystem path to write the model file.

        Returns:
            None. Model is written to disk.

        Raises:
            RuntimeError: If the model has not been trained yet.
            OSError: If the file cannot be written.

        TODO:
            - Use a safer serialisation format (e.g., JSON + params)
            - Add model metadata alongside the serialised weights
        """
        ...

    @classmethod
    def load(cls, path: str) -> ForecastingModel:
        """Load a previously serialised model from disk.

        Args:
            path: Filesystem path to the serialised model file.

        Returns:
            A ForecastingModel instance with the trained model loaded.

        Raises:
            FileNotFoundError: If the model file does not exist.
            RuntimeError: If the file is corrupted or incompatible.

        TODO:
            - Validate model version compatibility on load
            - Add model health check after loading
        """
        ...
