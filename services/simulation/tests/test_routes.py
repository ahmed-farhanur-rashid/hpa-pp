"""Tests for the FastAPI simulation API routes.

Uses TestClient with overridden dependencies to avoid real DB/engine init.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from shared.simulation import SimulatorStatus
from shared.enums import TrafficPattern
from shared.simulation import SimulationConfig, DeploymentSpec, TrafficProfile


# ── Helpers ────────────────────────────────────────────────────

def _make_client():
    """Create TestClient with fresh engine + DB for each call."""
    from app.main import create_app
    from app.dependencies import engine_instance, db_instance
    from shared.db.manager import DatabaseManager
    from app.metrics_generator import MetricsGenerator
    from app.engine import SimulationEngine
    from pathlib import Path

    app = create_app()

    db = DatabaseManager(db_path=Path(":memory:"))
    db.connect()

    config = SimulationConfig(
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
                ),
            ),
        ],
    )

    mg = MetricsGenerator(seed=42)
    engine = SimulationEngine(config, db, mg)

    import app.dependencies as deps
    deps.db_instance = db
    deps.engine_instance = engine

    client = TestClient(app)
    return client, engine, db


def _api_data(resp):
    """Extract data field from an ApiResponse JSON body."""
    return resp.json()["data"]


# ── Health ─────────────────────────────────────────────────────

class TestHealth:
    """Test health check endpoint."""

    def test_health_endpoint(self):
        """GET /health should return 200."""
        client, _, _ = _make_client()
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"


# ── Simulation Control ─────────────────────────────────────────

class TestSimControl:
    """Test simulation lifecycle endpoints."""

    def test_get_initial_status(self):
        """GET /api/v1/sim/status should show STOPPED initially."""
        client, _, _ = _make_client()
        resp = client.get("/api/v1/sim/status")
        assert resp.status_code == 200
        assert _api_data(resp)["status"] == SimulatorStatus.STOPPED

    def test_start_simulation(self):
        """POST /api/v1/sim/start should transition to RUNNING."""
        client, engine, _ = _make_client()
        resp = client.post("/api/v1/sim/start")
        assert resp.status_code == 200
        assert _api_data(resp)["status"] == SimulatorStatus.RUNNING
        # Stop so the next test gets a clean start
        asyncio.run(engine.stop())

    def test_start_twice_returns_error(self):
        """Starting twice should return error."""
        client, engine, _ = _make_client()
        # Start once
        resp = client.post("/api/v1/sim/start")
        assert resp.status_code == 200

        # Start again — should fail with RuntimeError from engine
        resp = client.post("/api/v1/sim/start")
        assert resp.status_code == 500

        asyncio.run(engine.stop())

    def test_pause_simulation(self):
        """POST /api/v1/sim/pause should transition to PAUSED."""
        client, engine, _ = _make_client()
        resp = client.post("/api/v1/sim/start")
        assert resp.status_code == 200

        resp = client.post("/api/v1/sim/pause")
        assert resp.status_code == 200
        assert _api_data(resp)["status"] == SimulatorStatus.PAUSED

        asyncio.run(engine.stop())

    def test_pause_without_start(self):
        """Pausing without start should return 500."""
        client, engine, _ = _make_client()
        resp = client.post("/api/v1/sim/pause")
        assert resp.status_code == 500
        asyncio.run(engine.stop())

    def test_stop_without_start(self):
        """Stopping without start should succeed (no-op)."""
        client, engine, _ = _make_client()
        resp = client.post("/api/v1/sim/stop")
        assert resp.status_code == 200
        assert _api_data(resp)["status"] == SimulatorStatus.STOPPED

    def test_stop_simulation(self):
        """POST /api/v1/sim/stop should reset to STOPPED."""
        client, engine, _ = _make_client()
        client.post("/api/v1/sim/start")
        resp = client.post("/api/v1/sim/stop")
        assert resp.status_code == 200
        assert _api_data(resp)["status"] == SimulatorStatus.STOPPED
        asyncio.run(engine.stop())


# ── Metrics ────────────────────────────────────────────────────

class TestMetrics:
    """Test metrics endpoints."""

    def test_get_metrics_empty(self):
        """GET /api/v1/metrics should return empty list initially."""
        client, _, _ = _make_client()
        resp = client.get("/api/v1/metrics")
        assert resp.status_code == 200
        assert _api_data(resp) == []

    def test_get_metrics_with_params(self):
        """GET /api/v1/metrics should accept filter params."""
        client, _, _ = _make_client()
        resp = client.get(
            "/api/v1/metrics",
            params={"deployment_id": "test-web", "limit": 50},
        )
        assert resp.status_code == 200

    def test_get_latest_metrics(self):
        """GET /api/v1/metrics/latest should work."""
        client, _, _ = _make_client()
        resp = client.get("/api/v1/metrics/latest")
        assert resp.status_code == 200

    def test_get_latest_with_count(self):
        """GET /api/v1/metrics/latest should respect count param."""
        client, _, _ = _make_client()
        resp = client.get("/api/v1/metrics/latest", params={"count": 5})
        assert resp.status_code == 200


# ── Cluster State ──────────────────────────────────────────────

class TestClusterState:
    """Test cluster state endpoints."""

    def test_cluster_state_before_start(self):
        """GET /api/v1/cluster/state before start should return 400."""
        client, _, _ = _make_client()
        resp = client.get("/api/v1/cluster/state")
        assert resp.status_code == 400

    def test_cluster_nodes_before_start(self):
        """GET /api/v1/cluster/nodes before start should return empty."""
        client, _, _ = _make_client()
        resp = client.get("/api/v1/cluster/nodes")
        assert resp.status_code == 200
        assert _api_data(resp) == []

    def test_cluster_deployments_before_start(self):
        """GET /api/v1/cluster/deployments before start should return empty."""
        client, _, _ = _make_client()
        resp = client.get("/api/v1/cluster/deployments")
        assert resp.status_code == 200
        assert _api_data(resp) == []


# ── Configuration ──────────────────────────────────────────────

class TestConfig:
    """Test configuration endpoint."""

    def test_update_config(self):
        """POST /api/v1/sim/config should accept a new config."""
        from shared.simulation import SimulationConfig, DeploymentSpec, TrafficProfile
        from shared.enums import TrafficPattern

        client, _, _ = _make_client()

        new_config = SimulationConfig(
            sim_name="updated-sim",
            tick_interval_real_seconds=0.1,
            seconds_per_simulated_minute=0.5,
            total_simulated_minutes=30,
            node_count=1,
            cpu_per_node_millicores=2000,
            memory_per_node_mb=4096,
            gpus_per_node=0,
            gpu_memory_per_device_mb=0,
            seed=1,
            deployments=[
                DeploymentSpec(
                    deployment_id="web",
                    initial_replicas=1,
                    cpu_request_millicores=500,
                    memory_request_mb=512,
                    traffic_profile=TrafficProfile(
                        pattern=TrafficPattern.STEADY,
                        base_load_rps=30.0,
                    ),
                ),
            ],
        )

        resp = client.post(
            "/api/v1/sim/config",
            json={"config": new_config.model_dump(mode="json")},
        )
        assert resp.status_code == 200
        data = _api_data(resp)
        assert data["sim_name"] == "updated-sim"
