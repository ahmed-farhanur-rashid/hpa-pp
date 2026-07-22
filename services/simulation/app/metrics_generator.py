"""Metrics generator for producing simulated metric samples.

Uses traffic profiles and cluster state to generate realistic
metric data each simulation tick. Applies noise for realism.
"""

import random

from shared.metrics import MetricSample
from shared.cluster import DeploymentState, ClusterSnapshot


class MetricsGenerator:
    """Generates simulated metric samples for all deployments.

    Each tick, produces one MetricSample per deployment based on
    the deployment's traffic profile and current cluster state.
    Applies Gaussian noise for realistic variation.

    Attributes:
        rng: Random number generator for noise and profile functions.

    TODO:
        - Support custom metric distributions per deployment
        - Add latency modeling based on CPU saturation
        - Add error rate modeling
    """

    def __init__(self, seed: int | None = None) -> None:
        """Initialize the metrics generator.

        Args:
            seed: Random seed for deterministic output. None for random.

        TODO:
            - Store seed for reproducibility logging
            - Initialize traffic profile registry
        """
        ...

    def generate_batch(
        self,
        deployments: list[DeploymentState],
        cluster_state: ClusterSnapshot,
        simulated_time: float,
    ) -> list[MetricSample]:
        """Generate metric samples for all deployments at current time.

        Args:
            deployments: List of deployment states to generate metrics for.
            cluster_state: Current cluster snapshot for pod count context.
            simulated_time: Current simulation time in minutes.

        Returns:
            list[MetricSample]: One MetricSample per deployment.

        TODO:
            - Look up traffic profile per deployment
            - Compute RPS from profile
            - Derive CPU/memory utilization from RPS
            - Add noise to all values
            - Set pod_count from deployment state
        """
        ...

    def _get_current_rps(
        self,
        profile: dict,
        simulated_minute: float,
    ) -> float:
        """Compute current requests-per-second from traffic profile.

        Dispatches to the appropriate profile function based on
        the profile's pattern type.

        Args:
            profile: Traffic profile configuration dict.
            simulated_minute: Current simulation time in minutes.

        Returns:
            float: Current RPS value (always >= 0).

        TODO:
            - Support CUSTOM pattern with user-defined function
            - Cache profile function lookups
        """
        ...

    def _compute_cpu_util(
        self,
        rps_per_pod: float,
        baseline_per_pod: float,
    ) -> float:
        """Compute CPU utilization percentage from RPS.

        Uses a simple linear model: CPU% = (rps / baseline) * 100.
        Capped at 100%.

        Args:
            rps_per_pod: Requests per second handled by each pod.
            baseline_per_pod: RPS at which CPU = 100%.

        Returns:
            float: CPU utilization percentage (0.0 - 100.0).

        TODO:
            - Use non-linear model for saturation behavior
            - Add per-deployment baseline configuration
        """
        ...

    def _compute_memory_usage(
        self,
        rps_per_pod: float,
        base_memory_mb: float,
    ) -> float:
        """Compute memory usage from RPS and base memory.

        Memory grows sub-linearly with RPS to model real behavior.

        Args:
            rps_per_pod: Requests per second per pod.
            base_memory_mb: Base memory usage at idle in megabytes.

        Returns:
            float: Memory usage in megabytes.

        TODO:
            - Model memory growth curve (logarithmic?)
            - Add GC pause simulation
        """
        ...

    def _add_noise(self, value: float, noise_std_pct: float) -> float:
        """Add Gaussian noise to a metric value.

        Args:
            value: Original metric value.
            noise_std_pct: Standard deviation as percentage of value.

        Returns:
            float: Noised value, clamped to >= 0.

        TODO:
            - Use log-normal noise for positive values
            - Add temporal correlation (noise doesn't jump randomly)
        """
        ...
