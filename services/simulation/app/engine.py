"""Core simulation engine orchestrating the cluster simulation loop.

Manages the simulation lifecycle: start, pause, resume, stop, tick.
Coordinates between ClusterStateManager and MetricsGenerator.
"""

import asyncio
import time
from datetime import datetime, timezone

from shared.simulation import SimulationConfig, SimulatorStatus
from shared.metrics import MetricSample
from shared.enums import PodStatus
from shared.db.manager import DatabaseManager
from app.anomalies.base import AnomalyEffect
from app.anomalies.engine import AnomalyEngine
from app.cluster_state import ClusterStateManager
from app.events import EventBroadcaster, CHANNEL_METRICS, CHANNEL_CLUSTER, CHANNEL_STATUS
from app.metrics_generator import MetricsGenerator


def _to_iso(dt: datetime) -> str:
    """Convert a datetime to ISO 8601 string, handling timezone-aware/naive."""
    if dt.tzinfo is None:
        return dt.isoformat() + "Z"
    return dt.isoformat()


class SimulationEngine:
    """Orchestrates the cluster simulation lifecycle.

    Coordinates state management, metrics generation, and timing.
    Produces MetricSamples each tick and persists them via DatabaseManager.

    Attributes:
        config: Current simulation configuration.
        db_manager: Database manager for persisting metrics/snapshots.
        metrics_generator: Generator producing simulated metrics.

    TODO:
        - Add event bus for real-time updates to dashboard
        - Support multiple concurrent simulations
    """

    def __init__(
        self,
        config: SimulationConfig,
        db_manager: DatabaseManager,
        metrics_generator: MetricsGenerator,
        broadcaster: EventBroadcaster | None = None,
        anomaly_engine: AnomalyEngine | None = None,
    ) -> None:
        """Initialize the simulation engine.

        Args:
            config: Simulation configuration (cluster topology, timing, deployments).
            db_manager: Database manager for persisting metrics and snapshots.
            metrics_generator: Metrics generator for producing simulated data.
            broadcaster: Optional event broadcaster for real-time WebSocket streaming.
            anomaly_engine: Optional anomaly engine for failure injection.
        """
        self.config = config
        self.db_manager = db_manager
        self.metrics_generator = metrics_generator
        self.broadcaster = broadcaster
        self.anomaly_engine = anomaly_engine

        # ── Runtime state ──
        self.status: SimulatorStatus = SimulatorStatus.STOPPED
        self.cluster_state: ClusterStateManager | None = None
        self.tick_count: int = 0
        self.simulated_minutes: float = 0.0
        self._tick_task: asyncio.Task | None = None
        self._start_time: float = 0.0

    # ── Helpers ─────────────────────────────────────────────────

    def _fire(self, channel: str, event: str, data: object, **extra: object) -> None:
        """Fire-and-forget a broadcast event (non-blocking for tick loop).

        The broadcast runs as a background task so the tick loop is never
        delayed by a slow or disconnected WebSocket client.
        """
        if self.broadcaster is not None:
            asyncio.ensure_future(
                self.broadcaster.broadcast_event(channel, event, data, **extra),
            )

    # ── Lifecycle ──────────────────────────────────────────────

    async def start(self) -> None:
        """Start the simulation.

        Initializes cluster state, begins the tick loop, and starts
        persisting metrics to the database.

        Raises:
            RuntimeError: If simulation is already running.
        """
        if self.status == SimulatorStatus.RUNNING:
            raise RuntimeError("Simulation is already running")

        # Initialise cluster from config
        self.cluster_state = ClusterStateManager(self.config)
        self.cluster_state.initialize()

        # Wire deployment traffic profiles into the metrics generator
        profiles = {
            d.deployment_id: d.traffic_profile
            for d in self.config.deployments
        }
        self.metrics_generator.set_deployment_profiles(profiles)

        # Reset counters
        self.tick_count = 0
        self.simulated_minutes = 0.0
        self.status = SimulatorStatus.RUNNING
        self._start_time = time.monotonic()

        # Persist initial scaling configs
        for dep in self.config.deployments:
            if dep.scaling_config is not None:
                sc = dep.scaling_config
                self.db_manager.upsert_scaling_config({
                    "deployment_id": dep.deployment_id,
                    "min_replicas": sc.min_replicas,
                    "max_replicas": sc.max_replicas,
                    "baseline_per_pod": sc.baseline_per_pod,
                    "risk_asymmetry_factor": sc.risk_asymmetry_factor,
                    "cooldown_seconds": sc.cooldown_seconds,
                    "upscale_cpu_threshold_pct": getattr(sc, "upscale_cpu_threshold_pct", 70.0),
                })

        # Persist initial config record
        self.db_manager.insert("simulation_configs", {
            "timestamp_utc": _to_iso(datetime.now(timezone.utc)),
            "config_json": self.config.model_dump_json(),
            "active": 1,
        })

        # Notify subscribers
        self._fire("status", "started", {
            "status": self.status.value,
            "sim_name": self.config.sim_name,
        })

        # Start background tick loop
        self._tick_task = asyncio.create_task(self._tick_loop())

    async def pause(self) -> None:
        """Pause the simulation.

        Suspends the tick loop but preserves all state.
        Can be resumed later from the same point.

        Raises:
            RuntimeError: If simulation is not currently running.
        """
        if self.status != SimulatorStatus.RUNNING:
            raise RuntimeError("Simulation is not running")

        self.status = SimulatorStatus.PAUSED
        self._fire("status", "paused", {
            "status": self.status.value,
            "sim_name": self.config.sim_name,
        })
        if self._tick_task is not None:
            self._tick_task.cancel()
            try:
                await self._tick_task
            except asyncio.CancelledError:
                pass
            self._tick_task = None

    async def resume(self) -> None:
        """Resume a paused simulation.

        Restarts the tick loop from where it was paused.

        Raises:
            RuntimeError: If simulation is not currently paused.
        """
        if self.status != SimulatorStatus.PAUSED:
            raise RuntimeError("Simulation is not paused")

        self.status = SimulatorStatus.RUNNING
        self._fire("status", "resumed", {
            "status": self.status.value,
            "sim_name": self.config.sim_name,
        })
        self._tick_task = asyncio.create_task(self._tick_loop())

    async def stop(self) -> None:
        """Stop the simulation and clean up.

        Halts the tick loop, flushes remaining metrics, and resets state.
        """
        if self.status in (SimulatorStatus.STOPPED, SimulatorStatus.COMPLETED):
            return

        # Cancel tick task
        if self._tick_task is not None:
            self._tick_task.cancel()
            try:
                await self._tick_task
            except asyncio.CancelledError:
                pass
            self._tick_task = None

        # Notify subscribers
        self._fire("status", "stopped", {
            "status": SimulatorStatus.STOPPED.value,
            "sim_name": self.config.sim_name,
        })

        # Flush and reset
        self.db_manager.connection.commit()
        self.status = SimulatorStatus.STOPPED
        self.cluster_state = None
        self.tick_count = 0
        self.simulated_minutes = 0.0

    # ── Tick loop ──────────────────────────────────────────────

    async def _tick_loop(self) -> None:
        """Background asyncio task that ticks at the configured interval."""
        try:
            while self.status == SimulatorStatus.RUNNING:
                tick_start = time.monotonic()

                await self.tick()

                # Check if we've reached the total duration
                if self.simulated_minutes >= self.config.total_simulated_minutes:
                    self.status = SimulatorStatus.COMPLETED
                    self._fire("status", "completed", {
                        "status": SimulatorStatus.COMPLETED.value,
                        "sim_name": self.config.sim_name,
                        "total_ticks": self.tick_count,
                    })
                    break

                # Sleep for the remaining tick interval
                elapsed = time.monotonic() - tick_start
                sleep_time = self.config.tick_interval_real_seconds - elapsed
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

        except asyncio.CancelledError:
            # Normal cancellation during pause/stop — don't propagate
            pass
        except Exception:
            self.status = SimulatorStatus.ERROR
            raise

    async def tick(self) -> list[MetricSample]:
        """Execute one simulation tick.

        Advances the simulation clock, updates cluster state,
        generates metrics, and persists results.

        Returns:
            list[MetricSample]: Generated metric samples for this tick.
        """
        self.tick_count += 1

        # ── 1. Advance simulated time ──
        tick_minutes = (self.config.tick_interval_real_seconds
                        / self.config.seconds_per_simulated_minute)
        self.simulated_minutes += tick_minutes

        # ── 2. Get current cluster state ──
        cluster = self.cluster_state
        if cluster is None:
            return []

        deployments = cluster.get_all_deployments()
        snapshot = cluster.get_snapshot()

        # ── 3. Process active anomalies (may mutate cluster state) ──
        anomaly_effect: AnomalyEffect | None = None
        if self.anomaly_engine is not None and cluster is not None:
            anomaly_effect = self.anomaly_engine.process_tick(
                self.simulated_minutes, cluster,
            )

        # ── 4. Generate metrics from traffic profiles ├ anomalies ──
        samples = self.metrics_generator.generate_batch(
            deployments, snapshot, self.simulated_minutes,
            anomaly_effect=anomaly_effect,
        )

        # ── 5. Update pod resource usage from generated metrics ──
        for sample in samples:
            try:
                dep = cluster.get_deployment(sample.deployment_id)
            except KeyError:
                continue
            running_pods = [p for p in dep.pods if p.status == PodStatus.RUNNING]
            if not running_pods:
                continue

            n = len(running_pods)
            for pod in running_pods:
                cluster.update_pod_usage(
                    pod.pod_id,
                    cpu_pct=sample.cpu_utilization_pct / n,
                    memory_mb=sample.memory_usage_mb / n,
                    gpu_pct=(sample.gpu_utilization_pct / n
                              if sample.gpu_utilization_pct is not None
                              else None),
                )

        # ── 5. Persist metrics to DB ──
        now_iso = _to_iso(datetime.now(timezone.utc))
        metrics_rows = []
        for s in samples:
            metrics_rows.append({
                "timestamp_utc": now_iso,
                "simulated_time_utc": _to_iso(s.simulated_time_utc),
                "deployment_id": s.deployment_id,
                "cpu_utilization_pct": s.cpu_utilization_pct,
                "memory_usage_mb": s.memory_usage_mb,
                "requests_per_second": s.requests_per_second,
                "gpu_utilization_pct": s.gpu_utilization_pct,
                "gpu_memory_used_mb": s.gpu_memory_used_mb,
                "latency_ms": s.latency_ms,
                "pod_count": s.pod_count,
            })
        self.db_manager.insert_many("metric_samples", metrics_rows)

        # ── 6. Persist cluster snapshot periodically ──
        if self.tick_count % 10 == 0:
            snap = cluster.get_snapshot()
            self.db_manager.insert_cluster_snapshot({
                "timestamp_utc": now_iso,
                "snapshot_id": snap.snapshot_id,
                "simulated_time_utc": snap.simulated_time_utc,
                "snapshot_json": snap.model_dump_json(),
                "total_pods": snap.total_pods,
                "running_pods": snap.running_pods,
                "pending_pods": snap.pending_pods,
                "gpu_count": snap.gpu_count,
                "gpu_utilization_avg_pct": snap.gpu_utilization_avg_pct,
                "total_cpu_millicores": snap.total_cpu_millicores,
                "allocated_cpu_millicores": snap.allocated_cpu_millicores,
                "total_memory_mb": snap.total_memory_mb,
                "allocated_memory_mb": snap.allocated_memory_mb,
            })

        # ── 7. Broadcast to WebSocket subscribers ──
        self._fire("metrics", "tick",
            {"samples": [s.model_dump() for s in samples]},
            tick_count=self.tick_count,
            simulated_minutes=self.simulated_minutes,
        )
        if cluster is not None:
            snap = cluster.get_snapshot()
            self._fire("cluster", "snapshot", snap.model_dump(),
                tick_count=self.tick_count,
            )

        return samples

    # ── Queries ────────────────────────────────────────────────

    def get_status(self) -> SimulatorStatus:
        """Get current simulator status.

        Returns:
            SimulatorStatus: Current status enum value.
        """
        return self.status

    def get_config(self) -> SimulationConfig:
        """Get current simulation configuration.

        Returns:
            SimulationConfig: The active configuration.
        """
        return self.config

    async def update_config(self, config: SimulationConfig) -> None:
        """Update simulation configuration.

        Only allowed when simulation is stopped or paused.

        Args:
            config: New simulation configuration.

        Raises:
            RuntimeError: If simulation is currently running.
        """
        if self.status == SimulatorStatus.RUNNING:
            raise RuntimeError(
                "Cannot update config while simulation is running"
            )
        self.config = config
