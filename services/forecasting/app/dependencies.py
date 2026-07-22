"""Dependency injection for the Forecasting microservice.

Provides FastAPI Depends() callables that supply database managers,
pipeline instances, and other shared resources to route handlers.
"""

from typing import Annotated

from fastapi import Depends

from app.pipeline import ForecastPipeline


async def get_db() -> None:
    """Yield the shared DatabaseManager for request-scoped access.

    Reads the database manager from app.state (set during lifespan).
    Ensures the connection is healthy before yielding.

    Returns:
        A connected DatabaseManager instance.

    Raises:
        RuntimeError: If the database is not initialised or unreachable.

    TODO:
        - Return actual DatabaseManager instance from app.state
        - Add connection health check (ping/query)
        - Implement request-scoped transaction support
    """
    ...


async def get_pipeline(
    db: Annotated[None, Depends(get_db)],
) -> ForecastPipeline:
    """Create or retrieve a ForecastPipeline for the current request.

    Builds a pipeline wired to the database manager and the
    default deployment. Reused across requests within the same
    lifespan via app.state caching.

    Args:
        db: The database manager dependency.

    Returns:
        A ready-to-use ForecastPipeline instance.

    TODO:
        - Cache pipeline instances by deployment_id in app.state
        - Inject model configuration from environment
        - Support per-request deployment_id override
    """
    ...
