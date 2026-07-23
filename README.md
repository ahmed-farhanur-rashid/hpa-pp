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
│   │   ├── routes.py            — REST API + WebSocket endpoints
│   │   ├── events.py            — WebSocket event broadcaster
│   │   ├── main.py              — FastAPI app factory with lifespan
│   │   └── dependencies.py      — Singleton wiring
│   └── tests/                   — 121 tests (unit + integration + WebSocket)
├── forecasting/   — Prophet forecasting engine (FastAPI :8002) [WIP]
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

**121 tests** covering:
- Database CRUD (init, insert, query, upsert, insert_many)
- Traffic profiles (all 7 patterns, registry, edge cases)
- Cluster state (node ops, pod scheduling, GPU tracking, scaling, snapshots)
- Metrics generator (CPU/memory/GPU/latency models, noise, ranges)
- Engine lifecycle (start/pause/resume/stop, tick loop, completion)
- REST API (12 endpoints, error handling, CORS)
- WebSocket (broadcaster, 3 channels, multiple clients, disconnect recovery)

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
