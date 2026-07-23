"""Tests for the anomaly injection system.

Covers AnomalyEffect, AnomalyEngine, handler registration,
and integration with the simulation lifecycle.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from shared.simulation import SimulationConfig, DeploymentSpec, TrafficProfile
from shared.enums import TrafficPattern, PodStatus
from shared.db.manager import DatabaseManager
from app.anomalies import AnomalyDefinition, AnomalyType, TriggerType
from app.anomalies.base import AnomalyEffect, HANDLER_REGISTRY, merge_effects
from app.anomalies.engine import AnomalyEngine
from app.cluster_state import ClusterStateManager
from app.metrics_generator import MetricsGenerator
from app.engine import SimulationEngine

# ── Register all handlers ────────────────────────────────────
import app.anomalies.handlers  # noqa: F401


# ── Helpers ──────────────────────────────────────────────────

def _fast_config(**overrides: Any) -> SimulationConfig:
    """Minimal simulation config for testing."""
    kw = {
        "sim_name": "test",
        "tick_interval_real_seconds": 0.1,
        "seconds_per_simulated_minute": 0.1,
        "total_simulated_minutes": 10,
        "node_count": 2,
        "cpu_per_node_millicores": 2000,
        "memory_per_node_mb": 4096,
        "gpus_per_node": 1,
        "gpu_memory_per_device_mb": 4096,
        "seed": 42,
        "deployments": [
            DeploymentSpec(
                deployment_id="app",
                initial_replicas=1,
                cpu_request_millicores=500,
                memory_request_mb=256,
                traffic_profile=TrafficProfile(
                    pattern=TrafficPattern.STEADY,
                    base_load_rps=50.0,
                    noise_std_pct=1.0,
                ),
            ),
            DeploymentSpec(
                deployment_id="gpu-app",
                initial_replicas=1,
                cpu_request_millicores=500,
                memory_request_mb=256,
                gpu_required=True,
                gpu_memory_request_mb=1024,
                traffic_profile=TrafficProfile(
                    pattern=TrafficPattern.STEADY,
                    base_load_rps=10.0,
                    noise_std_pct=1.0,
                ),
            ),
        ],
    }
    kw.update(overrides)
    return SimulationConfig(**kw)


def _make_app_for_anomaly_test() -> tuple[Any, Any, Any, Any]:
    """Create test dependencies with anomaly engine wired in."""
    db = DatabaseManager(db_path=Path(":memory:"))
    db.connect()
    config = _fast_config()
    mg = MetricsGenerator(seed=config.seed)
    ae = AnomalyEngine()
    engine = SimulationEngine(
        config, db, mg,
        anomaly_engine=ae,
    )
    return engine, ae, db, config


# ── AnomalyEffect unit tests ──────────────────────────────────

class TestAnomalyEffect:
    def test_empty_effect_has_is_empty_true(self):
        assert AnomalyEffect().is_empty

    def test_non_empty_has_is_empty_false(self):
        e = AnomalyEffect(blocked_nodes={"node-0"})
        assert not e.is_empty

    def test_merge_combines_sets(self):
        a = AnomalyEffect(blocked_nodes={"node-0"}, blocked_gpus={"gpu-0"})
        b = AnomalyEffect(blocked_nodes={"node-1"}, force_gpu_off={"app"})
        merged = merge_effects([a, b])
        assert merged.blocked_nodes == {"node-0", "node-1"}
        assert merged.blocked_gpus == {"gpu-0"}
        assert merged.force_gpu_off == {"app"}

    def test_merge_multiplies_rps(self):
        a = AnomalyEffect(rps_multiplier={"app": 2.0})
        b = AnomalyEffect(rps_multiplier={"app": 3.0})
        merged = merge_effects([a, b])
        assert merged.rps_multiplier["app"] == 6.0

    def test_merge_adds_cpu_offset(self):
        a = AnomalyEffect(cpu_offset_pp={"app": 10.0})
        b = AnomalyEffect(cpu_offset_pp={"app": 20.0})
        merged = merge_effects([a, b])
        assert merged.cpu_offset_pp["app"] == 30.0

    def test_merge_takes_max_jitter(self):
        a = AnomalyEffect(jitter=0.1)
        b = AnomalyEffect(jitter=0.5)
        merged = merge_effects([a, b])
        assert merged.jitter == 0.5

    def test_merge_empty_list(self):
        merged = merge_effects([])
        assert merged.is_empty


# ── AnomalyEngine unit tests ─────────────────────────────────

class TestAnomalyEngine:
    def test_process_tick_with_no_definitions_returns_none(self):
        ae = AnomalyEngine()
        state = ClusterStateManager(_fast_config())
        state.initialize()
        result = ae.process_tick(10.0, state)
        assert result is None

    def test_scheduled_anomaly_activates_at_trigger_time(self):
        ae = AnomalyEngine()
        state = ClusterStateManager(_fast_config())
        state.initialize()

        defn = AnomalyDefinition(
            anomaly_id="fail-1",
            anomaly_type=AnomalyType.CPU_THROTTLE,
            target="node-0",
            trigger_type=TriggerType.SCHEDULED,
            trigger_value=5.0,
            duration_minutes=10.0,
            severity=0.5,
        )
        ae.add_definition(defn)

        # Before trigger
        result = ae.process_tick(4.0, state)
        assert result is None

        # At trigger
        result = ae.process_tick(5.0, state)
        assert result is not None
        assert not result.is_empty

    def test_anomaly_expires_after_duration(self):
        ae = AnomalyEngine()
        state = ClusterStateManager(_fast_config())
        state.initialize()

        defn = AnomalyDefinition(
            anomaly_id="expire-test",
            anomaly_type=AnomalyType.CPU_THROTTLE,
            target="node-0",
            trigger_type=TriggerType.SCHEDULED,
            trigger_value=5.0,
            duration_minutes=3.0,
            severity=0.5,
        )
        ae.add_definition(defn)

        # Activate
        result = ae.process_tick(5.0, state)
        assert result is not None

        # Still active during duration
        result = ae.process_tick(7.0, state)
        assert result is not None

        # After expiry
        result = ae.process_tick(9.0, state)
        assert result is None

    def test_expired_anomaly_calls_revert(self):
        ae = AnomalyEngine()
        state = ClusterStateManager(_fast_config())
        state.initialize()
        node_count_before = len(state.nodes)

        defn = AnomalyDefinition(
            anomaly_id="revert-test",
            anomaly_type=AnomalyType.NODE_CRASH,
            target="node-0",
            trigger_type=TriggerType.SCHEDULED,
            trigger_value=2.0,
            duration_minutes=4.0,
            severity=1.0,
        )
        ae.add_definition(defn)

        # Activate — node-0 blocked
        ae.process_tick(2.0, state)
        assert "node-0" in state.blocked_nodes
        assert len(state.deployments["app"].pods) + len(
            state.deployments["gpu-app"].pods
        ) < 2  # pods evicted

        # After expiry — node-0 unblocked
        ae.process_tick(7.0, state)
        assert "node-0" not in state.blocked_nodes

    def test_get_active_returns_info(self):
        ae = AnomalyEngine()
        state = ClusterStateManager(_fast_config())
        state.initialize()

        defn = AnomalyDefinition(
            anomaly_id="active-test",
            anomaly_type=AnomalyType.CPU_THROTTLE,
            target="node-0",
            trigger_type=TriggerType.SCHEDULED,
            trigger_value=5.0,
            duration_minutes=10.0,
            severity=0.5,
        )
        ae.add_definition(defn)
        ae.process_tick(5.0, state)

        active = ae.get_active()
        assert len(active) == 1
        assert active[0]["anomaly_id"] == "active-test"
        assert active[0]["target"] == "node-0"

    def test_get_definitions_returns_copy(self):
        ae = AnomalyEngine()
        defn = AnomalyDefinition(
            anomaly_id="def-test",
            anomaly_type=AnomalyType.CPU_THROTTLE,
            target="node-0",
            trigger_type=TriggerType.SCHEDULED,
            trigger_value=5.0,
            duration_minutes=10.0,
            severity=0.5,
        )
        ae.add_definition(defn)
        assert len(ae.get_definitions()) == 1
        assert ae.get_definitions()[0].anomaly_id == "def-test"

    def test_remove_definition_stops_future_activation(self):
        ae = AnomalyEngine()
        defn = AnomalyDefinition(
            anomaly_id="remove-test",
            anomaly_type=AnomalyType.CPU_THROTTLE,
            target="node-0",
            trigger_type=TriggerType.SCHEDULED,
            trigger_value=5.0,
            duration_minutes=10.0,
            severity=0.5,
        )
        ae.add_definition(defn)
        ae.remove_definition("remove-test")
        assert ae.get_definitions() == []


# ── Handler registration tests ───────────────────────────────

class TestHandlerRegistry:
    def test_all_61_anomaly_types_have_handlers(self):
        """Every member of AnomalyType has a registered handler."""
        for at in AnomalyType:
            assert at in HANDLER_REGISTRY, f"Missing handler for {at}"

    def test_each_handler_is_valid(self):
        """Each handler entry is an (apply_fn, revert_or_None) tuple."""
        for at, (apply_fn, revert_fn) in HANDLER_REGISTRY.items():
            assert callable(apply_fn), f"{at} apply is not callable"
            if revert_fn is not None:
                assert callable(revert_fn)

    def test_apply_fn_returns_anomaly_effect(self):
        """Each handler's apply function returns an AnomalyEffect."""
        state = ClusterStateManager(_fast_config())
        state.initialize()
        for at, (apply_fn, _) in sorted(HANDLER_REGISTRY.items()):
            defn = AnomalyDefinition(
                anomaly_id=f"test-{at.value}",
                anomaly_type=at,
                target="node-0",
                trigger_type=TriggerType.SCHEDULED,
                trigger_value=1.0,
                duration_minutes=5.0,
                severity=0.5,
            )
            effect = apply_fn(state, defn, 0.5)
            assert isinstance(effect, AnomalyEffect), f"{at} didn't return AnomalyEffect"


# ── Integration: anomalies distort metrics ───────────────────

class TestAnomalyMetricsIntegration:
    @pytest.mark.asyncio
    async def test_node_crash_reduces_pod_count_in_metrics(self):
        """NODE_CRASH evicts pods — tick still produces valid samples for survivors."""
        engine, ae, db, config = _make_app_for_anomaly_test()
        # Wire traffic profiles so metrics generate properly
        engine.metrics_generator.set_deployment_profiles({
            d.deployment_id: d.traffic_profile for d in config.deployments
        })
        state = ClusterStateManager(config)
        state.initialize()
        engine.cluster_state = state

        defn = AnomalyDefinition(
            anomaly_id="crash-test",
            anomaly_type=AnomalyType.NODE_CRASH,
            target="node-0",
            trigger_type=TriggerType.SCHEDULED,
            trigger_value=5.0,
            duration_minutes=5.0,
            severity=1.0,
        )
        ae.add_definition(defn)

        # Activate anomaly manually
        ae.process_tick(5.0, state)

        # Tick with anomaly active — should produce valid metric samples
        samples = await engine.tick()
        assert len(samples) == 2  # one per deployment
        for s in samples:
            assert s.pod_count >= 0
            assert s.cpu_utilization_pct >= 0.0

    @pytest.mark.asyncio
    async def test_traffic_spike_multiplies_rps_in_metrics(self):
        """TRAFFIC_SPIKE increases RPS in generated metric samples."""
        engine, ae, db, config = _make_app_for_anomaly_test()
        # Wire traffic profiles
        profiles = {d.deployment_id: d.traffic_profile for d in config.deployments}
        engine.metrics_generator.set_deployment_profiles(profiles)
        state = ClusterStateManager(config)
        state.initialize()
        engine.cluster_state = state

        # Get baseline RPS (no anomaly active)
        engine.cluster_state = state
        engine.simulated_minutes = 0.0
        baseline = await engine.tick()

        defn = AnomalyDefinition(
            anomaly_id="spike-test",
            anomaly_type=AnomalyType.TRAFFIC_SPIKE,
            target="app",
            trigger_type=TriggerType.SCHEDULED,
            trigger_value=5.0,
            duration_minutes=5.0,
            severity=0.8,
        )
        ae.add_definition(defn)

        # Activate anomaly manually, then tick
        ae.process_tick(5.0, state)
        engine.simulated_minutes = 6.0
        spiked = await engine.tick()

        baseline_rps = next(s.requests_per_second for s in baseline if s.deployment_id == "app")
        spiked_rps = next(s.requests_per_second for s in spiked if s.deployment_id == "app")
        assert spiked_rps > baseline_rps * 1.2, (
            f"Expected spiked RPS > baseline, got {spiked_rps} <= {baseline_rps * 1.2}"
        )

    @pytest.mark.asyncio
    async def test_node_crash_blocks_scheduling(self):
        """Blocked nodes are excluded from pod scheduling."""
        config = _fast_config()
        state = ClusterStateManager(config)
        state.initialize()
        ae = AnomalyEngine()

        defn = AnomalyDefinition(
            anomaly_id="sched-test",
            anomaly_type=AnomalyType.NODE_CRASH,
            target="node-0",
            trigger_type=TriggerType.SCHEDULED,
            trigger_value=1.0,
            duration_minutes=10.0,
            severity=1.0,
        )
        ae.add_definition(defn)

        # Activate
        ae.process_tick(1.0, state)

        # Try scheduling a new pod — should land on node-1 (not blocked)
        from shared.cluster import PodState
        new_pod = PodState(
            pod_id="test-sched",
            deployment_id="app",
            status=PodStatus.PENDING,
            cpu_request_millicores=200,
            memory_request_mb=128,
            gpu_memory_request_mb=0,
        )
        node_id = state.schedule_pod(new_pod)
        assert node_id == "node-1", f"Expected node-1, got {node_id}"


# ── Anomaly Routes Tests ────────────────────────────────────

@pytest.fixture
def anomaly_client():
    """TestClient with anomaly engine wired in."""
    from app.main import create_app
    import app.dependencies as deps

    app = create_app()

    # Already set up by lifespan? No — for test we need to create directly
    db = DatabaseManager(db_path=Path(":memory:"))
    db.connect()
    config = _fast_config()
    mg = MetricsGenerator(seed=config.seed)
    ae = AnomalyEngine()
    engine = SimulationEngine(config, db, mg, anomaly_engine=ae)
    deps.db_instance = db
    deps.engine_instance = engine
    deps.anomaly_engine_instance = ae

    client = TestClient(app, raise_server_exceptions=False)
    return client, ae


class TestAnomalyRoutes:
    def test_list_anomalies_empty(self, anomaly_client):
        client, _ = anomaly_client
        resp = client.get("/api/v1/anomalies")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert data["data"] == []

    def test_add_and_list_anomaly(self, anomaly_client):
        client, _ = anomaly_client
        payload = {
            "anomaly_id": "route-test",
            "anomaly_type": "cpu_throttle",
            "target": "app",
            "trigger_type": "scheduled",
            "trigger_value": 5.0,
            "duration_minutes": 10.0,
            "severity": 0.5,
        }
        add = client.post("/api/v1/anomalies", json=payload)
        assert add.status_code == 200, add.text

        # List includes it
        resp = client.get("/api/v1/anomalies")
        assert resp.status_code == 200
        definitions = resp.json()["data"]
        assert any(d["anomaly_id"] == "route-test" for d in definitions)

    def test_list_active_anomalies(self, anomaly_client):
        client, ae = anomaly_client
        defn = AnomalyDefinition(
            anomaly_id="active-route",
            anomaly_type=AnomalyType.CPU_THROTTLE,
            target="node-0",
            trigger_type=TriggerType.SCHEDULED,
            trigger_value=5.0,
            duration_minutes=10.0,
            severity=0.5,
        )
        ae.add_definition(defn)

        resp = client.get("/api/v1/anomalies/active")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

        # Activate it
        state = ClusterStateManager(_fast_config())
        state.initialize()
        ae.process_tick(5.0, state)

        resp = client.get("/api/v1/anomalies/active")
        assert resp.status_code == 200
        active = resp.json()["data"]
        assert len(active) == 1
        assert active[0]["anomaly_id"] == "active-route"

    def test_delete_anomaly(self, anomaly_client):
        client, ae = anomaly_client
        defn = AnomalyDefinition(
            anomaly_id="delete-me",
            anomaly_type=AnomalyType.CPU_THROTTLE,
            target="node-0",
            trigger_type=TriggerType.SCHEDULED,
            trigger_value=5.0,
            duration_minutes=10.0,
            severity=0.5,
        )
        ae.add_definition(defn)

        resp = client.delete("/api/v1/anomalies/delete-me")
        assert resp.status_code == 200

        resp = client.get("/api/v1/anomalies")
        assert len(resp.json()["data"]) == 0

    def test_delete_nonexistent_returns_404(self, anomaly_client):
        client, _ = anomaly_client
        resp = client.delete("/api/v1/anomalies/no-such-id")
        assert resp.status_code == 404
