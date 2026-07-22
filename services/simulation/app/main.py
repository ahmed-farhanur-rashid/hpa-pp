"""FastAPI application factory for the HPA++ Simulation Service.

Provides create_app() for both direct uvicorn invocation and testing.
"""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import router


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

    TODO:
        - Initialize DatabaseManager and store in app.state
        - Initialize SimulationEngine with default config
        - Clean up engine and DB connections on shutdown
    """
    ...
    yield
    ...


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Sets up CORS middleware, includes the API router, and registers
    the health check endpoint.

    Returns:
        FastAPI: Configured application instance ready to serve.

    TODO:
        - Add configurable CORS origins from environment
        - Add request logging middleware
        - Add OpenAPI metadata (title, description, version)
    """
    ...
