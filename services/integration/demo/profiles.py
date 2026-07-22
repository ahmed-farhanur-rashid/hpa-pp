"""Demo profile configurations for the integration service.

Standalone pure functions providing named workload profiles and
benchmark configurations for demos and testing.
"""

from __future__ import annotations

from typing import Any


# ── Named demo profiles ─────────────────────────────────────────────

DEMO_PROFILES: dict[str, dict[str, Any]] = {
    "light": {
        "description": "Light workload with minimal GPU demand",
        "tick_interval": 5.0,
        "initial_users": 10,
        "spawn_rate": 2,
    },
    "standard": {
        "description": "Standard workload simulating typical production",
        "tick_interval": 2.0,
        "initial_users": 100,
        "spawn_rate": 10,
    },
    "heavy": {
        "description": "Heavy workload testing scaling limits",
        "tick_interval": 1.0,
        "initial_users": 500,
        "spawn_rate": 50,
    },
    "spike": {
        "description": "Sudden traffic spike to test reactive scaling",
        "tick_interval": 0.5,
        "initial_users": 1000,
        "spawn_rate": 200,
    },
}


def get_default_profiles() -> dict[str, dict[str, Any]]:
    """Return all default demo profiles.

    Returns:
        dict: Mapping of profile names to their configuration dicts.
            Each profile includes description, tick_interval,
            initial_users, and spawn_rate.

    TODO: Load additional profiles from YAML config files.
    TODO: Validate all profiles have required fields.
    """
    ...


def get_benchmark_configs() -> list[dict[str, Any]]:
    """Return a list of benchmark configurations.

    Each config defines a complete benchmark scenario with workload
    parameters, duration, and comparison targets.

    Returns:
        list[dict]: List of benchmark config dicts with keys:
            name, profile, duration_s, comparison_mode.

    TODO: Generate configs dynamically based on available services.
    TODO: Include edge-case scenarios (low memory, high churn).
    """
    ...
