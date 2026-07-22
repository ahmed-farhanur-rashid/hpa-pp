"""API routes for the HPA++ Simulation Service.

All endpoints return ApiResponse[T] for consistency with other services.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from shared.api import ApiResponse, SimulatorStatusResponse
from shared.metrics import MetricSample
from shared.cluster import ClusterSnapshot, NodeState, DeploymentState
from shared.simulation import SimulationConfig
from app.dependencies import get_simulation_engine, get_db

router = APIRouter()


# ── Request body models ────────────────────────────────────────

class StartSimulationRequest(BaseModel):
    """Optional config override when starting simulation."""
    config: SimulationConfig | None = None


class UpdateConfigRequest(BaseModel):
    """New simulation configuration."""
    config: SimulationConfig


# ── Metrics endpoints ──────────────────────────────────────────

@router.get("/metrics", response_model=ApiResponse[list[MetricSample]])
async def get_metrics(
    deployment_id: str | None = Query(None, description="Filter by deployment ID"),
    from_time: datetime | None = Query(None, description="Start time (ISO 8601)"),
    to_time: datetime | None = Query(None, description="End time (ISO 8601)"),
    limit: int = Query(100, ge=1, le=1000, description="Max samples to return"),
    db=Depends(get_db),
):
    """Query metric samples with optional time and deployment filters.

    Args:
        deployment_id: Filter by specific deployment.
        from_time: Lower bound for simulated_time_utc.
        to_time: Upper bound for simulated_time_utc.
        limit: Maximum number of samples to return.
        db: Database manager dependency.

    Returns:
        ApiResponse containing list of MetricSample.

    TODO:
        - Validate from_time < to_time
        - Add pagination support
    """
    ...


@router.get("/metrics/latest", response_model=ApiResponse[list[MetricSample]])
async def get_latest_metrics(
    count: int = Query(10, ge=1, le=100, description="Number of latest samples"),
    db=Depends(get_db),
):
    """Get the most recent N metric samples.

    Args:
        count: Number of latest samples to return.
        db: Database manager dependency.

    Returns:
        ApiResponse containing list of latest MetricSample.

    TODO:
        - Support per-deployment latest via optional deployment_id
    """
    ...


# ── Cluster state endpoints ────────────────────────────────────

@router.get("/cluster/state", response_model=ApiResponse[ClusterSnapshot])
async def get_cluster_state(
    engine=Depends(get_simulation_engine),
):
    """Get full cluster snapshot.

    Args:
        engine: Simulation engine dependency.

    Returns:
        ApiResponse containing ClusterSnapshot with all nodes and deployments.

    TODO:
        - Return 404 if simulation hasn't started yet
    """
    ...


@router.get("/cluster/nodes", response_model=ApiResponse[list[NodeState]])
async def get_cluster_nodes(
    engine=Depends(get_simulation_engine),
):
    """Get list of all node states.

    Args:
        engine: Simulation engine dependency.

    Returns:
        ApiResponse containing list of NodeState.

    TODO:
        - Filter by node_id if query param provided
    """
    ...


@router.get("/cluster/deployments", response_model=ApiResponse[list[DeploymentState]])
async def get_cluster_deployments(
    engine=Depends(get_simulation_engine),
):
    """Get list of all deployment states.

    Args:
        engine: Simulation engine dependency.

    Returns:
        ApiResponse containing list of DeploymentState.

    TODO:
        - Filter by deployment_id if query param provided
    """
    ...


# ── Simulation control endpoints ───────────────────────────────

@router.get("/sim/status", response_model=ApiResponse[SimulatorStatusResponse])
async def get_sim_status(
    engine=Depends(get_simulation_engine),
):
    """Get current simulator status.

    Args:
        engine: Simulation engine dependency.

    Returns:
        ApiResponse containing SimulatorStatusResponse with status, tick count, etc.
    """
    ...


@router.post("/sim/start", response_model=ApiResponse[SimulatorStatusResponse])
async def start_simulation(
    request: StartSimulationRequest | None = None,
    engine=Depends(get_simulation_engine),
):
    """Start simulation with optional config override.

    Args:
        request: Optional request body with config override.
        engine: Simulation engine dependency.

    Returns:
        ApiResponse containing SimulatorStatusResponse after start.

    Raises:
        400: If simulation is already running.

    TODO:
        - Return error if sim already running
        - Apply config override if provided
    """
    ...


@router.post("/sim/pause", response_model=ApiResponse[SimulatorStatusResponse])
async def pause_simulation(
    engine=Depends(get_simulation_engine),
):
    """Pause the running simulation.

    Args:
        engine: Simulation engine dependency.

    Returns:
        ApiResponse containing SimulatorStatusResponse after pause.

    Raises:
        400: If simulation is not running.

    TODO:
        - Return error if sim not in RUNNING state
    """
    ...


@router.post("/sim/resume", response_model=ApiResponse[SimulatorStatusResponse])
async def resume_simulation(
    engine=Depends(get_simulation_engine),
):
    """Resume the paused simulation.

    Args:
        engine: Simulation engine dependency.

    Returns:
        ApiResponse containing SimulatorStatusResponse after resume.

    Raises:
        400: If simulation is not paused.

    TODO:
        - Return error if sim not in PAUSED state
    """
    ...


@router.post("/sim/stop", response_model=ApiResponse[SimulatorStatusResponse])
async def stop_simulation(
    engine=Depends(get_simulation_engine),
):
    """Stop the simulation and reset state.

    Args:
        engine: Simulation engine dependency.

    Returns:
        ApiResponse containing SimulatorStatusResponse after stop.

    TODO:
        - Clean up cluster state
        - Flush remaining metrics to DB
    """
    ...


@router.post("/sim/config", response_model=ApiResponse[SimulationConfig])
async def update_simulation_config(
    request: UpdateConfigRequest,
    engine=Depends(get_simulation_engine),
):
    """Update simulation configuration.

    Only allowed when simulation is stopped or paused.

    Args:
        request: Request body with new SimulationConfig.
        engine: Simulation engine dependency.

    Returns:
        ApiResponse containing updated SimulationConfig.

    Raises:
        400: If simulation is currently running.

    TODO:
        - Validate new config against current state
        - Prevent changing deployment count while running
    """
    ...
