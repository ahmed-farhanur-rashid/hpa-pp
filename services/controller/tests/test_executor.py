"""Tests for ScaleExecutor and ReactiveFallback."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.executor import ScaleExecutor, ReactiveFallback
from shared.decisions import ScalingDecision, ScalingAction
from shared.metrics import MetricsSnapshot


def _make_decision(deployment: str = "web-app") -> ScalingDecision:
    return ScalingDecision(
        decision_id="test-decision-1",
        deployment_id=deployment,
        simulated_time_utc="2026-07-23T12:00:00Z",
        current_pod_count=3,
        target_pod_count=5,
        action=ScalingAction.SCALE_UP,
        execution_source="predictive",
        forecast_yhat=150.0,
        forecast_lower=120.0,
        forecast_upper=180.0,
        risk_score=0.3,
        confidence_score=0.75,
        risk_level="medium",
        formula_raw_target=2.0,
        formula_confidence_factor=0.75,
        formula_risk_bias=1.5,
        formula_final_before_clamp=3.5,
    )


def _make_snapshot(deployment: str = "web-app", cpu: float = 50.0) -> MetricsSnapshot:
    return MetricsSnapshot(
        deployment_id=deployment,
        simulated_time_utc="2026-07-23T12:00:00Z",
        cpu_utilization_pct=cpu,
        memory_usage_mb=512.0,
        requests_per_second=100.0,
        gpu_utilization_pct=0.0,
        latency_ms=12.0,
        pod_count=3,
    )


class TestReactiveFallback:
    """Tests for the reactive CPU-threshold fallback."""

    def test_init(self):
        rf = ReactiveFallback(cpu_threshold_pct=70.0)
        assert rf.cpu_threshold_pct == 70.0

    def test_init_invalid_threshold_raises(self):
        with pytest.raises(ValueError):
            ReactiveFallback(cpu_threshold_pct=-1.0)
        with pytest.raises(ValueError):
            ReactiveFallback(cpu_threshold_pct=200.0)

    def test_evaluate_scale_up(self, default_config):
        rf = ReactiveFallback(cpu_threshold_pct=70.0)
        snap = _make_snapshot(cpu=95.0)
        d = rf.evaluate(snap, current_pods=3, config=default_config)
        assert d is not None
        assert d.action == ScalingAction.SCALE_UP
        assert d.target_pod_count > 3

    def test_evaluate_normal_stays(self, default_config):
        rf = ReactiveFallback(cpu_threshold_pct=70.0)
        snap = _make_snapshot(cpu=65.0)
        d = rf.evaluate(snap, current_pods=3, config=default_config)
        assert d is None

    def test_evaluate_no_config(self):
        rf = ReactiveFallback(cpu_threshold_pct=80.0)
        snap = _make_snapshot(cpu=95.0)
        d = rf.evaluate(snap, current_pods=2)
        assert d is not None
        assert d.target_pod_count > 2
        assert d.execution_source == "reactive_fallback"

    def test_scale_down_hysteresis(self, default_config):
        rf = ReactiveFallback(cpu_threshold_pct=70.0)
        snap = _make_snapshot(cpu=20.0)
        d = rf.evaluate(snap, current_pods=5, config=default_config)
        assert d is not None
        assert d.action == ScalingAction.SCALE_DOWN

    def test_hysteresis_band_no_action(self, default_config):
        rf = ReactiveFallback(cpu_threshold_pct=70.0)
        snap = _make_snapshot(cpu=62.0)
        d = rf.evaluate(snap, current_pods=3, config=default_config)
        assert d is None


class TestScaleExecutor:
    """Tests for ScaleExecutor execution modes."""

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError):
            ScaleExecutor(mode="invalid")

    @pytest.mark.asyncio
    async def test_dry_run(self):
        ex = ScaleExecutor(mode="dry_run")
        assert await ex.execute(_make_decision()) is True

    @pytest.mark.asyncio
    async def test_simulation_mode(self):
        ex = ScaleExecutor(mode="dry_run")
        for _ in range(3):
            await ex.execute(_make_decision())
        log = ex.get_execution_log("web-app")
        assert len(log) >= 3

    @pytest.mark.asyncio
    async def test_rollback_dry_run(self):
        ex = ScaleExecutor(mode="dry_run")
        assert await ex.rollback(_make_decision()) is True
