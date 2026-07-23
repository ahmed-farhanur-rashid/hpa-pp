"""
Scaling execution module.
"""
from __future__ import annotations

import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx

from shared.decisions import ScalingAction, ScalingConfig, ScalingDecision
from shared.metrics import MetricsSnapshot

logger = logging.getLogger(__name__)


class ScaleExecutor:
    """Executes scaling decisions against target infrastructure.

    Supports multiple execution modes for testing and production use.

    Attributes:
        MODE_SIMULATION: Simulation mode for testing.
        MODE_REAL_K8S: Real Kubernetes cluster execution.
        MODE_DRY_RUN: Dry-run mode (validates without executing).
    """

    MODE_SIMULATION = "simulation"
    MODE_REAL_K8S = "real_kubernetes"
    MODE_DRY_RUN = "dry_run"

    def __init__(
        self,
        mode: str = "simulation",
        sim_base_url: str = "http://simulation:8001/api/v1",
    ) -> None:
        """Initialize ScaleExecutor.

        Args:
            mode: Execution mode (simulation, real_kubernetes, dry_run).
            sim_base_url: Base URL for the simulation API.

        Raises:
            ValueError: If mode is not a valid execution mode.
        """
        if mode not in (self.MODE_SIMULATION, self.MODE_REAL_K8S, self.MODE_DRY_RUN):
            raise ValueError(
                f"Invalid mode '{mode}'. Must be one of: "
                f"{self.MODE_SIMULATION}, {self.MODE_REAL_K8S}, {self.MODE_DRY_RUN}"
            )
        self.mode = mode
        self.sim_base_url = sim_base_url.rstrip("/")
        self._http = httpx.AsyncClient(timeout=10.0)
        self._log: list[dict] = []

    async def execute(self, decision: ScalingDecision) -> bool:
        """Execute a scaling decision.

        Applies the scaling action specified in the decision to the
        target infrastructure.

        Args:
            decision: Scaling decision to execute.

        Returns:
            bool: True if execution succeeded, False otherwise.
        """
        log_entry = {
            "decision_id": decision.decision_id,
            "deployment_id": decision.deployment_id,
            "action": decision.action.value,
            "target_replicas": decision.target_pod_count,
            "current_replicas": decision.current_pod_count,
            "mode": self.mode,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if self.mode == self.MODE_DRY_RUN:
            log_entry["result"] = "dry_run_success"
            self._log.append(log_entry)
            logger.info(
                "Dry-run execution for deployment %s: target=%d",
                decision.deployment_id,
                decision.target_pod_count,
            )
            return True

        if self.mode == self.MODE_SIMULATION:
            url = f"{self.sim_base_url}/sim/scale"
            payload = {
                "deployment_id": decision.deployment_id,
                "target_replicas": decision.target_pod_count,
                "execution_source": decision.execution_source,
            }
            try:
                response = await self._http.post(url, json=payload)
                response.raise_for_status()
                log_entry["result"] = "simulation_success"
                log_entry["status_code"] = response.status_code
                self._log.append(log_entry)
                logger.info(
                    "Simulation scaling succeeded for deployment %s: target=%d",
                    decision.deployment_id,
                    decision.target_pod_count,
                )
                return True
            except httpx.HTTPStatusError as exc:
                log_entry["result"] = "simulation_failure"
                log_entry["error"] = f"HTTP {exc.response.status_code}: {exc.response.text}"
                self._log.append(log_entry)
                logger.error(
                    "Simulation scaling failed for deployment %s: HTTP %s",
                    decision.deployment_id,
                    exc.response.status_code,
                )
                return False
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                log_entry["result"] = "simulation_failure"
                log_entry["error"] = str(exc)
                self._log.append(log_entry)
                logger.error(
                    "Simulation scaling failed for deployment %s: %s",
                    decision.deployment_id,
                    exc,
                )
                return False

        # MODE_REAL_K8S — not yet implemented
        log_entry["result"] = "mode_not_implemented"
        self._log.append(log_entry)
        logger.warning(
            "Real Kubernetes mode is not yet implemented. Deployment %s not scaled.",
            decision.deployment_id,
        )
        return False

    async def rollback(self, decision: ScalingDecision) -> bool:
        """Rollback a previously executed scaling decision.

        Reverts the scaling action by restoring previous pod count.

        Args:
            decision: Scaling decision to rollback.

        Returns:
            bool: True if rollback succeeded, False otherwise.
        """
        log_entry = {
            "decision_id": decision.decision_id,
            "deployment_id": decision.deployment_id,
            "action": "rollback",
            "target_replicas": decision.current_pod_count,
            "current_replicas": decision.target_pod_count,
            "mode": self.mode,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if self.mode == self.MODE_DRY_RUN:
            log_entry["result"] = "dry_run_success"
            self._log.append(log_entry)
            logger.info(
                "Dry-run rollback for deployment %s: restoring to %d",
                decision.deployment_id,
                decision.current_pod_count,
            )
            return True

        if self.mode == self.MODE_SIMULATION:
            url = f"{self.sim_base_url}/sim/scale"
            payload = {
                "deployment_id": decision.deployment_id,
                "target_replicas": decision.current_pod_count,
                "execution_source": decision.execution_source,
            }
            try:
                response = await self._http.post(url, json=payload)
                response.raise_for_status()
                log_entry["result"] = "simulation_success"
                log_entry["status_code"] = response.status_code
                self._log.append(log_entry)
                logger.info(
                    "Simulation rollback succeeded for deployment %s: restored to %d",
                    decision.deployment_id,
                    decision.current_pod_count,
                )
                return True
            except httpx.HTTPStatusError as exc:
                log_entry["result"] = "simulation_failure"
                log_entry["error"] = f"HTTP {exc.response.status_code}: {exc.response.text}"
                self._log.append(log_entry)
                logger.error(
                    "Simulation rollback failed for deployment %s: HTTP %s",
                    decision.deployment_id,
                    exc.response.status_code,
                )
                return False
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                log_entry["result"] = "simulation_failure"
                log_entry["error"] = str(exc)
                self._log.append(log_entry)
                logger.error(
                    "Simulation rollback failed for deployment %s: %s",
                    decision.deployment_id,
                    exc,
                )
                return False

        # MODE_REAL_K8S — not yet implemented
        log_entry["result"] = "mode_not_implemented"
        self._log.append(log_entry)
        logger.warning(
            "Real Kubernetes mode is not yet implemented. Deployment %s rollback skipped.",
            decision.deployment_id,
        )
        return False

    def get_execution_log(
        self,
        deployment_id: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Get execution history.

        Args:
            deployment_id: Optional deployment ID to filter by.
            limit: Maximum number of log entries to return.

        Returns:
            list[dict]: Execution log entries ordered by time (most recent last).
        """
        filtered = self._log
        if deployment_id is not None:
            filtered = [entry for entry in self._log if entry.get("deployment_id") == deployment_id]
        return filtered[-limit:]


class ReactiveFallback:
    """Reactive scaling fallback for when predictions are unavailable.

    Provides simple threshold-based scaling when predictive models
    are unavailable or forecast confidence is too low.

    Attributes:
        cpu_threshold_pct: CPU utilization threshold for scaling trigger.
    """

    def __init__(self, cpu_threshold_pct: float = 70.0) -> None:
        """Initialize ReactiveFallback.

        Args:
            cpu_threshold_pct: CPU utilization percentage to trigger scaling.

        Raises:
            ValueError: If threshold is not in [0, 100] range.
        """
        if not 0.0 <= cpu_threshold_pct <= 100.0:
            raise ValueError(
                f"cpu_threshold_pct must be between 0 and 100, got {cpu_threshold_pct}"
            )
        self.cpu_threshold_pct = cpu_threshold_pct

    def evaluate(
        self,
        current_metrics: MetricsSnapshot,
        current_pods: int,
        config: Optional[ScalingConfig] = None,
    ) -> Optional[ScalingDecision]:
        """Evaluate whether reactive scaling is needed.

        Args:
            current_metrics: Current system metrics.
            current_pods: Current pod count.
            config: Optional scaling config overrides.

        Returns:
            Optional[ScalingDecision]: Scaling decision if needed, None otherwise.
        """
        threshold = (
            config.upscale_cpu_threshold_pct if config else self.cpu_threshold_pct
        )
        min_pods = config.min_replicas if config else 1
        max_pods = config.max_replicas if config else 100
        cpu = current_metrics.cpu_utilization_pct

        # Scale-up: CPU exceeds threshold
        if cpu > threshold:
            scale_ratio = cpu / threshold
            target = math.ceil(current_pods * scale_ratio)
            target = max(min_pods, min(target, max_pods))
            return ScalingDecision(
                decision_id=str(uuid.uuid4()),
                deployment_id=current_metrics.deployment_id,
                simulated_time_utc=datetime.now(timezone.utc).isoformat(),
                current_pod_count=current_pods,
                target_pod_count=target,
                action=ScalingAction.SCALE_UP,
                forecast_id=None,
                forecast_yhat=0.0,
                forecast_lower=0.0,
                forecast_upper=0.0,
                risk_score=0.5,
                confidence_score=0.0,
                risk_level="medium",
                formula_raw_target=float(target),
                formula_confidence_factor=1.0,
                formula_risk_bias=0.0,
                formula_final_before_clamp=float(target),
                executed=False,
                execution_source="reactive_fallback",
                reason=f"Reactive fallback: CPU {cpu:.1f}% exceeds threshold {threshold:.1f}%",
            )

        # Scale-down: CPU is below threshold with hysteresis band
        if cpu < threshold - 10.0:
            target = max(min_pods, math.floor(current_pods * 0.7))
            target = max(min_pods, min(target, max_pods))
            return ScalingDecision(
                decision_id=str(uuid.uuid4()),
                deployment_id=current_metrics.deployment_id,
                simulated_time_utc=datetime.now(timezone.utc).isoformat(),
                current_pod_count=current_pods,
                target_pod_count=target,
                action=ScalingAction.SCALE_DOWN,
                forecast_id=None,
                forecast_yhat=0.0,
                forecast_lower=0.0,
                forecast_upper=0.0,
                risk_score=0.2,
                confidence_score=0.0,
                risk_level="low",
                formula_raw_target=float(target),
                formula_confidence_factor=1.0,
                formula_risk_bias=0.0,
                formula_final_before_clamp=float(target),
                executed=False,
                execution_source="reactive_fallback",
                reason=f"Reactive fallback: CPU {cpu:.1f}% below hysteresis band {threshold - 10.0:.1f}%",
            )

        # Within hysteresis band — no action needed
        return None
