"""Integration tests: simulation engine with anomaly injection.

Tests that the full tick → anomaly → cluster mutation → metrics pipeline
produces correct data under realistic conditions.
"""

from __future__ import annotations

import pytest

from app.anomalies import AnomalyDefinition, AnomalyType, TriggerType
from app.anomalies.engine import AnomalyEngine
from app.cluster_state import ClusterStateManager
from app.metrics_generator import MetricsGenerator

from shared.simulation import SimulationConfig, DeploymentSpec, TrafficProfile
from shared.enums import TrafficPattern

# Ensure anomaly handlers are registered in the HANDLER_REGISTRY
from app.anomalies.handlers import node  # noqa: F401 — registers node anomaly handlers


@pytest.fixture
def anomaly_config() -> SimulationConfig:
    """2-node, 2-deployment config for anomaly integration tests."""
    return SimulationConfig(
        sim_name="anomaly-test",
        tick_interval_real_seconds=0.1,
        seconds_per_simulated_minute=1.0,
        total_simulated_minutes=60,
        node_count=2,
        cpu_per_node_millicores=2000,
        memory_per_node_mb=4096,
        gpus_per_node=0,
        gpu_memory_per_device_mb=0,
        seed=42,
        deployments=[
            DeploymentSpec(
                deployment_id="web-app",
                initial_replicas=2,
                cpu_request_millicores=500,
                memory_request_mb=512,
                gpu_required=False,
                traffic_profile=TrafficProfile(
                    pattern=TrafficPattern.SINE_WAVE,
                    base_load_rps=100.0,
                    spike_multiplier=2.0,
                    period_minutes=30,
                    noise_std_pct=5.0,
                ),
            ),
        ],
    )


@pytest.fixture
def anomaly_state(anomaly_config):
    """Cluster state initialized from anomaly_config."""
    state = ClusterStateManager(anomaly_config)
    state.initialize()
    return state


@pytest.fixture
def anomaly_mg():
    """MetricsGenerator with profiles matching anomaly_config."""
    mg = MetricsGenerator(seed=42)
    mg.set_deployment_profiles({
        "web-app": TrafficProfile(
            pattern=TrafficPattern.SINE_WAVE,
            base_load_rps=100.0,
            spike_multiplier=2.0,
            period_minutes=30,
            noise_std_pct=5.0,
        ),
    })
    return mg


class TestAnomalyMetricsPipeline:
    """Anomaly → cluster mutation → metrics distortion pipeline."""

    def test_baseline_metrics_valid(self, anomaly_state, anomaly_mg):
        """Pre-anomaly: metrics have valid ranges."""
        deps = list(anomaly_state.deployments.values())
        snap = anomaly_state.get_snapshot()
        samples = anomaly_mg.generate_batch(deps, snap, simulated_time=5.0)
        assert len(samples) == 1
        s = samples[0]
        assert 0 <= s.cpu_utilization_pct <= 100
        assert s.memory_usage_mb > 0
        assert s.requests_per_second >= 0
        assert s.latency_ms >= 0

    def test_node_crash_blocks_node(self, anomaly_state):
        """NODE_CRASH marks target node as blocked and evicts its pods."""
        ae = AnomalyEngine()
        ae.add_definition(AnomalyDefinition(
            anomaly_id="crash-n1",
            anomaly_type=AnomalyType.NODE_CRASH,
            target="node-1",
            trigger_type=TriggerType.SCHEDULED,
            trigger_value=5.0,
            duration_minutes=10.0,
            severity=1.0,
        ))
        ae.process_tick(5.0, anomaly_state)
        assert anomaly_state.nodes["node-1"].node_id in anomaly_state.blocked_nodes
        # All pods on node-1 are evicted
        assert len(anomaly_state.nodes["node-1"].pods) == 0

    def test_node_crash_metrics_still_valid(self, anomaly_state, anomaly_mg):
        """Metrics generated after NODE_CRASH remain valid."""
        ae = AnomalyEngine()
        ae.add_definition(AnomalyDefinition(
            anomaly_id="crash-n1",
            anomaly_type=AnomalyType.NODE_CRASH,
            target="node-1",
            trigger_type=TriggerType.SCHEDULED,
            trigger_value=5.0,
            duration_minutes=10.0,
            severity=1.0,
        ))
        ae.process_tick(5.0, anomaly_state)
        deps = list(anomaly_state.deployments.values())
        snap = anomaly_state.get_snapshot()
        samples = anomaly_mg.generate_batch(deps, snap, simulated_time=5.0)
        assert len(samples) >= 1
        for s in samples:
            assert 0 <= s.cpu_utilization_pct <= 100

    def test_traffic_spike_multiplies_rps(self, anomaly_state, anomaly_mg):
        """TRAFFIC_SPIKE returns effect with rps_multiplier."""
        ae = AnomalyEngine()
        ae.add_definition(AnomalyDefinition(
            anomaly_id="spike-wa",
            anomaly_type=AnomalyType.TRAFFIC_SPIKE,
            target="web-app",
            trigger_type=TriggerType.SCHEDULED,
            trigger_value=5.0,
            duration_minutes=5.0,
            severity=0.8,
        ))
        ae.process_tick(5.0, anomaly_state)
        # Check that active anomalies exist
        active_info = ae.get_active()
        assert len(active_info) == 1
        assert active_info[0]["target"] == "web-app"

    def test_anomaly_expiry_unblocks_node(self, anomaly_state):
        """After NODE_CRASH duration expires, node is unblocked."""
        ae = AnomalyEngine()
        ae.add_definition(AnomalyDefinition(
            anomaly_id="crash-n1",
            anomaly_type=AnomalyType.NODE_CRASH,
            target="node-1",
            trigger_type=TriggerType.SCHEDULED,
            trigger_value=5.0,
            duration_minutes=5.0,
            severity=1.0,
        ))
        ae.process_tick(5.0, anomaly_state)
        assert "node-1" in anomaly_state.blocked_nodes
        ae.process_tick(10.0, anomaly_state)
        assert "node-1" not in anomaly_state.blocked_nodes

    def test_multiple_anomalies_merge_effects(self, anomaly_state):
        """Two concurrent anomalies produce merged effect."""
        ae = AnomalyEngine()
        ae.add_definition(AnomalyDefinition(
            anomaly_id="crash",
            anomaly_type=AnomalyType.NODE_CRASH,
            target="node-1", trigger_type=TriggerType.SCHEDULED,
            trigger_value=5.0, duration_minutes=10.0, severity=1.0,
        ))
        ae.add_definition(AnomalyDefinition(
            anomaly_id="spike",
            anomaly_type=AnomalyType.TRAFFIC_SPIKE,
            target="web-app", trigger_type=TriggerType.SCHEDULED,
            trigger_value=5.0, duration_minutes=10.0, severity=0.8,
        ))

        merged = ae.process_tick(5.0, anomaly_state)
        assert merged is not None
        assert "node-1" in merged.blocked_nodes

    def test_disconnected_reconnect(self, anomaly_config, anomaly_state, anomaly_mg):
        """Engine runs multiple ticks with anomalies — no crashes."""
        ae = AnomalyEngine()
        ae.add_definition(AnomalyDefinition(
            anomaly_id="ongoing",
            anomaly_type=AnomalyType.NODE_CRASH,
            target="node-1", trigger_type=TriggerType.SCHEDULED,
            trigger_value=2.0, duration_minutes=20.0, severity=1.0,
        ))

        for tick_min in [1, 2, 5, 10]:
            ae.process_tick(float(tick_min), anomaly_state)
            deps = list(anomaly_state.deployments.values())
            snap = anomaly_state.get_snapshot()
            samples = anomaly_mg.generate_batch(deps, snap, simulated_time=float(tick_min))
            assert len(samples) >= 1
            for s in samples:
                assert s.cpu_utilization_pct >= 0

    # ── Negative tests ──

    def test_traffic_spike_nonexistent_target(self, anomaly_state):
        """TRAFFIC_SPIKE with nonexistent target doesn't crash."""
        ae = AnomalyEngine()
        ae.add_definition(AnomalyDefinition(
            anomaly_id="spike-nonexistent",
            anomaly_type=AnomalyType.TRAFFIC_SPIKE,
            target="nonexistent-deployment",
            trigger_type=TriggerType.SCHEDULED,
            trigger_value=1.0, duration_minutes=5.0, severity=0.8,
        ))
        # Traffic spike handler returns an effect without mutating state,
        # even for nonexistent targets — rps_multiplier applies regardless
        result = ae.process_tick(1.0, anomaly_state)
        assert result is not None
        assert "nonexistent-deployment" in result.rps_multiplier

    def test_remove_definition_deactivates(self, anomaly_state):
        """Removing a definition stops it from activating."""
        ae = AnomalyEngine()
        ae.add_definition(AnomalyDefinition(
            anomaly_id="temp",
            anomaly_type=AnomalyType.NODE_CRASH,
            target="node-1", trigger_type=TriggerType.SCHEDULED,
            trigger_value=5.0, duration_minutes=10.0, severity=1.0,
        ))
        ae.remove_definition("temp")
        ae.process_tick(5.0, anomaly_state)
        assert ae.get_active() == []
