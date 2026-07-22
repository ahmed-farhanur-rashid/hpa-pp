"""Tests for the Simulation Service API routes."""

import pytest


class TestSimulationRoutes:
    """Test suite for FastAPI API endpoints.

    TODO:
        - Set up httpx AsyncClient with TestClient fixture
        - Mock SimulationEngine and DatabaseManager dependencies
    """

    async def test_get_metrics(self) -> None:
        """Test GET /api/v1/metrics returns metric samples.

        TODO:
            - Seed DB with metric samples
            - Verify response is ApiResponse with list of MetricSample
            - Verify filtering by deployment_id works
            - Verify from_time/to_time filtering works
            - Verify limit parameter is respected
        """
        ...

    async def test_start_simulation(self) -> None:
        """Test POST /api/v1/sim/start starts the simulation.

        TODO:
            - Verify returns ApiResponse with SimulatorStatusResponse
            - Verify status transitions to RUNNING
            - Verify start without config uses defaults
            - Verify start with config override applies it
            - Verify starting when already running returns 400
        """
        ...

    async def test_sim_status(self) -> None:
        """Test GET /api/v1/sim/status returns current status.

        TODO:
            - Verify returns ApiResponse with SimulatorStatusResponse
            - Verify status field is valid SimulatorStatus enum
            - Verify tick_count and uptime are non-negative
            - Verify sim_name matches config
        """
        ...
