"""Database initialisation — creates all tables.

Every service calls init_db() on startup to ensure the database
and all tables exist. Schema migrations go here.

RULE 1.1: All table schemas are defined here, in the central registry.
No service defines its own tables.
"""

from pathlib import Path
import sqlite3

# Default database path (configurable via env var)
DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data" / "hpap.db"

# ── Full DDL for all tables ───────────────────────────────────
# Every shared model has a corresponding CREATE TABLE statement.
# All columns use snake_case with explicit units per RULE 1.2.

SCHEMA_SQL: str = """
-- Metric samples (produced by simulation, consumed by forecasting)
CREATE TABLE IF NOT EXISTS metric_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_utc TEXT NOT NULL,
    simulated_time_utc TEXT NOT NULL,
    deployment_id TEXT NOT NULL,
    cpu_utilization_pct REAL NOT NULL CHECK(cpu_utilization_pct >= 0 AND cpu_utilization_pct <= 100),
    memory_usage_mb REAL NOT NULL CHECK(memory_usage_mb >= 0),
    requests_per_second REAL NOT NULL CHECK(requests_per_second >= 0),
    gpu_utilization_pct REAL CHECK(gpu_utilization_pct IS NULL OR (gpu_utilization_pct >= 0 AND gpu_utilization_pct <= 100)),
    gpu_memory_used_mb REAL CHECK(gpu_memory_used_mb IS NULL OR gpu_memory_used_mb >= 0),
    latency_ms REAL CHECK(latency_ms IS NULL OR latency_ms >= 0),
    pod_count INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_metrics_deployment ON metric_samples(deployment_id, simulated_time_utc);
CREATE INDEX IF NOT EXISTS idx_metrics_time ON metric_samples(simulated_time_utc);

-- Forecast windows (produced by forecasting, consumed by controller)
CREATE TABLE IF NOT EXISTS forecast_windows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_utc TEXT NOT NULL,
    forecast_id TEXT NOT NULL UNIQUE,
    deployment_id TEXT NOT NULL,
    forecast_time_utc TEXT NOT NULL,
    generation_time_utc TEXT NOT NULL,
    yhat REAL NOT NULL,
    yhat_lower REAL NOT NULL,
    yhat_upper REAL NOT NULL,
    model_version TEXT NOT NULL,
    training_window_minutes INTEGER NOT NULL,
    training_end_time_utc TEXT NOT NULL,
    forecast_horizon_minutes INTEGER NOT NULL DEFAULT 30,
    uncertainty_pct REAL
);
CREATE INDEX IF NOT EXISTS idx_forecast_deployment ON forecast_windows(deployment_id, forecast_time_utc);

-- Forecast metadata (one per training run)
CREATE TABLE IF NOT EXISTS forecast_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_version TEXT NOT NULL UNIQUE,
    deployment_id TEXT NOT NULL,
    training_start_utc TEXT NOT NULL,
    training_end_utc TEXT NOT NULL,
    data_window_minutes INTEGER NOT NULL,
    data_points_count INTEGER NOT NULL DEFAULT 0,
    rmse REAL,
    mae REAL,
    mape_pct REAL,
    seasonality_daily INTEGER NOT NULL DEFAULT 1,
    seasonality_weekly INTEGER NOT NULL DEFAULT 0,
    changepoint_prior_scale REAL NOT NULL DEFAULT 0.05,
    status TEXT NOT NULL DEFAULT 'success' CHECK(status IN ('success', 'failed', 'fallback')),
    error_message TEXT
);

-- Scaling decisions (produced by controller, consumed by dashboard)
CREATE TABLE IF NOT EXISTS scaling_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_utc TEXT NOT NULL,
    decision_id TEXT NOT NULL UNIQUE,
    deployment_id TEXT NOT NULL,
    simulated_time_utc TEXT NOT NULL,
    current_pod_count INTEGER NOT NULL CHECK(current_pod_count >= 0),
    target_pod_count INTEGER NOT NULL CHECK(target_pod_count >= 0),
    action TEXT NOT NULL CHECK(action IN ('scale_up', 'scale_down', 'hold', 'emergency_scale_up')),
    forecast_id TEXT,
    forecast_yhat REAL NOT NULL,
    forecast_lower REAL NOT NULL,
    forecast_upper REAL NOT NULL,
    risk_score REAL NOT NULL CHECK(risk_score >= 0 AND risk_score <= 1),
    confidence_score REAL NOT NULL CHECK(confidence_score >= 0 AND confidence_score <= 1),
    risk_level TEXT NOT NULL DEFAULT 'medium',
    formula_raw_target REAL NOT NULL,
    formula_confidence_factor REAL NOT NULL,
    formula_risk_bias REAL NOT NULL,
    formula_final_before_clamp REAL NOT NULL,
    executed INTEGER NOT NULL DEFAULT 0,
    execution_source TEXT NOT NULL DEFAULT 'predictive',
    reason TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_decisions_deployment ON scaling_decisions(deployment_id, simulated_time_utc);

-- GPU assignments (produced by GPU scheduler, consumed by dashboard)
CREATE TABLE IF NOT EXISTS gpu_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_utc TEXT NOT NULL,
    assignment_id TEXT NOT NULL UNIQUE,
    gpu_id TEXT NOT NULL,
    pod_id TEXT NOT NULL,
    deployment_id TEXT NOT NULL,
    memory_allocated_mb INTEGER NOT NULL CHECK(memory_allocated_mb >= 1),
    compute_allocated_pct REAL NOT NULL CHECK(compute_allocated_pct >= 0 AND compute_allocated_pct <= 100),
    effective_utilization_pct REAL
);

-- GPU rebalance events
CREATE TABLE IF NOT EXISTS gpu_rebalance_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_utc TEXT NOT NULL,
    event_id TEXT NOT NULL UNIQUE,
    trigger_reason TEXT NOT NULL,
    assignments_before INTEGER NOT NULL,
    assignments_after INTEGER NOT NULL,
    gpus_involved TEXT NOT NULL DEFAULT '[]',
    duration_ms REAL NOT NULL DEFAULT 0.0
);

-- Cluster snapshots (periodic state dumps by simulation)
CREATE TABLE IF NOT EXISTS cluster_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_utc TEXT NOT NULL,
    snapshot_id TEXT NOT NULL UNIQUE,
    simulated_time_utc TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    total_pods INTEGER NOT NULL,
    running_pods INTEGER NOT NULL,
    pending_pods INTEGER NOT NULL,
    gpu_count INTEGER NOT NULL,
    gpu_utilization_avg_pct REAL,
    total_cpu_millicores INTEGER NOT NULL,
    allocated_cpu_millicores INTEGER NOT NULL,
    total_memory_mb INTEGER NOT NULL,
    allocated_memory_mb INTEGER NOT NULL
);

-- Simulation configurations
CREATE TABLE IF NOT EXISTS simulation_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_utc TEXT NOT NULL,
    config_json TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 0
);

-- Per-deployment scaling configurations
CREATE TABLE IF NOT EXISTS scaling_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deployment_id TEXT NOT NULL UNIQUE,
    min_replicas INTEGER NOT NULL DEFAULT 1,
    max_replicas INTEGER NOT NULL DEFAULT 20,
    baseline_per_pod REAL NOT NULL DEFAULT 100.0,
    risk_asymmetry_factor REAL NOT NULL DEFAULT 5.0,
    cooldown_seconds INTEGER NOT NULL DEFAULT 60,
    upscale_cpu_threshold_pct REAL NOT NULL DEFAULT 70.0
);
"""


def get_db_path() -> Path:
    """Get the database file path.

    Checks the HPAP_DB_PATH environment variable first,
    falls back to DEFAULT_DB_PATH.

    TODO: Add support for PostgreSQL via environment variable.
    """
    import os

    env_path = os.environ.get("HPAP_DB_PATH")
    if env_path:
        return Path(env_path)
    return DEFAULT_DB_PATH


def init_db(db_path: Path | None = None) -> sqlite3.Connection:
    """Initialise the SQLite database with all tables.

    Creates the data directory if it doesn't exist.
    Enables WAL mode for concurrent read access.
    Executes all CREATE TABLE IF NOT EXISTS statements.

    Args:
        db_path: Path to the database file. Uses get_db_path() if None.

    Returns:
        sqlite3.Connection: A connection to the initialised database.

    Raises:
        sqlite3.Error: If database initialisation fails.
        PermissionError: If the data directory cannot be created.

    TODO:
        - Add migration system (version tracking table)
        - Add PostgreSQL support for production deployments
    """
    resolved = db_path or get_db_path()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(resolved), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn
