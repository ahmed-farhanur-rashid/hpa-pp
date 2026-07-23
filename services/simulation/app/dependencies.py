"""Dependency injection for the Simulation Service.

Uses singleton pattern for the simulation engine and database manager.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.anomalies.engine import AnomalyEngine
from app.engine import SimulationEngine
from app.events import EventBroadcaster

if TYPE_CHECKING:
    from shared.db.manager import DatabaseManager

# ── Singleton instances ────────────────────────────────────────

engine_instance: SimulationEngine | None = None
db_instance: DatabaseManager | None = None
broadcaster_instance: EventBroadcaster | None = None
anomaly_engine_instance: AnomalyEngine | None = None


async def get_simulation_engine() -> SimulationEngine:
    """FastAPI dependency that returns the singleton SimulationEngine.

    Returns:
        SimulationEngine: The singleton engine instance.

    Raises:
        RuntimeError: If engine has not been initialized (startup incomplete).
    """
    if engine_instance is None:
        raise RuntimeError(
            "Simulation engine not initialised. Call init_simulation() first."
        )
    return engine_instance


async def get_db() -> DatabaseManager:
    """FastAPI dependency that returns the DatabaseManager.

    Returns:
        DatabaseManager: The database manager instance.

    Raises:
        RuntimeError: If DB connection has not been established.
    """
    if db_instance is None:
        raise RuntimeError(
            "Database not initialised. Call init_database() first."
        )
    return db_instance
