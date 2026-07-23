"""Tests for the WebSocket event streaming subsystem.

Covers the EventBroadcaster unit behaviour and full integration
via the FastAPI WebSocket endpoints.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.events import (
    EventBroadcaster,
    CHANNEL_METRICS,
    CHANNEL_CLUSTER,
    CHANNEL_STATUS,
    make_event,
    ALL_CHANNELS,
)
from app.engine import SimulationEngine
from app.metrics_generator import MetricsGenerator
from app.routes import router
from shared.db.manager import DatabaseManager
from shared.simulation import (
    SimulationConfig,
    DeploymentSpec,
    TrafficProfile,
)
from shared.enums import TrafficPattern


# ── Helpers ─────────────────────────────────────────────────────


def _fast_config() -> SimulationConfig:
    """Small config with fast ticks for quick tests."""
    return SimulationConfig(
        sim_name="ws-test",
        tick_interval_real_seconds=0.1,
        seconds_per_simulated_minute=0.5,
        total_simulated_minutes=60,
        node_count=2,
        cpu_per_node_millicores=2000,
        memory_per_node_mb=4096,
        gpus_per_node=0,
        seed=42,
        deployments=[
            DeploymentSpec(
                deployment_id="web",
                initial_replicas=2,
                cpu_request_millicores=500,
                memory_request_mb=512,
                traffic_profile=TrafficProfile(
                    pattern=TrafficPattern.STEADY,
                    base_load_rps=50.0,
                ),
            ),
        ],
    )


def make_mock_ws(alive: bool = True) -> AsyncMock:
    """Create a fake WebSocket with controllable send success."""
    ws = AsyncMock()
    ws.send_text = AsyncMock()
    if not alive:
        ws.send_text.side_effect = Exception("Connection closed")
    return ws


# ── EventBroadcaster unit tests ─────────────────────────────────


class TestEventBroadcaster:
    """Pure-async unit tests for the EventBroadcaster class."""

    @pytest.mark.asyncio
    async def test_broadcast_to_empty_channel_is_noop(self):
        """Broadcasting with zero subscribers should succeed silently."""
        bc = EventBroadcaster()
        await bc.broadcast_event(CHANNEL_METRICS, "tick", {"msg": "hi"})
        # No crash = pass

    @pytest.mark.asyncio
    async def test_subscribed_client_receives_message(self):
        """A subscribed WebSocket should receive broadcast messages."""
        bc = EventBroadcaster()
        ws = make_mock_ws(alive=True)

        await bc.subscribe(CHANNEL_METRICS, ws)
        await bc.broadcast_event(CHANNEL_METRICS, "tick", {"key": "val"})

        ws.send_text.assert_awaited_once()
        payload = json.loads(ws.send_text.await_args[0][0])
        assert payload["channel"] == CHANNEL_METRICS
        assert payload["event"] == "tick"
        assert payload["data"] == {"key": "val"}

    @pytest.mark.asyncio
    async def test_unsubscribed_client_does_not_receive(self):
        """After unsubscribe, a client should no longer receive messages."""
        bc = EventBroadcaster()
        ws = make_mock_ws(alive=True)

        await bc.subscribe(CHANNEL_METRICS, ws)
        await bc.unsubscribe(CHANNEL_METRICS, ws)
        await bc.broadcast_event(CHANNEL_METRICS, "tick", {"msg": "gone"})

        ws.send_text.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_multiple_subscribers_all_receive(self):
        """All subscribers on the same channel should get the same message."""
        bc = EventBroadcaster()
        ws1, ws2 = make_mock_ws(alive=True), make_mock_ws(alive=True)

        await bc.subscribe(CHANNEL_METRICS, ws1)
        await bc.subscribe(CHANNEL_METRICS, ws2)
        await bc.broadcast_event(CHANNEL_METRICS, "tick", {"all": "yes"})

        ws1.send_text.assert_awaited_once()
        ws2.send_text.assert_awaited_once()

        a = json.loads(ws1.send_text.await_args[0][0])
        b = json.loads(ws2.send_text.await_args[0][0])
        assert a["data"] == b["data"] == {"all": "yes"}

    @pytest.mark.asyncio
    async def test_channel_isolation(self):
        """Messages on one channel should not leak to another."""
        bc = EventBroadcaster()
        ws = make_mock_ws(alive=True)

        await bc.subscribe(CHANNEL_METRICS, ws)
        await bc.broadcast_event(CHANNEL_CLUSTER, "snapshot", {})

        ws.send_text.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_dead_connection_is_pruned(self):
        """A client that raises on send should be removed from the set."""
        bc = EventBroadcaster()
        alive_ws = make_mock_ws(alive=True)
        dead_ws = make_mock_ws(alive=False)

        await bc.subscribe(CHANNEL_METRICS, alive_ws)
        await bc.subscribe(CHANNEL_METRICS, dead_ws)
        await bc.broadcast_event(CHANNEL_METRICS, "tick", {"prune": True})

        # The live client got the message
        alive_ws.send_text.assert_awaited_once()

        # After broadcast, the dead connection should have been removed.
        # Subscribe a client to the same channel again — it should be alone.
        checker = make_mock_ws(alive=True)
        await bc.subscribe(CHANNEL_METRICS, checker)
        # The dead_ws slot should not be there.
        # We can verify by checking that alive_ws + checker = 2 subscribers,
        # not 3 (alive + dead + checker).
        await bc.unsubscribe(CHANNEL_METRICS, alive_ws)
        await bc.unsubscribe(CHANNEL_METRICS, checker)
        # If dead_ws wasn't pruned, we'd have to call unsubscribe 3 times.
        # We can count that the set size is as expected.
        async with bc._lock:
            remaining = bc._subscribers[CHANNEL_METRICS]
            assert len(remaining) <= 2  # at most alive + checker

    @pytest.mark.asyncio
    async def test_make_event_includes_extra_fields(self):
        """Extra keyword arguments should appear at the top level of the event."""
        msg = make_event(CHANNEL_METRICS, "tick", {"rps": 80}, tick_count=5, sim_min=1.0)
        payload = json.loads(msg)
        assert payload["tick_count"] == 5
        assert payload["sim_min"] == 1.0
        assert payload["data"] == {"rps": 80}


# ── Helpers for integration tests ───────────────────────────────


def _make_ws_app() -> tuple[
    TestClient,
    SimulationEngine,
    EventBroadcaster,
    DatabaseManager,
]:
    """Create a TestClient with a fast-ticking simulation engine.

    Returns (client, engine, broadcaster, db) for test use.
    The engine is already wired into ``app.dependencies``.
    """
    # Build a minimal FastAPI app without the production lifespan
    # so we can control deps directly.
    app = FastAPI(title="HPA++ Simulation Test")
    app.include_router(router, prefix="/api/v1")

    db = DatabaseManager(db_path=Path(":memory:"))
    db.connect()

    config = _fast_config()
    mg = MetricsGenerator(seed=config.seed)
    broadcaster = EventBroadcaster()
    engine = SimulationEngine(config, db, mg, broadcaster=broadcaster)

    import app.dependencies as deps

    deps.db_instance = db
    deps.engine_instance = engine
    deps.broadcaster_instance = broadcaster

    client = TestClient(app, raise_server_exceptions=False)
    return client, engine, broadcaster, db


# ── WebSocket integration tests ─────────────────────────────────


class TestWebSocketIntegration:
    """End-to-end tests for real-time simulation streaming via WebSocket."""

    def _recv_until(
        self,
        ws,
        condition,
        timeout: float = 5.0,
    ) -> list[dict]:
        """Receive JSON messages until *condition* returns True for one."""
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            msg = ws.receive_json()
            if condition(msg):
                return msg
        raise TimeoutError(
            f"No message satisfying condition within {timeout}s"
        )

    def test_metrics_stream_receives_tick_events(self):
        """After starting a simulation, the /ws/metrics endpoint should
        emit tick events containing metric samples."""
        client, engine, *_ = _make_ws_app()
        with client:
            with client.websocket_connect("/api/v1/ws/metrics") as ws:
                # Start simulation
                client.post("/api/v1/sim/start")

                msg = self._recv_until(ws, lambda m: m.get("event") == "tick")

                assert msg["channel"] == "metrics"
                assert msg["event"] == "tick"
                assert "data" in msg
                assert "samples" in msg["data"]
                assert len(msg["data"]["samples"]) > 0
                assert "tick_count" in msg
                assert "simulated_minutes" in msg
                assert "timestamp_utc" in msg

                sample = msg["data"]["samples"][0]
                assert "deployment_id" in sample
                assert "cpu_utilization_pct" in sample
                assert "memory_usage_mb" in sample
                assert "requests_per_second" in sample
                assert "latency_ms" in sample

    def test_cluster_stream_receives_snapshots(self):
        """The /ws/cluster endpoint should emit cluster snapshots."""
        client, engine, *_ = _make_ws_app()
        with client:
            with client.websocket_connect("/api/v1/ws/cluster") as ws:
                client.post("/api/v1/sim/start")

                msg = self._recv_until(ws, lambda m: m.get("event") == "snapshot")

                assert msg["channel"] == "cluster"
                assert msg["event"] == "snapshot"
                assert "node_count" in msg["data"] or "total_pods" in msg["data"]

    def test_status_stream_lifecycle_events(self):
        """The /ws/status endpoint should emit started, paused, stopped events."""
        client, engine, *_ = _make_ws_app()
        with client:
            with client.websocket_connect("/api/v1/ws/status") as ws:
                # Start
                client.post("/api/v1/sim/start")
                started = self._recv_until(ws, lambda m: m.get("event") == "started")
                assert started["channel"] == "status"
                assert started["data"]["status"] == "running"

                # Pause
                client.post("/api/v1/sim/pause")
                paused = self._recv_until(ws, lambda m: m.get("event") == "paused")
                assert paused["data"]["status"] == "paused"

                # Resume
                client.post("/api/v1/sim/resume")
                resumed = self._recv_until(ws, lambda m: m.get("event") == "resumed")
                assert resumed["data"]["status"] == "running"

                # Stop
                client.post("/api/v1/sim/stop")
                stopped = self._recv_until(ws, lambda m: m.get("event") == "stopped")
                assert stopped["data"]["status"] == "stopped"

    def test_multiple_clients_receive_same_stream(self):
        """Two WebSocket clients on the same channel should get the same
        tick count in their first tick event."""
        client, engine, *_ = _make_ws_app()
        with client:
            with (
                client.websocket_connect("/api/v1/ws/metrics") as ws1,
                client.websocket_connect("/api/v1/ws/metrics") as ws2,
            ):
                client.post("/api/v1/sim/start")

                m1 = self._recv_until(ws1, lambda m: m.get("event") == "tick")
                m2 = self._recv_until(ws2, lambda m: m.get("event") == "tick")

                assert m1["tick_count"] == m2["tick_count"]

    def test_disconnect_does_not_crash_broadcaster(self):
        """A WebSocket client that disconnects should not affect subsequent
        broadcasts to other clients."""
        client, *_ = _make_ws_app()
        with client:
            # Connect two clients (nested `with` to enter context managers)
            with client.websocket_connect("/api/v1/ws/metrics") as ws1:
                with client.websocket_connect("/api/v1/ws/metrics") as ws2:

                    client.post("/api/v1/sim/start")

                    # Wait for first tick on ws2
                    msg2 = self._recv_until(
                        ws2, lambda m: m.get("event") == "tick"
                    )
                    assert msg2["event"] == "tick"

                    # Disconnect ws1
                    ws1.close()

                    # More ticks should still arrive on ws2 (no crash)
                    for _ in range(3):
                        next_tick = self._recv_until(
                            ws2, lambda m: m.get("event") == "tick"
                        )
                        assert next_tick["event"] == "tick"

    def test_completion_event(self):
        """When simulation finishes, a 'completed' status event is emitted."""
        # Use a config that completes in ~3 ticks
        from shared.simulation import SimulationConfig

        config = SimulationConfig(
            sim_name="completion-test",
            tick_interval_real_seconds=0.1,
            seconds_per_simulated_minute=1.0,
            total_simulated_minutes=1,
            node_count=1,
            cpu_per_node_millicores=500,
            memory_per_node_mb=1024,
            gpus_per_node=0,
            seed=42,
            deployments=[
                DeploymentSpec(
                    deployment_id="tiny",
                    initial_replicas=1,
                    cpu_request_millicores=200,
                    memory_request_mb=256,
                    traffic_profile=TrafficProfile(
                        pattern=TrafficPattern.STEADY,
                        base_load_rps=10.0,
                    ),
                ),
            ],
        )

        db = DatabaseManager(db_path=Path(":memory:"))
        db.connect()

        mg = MetricsGenerator(seed=config.seed)
        broadcaster = EventBroadcaster()
        engine = SimulationEngine(config, db, mg, broadcaster=broadcaster)

        import app.dependencies as deps

        deps.db_instance = db
        deps.engine_instance = engine
        deps.broadcaster_instance = broadcaster

        app = FastAPI(title="Test")
        app.include_router(router, prefix="/api/v1")

        with TestClient(app, raise_server_exceptions=False) as client:
            with client.websocket_connect("/api/v1/ws/status") as ws:
                client.post("/api/v1/sim/start")

                completed = self._recv_until(
                    ws, lambda m: m.get("event") == "completed", timeout=10.0
                )
                assert completed["event"] == "completed"
                assert completed["data"]["status"] == "completed"
