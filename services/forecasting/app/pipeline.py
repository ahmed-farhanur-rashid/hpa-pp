"""Forecast orchestration pipeline.

Coordinates the complete forecast cycle: reads metrics, extracts
features, trains model, predicts, and stores results. The pipeline
is the only component that touches both the database and the model.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from shared.forecast import ForecastMetadata, ForecastWindow

if TYPE_CHECKING:
    from app.model import ForecastingModel


class ForecastPipeline:
    """Orchestrates the complete forecast cycle.

    Reads metrics → extracts features → trains model → predicts → stores results.

    SOLID: Single responsibility — pipeline orchestration.
    Depends on ForecastingModel and feature extraction functions via interfaces.
    """

    def __init__(self, db_manager: None, deployment_id: str, model: ForecastingModel | None = None) -> None:
        """Initialise the forecast pipeline.

        Args:
            db_manager: Database manager for reading metrics and writing
                forecast results. Injected via FastAPI Depends().
            deployment_id: The deployment to forecast for. All operations
                are scoped to this deployment.
            model: An optional pre-trained ForecastingModel. If None,
                a new model is created and trained on first run_once().

        Returns:
            None.

        TODO:
            - Accept a model factory callable instead of optional model
            - Add pipeline configuration (horizon, interval, window)
            - Validate deployment_id exists in the database
        """
        ...

    async def run_once(self) -> ForecastWindow | None:
        """Execute one complete forecast cycle.

        Steps:
        1. Read recent MetricSamples from DB via db_manager.
        2. Extract training data via features.extract_training_data().
        3. Train the ForecastingModel (or retrain if model exists).
        4. Generate forecast for the configured horizon.
        5. Store ForecastMetadata in DB.
        6. Convert forecast to ForecastWindow records and store.
        7. Return the latest ForecastWindow (or None if no data).

        Returns:
            The latest ForecastWindow record, or None if insufficient data
            was available for training.

        Raises:
            RuntimeError: If database operations fail.
            RuntimeError: If model training fails after all retries.

        TODO:
            - Add retry logic with exponential backoff
            - Emit structured logging for each pipeline stage
            - Store pipeline duration in ForecastMetadata
        """
        ...

    async def run_loop(self, interval_seconds: int = 60) -> None:
        """Run the forecast cycle in a continuous loop.

        Calls run_once() every interval_seconds until the task is
        cancelled. Designed to run as a background asyncio task
        started from the /forecast/start-loop endpoint.

        Args:
            interval_seconds: Seconds between forecast cycles.
                Default: 60. Must be between 10 and 3600.

        Returns:
            None. The loop runs until cancelled.

        Raises:
            ValueError: If interval_seconds is outside [10, 3600].

        TODO:
            - Log each cycle completion with duration and status
            - Support adaptive interval based on traffic patterns
            - Emit metrics (forecast latency, error rate) for monitoring
        """
        ...

    def get_latest_forecast(self) -> ForecastWindow | None:
        """Retrieve the most recent forecast from DB.

        Returns:
            The most recent ForecastWindow for this deployment,
            or None if no forecast has been generated yet.

        TODO:
            - Cache the result with TTL for fast repeated reads
            - Support filtering by forecast_id
        """
        ...

    def get_metadata(self) -> ForecastMetadata | None:
        """Retrieve metadata from the latest training run.

        Returns:
            The most recent ForecastMetadata for this deployment,
            or None if no training has been performed.

        TODO:
            - Return full metadata history for debugging
            - Include model health indicators
        """
        ...
