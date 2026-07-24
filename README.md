# HPA++

**AI-Powered Predictive Auto Scaling & GPU Scheduling for Kubernetes**

Replaces Kubernetes' reactive HPA with forecast-driven, risk-aware scaling decisions. Simulates cluster environments, generates realistic traffic, trains Prophet forecasts, and makes proactive scaling decisions with confidence awareness.

## Architecture

```
services/
├── simulation/     — Cluster simulation engine (FastAPI :8001)
│   ├── app/
│   │   ├── engine.py            — Async tick loop with start/pause/resume/stop
│   │   ├── cluster_state.py     — Bin-packing pod scheduling, GPU tracking
│   │   ├── metrics_generator.py — Non-linear CPU/memory/GPU/latency from RPS
│   │   ├── traffic_profiles.py  — 7 traffic patterns (steady, sine, spike, …)
│   │   ├── anomalies/           — 61 anomaly types for chaos injection
│   │   │   ├── engine.py        — Anomaly lifecycle (check/apply/revert)
│   │   │   ├── base.py          — AnomalyEffect, handler registry
│   │   │   └── handlers/        — 9 domain files, one per failure class
│   │   ├── routes.py            — REST API + WebSocket endpoints
│   │   ├── events.py            — WebSocket event broadcaster
│   │   ├── main.py              — FastAPI app factory with lifespan
│   │   └── dependencies.py      — Singleton wiring
│   └── tests/                   — 146 tests (unit + integration + WebSocket + anomalies)
├── forecasting/   — Multivariate prediction engine — Prophet/CTGAN/Transformer (FastAPI :8002) [WIP]
├── controller/    — Predictive controller + GPU scheduler (FastAPI :8003) [WIP]
├── integration/   — Integration layer (FastAPI :8000) [WIP]
└── dashboard/     — Streamlit dashboard (:8501) [WIP]

shared/
├── db/            — SQLite with WAL mode, full DDL, CRUD manager
│   ├── init.py    — 12 tables: metrics, forecasts, decisions, snapshots, configs
│   └── manager.py — query_metrics, insert_forecast, upsert_config, etc.
├── schemas/       — Pydantic v2 schema registry (single source of truth)
│   ├── metrics.py, forecast.py, decisions.py, gpu.py, cluster.py, …
│   └── api.py     — ApiResponse[T] generic envelope
├── simulation.py  — SimulationConfig, DeploymentSpec, TrafficProfile models
├── enums.py       — PodStatus, TrafficPattern, RiskLevel, ScalingAction
└── base.py        — BaseModel config, timestamp mixins

data/
└── synthetic_hpa_traffic_all_clusters_365d.csv  — 525K rows, 5 clusters, 365 days
```

## Simulation Service

The simulation service (`services/simulation/`) emulates a Kubernetes cluster with nodes, pods, deployments, and GPU resources. It produces realistic metric time-series from configurable traffic profiles.

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/health` | Health check |
| GET | `/api/v1/metrics` | Query metric samples (with deployment/time filters) |
| GET | `/api/v1/metrics/latest` | Latest N metric samples |
| GET | `/api/v1/cluster/state` | Full cluster snapshot |
| GET | `/api/v1/cluster/nodes` | List of node states |
| GET | `/api/v1/cluster/deployments` | List of deployment states |
| GET | `/api/v1/sim/status` | Simulation status |
| POST | `/api/v1/sim/start` | Start simulation (optional config override) |
| POST | `/api/v1/sim/pause` | Pause simulation |
| POST | `/api/v1/sim/resume` | Resume simulation |
| POST | `/api/v1/sim/stop` | Stop simulation |
| POST | `/api/v1/sim/config` | Update config (when stopped/paused) |

### WebSocket Event Streams

Real-time push-based streaming for other microservices:

| Path | Channel | Event | Frequency |
|------|---------|-------|-----------|
| `/api/v1/ws/metrics` | `metrics` | Tick data with all samples | Every tick (~100ms) |
| `/api/v1/ws/cluster` | `cluster` | Cluster snapshot | Every tick |
| `/api/v1/ws/status` | `status` | Lifecycle transitions | On start/pause/resume/stop/complete |

**Client usage (5 lines):**
```python
import asyncio, websockets, json

async def stream():
    async with websockets.connect("ws://simulation:8001/api/v1/ws/metrics") as ws:
        async for msg in ws:
            data = json.loads(msg)  # {"channel":"metrics","event":"tick",…}
            print(data["data"]["samples"])
```

### Anomaly Injection (61 types)

Inject realistic cluster failures into the simulation. Anomalies mutate cluster state and distort metrics via an `AnomalyEffect` pipeline each tick:

```
_tick_loop():
  1. anomaly_engine.process_tick() → activates new, applies active, expires old
  2. MetricsGenerator.generate_batch(anomaly_effect=effect)
  3. DB persist + broadcast
```

**API:**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/anomalies` | List all registered anomaly definitions |
| GET | `/api/v1/anomalies/active` | List currently active anomalies |
| POST | `/api/v1/anomalies` | Register a new anomaly definition |
| DELETE | `/api/v1/anomalies/{id}` | Remove a definition (active expires naturally) |

**Example — schedule a node failure at minute 60:**
```bash
curl -X POST http://localhost:8001/api/v1/anomalies \
  -H 'Content-Type: application/json' \
  -d '{
    "anomaly_id": "node0-crash",
    "anomaly_type": "node_crash",
    "target": "node-0",
    "trigger_type": "scheduled",
    "trigger_value": 60.0,
    "duration_minutes": 15.0,
    "severity": 1.0
  }'
```

**Failure domains (61 anomalies across 9 categories):**

| Domain | Count | Examples |
|--------|-------|---------|
| Node/CPU/RAM | 10 | node_crash, cpu_throttle, memory_leak, ram_corruption |
| GPU | 10 | gpu_xid_error, gpu_oom, gpu_ecc_cascade, gpu_nvlink_failure |
| Network | 8 | network_partition, packet_loss, dns_failure, lb_failure |
| Storage | 5 | pv_failure, iops_throttle, disk_full, quota_exceeded |
| Pod/Container | 8 | crash_loop, oom_kill, liveness_fail, sidecar_crash |
| Deploy/Config | 6 | rollout_fail, config_drift, affinity_violation |
| Traffic/Load | 6 | traffic_spike, load_imbalance, thundering_herd |
| Control Plane | 4 | api_server_slow, scheduler_fail, etcd_slow |
| Security | 4 | crypto_miner, data_exfil, rbac_break, cert_expiry |

Each anomaly applies handlers that either mutate `ClusterStateManager` (evict pods, block nodes) or return metric modifiers (RPS multipliers, CPU offsets, latency overrides). Effects merge across concurrent anomalies.

### Traffic Profiles

| Pattern | Description |
|---------|-------------|
| `steady` | Constant load at base_rps |
| `sine_wave` | Sinusoidal oscillation with configurable period |
| `step_spike` | Sudden spike at spike_minute for spike_duration |
| `flash_sale` | Gradual ramp to peak, then exponential decay |
| `exam_start` | Ramp-up, sustain at peak, then drop |
| `random_walk` | Brownian motion with mean-reversion |

### Simulation Engine

- **Tick rate**: Configurable (default 0.5s real = 1 simulated minute)
- **Lifecycle**: start → tick loop → pause/resume → stop
- **State**: Cluster state in memory; metrics + snapshots persisted to SQLite every tick
- **Snapshot period**: Full cluster snapshot every 10 ticks
- **GPU**: Per-device tracking, GPU utilization correlated to CPU

### Running

```bash
python -m services.simulation.app.main
# or via docker-compose:
docker compose up simulation
```

### Tests

```bash
cd /path/to/HPA-pp
PYTHONPATH=. python -m pytest services/simulation/tests/ -v
```

**214 tests** covering:
- Database CRUD (init, insert, query, upsert, insert_many)
- Traffic profiles (all 7 patterns, registry, edge cases)
- Cluster state (node ops, pod scheduling, GPU tracking, scaling, snapshots, GPU assignment)
- Metrics generator (CPU/memory/GPU/latency models, noise, ranges)
- Engine lifecycle (start/pause/resume/stop, tick loop, completion)
- REST API (14 endpoints, error handling, CORS, anomaly CRUD, scale, GPU assign)
- WebSocket (broadcaster, 3 channels, multiple clients, disconnect recovery)
- Anomaly engine (activation, expiry, revert, merge, 61 handler registration, integration)
- PredictiveController (peak extraction, confidence, risk, action, fallbacks)
- ScaleExecutor (simulation/dry-run, error recovery, rollback)
- ReactiveFallback (CPU threshold, hysteresis edge cases)
- GpuScheduler (bin-pack/spread strategies, contention, rebalance, edge cases)
- Sim+Controller integration (full evaluate→persist→execute pipeline with mocked forecasts)
- Sim+Anomaly integration (metrics distortion, scheduling with blocked nodes)
- Controller route smoke tests (evaluate + GPU assign HTTP endpoints)

Total: **155 simulation + 59 controller = 214 passing tests**

## Prediction Engine Contract

The forecasting service (`services/forecasting/`) predicts **multivariate system state** — not just RPS. Every model (Prophet, CTGAN, transformer, naive fallback) produces the same output shape. The controller and dashboard never touch the underlying model.

### Training Data

`data/synthetic_hpa_traffic_all_clusters_365d.csv` — 525K rows, 5 clusters (ecommerce, exam_system, genai_inference, streaming, university_portal), 365 days of 5-minute interval metrics with labeled anomaly events:

| Feature | Type | Consumer |
|---------|------|----------|
| `requests_per_second` | float | Controller → pod target |
| `cpu_utilization_pct` | float | Controller → reactive fallback; Dashboard |
| `gpu_utilization_pct` | float | GPU scheduler → rebalance decisions |
| `gpus_in_use` | int | GPU scheduler → capacity planning |
| `active_pods` | int | Controller → sanity check |
| `concurrent_users` | float | Dashboard |
| `requests_per_5min` | float | Dashboard (smoothed) |
| `is_flash_event_spike` | bool | Dashboard → anomaly highlight |
| `is_outage_event` | bool | Dashboard → anomaly highlight |
| `is_memleak_event` | bool | Dashboard → anomaly highlight |

### Output — the `ForecastTrajectory` schema

Every endpoint returns this shape. The `features` dict keys are column names from the training data — a CTGAN model might predict all 17, Prophet might only predict `requests_per_second`.

```json
{
  "forecast_id": "f47ac10b-...",
  "deployment_id": "web-app",
  "model_type": "ctgan",
  "features_predicted": ["requests_per_second", "cpu_utilization_pct",
                         "gpu_utilization_pct", "active_pods"],
  "points": [
    {
      "minute": 21,
      "features": {
        "requests_per_second": { "value": 145.2 },
        "cpu_utilization_pct": { "value": 45.0 },
        "gpu_utilization_pct": { "value": 24.5 },
        "active_pods": { "value": 5 }
      }
    }
  ],
  "summary": {
    "peak_requests_per_second": { "value": 198.3 },
    "peak_gpu_utilization_pct": { "value": 65.0 },
    "trend": "rising",
    "volatility": 0.15,
    "uncertainty_pct": null
  },
  "quality": {
    "status": "success",
    "rmse": {"requests_per_second": 12.3, "cpu_utilization_pct": 4.5},
    "mape_pct": {"requests_per_second": 6.2}
  }
}
```

### How each consumer reads it

**Controller** (`services/controller/app/scaler.py`):
```python
peak = forecast["summary"]["peak_requests_per_second"]["value"]
raw_target = ceil(peak / config.baseline_per_pod)  # "Pods needed at peak"

# Risk-aware bias from confidence (if available)
upper = forecast["points"][0]["features"]["requests_per_second"].get("upper")
if upper:
    ci_width = (upper - lower) / value
    risk_bias = ci_width * config.risk_asymmetry_factor
else:
    risk_bias = config.risk_asymmetry_factor * 0.2  # neutral default

# Trend urgency
if forecast["summary"]["trend"] == "rising":
    risk_bias += 1.0  # "Getting worse — scale proactively"

final = clamp(raw_target + risk_bias, config.min_replicas, config.max_replicas)
```

**GPU scheduler** (`services/controller/app/gpu_scheduler.py`):
```python
peak_gpu = forecast["summary"].get("peak_gpu_utilization_pct")
if peak_gpu and peak_gpu["value"] > 80.0:
    gpu_scheduler.rebalance(trigger_reason="predicted_gpu_overcommit")
```

**Dashboard** (`services/dashboard/app/main.py`):
```python
rps_values = [p["features"]["requests_per_second"]["value"] for p in points]
cpu_values = [p["features"]["cpu_utilization_pct"]["value"] for p in points]
gpu_values = [p["features"]["gpu_utilization_pct"]["value"] for p in points]
# Plot all three on their respective panels
```

### Fallback chain

| Data available | `quality.status` | Controller behavior |
|----------------|------------------|---------------------|
| ≥60 min history | `success` | Full predictive + risk-aware |
| 10–59 min      | `success` | Wider confidence → higher risk bias |
| <10 min        | `fallback` | Naive forecast (flat at last value). Controller sets `risk_asymmetry_factor × 2` |
| No data        | `failed` | Reactive fallback only (CPU threshold-based) |

The controller checks `quality.status` every evaluation cycle and adjusts its behaviour automatically.

### API Endpoints (forecasting service, `:8002`)

| Method | Path | Returns |
|--------|------|---------|
| GET | `/api/v1/forecast/trajectory?deployment_id=X&horizon_minutes=30` | `ForecastTrajectory` |
| GET | `/api/v1/forecast/latest?deployment_id=X` | Single-point forecast |
| POST | `/api/v1/forecast/run` | Trigger one prediction cycle |

The ML engineer chooses the model (Prophet, CTGAN, transformer, or ensemble).
The controller, GPU scheduler, and dashboard teams build against this schema
using the naive fallback until the real model is ready.

## Development

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run simulation service
PYTHONPATH=. uvicorn services.simulation.app.main:create_app --reload --port 8001

# Run all tests
PYTHONPATH=. pytest services/ -v
```