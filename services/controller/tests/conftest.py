"""Controller test configuration and fixtures."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Ensure project root is on the path for shared/ imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Set DB path to in-memory for tests
os.environ["HPAP_DB_PATH"] = ":memory:"

from shared.db.manager import DatabaseManager
from shared.decisions import ScalingConfig, ScalingDecision, ScalingAction


@pytest.fixture
def in_memory_db() -> DatabaseManager:
    """Create an in-memory database for tests."""
    db = DatabaseManager()
    db.init_db()
    return db


@pytest.fixture
def default_config() -> ScalingConfig:
    """Default scaling config for testing."""
    return ScalingConfig(
        deployment_id="web-app",
        min_replicas=1,
        max_replicas=10,
        risk_asymmetry_factor=5.0,
        baseline_per_pod=100.0,
        cooldown_seconds=30,
        upscale_cpu_threshold_pct=70.0,
    )


@pytest.fixture
def sample_decision(in_memory_db, default_config) -> ScalingDecision:
    """Create and persist a sample scaling decision."""
    decision = ScalingDecision(
        deployment_id="web-app",
        simulated_time_utc="2026-07-23T12:00:00Z",
        action=ScalingAction.SCALE_UP,
        current_pod_count=3,
        target_pod_count=5,
        execution_source="predictive",
        forecast_yhat=150.0,
        forecast_lower=120.0,
        forecast_upper=180.0,
        risk_score=0.3,
        confidence_score=0.75,
        risk_level="medium",
        formula_raw_target=5.0,
        formula_confidence_factor=0.75,
        formula_risk_bias=1.5,
        formula_final_before_clamp=6.5,
        executed=False,
    )
    in_memory_db.insert_scaling_decision(decision)
    return decision