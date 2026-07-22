"""Demo setup and management for the integration service.

Handles demo configuration loading, Locust load test orchestration,
and demo lifecycle management.
"""

from __future__ import annotations

from typing import Any


class DemoManager:
    """Manages demo configurations and load test execution.

    Coordinates with the PipelineOrchestrator to run preconfigured
    demo scenarios and Locust-based load profiles.

    Args:
        orchestrator: The PipelineOrchestrator instance to control.
        db_manager: Database manager for persisting demo results.

    TODO: Add support for custom user-defined demo profiles.
    TODO: Implement demo result export (JSON, CSV).
    """

    def __init__(self, orchestrator: Any, db_manager: Any) -> None:
        ...

    async def load_demo_config(self, profile_name: str) -> dict[str, Any]:
        """Load a named demo configuration profile.

        Args:
            profile_name: Name of the profile to load from
                demo/profiles.py DEMO_PROFILES constant.

        Returns:
            dict: The loaded profile configuration.

        Raises:
            ValueError: If the profile name is not found.
            FileNotFoundError: If the profiles module is missing.

        TODO: Validate profile schema against expected fields.
        """
        ...

    async def start_load_test(
        self, profile: dict[str, Any], duration_s: int
    ) -> dict[str, Any]:
        """Start a Locust-based load testing session.

        Args:
            profile: Load test profile with user count, spawn rate,
                and target endpoints.
            duration_s: Duration of the load test in seconds.

        Returns:
            dict: Load test ID and initial status.

        Raises:
            RuntimeError: If a load test is already running.
            ValueError: If the profile is invalid.

        TODO: Stream Locust stats to database for real-time dashboard.
        """
        ...

    async def stop_load_test(self) -> dict[str, Any]:
        """Stop the currently running load test.

        Returns:
            dict: Final load test results (RPS, failures, p99 latency).

        Raises:
            RuntimeError: If no load test is running.

        TODO: Generate summary report after stop.
        """
        ...

    def get_load_test_status(self) -> dict[str, Any]:
        """Get the current status of the active load test.

        Returns:
            dict: Status including is_running, active_users,
                requests_per_second, failure_rate, and elapsed_time.

        TODO: Include per-endpoint breakdown.
        """
        ...
