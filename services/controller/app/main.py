"""Controller service — FastAPI app factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import dependencies as deps
from app.executor import ScaleExecutor
from app.gpu_scheduler import GpuScheduler
from app.routes import router, _sim_http, _sim_base_url
from app.scaler import PredictiveController
from httpx import AsyncClient
from shared.db.manager import DatabaseManager


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialize controller singletons on startup, clean up on shutdown."""
    # Database
    db = DatabaseManager()
    db.init_db()

    # Simulation base URL (configurable via env or default)
    sim_url = "http://simulation:8001/api/v1"
    forecast_url = "http://forecast:8002/api/v1"

    # Shared HTTP client for routes
    deps.db_instance = db
    routes_http = AsyncClient(timeout=10.0, verify=False)
    routes_setattr = getattr(router, "_sim_http", None)
    globals()["_sim_http"] = routes_http

    # Core components
    deps.controller_instance = PredictiveController(
        db_manager=db,
        forecast_base_url=forecast_url,
        sim_base_url=sim_url,
    )
    deps.executor_instance = ScaleExecutor(
        mode="simulation",
        sim_base_url=sim_url,
    )
    deps.scheduler_instance = GpuScheduler(
        db_manager=db,
    )

    # Copy _sim_base_url into routes module for HTTP calls
    # (the routes already reference the global)
    import app.routes as routes_mod
    routes_mod._sim_http = routes_http
    routes_mod._sim_base_url = sim_url

    yield

    # Shutdown
    await routes_http.aclose()
    deps.controller_instance = None
    deps.executor_instance = None
    deps.scheduler_instance = None
    deps.db_instance = None


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="HPA++ Controller",
        description="Predictive scaling controller with risk-aware evaluation and GPU scheduling",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router, prefix="/api/v1")

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    return app
