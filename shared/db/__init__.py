"""Database layer for HPA++.

All services use this module for database access.
Single source of truth for all table schemas and queries.
"""

from shared.db.init import get_db_path, init_db
from shared.db.manager import DatabaseManager
from shared.db.queries import (
    insert_metric_samples,
    query_metrics,
    query_latest_metrics,
    insert_forecast_windows,
    query_latest_forecast,
    query_forecast_history,
    insert_scaling_decision,
    query_scaling_decisions,
    query_latest_decision,
    insert_gpu_assignments,
    query_gpu_assignments,
    insert_cluster_snapshot,
    query_latest_snapshot,
)

__all__ = [
    "get_db_path",
    "init_db",
    "DatabaseManager",
    "insert_metric_samples",
    "query_metrics",
    "query_latest_metrics",
    "insert_forecast_windows",
    "query_latest_forecast",
    "query_forecast_history",
    "insert_scaling_decision",
    "query_scaling_decisions",
    "query_latest_decision",
    "insert_gpu_assignments",
    "query_gpu_assignments",
    "insert_cluster_snapshot",
    "query_latest_snapshot",
]
