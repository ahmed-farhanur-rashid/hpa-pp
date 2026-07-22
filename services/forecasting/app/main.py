"""FastAPI application factory for the Forecasting microservice.

Creates the app with lifespan management, CORS, and health check.
Deployed independently on Render via Docker.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager.

    Initialises shared resources on startup and tears them down on shutdown.
    Runs as the `lifespan` parameter to FastAPI, so it wraps every request.

    Args:
        app: The FastAPI application instance being managed.

    Yields:
        None — control is returned to FastAPI while the app is running.

    TODO:
        - Initialise SQLite connection pool (sqlite3-worker) on startup
        - Store db_manager in app.state for dependency injection
        - Gracefully close the connection pool on shutdown
        - Add startup log with model version and configuration
    """
    ...


def create_app() -> FastAPI:
    """FastAPI application factory.

    Builds and configures the Forecasting service application.
    Called by uvicorn via `uvicorn "app.main:create_app()"`.

    Returns:
        A fully configured FastAPI instance ready to serve requests.

    TODO:
        - Load configuration from environment variables (DB path, model params)
        - Register the router with prefix "/api/v1"
        - Configure CORS for the frontend origin
        - Add OpenAPI metadata (title, version, description)
    """
    ...
