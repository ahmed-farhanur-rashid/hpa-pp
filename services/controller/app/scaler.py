"""Predictive scaling controller — risk-aware evaluation engine.

Implements the 9-step evaluation pipeline that combines forecast
trajectories with risk assessment and confidence bounds to produce
auditable, explainable scaling decisions.
"""

from __future__ import annotations

import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx

from shared.db.manager import DatabaseManager
from shared.decisions import ScalingConfig, ScalingDecision, ScalingAction
from shared.forecast import ForecastTrajectory

from app.config import load_scaling_config

logger = logging.getLogger(__name__)


class PredictiveController:
    """Risk-aware predictive scaling controller.

    Combines forecasting output with risk assessment and confidence
    factors to compute optimal scaling targets.

    The 9-step evaluation is fully transparent — every intermediate
    value is recorded in the returned ScalingDecision for auditability.

    Args:
        db_manager: Database manager for reading/writing decisions.
        forecast_base_url: Base URL of the forecasting service.
        sim_base_url: Base URL of the simulation service.
        default_confidence: Default confidence when forecast lacks CI data.
    """

    def __init__(
        self,
        db_manager: DatabaseManager,
        forecast_base_url: str = "http://forecast:8002/api/v1",
        sim_base_url: str = "http://simulation:8001/api/v1",
        default_confidence: float = 0.8,
    ) -> None:
        self.db = db_manager
        self.forecast_base_url = forecast_base_url.rstrip("/")
        self.sim_base_url = sim_base_url.rstrip("/")
        self.default_confidence = default_confidence
        self._http = httpx.AsyncClient(timeout=10.0, verify=False)

    # ── Public API ──────────────────────────────────────────────

    async def evaluate(
        self,
        deployment_id: str,
        config: Optional[ScalingConfig] = None,
    ) -> ScalingDecision:
        """Full 9-step evaluation — the centrepiece of the controller.

        Args:
            deployment_id: Deployment to evaluate.
            config: Optional scaling config override.

        Returns:
            ScalingDecision with all formula fields populated.
        """
        # Step 0: Load config
        if config is None:
            config = load_scaling_config(deployment_id, self.db)

        # Step 1: Fetch forecast trajectory
        forecast = await self._fetch_forecast(deployment_id)

        # Step 2: Fetch current cluster state
        current_replicas = await self._fetch_current_replicas(deployment_id)

        # Step 3: Extract peak RPS from forecast
        peak_rps = self._extract_peak_rps(forecast)

        # Step 4: Compute raw pod target
        raw_target = max(1, math.ceil(peak_rps / config.baseline_per_pod))

        # Step 5: Compute confidence factor from CI width
        confidence = self._compute_confidence_factor(forecast, peak_rps)

        # Step 6: Compute risk score
        history = self.get_decision_history(deployment_id, 20)
        risk_score = self._compute_risk_score(forecast, history)

        # Step 7-8: Apply risk bias and clamp
        urgency_bonus = 1.0 if risk_score > 0.6 else 0.0
        risk_bias = risk_score * config.risk_asymmetry_factor + urgency_bonus
        final_before = raw_target + risk_bias
        final_replicas = max(
            config.min_replicas,
            min(config.max_replicas, math.ceil(final_before)),
        )

        # Step 9: Determine action
        action = self._determine_action(final_replicas, current_replicas)

        # Build decision with full audit trail
        forecast_id = forecast.forecast_id if forecast else None
        forecast_yhat, forecast_lower, forecast_upper = self._extract_forecast_bounds(
            forecast, peak_rps,
        )

        risk_level = "low"
        if risk_score > 0.3:
            risk_level = "medium"
        if risk_score > 0.6:
            risk_level = "high"

        decision = ScalingDecision(
            decision_id=str(uuid.uuid4()),
            deployment_id=deployment_id,
            simulated_time_utc=datetime.now(timezone.utc).isoformat(),
            current_pod_count=current_replicas,
            target_pod_count=final_replicas,
            action=action,
            execution_source="predictive",
            forecast_id=forecast_id,
            forecast_yhat=forecast_yhat,
            forecast_lower=forecast_lower,
            forecast_upper=forecast_upper,
            risk_score=risk_score,
            confidence_score=confidence,
            risk_level=risk_level,
            formula_raw_target=float(raw_target),
            formula_confidence_factor=confidence,
            formula_risk_bias=risk_bias,
            formula_final_before_clamp=float(final_before),
        )

        self.db.insert_scaling_decision(decision.model_dump(mode="json"))
        logger.info(
            "Evaluated %s: action=%s target=%d (raw=%d, risk=%.2f, conf=%.2f)",
            deployment_id, action.value, final_replicas,
            raw_target, risk_score, confidence,
        )
        return decision

    def compute_target_pods(
        self,
        raw_target: int,
        confidence_factor: float,
        risk_score: float,
        config: ScalingConfig,
    ) -> int:
        """Apply risk bias and clamp to [min, max].

        Args:
            raw_target: Pod count from forecast alone.
            confidence_factor: Confidence in the prediction (0-1).
            risk_score: Aggregate risk score (0-1).
            config: Scaling config with min/max bounds.

        Returns:
            Final target pod count within configured bounds.
        """
        urgency_bonus = 1.0 if risk_score > 0.6 else 0.0
        risk_bias = risk_score * config.risk_asymmetry_factor + urgency_bonus
        final_before = raw_target + risk_bias
        return max(
            config.min_replicas,
            min(config.max_replicas, math.ceil(final_before)),
        )

    def get_decision_history(
        self,
        deployment_id: str,
        limit: int = 100,
    ) -> list[ScalingDecision]:
        """Retrieve recent scaling decisions for a deployment.

        Args:
            deployment_id: Deployment to query.
            limit: Max decisions to return.

        Returns:
            List of ScalingDecision ordered by time descending.
        """
        rows = self.db.query_scaling_decisions(
            deployment_id=deployment_id, limit=limit,
        )
        result: list[ScalingDecision] = []
        for r in rows:
            r.pop("id", None)  # Remove DB auto-increment PK
            result.append(ScalingDecision.model_validate(r))
        return result

    # ── Internal helpers ────────────────────────────────────────

    async def _fetch_forecast(
        self, deployment_id: str,
    ) -> ForecastTrajectory | None:
        """Fetch forecast trajectory from the forecasting service.

        Returns None if the service is unavailable.
        """
        try:
            resp = await self._http.get(
                f"{self.forecast_base_url}/forecast/trajectory",
                params={"deployment_id": deployment_id, "horizon_minutes": 30},
            )
            if resp.status_code == 200:
                body = resp.json()
                if body.get("success") and body.get("data"):
                    return ForecastTrajectory.model_validate(body["data"])
            return None
        except Exception as e:
            logger.warning("Forecast service unavailable: %s", e)
            return None

    async def _fetch_current_replicas(self, deployment_id: str) -> int:
        """Get current replica count from the simulation.

        Returns 1 as a safe default if the simulation is unreachable.
        """
        try:
            resp = await self._http.get(
                f"{self.sim_base_url}/cluster/deployments",
            )
            if resp.status_code == 200:
                body = resp.json()
                for dep in body.get("data", []):
                    if dep.get("deployment_id") == deployment_id:
                        return int(dep.get("current_replicas", 1))
            return 1
        except Exception as e:
            logger.warning("Simulation service unavailable: %s", e)
            return 1

    def _extract_peak_rps(self, forecast: ForecastTrajectory | None) -> float:
        """Extract the peak predicted RPS from a forecast trajectory.

        Falls back to 100.0 if no forecast data is available.
        """
        if forecast is None:
            return 100.0

        # Prefer summary field
        if forecast.summary and forecast.summary.peak_requests_per_second:
            return forecast.summary.peak_requests_per_second.value

        # Fallback: max over all trajectory points
        if forecast.points:
            values = [
                p.features.get("requests_per_second")
                for p in forecast.points
            ]
            valid = [v.value for v in values if v and v.value is not None]
            if valid:
                return max(valid)

        return 100.0

    def _compute_confidence_factor(
        self,
        forecast: ForecastTrajectory | None,
        peak_rps: float,
    ) -> float:
        """Compute confidence factor from forecast prediction interval width.

        Falls back to default_confidence when CI data is unavailable.
        """
        if forecast is None:
            return self.default_confidence

        # Try to find CI at the peak point
        for p in forecast.points or []:
            fv = p.features.get("requests_per_second")
            if fv and fv.value == peak_rps and fv.lower is not None and fv.upper is not None:
                if fv.value > 0:
                    ci_width = (fv.upper - fv.lower) / fv.value
                    return max(0.0, min(1.0, 1.0 - ci_width))

        return self.default_confidence

    def _compute_risk_score(
        self,
        forecast: ForecastTrajectory | None,
        history: list[ScalingDecision],
    ) -> float:
        """Compute risk score from historical miss-rate, CI uncertainty,
        and trajectory volatility.

        Returns 0.0–1.0 where higher = riskier.
        """
        miss_rate = 0.3
        if history:
            misses = sum(
                1 for d in history
                if d.risk_score is not None and d.risk_score > 0.5
            )
            miss_rate = misses / max(1, len(history))

        volatility = (
            forecast.summary.volatility
            if forecast and forecast.summary
            else 0.15
        )
        ci_uncertainty = 1.0 - self._compute_confidence_factor(forecast, 0.0)

        score = (
            0.4 * miss_rate
            + 0.3 * volatility
            + 0.3 * ci_uncertainty
        )
        return min(1.0, max(0.0, score))

    def _determine_action(
        self,
        target: int,
        current: int,
    ) -> ScalingAction:
        """Determine the scaling action based on target vs current."""
        if target > current:
            return ScalingAction.SCALE_UP
        if target < current:
            return ScalingAction.SCALE_DOWN
        return ScalingAction.HOLD

    def _extract_forecast_bounds(
        self,
        forecast: ForecastTrajectory | None,
        peak_rps: float,
    ) -> tuple[float, float, float]:
        """Extract yhat, lower, upper at the peak RPS point."""
        if forecast is None:
            return (peak_rps, peak_rps, peak_rps)

        for p in forecast.points or []:
            fv = p.features.get("requests_per_second")
            if fv and fv.value == peak_rps:
                return (
                    peak_rps,
                    fv.lower or peak_rps,
                    fv.upper or peak_rps,
                )

        if forecast.points:
            first = forecast.points[0].features.get("requests_per_second")
            if first:
                return (
                    first.value or peak_rps,
                    first.lower or peak_rps,
                    first.upper or peak_rps,
                )

        return (peak_rps, peak_rps, peak_rps)
