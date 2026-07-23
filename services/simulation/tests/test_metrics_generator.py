"""Tests for the MetricsGenerator class."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.metrics_generator import MetricsGenerator
from shared.metrics import MetricSample
from shared.cluster import DeploymentState, NodeState, ClusterSnapshot, PodState
from shared.enums import PodStatus, NodeStatus, TrafficPattern
from shared.simulation import TrafficProfile


# ── Helper fixtures ────────────────────────────────────────────

def _make_deployment(
    dep_id: str,
    replicas: int,
    cpu_req: int = 500,
    mem_req_mb: int = 512,
    requires_gpu: bool = False,
) -> DeploymentState:
    return DeploymentState(
        deployment_id=dep_id,
        current_replicas=replicas,
        target_replicas=replicas,
        available_replicas=replicas,
        pods=[PodState(
            pod_id=f"{dep_id}-pod-{i}",
            deployment_id=dep_id,
            status=PodStatus.RUNNING,
            node_id="node-0",
            cpu_request_millicores=cpu_req,
            memory_request_mb=mem_req_mb,
        ) for i in range(replicas)],
        cpu_request_millicores=cpu_req,
        memory_request_mb=mem_req_mb,
        requires_gpu=requires_gpu,
    )


def _make_snapshot(deployments: list[DeploymentState]) -> ClusterSnapshot:
    return ClusterSnapshot(
        snapshot_id="test-snap-001",
        simulated_time_utc="2026-01-01T00:00:00Z",
        nodes=[],
        deployments=deployments,
        total_pods=sum(d.current_replicas for d in deployments),
        running_pods=sum(d.current_replicas for d in deployments),
        pending_pods=0,
        gpu_count=0,
        gpu_utilization_avg_pct=None,
        total_cpu_millicores=16000,
        allocated_cpu_millicores=8000,
        total_memory_mb=32768,
        allocated_memory_mb=16384,
    )


# ── Tests ──────────────────────────────────────────────────────

class TestMetricsGenerator:
    """Test MetricsGenerator output and behavior."""

    def test_generate_batch_one_per_deployment(self, metrics_generator):
        """generate_batch should return one sample per deployment."""
        deps = [
            _make_deployment("web", 2),
            _make_deployment("api", 3),
        ]
        metrics_generator.set_deployment_profiles({
            "web": TrafficProfile(pattern=TrafficPattern.STEADY, base_load_rps=50.0),
            "api": TrafficProfile(pattern=TrafficPattern.STEADY, base_load_rps=30.0),
        })
        snap = _make_snapshot(deps)
        samples = metrics_generator.generate_batch(deps, snap, simulated_time=30.0)
        assert len(samples) == 2
        assert {s.deployment_id for s in samples} == {"web", "api"}

    def test_generate_batch_field_ranges(self, metrics_generator):
        """All metric fields should be within valid ranges."""
        deps = [_make_deployment("web", 2)]
        metrics_generator.set_deployment_profiles({
            "web": TrafficProfile(
                pattern=TrafficPattern.SINE_WAVE,
                base_load_rps=80.0,
                spike_multiplier=2.0,
                period_minutes=30,
                noise_std_pct=2.0,
            ),
        })
        snap = _make_snapshot(deps)
        samples = metrics_generator.generate_batch(deps, snap, simulated_time=15.0)
        sample = samples[0]

        assert 0.0 <= sample.cpu_utilization_pct <= 100.0
        assert sample.memory_usage_mb >= 0.0
        assert sample.requests_per_second >= 0.0
        assert sample.pod_count > 0
        assert sample.simulated_time_utc is not None

    def test_generate_batch_with_gpu(self, metrics_generator):
        """GPU deployments should have gpu_utilization_pct set."""
        deps = [_make_deployment("ml-inference", 1, requires_gpu=True, mem_req_mb=4096)]
        metrics_generator.set_deployment_profiles({
            "ml-inference": TrafficProfile(
                pattern=TrafficPattern.EXAM_START,
                base_load_rps=10.0,
                spike_multiplier=5.0,
                spike_minute=20,
                spike_duration_minutes=60,
                noise_std_pct=2.0,
            ),
        })
        snap = _make_snapshot(deps)
        samples = metrics_generator.generate_batch(deps, snap, simulated_time=30.0)
        sample = samples[0]

        assert sample.gpu_utilization_pct is not None
        assert 0.0 <= sample.gpu_utilization_pct <= 100.0

    def test_generate_batch_without_gpu(self, metrics_generator):
        """Non-GPU deployments should have gpu_utilization_pct as None."""
        deps = [_make_deployment("web", 2)]
        metrics_generator.set_deployment_profiles({
            "web": TrafficProfile(pattern=TrafficPattern.STEADY, base_load_rps=50.0),
        })
        snap = _make_snapshot(deps)
        samples = metrics_generator.generate_batch(deps, snap, simulated_time=30.0)
        assert samples[0].gpu_utilization_pct is None

    def test_generate_batch_no_profile(self, metrics_generator):
        """Deployments without a profile should return zero metrics."""
        deps = [_make_deployment("unknown", 1)]
        snap = _make_snapshot(deps)
        samples = metrics_generator.generate_batch(deps, snap, simulated_time=30.0)
        assert samples[0].cpu_utilization_pct == 0.0
        assert samples[0].requests_per_second == 0.0

    def test_simulated_time_progression(self, metrics_generator):
        """simulated_time_utc should advance with simulated_time."""
        deps = [_make_deployment("web", 2)]
        metrics_generator.set_deployment_profiles({
            "web": TrafficProfile(pattern=TrafficPattern.STEADY, base_load_rps=50.0),
        })
        snap = _make_snapshot(deps)

        s1 = metrics_generator.generate_batch(deps, snap, simulated_time=0.0)
        s2 = metrics_generator.generate_batch(deps, snap, simulated_time=30.0)
        assert s2[0].simulated_time_utc > s1[0].simulated_time_utc

    def test_cpu_increases_with_rps(self, metrics_generator):
        """Higher RPS should result in higher CPU utilization."""
        deps = [_make_deployment("web", 1)]
        snap = _make_snapshot(deps)

        # Low load
        metrics_generator.set_deployment_profiles({
            "web": TrafficProfile(pattern=TrafficPattern.STEADY, base_load_rps=10.0),
        })
        low = metrics_generator.generate_batch(deps, snap, simulated_time=30.0)[0]

        # High load
        metrics_generator.set_deployment_profiles({
            "web": TrafficProfile(pattern=TrafficPattern.STEADY, base_load_rps=500.0),
        })
        high = metrics_generator.generate_batch(deps, snap, simulated_time=30.0)[0]

        assert high.cpu_utilization_pct > low.cpu_utilization_pct

    def test_noise_zero_returns_exact(self, metrics_generator):
        """_add_noise with noise_std_pct=0 should return exact value."""
        result = metrics_generator._add_noise(50.0, 0.0)
        assert result == 50.0

    def test_noise_positive_with_noise(self, metrics_generator):
        """_add_noise with positive std should produce variation."""
        noisy = metrics_generator._add_noise(50.0, 10.0)
        assert noisy >= 0

    def test_latency_increases_with_cpu(self, metrics_generator):
        """Latency should increase as CPU utilization approaches 100%."""
        deps = [_make_deployment("web", 1)]
        snap = _make_snapshot(deps)

        metrics_generator.set_deployment_profiles({
            "web": TrafficProfile(pattern=TrafficPattern.STEADY, base_load_rps=10.0),
        })
        low_latency = metrics_generator.generate_batch(deps, snap, 30.0)[0].latency_ms

        metrics_generator.set_deployment_profiles({
            "web": TrafficProfile(pattern=TrafficPattern.STEADY, base_load_rps=1000.0),
        })
        high_latency = metrics_generator.generate_batch(deps, snap, 30.0)[0].latency_ms

        assert low_latency is not None
        assert high_latency is not None
        assert high_latency >= low_latency
