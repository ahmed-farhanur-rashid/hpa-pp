"""Unit tests for the GPU scheduler — positive, negative, and edge cases."""

from __future__ import annotations

import uuid

import pytest

from app.gpu_scheduler import GpuScheduler
from shared.gpu import GpuAssignment

# Shared test data: gpu_specs = list[dict] with gpu_id, node_id, total_memory_mb, allocated_memory_mb
GPU_SPECS = [
    {"gpu_id": "gpu-0", "node_id": "node-0", "total_memory_mb": 16384, "allocated_memory_mb": 0},
    {"gpu_id": "gpu-1", "node_id": "node-0", "total_memory_mb": 16384, "allocated_memory_mb": 0},
    {"gpu_id": "gpu-2", "node_id": "node-1", "total_memory_mb": 16384, "allocated_memory_mb": 8192},
]

POD_IDS = ["pod-ml-1", "pod-ml-2", "pod-ml-3"]


def make_assignment(
    gpu_id: str,
    pod_id: str,
    allocated_mb: int = 4096,
    total_mb: int = 16384,
) -> GpuAssignment:
    """Helper to create a GpuAssignment for testing."""
    return GpuAssignment(
        assignment_id=str(uuid.uuid4()),
        gpu_id=gpu_id,
        pod_id=pod_id,
        deployment_id="ml-inference",
        memory_allocated_mb=allocated_mb,
        compute_allocated_pct=round((allocated_mb / total_mb) * 100, 2),
    )


@pytest.fixture
def scheduler() -> GpuScheduler:
    return GpuScheduler()


class TestAssignGpus:
    """Positive: assign GPUs to pods correctly."""

    @pytest.mark.asyncio
    async def test_bin_pack_assigns_to_fullest(self, scheduler):
        """bin_pack places pods on GPU with highest current utilization first."""
        assignments = await scheduler.assign_gpus(POD_IDS, GPU_SPECS, strategy="bin_pack")
        assert len(assignments) == 3
        # gpu-2 has 50% utilization (8192/16384) — fullest → gets first pod
        assert assignments[0].gpu_id == "gpu-2"

    @pytest.mark.asyncio
    async def test_spread_assigns_to_emptiest(self, scheduler):
        """spread places pods on GPU with lowest current utilization first."""
        assignments = await scheduler.assign_gpus(POD_IDS, GPU_SPECS, strategy="spread")
        assert len(assignments) == 3
        # gpu-0 and gpu-1 have 0% — emptiest → first pod goes to one of them
        assert assignments[0].gpu_id in ("gpu-0", "gpu-1")

    @pytest.mark.asyncio
    async def test_assigns_all_pods(self, scheduler):
        """All pods receive a valid GpuAssignment."""
        assignments = await scheduler.assign_gpus(POD_IDS, GPU_SPECS)
        assert len(assignments) == len(POD_IDS)
        assigned_pods = {a.pod_id for a in assignments}
        assert assigned_pods == set(POD_IDS)
        for a in assignments:
            assert a.gpu_id in {g["gpu_id"] for g in GPU_SPECS}

    @pytest.mark.asyncio
    async def test_empty_gpus_returns_no_assignments(self, scheduler):
        """Empty GPU list returns empty assignments, no error."""
        assignments = await scheduler.assign_gpus(POD_IDS, [])
        assert assignments == []

    @pytest.mark.asyncio
    async def test_no_pods_returns_empty(self, scheduler):
        """Empty pod list returns empty assignments list."""
        assignments = await scheduler.assign_gpus([], GPU_SPECS)
        assert assignments == []

    @pytest.mark.asyncio
    async def test_more_pods_than_capacity(self, scheduler):
        """When pods exceed GPU memory, only fit pods are assigned."""
        one_small_gpu = [{"gpu_id": "gpu-0", "node_id": "node-0", "total_memory_mb": 4096, "allocated_memory_mb": 0}]
        eight_pods = [f"pod-{i}" for i in range(8)]
        assignments = await scheduler.assign_gpus(eight_pods, one_small_gpu, memory_per_pod_mb=1024)
        # 4096 / 1024 = 4 pods max
        assert len(assignments) < len(eight_pods)
        assert len(assignments) <= 4

    @pytest.mark.asyncio
    async def test_invalid_strategy_raises(self, scheduler):
        """Unknown strategy string raises ValueError."""
        with pytest.raises(ValueError, match="strategy"):
            await scheduler.assign_gpus(POD_IDS, GPU_SPECS, strategy="invalid")


class TestDetectContention:
    """Positive and negative: detect GPU contention from gpu_specs."""

    CONTENDED_SPECS = [
        {"gpu_id": "gpu-0", "node_id": "node-0", "total_memory_mb": 16384, "allocated_memory_mb": 15500},
        {"gpu_id": "gpu-1", "node_id": "node-0", "total_memory_mb": 16384, "allocated_memory_mb": 4000},
    ]

    def test_above_threshold_flagged(self, scheduler):
        """GPU above 90% utilization is flagged as contended."""
        contended = scheduler.detect_contention([], self.CONTENDED_SPECS, threshold_pct=90.0)
        assert "gpu-0" in contended  # 15500/16384 ≈ 94.6%
        assert "gpu-1" not in contended  # 4000/16384 ≈ 24.4%

    def test_below_threshold_not_flagged(self, scheduler):
        """GPU below threshold is not flagged."""
        contended = scheduler.detect_contention([], self.CONTENDED_SPECS, threshold_pct=90.0)
        assert "gpu-1" not in contended

    def test_empty_specs_returns_empty(self, scheduler):
        """Empty GPU list returns no contention."""
        contended = scheduler.detect_contention([], [])
        assert contended == []

    def test_zero_threshold_contends_all(self, scheduler):
        """Zero threshold flags every GPU that has allocation."""
        contended = scheduler.detect_contention([], self.CONTENDED_SPECS, threshold_pct=0.0)
        # Both GPUs have non-zero allocation
        assert len(contended) == 2

    def test_100_threshold_no_contention(self, scheduler):
        """100% threshold flags nothing unless fully allocated (which none are)."""
        contended = scheduler.detect_contention([], self.CONTENDED_SPECS, threshold_pct=100.0)
        assert len(contended) == 0


class TestRebalance:
    """Positive: rebalancing moves assignments from contended GPUs."""

    @pytest.mark.asyncio
    async def test_rebalance_with_contention(self, scheduler):
        """Rebalance with contentious assignments returns event with gpus_involved."""
        specs = [
            {"gpu_id": "gpu-0", "node_id": "node-0", "total_memory_mb": 16384, "allocated_memory_mb": 15500},
            {"gpu_id": "gpu-1", "node_id": "node-0", "total_memory_mb": 16384, "allocated_memory_mb": 0},
        ]
        assignments = [make_assignment("gpu-0", "pod-a", allocated_mb=15500)]
        event = await scheduler.rebalance(assignments, specs, trigger_reason="test")
        assert event.trigger_reason == "test"
        assert event.gpus_involved is not None

    @pytest.mark.asyncio
    async def test_rebalance_no_contention_no_gpus_involved(self, scheduler):
        """Rebalance with no contention returns empty gpus_involved."""
        low_specs = [
            {"gpu_id": "gpu-0", "node_id": "node-0", "total_memory_mb": 16384, "allocated_memory_mb": 2000},
            {"gpu_id": "gpu-1", "node_id": "node-0", "total_memory_mb": 16384, "allocated_memory_mb": 3000},
        ]
        assignments = [make_assignment("gpu-0", "pod-a")]
        event = await scheduler.rebalance(assignments, low_specs, trigger_reason="scheduled")
        assert event.gpus_involved == []


class TestGetUtilization:
    """Positive and negative: GPU utilization calculation."""

    def test_utilization_ratio(self, scheduler):
        """Utilization is allocated / total * 100."""
        util = scheduler.get_gpu_utilization("gpu-2", GPU_SPECS)
        assert util == pytest.approx(50.0)  # 8192 / 16384 = 50%

    def test_zero_utilization(self, scheduler):
        """Unallocated GPU returns 0% utilization."""
        util = scheduler.get_gpu_utilization("gpu-0", GPU_SPECS)
        assert util == 0.0

    def test_unknown_gpu_raises(self, scheduler):
        """Requesting utilization for unknown GPU raises ValueError."""
        with pytest.raises(ValueError):
            scheduler.get_gpu_utilization("nonexistent", GPU_SPECS)

    def test_empty_specs_raises(self, scheduler):
        """Empty GPU list raises ValueError on lookup."""
        with pytest.raises(ValueError):
            scheduler.get_gpu_utilization("gpu-0", [])

    def test_full_allocation(self, scheduler):
        """Fully allocated GPU returns 100%."""
        full_spec = [{"gpu_id": "gpu-0", "node_id": "node-0", "total_memory_mb": 8192, "allocated_memory_mb": 8192}]
        util = scheduler.get_gpu_utilization("gpu-0", full_spec)
        assert util == 100.0

    def test_partial_allocation(self, scheduler):
        """Partially allocated GPU returns correct percentage."""
        spec = [{"gpu_id": "gpu-0", "node_id": "node-0", "total_memory_mb": 16384, "allocated_memory_mb": 4096}]
        util = scheduler.get_gpu_utilization("gpu-0", spec)
        assert util == 25.0
