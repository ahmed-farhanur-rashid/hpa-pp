"""Scaling configuration — load, save, validate."""

from __future__ import annotations

from typing import Any

from shared.db.manager import DatabaseManager
from shared.decisions import ScalingConfig

DEFAULT_SCALING_CONFIG: dict[str, Any] = {
    "min_pods": 1,
    "max_pods": 10,
    "target_cpu_pct": 70.0,
    "scale_up_cooldown_seconds": 300,
    "scale_down_cooldown_seconds": 600,
    "stabilization_window_seconds": 300,
    "aggressive_scaling_enabled": False,
    "risk_threshold": 0.7,
    "confidence_threshold": 0.6,
    "gpu_assignment_strategy": "bin_pack",
}


def load_scaling_config(
    deployment_id: str,
    db: DatabaseManager,
) -> ScalingConfig:
    """Load scaling config for a deployment, merging with defaults.

    Args:
        deployment_id: Deployment to load config for.
        db: Database manager.

    Returns:
        ScalingConfig populated with per-deployment or default values.
    """
    row = db.get_scaling_config(deployment_id=deployment_id)
    if row:
        return ScalingConfig.model_validate(row)
    return ScalingConfig(
        deployment_id=deployment_id,
        min_replicas=DEFAULT_SCALING_CONFIG["min_pods"],
        max_replicas=DEFAULT_SCALING_CONFIG["max_pods"],
        target_cpu_utilization_pct=DEFAULT_SCALING_CONFIG["target_cpu_pct"],
        scale_up_cooldown_seconds=DEFAULT_SCALING_CONFIG["scale_up_cooldown_seconds"],
        scale_down_cooldown_seconds=DEFAULT_SCALING_CONFIG["scale_down_cooldown_seconds"],
        stabilization_window_seconds=DEFAULT_SCALING_CONFIG["stabilization_window_seconds"],
        risk_asymmetry_factor=3.0,
        baseline_per_pod=100.0,
    )


def save_scaling_config(
    config: ScalingConfig,
    db: DatabaseManager,
) -> None:
    """Persist a scaling config to the database.

    Args:
        config: Scaling config to save.
        db: Database manager.

    Raises:
        ValueError: If config validation fails.
    """
    errors = validate_scaling_config(config)
    if errors:
        raise ValueError("; ".join(errors))
    db.upsert_scaling_config(config)


def validate_scaling_config(config: ScalingConfig) -> list[str]:
    """Validate scaling config ranges. Returns error messages (empty = valid)."""
    errors: list[str] = []
    if config.min_replicas > config.max_replicas:
        errors.append("min_replicas exceeds max_replicas")
    if config.min_replicas < 0:
        errors.append("min_replicas must be >= 0")
    if not 0 <= config.target_cpu_utilization_pct <= 100:
        errors.append("target_cpu_utilization_pct must be 0-100")
    if config.scale_up_cooldown_seconds < 0:
        errors.append("scale_up_cooldown_seconds must be >= 0")
    if config.scale_down_cooldown_seconds < 0:
        errors.append("scale_down_cooldown_seconds must be >= 0")
    if config.stabilization_window_seconds < 0:
        errors.append("stabilization_window_seconds must be >= 0")
    if not 0 <= config.risk_asymmetry_factor <= 20:
        errors.append("risk_asymmetry_factor must be 0-20")
    if config.baseline_per_pod <= 0:
        errors.append("baseline_per_pod must be > 0")
    return errors
