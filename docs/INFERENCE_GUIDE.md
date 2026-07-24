# HPA++ Model Inference — Technical Guide

This guide provides complete technical documentation on how to perform inference using trained forecasting checkpoints in HPA++. It covers both **PyTorch Deep Learning Models (PSA-Net, PatchTST)** and **Facebook Prophet**.

---

## 1. Overview & Unified Data Contract

All models take a **historical context window** of telemetry data and generate a **multi-step forecast horizon** into the future with **80% uncertainty bounds**.

### Inputs & Outputs

| Parameter | Value / Description |
| :--- | :--- |
| **Input Context (`input_window`)** | Last **120 rows** (2 hours at 1-minute resolution) |
| **Output Horizon (`horizon`)** | Next **15 rows** (15 minutes into the future) |
| **Features ($F$)** | `requests_per_second`, `concurrent_users`, `cpu_utilization_pct`, `memory_utilization_pct`, `gpu_utilization_pct`, `pod_count` (plus 5 one-hot `cluster_*` identifiers) |
| **Quantiles ($Q$)** | $q_{0.1}$ (10th percentile / lower bound), $q_{0.5}$ (median point forecast), $q_{0.9}$ (90th percentile / upper bound) |

---

## 2. Deep Learning Inference (PSA-Net & PatchTST)

PyTorch model checkpoints (`.pt` files) store model weights, configuration, and feature z-score normalization parameters (`mean` and `std`).

### Pipeline Steps
1. **Load Checkpoint**: Load checkpoint dictionary via `torch.load(path, map_location=device)`.
2. **Extract Parameters**: Retrieve `config`, `model_state`, `mean`, `std`, and `feature_cols`.
3. **Preprocess Context Window**:
   - Extract the last 120 rows of `feature_cols` from historical DataFrame.
   - Apply z-score normalization: $\mathbf{x}_{\text{norm}} = \frac{\mathbf{x} - \text{mean}}{\text{std} + 1e-6}$.
   - Convert to float tensor of shape `[1, 120, F]`.
4. **Forward Pass**: Run `model.eval()` within `torch.no_grad()` context.
   - **PSA-Net**: `preds = model(hist, tod, dow)` $\rightarrow$ shape `[1, 15, F, 3]`
   - **PatchTST**: `preds = model(hist)` $\rightarrow$ shape `[1, 15, F, 3]`
5. **Postprocess & Unscale**:
   - Unscale back to original metric units: $\mathbf{y}_{\text{orig}} = \mathbf{preds} \times \text{std} + \text{mean}$.
   - Slice quantiles: $q_{0.1}$ = `preds[..., 0]`, $q_{0.5}$ = `preds[..., 1]`, $q_{0.9}$ = `preds[..., 2]`.

### Python Code Example (PyTorch Deep Learning Models)

```python
import torch
import pandas as pd
import numpy as np

def predict_pytorch_checkpoint(checkpoint_path: str, context_df: pd.DataFrame, device: str = "cpu"):
    # 1. Load Checkpoint
    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
    cfg = checkpoint["config"]
    mean, std = checkpoint["mean"], checkpoint["std"]
    feature_cols = checkpoint.get("feature_cols", [
        "cluster_ecommerce", "cluster_exam_system", "cluster_genai_inference", "cluster_streaming", "cluster_university_portal",
        "requests_per_second", "concurrent_users", "cpu_utilization_pct", "memory_utilization_pct", "gpu_utilization_pct", "pod_count"
    ])
    
    # 2. Instantiate Model
    is_patchtst = (type(cfg).__name__ == "PatchTSTConfig")
    if is_patchtst:
        from patchtst import PatchTST
        model = PatchTST(cfg).to(device)
    else:
        from psanet.model import PSANet
        model = PSANet(cfg).to(device)
        
    model.load_state_dict(checkpoint["model_state"])
    model.eval()

    # 3. Preprocess Input Context (Last 120 timesteps)
    window_data = context_df[feature_cols].values[-cfg.input_window:].astype(np.float32)
    norm_data = (window_data - mean) / std
    hist_tensor = torch.tensor(norm_data, dtype=torch.float32).unsqueeze(0).to(device)

    # 4. Generate Predictions
    with torch.no_grad():
        if is_patchtst:
            raw_preds = model(hist_tensor)  # [1, horizon, F, 3]
        else:
            # Generate TOD/DOW patch indices for PSA-Net
            tod_dummy = torch.zeros((1, (cfg.input_window - cfg.patch_len) // cfg.patch_stride + 1), dtype=torch.long, device=device)
            dow_dummy = torch.zeros((1, (cfg.input_window - cfg.patch_len) // cfg.patch_stride + 1), dtype=torch.long, device=device)
            raw_preds = model(hist_tensor, tod_dummy, dow_dummy)

    # 5. Unscale Predictions to Original Metric Units
    preds_np = raw_preds.squeeze(0).cpu().numpy()  # [horizon, F, 3]
    preds_unscaled = preds_np * std[None, :, None] + mean[None, :, None]

    # 6. Format Result DataFrame (using median q=0.5)
    forecast_df = pd.DataFrame(preds_unscaled[..., 1], columns=feature_cols)
    return forecast_df
```

---

## 3. Prophet Model Inference

Prophet checkpoints (`.json` files) store serialized per-feature additive regression models.

### Pipeline Steps
1. **Load Checkpoint**: Deserializes JSON file containing model parameters via `ProphetForecaster.load(path)`.
2. **Extract Last Timestamp**: Reads the last timestamp from historical `context_df` (`last_ts = context_df['timestamp'].iloc[-1]`).
3. **Generate Future Timestamps**: Construct date range for the next 15 minutes (`pd.date_range(start=last_ts + 1min, periods=horizon)`).
4. **Evaluate Curve Equations**: For each feature, runs `m.predict(future_df)` to compute point predictions ($yhat$) and 80% bounds ($yhat_{\text{lower}}$, $yhat_{\text{upper}}$).

### Python Code Example (Prophet)

```python
import sys
import os
import pandas as pd

# Add prophet module path
sys.path.insert(0, "services/forecasting/models/prophet")
from model import ProphetForecaster

def predict_prophet_checkpoint(checkpoint_path: str, context_df: pd.DataFrame, horizon: int = 15):
    # 1. Load Serialized Prophet Checkpoint
    forecaster = ProphetForecaster()
    forecaster.load(checkpoint_path)

    # 2. Perform Inference for Future Horizon
    forecast_df = forecaster.predict(context_df, horizon=horizon)
    return forecast_df
```

---

## 4. Unified Object Interface (`BaseForecaster`)

Both PSA-Net (`PSANetForecaster`) and Prophet (`ProphetForecaster`) adhere to the unified `BaseForecaster` interface located in [base_model.py](file:///home/farhan/my-projects/hpa-pp/services/forecasting/models/base_model.py):

```python
from base_model import BaseForecaster
from custom_model.model import PSANetForecaster

# 1. Instantiate Forecaster
forecaster = PSANetForecaster(input_window=120, forecast_horizon=15)

# 2. Load Trained Weights
forecaster.load("models/psa-net.pt")

# 3. Generate Predictions on Recent Context
forecast_df = forecaster.predict(recent_context_df, horizon=15)
```

---

## 5. Command-Line Evaluation Benchmark

To run automated inference and compute evaluation metrics (MAE, RMSE, WAPE, 80% Coverage) across the out-of-distribution test set:

```bash
# Evaluate PSA-Net Checkpoint
python services/forecasting/models/evaluate.py \
  --checkpoint models/psa-net.pt \
  --test_csv data/synthetic_hpa_traffic_shifted_test.csv

# Evaluate PatchTST Baseline Checkpoint
python services/forecasting/models/evaluate.py \
  --checkpoint models/patchtst.pt \
  --test_csv data/synthetic_hpa_traffic_shifted_test.csv

# Evaluate Prophet Baseline Checkpoint
python services/forecasting/models/evaluate.py \
  --checkpoint models/prophet.json \
  --test_csv data/synthetic_hpa_traffic_shifted_test.csv
```
