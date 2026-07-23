"""Tests for PredictiveController — risk-aware scaling evaluation."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.scaler import PredictiveController
from shared.forecast import (
    ForecastTrajectory,
    TrajectoryPoint,
    TrajectorySummary,
    TrajectoryQuality,
    FeatureValue,
)


def _make_trajectory_rps(
    values: list[float],
    forecast_id: str = "test-001",
) -> ForecastTrajectory:
    """Build a ForecastTrajectory with given RPS values."""
    points = [
        TrajectoryPoint(
            minute=21 + i,
            features={
                "requests_per_second": FeatureValue(
                    value=v,
                    lower=v * 0.85,
                    upper=v * 1.15,
                ),
            },
        )
        for i, v in enumerate(values)
    ]
    peak = max(values) if values else 100.0
    return ForecastTrajectory(
        forecast_id=forecast_id,
        deployment_id="web-app",
        points=points,
        summary=TrajectorySummary(
            peak_requests_per_second=FeatureValue(
                value=peak, lower=peak * 0.85, upper=peak * 1.15,
            ),
            trend="rising",
            volatility=0.15,
        ),
            quality=TrajectoryQuality(status="success"),
        generation_time_utc="2026-07-23T12:00:00Z",
        model_version="test",
        features_predicted=["requests_per_second"],
        horizon_minutes=30,
    )


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.query_scaling_decisions.return_value = []
    return db


@pytest.fixture
def controller(mock_db, default_config):
    return PredictiveController(
        db_manager=mock_db,
        forecast_base_url="http://forecast:8002/api/v1",
        sim_base_url="http://simulation:8001/api/v1",
        default_confidence=0.8,
    )


class TestPredictiveController:
    """Unit tests for PredictiveController."""

    def test_compute_target_pods_basic(self, controller, default_config):
        """Compute target pods from raw + risk is clamped to bounds."""
        target = controller.compute_target_pods(3, 0.9, 0.2, default_config)
        assert 1 <= target <= 10
        assert target >= 3

    def test_compute_target_pods_min_clamp(self, controller, default_config):
        target = controller.compute_target_pods(0, 1.0, 0.0, default_config)
        assert target == default_config.min_replicas

    def test_compute_target_pods_max_clamp(self, controller, default_config):
        target = controller.compute_target_pods(50, 1.0, 0.0, default_config)
        assert target == default_config.max_replicas

    def test_compute_target_pods_high_risk_bonus(self, controller, default_config):
        """Risk score > 0.6 adds urgency bonus."""
        low = controller.compute_target_pods(3, 1.0, 0.2, default_config)
        high = controller.compute_target_pods(3, 1.0, 0.8, default_config)
        assert high >= low

    def test_extract_peak_rps_from_points(self, controller):
        forecast = _make_trajectory_rps([10, 50, 30, 80, 20])
        peak = controller._extract_peak_rps(forecast)
        assert peak == 80.0

    def test_extract_peak_rps_none(self, controller):
        peak = controller._extract_peak_rps(None)
        assert peak == 100.0

    def test_confidence_factor_from_ci(self, controller):
        forecast = _make_trajectory_rps([100])
        confidence = controller._compute_confidence_factor(forecast, 100.0)
        assert 0.5 <= confidence <= 1.0

    def test_confidence_factor_fallback(self, controller):
        confidence = controller._compute_confidence_factor(None, 100.0)
        assert confidence == 0.8

    def test_risk_score_range(self, controller):
        forecast = _make_trajectory_rps([50, 60, 70])
        score = controller._compute_risk_score(forecast, [])
        assert 0.0 <= score <= 1.0

    def test_determine_action_scale_up(self, controller):
        assert controller._determine_action(5, 3).value == "scale_up"

    def test_determine_action_scale_down(self, controller):
        assert controller._determine_action(2, 5).value == "scale_down"

    def test_determine_action_noop(self, controller):
        assert controller._determine_action(5, 5).value == "hold"

    def test_get_decision_history_empty(self, controller, mock_db):
        mock_db.query_scaling_decisions.return_value = []
        history = controller.get_decision_history("web-app")
        assert history == []

    @pytest.mark.asyncio
    async def test_fetch_forecast_unavailable(self, controller):
        """Forecast service down returns None gracefully."""
        result = await controller._fetch_forecast("web-app")
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_current_replicas_unavailable(self, controller):
        """Simulation service down returns default 1."""
        result = await controller._fetch_current_replicas("web-app")
        assert result == 1

    def test_extract_forecast_bounds(self, controller):
        forecast = _make_trajectory_rps([100])
        yhat, lo, hi = controller._extract_forecast_bounds(forecast, 100.0)
        assert yhat == 100.0
        assert lo < hi
