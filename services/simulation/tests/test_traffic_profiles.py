"""Tests for traffic profile functions."""

from __future__ import annotations

import math

import pytest

from app.traffic_profiles import (
    steady_profile,
    sine_wave_profile,
    step_spike_profile,
    flash_sale_profile,
    exam_start_profile,
    random_walk_profile,
    PROFILE_REGISTRY,
)
from shared.enums import TrafficPattern


class TestTrafficProfiles:
    """Test all traffic profile functions produce valid RPS values."""

    # ── Steady ────────────────────────────────────────────────

    def test_steady_always_returns_base(self):
        """Steady profile should return base_rps unchanged."""
        for t in [0, 30, 60, 120]:
            assert steady_profile(t, 50.0) == 50.0

    def test_steady_non_negative(self):
        """Steady should never return negative, even for negative base."""
        val = steady_profile(10, -10.0)
        assert val >= 0.0

    # ── Sine Wave ─────────────────────────────────────────────

    def test_sine_wave_oscillates_around_base(self):
        """Sine wave should oscillate around base_rps."""
        base = 100.0
        values = [sine_wave_profile(t, base, spike_multiplier=2.0, period_minutes=60)
                  for t in range(0, 121, 5)]
        avg = sum(values) / len(values)
        # Average should be close to base_rps
        assert abs(avg - base) < base * 0.15, f"Avg {avg} too far from base {base}"

    def test_sine_wave_symmetry(self):
        """Sine at t=0 and t=period/2 should be opposite sides of base."""
        base = 100.0
        v0 = sine_wave_profile(0, base, spike_multiplier=2.0, period_minutes=60)
        v30 = sine_wave_profile(30, base, spike_multiplier=2.0, period_minutes=60)
        # One should be above base, the other below
        assert (v0 - base) * (v30 - base) < 0 or abs(v0 - base) < 0.01

    def test_sine_wave_non_negative(self):
        """Sine wave should never return negative."""
        for t in range(0, 120):
            val = sine_wave_profile(float(t), 50.0, spike_multiplier=1.0)
            assert val >= 0.0

    # ── Step Spike ────────────────────────────────────────────

    def test_step_spike_before_and_after(self):
        """Outside the spike window, should return base_rps."""
        base = 50.0
        assert step_spike_profile(10, base, spike_minute=30, spike_duration_minutes=10) == base
        assert step_spike_profile(41, base, spike_minute=30, spike_duration_minutes=10) == base

    def test_step_spike_during(self):
        """Inside the spike window, should return spike_multiplier * base."""
        base = 50.0
        val = step_spike_profile(35, base, spike_multiplier=5.0, spike_minute=30, spike_duration_minutes=10)
        assert val == 250.0

    @pytest.mark.parametrize("t", [30, 35, 39.9])
    def test_step_spike_window_boundaries(self, t):
        """Boundary conditions for spike window."""
        base = 50.0
        val = step_spike_profile(t, base, spike_minute=30, spike_duration_minutes=10)
        assert val == 250.0

    # ── Flash Sale ────────────────────────────────────────────

    def test_flash_sale_before(self):
        """Before sale start, should return base_rps."""
        base = 50.0
        val = flash_sale_profile(30, base, spike_minute=60, spike_multiplier=10.0)
        assert val == 50.0

    def test_flash_sale_peak(self):
        """At sale start, value should be at peak."""
        base = 50.0
        val = flash_sale_profile(60, base, spike_minute=60, spike_multiplier=10.0)
        assert val == 50.0 + 50.0 * 9.0  # base + base * (10-1) * exp(0)
        # Actually the decay_factor = exp(-3.0 * 0 / 20) = exp(0) = 1
        # So value = 50 + 50 * 9 * 1 = 500
        assert pytest.approx(val, rel=0.01) == 500.0

    def test_flash_sale_decays(self):
        """Value should be decreasing during the sale window."""
        base = 50.0
        t1 = 65  # 5 min in
        t2 = 70  # 10 min in
        v1 = flash_sale_profile(t1, base, spike_minute=60, spike_duration_minutes=20)
        v2 = flash_sale_profile(t2, base, spike_minute=60, spike_duration_minutes=20)
        assert v2 <= v1  # Should be decaying

    def test_flash_sale_after(self):
        """After sale ends, should return base_rps."""
        base = 50.0
        val = flash_sale_profile(100, base, spike_minute=60, spike_duration_minutes=20)
        assert val == 50.0

    # ── Exam Start ────────────────────────────────────────────

    def test_exam_before(self):
        """Before exam, should return base_rps."""
        val = exam_start_profile(10, 30.0, spike_minute=30)
        assert val == 30.0

    def test_exam_ramp_up(self):
        """During ramp-up, value should increase."""
        base = 30.0
        v1 = exam_start_profile(32, base, spike_minute=30)  # 2 min into ramp
        v2 = exam_start_profile(40, base, spike_minute=30)  # 10 min into ramp (near peak)
        assert v1 > base  # Should have started increasing
        assert v2 > v1   # Should still be increasing

    def test_exam_sustain(self):
        """During sustain phase, should be at peak."""
        base = 30.0
        val = exam_start_profile(50, base, spike_minute=30, spike_multiplier=8.0)
        # 50 is within sustain zone (45-90)
        assert pytest.approx(val, rel=0.05) == 240.0  # base * 8

    def test_exam_after_drop(self):
        """After sustain, should start dropping toward base."""
        base = 30.0
        val = exam_start_profile(120, base, spike_minute=30, spike_duration_minutes=60)
        # Should still be above base but below peak
        assert val >= base
        assert val < 240.0

    # ── Random Walk ───────────────────────────────────────────

    def test_random_walk_starts_at_base(self):
        """First call should return base_rps."""
        val = random_walk_profile(0, 100.0)
        assert val > 0
        # First call — base_rps with a small noise step
        assert abs(val - 100.0) < 20.0

    def test_random_walk_maintains_state(self):
        """Subsequent calls should have continuity (no huge jumps)."""
        # Reset state for clean test
        from app.traffic_profiles import _random_walk_state
        _random_walk_state.clear()

        values = [random_walk_profile(float(i), 100.0) for i in range(10)]
        # Each step should be a small change from the previous
        for i in range(1, len(values)):
            assert abs(values[i] - values[i - 1]) < 30.0

    def test_random_walk_mean_reversion(self):
        """Random walk should revert toward base_rps over time."""
        from app.traffic_profiles import _random_walk_state
        _random_walk_state.clear()

        # Push the walk to an extreme, then check it drifts back
        for _ in range(20):
            random_walk_profile(float(_), 100.0)
        avg = sum(_random_walk_state.values()) / len(_random_walk_state)
        assert abs(avg - 100.0) < 30.0

    # ── Registry ──────────────────────────────────────────────

    def test_registry_has_all_patterns(self):
        """PROFILE_REGISTRY should have an entry for every non-CUSTOM pattern."""
        for pattern in TrafficPattern:
            if pattern == TrafficPattern.CUSTOM:
                continue
            assert pattern in PROFILE_REGISTRY, f"Missing profile for {pattern}"

    def test_registry_functions_are_callable(self):
        """Every entry in the registry should be callable."""
        for pattern, func in PROFILE_REGISTRY.items():
            assert callable(func), f"{pattern} entry is not callable"
            # Test that it returns a valid RPS value
            val = func(30, 100.0)
            assert isinstance(val, float)
            assert val >= 0.0
