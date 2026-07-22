"""Traffic profile functions for simulating different load patterns.

Each function computes a requests-per-second value at a given minute.
Pure functions — no side effects, no state.
"""

from collections.abc import Callable

from shared.enums import TrafficPattern


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
    ...


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
    ...


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
    ...


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
    ...


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
    ...


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
    ...


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
