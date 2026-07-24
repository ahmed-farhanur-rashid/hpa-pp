# HPA++ Forecasting Engine — Q&A & Technical Guide

This document answers common questions regarding how the time-series forecasting models in HPA++ operate, how history lookback and forecast horizons work, and the key architectural differences between PSA-Net, PatchTST, and Prophet.

---

## 1. Core Forecasting Concepts

### Q1: What is History Lookback (`input_window`)?
**History Lookback** is how far back into the past the model inspects metric data before generating a prediction.
- **Configured Value**: `120` timesteps (**2 hours** at 1-minute resolution).
- **Example**: At `2:00 PM`, the model reads all historical metric values from `12:00 PM` to `2:00 PM`.

### Q2: What is Forecast Horizon (`forecast_horizon`)?
**Forecast Horizon** is how far into the future the model predicts.
- **Microservice Serving Horizon**: `15` timesteps (**15 minutes** ahead).
- **Long-Range Model Horizon**: `60` timesteps (**60 minutes / 1 hour** ahead).
- **Example**: At `2:00 PM`, the model outputs minute-by-minute predictions for `2:01 PM` through `2:15 PM` (or `2:60 PM`).

```
         ◄━━━━ HISTORY LOOKBACK ━━━━► │ ◄━━━ FORECAST HORIZON ━━━►
                  (2 Hours)           │        (15 Minutes)
┌─────────────────────────────────────┼────────────────────────────┐
│ 12:00 PM                  2:00 PM   │ 2:01 PM            2:15 PM │
│ (Past telemetry fed to model)      │ (Predicted future metrics) │
└─────────────────────────────────────┴────────────────────────────┘
                                      ▲
                                 NOW (2:00 PM)
```

### Q3: What metrics and values does each prediction contain?
For **every single minute** in the future horizon ($t+1, t+2, \dots, t+15$), the model predicts **6 telemetry metrics**:
1. `requests_per_second` (RPS)
2. `concurrent_users`
3. `cpu_utilization_pct`
4. `memory_utilization_pct`
5. `gpu_utilization_pct`
6. `pod_count`

For each metric at each minute, the model outputs **3 uncertainty quantiles**:
- **$q_{0.1}$ (10th percentile)**: Conservative lower bound.
- **$q_{0.5}$ (50th percentile)**: Median point forecast.
- **$q_{0.9}$ (90th percentile)**: Upper bound used by the controller for proactive scaling.

---

## 2. Architectural Comparison

### Q4: How do PSA-Net, PatchTST, and Prophet differ?

| Feature | PSA-Net (Custom Model) | PatchTST Baseline | Prophet Baseline |
| :--- | :--- | :--- | :--- |
| **Model Type** | Multi-Branch Deep Transformer | Channel-Independent Transformer | Additive Curve-Fitting Regression |
| **Cross-Channel Correlation** | **Yes** (Channel mixing across features) | **No** (Channel independent, shared weights) | **No** (Univariate independent models) |
| **Specialized Components** | Dual Time/FFT Spectral, Seasonal Lookup, Spike Pattern Bank | Patch Embeddings + Shared Encoder | Trend + Fourier Seasonality |
| **Execution** | 1 GPU forward pass | 1 GPU forward pass | CPU L-BFGS optimization |
| **Parameters** | **~6.2M** (15m horizon) / **~23M** (60m horizon) | **~446k** | Parametric curve coefficients |
| **Disk Size** | **~25 MB** / **~92 MB** | **~1.8 MB** | **~1.5 MB** (JSON checkpoint) |

---

## 3. Model Checkpoints & Storage

### Q5: Where are model checkpoints saved?
All service checkpoints are saved in `services/forecasting/checkpoints/`:
- `services/forecasting/checkpoints/psanet_checkpoint.pt`: PSA-Net 15-minute checkpoint (~25 MB)
- `services/forecasting/checkpoints/patchtst_checkpoint.pt`: PatchTST 15-minute checkpoint (~1.8 MB)
- `services/forecasting/checkpoints/prophet_checkpoint.json`: Prophet 15-minute checkpoint (~1.5 MB)
- `models/psanet_checkpoint.pt`: Standalone 60-minute PSA-Net model (~92 MB)

### Q6: Why is PatchTST so lightweight (1.8 MB) compared to PSA-Net (25 MB / 92 MB)?
1. **Channel Independence**: PatchTST reuses the exact same Transformer weights across all 11 feature channels independently. The weights do not multiply by feature count.
2. **Channel-Mixing Head**: PSA-Net flattens all features and patches into a joint representation matrix (`n_features * n_patches * d_model`), creating a much larger output projection layer.
3. **Auxiliary Modules**: PSA-Net includes extra modules (FFT spectral projection, 1440-step seasonal embedding tables, and a 16-pattern Spike Pattern Bank cross-attention layer).

---

## 4. Evaluation & Verification

### Q7: How do I evaluate any model checkpoint on the test set?

Run the unified evaluation script ([evaluate.py](file:///home/farhan/my-projects/hpa-pp/services/forecasting/models/evaluate.py)):

```bash
# Evaluate PSA-Net
python services/forecasting/models/evaluate.py \
  --checkpoint services/forecasting/checkpoints/psanet_checkpoint.pt \
  --test_csv data/synthetic_hpa_traffic_shifted_test.csv

# Evaluate PatchTST
python services/forecasting/models/evaluate.py \
  --checkpoint services/forecasting/checkpoints/patchtst_checkpoint.pt \
  --test_csv data/synthetic_hpa_traffic_shifted_test.csv

# Evaluate Prophet
python services/forecasting/models/evaluate.py \
  --checkpoint services/forecasting/checkpoints/prophet_checkpoint.json \
  --test_csv data/synthetic_hpa_traffic_shifted_test.csv
```
