"""Tests for the SimulationEngine class."""

import pytest


class TestSimulationEngine:
    """Test suite for SimulationEngine lifecycle and tick behavior.

    TODO:
        - Set up mock DatabaseManager and MetricsGenerator fixtures
        - Create default SimulationConfig fixture
    """

    async def test_start_pause_resume(self) -> None:
        """Test that start/pause/resume transitions work correctly.

        TODO:
            - Verify status transitions: STOPPED -> RUNNING -> PAUSED -> RUNNING
            - Verify start() raises if already running
            - Verify pause() raises if not running
            - Verify resume() raises if not paused
        """
        ...

    async def test_tick_produces_metrics(self) -> None:
        """Test that tick() produces valid MetricSample list.

        TODO:
            - Verify tick returns list of MetricSample
            - Verify one sample per deployment
            - Verify simulated_time advances
            - Verify metrics are persisted to DB
        """
        ...

    async def test_stop_cleans_up(self) -> None:
        """Test that stop() properly cleans up resources.

        TODO:
            - Verify status changes to STOPPED
            - Verify pending metrics are flushed
            - Verify cluster state is reset
            - Verify tick loop is cancelled
        """
        ...
