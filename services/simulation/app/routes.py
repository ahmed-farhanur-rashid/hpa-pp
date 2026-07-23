"""API routes for the HPA++ Simulation Service.

All endpoints return ApiResponse[T] for consistency with other services.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from shared.api import ApiResponse, SimulatorStatusResponse
from shared.metrics import MetricSample, MetricBatch
from shared.cluster import ClusterSnapshot, NodeState, DeploymentState
from shared.simulation import SimulationConfig, SimulatorStatus
from app import dependencies as deps
from app.dependencies import get_simulation_engine, get_db
from app.events import CHANNEL_METRICS, CHANNEL_CLUSTER, CHANNEL_STATUS
from app.engine import SimulationEngine

router = APIRouter()


# ── Request body models ────────────────────────────────────────

class StartSimulationRequest(BaseModel):
    """Optional config override when starting simulation."""
    config: SimulationConfig | None = None


class UpdateConfigRequest(BaseModel):
    """New simulation configuration."""
    config: SimulationConfig


# ── Helpers ────────────────────────────────────────────────────

def _build_status_response(engine: SimulationEngine) -> SimulatorStatusResponse:
    """Build a SimulatorStatusResponse from the engine."""
    return SimulatorStatusResponse(
        status=engine.get_status(),
        sim_name=engine.get_config().sim_name,
        tick_count=getattr(engine, "tick_count", 0),
        simulated_minutes_elapsed=getattr(engine, "simulated_minutes", 0.0),
        uptime_seconds=0.0,  # simplified; could track start time
    )


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
    """
    raw = db.query_metrics(
        deployment_id=deployment_id,
        from_time=from_time.isoformat() if from_time else None,
        to_time=to_time.isoformat() if to_time else None,
        limit=limit,
    )
    samples = [MetricSample.model_validate(r) for r in raw]
    return ApiResponse(data=samples)


@router.get("/metrics/latest", response_model=ApiResponse[list[MetricSample]])
async def get_latest_metrics(
    count: int = Query(10, ge=1, le=100, description="Number of latest samples"),
    deployment_id: str | None = Query(None, description="Filter by deployment ID"),
    db=Depends(get_db),
):
    """Get the most recent N metric samples.

    Args:
        count: Number of latest samples to return.
        deployment_id: Optional filter by deployment ID.
        db: Database manager dependency.

    Returns:
        ApiResponse containing list of latest MetricSample.
    """
    raw = db.query_latest_metrics(deployment_id=deployment_id, count=count)
    samples = [MetricSample.model_validate(r) for r in raw]
    return ApiResponse(data=samples)


# ── Cluster state endpoints ────────────────────────────────────

@router.get("/cluster/state", response_model=ApiResponse[ClusterSnapshot])
async def get_cluster_state(
    engine: SimulationEngine = Depends(get_simulation_engine),
):
    """Get full cluster snapshot.

    Args:
        engine: Simulation engine dependency.

    Returns:
        ApiResponse containing ClusterSnapshot with all nodes and deployments.
    """
    cluster = getattr(engine, "cluster_state", None)
    if cluster is None:
        raise HTTPException(status_code=400, detail="Simulation has not been started yet")
    return ApiResponse(data=cluster.get_snapshot())


@router.get("/cluster/nodes", response_model=ApiResponse[list[NodeState]])
async def get_cluster_nodes(
    engine: SimulationEngine = Depends(get_simulation_engine),
):
    """Get list of all node states.

    Args:
        engine: Simulation engine dependency.

    Returns:
        ApiResponse containing list of NodeState.
    """
    cluster = getattr(engine, "cluster_state", None)
    if cluster is None:
        return ApiResponse(data=[])
    return ApiResponse(data=cluster.get_all_nodes())


@router.get("/cluster/deployments", response_model=ApiResponse[list[DeploymentState]])
async def get_cluster_deployments(
    engine: SimulationEngine = Depends(get_simulation_engine),
):
    """Get list of all deployment states.

    Args:
        engine: Simulation engine dependency.

    Returns:
        ApiResponse containing list of DeploymentState.
    """
    cluster = getattr(engine, "cluster_state", None)
    if cluster is None:
        return ApiResponse(data=[])
    return ApiResponse(data=cluster.get_all_deployments())


# ── Simulation control endpoints ───────────────────────────────

@router.get("/sim/status", response_model=ApiResponse[SimulatorStatusResponse])
async def get_sim_status(
    engine: SimulationEngine = Depends(get_simulation_engine),
):
    """Get current simulator status.

    Args:
        engine: Simulation engine dependency.

    Returns:
        ApiResponse containing SimulatorStatusResponse with status, tick count, etc.
    """
    return ApiResponse(data=_build_status_response(engine))


@router.post("/sim/start", response_model=ApiResponse[SimulatorStatusResponse])
async def start_simulation(
    request: StartSimulationRequest | None = None,
    engine: SimulationEngine = Depends(get_simulation_engine),
):
    """Start simulation with optional config override.

    Args:
        request: Optional request body with config override.
        engine: Simulation engine dependency.

    Returns:
        ApiResponse containing SimulatorStatusResponse after start.

    Raises:
        400: If simulation is already running.
    """
    try:
        if request and request.config is not None:
            await engine.update_config(request.config)
        await engine.start()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return ApiResponse(data=_build_status_response(engine))


@router.post("/sim/pause", response_model=ApiResponse[SimulatorStatusResponse])
async def pause_simulation(
    engine: SimulationEngine = Depends(get_simulation_engine),
):
    """Pause the running simulation.

    Args:
        engine: Simulation engine dependency.

    Returns:
        ApiResponse containing SimulatorStatusResponse after pause.

    Raises:
        400: If simulation is not running.
    """
    try:
        await engine.pause()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return ApiResponse(data=_build_status_response(engine))


@router.post("/sim/resume", response_model=ApiResponse[SimulatorStatusResponse])
async def resume_simulation(
    engine: SimulationEngine = Depends(get_simulation_engine),
):
    """Resume the paused simulation.

    Args:
        engine: Simulation engine dependency.

    Returns:
        ApiResponse containing SimulatorStatusResponse after resume.

    Raises:
        400: If simulation is not paused.
    """
    try:
        await engine.resume()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return ApiResponse(data=_build_status_response(engine))


@router.post("/sim/stop", response_model=ApiResponse[SimulatorStatusResponse])
async def stop_simulation(
    engine: SimulationEngine = Depends(get_simulation_engine),
):
    """Stop the simulation and reset state.

    Args:
        engine: Simulation engine dependency.

    Returns:
        ApiResponse containing SimulatorStatusResponse after stop.
    """
    await engine.stop()
    return ApiResponse(data=_build_status_response(engine))


@router.post("/sim/config", response_model=ApiResponse[SimulationConfig])
async def update_simulation_config(
    request: UpdateConfigRequest,
    engine: SimulationEngine = Depends(get_simulation_engine),
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
    """
    try:
        await engine.update_config(request.config)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return ApiResponse(data=engine.get_config())


# ── WebSocket event streams ────────────────────────────────────


@router.websocket("/ws/metrics")
async def ws_metrics_stream(websocket: WebSocket) -> None:
    """Subscribe to real-time metric samples as they are generated.

    Emits a JSON event envelope on every simulation tick::

        {
          "channel": "metrics",
          "event": "tick",
          "timestamp_utc": "...",
          "tick_count": 42,
          "simulated_minutes": 8.4,
          "data": {"samples": [...]}
        }
    """
    await websocket.accept()
    bc = deps.broadcaster_instance
    if bc is None:
        await websocket.close(code=1011, reason="Broadcaster not initialized")
        return
    await bc.subscribe(CHANNEL_METRICS, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await bc.unsubscribe(CHANNEL_METRICS, websocket)


@router.websocket("/ws/cluster")
async def ws_cluster_stream(websocket: WebSocket) -> None:
    """Subscribe to cluster state snapshots as they are generated.

    Emits every tick::

        {
          "channel": "cluster",
          "event": "snapshot",
          "timestamp_utc": "...",
          "tick_count": 42,
          "data": {ClusterSnapshot fields}
        }
    """
    await websocket.accept()
    bc = deps.broadcaster_instance
    if bc is None:
        await websocket.close(code=1011, reason="Broadcaster not initialized")
        return
    await bc.subscribe(CHANNEL_CLUSTER, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await bc.unsubscribe(CHANNEL_CLUSTER, websocket)


@router.websocket("/ws/status")
async def ws_status_stream(websocket: WebSocket) -> None:
    """Subscribe to simulation lifecycle events.

    Emitted on start / pause / resume / stop / complete::

        {
          "channel": "status",
          "event": "started",
          "timestamp_utc": "...",
          "data": {"status": "running", "sim_name": "..."}
        }
    """
    await websocket.accept()
    bc = deps.broadcaster_instance
    if bc is None:
        await websocket.close(code=1011, reason="Broadcaster not initialized")
        return
    await bc.subscribe(CHANNEL_STATUS, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await bc.unsubscribe(CHANNEL_STATUS, websocket)
