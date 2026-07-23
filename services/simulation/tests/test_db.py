"""Tests for the database layer (init.py + DatabaseManager)."""

from __future__ import annotations

from pathlib import Path

import pytest


class TestDatabaseInit:
    """Test get_db_path and init_db."""

    def test_get_db_path_default(self, monkeypatch):
        """Default path should be under data/ relative to shared."""
        monkeypatch.delenv("HPAP_DB_PATH", raising=False)
        from shared.db.init import get_db_path, DEFAULT_DB_PATH

        path = get_db_path()
        assert path == DEFAULT_DB_PATH

    def test_get_db_path_env_override(self, monkeypatch):
        """HPAP_DB_PATH env var should override default."""
        from shared.db.init import get_db_path

        monkeypatch.setenv("HPAP_DB_PATH", "/tmp/test_hpap/test.db")
        path = get_db_path()
        assert path == Path("/tmp/test_hpap/test.db")

    def test_init_db_creates_tables(self, tmp_path):
        """init_db should create all expected tables."""
        from shared.db.init import init_db

        db_path = tmp_path / "test.db"
        conn = init_db(db_path)
        try:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
            table_names = {r["name"] for r in tables}
            expected = {
                "metric_samples",
                "forecast_windows",
                "scaling_decisions",
                "gpu_assignments",
                "cluster_snapshots",
                "scaling_configs",
                "simulation_configs",
            }
            for t in expected:
                assert t in table_names, f"Missing table: {t}"
        finally:
            conn.close()


class TestDatabaseManager:
    """Test DatabaseManager CRUD operations."""

    def test_connect_and_close(self):
        """Connect and close should work without errors."""
        from shared.db.manager import DatabaseManager

        db = DatabaseManager(db_path=Path(":memory:"))
        db.connect()
        db.close()
        # Second close should be safe
        db.close()

    def test_connection_property_raises(self):
        """Accessing connection before connect should raise."""
        from shared.db.manager import DatabaseManager

        db = DatabaseManager()
        with pytest.raises(RuntimeError, match="not connected"):
            _ = db.connection

    def test_insert_and_query(self):
        """Insert a metric sample then query it back."""
        from shared.db.manager import DatabaseManager

        db = DatabaseManager(db_path=Path(":memory:"))
        db.connect()

        row_id = db.insert("metric_samples", {
            "timestamp_utc": "2026-01-01T00:00:00Z",
            "simulated_time_utc": "2026-01-01T00:00:00Z",
            "deployment_id": "test-app",
            "cpu_utilization_pct": 45.5,
            "memory_usage_mb": 256.0,
            "requests_per_second": 100.0,
            "gpu_utilization_pct": None,
            "gpu_memory_used_mb": None,
            "latency_ms": 12.3,
            "pod_count": 3,
        })
        assert isinstance(row_id, int)
        assert row_id > 0

        rows = db.query_metrics(deployment_id="test-app", limit=10)
        assert len(rows) == 1
        assert rows[0]["deployment_id"] == "test-app"
        assert rows[0]["cpu_utilization_pct"] == 45.5

        db.close()

    def test_insert_many(self):
        """Batch insert should return correct row IDs."""
        from shared.db.manager import DatabaseManager

        db = DatabaseManager(db_path=Path(":memory:"))
        db.connect()

        rows = [
            {
                "timestamp_utc": "2026-01-01T00:00:00Z",
                "simulated_time_utc": "2026-01-01T00:00:00Z",
                "deployment_id": "test-app",
                "cpu_utilization_pct": 30.0 + i * 10,
                "memory_usage_mb": 200.0 + i * 10,
                "requests_per_second": 80.0 + i * 5,
                "gpu_utilization_pct": None,
                "gpu_memory_used_mb": None,
                "latency_ms": 10.0,
                "pod_count": 2,
            }
            for i in range(3)
        ]
        ids = db.insert_many("metric_samples", rows)
        assert len(ids) == 3
        assert ids == [1, 2, 3]

        db.close()

    def test_fetchone_and_fetchall(self):
        """fetchone returns None for empty results, fetchall returns list."""
        from shared.db.manager import DatabaseManager

        db = DatabaseManager(db_path=Path(":memory:"))
        db.connect()

        assert db.fetchone("SELECT * FROM metric_samples") is None
        assert db.fetchall("SELECT * FROM metric_samples") == []

        db.close()

    def test_cluster_snapshot_lifecycle(self):
        """Insert a cluster snapshot and query it back."""
        from shared.db.manager import DatabaseManager

        db = DatabaseManager(db_path=Path(":memory:"))
        db.connect()

        snap_id = db.insert_cluster_snapshot({
            "timestamp_utc": "2026-01-01T00:00:00Z",
            "snapshot_id": "snap-001",
            "simulated_time_utc": "2026-01-01T00:00:00Z",
            "snapshot_json": "{}",
            "total_pods": 5,
            "running_pods": 4,
            "pending_pods": 1,
            "gpu_count": 2,
            "gpu_utilization_avg_pct": 45.0,
            "total_cpu_millicores": 8000,
            "allocated_cpu_millicores": 3000,
            "total_memory_mb": 16384,
            "allocated_memory_mb": 4096,
        })
        assert snap_id > 0

        latest = db.query_latest_snapshot()
        assert latest is not None
        assert latest["snapshot_id"] == "snap-001"
        assert latest["total_pods"] == 5

        db.close()

    def test_scaling_config_upsert(self):
        """Upsert should insert then update without errors."""
        from shared.db.manager import DatabaseManager

        db = DatabaseManager(db_path=Path(":memory:"))
        db.connect()

        db.upsert_scaling_config({
            "deployment_id": "test-app",
            "min_replicas": 2,
            "max_replicas": 10,
            "baseline_per_pod": 100.0,
            "risk_asymmetry_factor": 5.0,
            "cooldown_seconds": 60,
            "upscale_cpu_threshold_pct": 70.0,
        })

        config = db.get_scaling_config("test-app")
        assert config is not None
        assert config["min_replicas"] == 2
        assert config["max_replicas"] == 10

        # Upsert again — should update
        db.upsert_scaling_config({
            "deployment_id": "test-app",
            "min_replicas": 3,
            "max_replicas": 15,
            "baseline_per_pod": 100.0,
            "risk_asymmetry_factor": 5.0,
            "cooldown_seconds": 60,
            "upscale_cpu_threshold_pct": 70.0,
        })

        config = db.get_scaling_config("test-app")
        assert config is not None
        assert config["min_replicas"] == 3

        db.close()

    def test_scaling_decision_insert(self):
        """Insert and query scaling decisions."""
        from shared.db.manager import DatabaseManager
        import uuid

        db = DatabaseManager(db_path=Path(":memory:"))
        db.connect()

        db.insert_scaling_decision({
            "timestamp_utc": "2026-01-01T00:00:00Z",
            "simulated_time_utc": "2026-01-01T00:00:00Z",
            "deployment_id": "test-app",
            "decision_id": f"dec-{uuid.uuid4()}",
            "action": "scale_up",
            "current_pod_count": 2,
            "target_pod_count": 4,
            "reason": "CPU above threshold",
            "forecast_id": None,
            "forecast_yhat": 75.0,
            "forecast_lower": 60.0,
            "forecast_upper": 90.0,
            "risk_score": 0.5,
            "confidence_score": 0.8,
            "risk_level": "MODERATE",
            "formula_raw_target": 4.0,
            "formula_confidence_factor": 1.0,
            "formula_risk_bias": 0.0,
            "formula_final_before_clamp": 4.0,
            "executed": 0,
            "execution_source": "predictive",
        })

        decisions = db.query_scaling_decisions("test-app")
        assert len(decisions) == 1
        assert decisions[0]["action"] == "scale_up"

        latest = db.query_latest_decision("test-app")
        assert latest is not None
        assert latest["target_pod_count"] == 4

        db.close()

    def test_insert_many_empty(self):
        """insert_many with empty list should return empty."""
        from shared.db.manager import DatabaseManager

        db = DatabaseManager(db_path=Path(":memory:"))
        db.connect()

        result = db.insert_many("metric_samples", [])
        assert result == []

        db.close()
