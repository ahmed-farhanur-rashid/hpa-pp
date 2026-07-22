"""Convenience query functions — thin wrappers around DatabaseManager.

These module-level functions accept a DatabaseManager and delegate
to its methods. They exist so that services can import individual
query functions without needing the DatabaseManager class directly.

All functions are stubs — the actual logic lives in DatabaseManager.
"""

from shared.db.manager import DatabaseManager


def insert_metric_samples(
    db: DatabaseManager,
    samples: list[dict],
) -> list[int]:
    """Insert a batch of metric samples.

    Args:
        db: DatabaseManager instance.
        samples: List of MetricSample-compatible dicts.

    Returns:
        list[int]: Row IDs of inserted records.

    TODO:
        - Validate each dict against MetricSample Pydantic model.
    """
    ...


def query_metrics(
    db: DatabaseManager,
    deployment_id: str | None = None,
    from_time: str | None = None,
    to_time: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Query metric samples with filters."""
    ...


def query_latest_metrics(
    db: DatabaseManager,
    deployment_id: str | None = None,
    count: int = 10,
) -> list[dict]:
    """Get the N most recent metric samples."""
    ...


def insert_forecast_windows(
    db: DatabaseManager,
    records: list[dict],
) -> list[int]:
    """Insert forecast window records."""
    ...


def query_latest_forecast(
    db: DatabaseManager,
    deployment_id: str,
) -> dict | None:
    """Get the most recent forecast for a deployment."""
    ...


def query_forecast_history(
    db: DatabaseManager,
    deployment_id: str,
    limit: int = 100,
) -> list[dict]:
    """Get forecast history."""
    ...


def insert_scaling_decision(
    db: DatabaseManager,
    decision: dict,
) -> int:
    """Insert a scaling decision record."""
    ...


def query_scaling_decisions(
    db: DatabaseManager,
    deployment_id: str,
    limit: int = 100,
) -> list[dict]:
    """Get scaling decisions for a deployment."""
    ...


def query_latest_decision(
    db: DatabaseManager,
    deployment_id: str,
) -> dict | None:
    """Get the most recent scaling decision."""
    ...


def insert_gpu_assignments(
    db: DatabaseManager,
    assignments: list[dict],
) -> list[int]:
    """Insert GPU assignment records."""
    ...


def query_gpu_assignments(
    db: DatabaseManager,
    deployment_id: str | None = None,
) -> list[dict]:
    """Query GPU assignments."""
    ...


def insert_cluster_snapshot(
    db: DatabaseManager,
    snapshot: dict,
) -> int:
    """Insert a cluster snapshot."""
    ...


def query_latest_snapshot(
    db: DatabaseManager,
) -> dict | None:
    """Get the most recent cluster snapshot."""
    ...
