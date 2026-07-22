"""Tests for FastAPI routes (app/routes.py).

Stubs only — TODO: implement test cases with httpx AsyncClient.
"""

import pytest


class TestHealthCheck:
    """Tests for GET /health."""

    def test_health_returns_ok(self) -> None:
        """Health endpoint should return 200 OK.

        TODO: use httpx.AsyncClient, verify status and response body.
        """
        ...


class TestGetLatestForecast:
    """Tests for GET /api/v1/forecast/latest."""

    def test_returns_forecast(self) -> None:
        """Should return ApiResponse with ForecastWindow.

        TODO: mock pipeline, verify response structure.
        """
        ...

    def test_returns_none_when_empty(self) -> None:
        """Should return ApiResponse with null data.

        TODO: mock pipeline to return None.
        """
        ...

    def test_missing_deployment_id(self) -> None:
        """Should return 422 when deployment_id is missing.

        TODO: omit query param, verify validation error.
        """
        ...


class TestGetForecastHistory:
    """Tests for GET /api/v1/forecast/history."""

    def test_returns_list(self) -> None:
        """Should return ApiResponse with list of ForecastWindows.

        TODO: mock pipeline, verify list structure.
        """
        ...

    def test_limit_validation(self) -> None:
        """Should reject limit > 1000.

        TODO: pass limit=1001, verify 422.
        """
        ...


class TestRunForecast:
    """Tests for POST /api/v1/forecast/run."""

    def test_triggers_forecast(self) -> None:
        """Should trigger a single forecast cycle.

        TODO: mock pipeline.run_once(), verify response.
        """
        ...

    def test_missing_body(self) -> None:
        """Should return 422 when deployment_id is missing from body.

        TODO: send empty body, verify validation error.
        """
        ...


class TestStartStopLoop:
    """Tests for POST /api/v1/forecast/start-loop and stop-loop."""

    def test_start_loop(self) -> None:
        """Should start the forecast loop and return status.

        TODO: mock pipeline.run_loop(), verify "started" status.
        """
        ...

    def test_stop_loop(self) -> None:
        """Should stop the forecast loop and return status.

        TODO: mock cancellation, verify "stopped" status.
        """
        ...


class TestModelEndpoints:
    """Tests for POST /api/v1/model/train and GET /api/v1/model/info."""

    def test_train_model(self) -> None:
        """Should trigger retrain and return ForecastMetadata.

        TODO: mock pipeline, verify metadata in response.
        """
        ...

    def test_model_info(self) -> None:
        """Should return model info dict.

        TODO: mock pipeline, verify dict keys.
        """
        ...
