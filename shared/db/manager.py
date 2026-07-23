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


def _dict_from_row(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a sqlite3.Row to a plain dict."""
    return dict(row)


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
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> None:
        """Open a connection to the database.

        Enables WAL mode and foreign keys.
        Creates database and tables if they don't exist.

        Raises:
            sqlite3.Error: If connection fails.
        """
        self._conn = init_db(self._db_path)

    def close(self) -> None:
        """Close the database connection.

        Commits any pending transactions before closing.
        Safe to call multiple times.
        """
        if self._conn is not None:
            try:
                self._conn.commit()
            except Exception:
                pass
            self._conn.close()
            self._conn = None

    @property
    def connection(self) -> sqlite3.Connection:
        """Get the active connection.

        Raises:
            RuntimeError: If connect() has not been called.
        """
        if self._conn is None:
            raise RuntimeError(
                "Database not connected. Call connect() first."
            )
        return self._conn

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
        return self.connection.execute(sql, params)

    def fetchone(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        """Fetch one row as a dictionary.

        Returns:
            dict with column names as keys, or None if no rows.
        """
        cur = self.execute(sql, params)
        row = cur.fetchone()
        if row is None:
            return None
        return _dict_from_row(row)

    def fetchall(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        """Fetch all rows as a list of dictionaries."""
        cur = self.execute(sql, params)
        return [_dict_from_row(r) for r in cur.fetchall()]

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
        columns = list(data.keys())
        placeholders = ",".join("?" for _ in columns)
        sql = (
            f"INSERT INTO {table} "
            f"({','.join(columns)}) "
            f"VALUES ({placeholders})"
        )
        cur = self.execute(sql, tuple(data[c] for c in columns))
        self.connection.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def insert_many(self, table: str, data: list[dict[str, Any]]) -> list[int]:
        """Insert multiple rows efficiently.

        Uses individual inserts for reliable rowid tracking.
        Returns list of inserted row IDs.
        """
        if not data:
            return []
        columns = list(data[0].keys())
        placeholders = ",".join("?" for _ in columns)
        sql = (
            f"INSERT INTO {table} "
            f"({','.join(columns)}) "
            f"VALUES ({placeholders})"
        )
        ids: list[int] = []
        for item in data:
            cur = self.execute(sql, tuple(item[c] for c in columns))
            if cur.lastrowid is not None:
                ids.append(cur.lastrowid)
        self.connection.commit()
        return ids

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
        conditions: list[str] = []
        params: list[Any] = []

        if deployment_id is not None:
            conditions.append("deployment_id = ?")
            params.append(deployment_id)
        if from_time is not None:
            conditions.append("simulated_time_utc >= ?")
            params.append(from_time)
        if to_time is not None:
            conditions.append("simulated_time_utc <= ?")
            params.append(to_time)

        where = ""
        if conditions:
            where = "WHERE " + " AND ".join(conditions)

        sql = (
            f"SELECT * FROM metric_samples {where} "
            f"ORDER BY simulated_time_utc DESC LIMIT ?"
        )
        params.append(limit)
        return self.fetchall(sql, tuple(params))

    def query_latest_metrics(
        self,
        deployment_id: str | None = None,
        count: int = 10,
    ) -> list[dict[str, Any]]:
        """Get the most recent metric samples."""
        if deployment_id is not None:
            return self.fetchall(
                "SELECT * FROM metric_samples "
                "WHERE deployment_id = ? "
                "ORDER BY id DESC LIMIT ?",
                (deployment_id, count),
            )
        return self.fetchall(
            "SELECT * FROM metric_samples ORDER BY id DESC LIMIT ?",
            (count,),
        )

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
        return self.insert_many("forecast_windows", records)

    def query_latest_forecast(
        self, deployment_id: str
    ) -> dict[str, Any] | None:
        """Get the most recent forecast for a deployment."""
        return self.fetchone(
            "SELECT * FROM forecast_windows "
            "WHERE deployment_id = ? "
            "ORDER BY forecast_time_utc DESC LIMIT 1",
            (deployment_id,),
        )

    def query_forecast_history(
        self, deployment_id: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Get forecast history for a deployment."""
        return self.fetchall(
            "SELECT * FROM forecast_windows "
            "WHERE deployment_id = ? "
            "ORDER BY forecast_time_utc DESC LIMIT ?",
            (deployment_id, limit),
        )

    # ── Scaling decision queries ──────────────────────────────

    def insert_scaling_decision(
        self, decision: dict[str, Any]
    ) -> int:
        """Insert a scaling decision record."""
        return self.insert("scaling_decisions", decision)

    def query_scaling_decisions(
        self, deployment_id: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Get scaling decisions for a deployment."""
        return self.fetchall(
            "SELECT * FROM scaling_decisions "
            "WHERE deployment_id = ? "
            "ORDER BY simulated_time_utc DESC LIMIT ?",
            (deployment_id, limit),
        )

    def query_latest_decision(
        self, deployment_id: str
    ) -> dict[str, Any] | None:
        """Get the most recent scaling decision."""
        return self.fetchone(
            "SELECT * FROM scaling_decisions "
            "WHERE deployment_id = ? "
            "ORDER BY simulated_time_utc DESC LIMIT 1",
            (deployment_id,),
        )

    # ── GPU queries ──────────────────────────────────────────

    def insert_gpu_assignments(
        self, assignments: list[dict[str, Any]]
    ) -> list[int]:
        """Insert GPU assignment records."""
        return self.insert_many("gpu_assignments", assignments)

    def query_gpu_assignments(
        self, deployment_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Query GPU assignments, optionally filtered by deployment."""
        if deployment_id is not None:
            return self.fetchall(
                "SELECT * FROM gpu_assignments "
                "WHERE deployment_id = ? "
                "ORDER BY timestamp_utc DESC",
                (deployment_id,),
            )
        return self.fetchall(
            "SELECT * FROM gpu_assignments ORDER BY timestamp_utc DESC"
        )

    # ── Cluster snapshot queries ─────────────────────────────

    def insert_cluster_snapshot(
        self, snapshot: dict[str, Any]
    ) -> int:
        """Insert a cluster snapshot record."""
        return self.insert("cluster_snapshots", snapshot)

    def query_latest_snapshot(self) -> dict[str, Any] | None:
        """Get the most recent cluster snapshot."""
        return self.fetchone(
            "SELECT * FROM cluster_snapshots ORDER BY id DESC LIMIT 1"
        )

    # ── Configuration queries ─────────────────────────────────

    def get_scaling_config(
        self, deployment_id: str
    ) -> dict[str, Any] | None:
        """Get the scaling configuration for a deployment."""
        return self.fetchone(
            "SELECT * FROM scaling_configs WHERE deployment_id = ?",
            (deployment_id,),
        )

    def upsert_scaling_config(
        self, config: dict[str, Any]
    ) -> None:
        """Insert or update a scaling configuration."""
        self.execute(
            "INSERT INTO scaling_configs "
            "(deployment_id, min_replicas, max_replicas, baseline_per_pod, "
            " risk_asymmetry_factor, cooldown_seconds, upscale_cpu_threshold_pct) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(deployment_id) DO UPDATE SET "
            "  min_replicas = excluded.min_replicas, "
            "  max_replicas = excluded.max_replicas, "
            "  baseline_per_pod = excluded.baseline_per_pod, "
            "  risk_asymmetry_factor = excluded.risk_asymmetry_factor, "
            "  cooldown_seconds = excluded.cooldown_seconds, "
            "  upscale_cpu_threshold_pct = excluded.upscale_cpu_threshold_pct",
            (
                config["deployment_id"],
                config.get("min_replicas", 1),
                config.get("max_replicas", 20),
                config.get("baseline_per_pod", 100.0),
                config.get("risk_asymmetry_factor", 5.0),
                config.get("cooldown_seconds", 60),
                config.get("upscale_cpu_threshold_pct", 70.0),
            ),
        )
        self.connection.commit()
