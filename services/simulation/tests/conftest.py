"""Pytest configuration and shared fixtures for the Simulation Service tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

# ── Ensure shared module is importable ──────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent  # HPA-pp/
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("HPAP_DB_PATH", ":memory:")

# ── pytest-asyncio: auto-mode for all async tests ──────────────
def pytest_configure(config):
    """Configure pytest-asyncio to auto-detect async tests."""
    config.option.asyncio_mode = "auto"


@pytest.fixture
def default_config():
    """Create a small SimulationConfig for testing."""
    from shared.simulation import SimulationConfig, DeploymentSpec, TrafficProfile
    from shared.enums import TrafficPattern

    return SimulationConfig(
        sim_name="test-sim",
        tick_interval_real_seconds=0.1,
        seconds_per_simulated_minute=0.5,
        total_simulated_minutes=60,
        node_count=2,
        cpu_per_node_millicores=2000,
        memory_per_node_mb=4096,
        gpus_per_node=1,
        gpu_memory_per_device_mb=8192,
        seed=42,
        deployments=[
            DeploymentSpec(
                deployment_id="test-web",
                initial_replicas=2,
                cpu_request_millicores=500,
                memory_request_mb=512,
                traffic_profile=TrafficProfile(
                    pattern=TrafficPattern.STEADY,
                    base_load_rps=50.0,
                    noise_std_pct=2.0,
                ),
            ),
            DeploymentSpec(
                deployment_id="test-gpu",
                initial_replicas=1,
                cpu_request_millicores=1000,
                memory_request_mb=1024,
                gpu_required=True,
                gpu_memory_request_mb=2048,
                traffic_profile=TrafficProfile(
                    pattern=TrafficPattern.SINE_WAVE,
                    base_load_rps=20.0,
                    spike_multiplier=2.0,
                    period_minutes=10,
                    noise_std_pct=1.0,
                ),
            ),
        ],
    )


@pytest.fixture
def in_memory_db():
    """Create a DatabaseManager backed by an in-memory SQLite DB."""
    from shared.db.manager import DatabaseManager

    db = DatabaseManager(db_path=Path(":memory:"))
    db.connect()
    yield db
    db.close()


@pytest.fixture
def metrics_generator():
    """Create a MetricsGenerator with fixed seed for reproducibility."""
    from app.metrics_generator import MetricsGenerator

    return MetricsGenerator(seed=42)


@pytest.fixture
def cluster_state(default_config):
    """Create and initialize a ClusterStateManager from the default config."""
    from app.cluster_state import ClusterStateManager

    csm = ClusterStateManager(default_config)
    csm.initialize()
    return csm


@pytest.fixture
def simulation_engine(default_config, in_memory_db, metrics_generator):
    """Create a SimulationEngine wired with test dependencies."""
    from app.engine import SimulationEngine

    return SimulationEngine(default_config, in_memory_db, metrics_generator)


@pytest_asyncio.fixture
async def running_engine(simulation_engine):
    """Start the simulation engine and yield it for test use."""
    await simulation_engine.start()
    yield simulation_engine
    await simulation_engine.stop()
