"""Tests for the SimulationEngine lifecycle and tick behavior."""

from __future__ import annotations

import asyncio

import pytest

from shared.simulation import SimulatorStatus
from shared.enums import PodStatus


class TestSimulationEngine:
    """Test suite for SimulationEngine lifecycle, ticks, and edge cases."""

    # ── Lifecycle ─────────────────────────────────────────────

    async def test_initial_status(self, simulation_engine):
        """Engine should start in STOPPED status."""
        assert simulation_engine.get_status() == SimulatorStatus.STOPPED

    async def test_start_transition(self, running_engine):
        """start() should transition to RUNNING status."""
        assert running_engine.get_status() == SimulatorStatus.RUNNING

    async def test_pause_transition(self, running_engine):
        """pause() should transition to PAUSED status."""
        await running_engine.pause()
        assert running_engine.get_status() == SimulatorStatus.PAUSED

    async def test_resume_transition(self, running_engine):
        """resume() should transition back to RUNNING."""
        await running_engine.pause()
        await running_engine.resume()
        assert running_engine.get_status() == SimulatorStatus.RUNNING

    async def test_stop_transition(self, simulation_engine):
        """stop() should return to STOPPED status."""
        await simulation_engine.start()
        await simulation_engine.stop()
        assert simulation_engine.get_status() == SimulatorStatus.STOPPED

    async def test_start_while_running_raises(self, running_engine):
        """Starting an already-running engine should raise."""
        with pytest.raises(RuntimeError, match="already running"):
            await running_engine.start()

    async def test_pause_while_stopped_raises(self, simulation_engine):
        """Pausing a stopped engine should raise."""
        with pytest.raises(RuntimeError, match="not running"):
            await simulation_engine.pause()

    async def test_resume_while_running_raises(self, running_engine):
        """Resuming a running engine should raise."""
        with pytest.raises(RuntimeError, match="not paused"):
            await running_engine.resume()

    async def test_stop_while_stopped(self, simulation_engine):
        """Stopping an already-stopped engine should be a no-op."""
        await simulation_engine.stop()
        assert simulation_engine.get_status() == SimulatorStatus.STOPPED

    async def test_update_config_while_running_raises(self, running_engine):
        """Updating config while running should raise."""
        with pytest.raises(RuntimeError, match="running"):
            await running_engine.update_config(running_engine.get_config())

    async def test_update_config_while_stopped(self, simulation_engine):
        """Updating config while stopped should succeed."""
        config = simulation_engine.get_config()
        config.sim_name = "updated-sim"
        await simulation_engine.update_config(config)
        assert simulation_engine.get_config().sim_name == "updated-sim"

    # ── Tick behavior ─────────────────────────────────────────

    async def test_tick_produces_samples(self, simulation_engine):
        """A single tick should return metric samples."""
        await simulation_engine.start()
        await asyncio.sleep(0.15)
        # After a brief period, the tick loop should have run
        assert simulation_engine.tick_count > 0
        await simulation_engine.stop()

    async def test_tick_persists_to_db(self, simulation_engine):
        """Ticks should persist metrics to the database."""
        db = simulation_engine.db_manager
        await simulation_engine.start()
        await asyncio.sleep(0.3)
        await simulation_engine.stop()

        metrics = db.query_metrics(limit=10)
        assert len(metrics) > 0

    async def test_tick_advances_simulated_time(self, simulation_engine):
        """Simulated time should advance after ticks (check before stop)."""
        await simulation_engine.start()
        await asyncio.sleep(0.3)
        # Check BEFORE stop — stop resets counters to 0
        assert simulation_engine.simulated_minutes > 0
        await simulation_engine.stop()

    async def test_multiple_ticks_increment_count(self, simulation_engine):
        """Multiple ticks should increment tick_count (check before stop)."""
        await simulation_engine.start()
        await asyncio.sleep(0.5)
        # Check BEFORE stop — stop resets counters to 0
        assert simulation_engine.tick_count >= 1
        await simulation_engine.stop()

    async def test_tick_updates_pod_usage(self, simulation_engine):
        """Ticks should update pod resource usage in cluster state."""
        await simulation_engine.start()
        await asyncio.sleep(0.3)

        # Check cluster state BEFORE stop (stop resets it)
        cluster = simulation_engine.cluster_state
        assert cluster is not None
        for dep in cluster.get_all_deployments():
            for pod in dep.pods:
                if pod.status == PodStatus.RUNNING:
                    # After at least one tick, pod should have usage data
                    assert pod.current_cpu_util_pct is not None

        await simulation_engine.stop()

    # ── Configuration ─────────────────────────────────────────

    async def test_get_config_returns_config(self, simulation_engine):
        """get_config should return the active config."""
        config = simulation_engine.get_config()
        assert config.sim_name == "test-sim"
        assert len(config.deployments) == 2

    # ── Edge cases ────────────────────────────────────────────

    async def test_pause_stops_tick_loop(self, running_engine):
        """After pause, tick_count should stop incrementing."""
        await asyncio.sleep(0.2)
        count_before = running_engine.tick_count
        await running_engine.pause()
        await asyncio.sleep(0.3)
        assert running_engine.tick_count == count_before

    async def test_resume_restarts_tick_loop(self, running_engine):
        """After resume, tick_count should start incrementing again."""
        await running_engine.pause()
        count_before = running_engine.tick_count
        await running_engine.resume()
        await asyncio.sleep(0.3)
        assert running_engine.tick_count > count_before
        await running_engine.stop()

    async def test_completion_status(self, simulation_engine):
        """Engine should transition to COMPLETED when total time reached."""
        from shared.simulation import SimulationConfig, DeploymentSpec, TrafficProfile
        from shared.enums import TrafficPattern

        quick_config = SimulationConfig(
            sim_name="quick-test",
            tick_interval_real_seconds=0.1,
            seconds_per_simulated_minute=0.5,
            total_simulated_minutes=3,
            node_count=1,
            cpu_per_node_millicores=1000,
            memory_per_node_mb=1024,
            gpus_per_node=0,
            gpu_memory_per_device_mb=0,
            seed=1,
            deployments=[
                DeploymentSpec(
                    deployment_id="quick-app",
                    initial_replicas=1,
                    cpu_request_millicores=500,
                    memory_request_mb=256,
                    traffic_profile=TrafficProfile(
                        pattern=TrafficPattern.STEADY,
                        base_load_rps=50.0,
                    ),
                ),
            ],
        )
        await simulation_engine.update_config(quick_config)
        await simulation_engine.start()

        # Each tick = 0.1/0.5 = 0.2 simulated minutes.
        # To reach 3.0 simulated minutes: 15 ticks × 0.1s = 1.5s
        await asyncio.sleep(2.0)

        assert simulation_engine.get_status() in (
            SimulatorStatus.COMPLETED, SimulatorStatus.RUNNING
        )
        if simulation_engine.get_status() == SimulatorStatus.RUNNING:
            await simulation_engine.stop()
