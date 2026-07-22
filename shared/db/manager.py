"""DatabaseManager — singleton-style database access for all services.

Provides thread-safe CRUD operations with Pydantic validation
on all read/write operations. Every service uses this class.

RULE 1.3: All data is validated at the boundary via Pydantic models
before being written or returned from the database.
"""

import sqlite3
from pathlib import Path
from typing import Any

from shared.db.init import init_db


class DatabaseManager:
    """Manages database connections and provides CRUD operations.

    Wraps sqlite3 with Pydantic validation on all entries/exits.
    Uses WAL mode for concurrent reading from multiple services.

    SOLID: Single responsibility — database access only.
    No business logic, no data transformation beyond serialization.

    Usage:
        db = DatabaseManager()
        db.connect()
        samples = db.query_metrics("web-app", limit=100)
        db.close()
    """

    def __init__(self, db_path: Path | None = None) -> None:
        """Initialise the DatabaseManager.

        Args:
            db_path: Path to the SQLite database file.
                Uses default path from init.get_db_path() if None.

        TODO:
            - Implement connection pooling for production
            - Add retry logic for concurrent write conflicts
        """
        ...

    def connect(self) -> None:
        """Open a connection to the database.

        Enables WAL mode and foreign keys.
        Creates database and tables if they don't exist.

        Raises:
            sqlite3.Error: If connection fails.
        """
        ...

    def close(self) -> None:
        """Close the database connection.

        Commits any pending transactions before closing.
        Safe to call multiple times.
        """
        ...

    @property
    def connection(self) -> sqlite3.Connection:
        """Get the active connection.

        Raises:
            RuntimeError: If connect() has not been called.
        """
        ...

    # ── Generic helpers ───────────────────────────────────────

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a SQL query with parameters.

        Args:
            sql: SQL query string.
            params: Query parameters (positional).

        Returns:
            sqlite3.Cursor: The cursor after execution.

        TODO:
            - Log all queries with duration for debugging
            - Add query timeout safeguard
        """
        ...

    def fetchone(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        """Fetch one row as a dictionary.

        Returns:
            dict with column names as keys, or None if no rows.
        """
        ...

    def fetchall(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        """Fetch all rows as a list of dictionaries."""
        ...

    def insert(self, table: str, data: dict[str, Any]) -> int:
        """Insert a row and return its ID.

        Args:
            table: Table name.
            data: Column-value mapping.

        Returns:
            int: The rowid of the inserted row.

        TODO:
            - Validate data against the corresponding Pydantic model
            - Handle INSERT OR REPLACE for upsert patterns
        """
        ...

    def insert_many(self, table: str, data: list[dict[str, Any]]) -> list[int]:
        """Insert multiple rows efficiently.

        Uses executemany for batch performance.
        Returns list of inserted row IDs.
        """
        ...

    # ── Metric queries ────────────────────────────────────────

    def query_metrics(
        self,
        deployment_id: str | None = None,
        from_time: str | None = None,
        to_time: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query metric samples with optional filters.

        Args:
            deployment_id: Filter by deployment (None = all deployments).
            from_time: ISO 8601 start time (None = no lower bound).
            to_time: ISO 8601 end time (None = no upper bound).
            limit: Maximum rows to return.

        Returns:
            List of metric_samples row dicts.

        TODO:
            - Add pagination support
            - Add aggregation (avg, max, min per time bucket)
        """
        ...

    def query_latest_metrics(
        self,
        deployment_id: str | None = None,
        count: int = 10,
    ) -> list[dict[str, Any]]:
        """Get the most recent metric samples."""
        ...

    # ── Forecast queries ──────────────────────────────────────

    def insert_forecast_windows(
        self, records: list[dict[str, Any]]
    ) -> list[int]:
        """Insert forecast window records.

        Validates each record against ForecastWindow schema
        before inserting.

        TODO:
            - Batch validate with Pydantic before insert
        """
        ...

    def query_latest_forecast(
        self, deployment_id: str
    ) -> dict[str, Any] | None:
        """Get the most recent forecast for a deployment."""
        ...

    def query_forecast_history(
        self, deployment_id: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Get forecast history for a deployment."""
        ...

    # ── Scaling decision queries ──────────────────────────────

    def insert_scaling_decision(
        self, decision: dict[str, Any]
    ) -> int:
        """Insert a scaling decision record."""
        ...

    def query_scaling_decisions(
        self, deployment_id: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Get scaling decisions for a deployment."""
        ...

    def query_latest_decision(
        self, deployment_id: str
    ) -> dict[str, Any] | None:
        """Get the most recent scaling decision."""
        ...

    # ── GPU queries ──────────────────────────────────────────

    def insert_gpu_assignments(
        self, assignments: list[dict[str, Any]]
    ) -> list[int]:
        """Insert GPU assignment records."""
        ...

    def query_gpu_assignments(
        self, deployment_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Query GPU assignments, optionally filtered by deployment."""
        ...

    # ── Cluster snapshot queries ─────────────────────────────

    def insert_cluster_snapshot(
        self, snapshot: dict[str, Any]
    ) -> int:
        """Insert a cluster snapshot record."""
        ...

    def query_latest_snapshot(self) -> dict[str, Any] | None:
        """Get the most recent cluster snapshot."""
        ...

    # ── Configuration queries ─────────────────────────────────

    def get_scaling_config(
        self, deployment_id: str
    ) -> dict[str, Any] | None:
        """Get the scaling configuration for a deployment."""
        ...

    def upsert_scaling_config(
        self, config: dict[str, Any]
    ) -> None:
        """Insert or update a scaling configuration."""
        ...
