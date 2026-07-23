"""AnomalyEngine — manages anomaly lifecycle and effect computation.

Integrates with SimulationEngine.tick() via process_tick() which
returns an AnomalyEffect the metrics generator reads each tick.
"""

from __future__ import annotations

from app.anomalies import AnomalyDefinition, TriggerType
from app.anomalies.base import AnomalyEffect, HANDLER_REGISTRY, merge_effects


class ActiveAnomaly:
    """An anomaly that has been triggered and is currently active."""

    __slots__ = ("definition", "started_at", "apply_fn", "revert_fn")

    def __init__(self, definition: AnomalyDefinition, started_at: float) -> None:
        self.definition = definition
        self.started_at = started_at
        tup = HANDLER_REGISTRY[definition.anomaly_type]
        self.apply_fn = tup[0]
        self.revert_fn = tup[1]


class AnomalyEngine:
    """Manages anomaly definitions, activation, application, and expiry.

    One instance lives alongside SimulationEngine in deps."""

    def __init__(self) -> None:
        self.definitions: dict[str, AnomalyDefinition] = {}
        self.active: dict[str, ActiveAnomaly] = {}

    # ── Management ───────────────────────────────────────────────

    def add_definition(self, defn: AnomalyDefinition) -> None:
        """Register an anomaly definition."""
        self.definitions[defn.anomaly_id] = defn

    def remove_definition(self, anomaly_id: str) -> bool:
        """Remove a definition. Active instance stays until expiry."""
        return self.definitions.pop(anomaly_id, None) is not None

    def get_definitions(self) -> list[AnomalyDefinition]:
        """Return all registered definitions."""
        return list(self.definitions.values())

    def get_active(self) -> list[dict]:
        """Return active anomaly info for the status endpoint."""
        return [
            {
                "anomaly_id": a.definition.anomaly_id,
                "anomaly_type": a.definition.anomaly_type.value,
                "target": a.definition.target,
                "started_at_minute": a.started_at,
            }
            for a in self.active.values()
        ]

    # ── Tick processing ─────────────────────────────────────────

    def process_tick(
        self,
        simulated_minutes: float,
        cluster_state: object,
    ) -> AnomalyEffect | None:
        """Process one tick of anomaly lifecycles.

        1. Activate newly triggered definitions.
        2. Apply all active anomalies.
        3. Expire anomalies whose duration has elapsed.

        Returns:
            Merged AnomalyEffect, or None if nothing active.
        """
        if not self.definitions and not self.active:
            return None

        # 1. Activate — check deferred in case definitions cleared mid-sim
        for defn in self.definitions.values():
            if defn.anomaly_id in self.active:
                continue
            if self._should_activate(defn, simulated_minutes):
                self.active[defn.anomaly_id] = ActiveAnomaly(defn, simulated_minutes)

        if not self.active:
            return None

        # 2. Apply + expiry
        effects: list[AnomalyEffect] = []
        for anomaly_id, active in list(self.active.items()):
            defn = active.definition
            duration = defn.duration_minutes
            if duration is not None:
                elapsed = simulated_minutes - active.started_at
                if elapsed >= duration:
                    self._deactivate(anomaly_id, cluster_state)
                    continue

            effect = active.apply_fn(cluster_state, defn, defn.severity)
            effects.append(effect)

        if not effects:
            return None

        merged = merge_effects(effects)
        if merged.is_empty:
            return None
        return merged

    # ── Private helpers ─────────────────────────────────────────

    @staticmethod
    def _should_activate(defn: AnomalyDefinition, now: float) -> bool:
        if defn.trigger_type == TriggerType.SCHEDULED:
            return now >= (defn.trigger_value or float("inf"))
        return False

    def _deactivate(self, anomaly_id: str, cluster_state: object) -> None:
        active = self.active.pop(anomaly_id, None)
        if active is not None and active.revert_fn is not None:
            try:
                active.revert_fn(cluster_state, active.definition)
            except Exception:
                pass  # best-effort revert
