"""Metrics generator for producing simulated metric samples.

Uses traffic profiles and cluster state to generate realistic
metric data each simulation tick. Applies noise for realism.
"""

import math
import random
from datetime import datetime, timedelta

from shared.metrics import MetricSample
from shared.cluster import DeploymentState, ClusterSnapshot
from shared.simulation import TrafficProfile
from shared.enums import TrafficPattern
from app.anomalies.base import AnomalyEffect
from app.traffic_profiles import PROFILE_REGISTRY


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

    # Base UTC time for converting simulated minutes to datetime
    _BASE_UTC = datetime(2026, 1, 1, 0, 0, 0)

    def __init__(self, seed: int | None = None) -> None:
        """Initialize the metrics generator.

        Args:
            seed: Random seed for deterministic output. None for random.

        TODO:
            - Store seed for reproducibility logging
            - Initialize traffic profile registry
        """
        self.seed = seed
        self.rng = random.Random(seed)
        self._deployment_profiles: dict[str, TrafficProfile] = {}

    def set_deployment_profiles(self, profiles: dict[str, TrafficProfile]) -> None:
        """Set the traffic profile for each deployment.

        Args:
            profiles: Mapping of deployment_id to its TrafficProfile.
        """
        self._deployment_profiles = profiles

    def generate_batch(
        self,
        deployments: list[DeploymentState],
        cluster_state: ClusterSnapshot,
        simulated_time: float,
        anomaly_effect: AnomalyEffect | None = None,
    ) -> list[MetricSample]:
        """Generate metric samples for all deployments at current time.

        Args:
            deployments: List of deployment states to generate metrics for.
            cluster_state: Current cluster snapshot for pod count context.
            simulated_time: Current simulation time in minutes.
            anomaly_effect: Optional anomaly modifiers to distort metrics.

        Returns:
            list[MetricSample]: One MetricSample per deployment.
        """
        extra_jitter = anomaly_effect.jitter if anomaly_effect else 0.0
        simulated_minute = simulated_time
        simulated_time_utc = self._BASE_UTC + timedelta(minutes=simulated_minute)

        batch: list[MetricSample] = []

        for deployment in deployments:
            dep_id = deployment.deployment_id

            # ── Anomaly: skip blocked deployments entirely ──
            if anomaly_effect and dep_id in anomaly_effect.blocked_deployments:
                sample = MetricSample(
                    deployment_id=dep_id,
                    simulated_time_utc=simulated_time_utc,
                    cpu_utilization_pct=0.0,
                    memory_usage_mb=0.0,
                    requests_per_second=0.0,
                    gpu_utilization_pct=None,
                    latency_ms=None,
                    pod_count=deployment.current_replicas,
                )
                batch.append(sample)
                continue

            profile = self._deployment_profiles.get(deployment.deployment_id)
            if profile is None:
                # No profile — generate zero/empty metrics
                sample = MetricSample(
                    deployment_id=deployment.deployment_id,
                    simulated_time_utc=simulated_time_utc,
                    cpu_utilization_pct=0.0,
                    memory_usage_mb=0.0,
                    requests_per_second=0.0,
                    gpu_utilization_pct=None,
                    latency_ms=None,
                    pod_count=deployment.current_replicas,
                )
                batch.append(sample)
                continue

            # Compute current RPS from traffic profile
            rps = self._get_current_rps(profile, simulated_minute)

            # ── Anomaly: apply RPS multiplier ──
            if anomaly_effect and dep_id in anomaly_effect.rps_multiplier:
                rps *= anomaly_effect.rps_multiplier[dep_id]

            # Pod count from deployment state
            pod_count = max(1, deployment.current_replicas)

            # RPS distributed across pods
            rps_per_pod = rps / pod_count

            # CPU utilization: non-linear saturation model
            # baseline_per_pod represents the RPS at which a single pod hits ~100% CPU
            baseline_per_pod = 100.0
            cpu_util = self._compute_cpu_util(rps_per_pod, baseline_per_pod)

            # ── Anomaly: apply CPU offset ──
            if anomaly_effect and dep_id in anomaly_effect.cpu_offset_pp:
                cpu_util += anomaly_effect.cpu_offset_pp[dep_id]
                cpu_util = max(0.0, min(100.0, cpu_util))

            # Memory usage: logarithmic growth from base
            base_memory_mb = float(deployment.memory_request_mb) * 0.5
            memory_usage = self._compute_memory_usage(rps_per_pod, base_memory_mb)

            # ── Anomaly: apply memory multiplier ──
            if anomaly_effect and dep_id in anomaly_effect.memory_multiplier:
                memory_usage *= anomaly_effect.memory_multiplier[dep_id]

            # GPU utilization: only if deployment requires GPU
            gpu_utilization = None
            if deployment.requires_gpu:
                if anomaly_effect and dep_id in anomaly_effect.force_gpu_off:
                    gpu_utilization = None
                else:
                    gpu_utilization = self._add_noise(
                        min(100.0, cpu_util * 0.9 + self.rng.uniform(0, 5)),
                        profile.noise_std_pct,
                    )
                    gpu_utilization = max(0.0, min(100.0, gpu_utilization))

            # Latency: derived from CPU saturation (higher CPU = higher latency)
            # Base latency ~5ms, grows exponentially as CPU approaches 100%
            base_latency_ms = 5.0
            if anomaly_effect and anomaly_effect.latency_ms_absolute is not None:
                base_latency_ms = anomaly_effect.latency_ms_absolute
            latency_ms = base_latency_ms * (1.0 + (cpu_util / 100.0) ** 3 * 19.0)
            # ── Anomaly: apply latency multiplier ──
            if anomaly_effect and dep_id in anomaly_effect.latency_multiplier:
                latency_ms *= anomaly_effect.latency_multiplier[dep_id]
            latency_ms = self._add_noise(latency_ms, profile.noise_std_pct)
            latency_ms = max(0.0, latency_ms)

            # Noise + extra jitter from anomalies
            effective_noise = profile.noise_std_pct + extra_jitter * 100.0
            cpu_util = self._add_noise(cpu_util, effective_noise)
            cpu_util = max(0.0, min(100.0, cpu_util))

            memory_usage = self._add_noise(memory_usage, effective_noise)
            memory_usage = max(0.0, memory_usage)

            rps = self._add_noise(rps, effective_noise)
            rps = max(0.0, rps)

            sample = MetricSample(
                deployment_id=deployment.deployment_id,
                simulated_time_utc=simulated_time_utc,
                cpu_utilization_pct=cpu_util,
                memory_usage_mb=memory_usage,
                requests_per_second=rps,
                gpu_utilization_pct=gpu_utilization,
                latency_ms=latency_ms,
                pod_count=pod_count,
            )
            batch.append(sample)

        return batch

    def _get_current_rps(
        self,
        profile: TrafficProfile,
        simulated_minute: float,
    ) -> float:
        """Compute current requests-per-second from traffic profile.

        Dispatches to the appropriate profile function based on
        the profile's pattern type.

        Args:
            profile: TrafficProfile configuration object.
            simulated_minute: Current simulation time in minutes.

        Returns:
            float: Current RPS value (always >= 0).
        """
        profile_fn = PROFILE_REGISTRY[profile.pattern]
        kwargs = {
            "spike_multiplier": profile.spike_multiplier,
            "noise_std_pct": profile.noise_std_pct,
            "period_minutes": profile.period_minutes,
            "spike_minute": profile.spike_minute,
            "spike_duration_minutes": profile.spike_duration_minutes,
            "trend_gradient": profile.trend_gradient,
        }
        rps = profile_fn(simulated_minute, profile.base_load_rps, **kwargs)
        return max(0.0, float(rps))

    def _compute_cpu_util(
        self,
        rps_per_pod: float,
        baseline_per_pod: float,
    ) -> float:
        """Compute CPU utilization percentage from RPS.

        Uses a non-linear saturation model:
        - Below baseline: sub-linear growth (power curve)
        - At/above baseline: approaches 100% asymptotically

        Args:
            rps_per_pod: Requests per second handled by each pod.
            baseline_per_pod: RPS at which CPU ~ 100%.

        Returns:
            float: CPU utilization percentage (0.0 - 100.0).
        """
        if baseline_per_pod <= 0:
            return 0.0

        if rps_per_pod >= baseline_per_pod:
            cpu = 80.0 + 20.0 * (1.0 - math.exp(-0.5 * (rps_per_pod - baseline_per_pod)))
        else:
            cpu = 100.0 * (rps_per_pod / baseline_per_pod) ** 0.7

        return max(0.0, min(100.0, cpu))

    def _compute_memory_usage(
        self,
        rps_per_pod: float,
        base_memory_mb: float,
    ) -> float:
        """Compute memory usage from RPS and base memory.

        Memory grows logarithmically with RPS to model real behavior.
        Capped at 1.5x base memory to prevent runaway growth.

        Args:
            rps_per_pod: Requests per second per pod.
            base_memory_mb: Base memory usage at idle in megabytes.

        Returns:
            float: Memory usage in megabytes.
        """
        usage = base_memory_mb * min(1.5, 1.0 + 0.15 * math.log(1.0 + rps_per_pod / 5.0))
        return max(0.0, usage)

    def _add_noise(self, value: float, noise_std_pct: float) -> float:
        """Add Gaussian noise to a metric value.

        Args:
            value: Original metric value.
            noise_std_pct: Standard deviation as percentage of value.

        Returns:
            float: Noised value, clamped to >= 0.
        """
        if noise_std_pct <= 0:
            return value
        noise_value = self.rng.gauss(value, value * noise_std_pct / 100.0)
        return max(0.0, noise_value)
