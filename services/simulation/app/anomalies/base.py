"""Anomaly handler registry and AnomalyEffect data class.

Every anomaly handler is registered in HANDLER_REGISTRY as a tuple
(apply_fn, revert_fn_or_None).  The apply function receives:

    apply(cluster_state, definition, severity) -> AnomalyEffect

The optional revert function receives:

    revert(cluster_state, definition)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from app.anomalies import AnomalyType

# Each entry: (apply_fn, revert_fn_or_None)
#   apply(cluster_state, definition, severity) -> AnomalyEffect
#   revert(cluster_state, definition) -> None
HandlerTuple = tuple[Callable[..., Any], Callable[..., Any] | None]

HANDLER_REGISTRY: dict[AnomalyType, HandlerTuple] = {}


# ── Effect data class ──────────────────────────────────────────

@dataclass
class AnomalyEffect:
    """Aggregated effect of all active anomalies for a single tick.

    MetricsGenerator reads this to modify metric computation per
    deployment without touching cluster state.
    """

    # Entities that are "dead" this tick
    blocked_nodes: set[str] = field(default_factory=set)
    blocked_gpus: set[str] = field(default_factory=set)
    blocked_deployments: set[str] = field(default_factory=set)
    blocked_pods: set[str] = field(default_factory=set)

    # Per-deployment metric modifiers
    rps_multiplier: dict[str, float] = field(default_factory=dict)
    rps_absolute: dict[str, float | None] = field(default_factory=dict)
    cpu_offset_pp: dict[str, float] = field(default_factory=dict)
    latency_multiplier: dict[str, float] = field(default_factory=dict)
    memory_multiplier: dict[str, float] = field(default_factory=dict)
    force_gpu_off: set[str] = field(default_factory=set)

    # If True, randomize some additional variance
    jitter: float = 0.0

    # Latency anomaly: baseline latency in ms (None = no change)
    latency_ms_absolute: float | None = None

    @property
    def is_empty(self) -> bool:
        """True if no modifiers are set (no work for metrics generator)."""
        return (
            not self.blocked_nodes
            and not self.blocked_gpus
            and not self.blocked_deployments
            and not self.blocked_pods
            and not self.rps_multiplier
            and not self.rps_absolute
            and not self.cpu_offset_pp
            and not self.latency_multiplier
            and not self.memory_multiplier
            and not self.force_gpu_off
            and self.jitter == 0.0
            and self.latency_ms_absolute is None
        )


def merge_effects(effects: list[AnomalyEffect]) -> AnomalyEffect:
    """Combine multiple anomaly effects into one aggregated effect."""
    merged = AnomalyEffect()
    for e in effects:
        merged.blocked_nodes |= e.blocked_nodes
        merged.blocked_gpus |= e.blocked_gpus
        merged.blocked_deployments |= e.blocked_deployments
        merged.blocked_pods |= e.blocked_pods
        for k, v in e.rps_multiplier.items():
            merged.rps_multiplier[k] = merged.rps_multiplier.get(k, 1.0) * v
        for k, v in e.rps_absolute.items():
            merged.rps_absolute[k] = v  # absolute overrides multiplier
        for k, v in e.cpu_offset_pp.items():
            merged.cpu_offset_pp[k] = merged.cpu_offset_pp.get(k, 0.0) + v
        for k, v in e.latency_multiplier.items():
            merged.latency_multiplier[k] = merged.latency_multiplier.get(k, 1.0) * v
        for k, v in e.memory_multiplier.items():
            merged.memory_multiplier[k] = merged.memory_multiplier.get(k, 1.0) * v
        merged.force_gpu_off |= e.force_gpu_off
        merged.jitter = max(merged.jitter, e.jitter)
        if e.latency_ms_absolute is not None:
            merged.latency_ms_absolute = e.latency_ms_absolute
    return merged


def register_handler(
    anomaly_type: AnomalyType,
    apply_fn: Callable[..., Any],
    revert_fn: Callable[..., Any] | None = None,
) -> None:
    """Register an anomaly handler in the global registry."""
    HANDLER_REGISTRY[anomaly_type] = (apply_fn, revert_fn)
