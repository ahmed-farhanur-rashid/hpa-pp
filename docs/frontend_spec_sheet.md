# HPA++ Dashboard — Frontend Specification Sheet

## Real-Time Monitoring Dashboard for Predictive Auto Scaling & GPU Scheduling

| Field | Details |
| :--- | :--- |
| **Project** | HPA++ Dashboard |
| **Service Dir** | `services/dashboard/` |
| **Framework** | Streamlit + Plotly (primary), React + D3/Recharts (optional extension) |
| **Data Source** | Shared SQLite DB (direct reads) + REST APIs from simulation/forecasting/controller services |
| **Style** | Dark theme, professional monitoring aesthetic |
| **Target Screen** | 1920x1080 (projector/demo), responsive down to 1280x720 |

---

## Table of Contents

1. [Design Principles](#1-design-principles)
2. [Style Guide](#2-style-guide)
3. [Component Tree & Layout](#3-component-tree--layout)
4. [Panel Specifications](#4-panel-specifications)
5. [Data Integration Specification](#5-data-integration-specification)
6. [State Management](#6-state-management)
7. [Navigation & Interaction Design](#7-navigation--interaction-design)
8. [Error & Edge Case Handling](#8-error--edge-case-handling)
9. [Performance Requirements](#9-performance-requirements)
10. [API Contract](#10-api-contract)

---

## 1. Design Principles

### 1.1 Core Principles

| # | Principle | Description |
| :--- | :--- | :--- |
| 1 | **Data tells the story** | Every visual element exists to communicate a metric or relationship. Decoration is minimal. The data IS the aesthetic. |
| 2 | **Actual vs Predicted** | The central narrative of HPA++ is comparing what happened vs what was forecast. Every panel that can show this contrast must do so. |
| 3 | **Explainability first** | Every scaling decision must be traceable to its inputs. Users should never wonder "why did it do that?" - the answer is one click away. |
| 4 | **Graceful degradation** | If a data source is unavailable, the affected panel degrades gracefully rather than crashing the whole dashboard. |
| 5 | **Real-time feel** | The dashboard auto-refreshes with smooth transitions. No full-page reloads, no flickering. |

### 1.2 Domain Boundaries

**OWN:** Visualization, layout, user input, navigation, responsive behaviour, animation, theme, data fetching, error display.

**DO NOT OWN:** Business logic (scaling formulas, risk computation, metric generation), raw data transformations, database schema changes, ML model training or inference.

**RULE:** If it requires math beyond formatting or aggregation for display, it belongs in the controller or forecasting service. File a spec request - never implement a crude version locally.

---

## 2. Style Guide

### 2.1 Colour Palette

Dark theme inspired by Grafana and Kubernetes Dashboard.

| Token | Hex | Usage |
| :--- | :--- | :--- |
| `--bg-primary` | `#0D1117` | Main background (page) |
| `--bg-secondary` | `#161B22` | Card/panel backgrounds |
| `--bg-tertiary` | `#21262D` | Input fields, table rows |
| `--bg-hover` | `#30363D` | Hover state for interactive elements |
| `--border-default` | `#30363D` | Borders, dividers |
| `--text-primary` | `#E6EDF3` | Primary text |
| `--text-secondary` | `#8B949E` | Secondary text, labels |
| `--text-muted` | `#484F58` | Disabled text, placeholders |
| `--accent-blue` | `#58A6FF` | Primary accent, links, active state |
| `--accent-green` | `#3FB950` | Healthy/adequate state, scale-up |
| `--accent-yellow` | `#D29922` | Warning, scaling imminent |
| `--accent-red` | `#F85149` | Danger, under-provisioned |
| `--accent-purple` | `#BC8CFF` | GPU-related visuals |
| `--accent-cyan` | `#39D2C0` | Forecast lines, predicted values |
| `--chart-line-actual` | `#58A6FF` | Actual metric line |
| `--chart-line-forecast` | `#39D2C0` | Forecast metric line |
| `--chart-band-forecast` | `rgba(57, 210, 192, 0.15)` | Forecast confidence band fill |
| `--chart-line-pods-current` | `#58A6FF` | Current pod count line |
| `--chart-line-pods-target` | `#F85149` | Target pod count line (dashed) |

### 2.2 Typography

| Element | Font | Size | Weight | Colour |
| :--- | :--- | :--- | :--- | :--- |
| Page title | Inter / system sans-serif | 24px | 700 | `--text-primary` |
| Card title | Inter / system sans-serif | 16px | 600 | `--text-primary` |
| Metric value | JetBrains Mono / monospace | 32px | 700 | `--text-primary` |
| Metric label | Inter / system sans-serif | 12px | 500 | `--text-secondary` |
| Table header | Inter / system sans-serif | 12px | 600 | `--text-secondary` |
| Table cell | Inter / system sans-serif | 13px | 400 | `--text-primary` |
| Small note | Inter / system sans-serif | 11px | 400 | `--text-muted` |
| Button text | Inter / system sans-serif | 14px | 500 | `--text-primary` |

### 2.3 Spacing

| Token | Value | Usage |
| :--- | :--- | :--- |
| `--space-xs` | 4px | Inner padding for tight elements |
| `--space-sm` | 8px | Between related elements |
| `--space-md` | 16px | Standard padding inside cards |
| `--space-lg` | 24px | Between cards, section margins |
| `--space-xl` | 32px | Page margins, large separators |
| `--radius-sm` | 4px | Small elements, badges |
| `--radius-md` | 8px | Cards, panels, inputs |
| `--radius-lg` | 12px | Modals, large containers |

### 2.4 Card Pattern

Every panel follows:

```
+-------------------------------------------------------+
|  Panel Title          [badge] [dropdown]               |
+-------------------------------------------------------+
|                                                       |
|  Chart / Table / Metric Cards                         |
|                                                       |
+-------------------------------------------------------+
|  Last updated: 2s ago          Auto                   |
+-------------------------------------------------------+
```

- Background: `--bg-secondary`
- Border: `--border-default`, 1px solid
- Radius: `--radius-md`
- Shadow: none (flat design)
- Header divider: bottom border `--border-default`

### 2.5 Chart Conventions

- **Line charts:** 2px line width, circle markers (4px radius) on data points
- **Confidence bands:** Translucent fill, no border
- **Grid lines:** `--border-default`, 0.5px, dashed
- **Labels:** `--text-secondary` at 11px
- **Legend:** Bottom-aligned, horizontal, `--text-secondary`
- **Hover:** Tooltip with all series values at that time point
- **Animation:** 300ms ease-in-out on data updates

---

## 3. Component Tree & Layout

### 3.1 Page Structure

```
+------------------------------------------------------------------+
| HEADER                                                           |
| [HPA++ Logo]  [Deployment v]  [Time Range v]  [Refresh 2s] [Settings] |
+------------------------------------------------------------------+
|                                                                   |
| +--------------+----------------+-------------------------------+ |
| | TRAFFIC      | POD SCALING    | GPU ALLOCATION               | |
| | OVERVIEW     | STATUS         | VIEW                         | |
| | (Line chart  | (Line chart    | (Heatmap + table)            | |
| |  + band)     |  + cards)      |                              | |
| +--------------+----------------+-------------------------------+ |
|                                                                   |
| +---------------------------------------------------------------+ |
| | DECISION LOG                                                  | |
| | [Table with expandable rows, colour-coded by action]          | |
| +---------------------------------------------------------------+ |
|                                                                   |
| +--------------+------------------------------------------------+ |
| | CLUSTER      | SIMULATION CONTROLS                            | |
| | OVERVIEW     | [Play] [Pause] [Stop]  Speed: [====o====] 10x  | |
| | (Summary     | Profile: flash_sale                            | |
| |  cards)      |                                                 | |
| +--------------+------------------------------------------------+ |
+------------------------------------------------------------------+
| FOOTER: Last updated: 12:34:56 UTC  |  Sim time: +45m  |  v1.0  |
+------------------------------------------------------------------+
```

### 3.2 Responsive Breakpoints

| Breakpoint | Layout |
| :--- | :--- |
| >=1400px | 3-column grid (Traffic | Pods | GPU) |
| 1000-1399px | 2-column (Traffic+Pods stacked, GPU full-width) |
| 700-999px | 1-column, all panels stacked |
| <700px | 1-column with condensed padding and compact tables |

### 3.3 Component Tree

```
App
+-- Sidebar
|   +-- DeploymentSelector  (dropdown of available deployments)
|   +-- TimeRangeSelector   (preset buttons: 15m, 30m, 1h, All)
|   +-- RefreshRateControl  (slider: 1s to 30s)
|   +-- SimulationControls  (Play/Pause/Stop + Speed slider)
|   +-- ThemeToggle         (Dark/Light - future)
|
+-- Header
|   +-- Logo
|   +-- LiveIndicator       (green dot + LIVE text)
|   +-- LastUpdated         (timestamp of last data refresh)
|
+-- DashboardGrid
|   +-- TrafficPanel
|   |   +-- TimeSeriesChart   (Plotly: actual vs forecast with band)
|   |   +-- MetricCards       (current RPS, peak RPS, avg latency)
|   |
|   +-- ScalingPanel
|   |   +-- PodLineChart      (Plotly: current vs target pods)
|   |   +-- ReplicaCard       (current / target count display)
|   |
|   +-- GpuPanel
|   |   +-- GpuHeatmap        (Plotly: GPU utilization matrix)
|   |   +-- GpuAssignmentTable (Table: pod-to-GPU mappings)
|   |   +-- ContentionAlert   (warning banner if GPU > 90%)
|   |
|   +-- DecisionLogPanel
|   |   +-- DecisionTable     (table with color-coded rows)
|   |   +-- DecisionDetail    (expandable: full formula breakdown)
|   |
|   +-- ClusterOverviewPanel
|   |   +-- SummaryCards      (total pods, running, pending, GPUs)
|   |   +-- NodeTable         (node resource bars)
|   |
|   +-- SimulationControlsPanel (from Sidebar if embedded)
|
+-- Footer
    +-- StatusBar
```

---

## 4. Panel Specifications

### 4.1 Traffic Overview Panel

**Purpose:** Central narrative - actual traffic vs predicted traffic with confidence bands.

**Data Source (DB):**
- Actual: `metric_samples` (requests_per_second, simulated_time_utc)
- Predicted: `forecast_windows` (yhat, yhat_lower, yhat_upper, forecast_time_utc)

**Data Source (API fallback):**
- GET `simulation:8000/api/v1/metrics?deployment_id=X&limit=200`
- GET `forecasting:8000/api/v1/forecast/latest?deployment_id=X`

**Chart:** Plotly Scatter with `fill='toself'` for confidence band.

**Series:**
1. Actual RPS (solid `--chart-line-actual`, 2px)
2. Forecast RPS (solid `--chart-line-forecast`, 2px)
3. Confidence band (fill `--chart-band-forecast`)
4. Lower/upper bounds (dashed, 1px, optional toggle)

**Metric Cards:**
- Current RPS (last known value, large text)
- Forecast peak RPS (max yhat in visible window)
- Confidence width ((upper-lower)/yhat as percentage)
- Current latency ms (if available)

**States:**
- Loading: Skeleton chart (grey pulsing boxes)
- Empty: "No metrics available. Start the simulation to generate data."
- Error: "Unable to load metrics." with retry button
- No forecast: Show actual line only. Message: "Forecast pending - insufficient training data"

**Interactions:**
- Hover: tooltip with all series values at that time
- Legend click: toggle series visibility
- Optional: range slider for zoom

### 4.2 Pod Scaling Status Panel

**Purpose:** Show how HPA++ scaling decisions affect pod counts over time.

**Data Source:**
- Current: `cluster_snapshots` or `deployment_state` from simulation API
- Target: `scaling_decisions` (target_pod_count, simulated_time_utc)

**Chart:** Plotly dual-line chart.

**Series:**
1. Current pods (solid `--chart-line-pods-current`, 2px)
2. Target pods (dashed `--chart-line-pods-target`, 2px)
3. Colour zone: background fill green/yellow/red based on (current - target) ratio

**Replica Card:**
- Large display: "12 / 15" (current / target)
- Colour: green if current >= target*0.9, yellow if >= target*0.7, red if below
- Trend arrow: up/down/flat based on last 3 decisions

**States:**
- Loading: Skeleton
- No decisions yet: "Waiting for first scaling decision..."
- No deployments: "No deployments configured"

### 4.3 GPU Allocation View Panel

**Purpose:** Visualize GPU resource allocation and detect contention.

**Data Source:**
- `gpu_assignments` table (gpu_id, pod_id, memory_allocated_mb, compute_allocated_pct)
- `gpu_rebalance_events` table for history

**Visualization:**
- Heatmap: GPU devices on Y axis, time on X axis (or pods on X axis)
- Colour intensity = utilization percentage
- Bar chart: per-GPU memory allocated vs total

**GPU Assignment Table:**
Columns: GPU ID | Pod ID | Deployment | Memory (MB) | Compute (%) | Util (%)
Sortable by any column.

**Contention Alert:**
- Banner at top if any GPU utilization > 90%
- "GPU overcommitted: gpu-2 at 94% utilization. Rebalance recommended."
- Yellow for warning, red for critical (>95%)

**States:**
- No GPUs: "No GPU resources in the cluster"
- No assignments: "No pods currently using GPU resources"
- Loading: Skeleton heatmap

### 4.4 Decision Log Panel

**Purpose:** Full explainability - every scaling decision is auditable.

**Data Source:**
- `scaling_decisions` table (all fields, ordered by simulated_time_utc DESC)

**Table Columns:**
Time | Deployment | Action (colour badge) | From->To Pods | Risk | Confidence | Reason
- Action badge: green for scale_up, blue for scale_down, grey for hold, red for emergency
- Risk: colour-coded LOW (green), MEDIUM (yellow), HIGH (red), CRITICAL (purple)
- Confidence: percentage bar

**Expandable Row Detail:**
When a row is clicked/expanded, show:
```
Decision ID: dec-abc123
Forecast: 842 RPS (CI: 712 - 982)
Formula breakdown:
  1. raw_target = ceil(842 / 100) = 9
  2. confidence_factor = 0.85
  3. risk_bias = 1 + 0.3 * 5.0 = 2.5
  4. target = 9 * (1 + 0.85 * 2.5) = 28
  5. clamped = clamp(28, 1, 20) = 20
Risk score: 0.30 (MEDIUM)
Execution: Applied (scale_up from 12 to 20)
```

**States:**
- Empty: "No scaling decisions yet. Start the simulation and wait for the first forecast cycle."
- Error: "Unable to load decision log."

### 4.5 Cluster Overview Panel

**Purpose:** Quick summary of cluster health and resource usage.

**Data Source:**
- `cluster_snapshots` table (latest record)
- Simulation API: GET `/api/v1/cluster/state`

**Summary Cards (4 cards in a row):**
1. Total Nodes - number with small "X Ready" subtitle
2. Total Pods - number with "X Running / X Pending" subtitle
3. GPU Count - number with "X Free / X Allocated" subtitle
4. Cluster CPU - percentage bar + "X / Y millicores"

**Node Table:**
Columns: Node ID | Status | CPU (bar) | Memory (bar) | Pods | GPUs

**States:**
- Loading: Skeleton cards
- Empty: "Cluster state not available. Ensure the simulation is running."
- Partial: Show what's available, grey out missing fields

### 4.6 Simulation Controls Panel

**Purpose:** Control the simulation and see its status.

**Data Source:**
- Simulation API: GET `/api/v1/sim/status`
- Simulation API: POST `/api/v1/sim/start`, `/pause`, `/resume`, `/stop`

**Controls:**
- Play button (start simulation with current config)
- Pause button (pause without resetting)
- Stop button (stop and reset)
- Speed slider (1x to 60x)
- Profile indicator (shows current traffic pattern name)

**Status Display:**
- Simulation status badge (Running/Paused/Stopped in green/yellow/red)
- Elapsed simulated time
- Tick count
- Active deployments count

**States:**
- Not connected: "Simulation service unreachable. [Retry]"
- No config: "No simulation configuration loaded. [Load Default]"

---

## 5. Data Integration Specification

### 5.1 Primary Data Flow (Direct DB Reads)

The dashboard reads directly from the shared SQLite database for performance during development/demo. This avoids network latency for every refresh.

```python
# Example: services/dashboard/app/data.py

class DashboardData:
    """Data access layer for the dashboard.

    SOLID: Single responsibility - fetching and caching data.
    All raw data transformations belong in other services.
    """

    def __init__(self, db_path: str | Path):
        """Connect to the shared SQLite database."""
        ...

    def get_traffic_data(self, deployment_id: str,
                         window_minutes: int = 30) -> dict:
        """Get actual + forecast traffic data for charting.

        Returns:
            dict with keys:
            - actual: list of {time, rps, cpu, memory}
            - forecast: list of {time, yhat, lower, upper}
            - meta: {deployment_id, last_updated}
        """
        ...

    def get_scaling_data(self, deployment_id: str) -> dict:
        """Get current + target pod counts.

        Returns:
            dict with keys:
            - history: list of {time, current_pods, target_pods}
            - latest: {current_pods, target_pods, action, risk_level}
        """
        ...

    def get_gpu_data(self) -> dict:
        """Get GPU assignments and utilization.

        Returns:
            dict with keys:
            - assignments: list of {gpu_id, pod_id, memory, compute, util}
            - summary: {total_gpus, allocated_gpus, avg_util}
            - contention: list of overheated GPU IDs
        """
        ...

    def get_decision_log(self, deployment_id: str,
                         limit: int = 50) -> list[dict]:
        """Get recent scaling decisions with full details."""
        ...

    def get_cluster_summary(self) -> dict:
        """Get cluster overview summary data."""
        ...
```

### 5.2 Secondary Data Flow (REST API Calls)

For remote/docker deployment where DB is not shared, fall back to REST APIs:

| Endpoint | Service | Port | Purpose |
| :--- | :--- | :--- | :--- |
| GET /api/v1/metrics | simulation | 8001 | Get metric samples |
| GET /api/v1/metrics/latest | simulation | 8001 | Get latest metrics |
| GET /api/v1/cluster/state | simulation | 8001 | Cluster snapshot |
| GET /api/v1/sim/status | simulation | 8001 | Simulator status |
| POST /api/v1/sim/* | simulation | 8001 | Simulator control |
| GET /api/v1/forecast/latest | forecasting | 8002 | Latest forecast |
| GET /api/v1/forecast/history | forecasting | 8002 | Forecast history |
| POST /api/v1/forecast/run | forecasting | 8002 | Trigger forecast |
| GET /api/v1/scale/decisions | controller | 8003 | Scaling decisions |
| GET /api/v1/scale/latest | controller | 8003 | Latest decision |
| GET /api/v1/gpu/assignments | controller | 8003 | GPU assignments |
| GET /api/v1/scale/config | controller | 8003 | Scaling config |

### 5.3 Auto-Refresh Strategy

```python
# Pseudocode for the refresh loop

def auto_refresh_loop(interval_seconds: int = 2):
    """Continuous data refresh loop.

    Strategy:
    1. Read all panel data in one DB transaction
    2. Update Streamlit session state
    3. Trigger st.rerun() or Plotly reactive update
    4. Sleep for interval_seconds

    On error:
    - Log error, don't crash
    - Keep showing stale data if available
    - Show error state after 3 consecutive failures
    """
    while True:
        try:
            data = dashboard_data.read_all(
                deployment=st.session_state.selected_deployment
            )
            st.session_state.data = data
            time.sleep(st.session_state.refresh_interval)
            st.rerun()
        except Exception as e:
            st.session_state.error_count += 1
            if st.session_state.error_count >= 3:
                st.session_state.show_error_state = True
            time.sleep(1)
```

---

## 6. State Management

For Streamlit, state is managed via `st.session_state`:

```python
# Initialise default state
def init_state():
    defaults = {
        "selected_deployment": None,
        "time_range_minutes": 30,
        "refresh_interval": 2,  # seconds
        "simulation_running": False,
        "simulation_speed": 10,
        "data": None,
        "error_count": 0,
        "show_error_state": False,
        "theme": "dark",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
```

### State Categories:

| Category | Variables | Persistence |
| :--- | :--- | :--- |
| **User preferences** | selected_deployment, time_range, refresh_interval, theme | Session only |
| **Live data** | data (entire dashboard payload) | Volatile, replaced on each refresh |
| **UI state** | expanded_rows, active_tab, panel_visibility | Session only |
| **Simulation state** | simulation_running, simulation_speed | Sync with sim API on connect |
| **Error state** | error_count, show_error_state, last_error | Reset on successful refresh |

For a React-based dashboard, use a state management library (Redux, Zustand, or React Context) with the same categories.

---

## 7. Navigation & Interaction Design

### 7.1 Header Bar
- Fixed top, always visible
- Deployment selector: dropdown, defaults to first deployment
- Time range: 15m / 30m / 1h / All preset buttons
- Refresh: interval dropdown (1s, 2s, 5s, 10s, 30s) + manual refresh button
- Settings: gear icon, opens sidebar or modal

### 7.2 Panel Interactions
- Each panel can be collapsed/expanded via header click
- Draggable panels (future enhancement)
- Full-screen mode for any panel (double-click header)
- Export chart as PNG (Plotly built-in)

### 7.3 Keyboard Shortcuts (React version only)
- `R`: Refresh
- `Space`: Toggle simulation play/pause
- `1-6`: Switch to panel tab
- `Escape`: Close expanded detail

### 7.4 Decision Log Interaction
- Click row: expand to show full formula breakdown
- The expanded view should show:
  - The forecast values at that time
  - Each step of the formula with intermediate values
  - The risk score breakdown
  - Whether the action was applied or dry-run
- This is THE key explainability feature of HPA++

---

## 8. Error & Edge Case Handling

Every panel must handle these states:

| State | Behaviour |
| :--- | :--- |
| **Loading** | Show skeleton/shimmer placeholder (not spinner) |
| **Empty data** | Show descriptive message with next-action guidance |
| **Error** | Show error message + retry button, keep stale data if available |
| **Timeout** | After 5s without data, show "Taking longer than expected" with cancel |
| **Service down** | If DB/API unreachable, show "Service X unreachable" in affected panel only |

### Edge Cases:

| Scenario | Handling |
| :--- | :--- |
| No deployments exist | "No deployments configured. Add a deployment in the simulation config." |
| Forecast not yet available | Show actual metrics only with explanatory note |
| GPU count is 0 | Hide GPU panel entirely, add note "Enable GPUs in simulation config" |
| Simulation not running | Show paused state with "Start simulation" button |
| Rapid data updates | Debounce refresh to avoid visual jitter (min 1s between updates) |
| Very large datasets | Downsample to 200 data points max per series for performance |
| Dashboard not responding | Stale data indicator: "Data may be delayed - last updated Xs ago" |

---

## 9. Performance Requirements

| Metric | Target | Notes |
| :--- | :--- | :--- |
| Initial load time | < 2s | From page open to first data display |
| Refresh latency | < 500ms | From DB read to chart update |
| Animation frame rate | 30 fps | Smooth transitions on data updates |
| Memory usage | < 200MB | For 1000 data points across all panels |
| DB query time | < 100ms | Per panel query, with proper indexing |
| Concurrent users | 1-5 | Demo/hackathon scale, not production |
| Chart data points | <= 200 per series | Downsample beyond this |

### Optimization Strategies:
1. Read all panel data in ONE DB query/transaction per refresh cycle
2. Cache metric data for 1s minimum to avoid re-querying on rapid refreshes
3. Downsample time-series data for display (LTTB algorithm)
4. Use Plotly react mode for efficient re-renders
5. Lazy-load panels below the fold (if using scroll layout)

---

## 10. API Contract

### 10.1 Data Shape Contract

Each panel's data layer MUST return data that conforms to the shapes below. These shapes mirror the shared Pydantic models but are specific to frontend consumption.

```typescript
// TypeScript types for frontend data shapes

interface TrafficData {
  deploymentId: string;
  lastUpdated: string;  // ISO 8601
  actual: Array<{
    time: string;        // ISO 8601
    requestsPerSecond: number;
    cpuUtilizationPct: number;
    memoryUsageMb: number;
    latencyMs?: number;
  }>;
  forecast: Array<{
    time: string;
    yhat: number;
    yhatLower: number;
    yhatUpper: number;
  }>;
}

interface ScalingData {
  history: Array<{
    time: string;
    currentPods: number;
    targetPods: number;
    action: 'scale_up' | 'scale_down' | 'hold';
  }>;
  latest: {
    currentPods: number;
    targetPods: number;
    action: string;
    riskLevel: string;
    confidenceScore: number;
  };
}

interface GpuData {
  assignments: Array<{
    gpuId: string;
    podId: string;
    deploymentId: string;
    memoryAllocatedMb: number;
    computeAllocatedPct: number;
    effectiveUtilizationPct?: number;
  }>;
  summary: {
    totalGpus: number;
    allocatedGpus: number;
    avgUtilizationPct: number;
  };
  contention: string[];  // GPU IDs over 90%
}

interface DecisionLogEntry {
  decisionId: string;
  time: string;
  deploymentId: string;
  action: string;
  fromPods: number;
  toPods: number;
  riskScore: number;
  confidenceScore: number;
  riskLevel: string;
  reason: string;
  formulaBreakdown: {
    rawTarget: number;
    confidenceFactor: number;
    riskBias: number;
    finalBeforeClamp: number;
    minReplicas: number;
    maxReplicas: number;
  };
}

interface ClusterSummary {
  totalNodes: number;
  readyNodes: number;
  totalPods: number;
  runningPods: number;
  pendingPods: number;
  totalGpus: number;
  allocatedGpus: number;
  cpuUtilizationPct: number;
  memoryUtilizationPct: number;
  gpuUtilizationAvgPct?: number;
  nodes: Array<{
    nodeId: string;
    status: string;
    cpuBar: number;     // 0-100
    memoryBar: number;  // 0-100
    podCount: number;
    gpuIds: string[];
  }>;
}

interface SimulatorStatus {
  status: 'running' | 'paused' | 'stopped' | 'error';
  simName: string;
  tickCount: number;
  simulatedMinutesElapsed: number;
  activeProfile: string;
  speed: number;
}
```

### 10.2 Validation

Every data payload from the API should be validated against these frontend types before rendering (use Zod if in TypeScript, or manual validation if in Streamlit/Python).

```typescript
// Example Zod schema for validation
import { z } from 'zod';

const TrafficDataSchema = z.object({
  deploymentId: z.string(),
  lastUpdated: z.string().datetime(),
  actual: z.array(z.object({
    time: z.string().datetime(),
    requestsPerSecond: z.number().nonnegative(),
    cpuUtilizationPct: z.number().min(0).max(100),
    memoryUsageMb: z.number().nonnegative(),
    latencyMs: z.number().nonnegative().optional(),
  })),
  forecast: z.array(z.object({
    time: z.string().datetime(),
    yhat: z.number(),
    yhatLower: z.number(),
    yhatUpper: z.number(),
  })),
});
```

If validation fails, the panel shows an error state: "Data format error from [service name]" instead of attempting to render malformed data.

---

## Folder Structure (Dashboard Service)

```
services/dashboard/
+-- app/
|   +-- __init__.py
|   +-- main.py              # Streamlit entry point
|   +-- data.py              # DashboardData class (DB reads)
|   +-- api_client.py        # REST API fallback client
|   +-- state.py             # Session state management
|   +-- panels/
|   |   +-- __init__.py
|   |   +-- traffic.py       # Traffic Overview panel
|   |   +-- scaling.py       # Pod Scaling panel
|   |   +-- gpu.py           # GPU Allocation panel
|   |   +-- decisions.py     # Decision Log panel
|   |   +-- cluster.py       # Cluster Overview panel
|   |   +-- controls.py      # Simulation Controls panel
|   +-- components/
|   |   +-- __init__.py
|   |   +-- charts.py        # Reusable Plotly chart builders
|   |   +-- cards.py         # Reusable metric cards
|   |   +-- table.py         # Reusable styled table
|   |   +-- alerts.py        # Contention/status alerts
|   +-- styles/
|       +-- theme.py         # Colour palette, typography, spacing
+-- tests/
|   +-- __init__.py
|   +-- test_data.py
|   +-- test_panels.py
+-- Dockerfile
+-- requirements.txt
```

---

## Quick Reference: Streamlit Implementation Plan

For a Streamlit implementation (primary target):

1. **Page config** in `main.py`: `st.set_page_config(layout="wide", initial_sidebar_state="expanded")`
2. **Custom CSS**: Inject via `st.markdown(f"<style>{DARK_THEME_CSS}</style>", unsafe_allow_html=True)` using the colour tokens from Section 2.1
3. **Sidebar**: `st.sidebar` with deployment selector, time range, refresh control
4. **Dashboard grid**: Use `st.columns([1, 1, 1])` for the 3-column layout
5. **Charts**: Use `plotly.graph_objects.Figure` with the dark template `plotly_dark` as base, then apply custom colours
6. **Auto-refresh**: Use `st.rerun()` inside a `time.sleep()` loop, or use Streamlit's `st.empty()` + `time.sleep()` pattern
7. **Data layer**: `DashboardData` class that queries SQLite directly
8. **Error handling**: Wrap each panel in try/except, show `st.error()` for errors, `st.info()` for empty states
9. **Session state**: `st.session_state` for user preferences, data cache, error counts

---

*End of frontend spec sheet. Build the dashboard following this document, referencing the shared schemas in `shared/` for data structures and the service APIs in each microservice's `routes.py` for endpoints.*
