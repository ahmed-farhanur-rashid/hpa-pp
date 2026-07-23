"""Traffic profile functions for simulating different load patterns.

Each function computes a requests-per-second value at a given minute.
Pure functions — no side effects, no state.
"""

import math
import random
from collections.abc import Callable

from shared.enums import TrafficPattern

_random_walk_state: dict[str, float] = {}


def steady_profile(
    current_minute: float,
    base_rps: float,
    **kwargs,
) -> float:
    """Constant traffic at base load.

    Args:
        current_minute: Current simulation time in minutes.
        base_rps: Baseline requests per second.
        **kwargs: Additional profile parameters (unused).

    Returns:
        float: Always returns base_rps.

    TODO:
        - Add optional slight ramp-in for first N minutes
    """
    return max(0.0, float(base_rps))


def sine_wave_profile(
    current_minute: float,
    base_rps: float,
    **kwargs,
) -> float:
    """Sinusoidal traffic pattern with configurable period.

    Oscillates between 0 and 2x base_rps.

    Args:
        current_minute: Current simulation time in minutes.
        base_rps: Baseline requests per second (midpoint of wave).
        **kwargs:
            period_minutes (int): Wave period in minutes. Default 60.
            spike_multiplier (float): Amplitude multiplier. Default 1.0.

    Returns:
        float: Current RPS following sine curve.

    TODO:
        - Support phase offset parameter
    """
    period_minutes: int = int(kwargs.get("period_minutes", 60))
    spike_multiplier: float = float(kwargs.get("spike_multiplier", 1.0))
    amplitude = base_rps * (spike_multiplier - 1.0) / 2.0
    value = base_rps + amplitude * math.sin(2.0 * math.pi * current_minute / period_minutes)
    return max(0.0, float(value))


def step_spike_profile(
    current_minute: float,
    base_rps: float,
    **kwargs,
) -> float:
    """Step function: base load with a rectangular spike.

    Traffic jumps to spike_multiplier * base_rps at spike_minute
    and returns to base after spike_duration_minutes.

    Args:
        current_minute: Current simulation time in minutes.
        base_rps: Baseline requests per second.
        **kwargs:
            spike_multiplier (float): Peak load multiplier. Default 5.0.
            spike_minute (int): Minute when spike starts. Default 30.
            spike_duration_minutes (int): Spike duration. Default 10.

    Returns:
        float: base_rps or spiked RPS depending on current time.

    TODO:
        - Support multiple spike windows
        - Add ramp-up/ramp-down at spike edges
    """
    spike_multiplier: float = float(kwargs.get("spike_multiplier", 5.0))
    spike_minute: float = float(kwargs.get("spike_minute", 30))
    spike_duration_minutes: float = float(kwargs.get("spike_duration_minutes", 10))
    if spike_minute <= current_minute < spike_minute + spike_duration_minutes:
        return max(0.0, float(base_rps * spike_multiplier))
    return max(0.0, float(base_rps))


def flash_sale_profile(
    current_minute: float,
    base_rps: float,
    **kwargs,
) -> float:
    """Flash sale pattern: sudden spike with exponential decay.

    Traffic jumps to spike_multiplier * base_rps, then decays
    exponentially back to base_rps.

    Args:
        current_minute: Current simulation time in minutes.
        base_rps: Baseline requests per second.
        **kwargs:
            spike_multiplier (float): Peak load multiplier. Default 10.0.
            spike_minute (int): Minute when sale starts. Default 60.
            spike_duration_minutes (int): Decay duration. Default 20.

    Returns:
        float: Current RPS following flash sale curve.

    TODO:
        - Model pre-sale buildup
        - Add secondary smaller spikes
    """
    spike_multiplier: float = float(kwargs.get("spike_multiplier", 10.0))
    spike_minute: float = float(kwargs.get("spike_minute", 60))
    spike_duration_minutes: float = float(kwargs.get("spike_duration_minutes", 20))
    if current_minute < spike_minute:
        return max(0.0, float(base_rps))
    if current_minute >= spike_minute + spike_duration_minutes:
        return max(0.0, float(base_rps))
    decay_factor = math.exp(-3.0 * (current_minute - spike_minute) / spike_duration_minutes)
    value = base_rps + (base_rps * (spike_multiplier - 1.0) * decay_factor)
    return max(0.0, float(value))


def exam_start_profile(
    current_minute: float,
    base_rps: float,
    **kwargs,
) -> float:
    """Exam start pattern: gradual ramp-up then sustained high load.

    Models students accessing an exam portal: ramp up over 15 minutes,
    sustain high load for 60 minutes, then drop off.

    Args:
        current_minute: Current simulation time in minutes.
        base_rps: Baseline requests per second.
        **kwargs:
            spike_multiplier (float): Peak load multiplier. Default 8.0.
            spike_minute (int): Minute when exam starts. Default 30.
            spike_duration_minutes (int): Exam duration. Default 60.

    Returns:
        float: Current RPS following exam pattern.

    TODO:
        - Model intermittent spikes during exam (question submissions)
        - Add post-exam grading traffic bump
    """
    spike_multiplier: float = float(kwargs.get("spike_multiplier", 8.0))
    spike_minute: float = float(kwargs.get("spike_minute", 30))
    spike_duration_minutes: float = float(kwargs.get("spike_duration_minutes", 60))
    ramp_up_minutes: float = 15.0
    if current_minute < spike_minute:
        return max(0.0, float(base_rps))
    ramp_end = spike_minute + ramp_up_minutes
    sustain_end = spike_minute + spike_duration_minutes
    if current_minute < ramp_end:
        progress = (current_minute - spike_minute) / ramp_up_minutes
        value = base_rps + (base_rps * (spike_multiplier - 1.0) * progress)
        return max(0.0, float(value))
    if current_minute < sustain_end:
        return max(0.0, float(base_rps * spike_multiplier))
    value = base_rps + (base_rps * (spike_multiplier - 1.0) * math.exp(-2.0 * (current_minute - sustain_end) / 10.0))
    return max(0.0, float(value))


def random_walk_profile(
    current_minute: float,
    base_rps: float,
    **kwargs,
) -> float:
    """Random walk traffic pattern.

    RPS changes by a small random amount each minute, with
    mean-reversion toward base_rps.

    Args:
        current_minute: Current simulation time in minutes.
        base_rps: Baseline requests per second (mean-reversion target).
        **kwargs:
            noise_std_pct (float): Step size as % of base_rps. Default 5.0.

    Returns:
        float: Current RPS after random walk step.

    TODO:
        - Maintain state between calls for continuity
        - Add mean-reversion strength parameter
    """
    noise_std_pct: float = float(kwargs.get("noise_std_pct", 5.0))
    key = str(base_rps)
    if key not in _random_walk_state:
        _random_walk_state[key] = base_rps
    current = _random_walk_state[key]
    step = base_rps * (noise_std_pct / 100.0) * random.gauss(0, 1)
    reversion = 0.05 * (base_rps - current)
    current = current + step + reversion
    _random_walk_state[key] = current
    return max(0.0, float(current))


# ── Profile registry ───────────────────────────────────────────

PROFILE_REGISTRY: dict[TrafficPattern, Callable] = {
    TrafficPattern.STEADY: steady_profile,
    TrafficPattern.SINE_WAVE: sine_wave_profile,
    TrafficPattern.STEP_SPIKE: step_spike_profile,
    TrafficPattern.FLASH_SALE: flash_sale_profile,
    TrafficPattern.EXAM_START: exam_start_profile,
    TrafficPattern.RANDOM_WALK: random_walk_profile,
}
"""Registry mapping TrafficPattern enum to profile function.

TODO:
    - Support TrafficPattern.CUSTOM with user-provided function
    - Add validation that all non-CUSTOM patterns have entries
"""
