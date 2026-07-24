"""Controller dependency injection — singleton wiring."""

from __future__ import annotations

from typing import AsyncGenerator, Optional

from shared.db.manager import DatabaseManager

from app.executor import ScaleExecutor
from app.gpu_scheduler import GpuScheduler
from app.scaler import PredictiveController

# ── Singleton instances (set in lifespan) ──────────────────────

controller_instance: Optional[PredictiveController] = None
executor_instance: Optional[ScaleExecutor] = None
scheduler_instance: Optional[GpuScheduler] = None
db_instance: Optional[DatabaseManager] = None


# ── FastAPI dependency functions ───────────────────────────────

async def get_controller() -> PredictiveController:
    if controller_instance is None:
        raise RuntimeError("Controller not initialized")
    return controller_instance


async def get_executor() -> ScaleExecutor:
    if executor_instance is None:
        raise RuntimeError("Executor not initialized")
    return executor_instance


async def get_gpu_scheduler() -> GpuScheduler:
    if scheduler_instance is None:
        raise RuntimeError("GPU scheduler not initialized")
    return scheduler_instance


async def get_db() -> AsyncGenerator[DatabaseManager, None]:
    if db_instance is None:
        raise RuntimeError("Database not initialized")
    yield db_instance
