"""Controller API routes — scaling, GPU, and status endpoints."""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from httpx import AsyncClient

from shared.api import ApiResponse
from shared.decisions import ScalingConfig, ScalingDecision
from shared.gpu import GpuAssignment, GpuRebalanceEvent

from app import dependencies as deps
from app.config import load_scaling_config, save_scaling_config
from app.executor import ReactiveFallback
from app.scaler import PredictiveController

logger = logging.getLogger(__name__)
router = APIRouter()

# Shared HTTP client for simulation calls (set during lifespan)
_sim_http: AsyncClient | None = None
_sim_base_url: str = "http://simulation:8001/api/v1"


# ── Scale evaluation ───────────────────────────────────────────

@router.post("/scale/evaluate", response_model=ApiResponse[dict[str, Any]])
async def evaluate_scaling(
    deployment_id: str,
    config: Optional[ScalingConfig] = None,
    controller: PredictiveController = Depends(deps.get_controller),
) -> ApiResponse[dict[str, Any]]:
    """Evaluate scaling decision for a deployment (9-step formula)."""
    try:
        decision = await controller.evaluate(deployment_id, config)
        return ApiResponse(data=decision.model_dump(mode="json"))
    except Exception as e:
        logger.error("Evaluation failed for %s: %s", deployment_id, e)
        raise HTTPException(status_code=500, detail=str(e))


# ── Scale execution ────────────────────────────────────────────

@router.post("/scale/execute", response_model=ApiResponse[dict[str, Any]])
async def execute_scaling(
    decision_id: str,
    executor=Depends(deps.get_executor),
    db=Depends(deps.get_db),
) -> ApiResponse[dict[str, Any]]:
    """Execute a previously evaluated scaling decision."""
    rows = db.query_scaling_decisions(deployment_id="", limit=200)
    decision: ScalingDecision | None = None
    for row in rows:
        d = ScalingDecision.model_validate(row)
        if d.decision_id == decision_id:
            decision = d
            break

    if decision is None:
        raise HTTPException(status_code=404, detail="Decision not found")

    success = await executor.execute(decision)
    if not success:
        raise HTTPException(status_code=500, detail="Execution failed")

    return ApiResponse(data={
        "decision_id": decision_id,
        "status": "executed",
        "target_replicas": decision.target_replicas,
    })


# ── Decision history ───────────────────────────────────────────

@router.get("/scale/decisions", response_model=ApiResponse[list[dict[str, Any]]])
async def get_scaling_decisions(
    deployment_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    controller: PredictiveController = Depends(deps.get_controller),
) -> ApiResponse[list[dict[str, Any]]]:
    """Get scaling decision history for a deployment."""
    decisions = controller.get_decision_history(deployment_id, limit)
    return ApiResponse(data=[d.model_dump(mode="json") for d in decisions])


@router.get("/scale/latest", response_model=ApiResponse[dict[str, Any] | None])
async def get_latest_scaling_decision(
    deployment_id: str,
    db=Depends(deps.get_db),
) -> ApiResponse[dict[str, Any] | None]:
    """Get the most recent scaling decision for a deployment."""
    row = db.query_latest_decision(deployment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="No decisions found")
    return ApiResponse(data=dict(row))


# ── Scaling config ─────────────────────────────────────────────

@router.post("/scale/config", response_model=ApiResponse[dict[str, Any]])
async def update_scaling_config(
    deployment_id: str,
    config: ScalingConfig,
    db=Depends(deps.get_db),
) -> ApiResponse[dict[str, Any]]:
    """Update scaling configuration for a deployment."""
    try:
        save_scaling_config(config, db)
        return ApiResponse(data={"deployment_id": deployment_id, "saved": True})
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/scale/config", response_model=ApiResponse[dict[str, Any] | None])
async def get_scaling_config_endpoint(
    deployment_id: str,
    db=Depends(deps.get_db),
) -> ApiResponse[dict[str, Any] | None]:
    """Get current scaling configuration for a deployment."""
    config = load_scaling_config(deployment_id, db)
    return ApiResponse(data=config.model_dump(mode="json"))


# ── GPU assignment ─────────────────────────────────────────────

@router.post("/gpu/assign", response_model=ApiResponse[list[dict[str, Any]]])
async def assign_gpus(
    pod_ids: list[str],
    gpu_specs: list[dict[str, Any]],
    strategy: str = Query(default="bin_pack"),
    scheduler=Depends(deps.get_gpu_scheduler),
) -> ApiResponse[list[dict[str, Any]]]:
    """Compute GPU-to-pod assignments using the specified strategy.

    Provide ``gpu_specs`` as list of dicts from the simulation's
    cluster nodes endpoint. Each dict needs:
      ``gpu_id``, ``node_id``, ``total_memory_mb``, ``allocated_memory_mb``.
    """
    assignments = await scheduler.assign_gpus(pod_ids, gpu_specs, strategy=strategy)
    return ApiResponse(data=[a.model_dump(mode="json") for a in assignments])


@router.post("/gpu/rebalance", response_model=ApiResponse[dict[str, Any]])
async def rebalance_gpus(
    trigger_reason: str = Query(default="manual"),
    scheduler=Depends(deps.get_gpu_scheduler),
    db=Depends(deps.get_db),
) -> ApiResponse[dict[str, Any]]:
    """Rebalance GPU assignments across pods.

    Fetches current GPU state from the simulation and existing
    assignments from the database, then invokes the rebalancer.
    """
    global _sim_http, _sim_base_url
    http = _sim_http or AsyncClient(timeout=5.0)

    try:
        # Fetch current cluster state from simulation
        nodes_resp = await http.get(f"{_sim_base_url}/cluster/nodes")
        nodes_data = nodes_resp.json().get("data", [])

        gpu_specs: list[dict[str, Any]] = []
        for node in nodes_data:
            for gpu_id in node.get("gpu_ids", []):
                gpu_specs.append({
                    "gpu_id": gpu_id,
                    "node_id": node["node_id"],
                    "total_memory_mb": node.get("total_gpu_memory_mb", 8192),
                    "allocated_memory_mb": node.get("allocated_gpu_memory_mb", 0),
                })

        # Fetch current assignments from DB
        rows = db.query_gpu_assignments()
        current_assignments = [GpuAssignment.model_validate(r) for r in rows]

        event = await scheduler.rebalance(
            current_assignments, gpu_specs, trigger_reason=trigger_reason,
        )
        return ApiResponse(data=event.model_dump(mode="json"))
    except Exception as e:
        logger.error("GPU rebalance failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/gpu/assignments", response_model=ApiResponse[list[dict[str, Any]]])
async def get_gpu_assignments_route(
    deployment_id: Optional[str] = Query(default=None),
    db=Depends(deps.get_db),
) -> ApiResponse[list[dict[str, Any]]]:
    """Get current GPU assignments from the database."""
    rows = db.query_gpu_assignments(limit=200)
    if deployment_id:
        rows = [r for r in rows if r.get("deployment_id") == deployment_id]
    return ApiResponse(data=[dict(r) for r in rows])


@router.get("/gpu/status", response_model=ApiResponse[dict[str, Any]])
async def get_gpu_status() -> ApiResponse[dict[str, Any]]:
    """Get GPU utilisation summary from the simulation."""
    global _sim_http, _sim_base_url
    http = _sim_http or AsyncClient(timeout=5.0)

    try:
        resp = await http.get(f"{_sim_base_url}/cluster/nodes")
        nodes = resp.json().get("data", [])

        total_gpus = 0
        allocated_gpus = 0
        for node in nodes:
            gpu_ids = node.get("gpu_ids", [])
            total_gpus += len(gpu_ids)
            alloc = node.get("allocated_gpu_memory_mb", 0)
            total = node.get("total_gpu_memory_mb", 8192)
            if alloc > 0:
                allocated_gpus += len(gpu_ids)

        return ApiResponse(data={
            "total_gpus": total_gpus,
            "allocated_gpus": allocated_gpus,
            "nodes_with_gpu": sum(1 for n in nodes if n.get("gpu_ids")),
        })
    except Exception as e:
        logger.warning("Simulation GPU status unavailable: %s", e)
        return ApiResponse(data={
            "total_gpus": 0, "allocated_gpus": 0, "nodes_with_gpu": 0,
            "error": str(e),
        })


# ── Service health ─────────────────────────────────────────────

@router.get("/status", response_model=ApiResponse[dict[str, Any]])
async def get_controller_status(
    db=Depends(deps.get_db),
) -> ApiResponse[dict[str, Any]]:
    """Controller service health and operational status."""
    db_ok = False
    try:
        db.connection  # lazy connect check
        db_ok = True
    except Exception:
        pass

    return ApiResponse(data={
        "service": "controller",
        "database": "connected" if db_ok else "disconnected",
        "controller_ready": deps.controller_instance is not None,
        "executor_ready": deps.executor_instance is not None,
    })
