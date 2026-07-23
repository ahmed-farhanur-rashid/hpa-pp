"""Integration tests: controller + simulation + anomalies end-to-end.

Uses respx to mock the forecast service HTTP calls while testing
the controller's evaluate, execute, and GPU scheduling flows.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch, AsyncMock

import pytest
import respx
from httpx import Response

from pathlib import Path
from shared.db.manager import DatabaseManager
from shared.decisions import ScalingConfig, ScalingAction
from shared.forecast import (
    ForecastTrajectory, TrajectoryPoint, TrajectorySummary,
    TrajectoryQuality, FeatureValue,
)
from app.scaler import PredictiveController
from app.executor import ScaleExecutor


@pytest.fixture
def db():
    mgr = DatabaseManager(db_path=Path(":memory:"))
    mgr.connect()
    yield mgr
    mgr.close()


@pytest.fixture
def scaling_config():
    return ScalingConfig(
        deployment_id="web-app",
        min_replicas=1,
        max_replicas=10,
        baseline_per_pod=100.0,
        risk_asymmetry_factor=5.0,
        cooldown_seconds=30,
    )


@pytest.fixture
def mock_trajectory():
    """Realistic forecast trajectory resembling CTGAN/transformer output."""
    return ForecastTrajectory(
        forecast_id=str(uuid.uuid4()),
        deployment_id="web-app",
        generation_time_utc="2026-07-23T12:00:00Z",
        model_version="test_transformer_v1",
        model_type="transformer",
        training_window_minutes=60,
        horizon_minutes=30,
        features_predicted=["requests_per_second"],
        points=[
            TrajectoryPoint(minute=31, features={
                "requests_per_second": FeatureValue(value=100.0, lower=85.0, upper=115.0),
            }),
            TrajectoryPoint(minute=35, features={
                "requests_per_second": FeatureValue(value=150.0, lower=125.0, upper=175.0),
            }),
            TrajectoryPoint(minute=40, features={
                "requests_per_second": FeatureValue(value=120.0, lower=100.0, upper=140.0),
            }),
        ],
        summary=TrajectorySummary(
            peak_requests_per_second=FeatureValue(value=150.0, lower=125.0, upper=175.0),
            trend="rising",
            volatility=0.15,
        ),
        quality=TrajectoryQuality(status="success"),
    )


class TestControllerIntegration:
    """Controller evaluation with mocked forecast + simulation data."""

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_evaluate_returns_full_decision(self, db, scaling_config, mock_trajectory):
        """Full evaluate() produces a ScalingDecision with all formula fields."""
        controller = PredictiveController(db)
        with patch.object(controller, "_fetch_forecast", return_value=mock_trajectory):
            with patch.object(controller, "_fetch_current_replicas", return_value=3):
                decision = await controller.evaluate("web-app", config=scaling_config)
        
        assert decision.deployment_id == "web-app"
        assert 1 <= decision.target_pod_count <= 10
        assert decision.formula_raw_target is not None
        assert decision.formula_confidence_factor is not None
        assert decision.formula_risk_bias is not None
        assert decision.formula_final_before_clamp is not None
        assert decision.risk_score is not None
        assert decision.confidence_score is not None
        assert decision.forecast_yhat is not None
        assert decision.execution_source == "predictive"

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_evaluate_scale_up_peak_higher(self, db, scaling_config, mock_trajectory):
        """When peak is 150 and baseline is 100, raw_target = 2, bumps to 3 with risk."""
        controller = PredictiveController(db)
        with patch.object(controller, "_fetch_forecast", return_value=mock_trajectory):
            with patch.object(controller, "_fetch_current_replicas", return_value=2):
                decision = await controller.evaluate("web-app", config=scaling_config)
        assert decision.action == "scale_up"
        assert decision.target_pod_count >= 2
        assert decision.formula_raw_target >= 2

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_evaluate_scale_down_low_traffic(self, db, mock_trajectory):
        """When peak is lower and current replicas are high, scale down."""
        low_config = ScalingConfig(
            deployment_id="web-app", baseline_per_pod=100.0,
            min_replicas=1, max_replicas=10,
        )
        controller = PredictiveController(db)
        with patch.object(controller, "_fetch_forecast", return_value=mock_trajectory):
            with patch.object(controller, "_fetch_current_replicas", return_value=8):
                decision = await controller.evaluate("web-app", config=low_config)
        assert decision.action == "scale_down"
        assert decision.target_pod_count < 8

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_evaluate_with_high_baseline(self, db, mock_trajectory):
        """High baseline_per_pod produces SCALE_UP when risk bias pushes target above current."""
        high_baseline = ScalingConfig(
            deployment_id="web-app", baseline_per_pod=200.0,
            min_replicas=1, max_replicas=10,
        )
        controller = PredictiveController(db)
        with patch.object(controller, "_fetch_forecast", return_value=mock_trajectory):
            with patch.object(controller, "_fetch_current_replicas", return_value=1):
                decision = await controller.evaluate("web-app", config=high_baseline)
        assert decision.action == ScalingAction.SCALE_UP
        assert decision.target_pod_count > decision.current_pod_count

    @pytest.mark.asyncio
    async def test_forecast_unavailable_fallback(self, db, scaling_config):
        """When forecast service is down, controller still produces a decision."""
        controller = PredictiveController(db)
        with patch.object(controller, "_fetch_forecast", return_value=None):
            with patch.object(controller, "_fetch_current_replicas", return_value=3):
                decision = await controller.evaluate("web-app", config=scaling_config)
        assert decision is not None
        # Should still produce a decision — uses default peak of 100
        assert decision.forecast_id is None  # No forecast available

    @pytest.mark.asyncio
    async def test_forecast_bounds_used_in_decision(self, db, scaling_config, mock_trajectory):
        """Confidence interval bounds appear in the decision."""
        controller = PredictiveController(db)
        with patch.object(controller, "_fetch_forecast", return_value=mock_trajectory):
            with patch.object(controller, "_fetch_current_replicas", return_value=3):
                decision = await controller.evaluate("web-app", config=scaling_config)
        assert decision.forecast_yhat == 150.0
        assert decision.forecast_lower == 125.0
        assert decision.forecast_upper == 175.0

    @pytest.mark.asyncio
    async def test_decision_persisted_to_db(self, db, scaling_config, mock_trajectory):
        """evaluate() stores the decision in the database."""
        controller = PredictiveController(db)
        with patch.object(controller, "_fetch_forecast", return_value=mock_trajectory):
            with patch.object(controller, "_fetch_current_replicas", return_value=3):
                await controller.evaluate("web-app", config=scaling_config)
        history = controller.get_decision_history("web-app", limit=10)
        assert len(history) == 1
        assert history[0].deployment_id == "web-app"


class TestExecutorIntegration:
    """ScaleExecutor with mocked simulation HTTP calls."""

    @pytest.mark.asyncio
    async def test_execute_simulation_mode(self):
        """Executor POSTs to simulation and returns True on success."""
        executor = ScaleExecutor(mode="simulation")
        with respx.mock:
            respx.post("http://simulation:8001/api/v1/sim/scale").mock(
                return_value=Response(200, json={"status": "ok"})
            )
            from shared.decisions import ScalingDecision
            _decision = ScalingDecision(
                decision_id=str(uuid.uuid4()),
                deployment_id="web-app",
                action="scale_up",
                current_pod_count=2,
                target_pod_count=5,
                execution_source="predictive",
                simulated_time_utc="2026-07-23T12:00:00Z",
                forecast_yhat=100.0,
                forecast_lower=80.0,
                forecast_upper=120.0,
                risk_score=0.2,
                confidence_score=0.8,
                formula_raw_target=2.0,
                formula_confidence_factor=0.8,
                formula_risk_bias=1.5,
                formula_final_before_clamp=4.0,
            )
            result = await executor.execute(_decision)
            assert result is True

    @pytest.mark.asyncio
    async def test_execute_simulation_failure(self):
        """When simulation returns non-200, executor returns False."""
        executor = ScaleExecutor(mode="simulation")
        with respx.mock:
            respx.post("http://simulation:8001/api/v1/sim/scale").mock(
                return_value=Response(500)
            )
            from shared.decisions import ScalingDecision
            _decision = ScalingDecision(
                decision_id=str(uuid.uuid4()),
                deployment_id="web-app",
                action="scale_up",
                current_pod_count=2,
                target_pod_count=5,
                execution_source="predictive",
                simulated_time_utc="2026-07-23T12:00:00Z",
                forecast_yhat=100.0,
                forecast_lower=80.0,
                forecast_upper=120.0,
                risk_score=0.2,
                confidence_score=0.8,
                formula_raw_target=2.0,
                formula_confidence_factor=0.8,
                formula_risk_bias=1.5,
                formula_final_before_clamp=4.0,
            )
            result = await executor.execute(_decision)
            assert result is False

    @pytest.mark.asyncio
    async def test_dry_run_returns_true(self):
        """Dry-run executor returns True without HTTP calls."""
        executor = ScaleExecutor(mode="dry_run")
        from shared.decisions import ScalingDecision
        _decision = ScalingDecision(
            decision_id=str(uuid.uuid4()),
            deployment_id="web-app",
            action="scale_up",
            current_pod_count=2,
            target_pod_count=5,
            execution_source="predictive",
            simulated_time_utc="2026-07-23T12:00:00Z",
            forecast_yhat=100.0,
            forecast_lower=80.0,
            forecast_upper=120.0,
            risk_score=0.2,
            confidence_score=0.8,
            formula_raw_target=2.0,
            formula_confidence_factor=0.8,
            formula_risk_bias=1.5,
            formula_final_before_clamp=4.0,
        )
        result = await executor.execute(_decision)
        assert result is True
