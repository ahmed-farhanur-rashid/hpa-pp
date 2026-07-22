"""Integration service API routes.

Defines all REST endpoints for orchestrator control, demo management,
benchmarking, and health checks.
"""

from __future__ import annotations

from fastapi import APIRouter

from shared.schemas import ApiResponse

router = APIRouter()


# ── Orchestrator endpoints ──────────────────────────────────────────


@router.post("/orchestrator/start")
async def start_orchestrator() -> ApiResponse:
    """Start the full integration pipeline (sim → forecast → scale loop).

    Returns:
        ApiResponse: Status of the pipeline start operation.

    Raises:
        HTTPException: If the pipeline is already running or
            required services are unreachable.

    TODO: Accept optional config payload to override default tick interval
          and service URLs.
    """
    ...


@router.post("/orchestrator/stop")
async def stop_orchestrator() -> ApiResponse:
    """Stop the running integration pipeline gracefully.

    Returns:
        ApiResponse: Confirmation of pipeline stop.

    Raises:
        HTTPException: If the pipeline is not currently running.

    TODO: Implement graceful drain with configurable timeout.
    """
    ...


@router.get("/orchestrator/status")
async def get_orchestrator_status() -> ApiResponse:
    """Get current pipeline status including tick count and last error.

    Returns:
        ApiResponse: Pipeline status payload with runtime metrics.

    TODO: Include uptime, tick history, and service health indicators.
    """
    ...


@router.post("/orchestrator/reset")
async def reset_orchestrator() -> ApiResponse:
    """Reset all pipeline state including metrics and tick counters.

    Returns:
        ApiResponse: Confirmation of reset.

    TODO: Flush any cached forecast results and reset DB counters.
    """
    ...


# ── Demo endpoints ──────────────────────────────────────────────────


@router.post("/demo/load")
async def start_demo_load() -> ApiResponse:
    """Start a Locust-based load testing profile.

    Returns:
        ApiResponse: Load test ID and initial status.

    Raises:
        HTTPException: If a load test is already running.

    TODO: Accept profile name and duration as request body parameters.
    """
    ...


@router.get("/demo/load/status")
async def get_demo_load_status() -> ApiResponse:
    """Get the current status of the running load test.

    Returns:
        ApiResponse: Load test metrics (RPS, failures, active users).

    TODO: Stream progress updates via SSE for live dashboards.
    """
    ...


@router.post("/demo/benchmark")
async def run_benchmark() -> ApiResponse:
    """Run a full benchmark (sim + forecast + scale + measure).

    Returns:
        ApiResponse: Benchmark run ID and configuration used.

    Raises:
        HTTPException: If a benchmark is already in progress.

    TODO: Accept optional config to override benchmark parameters.
    """
    ...


@router.get("/demo/benchmark/results")
async def get_benchmark_results() -> ApiResponse:
    """Get stored benchmark results.

    Returns:
        ApiResponse: List of completed benchmark results.

    TODO: Support pagination and filtering by date range.
    """
    ...


# ── Health check ────────────────────────────────────────────────────


@router.get("/health")
async def health_check() -> ApiResponse:
    """Health check endpoint for load balancers and orchestrators.

    Returns:
        ApiResponse: Service health status and version info.

    TODO: Include dependency health (DB, forecast service, sim service).
    """
    ...
