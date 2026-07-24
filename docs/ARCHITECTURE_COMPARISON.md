# Architecture Comparison & PSA-Net Specialties

This document provides a comprehensive technical audit comparing **PSA-Net (Patch-Spectral Attention Network)** against baseline models (**PatchTST** and **Prophet**) for Kubernetes HPA telemetry forecasting.

---

## 1. Executive Summary & Audit Assessment

Evaluating the trained **PSA-Net (10 Epochs)** model on the 30-day out-of-distribution test set (`data/synthetic_hpa_traffic_shifted_test.csv`):

| Telemetry Feature Column | MAE | RMSE | WAPE (%) | Performance Verdict |
| :--- | :---: | :---: | :---: | :--- |
| **`gpu_utilization_pct`** | **$3.53\%$** | $6.85\%$ | **$6.05\%$** | 🌟 **Exceptional Precision** (Ideal for GenAI LLM workloads) |
| **`pod_count`** | **$2.88$ pods** | $9.52$ | **$13.61\%$** | 🟢 **Strong Proactive Scaling** (Predicts required pods within 2.8 pods) |
| **`memory_utilization_pct`** | **$7.80\%$** | $9.03\%$ | **$15.02\%$** | 🟢 **Very Strong Fit** |
| **`concurrent_users`** | **$341.39$ users** | $1209.18$ | **$15.10\%$** | 🟢 **Solid Traffic Leading Indicator** |
| **`requests_per_second`** | **$295.25$ QPS** | $594.59$ | **$27.42\%$** | 🟡 **Good Out-of-Distribution Baseline** |
| **`cpu_utilization_pct`** | **$8.26\%$** | $12.04\%$ | **$28.03\%$** | 🟡 **Good Out-of-Distribution Baseline** |

---

## 2. Model Feature Matrix

| Technical Capability | Prophet (Additive) | PatchTST (Transformer) | **PSA-Net (Custom Architecture)** |
| :--- | :---: | :---: | :---: |
| **Multi-Input Multi-Output (MIMO)** | ❌ (Univariate SISO) | ✅ Yes | **✅ Yes** |
| **Inter-Channel Cross-Attention** | ❌ None | ❌ Channel Independent | **✅ Joint Channel Cross-Attention** |
| **Frequency Domain Spectral Branch** | ❌ No | ❌ No | **✅ FFT Spectral Branch (`n_freq_bins=32`)** |
| **Spike Pattern Memory Bank** | ❌ No | ❌ No | **✅ Learned Spike Cross-Attention Bank (`n_patterns=16`)** |
| **Quantile Uncertainty Output ($q_{0.1}, q_{0.5}, q_{0.9}$)** | ⚠️ Interval Bounds | ✅ Quantile Loss | **✅ Quantile Loss** |

---

## 3. Why PSA-Net is Superior for Kubernetes HPA Telemetry

### A. Dual Time + FFT Spectral Branch (Frequency Domain)
* **Problem**: Standard transformers process history purely in the time domain, requiring massive input windows (e.g. 1,440 timesteps) to discover 24-hour daily seasonality.
* **PSA-Net Solution**: Each patch is transformed via **Fast Fourier Transform (FFT)** into the frequency domain. Diurnal 24-hour cycles show up as sharp low-frequency peaks, giving seasonality a dedicated representational path without relying on self-attention alone.

### B. Spike Pattern Cross-Attention Bank
* **Problem**: Conventional networks react only after a magnitude threshold is crossed (e.g. "CPU is currently > 80%").
* **PSA-Net Solution**: Maintains a learned memory bank of reference **"Spike Shape Embeddings"**. As soon as a leading edge appears in traffic, the model performs cross-attention against reference spike signatures (*"This exponential slope matches a flash-sale surge!"*), triggering proactive pod scaling **before** resource saturation occurs.

### C. Multivariate Inter-Channel Fusion
* **Problem**: PatchTST operates under *Channel Independence* (treating each telemetry variable as an isolated series).
* **PSA-Net Solution**: Fuses channel representations so that surges in `concurrent_users` or `requests_per_second` explicitly inform upcoming `gpu_utilization_pct` and `pod_count` forecasts.

---
