"""Tests for ClusterStateManager."""

from __future__ import annotations

import pytest

from app.cluster_state import ClusterStateManager
from shared.enums import PodStatus, NodeStatus


class TestClusterStateManager:
    """Test cluster node/pod management, scheduling, and snapshots."""

    # ── Initialization ────────────────────────────────────────

    def test_initialize_creates_nodes(self, cluster_state):
        """initialize() should create nodes matching config."""
        assert len(cluster_state.get_all_nodes()) == 2

    def test_initialize_creates_deployments(self, cluster_state, default_config):
        """initialize() should create deployments from config."""
        deps = cluster_state.get_all_deployments()
        assert len(deps) == len(default_config.deployments)

    def test_initialize_schedules_pods(self, cluster_state):
        """initialize() should schedule initial replicas."""
        for dep in cluster_state.get_all_deployments():
            running = sum(1 for p in dep.pods if p.status == PodStatus.RUNNING)
            assert running == dep.target_replicas

    # ── Node operations ──────────────────────────────────────

    def test_create_node_with_gpus(self, cluster_state):
        """create_node creates a node with GPU devices."""
        node = cluster_state.create_node("test-node-1", 2000, 4096, 2, 8192)
        assert node.node_id == "test-node-1"
        assert len(node.gpu_ids) == 2
        assert node.gpu_ids[0] == "test-node-1-gpu-0"
        assert node.gpu_ids[1] == "test-node-1-gpu-1"
        assert node.total_gpu_memory_mb == 16384

    def test_get_node_raises_keyerror(self, cluster_state):
        """get_node should raise for missing node."""
        with pytest.raises(KeyError, match="nonexistent"):
            cluster_state.get_node("nonexistent")

    def test_get_all_nodes_returns_list(self, cluster_state):
        """get_all_nodes should return all created nodes."""
        nodes = cluster_state.get_all_nodes()
        assert len(nodes) == 2
        assert all(n.status == NodeStatus.READY for n in nodes)

    # ── Pod operations ────────────────────────────────────────

    def test_create_pod(self, cluster_state):
        """create_pod creates a PENDING pod and adds it to deployment."""
        pod = cluster_state.create_pod("test-web", 500, 512)
        assert pod.status == PodStatus.PENDING
        assert pod.node_id is None
        assert pod.deployment_id == "test-web"
        assert pod.cpu_request_millicores == 500

        # Verify it's in the deployment
        dep = cluster_state.get_deployment("test-web")
        assert any(p.pod_id == pod.pod_id for p in dep.pods)

    def test_schedule_pod_first_fit(self, cluster_state):
        """schedule_pod should find a node with enough resources."""
        # Create a pod that can fit on any node
        pod = cluster_state.create_pod("test-web", 200, 256)
        node_id = cluster_state.schedule_pod(pod)
        assert node_id is not None
        assert pod.status == PodStatus.RUNNING
        assert pod.node_id == node_id

    def test_schedule_pod_resource_exhaustion(self, cluster_state):
        """schedule_pod should return None when no node can fit."""
        # Create many large pods to fill up nodes
        for _ in range(20):
            pod_obj = cluster_state.create_pod("test-web", 4000, 8000)
            cluster_state.schedule_pod(pod_obj)

        # Now try to schedule another — should fail
        big_pod = cluster_state.create_pod("test-web", 4000, 8000)
        result = cluster_state.schedule_pod(big_pod)
        assert result is None
        assert big_pod.status == PodStatus.PENDING

    def test_schedule_pod_gpu_requirement(self, cluster_state):
        """schedule_pod should find a node with free GPU for GPU pods."""
        pod = cluster_state.create_pod("test-gpu", 500, 512, gpu_request_mb=2048)
        node_id = cluster_state.schedule_pod(pod)
        assert node_id is not None
        assert pod.gpu_id is not None
        assert pod.gpu_id.startswith(node_id)

    def test_schedule_pod_gpu_exhaustion(self, cluster_state):
        """schedule_pod should return None when no GPU available."""
        # Each node has 1 GPU, we have 2 nodes — schedule 2 GPU pods
        for _ in range(5):
            gpu_pod = cluster_state.create_pod("test-gpu", 500, 512, gpu_request_mb=2048)
            cluster_state.schedule_pod(gpu_pod)

        # Already exhausted available GPUs
        extra_pod = cluster_state.create_pod("test-gpu", 500, 512, gpu_request_mb=2048)
        result = cluster_state.schedule_pod(extra_pod)
        assert result is None

    def test_remove_pod_frees_resources(self, cluster_state):
        """remove_pod should free CPU, memory, and GPU resources."""
        # Get total cluster allocation before removal
        def total_alloc_cpu():
            return sum(n.allocated_cpu_millicores for n in cluster_state.get_all_nodes())
        def total_alloc_mem():
            return sum(n.allocated_memory_mb for n in cluster_state.get_all_nodes())

        cpu_before = total_alloc_cpu()
        mem_before = total_alloc_mem()

        dep = cluster_state.get_deployment("test-web")
        running = [p for p in dep.pods if p.status == PodStatus.RUNNING]
        assert len(running) > 0

        target = running[0]
        cpu_released = target.cpu_request_millicores
        mem_released = target.memory_request_mb

        cluster_state.remove_pod(target.pod_id)

        # Check cluster-wide resources decreased by the correct amount
        assert total_alloc_cpu() == cpu_before - cpu_released
        assert total_alloc_mem() == mem_before - mem_released

        # Pod should not exist in deployment or any node
        assert target.pod_id not in {p.pod_id for p in dep.pods}
        for node in cluster_state.get_all_nodes():
            assert target.pod_id not in {p.pod_id for p in node.pods}

    def test_remove_pod_raises_keyerror(self, cluster_state):
        """remove_pod should raise for nonexistent pod."""
        with pytest.raises(KeyError, match="nonexistent"):
            cluster_state.remove_pod("nonexistent")

    # ── Pod usage updates ──────────────────────────────────────

    def test_update_pod_usage(self, cluster_state):
        """update_pod_usage should update a running pod's metrics."""
        dep = cluster_state.get_deployment("test-web")
        running = [p for p in dep.pods if p.status == PodStatus.RUNNING]
        assert len(running) > 0

        pod = running[0]
        cluster_state.update_pod_usage(pod.pod_id, cpu_pct=65.5, memory_mb=300.0)
        assert pod.current_cpu_util_pct == 65.5
        assert pod.current_memory_mb == 300.0

    def test_update_pod_usage_clamps_values(self, cluster_state):
        """update_pod_usage should clamp CPU to [0, 100]."""
        dep = cluster_state.get_deployment("test-web")
        running = [p for p in dep.pods if p.status == PodStatus.RUNNING]

        cluster_state.update_pod_usage(running[0].pod_id, cpu_pct=150.0, memory_mb=500.0)
        assert running[0].current_cpu_util_pct == 100.0

        cluster_state.update_pod_usage(running[0].pod_id, cpu_pct=-10.0, memory_mb=500.0)
        assert running[0].current_cpu_util_pct == 0.0

    def test_update_pod_usage_raises_keyerror(self, cluster_state):
        """update_pod_usage should raise for nonexistent pod."""
        with pytest.raises(KeyError, match="nonexistent"):
            cluster_state.update_pod_usage("nonexistent", 50.0, 256.0)

    # ── Scaling ────────────────────────────────────────────────

    def test_scale_up(self, cluster_state):
        """scale_deployment should create and schedule new pods."""
        new_pods = cluster_state.scale_deployment("test-web", 4)
        assert len(new_pods) == 2  # was 2, now 4

        dep = cluster_state.get_deployment("test-web")
        assert len(dep.pods) == 4
        assert dep.target_replicas == 4
        assert all(p.status == PodStatus.RUNNING for p in new_pods)

    def test_scale_down(self, cluster_state):
        """scale_deployment should remove newest pods when scaling down."""
        cluster_state.scale_deployment("test-web", 1)
        dep = cluster_state.get_deployment("test-web")
        assert len(dep.pods) == 1
        assert dep.target_replicas == 1

    def test_scale_to_zero(self, cluster_state):
        """scale_deployment with 0 should remove all pods."""
        cluster_state.scale_deployment("test-web", 0)
        dep = cluster_state.get_deployment("test-web")
        assert len(dep.pods) == 0
        assert dep.target_replicas == 0

    def test_scale_negative_raises(self, cluster_state):
        """scale_deployment with negative should raise ValueError."""
        with pytest.raises(ValueError, match="non-negative"):
            cluster_state.scale_deployment("test-web", -1)

    def test_scale_nonexistent_deployment_raises(self, cluster_state):
        """scale_deployment with nonexistent ID should raise KeyError."""
        with pytest.raises(KeyError):
            cluster_state.scale_deployment("nonexistent", 3)

    # ── Snapshots ─────────────────────────────────────────────

    def test_get_snapshot_structure(self, cluster_state):
        """get_snapshot should return a properly structured ClusterSnapshot."""
        snap = cluster_state.get_snapshot()
        assert snap.snapshot_id is not None
        assert len(snap.nodes) == 2
        assert len(snap.deployments) == 2
        assert snap.total_pods > 0
        assert snap.running_pods > 0
        assert snap.total_cpu_millicores > 0
        assert snap.total_memory_mb > 0
        assert snap.gpu_count > 0

    def test_snapshot_resource_totals(self, cluster_state):
        """Snapshot should accurately reflect resource totals."""
        snap = cluster_state.get_snapshot()
        node = cluster_state.get_all_nodes()[0]
        expected_total = node.total_cpu_millicores * 2
        assert snap.total_cpu_millicores == expected_total

    def test_snapshot_counts_after_scale(self, cluster_state):
        """Snapshot should reflect scaling changes."""
        snap_before = cluster_state.get_snapshot()
        pods_before = snap_before.total_pods

        cluster_state.scale_deployment("test-web", 4)
        snap_after = cluster_state.get_snapshot()
        assert snap_after.total_pods == pods_before + 2

    # ── Edge cases ────────────────────────────────────────────

    def test_no_pending_after_initial_schedule(self, cluster_state):
        """After initialization, no pods should be PENDING (unless resource constrained)."""
        snap = cluster_state.get_snapshot()
        assert snap.pending_pods == 0

    def test_create_pod_unique_ids(self, cluster_state):
        """Each created pod should have a unique ID."""
        ids = set()
        for _ in range(5):
            pod = cluster_state.create_pod("test-web", 100, 128)
            assert pod.pod_id not in ids
            ids.add(pod.pod_id)

    def test_get_deployment_raises_keyerror(self, cluster_state):
        """get_deployment for nonexistent ID should raise KeyError."""
        with pytest.raises(KeyError):
            cluster_state.get_deployment("nonexistent")
