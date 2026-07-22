"""Dependency injection for the integration service.

Provides singleton instances and FastAPI dependency functions for
the orchestrator, benchmark runner, demo manager, and database.
"""

from __future__ import annotations

from typing import Any

from app.orchestrator import PipelineOrchestrator
from app.benchmark_runner import BenchmarkRunner
from app.demo_setup import DemoManager


# ── Singleton instances ─────────────────────────────────────────────

orchestrator_instance: PipelineOrchestrator | None = None
benchmark_instance: BenchmarkRunner | None = None
demo_instance: DemoManager | None = None


async def get_orchestrator() -> PipelineOrchestrator:
    """Get or create the singleton PipelineOrchestrator.

    Returns:
        PipelineOrchestrator: The shared orchestrator instance.

    Raises:
        RuntimeError: If the orchestrator cannot be initialized.

    TODO: Lazy-init with proper service URL resolution from config.
    """
    ...


async def get_benchmark_runner() -> BenchmarkRunner:
    """Get or create the singleton BenchmarkRunner.

    Returns:
        BenchmarkRunner: The shared benchmark runner instance.

    Raises:
        RuntimeError: If the runner cannot be initialized.

    TODO: Wire up dependency injection for database and orchestrator.
    """
    ...


async def get_demo_manager() -> DemoManager:
    """Get or create the singleton DemoManager.

    Returns:
        DemoManager: The shared demo manager instance.

    Raises:
        RuntimeError: If the demo manager cannot be initialized.

    TODO: Pass orchestrator and db dependencies on first init.
    """
    ...


async def get_db() -> Any:
    """Get the database connection or session.

    Returns:
        Any: Database connection/session object.

    Raises:
        ConnectionError: If the database is unreachable.

    TODO: Implement connection pooling and health checks.
    """
    ...
