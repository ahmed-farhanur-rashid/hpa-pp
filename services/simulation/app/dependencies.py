"""Dependency injection for the Simulation Service.

Uses singleton pattern for the simulation engine and database manager.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.engine import SimulationEngine

if TYPE_CHECKING:
    from shared.db.manager import DatabaseManager

# ── Singleton instances ────────────────────────────────────────

engine_instance: SimulationEngine | None = None


async def get_simulation_engine() -> SimulationEngine:
    """FastAPI dependency that returns the singleton SimulationEngine.

    Returns:
        SimulationEngine: The singleton engine instance.

    Raises:
        RuntimeError: If engine has not been initialized (startup incomplete).

    TODO:
        - Add health check that verifies engine is responsive
        - Support multiple engine instances for multi-sim scenarios
    """
    ...


async def get_db() -> DatabaseManager:
    """FastAPI dependency that returns the DatabaseManager.

    Returns:
        DatabaseManager: The database manager instance.

    Raises:
        RuntimeError: If DB connection has not been established.

    TODO:
        - Ensure connection is alive before returning
        - Add connection pooling support
    """
    ...
