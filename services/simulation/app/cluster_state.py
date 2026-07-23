"""Cluster state manager for the simulated Kubernetes cluster.

Manages nodes, pods, deployments, and scheduling decisions.
Maintains the authoritative cluster state that the simulation engine
reads and updates each tick.
"""

import uuid
from datetime import datetime, timezone

from shared.simulation import SimulationConfig
from shared.cluster import PodState, NodeState, DeploymentState, ClusterSnapshot
from shared.enums import PodStatus, NodeStatus


class ClusterStateManager:
    """Manages the simulated Kubernetes cluster state.

    Responsible for:
    - Initializing nodes from config
    - Creating and scheduling pods
    - Tracking resource allocation per node
    - Producing cluster snapshots
    - Handling deployment scaling

    Attributes:
        config: Simulation configuration defining cluster topology.
        nodes: Dict of node_id -> NodeState.
        deployments: Dict of deployment_id -> DeploymentState.

    TODO:
        - Implement bin-packing scheduling algorithm
        - Add node affinity and taint/toleration support
        - Support GPU device assignment
    """

    def __init__(self, config: SimulationConfig) -> None:
        """Initialize the cluster state manager.

        Args:
            config: Simulation configuration with node count, resources, etc.

        TODO:
            - Validate config has at least one deployment
            - Pre-compute resource capacity totals
        """
        self.config = config
        self.nodes: dict[str, NodeState] = {}
        self.deployments: dict[str, DeploymentState] = {}
        self._pod_counter: int = 0
        self._node_counter: int = 0
        self._gpu_counter: int = 0
        self._node_gpu_alloc: dict[str, dict[str, str | None]] = {}
        self.blocked_nodes: set[str] = set()
        self.blocked_gpus: set[str] = set()

    def initialize(self) -> None:
        """Create initial cluster state from config.

        Creates all nodes with their full resource capacity and
        creates initial pods for each deployment.

        TODO:
            - Create N nodes based on config.node_count
            - Create GPU devices per node
            - Create initial pods for each deployment
            - Schedule initial pods across nodes
        """
        for i in range(self.config.node_count):
            node_id = f"node-{i}"
            self._node_counter += 1
            self.create_node(
                node_id=node_id,
                cpu_millicores=self.config.cpu_per_node_millicores,
                memory_mb=self.config.memory_per_node_mb,
                gpu_count=self.config.gpus_per_node,
                gpu_memory_mb=self.config.gpu_memory_per_device_mb,
            )

        for spec in self.config.deployments:
            deployment = DeploymentState(
                deployment_id=spec.deployment_id,
                current_replicas=0,
                target_replicas=spec.initial_replicas,
                available_replicas=0,
                pods=[],
                cpu_request_millicores=spec.cpu_request_millicores,
                memory_request_mb=spec.memory_request_mb,
                requires_gpu=spec.gpu_required,
            )
            self.deployments[spec.deployment_id] = deployment

            for _ in range(spec.initial_replicas):
                gpu_request = spec.gpu_memory_request_mb if spec.gpu_required else 0
                pod = self.create_pod(
                    deployment_id=spec.deployment_id,
                    cpu_request=spec.cpu_request_millicores,
                    memory_request_mb=spec.memory_request_mb,
                    gpu_request_mb=gpu_request,
                )
                self.schedule_pod(pod)

    def create_node(
        self,
        node_id: str,
        cpu_millicores: int,
        memory_mb: int,
        gpu_count: int,
        gpu_memory_mb: int,
    ) -> NodeState:
        """Create a new node with given resource capacity.

        Args:
            node_id: Unique identifier for the node.
            cpu_millicores: Total CPU capacity in millicores.
            memory_mb: Total memory capacity in megabytes.
            gpu_count: Number of GPU devices on this node.
            gpu_memory_mb: Memory per GPU device in megabytes.

        Returns:
            NodeState: The newly created node state.

        TODO:
            - Generate GPU device IDs
            - Add node to internal tracking dict
        """
        gpu_ids: list[str] = []
        gpu_alloc: dict[str, str | None] = {}

        for g in range(gpu_count):
            gpu_id = f"{node_id}-gpu-{g}"
            gpu_ids.append(gpu_id)
            gpu_alloc[gpu_id] = None
            self._gpu_counter += 1

        total_gpu_memory = gpu_count * gpu_memory_mb

        node = NodeState(
            node_id=node_id,
            status=NodeStatus.READY,
            total_cpu_millicores=cpu_millicores,
            total_memory_mb=memory_mb,
            allocated_cpu_millicores=0,
            allocated_memory_mb=0,
            allocated_gpu_memory_mb=0,
            gpu_ids=gpu_ids,
            total_gpu_memory_mb=total_gpu_memory,
            pods=[],
        )

        self.nodes[node_id] = node
        self._node_gpu_alloc[node_id] = gpu_alloc

        return node

    def create_pod(
        self,
        deployment_id: str,
        cpu_request: int,
        memory_request_mb: int,
        gpu_request_mb: int = 0,
    ) -> PodState:
        """Create a new pod for a deployment.

        Args:
            deployment_id: Deployment that owns this pod.
            cpu_request: CPU request in millicores.
            memory_request_mb: Memory request in megabytes.
            gpu_request_mb: GPU memory request in megabytes (0 = no GPU).

        Returns:
            PodState: The newly created pod in PENDING status.

        TODO:
            - Generate unique pod ID
            - Add pod to deployment's pod list
        """
        pod_id = f"{deployment_id}-pod-{self._pod_counter}"
        self._pod_counter += 1

        pod = PodState(
            pod_id=pod_id,
            deployment_id=deployment_id,
            status=PodStatus.PENDING,
            node_id=None,
            cpu_request_millicores=cpu_request,
            memory_request_mb=memory_request_mb,
            gpu_memory_request_mb=gpu_request_mb,
        )

        self.deployments[deployment_id].pods.append(pod)

        return pod

    def schedule_pod(self, pod: PodState) -> str | None:
        """Attempt to schedule a pod onto a node.

        Uses simple bin-packing: find the first node with enough
        free CPU, memory, and GPU resources.

        Args:
            pod: Pod to schedule (must be in PENDING status).

        Returns:
            str | None: Node ID if scheduled successfully, None if no fit.

        TODO:
            - Implement least-fit or balanced scheduling
            - Consider GPU requirements for scheduling
            - Update node allocated resources on success
        """
        if pod.status != PodStatus.PENDING:
            return None

        for node_id, node in self.nodes.items():
            if node.status != NodeStatus.READY:
                continue
            if node_id in self.blocked_nodes:
                continue

            free_cpu = node.total_cpu_millicores - node.allocated_cpu_millicores
            if free_cpu < pod.cpu_request_millicores:
                continue

            free_memory = node.total_memory_mb - node.allocated_memory_mb
            if free_memory < pod.memory_request_mb:
                continue

            if pod.gpu_memory_request_mb > 0:
                gpu_found = False
                for gpu_id, assigned_pod_id in self._node_gpu_alloc[node_id].items():
                    if assigned_pod_id is None:
                        pod.gpu_id = gpu_id
                        self._node_gpu_alloc[node_id][gpu_id] = pod.pod_id
                        node.allocated_gpu_memory_mb += pod.gpu_memory_request_mb
                        gpu_found = True
                        break
                if not gpu_found:
                    continue

            pod.node_id = node_id
            pod.status = PodStatus.RUNNING
            node.allocated_cpu_millicores += pod.cpu_request_millicores
            node.allocated_memory_mb += pod.memory_request_mb
            node.pods.append(pod)

            deployment = self.deployments[pod.deployment_id]
            deployment.current_replicas += 1
            deployment.available_replicas += 1

            return node_id

        return None

    def remove_pod(self, pod_id: str) -> None:
        """Remove a pod from the cluster.

        Frees resources on the node it was scheduled on and
        removes it from its deployment's pod list.

        Args:
            pod_id: ID of the pod to remove.

        Raises:
            KeyError: If pod_id not found.

        TODO:
            - Free node CPU/memory/GPU allocations
            - Remove from deployment pod list
            - Handle GPU device release
        """
        target_pod: PodState | None = None
        target_deployment: DeploymentState | None = None

        for deployment in self.deployments.values():
            for pod in deployment.pods:
                if pod.pod_id == pod_id:
                    target_pod = pod
                    target_deployment = deployment
                    break
            if target_pod is not None:
                break

        if target_pod is None or target_deployment is None:
            raise KeyError(f"Pod '{pod_id}' not found")

        if target_pod.node_id is not None:
            node = self.nodes[target_pod.node_id]
            node.allocated_cpu_millicores -= target_pod.cpu_request_millicores
            node.allocated_memory_mb -= target_pod.memory_request_mb
            node.pods = [p for p in node.pods if p.pod_id != pod_id]

            if target_pod.gpu_id is not None:
                node.allocated_gpu_memory_mb -= target_pod.gpu_memory_request_mb
                self._node_gpu_alloc[target_pod.node_id][target_pod.gpu_id] = None
                target_pod.gpu_id = None

            if target_pod.status == PodStatus.RUNNING:
                target_deployment.current_replicas -= 1
                target_deployment.available_replicas -= 1
            elif target_pod.status == PodStatus.PENDING:
                target_deployment.current_replicas -= 1
        else:
            target_deployment.current_replicas -= 1

        target_deployment.pods = [
            p for p in target_deployment.pods if p.pod_id != pod_id
        ]

    def block_node(self, node_id: str) -> list[PodState]:
        """Mark a node as blocked and evict all its pods.

        Evicted pods are returned so callers can store them; they
        become Pending and can be re-scheduled when the node unblocks.

        Args:
            node_id: Node to block.

        Returns:
            list[PodState]: Pods that were evicted from this node.
        """
        if node_id not in self.nodes:
            raise KeyError(f"Node {node_id} not found")
        self.blocked_nodes.add(node_id)
        node = self.nodes[node_id]
        evicted = list(node.pods)
        for pod in evicted:
            self.remove_pod(pod.pod_id)
        node.pods = []
        node.allocated_cpu_millicores = 0
        node.allocated_memory_mb = 0
        return evicted

    def unblock_node(self, node_id: str) -> None:
        """Remove a node from the blocked set, allowing scheduling again."""
        self.blocked_nodes.discard(node_id)

    def block_gpu(self, gpu_id: str) -> None:
        """Mark a GPU device as unavailable."""
        self.blocked_gpus.add(gpu_id)

    def unblock_gpu(self, gpu_id: str) -> None:
        """Mark a GPU device as available again."""
        self.blocked_gpus.discard(gpu_id)

    def update_pod_usage(
        self,
        pod_id: str,
        cpu_pct: float,
        memory_mb: float,
        gpu_pct: float | None = None,
    ) -> None:
        """Update current resource usage of a running pod.

        Args:
            pod_id: ID of the pod to update.
            cpu_pct: Current CPU utilization percentage (0-100).
            memory_mb: Current memory usage in megabytes.
            gpu_pct: Current GPU utilization percentage (0-100, None if no GPU).

        Raises:
            KeyError: If pod_id not found.

        TODO:
            - Validate pod is in RUNNING status
            - Clamp values to valid ranges
        """
        target_pod: PodState | None = None

        for deployment in self.deployments.values():
            for pod in deployment.pods:
                if pod.pod_id == pod_id:
                    target_pod = pod
                    break
            if target_pod is not None:
                break

        if target_pod is None:
            raise KeyError(f"Pod '{pod_id}' not found")

        if target_pod.status != PodStatus.RUNNING:
            return

        target_pod.current_cpu_util_pct = max(0.0, min(100.0, cpu_pct))
        target_pod.current_memory_mb = max(0.0, memory_mb)

        if gpu_pct is not None and target_pod.gpu_id is not None:
            target_pod.current_gpu_util_pct = max(0.0, min(100.0, gpu_pct))

    def get_snapshot(self) -> ClusterSnapshot:
        """Produce a point-in-time snapshot of the entire cluster.

        Returns:
            ClusterSnapshot: Complete cluster state including nodes,
                deployments, and aggregate counts.

        TODO:
            - Compute aggregate pod counts
            - Calculate average GPU utilization
            - Generate unique snapshot ID
        """
        total_pods = 0
        running_pods = 0
        pending_pods = 0

        for deployment in self.deployments.values():
            for pod in deployment.pods:
                total_pods += 1
                if pod.status == PodStatus.RUNNING:
                    running_pods += 1
                elif pod.status == PodStatus.PENDING:
                    pending_pods += 1

        gpu_count = 0
        gpu_util_sum = 0.0
        gpu_util_count = 0

        for node in self.nodes.values():
            gpu_count += len(node.gpu_ids)

        for deployment in self.deployments.values():
            for pod in deployment.pods:
                if pod.current_gpu_util_pct is not None:
                    gpu_util_sum += pod.current_gpu_util_pct
                    gpu_util_count += 1

        gpu_util_avg = (gpu_util_sum / gpu_util_count) if gpu_util_count > 0 else None

        total_cpu = sum(n.total_cpu_millicores for n in self.nodes.values())
        allocated_cpu = sum(n.allocated_cpu_millicores for n in self.nodes.values())
        total_memory = sum(n.total_memory_mb for n in self.nodes.values())
        allocated_memory = sum(n.allocated_memory_mb for n in self.nodes.values())

        return ClusterSnapshot(
            snapshot_id=str(uuid.uuid4()),
            simulated_time_utc=datetime.now(timezone.utc).isoformat(),
            nodes=list(self.nodes.values()),
            deployments=list(self.deployments.values()),
            total_pods=total_pods,
            running_pods=running_pods,
            pending_pods=pending_pods,
            gpu_count=gpu_count,
            gpu_utilization_avg_pct=gpu_util_avg,
            total_cpu_millicores=total_cpu,
            allocated_cpu_millicores=allocated_cpu,
            total_memory_mb=total_memory,
            allocated_memory_mb=allocated_memory,
        )

    def get_deployment(self, deployment_id: str) -> DeploymentState:
        """Get state of a specific deployment.

        Args:
            deployment_id: Deployment to look up.

        Returns:
            DeploymentState: Current deployment state.

        Raises:
            KeyError: If deployment_id not found.
        """
        if deployment_id not in self.deployments:
            raise KeyError(f"Deployment '{deployment_id}' not found")
        return self.deployments[deployment_id]

    def get_node(self, node_id: str) -> NodeState:
        """Get state of a specific node.

        Args:
            node_id: Node to look up.

        Returns:
            NodeState: Current node state.

        Raises:
            KeyError: If node_id not found.
        """
        if node_id not in self.nodes:
            raise KeyError(f"Node '{node_id}' not found")
        return self.nodes[node_id]

    def get_all_nodes(self) -> list[NodeState]:
        """Get list of all node states.

        Returns:
            list[NodeState]: All nodes in the cluster.
        """
        return list(self.nodes.values())

    def get_all_deployments(self) -> list[DeploymentState]:
        """Get list of all deployment states.

        Returns:
            list[DeploymentState]: All deployments in the cluster.
        """
        return list(self.deployments.values())

    def scale_deployment(
        self,
        deployment_id: str,
        target_replicas: int,
    ) -> list[PodState]:
        """Scale a deployment to the target replica count.

        Creates or removes pods to match the target count.
        New pods are attempted to be scheduled immediately.

        Args:
            deployment_id: Deployment to scale.
            target_replicas: Desired number of replicas.

        Returns:
            list[PodState]: Newly created pods (empty if scaling down).

        Raises:
            KeyError: If deployment_id not found.
            ValueError: If target_replicas < 0.

        TODO:
            - Handle scale-down by removing newest pods
            - Attempt scheduling for newly created pods
            - Return list of created (unscheduled) pods
        """
        if deployment_id not in self.deployments:
            raise KeyError(f"Deployment '{deployment_id}' not found")

        if target_replicas < 0:
            raise ValueError("target_replicas must be non-negative")

        deployment = self.deployments[deployment_id]
        current_count = len(deployment.pods)

        if target_replicas == current_count:
            return []

        new_pods: list[PodState] = []

        if target_replicas > current_count:
            diff = target_replicas - current_count

            spec = None
            for s in self.config.deployments:
                if s.deployment_id == deployment_id:
                    spec = s
                    break

            if spec is None:
                raise KeyError(f"Deployment spec '{deployment_id}' not found in config")

            for _ in range(diff):
                gpu_request = spec.gpu_memory_request_mb if spec.gpu_required else 0
                pod = self.create_pod(
                    deployment_id=deployment_id,
                    cpu_request=spec.cpu_request_millicores,
                    memory_request_mb=spec.memory_request_mb,
                    gpu_request_mb=gpu_request,
                )
                self.schedule_pod(pod)
                new_pods.append(pod)
        else:
            diff = current_count - target_replicas
            pods_to_remove = deployment.pods[-diff:]
            for pod in pods_to_remove:
                self.remove_pod(pod.pod_id)

        deployment.target_replicas = target_replicas
        return new_pods
