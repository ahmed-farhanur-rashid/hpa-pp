"""
GPU scheduling module.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from shared.db.manager import DatabaseManager
from shared.gpu import GpuAssignment, GpuRebalanceEvent

logger = logging.getLogger(__name__)


class GpuScheduler:
    """Manages GPU assignment and rebalancing for pods.

    Provides bin-pack and spread scheduling strategies with
    contention detection and utilization monitoring.

    Attributes:
        db: Database manager for persistence.
    """

    def __init__(self, db_manager: Optional[DatabaseManager] = None) -> None:
        """Initialize GpuScheduler.

        Args:
            db_manager: Database manager for persistence operations.
        """
        self.db = db_manager

    async def assign_gpus(
        self,
        pod_ids: list[str],
        gpu_specs: list[dict],
        memory_per_pod_mb: int = 4096,
        strategy: str = "bin_pack",
    ) -> list[GpuAssignment]:
        """Assign GPUs to pods using the specified strategy.

        Args:
            pod_ids: List of pod identifiers requesting GPUs.
            gpu_specs: List of dicts, each with keys: gpu_id, node_id,
                total_memory_mb, allocated_memory_mb.
            memory_per_pod_mb: How much GPU memory each pod needs.
            strategy: Scheduling strategy ('bin_pack' or 'spread').

        Returns:
            list[GpuAssignment]: GPU assignments for each pod.

        Raises:
            ValueError: If strategy is not 'bin_pack' or 'spread'.
        """
        if strategy not in ("bin_pack", "spread"):
            raise ValueError(
                f"Unknown strategy '{strategy}', must be 'bin_pack' or 'spread'"
            )

        if not pod_ids:
            return []

        # Work on a mutable copy so we can track allocated_memory_mb changes
        specs = [dict(s) for s in gpu_specs]

        if strategy == "bin_pack":
            # Fullest GPUs first — pack tightly
            specs.sort(key=lambda s: s["allocated_memory_mb"], reverse=True)
        else:
            # Spread: emptiest GPUs first
            specs.sort(key=lambda s: s["allocated_memory_mb"])

        assignments: list[GpuAssignment] = []
        unassigned_pods: list[str] = []

        for pod_id in pod_ids:
            placed = False
            for spec in specs:
                free = spec["total_memory_mb"] - spec["allocated_memory_mb"]
                if free >= memory_per_pod_mb:
                    assignment = GpuAssignment(
                        assignment_id=str(uuid.uuid4()),
                        gpu_id=spec["gpu_id"],
                        pod_id=pod_id,
                        deployment_id=pod_id,
                        memory_allocated_mb=memory_per_pod_mb,
                        compute_allocated_pct=round(
                            (memory_per_pod_mb / spec["total_memory_mb"]) * 100, 2
                        ),
                        effective_utilization_pct=None,
                    )
                    assignments.append(assignment)
                    # Update the local copy to reflect the new allocation
                    spec["allocated_memory_mb"] += memory_per_pod_mb
                    placed = True
                    break
            if not placed:
                unassigned_pods.append(pod_id)

        if unassigned_pods:
            logger.warning(
                "Could not assign GPUs to %d pod(s): %s",
                len(unassigned_pods),
                unassigned_pods,
            )

        return assignments

    async def rebalance(
        self,
        assignments: list[GpuAssignment],
        gpu_specs: list[dict],
        trigger_reason: str = "scheduled",
    ) -> GpuRebalanceEvent:
        """Rebalance GPU assignments to optimize utilization.

        Detects contention, then moves assignments from contended GPUs
        to under-loaded ones.

        Args:
            assignments: Current GPU assignments.
            gpu_specs: List of dicts with gpu_id, node_id, total_memory_mb,
                allocated_memory_mb.
            trigger_reason: Why rebalancing was triggered.

        Returns:
            GpuRebalanceEvent: Rebalance event with before/after state.
        """
        contended = self.detect_contention(assignments, gpu_specs)
        if not contended:
            return GpuRebalanceEvent(
                event_id=str(uuid.uuid4()),
                trigger_reason=trigger_reason,
                assignments_before=len(assignments),
                assignments_after=len(assignments),
                gpus_involved=[],
                duration_ms=0.0,
            )

        # Build a mutable copy of specs keyed by gpu_id
        spec_map: dict[str, dict] = {}
        for s in gpu_specs:
            spec_map[s["gpu_id"]] = dict(s)

        gpus_involved: list[str] = []
        new_assignments: list[GpuAssignment] = []

        for assignment in assignments:
            if assignment.gpu_id in contended:
                # Try to find a new GPU with enough free memory
                moved = False
                for sid, spec in spec_map.items():
                    if sid == assignment.gpu_id:
                        continue
                    if sid in contended:
                        # Don't move to another contended GPU
                        continue
                    free = spec["total_memory_mb"] - spec["allocated_memory_mb"]
                    if free >= assignment.memory_allocated_mb:
                        # Record old GPU as involved
                        if assignment.gpu_id not in gpus_involved:
                            gpus_involved.append(assignment.gpu_id)

                        # Update old spec: free the memory
                        old_spec = spec_map[assignment.gpu_id]
                        old_spec["allocated_memory_mb"] -= (
                            assignment.memory_allocated_mb
                        )

                        # Update new spec: allocate the memory
                        spec["allocated_memory_mb"] += (
                            assignment.memory_allocated_mb
                        )

                        new_assignment = GpuAssignment(
                            assignment_id=assignment.assignment_id,
                            gpu_id=sid,
                            pod_id=assignment.pod_id,
                            deployment_id=assignment.deployment_id,
                            memory_allocated_mb=assignment.memory_allocated_mb,
                            compute_allocated_pct=round(
                                (
                                    assignment.memory_allocated_mb
                                    / spec["total_memory_mb"]
                                )
                                * 100,
                                2,
                            ),
                            effective_utilization_pct=None,
                        )
                        new_assignments.append(new_assignment)

                        if sid not in gpus_involved:
                            gpus_involved.append(sid)

                        moved = True
                        break

                if not moved:
                    # Keep on the original GPU
                    new_assignments.append(assignment)
            else:
                new_assignments.append(assignment)

        return GpuRebalanceEvent(
            event_id=str(uuid.uuid4()),
            trigger_reason=trigger_reason,
            assignments_before=len(assignments),
            assignments_after=len(new_assignments),
            gpus_involved=gpus_involved,
            duration_ms=0.0,
        )

    def detect_contention(
        self,
        assignments: list[GpuAssignment],
        gpu_specs: list[dict],
        threshold_pct: float = 90.0,
    ) -> list[str]:
        """Detect GPU contention based on utilization thresholds.

        Args:
            assignments: Current GPU assignments (unused; specs carry the state).
            gpu_specs: List of dicts with gpu_id, total_memory_mb,
                allocated_memory_mb.
            threshold_pct: Utilization percentage threshold for contention.

        Returns:
            list[str]: List of GPU IDs experiencing contention.
        """
        contended: list[str] = []
        for spec in gpu_specs:
            total = spec["total_memory_mb"]
            if total <= 0:
                continue
            utilization = (spec["allocated_memory_mb"] / total) * 100
            if utilization >= threshold_pct:
                contended.append(spec["gpu_id"])
        return contended

    def get_gpu_utilization(
        self,
        gpu_id: str,
        gpu_specs: list[dict],
    ) -> float:
        """Get utilization percentage for a specific GPU.

        Args:
            gpu_id: GPU identifier to check.
            gpu_specs: List of dicts with gpu_id, total_memory_mb,
                allocated_memory_mb.

        Returns:
            float: Utilization percentage (0.0-100.0).

        Raises:
            ValueError: If gpu_id is not found in gpu_specs.
        """
        for spec in gpu_specs:
            if spec["gpu_id"] == gpu_id:
                total = spec["total_memory_mb"]
                if total <= 0:
                    return 0.0
                return (spec["allocated_memory_mb"] / total) * 100.0
        raise ValueError(f"GPU '{gpu_id}' not found in gpu_specs")
