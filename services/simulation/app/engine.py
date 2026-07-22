"""Core simulation engine orchestrating the cluster simulation loop.

Manages the simulation lifecycle: start, pause, resume, stop, tick.
Coordinates between ClusterStateManager and MetricsGenerator.
"""

from shared.simulation import SimulationConfig, SimulatorStatus
from shared.metrics import MetricSample
from shared.db.manager import DatabaseManager
from app.metrics_generator import MetricsGenerator


class SimulationEngine:
    """Orchestrates the cluster simulation lifecycle.

    Coordinates state management, metrics generation, and timing.
    Produces MetricSamples each tick and persists them via DatabaseManager.

    Attributes:
        config: Current simulation configuration.
        db_manager: Database manager for persisting metrics/snapshots.
        metrics_generator: Generator producing simulated metrics.

    TODO:
        - Add async task management for tick loop
        - Add event bus for real-time updates to dashboard
        - Support multiple concurrent simulations
    """

    def __init__(
        self,
        config: SimulationConfig,
        db_manager: DatabaseManager,
        metrics_generator: MetricsGenerator,
    ) -> None:
        """Initialize the simulation engine.

        Args:
            config: Simulation configuration (cluster topology, timing, deployments).
            db_manager: Database manager for persisting metrics and snapshots.
            metrics_generator: Metrics generator for producing simulated data.

        TODO:
            - Validate config completeness before accepting
            - Store creation timestamp for uptime tracking
        """
        ...

    async def start(self) -> None:
        """Start the simulation.

        Initializes cluster state, begins the tick loop, and starts
        persisting metrics to the database.

        Raises:
            RuntimeError: If simulation is already running.

        TODO:
            - Initialize ClusterStateManager with config
            - Create initial deployments and pods
            - Start async tick loop task
        """
        ...

    async def pause(self) -> None:
        """Pause the simulation.

        Suspends the tick loop but preserves all state.
        Can be resumed later from the same point.

        Raises:
            RuntimeError: If simulation is not currently running.

        TODO:
            - Cancel async tick task
            - Set status to PAUSED
        """
        ...

    async def resume(self) -> None:
        """Resume a paused simulation.

        Restarts the tick loop from where it was paused.

        Raises:
            RuntimeError: If simulation is not currently paused.

        TODO:
            - Restart async tick task
            - Set status to RUNNING
        """
        ...

    async def stop(self) -> None:
        """Stop the simulation and clean up.

        Halts the tick loop, flushes remaining metrics, and resets state.

        TODO:
            - Cancel async tick task
            - Flush pending metrics to DB
            - Reset cluster state
            - Set status to STOPPED
        """
        ...

    async def tick(self) -> list[MetricSample]:
        """Execute one simulation tick.

        Advances the simulation clock, updates cluster state,
        generates metrics, and persists results.

        Returns:
            list[MetricSample]: Generated metric samples for this tick.

        TODO:
            - Advance simulated time by tick interval
            - Update pod ages and resource usage
            - Check for scaling triggers
            - Generate metrics via MetricsGenerator
            - Persist metrics and optional snapshot to DB
            - Return generated samples
        """
        ...

    def get_status(self) -> SimulatorStatus:
        """Get current simulator status.

        Returns:
            SimulatorStatus: Current status enum value.

        TODO:
            - Return richer status with tick count and uptime
        """
        ...

    def get_config(self) -> SimulationConfig:
        """Get current simulation configuration.

        Returns:
            SimulationConfig: The active configuration.
        """
        ...

    async def update_config(self, config: SimulationConfig) -> None:
        """Update simulation configuration.

        Only allowed when simulation is stopped or paused.

        Args:
            config: New simulation configuration.

        Raises:
            RuntimeError: If simulation is currently running.

        TODO:
            - Validate new config
            - Update cluster state if topology changed
        """
        ...
