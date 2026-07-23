"""FastAPI application factory for the HPA++ Simulation Service.

Provides create_app() for both direct uvicorn invocation and testing.
"""

import os
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shared.db.manager import DatabaseManager
from shared.simulation import (
    SimulationConfig,
    DeploymentSpec,
    TrafficProfile,
)
from shared.enums import TrafficPattern, SimulatorStatus
from app.anomalies.engine import AnomalyEngine
import app.anomalies.handlers  # noqa: F401 — populates HANDLER_REGISTRY
from app.engine import SimulationEngine
from app.events import EventBroadcaster
from app.metrics_generator import MetricsGenerator
from app.routes import router
from app import dependencies


def _default_config() -> SimulationConfig:
    """Create a sensible default simulation configuration for demos.

    Defines a small 3-node cluster with two representative deployments
    (web-app and api-gateway) that showcase different traffic patterns.
    """
    return SimulationConfig(
        sim_name="hpa_plus_plus_demo",
        tick_interval_real_seconds=0.5,
        seconds_per_simulated_minute=0.5,
        total_simulated_minutes=120,
        node_count=3,
        cpu_per_node_millicores=4000,
        memory_per_node_mb=8192,
        gpus_per_node=1,
        gpu_memory_per_device_mb=16384,
        seed=42,
        deployments=[
            DeploymentSpec(
                deployment_id="web-app",
                initial_replicas=3,
                cpu_request_millicores=500,
                memory_request_mb=512,
                traffic_profile=TrafficProfile(
                    pattern=TrafficPattern.SINE_WAVE,
                    base_load_rps=80.0,
                    spike_multiplier=3.0,
                    period_minutes=30,
                    noise_std_pct=5.0,
                ),
            ),
            DeploymentSpec(
                deployment_id="api-gateway",
                initial_replicas=2,
                cpu_request_millicores=1000,
                memory_request_mb=1024,
                traffic_profile=TrafficProfile(
                    pattern=TrafficPattern.STEP_SPIKE,
                    base_load_rps=40.0,
                    spike_multiplier=6.0,
                    spike_minute=45,
                    spike_duration_minutes=15,
                    noise_std_pct=3.0,
                ),
            ),
            DeploymentSpec(
                deployment_id="ml-inference",
                initial_replicas=2,
                cpu_request_millicores=2000,
                memory_request_mb=4096,
                gpu_required=True,
                gpu_memory_request_mb=4096,
                traffic_profile=TrafficProfile(
                    pattern=TrafficPattern.EXAM_START,
                    base_load_rps=10.0,
                    spike_multiplier=5.0,
                    spike_minute=20,
                    spike_duration_minutes=60,
                    noise_std_pct=2.0,
                ),
            ),
        ],
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan context manager.

    Handles startup/shutdown lifecycle for the simulation service.
    Initializes database connections and simulation engine on startup,
    cleans up resources on shutdown.

    Args:
        app: The FastAPI application instance.

    Yields:
        None: Application runs until shutdown.
    """
    # ── Startup ────────────────────────────────────────────────
    db = DatabaseManager()
    db.connect()
    dependencies.db_instance = db

    config = _default_config()
    metrics_gen = MetricsGenerator(seed=config.seed)
    broadcaster = EventBroadcaster()
    anomaly_engine = AnomalyEngine()
    engine = SimulationEngine(
        config, db, metrics_gen,
        broadcaster=broadcaster,
        anomaly_engine=anomaly_engine,
    )
    dependencies.engine_instance = engine
    dependencies.broadcaster_instance = broadcaster
    dependencies.anomaly_engine_instance = anomaly_engine

    yield

    # ── Shutdown ───────────────────────────────────────────────
    if engine.get_status() == SimulatorStatus.RUNNING:
        await engine.stop()
    db.close()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Sets up CORS middleware, includes the API router, and registers
    the health check endpoint.

    Returns:
        FastAPI: Configured application instance ready to serve.
    """
    app = FastAPI(
        title="HPA++ Simulation Service",
        description="Realistic Kubernetes cluster simulation for "
                    "predictive HPA testing and demos.",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv(
            "CORS_ORIGINS",
            "http://localhost:8501,http://localhost:3000",
        ).split(","),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router, prefix="/api/v1")

    @app.get("/health")
    async def health_check():
        """Basic health check endpoint."""
        return {"status": "healthy", "service": "simulation"}

    return app
