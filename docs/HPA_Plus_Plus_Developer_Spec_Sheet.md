# HPA++ Developer Specification Sheet

## AI-Powered Predictive Auto Scaling & GPU Scheduling for Kubernetes

| Field                | Details                                                     |
| :------------------- | :---------------------------------------------------------- |
| **Project**          | HPA++ — AI-Powered Predictive Auto Scaling & GPU Scheduling |
| **Hackathon**        | AI Innovation Hackathon 2026 — Phase 1                      |
| **Track**            | AI for Cluster Intelligence                                 |
| **Team**             | Team Falah                                                  |
| **Document Version** | 1.0                                                         |

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Executive Rules of Engagement](#2-executive-rules-of-engagement)
3. [System Architecture Overview](#3-system-architecture-overview)
4. [Developer Assignments](#4-developer-assignments)
5. [Subtask Breakdown](#5-subtask-breakdown)
6. [Shared Schema Registry Specification](#6-shared-schema-registry-specification)
7. [Inter-Service Contracts (API Boundaries)](#7-inter-service-contracts-api-boundaries)
8. [Database Schema](#8-database-schema)
9. [Data Flow & Pipeline Sequence](#9-data-flow--pipeline-sequence)
10. [Development Schedule & Milestones](#10-development-schedule--milestones)
11. [Integration & Demo Workflow](#11-integration--demo-workflow)
12. [Verification & Acceptance Criteria](#12-verification--acceptance-criteria)

---

## 1. Executive Summary

HPA++ is an end-to-end system that replaces Kubernetes' reactive Horizontal Pod Autoscaler (HPA) with **forecast-driven, risk-aware scaling decisions**. It simulates a Kubernetes cluster environment, generates realistic traffic metrics, trains a Prophet-based forecasting model, makes proactive scaling decisions with confidence awareness, schedules GPU resources intelligently, and visualises everything on a live dashboard.

### System Components

| #   | Component                                            | Owner   |
| :-- | :--------------------------------------------------- | :------ |
| 1   | **Cluster Simulation Engine**                        | Daiyaan |
| 2   | **Shared Schema Registry & Database**                | Daiyaan |
| 3   | **Forecasting Engine (Prophet)**                     | Farhan  |
| 4   | **Predictive Controller + GPU Scheduler**            | Farhan  |
| 5   | **Live Monitoring Dashboard**                        | Dristee |
| 6   | **Integration Layer, Contract Tests & Demo Harness** | Dristee |

### Technology Stack

| Layer              | Technology                                                                        |
| :----------------- | :-------------------------------------------------------------------------------- |
| Languages          | Python 3.x (all services), TypeScript/TSX (Dashboard if extending to web)         |
| ML / Forecasting   | Facebook Prophet, pandas, NumPy, scikit-learn                                     |
| Dashboard          | Streamlit + Plotly (primary), optionally React + recharts/d3                      |
| Simulation         | Custom Python event loop, Locust for load generation                              |
| Data / Persistence | SQLite (development), unified schemas via Pydantic (Python) / Zod (TS)            |
| Cluster Interface  | Kubernetes API via `kubernetes` Python client (mocked in sim, real in production) |
| Validation         | Pydantic v2 (all Python boundaries), Zod (frontend boundaries)                    |
| Testing            | pytest, pytest-asyncio, Locust, contract tests                                    |

---

## 2. Executive Rules of Engagement

### 2.1 Schema & Data Standards

**RULE 1.1 — Single Schema Registry:** No domain team may define top-level data models locally. Every shared object, event, or payload MUST be pulled from the central schema registry at `app/schemas/`. All teams import from this single source of truth.

**RULE 1.2 — Standard Casing & Explicit Units:** All JSON payloads and database columns must use `snake_case`. Every physical or temporal quantity variable MUST explicitly state its units in the name. Examples:

| ✅ Correct             | ❌ Incorrect         |
| :--------------------- | :------------------- |
| `cpu_utilization_pct`  | `cpu_util`           |
| `memory_usage_mb`      | `memory`             |
| `requests_per_second`  | `rps` / `reqs`       |
| `latency_ms`           | `latency`            |
| `gpu_utilization_pct`  | `gpu_util`           |
| `timestamp_utc`        | `timestamp` / `time` |
| `forecast_upper_bound` | `upper`              |
| `risk_score`           | `score`              |
| `pod_count`            | `pods`               |

**RULE 1.3 — Boundary Validation is Mandatory:** Every incoming payload from another service must pass strict runtime schema validation. Python services use Pydantic v2 models. Frontend uses Zod. Unvalidated data must be rejected immediately at the boundary with a descriptive error. No `Any` / `dict` escape hatches.

### 2.2 Domain & Responsibility Boundaries

**RULE 2.1 — Absolute Separation of Concerns:**

| Team                   | Owns                                                                        | Does NOT Touch                           |
| :--------------------- | :-------------------------------------------------------------------------- | :--------------------------------------- |
| **Simulation** (Dev 1) | State generation, physics loops, metric emission, data persistence          | ML heuristics, UI formatting             |
| **Prediction** (Dev 2) | Feature extraction, model inference, scaling decision logic, GPU scheduling | Raw physics simulation, visual rendering |
| **Frontend** (Dev 3)   | Visualization, user input, real-time display, integration orchestration     | Business logic, raw data transformations |

**RULE 2.2 — Zero Cross-Domain Trespassing:** If a feature requires logic in another domain, file a specification request — never build a placeholder for another team's work. Every module must function against mock outputs of its dependencies before integration.

**RULE 2.3 — Contract-First Integration:** Each service publishes a contract (Pydantic models defining its input/output boundaries). If a PR breaks a contract test owned by another team, the PR is automatically blocked from merging. Contract tests run in CI before any integration test.

### 2.3 Working Conventions

- **Repository structure:** Single monorepo at `HPA-pp/`. Each component lives under `app/<component_name>/`.
- **Feature branches:** `sim/<feature>`, `pred/<feature>`, `ui/<feature>` prefixes.
- **Mocks before integration:** No team waits for another. Simulation ships a `MockForecastStore` so Prediction can develop against synthetic data. Prediction ships a `MockClusterState` so Frontend can develop against fake forecasts. Contract tests validate that real outputs match mock shapes.
- **Daily sync:** 15-minute standup at 10 AM. Integration branch merged at EOD if all contract tests pass.

---

## 3. System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           HPA++ SYSTEM                                        │
├──────────────────┬───────────────────────┬──────────────────────────────────┤
│  SIMULATION      │  PREDICTION           │  VISUALIZATION & INTEGRATION     │
│  (Dev 1)         │  (Dev 2)              │  (Dev 3)                         │
│                  │                       │                                  │
│  ┌────────────┐  │  ┌─────────────────┐  │  ┌──────────────────────────┐   │
│  │Cluster Sim │  │  │Forecasting Eng  │  │  │Live Dashboard            │   │
│  │▪ Nodes     │  │  │▪ Prophet model  │  │  │▪ Actual vs predicted     │   │
│  │▪ Pods      │──┤  │▪ Rolling window │  │  │▪ Current vs target pods  │   │
│  │▪ Deploymts │  │  │▪ Confidence CI  │  │  │▪ Confidence bands        │   │
│  │▪ GPU pool  │  │  └──────┬──────────┘  │  │▪ Scaling decision log    │   │
│  │▪ Traffic   │  │         │             │  │▪ GPU allocation view     │   │
│  │  generator │  │  ┌──────▼──────────┐  │  └──────────────────────────┘   │
│  └──────┬─────┘  │  │Predictive Ctrl  │  │                                  │
│         │        │  │▪ Risk scoring   │  │  ┌──────────────────────────┐   │
│  ┌──────▼─────┐  │  │▪ Pod target     │  │  │Integration & Demo        │   │
│  │Schema/DB   │──┤  │  computation    │  │  │▪ Contract tests          │   │
│  │▪ Pydantic  │  │  │▪ Scale executor │  │  │▪ Demo bootstrap script   │   │
│  │▪ SQLite    │  │  └──────┬──────────┘  │  │▪ Locust test harness     │   │
│  │▪ Registry  │  │         │             │  │▪ E2E smoke test          │   │
│  └────────────┘  │  ┌──────▼──────────┐  │  └──────────────────────────┘   │
│                  │  │GPU Scheduler    │  │                                  │
│                  │  │▪ GPU allocator  │  │                                  │
│                  │  │▪ Contention     │  │                                  │
│                  │  │  resolver       │  │                                  │
│                  │  └─────────────────┘  │                                  │
├──────────────────┴───────────────────────┴──────────────────────────────────┤
│  DATA LAYER: SQLite file at app/data/hpap.db — all services read/write here  │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

1. **Shared SQLite database** as the communication backbone. Every service writes its output to known tables and reads its input from tables written by upstream services. This eliminates networked service dependencies during development and makes the data pipeline inspectable by all teams.

2. **Pydantic v2** for all Python boundary validation. Every table has a corresponding Pydantic model in the schema registry. Every read/write operation validates through the model.

3. **Simulation-in-the-loop.** The cluster simulator produces realistic metric time-series. The forecasting engine consumes them. The controller acts on the forecast. The dashboard visualises everything. This closed loop runs end-to-end for the demo.

4. **Mock-first parallelism.** Dev 1 provides `MockForecastStore` (returns canned forecasts), Dev 2 provides `MockClusterState` (returns synthetic pod/node states). Contract tests verify that real implementations produce the same shape as mocks.

---

## 4. Developer Assignments

| Developer                            | Role                   | Subtask 1                                       | Subtask 2                                                |
| :----------------------------------- | :--------------------- | :---------------------------------------------- | :------------------------------------------------------- |
| **Daiyaan Muhammad Fardeen**         | Simulation & Data      | **S1:** Shared Schema Registry & Database Layer | **S2:** Cluster Simulation Engine                        |
| **Ahmed Farhanur Rashid**            | Prediction & Control   | **S3:** Forecasting Engine (Prophet)            | **S4:** Predictive Controller + GPU Scheduler            |
| **Sanzida Chowdhury Dristee** (Lead) | Frontend & Integration | **S5:** Live Monitoring Dashboard               | **S6:** Integration Layer, Contract Tests & Demo Harness |

### Dependency Graph

```
S1 (Schema/DB) ──► S2 (Cluster Sim) ──► S3 (Forecast Eng) ──► S4 (Controller) ──► S5 (Dashboard)
       │                                    │                       │
       └──── ALL TEAMS IMPORT FROM HERE ────┴───────────────────────┘
                                              S6 (Integration) wraps everything
```

**Parallelism windows:**

- S1 must complete first (all teams depend on schemas).
- Once S1 schemas are published, S2, S3, and S5 can start in parallel (each operates against mock data).
- S4 requires S3's forecast output shape (can develop against MockForecast output).
- S6 runs last, wiring everything together.

---

## 5. Subtask Breakdown

### 5.1 Subtask S1 — Shared Schema Registry & Database Layer

**Owner:** Sanzida  
**Depends on:** Nothing (foundation)  
**Produces:** `app/schemas/` with all Pydantic models + `app/db/` database layer

**What to build:**

1. **Monorepo scaffolding:**
   - Set up `app/` directory structure: `app/schemas/`, `app/db/`, `app/simulation/`, `app/forecasting/`, `app/controller/`, `app/dashboard/`, `app/integration/`
   - `requirements.txt` / `pyproject.toml` with pinned dependencies
   - `Makefile` with targets: `install`, `lint`, `test`, `db-init`, `demo-run`
   - `pytest.ini` / `conftest.py` with shared fixtures

2. **All Pydantic schemas** defined in `app/schemas/` (see Section 6 for full specification):
   - `MetricSample`, `ForecastWindow`, `ScalingDecision`, `GpuAssignment`, `ClusterSnapshot`
   - `SimulationConfig`, `TrafficProfile`, `DeploymentSpec`
   - `ApiResponse[T]` generic wrapper
   - Unit tests for every schema (test valid construction, test invalid data rejection)

3. **Database layer** at `app/db/`:
   - SQLite database with tables matching every schema (see Section 8)
   - `DatabaseManager` class: `init_db()`, `insert()`, `query()`, `get_latest()`, `get_window()`
   - Connection pooling via `sqlite3` with WAL mode for concurrent reads
   - Migration system: `db/migrations/001_initial.py` etc.
   - `db-init` Makefile target

4. **Validation helpers:**
   - `validate_payload(model: type[BaseModel], data: dict) -> BaseModel` — validates and raises on failure
   - `validate_or_default(model: type[BaseModel], data: dict) -> BaseModel` — validates with fallback

5. **Unit tests** for schema validation, database CRUD, and boundary rejection of bad data.

**Acceptance criteria:**

- [ ] All schemas defined and tested (valid data accepted, invalid data rejected with clear errors)
- [ ] `DatabaseManager` can create tables, insert records, query by time range, get latest
- [ ] Verification: run `make db-init && pytest app/schemas/ -v` — all pass
- [ ] Verification: import a schema from another component `from app.schemas import MetricSample` works

---

### 5.2 Subtask S2 — Cluster Simulation Engine

**Owner:** Sanzida  
**Depends on:** S1 (schemas + DB)  
**Mock contract:** Provides `MockForecastStore` for S3, provides `MockClusterState` for S5

**What to build:**

1. **Cluster state model** (in-memory, driven by `SimulationConfig`):
   - Simulated nodes with CPU, memory, GPU capacity
   - Simulated deployments with replica counts, resource requests, traffic multipliers
   - Simulated pods with status (Pending/Running/Evicted), resource usage
   - GPU pool: each GPU has memory_mb, compute_units, assigned_pod

2. **Metric time-series generator:**
   - Configurable `TrafficProfile` with patterns: `steady`, `sine_wave`, `step_spike`, `flash_sale`, `exam_start`
   - Each profile produces `requests_per_second`, `cpu_utilization_pct`, `memory_usage_mb`, `gpu_utilization_pct` per deployment per tick
   - Configurable noise, seasonality (daily/hourly), and trend
   - Tick rate: configurable (default 1 simulated minute per 0.5s real time)

3. **Simulation loop** (`app/simulation/engine.py`):
   - `SimulationEngine` class with `start()`, `pause()`, `resume()`, `stop()`
   - `tick()` — advances one time step, updates cluster state, emits metrics to DB
   - Metrics writer: batches `MetricSample` records and inserts into DB
   - State writer: writes periodic `ClusterSnapshot` to DB
   - Configurable speed factor (1x, 10x, 60x)

4. **Mock services** for other teams:
   - `MockForecastStore`: reads recent metrics from DB, returns fake forecasts with correct schema shape
   - `MockClusterState`: returns current cluster state from DB (or fake if empty)

5. **Load generator integration** (optional enhancement):
   - Locustfile that hits a simulated endpoint and generates realistic request patterns
   - Can replace or augment the metric generator for demo

6. **Unit + integration tests:**
   - Test each `TrafficProfile` produces correct metric ranges
   - Test simulation loop writes to DB correctly
   - Test pause/resume state
   - Test mock services return correct schema shapes

**Acceptance criteria:**

- [ ] Simulation starts, runs N ticks, writes metric samples to DB
- [ ] All traffic profiles produce distinguishable patterns (verify via plot or statistical test)
- [ ] Pause/resume/stop work correctly
- [ ] `MockForecastStore` returns correctly-shaped forecast data (contract test passes)
- [ ] Verification: `python -m app.simulation.engine --profile flash_sale --ticks 60` writes 60 rows to DB

---

### 5.3 Subtask S3 — Forecasting Engine (Prophet)

**Owner:** Daiyaan  
**Depends on:** S1 (schemas + DB), consumes metrics from S2 (or mock metrics)  
**Mock contract:** Accepts `MockForecastStore` from S2 initially, integrates with real DB later

**What to build:**

1. **Feature extraction pipeline** (`app/forecasting/features.py`):
   - Reads raw `MetricSample` rows from DB for a time window (configurable: last N minutes)
   - Resamples to uniform time grid (e.g., 1-minute buckets)
   - Aggregates across deployments if needed
   - Outputs DataFrame with columns: `ds` (datetime), `y` (target metric)

2. **Prophet model wrapper** (`app/forecasting/model.py`):
   - `ForecastingModel` class wrapping Facebook Prophet
   - `train(metrics_df)` — fits Prophet on historical data
   - `predict(horizon_minutes)` — produces forecast with `yhat`, `yhat_lower`, `yhat_upper`
   - `retrain(metrics_df)` — incremental retrain on rolling window
   - Configurable seasonality: daily, weekly
   - Configurable horizon: default 30 minutes ahead

3. **Forecast pipeline** (`app/forecasting/pipeline.py`):
   - `ForecastPipeline` class that orchestrates: read → resample → train → predict → store
   - `run_once()` — single forecast cycle
   - `run_loop(interval_seconds)` — continuous forecasting at fixed interval
   - Stores `ForecastWindow` records to DB

4. **Model versioning** (lightweight):
   - Each forecast tagged with `model_version` (timestamp of training)
   - `ForecastMetadata` table: tracks training time, data window, model parameters, fit quality (rmse, mae)

5. **Fallback / safety:**
   - If Prophet fails to converge (e.g., too little data), fallback to naive forecast (last value)
   - If data window is empty, return None / skip cycle (don't crash)

6. **Tests:**
   - Unit tests with synthetic time-series (sin wave, linear trend, noise)
   - Integration test: read from DB → train → predict → write to DB
   - Test fallback behaviour with empty/incomplete data

**Acceptance criteria:**

- [ ] Prophet trains on 60+ metric samples and produces a 30-minute forecast
- [ ] Forecast output contains `yhat`, `yhat_lower`, `yhat_upper` with sane intervals
- [ ] Forecast saved to `forecast_windows` table in DB
- [ ] Fallback kicks in when data is insufficient (no crash)
- [ ] Verification: `python -m app.forecasting.pipeline --horizon 30 --db app/data/hpap.db` produces forecast rows

---

### 5.4 Subtask S4 — Predictive Controller + GPU Scheduler

**Owner:** Daiyaan  
**Depends on:** S1 (schemas + DB), S3 (forecast shape — can use mock forecast initially)

**What to build:**

#### Part A: Predictive Controller

1. **Scaling decision engine** (`app/controller/scaler.py`):
   - `PredictiveController` class
   - `compute_target_pods(forecast: ForecastWindow, current_pods: int, config: ScalingConfig) -> ScalingDecision`
   - Implements **confidence-aware scaling**:
     - If confidence interval is narrow → trust forecast, scale proactively
     - If confidence interval is wide → scale conservatively (bias toward current)
   - Implements **risk-aware scaling**:
     - Risk score = f(forecast error_magnitude, historical_miss_rate, cost_asymmetry)
     - Cost asymmetry: under-provisioning is 5x more expensive than over-provisioning (configurable)
     - `risk_threshold_high` → scale more aggressively
     - `risk_threshold_low` → scale minimally
   - Pod target bounds: `min_replicas ≤ target ≤ max_replicas` (from deployment config)

2. **Scaling formula:**

   ```
   raw_target = ceil(forecast_yhat / baseline_per_pod)
   confidence_factor = clip((upper - lower) / yhat, 0, 1)  # 1 = very uncertain
   risk_bias = 1 + risk_score * asymmetry_factor  # > 1 biases toward over-provision
   target = raw_target * (1 + confidence_factor * risk_bias * uncertainty_penalty)
   target = clamp(target, min_replicas, max_replicas)
   ```

3. **Scale executor** (`app/controller/executor.py`):
   - `ScaleExecutor` class
   - In simulation mode: writes target to `scaling_decisions` table and updates simulated cluster state
   - In real mode: calls Kubernetes API `apps/v1/deployments/{name}/scale`
   - Dry-run mode: logs decision without applying
   - Decision logging: every decision records timestamp, forecast values, confidence, risk score, formula terms, and outcome

4. **Decision audit log**:
   - Full explainability: every `ScalingDecision` record includes:
     - All forecast values that went into the decision
     - The exact formula with parameter values
     - Risk score breakdown
     - Whether the action was executed, dry-run, or blocked

#### Part B: GPU Scheduler

5. **GPU scheduling engine** (`app/controller/gpu_scheduler.py`):
   - `GpuScheduler` class
   - Input: list of pods requesting GPU, list of available GPUs with capacity
   - Output: `GpuAssignment` records
   - Algorithm: **bin-packing with contention minimization**
     - Sort GPUs by available memory (most free first for spread, least free first for packing — configurable)
     - Assign pods to GPUs to minimize fragmentation
     - Resolve contention: if multiple pods compete for same GPU, prefer pods from higher-priority deployments
   - Periodic rebalancing: every N seconds, reassess assignments to improve packing

6. **GPU metrics consumer**:
   - Reads `gpu_utilization_pct` from `MetricSample` records
   - Detects overcommitted GPUs (util > 90% for sustained period)
   - Triggers rebalancing when contention detected

7. **Tests:**
   - Unit tests for scaling formula with known inputs/outputs
   - Property-based test: target always within [min, max] bounds
   - GPU scheduler tests: N pods, M GPUs → correct assignments with no overallocation
   - Integration test: mock forecast → compute decision → write to DB

**Acceptance criteria:**

- [ ] Scaling formula produces deterministic, bounded results for all valid inputs
- [ ] Confidence-aware logic widens/narrows target based on forecast certainty
- [ ] GPU scheduler assigns N pods to M GPUs without exceeding any GPU's capacity
- [ ] Every decision is fully logged with all reasoning terms
- [ ] Verification: `python -m app.controller.scaler --forecast-id X` reads forecast, writes decision
- [ ] Verification: `python -m app.controller.gpu_scheduler --pods 10 --gpus 4` produces valid assignments

---

### 5.5 Subtask S5 — Live Monitoring Dashboard

**Owner:** Ahmed  
**Depends on:** S1 (schemas + DB), consumes data from S2/S3/S4 (or mock data)

**What to build:**

1. **Streamlit application** at `app/dashboard/app.py`:
   - Multi-page dashboard with auto-refresh (configurable interval, default 2s)
   - Reads directly from the shared SQLite DB (no intermediate API needed)

2. **Dashboard panels:**

   **Panel 1: Traffic Overview**
   - Time-series line chart: actual requests_per_second vs predicted (forecast_yhat)
   - Confidence band shading: `yhat_lower` to `yhat_upper` as translucent band
   - Dropdown to select deployment
   - Time range selector (last 15min / 30min / 1hr / all)

   **Panel 2: Pod Scaling Status**
   - Dual line chart: current pod count vs recommended target pod count
   - Color coding: green (adequate), yellow (scaling imminent), red (under-provisioned)
   - Current replica count display card

   **Panel 3: GPU Allocation View**
   - Heatmap or horizontal bar chart showing GPU utilization per GPU device
   - Pod-to-GPU mapping: which pods are on which GPU
   - Contention alerts (highlights GPUs above 90% util)

   **Panel 4: Decision Log**
   - Table of recent `ScalingDecision` records
   - Columns: timestamp, deployment, from→to pods, risk score, confidence, reason
   - Expandable row showing full formula breakdown
   - Color: green (scaled up), blue (scaled down), gray (no action)

   **Panel 5: Cluster State Overview**
   - Summary cards: total nodes, total pods, running pods, pending pods, GPU count
   - Node list table with resource usage bars

   **Panel 6: Simulation Controls** (if simulation is running)
   - Play/Pause/Stop buttons
   - Speed slider (1x – 60x)
   - Active traffic profile indicator

3. **Data layer** (`app/dashboard/data.py`):
   - `DashboardData` class wrapping DB queries
   - Cached queries with TTL to avoid DB hammering on every refresh
   - Helper methods: `get_recent_metrics()`, `get_latest_forecast()`, `get_scaling_history()`, `get_gpu_assignments()`, `get_cluster_snapshot()`

4. **Auto-refresh loop:**
   - Streamlit `st.autorefresh` or custom `time.sleep` loop
   - Page re-renders on new data

5. **Theme & layout:**
   - Dark theme (professional, suitable for dashboards)
   - Responsive layout, works on 1920x1080 demo screen
   - Consistent colour palette (use Plotly `plotly_dark` template as baseline)

6. **Tests:**
   - Unit tests for `DashboardData` query methods against a test DB
   - Verify data layer returns correct shapes even when DB tables are empty (graceful degradation)

**Acceptance criteria:**

- [ ] All 6 panels render correctly with live data from DB
- [ ] Dashboard auto-refreshes and shows new data within 3s of DB write
- [ ] Empty DB state shows graceful placeholders (no crashes, no infinite spinners)
- [ ] All time-series charts show actual vs predicted with confidence bands
- [ ] Decision log renders with expandable details
- [ ] Verification: `streamlit run app/dashboard/app.py` opens without errors

---

### 5.6 Subtask S6 — Integration Layer, Contract Tests & Demo Harness

**Owner:** Ahmed  
**Depends on:** S1–S5 (wires everything together last)

**What to build:**

1. **Contract test suite** (`app/integration/contracts/`):
   - Tests that validate each service's output matches its contract:
     - `test_metric_sample_contract()` — Simulation writes MetricSample with correct fields
     - `test_forecast_window_contract()` — Forecasting writes ForecastWindow with correct fields
     - `test_scaling_decision_contract()` — Controller writes ScalingDecision with correct fields
     - `test_gpu_assignment_contract()` — GPU Scheduler writes GpuAssignment with correct fields
   - Each test: call the service's public API → validate output against Pydantic model → fail if extra/missing/wrong fields
   - Run on PR to main branch (or at minimum before demo)

2. **Cross-domain boundary tests** (`app/integration/boundaries/`):
   - `test_simulation_to_forecast_boundary()` — verify ForecastPipeline correctly reads MetricSample from DB
   - `test_forecast_to_controller_boundary()` — verify PredictiveController correctly reads ForecastWindow from DB
   - `test_controller_to_dashboard_boundary()` — verify Dashboard can read ScalingDecision from DB
   - Tests insert known data into DB, run the downstream consumer, verify correct output

3. **End-to-end pipeline test** (`app/integration/e2e/`):
   - `test_full_pipeline.py`: starts simulation → runs for N ticks → runs forecasting → runs controller → verifies dashboard DB reads
   - Uses a clean test DB
   - Configurable tick count (default: 60 simulated minutes)
   - Asserts: metrics were written, forecast was produced, decision was made, dashboard can query

4. **Demo bootstrap script** (`app/integration/demo.py`):
   - `python -m app.integration.demo --profile flash_sale --duration 10`
   - Starts simulation with specified traffic profile
   - Launches forecasting pipeline in background thread
   - Launches controller loop in background thread
   - Opens dashboard (or prints instructions to open it)
   - Graceful shutdown on Ctrl+C

5. **Locust load test integration** (optional enhancement):
   - Locustfile that generates HTTP requests against a simulated endpoint
   - Metrics from Locust feed into the simulation metric stream
   - Benchmark: HPA++ vs standard HPA (simulated) under identical traffic

6. **Makefile targets:**
   - `make install` — install all dependencies
   - `make test` — run all tests (unit + contract + integration)
   - `make test-contracts` — contract tests only
   - `make test-e2e` — full pipeline test
   - `make demo` — launch demo bootstrap
   - `make demo-load` — launch with Locust load generation
   - `make lint` — ruff check
   - `make db-init` — initialise database
   - `make clean` — remove db, **pycache**, temp files

7. **Documentation:**
   - `README.md` updated with architecture diagram, setup instructions, and demo walkthrough
   - Each component's `__init__.py` or `README.md` with quickstart

**Acceptance criteria:**

- [ ] All contract tests pass (each service produces correct schema-shaped outputs)
- [ ] End-to-end pipeline test runs without errors in < 30s
- [ ] `make demo` launches a running system with simulation, forecasts, decisions, and dashboard
- [ ] Dashboard shows live-updating data within 5s of startup
- [ ] `make test` exits with code 0

---

## 6. Shared Schema Registry Specification

All schemas live in `app/schemas/`. Every team imports from here — never define shared models locally.

### 6.1 Schema Files

```
app/schemas/
├── __init__.py              # Re-exports all models
├── base.py                  # BaseModel config, timestamp mixins
├── metrics.py               # MetricSample, MetricBatch
├── forecast.py              # ForecastWindow, ForecastMetadata
├── decisions.py             # ScalingDecision, ScalingConfig
├── gpu.py                   # GpuAssignment, GpuSpec
├── cluster.py               # ClusterSnapshot, NodeState, PodState, DeploymentState
├── simulation.py            # SimulationConfig, TrafficProfile, DeploymentSpec
├── api.py                   # ApiResponse[T], ErrorResponse
└── enums.py                 # PodStatus, TrafficPattern, RiskLevel, ScalingAction
```

### 6.2 Model Specifications

#### `base.py`

```python
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class TimestampedModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        frozen=False,
        extra="forbid",  # Reject unknown fields at boundary
    )

class AuditModel(TimestampedModel):
    timestamp_utc: datetime = Field(
        default_factory=datetime.utcnow,
        description="Record creation timestamp in UTC"
    )
```

#### `enums.py`

```python
from enum import Enum

class PodStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    EVICTED = "evicted"
    FAILED = "failed"

class TrafficPattern(str, Enum):
    STEADY = "steady"
    SINE_WAVE = "sine_wave"
    STEP_SPIKE = "step_spike"
    FLASH_SALE = "flash_sale"
    EXAM_START = "exam_start"
    CUSTOM = "custom"

class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class ScalingAction(str, Enum):
    SCALE_UP = "scale_up"
    SCALE_DOWN = "scale_down"
    HOLD = "hold"
```

#### `metrics.py`

```python
class MetricSample(AuditModel):
    """Single metric observation from one deployment at one point in simulated time."""
    deployment_id: str = Field(..., description="Unique deployment identifier")
    simulated_time_utc: datetime = Field(..., description="Simulation clock time")
    cpu_utilization_pct: float = Field(
        ..., ge=0.0, le=100.0, description="CPU utilization percentage"
    )
    memory_usage_mb: float = Field(..., ge=0.0, description="Memory usage in MB")
    requests_per_second: float = Field(..., ge=0.0, description="Incoming request rate")
    gpu_utilization_pct: float | None = Field(
        default=None, ge=0.0, le=100.0, description="GPU utilization percentage (None if no GPU)"
    )
    latency_ms: float | None = Field(
        default=None, ge=0.0, description="Request latency in milliseconds"
    )

class MetricBatch(TimestampedModel):
    """Batch of metric samples for bulk insert."""
    samples: list[MetricSample]
    source_id: str = Field(..., description="Source identifier (e.g., 'cluster_sim')")
```

#### `forecast.py`

```python
class ForecastWindow(AuditModel):
    """A single forecast point from Prophet at a future simulated time."""
    deployment_id: str = Field(..., description="Target deployment")
    forecast_time_utc: datetime = Field(..., description="The future time being predicted")
    yhat: float = Field(..., description="Point forecast value (requests_per_second)")
    yhat_lower: float = Field(..., description="Lower bound of confidence interval")
    yhat_upper: float = Field(..., description="Upper bound of confidence interval")
    model_version: str = Field(..., description="Version/timestamp of the model that produced this")
    training_window_minutes: int = Field(..., ge=1, description="Minutes of training data used")
    training_end_time_utc: datetime = Field(..., description="When the training data ended")

class ForecastMetadata(TimestampedModel):
    """Metadata about a model training run."""
    model_version: str = Field(..., description="Unique model version identifier")
    deployment_id: str = Field(..., description="Deployment this model was trained for")
    training_start_utc: datetime = Field(...)
    training_end_utc: datetime = Field(...)
    data_window_minutes: int = Field(..., ge=1)
    rmse: float | None = Field(default=None, ge=0.0)
    mae: float | None = Field(default=None, ge=0.0)
    seasonality_daily: bool = Field(default=True)
    seasonality_weekly: bool = Field(default=False)
    status: str = Field(default="success", pattern="^(success|failed|fallback)$")
```

#### `decisions.py`

```python
class ScalingConfig(TimestampedModel):
    """Configuration for a deployment's scaling behaviour."""
    deployment_id: str = Field(...)
    min_replicas: int = Field(default=1, ge=1)
    max_replicas: int = Field(default=20, ge=1, le=100)
    baseline_per_pod: float = Field(
        default=100.0, ge=1.0,
        description="Estimated requests_per_second one pod can handle"
    )
    risk_asymmetry_factor: float = Field(
        default=5.0, ge=1.0,
        description="How much more expensive under-provisioning is than over-provisioning"
    )
    cooldown_seconds: int = Field(default=60, ge=0)

class ScalingDecision(AuditModel):
    """Record of a single scaling decision with full explainability."""
    decision_id: str = Field(..., description="Unique decision identifier")
    deployment_id: str = Field(...)
    forecast_id: str | None = Field(default=None, description="FK to ForecastWindow")
    simulated_time_utc: datetime = Field(..., description="Simulation time when decision was made")
    current_pod_count: int = Field(..., ge=0)
    target_pod_count: int = Field(..., ge=0)
    action: ScalingAction = Field(...)

    # Risk-aware fields
    risk_score: float = Field(..., ge=0.0, le=1.0)
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    forecast_yhat: float = Field(...)
    forecast_lower: float = Field(...)
    forecast_upper: float = Field(...)

    # Formula explanation
    formula_raw_target: float = Field(..., description="raw_target = ceil(forecast_yhat / baseline_per_pod)")
    formula_confidence_factor: float = Field(..., description="How forecast uncertainty affected the decision")
    formula_risk_bias: float = Field(..., description="How risk score biased the decision")
    formula_final_before_clamp: float = Field(..., description="Target before min/max clamping")

    # Outcome
    executed: bool = Field(default=False, description="Whether the scale action was applied")
    reason: str = Field(default="", description="Human-readable explanation of the decision")
```

#### `gpu.py`

```python
class GpuSpec(TimestampedModel):
    """Specification of a single GPU device."""
    gpu_id: str = Field(...)
    total_memory_mb: int = Field(..., ge=1)
    compute_units: float = Field(..., ge=0.0, description="Abstract compute capacity")
    deployment_id: str | None = Field(default=None, description="Currently assigned deployment")

class GpuAssignment(AuditModel):
    """Assignment of a pod to a GPU."""
    assignment_id: str = Field(..., description="Unique assignment ID")
    gpu_id: str = Field(...)
    pod_id: str = Field(...)
    deployment_id: str = Field(...)
    memory_allocated_mb: int = Field(..., ge=1)
    compute_allocated_pct: float = Field(..., ge=0.0, le=100.0)
    effective_utilization_pct: float | None = Field(default=None, ge=0.0, le=100.0)

class GpuRebalanceEvent(AuditModel):
    """Record of a GPU rebalancing action."""
    event_id: str = Field(...)
    trigger_reason: str = Field(..., description="Why rebalancing was triggered")
    assignments_before: int = Field(..., ge=0)
    assignments_after: int = Field(..., ge=0)
    gpus_involved: list[str] = Field(default_factory=list)
```

#### `cluster.py`

```python
class PodState(TimestampedModel):
    pod_id: str = Field(...)
    deployment_id: str = Field(...)
    status: PodStatus = Field(...)
    node_id: str | None = Field(default=None)
    cpu_request_millicores: int = Field(..., ge=0)
    memory_request_mb: int = Field(..., ge=0)
    gpu_id: str | None = Field(default=None)
    current_cpu_util_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    current_memory_mb: float = Field(default=0.0, ge=0.0)

class NodeState(TimestampedModel):
    node_id: str = Field(...)
    total_cpu_millicores: int = Field(..., ge=1)
    total_memory_mb: int = Field(..., ge=1)
    allocated_cpu_millicores: int = Field(default=0, ge=0)
    allocated_memory_mb: int = Field(default=0, ge=0)
    pods: list[PodState] = Field(default_factory=list)
    gpu_ids: list[str] = Field(default_factory=list)

class DeploymentState(TimestampedModel):
    deployment_id: str = Field(...)
    current_replicas: int = Field(..., ge=0)
    target_replicas: int | None = Field(default=None)
    pods: list[PodState] = Field(default_factory=list)

class ClusterSnapshot(AuditModel):
    """Point-in-time snapshot of the entire simulated cluster."""
    nodes: list[NodeState]
    deployments: list[DeploymentState]
    total_pods: int
    running_pods: int
    pending_pods: int
    gpu_count: int
    gpu_utilization_avg_pct: float | None = Field(default=None)
```

#### `simulation.py`

```python
class TrafficProfile(TimestampedModel):
    """Configuration for a traffic generation pattern."""
    pattern: TrafficPattern
    base_load_rps: float = Field(default=50.0, ge=0.0)
    spike_multiplier: float = Field(default=5.0, ge=1.0)
    noise_std_pct: float = Field(default=5.0, ge=0.0, le=50.0)
    period_minutes: int | None = Field(default=None, ge=1, description="For sine/periodic patterns")
    spike_minute: int | None = Field(default=None, ge=0, description="For step_spike patterns")

class DeploymentSpec(TimestampedModel):
    """Specification of a deployment in the simulation."""
    deployment_id: str = Field(...)
    initial_replicas: int = Field(default=2, ge=1)
    cpu_request_millicores: int = Field(default=500, ge=1)
    memory_request_mb: int = Field(default=512, ge=1)
    gpu_required: bool = Field(default=False)
    traffic_profile: TrafficProfile = Field(default_factory=TrafficProfile)
    scaling_config: ScalingConfig | None = Field(default=None)

class SimulationConfig(TimestampedModel):
    """Top-level configuration for a simulation run."""
    sim_name: str = Field(default="hpa_plus_plus_demo")
    tick_interval_real_seconds: float = Field(default=0.5, ge=0.1)
    seconds_per_simulated_minute: float = Field(default=0.5, ge=0.1)
    total_simulated_minutes: int = Field(default=120, ge=1)
    deployments: list[DeploymentSpec] = Field(default_factory=list)
    seed: int | None = Field(default=None, description="RNG seed for reproducibility")
```

#### `api.py`

```python
from typing import Generic, TypeVar

T = TypeVar("T")

class ApiResponse(BaseModel, Generic[T]):
    """Generic API response wrapper."""
    success: bool = True
    data: T | None = None
    error: str | None = None
    timestamp_utc: datetime = Field(default_factory=datetime.utcnow)

class ErrorResponse(ApiResponse):
    success: bool = False
    error: str = Field(...)
    error_code: str | None = Field(default=None)
```

---

## 7. Inter-Service Contracts (API Boundaries)

Since all services communicate through the shared SQLite database, the "contract" is defined by the schema of the tables they read and write.

### 7.1 Contract Matrix

| Service          | Writes To                                                      | Reads From                                                 | Contract Validates             |
| :--------------- | :------------------------------------------------------------- | :--------------------------------------------------------- | :----------------------------- |
| Cluster Sim (S2) | `metric_samples`, `cluster_snapshots`                          | `simulation_config`, `scaling_decisions`                   | MetricSample, ClusterSnapshot  |
| Forecasting (S3) | `forecast_windows`, `forecast_metadata`                        | `metric_samples`                                           | ForecastWindow                 |
| Controller (S4)  | `scaling_decisions`, `gpu_assignments`, `gpu_rebalance_events` | `forecast_windows`, `gpu_assignments`, `cluster_snapshots` | ScalingDecision, GpuAssignment |
| Dashboard (S5)   | (read-only)                                                    | All tables                                                 | N/A (read-only queries)        |

### 7.2 Contract Tests

Each contract test follows this pattern:

```python
def test_metric_sample_contract():
    """Verify ClusterSim produces valid MetricSample records."""
    # Insert known metric via simulation engine
    engine = SimulationEngine(config=TEST_CONFIG)
    engine.tick()

    # Read from DB
    samples = db.query_metrics(deployment_id="test-deploy", limit=10)

    # Validate every record against schema
    for s in samples:
        validated = MetricSample.model_validate(s)  # raises ValidationError if bad
        assert validated.cpu_utilization_pct <= 100.0
```

These tests run every PR merge. If a team changes the shape of data they write, the contract test catches it.

---

## 8. Database Schema

### 8.1 Tables

All tables use `snake_case` naming, match the Pydantic models exactly, and include an auto-increment `id` primary key + `timestamp_utc` audit column.

```sql
-- Metric samples from simulation
CREATE TABLE metric_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    timestamp_utc TEXT NOT NULL,
    simulated_time_utc TEXT NOT NULL,
    deployment_id TEXT NOT NULL,
    cpu_utilization_pct REAL NOT NULL CHECK(cpu_utilization_pct >= 0 AND cpu_utilization_pct <= 100),
    memory_usage_mb REAL NOT NULL CHECK(memory_usage_mb >= 0),
    requests_per_second REAL NOT NULL CHECK(requests_per_second >= 0),
    gpu_utilization_pct REAL CHECK(gpu_utilization_pct IS NULL OR (gpu_utilization_pct >= 0 AND gpu_utilization_pct <= 100)),
    latency_ms REAL CHECK(latency_ms IS NULL OR latency_ms >= 0)
);
CREATE INDEX idx_metrics_deployment_time ON metric_samples(deployment_id, simulated_time_utc);

-- Forecast windows from Prophet
CREATE TABLE forecast_windows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    timestamp_utc TEXT NOT NULL,
    deployment_id TEXT NOT NULL,
    forecast_time_utc TEXT NOT NULL,
    yhat REAL NOT NULL,
    yhat_lower REAL NOT NULL,
    yhat_upper REAL NOT NULL,
    model_version TEXT NOT NULL,
    training_window_minutes INTEGER NOT NULL,
    training_end_time_utc TEXT NOT NULL
);
CREATE INDEX idx_forecast_deployment ON forecast_windows(deployment_id, forecast_time_utc);

-- Forecast metadata (one per training run)
CREATE TABLE forecast_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    model_version TEXT NOT NULL UNIQUE,
    deployment_id TEXT NOT NULL,
    training_start_utc TEXT NOT NULL,
    training_end_utc TEXT NOT NULL,
    data_window_minutes INTEGER NOT NULL,
    rmse REAL CHECK(rmse IS NULL OR rmse >= 0),
    mae REAL CHECK(mae IS NULL OR mae >= 0),
    seasonality_daily INTEGER NOT NULL DEFAULT 1,
    seasonality_weekly INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'success' CHECK(status IN ('success', 'failed', 'fallback'))
);

-- Scaling decisions from controller
CREATE TABLE scaling_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    decision_id TEXT NOT NULL UNIQUE,
    timestamp_utc TEXT NOT NULL,
    deployment_id TEXT NOT NULL,
    simulated_time_utc TEXT NOT NULL,
    forecast_id TEXT,
    current_pod_count INTEGER NOT NULL CHECK(current_pod_count >= 0),
    target_pod_count INTEGER NOT NULL CHECK(target_pod_count >= 0),
    action TEXT NOT NULL CHECK(action IN ('scale_up', 'scale_down', 'hold')),
    risk_score REAL NOT NULL CHECK(risk_score >= 0 AND risk_score <= 1),
    confidence_score REAL NOT NULL CHECK(confidence_score >= 0 AND confidence_score <= 1),
    forecast_yhat REAL NOT NULL,
    forecast_lower REAL NOT NULL,
    forecast_upper REAL NOT NULL,
    formula_raw_target REAL NOT NULL,
    formula_confidence_factor REAL NOT NULL,
    formula_risk_bias REAL NOT NULL,
    formula_final_before_clamp REAL NOT NULL,
    executed INTEGER NOT NULL DEFAULT 0,
    reason TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_decisions_deployment ON scaling_decisions(deployment_id, simulated_time_utc);

-- GPU assignments from GPU scheduler
CREATE TABLE gpu_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    timestamp_utc TEXT NOT NULL,
    assignment_id TEXT NOT NULL UNIQUE,
    gpu_id TEXT NOT NULL,
    pod_id TEXT NOT NULL,
    deployment_id TEXT NOT NULL,
    memory_allocated_mb INTEGER NOT NULL CHECK(memory_allocated_mb >= 1),
    compute_allocated_pct REAL NOT NULL CHECK(compute_allocated_pct >= 0 AND compute_allocated_pct <= 100),
    effective_utilization_pct REAL CHECK(effective_utilization_pct IS NULL OR (effective_utilization_pct >= 0 AND effective_utilization_pct <= 100))
);

-- GPU rebalance events
CREATE TABLE gpu_rebalance_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    timestamp_utc TEXT NOT NULL,
    event_id TEXT NOT NULL UNIQUE,
    trigger_reason TEXT NOT NULL,
    assignments_before INTEGER NOT NULL,
    assignments_after INTEGER NOT NULL,
    gpus_involved TEXT NOT NULL DEFAULT '[]'  -- JSON array of GPU IDs
);

-- Cluster snapshots (periodic state dumps)
CREATE TABLE cluster_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    timestamp_utc TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,  -- JSON serialization of ClusterSnapshot
    total_pods INTEGER NOT NULL,
    running_pods INTEGER NOT NULL,
    pending_pods INTEGER NOT NULL,
    gpu_count INTEGER NOT NULL,
    gpu_utilization_avg_pct REAL
);

-- Simulation config (active configuration)
CREATE TABLE simulation_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    config_json TEXT NOT NULL,  -- JSON serialization of SimulationConfig
    active INTEGER NOT NULL DEFAULT 0
);

-- Scaling configs per deployment
CREATE TABLE scaling_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    deployment_id TEXT NOT NULL UNIQUE,
    min_replicas INTEGER NOT NULL DEFAULT 1,
    max_replicas INTEGER NOT NULL DEFAULT 20,
    baseline_per_pod REAL NOT NULL DEFAULT 100.0,
    risk_asymmetry_factor REAL NOT NULL DEFAULT 5.0,
    cooldown_seconds INTEGER NOT NULL DEFAULT 60
);
```

### 8.2 Initialisation Script

```python
# app/db/init.py
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "hpap.db"

SCHEMA_SQL = """
-- (all CREATE TABLE statements from above)
"""

def init_db(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn
```

---

## 9. Data Flow & Pipeline Sequence

### 9.1 Standard Loop (every tick)

```
1. SIM tick
   SimulationEngine.tick()
   ├── Update cluster state (nodes, pods, deployments)
   ├── Generate metrics from traffic profile
   └── Write MetricSample rows to DB

2. FORECAST (every N ticks, e.g., every 5 simulated minutes)
   ForecastPipeline.run_once()
   ├── Read recent MetricSamples from DB (last 60 min)
   ├── Resample to uniform time grid
   ├── Train Prophet (or update existing model)
   ├── Predict next 30 minutes
   └── Write ForecastWindow rows to DB

3. CONTROL (every tick)
   PredictiveController.evaluate()
   ├── Read latest ForecastWindow from DB
   ├── Read current pod count from cluster state
   ├── Compute target_pod_count with risk-aware formula
   ├── Check against min/max bounds
   └── Write ScalingDecision to DB

4. GPU SCHEDULE (every N ticks)
   GpuScheduler.rebalance()
   ├── Read pending GPU assignments and GPU specs
   ├── Run bin-packing algorithm
   ├── Resolve contention
   └── Write GpuAssignment records to DB

5. DASHBOARD (continuous, polling every 2s)
   Dashboard reads all tables and renders
```

### 9.2 Pipeline Modes

| Mode          | Description                                                                         | Make Target      |
| :------------ | :---------------------------------------------------------------------------------- | :--------------- |
| **data-only** | Sim writes metrics, stops. Forecast and controller run analytically.                | `make run-data`  |
| **full-loop** | Sim runs, forecast runs every N ticks, controller runs every tick, dashboard polls. | `make demo`      |
| **benchmark** | Full-loop + Locust load generation. Compare HPA++ vs reactive HPA.                  | `make demo-load` |

---

## 10. Development Schedule & Milestones

### Phase 1: Foundation (Days 1–2)

| Day       | Sanzida (S1→S2)                                    | Daiyaan (S3→S4)                                                   | Ahmed (S5→S6)                                    |
| :-------- | :------------------------------------------------- | :---------------------------------------------------------------- | :----------------------------------------------- |
| **1**     | S1: Schema definitions, DB layer, init script      | S1: Review schemas, set up forecasting directory, install Prophet | S1: Review schemas, set up dashboard scaffolding |
| **1**     | S1: Pydantic models + unit tests                   | S3: Prophet wrapper + train/predict on synthetic data             | S5: Streamlit app skeleton, DB reader            |
| **2**     | S2: Cluster state model, basic node/pod simulation | S3: Feature extraction from DB, forecast pipeline                 | S5: Traffic + pod scaling panels                 |
| **2**     | S2: Metric generator, traffic profiles             | S3: Fallback handling, model versioning                           | S5: GPU + decision log panels                    |
| **Check** | S1 ✅, S2 basic tick ✅                            | S3: train + predict on synthetic data ✅                          | S5: panels render with mock data ✅              |

### Phase 2: Core Logic (Days 3–5)

| Day       | Sanzida                                  | Daiyaan                                       | Ahmed                                                  |
| :-------- | :--------------------------------------- | :-------------------------------------------- | :----------------------------------------------------- |
| **3**     | S2: Simulation loop with pause/resume    | S4a: PredictiveController compute_target_pods | S5: Simulation controls, auto-refresh                  |
| **3**     | S2: MockForecastStore + MockClusterState | S4a: Risk scoring, confidence-aware formula   | S5: Dark theme, layout polish                          |
| **4**     | S2: Multiple deployments, GPU pool       | S4a: ScaleExecutor (sim mode + dry-run)       | S6: Contract test suite setup                          |
| **4**     | S2: Integration test with real DB        | S4b: GPU scheduler, bin-packing algorithm     | S6: Boundary tests (sim→forecast, forecast→controller) |
| **5**     | S2: Load generator integration (Locust)  | S4b: GPU rebalancing, contention detection    | S6: E2E pipeline test, Makefile targets                |
| **Check** | S2 ✅                                    | S4: formula validated + GPU sched tested ✅   | S6: contract + e2e tests pass ✅                       |

### Phase 3: Integration & Polish (Days 6–7)

| Day      | Sanzida                                               | Daiyaan                                        | Ahmed                                  |
| :------- | :---------------------------------------------------- | :--------------------------------------------- | :------------------------------------- |
| **6**    | Polish sim: edge cases, error handling                | Polish controller: edge cases, float precision | Wire everything: demo bootstrap script |
| **6**    | Test with all traffic profiles                        | Cross-boundary tests with real sim data        | Test full pipeline end-to-end          |
| **7**    | Bug fixes, README contributions                       | Bug fixes, README contributions                | Demo walkthrough, Locust benchmarks    |
| **7**    | **Hard freeze** — integration testing, bug fixes only |                                                |                                        |
| **Demo** | Run `make demo` — present live system                 |                                                |                                        |

---

## 11. Integration & Demo Workflow

### 11.1 Integration Sequence

1. **Day 1–2:** All teams work independently against mocks. No integration yet.
2. **Day 3:** S2 simulation writes real data. S3 switches from mock metrics to real DB reads. Validate contract test.
3. **Day 4:** S4 switches from mock forecasts to real DB reads. Validate contract test.
4. **Day 5:** S5 dashboard reads real data from all tables. E2E test passes.
5. **Day 6–7:** Full integration. Demo script launches everything.

### 11.2 Mock Strategy

| Service                | Mock Provided By                      | What It Returns                                           |
| :--------------------- | :------------------------------------ | :-------------------------------------------------------- |
| Metrics (for S3)       | S2 MockForecastStore                  | Synthetic MetricSample rows in DB with realistic patterns |
| Forecast (for S4)      | S3 MockForecastStore (or S2 fallback) | ForecastWindow with yhat ± 20% of current metric          |
| Cluster State (for S5) | S2 MockClusterState                   | ClusterSnapshot with N nodes, M pods, basic GPU info      |

### 11.3 Demo Runbook

```bash
# From project root:
make install         # Install dependencies
make db-init         # Create fresh database
make demo            # Launch full system

# Expected output:
# [SIM] Simulation started — profile: flash_sale, speed: 10x
# [FORECAST] Forecast pipeline started — interval: 60s
# [CTRL] Controller active — watching deployments: [web-app, api-gateway]
# [DASHBOARD] Open http://localhost:8501 to view dashboard
#
# Press Ctrl+C to stop all services gracefully.
```

### 11.4 Benchmark (Optional Enhancement)

Run Locust with two configurations:

```bash
# Benchmark 1: Reactive HPA only
make benchmark -- --mode reactive

# Benchmark 2: HPA++ predictive
make benchmark -- --mode predictive

# Compare:
# - P99 latency during spike
# - Total pod-minutes consumed
# - Time-to-scale after spike onset
```

---

## 12. Verification & Acceptance Criteria

### 12.1 Per-Service Gates

| Service             | Gate                                                        | How to Verify                                                                                                                       |
| :------------------ | :---------------------------------------------------------- | :---------------------------------------------------------------------------------------------------------------------------------- |
| **Schema Registry** | All models defined, validated, unit tested                  | `pytest app/schemas/ -v` — all pass                                                                                                 |
| **Database**        | Tables created, CRUD works, indices exist                   | `pytest app/db/ -v` — all pass                                                                                                      |
| **Simulation**      | N ticks → N metric rows in DB, all profiles distinguishable | `python -m app.simulation.engine --ticks 60 --profile flash_sale && sqlite3 app/data/hpap.db 'SELECT count(*) FROM metric_samples'` |
| **Forecasting**     | Train + predict produces bounded forecast                   | `pytest app/forecasting/ -v` — tests pass                                                                                           |
| **Controller**      | Target pods in [min, max], deterministic formula            | `pytest app/controller/ -v` — tests pass                                                                                            |
| **GPU Scheduler**   | No GPU overallocated, all pods assigned                     | `pytest app/controller/test_gpu_scheduler.py -v`                                                                                    |
| **Dashboard**       | All panels render, refresh works, empty DB doesn't crash    | Manual: `streamlit run app/dashboard/app.py`                                                                                        |
| **Integration**     | Contract tests pass, E2E pipeline completes                 | `make test` — exit 0                                                                                                                |

### 12.2 End-to-End Acceptance

| #     | Criterion                                                | How to Verify                                                             |
| :---- | :------------------------------------------------------- | :------------------------------------------------------------------------ |
| E2E-1 | System starts and runs without errors                    | `make demo` launches, no tracebacks                                       |
| E2E-2 | Dashboard shows live-updating data within 5s             | Visual inspection                                                         |
| E2E-3 | Forecast appears before traffic spike (3+ min lead time) | Dashboard "actual vs predicted" chart shows forecast rising before actual |
| E2E-4 | Scaling decision logged for every forecast cycle         | Query: `SELECT count(*) FROM scaling_decisions` > 0                       |
| E2E-5 | GPU assignments respect capacity limits                  | Query: no assignment where sum(allocated) > total capacity per GPU        |
| E2E-6 | All contract tests pass                                  | `make test-contracts` — exit 0                                            |
| E2E-7 | All boundary tests pass                                  | `make test-boundaries` — exit 0                                           |
| E2E-8 | Full pipeline completes in < 30s                         | `make test-e2e` — runs under 30s                                          |

### 12.3 Demo Presentation Checklist

- [ ] `make install && make db-init && make demo` — staged and ready
- [ ] Dashboard visible on projector/large screen (1920x1080)
- [ ] Simulation running with visible traffic profile (flash sale recommended — most visually dramatic)
- [ ] Forecast confidence bands clearly visible
- [ ] Scaling decisions appearing in the decision log
- [ ] GPU allocation heatmap showing assignments
- [ ] At least one traffic spike occurs during the presentation window
- [ ] Locust benchmark charts ready (if benchmarking)

---

## Appendix A: Directory Structure

```
HPA-pp/
├── app/
│   ├── __init__.py
│   ├── main.py                    # Optional entry point
│   ├── schemas/                   # S1 — Shared schema registry
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── metrics.py
│   │   ├── forecast.py
│   │   ├── decisions.py
│   │   ├── gpu.py
│   │   ├── cluster.py
│   │   ├── simulation.py
│   │   ├── api.py
│   │   └── enums.py
│   ├── db/                        # S1 — Database layer
│   │   ├── __init__.py
│   │   ├── manager.py
│   │   ├── init.py
│   │   ├── migrations/
│   │   │   └── 001_initial.py
│   │   └── queries.py
│   ├── simulation/                # S2 — Cluster Simulation
│   │   ├── __init__.py
│   │   ├── engine.py
│   │   ├── cluster_state.py
│   │   ├── metrics_generator.py
│   │   ├── traffic_profiles.py
│   │   ├── mocks.py
│   │   └── locustfile.py
│   ├── forecasting/               # S3 — Forecasting Engine
│   │   ├── __init__.py
│   │   ├── model.py
│   │   ├── features.py
│   │   ├── pipeline.py
│   │   └── fallback.py
│   ├── controller/                # S4 — Predictive Controller + GPU Scheduler
│   │   ├── __init__.py
│   │   ├── scaler.py
│   │   ├── executor.py
│   │   ├── gpu_scheduler.py
│   │   └── config.py
│   ├── dashboard/                 # S5 — Live Dashboard
│   │   ├── __init__.py
│   │   ├── app.py
│   │   ├── panels/
│   │   │   ├── traffic.py
│   │   │   ├── scaling.py
│   │   │   ├── gpu.py
│   │   │   ├── decisions.py
│   │   │   ├── cluster.py
│   │   │   └── controls.py
│   │   ├── data.py
│   │   └── assets/
│   └── integration/               # S6 — Integration, Contracts, Demo
│       ├── __init__.py
│       ├── contracts/
│       │   ├── test_metric_contract.py
│       │   ├── test_forecast_contract.py
│       │   ├── test_decision_contract.py
│       │   └── test_gpu_contract.py
│       ├── boundaries/
│       │   ├── test_sim_to_forecast.py
│       │   ├── test_forecast_to_controller.py
│       │   └── test_controller_to_dashboard.py
│       ├── e2e/
│       │   └── test_full_pipeline.py
│       ├── demo.py
│       └── locust/
│           └── locustfile.py
├── data/                          # Runtime data (gitignored)
│   └── hpap.db
├── tests/                         # Additional shared test fixtures
│   ├── conftest.py
│   └── fixtures/
├── requirements.txt
├── pyproject.toml
├── Makefile
├── README.md
└── HPA_Plus_Plus_Concept_Note.md
```

---

## Appendix B: Dependency Versions (requirements.txt)

```txt
# Core
python>=3.11
pydantic>=2.0
sqlite3-worker>=0.1

# Simulation
numpy>=1.24
pandas>=2.0
scipy>=1.10

# Forecasting
prophet>=1.1
scikit-learn>=1.3

# Dashboard
streamlit>=1.28
plotly>=5.17

# Testing
pytest>=7.4
pytest-asyncio>=0.21
pytest-cov>=4.1

# Dev tools
ruff>=0.1
mypy>=1.7

# Optional: Load testing
locust>=2.19

# Optional: Kubernetes (real mode)
kubernetes>=27.2
```

---

## Appendix C: Quick Reference — Makefile Commands

```makefile
.PHONY: install test lint clean db-init demo demo-load test-contracts test-e2e

install:
    pip install -r requirements.txt

test:
    pytest app/ -v --cov=app

test-contracts:
    pytest app/integration/contracts/ -v

test-e2e:
    pytest app/integration/e2e/ -v --timeout=60

lint:
    ruff check app/

db-init:
    python -m app.db.init

demo:
    python -m app.integration.demo

demo-load:
    python -m app.integration.demo --load

clean:
    rm -rf app/data/hpap.db __pycache__ .pytest_cache
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
```

---

_End of specification sheet. Each developer should start by reading Section 5 (their subtasks), Section 6 (shared schemas), and Section 8 (database schema). All other sections provide context and integration requirements._
