"""FastAPI router for the Forecasting microservice.

All endpoints return ApiResponse[T] for consistency with the
HPA++ API contract. The frontend always checks 'success' first.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query

from shared.api import ApiResponse
from shared.forecast import ForecastMetadata, ForecastWindow

from app.dependencies import get_db, get_pipeline
from app.pipeline import ForecastPipeline

router = APIRouter(prefix="/api/v1", tags=["forecasting"])


# ── Forecast CRUD ──────────────────────────────────────────────


@router.get("/forecast/latest", response_model=ApiResponse[ForecastWindow | None])
async def get_latest_forecast(
    deployment_id: Annotated[str, Query(description="Deployment to query")],
    db: Annotated[None, Depends(get_db)],
) -> ApiResponse[ForecastWindow | None]:
    """Get the most recent forecast for a deployment.

    Args:
        deployment_id: The deployment to query forecasts for.
        db: Database manager dependency.

    Returns:
        ApiResponse containing the latest ForecastWindow, or None
        if no forecast exists yet.

    TODO:
        - Validate deployment_id exists
        - Add cache headers (ETag, Cache-Control)
        """
    ...


@router.get("/forecast/history", response_model=ApiResponse[list[ForecastWindow]])
async def get_forecast_history(
    deployment_id: Annotated[str, Query(description="Deployment to query")],
    limit: Annotated[int, Query(default=100, le=1000, description="Max records")],
    db: Annotated[None, Depends(get_db)],
) -> ApiResponse[list[ForecastWindow]]:
    """Get historical forecast records for a deployment.

    Args:
        deployment_id: The deployment to query.
        limit: Maximum number of records to return (1–1000).
        db: Database manager dependency.

    Returns:
        ApiResponse containing a list of ForecastWindow records,
        ordered by forecast_time_utc descending.

    TODO:
        - Add pagination (cursor-based)
        - Support filtering by time range
        """
    ...


@router.get("/forecast/metadata", response_model=ApiResponse[ForecastMetadata | None])
async def get_forecast_metadata(
    deployment_id: Annotated[str, Query(description="Deployment to query")],
    db: Annotated[None, Depends(get_db)],
) -> ApiResponse[ForecastMetadata | None]:
    """Get training metadata for the latest model.

    Args:
        deployment_id: The deployment to query.
        db: Database manager dependency.

    Returns:
        ApiResponse containing the latest ForecastMetadata, or None
        if no training has been performed.

    TODO:
        - Return full metadata history for debugging
        """
    ...


# ── Pipeline Control ───────────────────────────────────────────


@router.post("/forecast/run", response_model=ApiResponse[ForecastWindow | None])
async def run_forecast(
    deployment_id: Annotated[str, Body(description="Deployment to forecast")],
    horizon_minutes: Annotated[int, Body(default=30, description="Forecast horizon")],
    db: Annotated[None, Depends(get_db)],
) -> ApiResponse[ForecastWindow | None]:
    """Trigger a single forecast cycle on demand.

    Useful for testing or manual re-triggering outside the loop.

    Args:
        deployment_id: The deployment to forecast for.
        horizon_minutes: How many minutes ahead to forecast.
        db: Database manager dependency.

    Returns:
        ApiResponse containing the newly generated ForecastWindow,
        or None if insufficient data was available.

    TODO:
        - Validate deployment_id exists
        - Return error if pipeline is already running
        """
    ...


@router.post("/forecast/start-loop", response_model=ApiResponse[dict])
async def start_forecast_loop(
    deployment_id: Annotated[str, Body(description="Deployment to forecast")],
    interval_seconds: Annotated[int, Body(default=60, description="Seconds between cycles")],
    pipeline: Annotated[ForecastPipeline, Depends(get_pipeline)],
) -> ApiResponse[dict]:
    """Start the continuous forecast loop for a deployment.

    Launches pipeline.run_loop() as a background asyncio task.

    Args:
        deployment_id: The deployment to forecast for.
        interval_seconds: Seconds between forecast cycles.
        pipeline: ForecastPipeline dependency.

    Returns:
        ApiResponse containing {"status": "started", "deployment_id": str}.

    TODO:
        - Store the background task reference for cancellation
        - Prevent duplicate loops for the same deployment
        - Return 409 Conflict if loop is already running
        """
    ...


@router.post("/forecast/stop-loop", response_model=ApiResponse[dict])
async def stop_forecast_loop(
    deployment_id: Annotated[str, Body(description="Deployment to stop")],
    pipeline: Annotated[ForecastPipeline, Depends(get_pipeline)],
) -> ApiResponse[dict]:
    """Stop the continuous forecast loop for a deployment.

    Cancels the background asyncio task started by start-loop.

    Args:
        deployment_id: The deployment to stop forecasting for.
        pipeline: ForecastPipeline dependency.

    Returns:
        ApiResponse containing {"status": "stopped", "deployment_id": str}.

    TODO:
        - Look up and cancel the stored background task
        - Return 404 if no loop is running for this deployment
        """
    ...


# ── Model Management ───────────────────────────────────────────


@router.post("/model/train", response_model=ApiResponse[ForecastMetadata])
async def train_model(
    deployment_id: Annotated[str, Body(description="Deployment to train for")],
    training_window_minutes: Annotated[int, Body(default=60, description="Training data window")],
    db: Annotated[None, Depends(get_db)],
) -> ApiResponse[ForecastMetadata]:
    """Force a model retrain on demand.

    Useful for retraining after configuration changes or data issues.

    Args:
        deployment_id: The deployment to train for.
        training_window_minutes: How many minutes of history to use.
        db: Database manager dependency.

    Returns:
        ApiResponse containing the ForecastMetadata for the new training run.

    TODO:
        - Validate deployment_id exists
        - Support async training with job ID return
        - Return 409 if training is already in progress
        """
    ...


@router.get("/model/info", response_model=ApiResponse[dict])
async def get_model_info(
    deployment_id: Annotated[str, Query(description="Deployment to query")],
    db: Annotated[None, Depends(get_db)],
) -> ApiResponse[dict]:
    """Get current model information and health.

    Args:
        deployment_id: The deployment to query.
        db: Database manager dependency.

    Returns:
        ApiResponse containing dict with:
            - model_version: str
            - is_trained: bool
            - last_training_utc: str | None
            - accuracy_metrics: dict[str, float] | None

    TODO:
        - Return full model configuration
        - Add model drift detection status
        """
    ...
