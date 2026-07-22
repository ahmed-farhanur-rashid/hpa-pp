import os
import json
import numpy as np
import pandas as pd
from scipy import stats, optimize

DATA_DIR = "/home/farhan/my-projects/hpa-pp/data"
OUTPUT_JSON = os.path.join(DATA_DIR, "extracted_parameters.json")

def extract_wikipedia_seasonality():
    """Extracts macro seasonality & trend parameters from train_by_site.csv."""
    filepath = os.path.join(DATA_DIR, "train_by_site.csv")
    df = pd.read_csv(filepath)
    
    # Target site: en.wikipedia.org (row index 2 or matching Site column)
    site_row = df[df["Site"] == "en.wikipedia.org"]
    if site_row.empty:
        site_row = df.iloc[0:1]
        
    date_cols = [c for c in df.columns if c != "Site"]
    traffic_series = site_row[date_cols].values.flatten().astype(float)
    
    # Handle any NaNs
    traffic_series = pd.Series(traffic_series).interpolate().bfill().values
    
    dates = pd.to_datetime(date_cols)
    dows = dates.dayofweek
    
    # Day-of-week multipliers relative to weekday mean
    dow_means = pd.Series(traffic_series).groupby(dows).mean()
    weekday_mean = dow_means.iloc[0:5].mean()
    dow_multipliers = (dow_means / weekday_mean).to_dict()
    
    # Trend fit (linear growth per day)
    t_days = np.arange(len(traffic_series))
    slope, intercept, r_value, p_value, std_err = stats.linregress(t_days, traffic_series)
    
    # Seasonality Strength Metric F_S (Weekly)
    # Using 7-day rolling decomposition
    s_series = pd.Series(traffic_series)
    rolling_7 = s_series.rolling(7, center=True).mean().bfill().ffill()
    detrended = s_series - rolling_7
    var_remainder = np.var(s_series - rolling_7)
    var_total = np.var(s_series)
    f_weekly = max(0.0, 1.0 - (var_remainder / max(1e-6, var_total)))
    
    return {
        "dataset_source": "train_by_site.csv (Kaggle Wikipedia Traffic)",
        "num_days_observed": len(traffic_series),
        "mean_daily_traffic": float(np.mean(traffic_series)),
        "std_daily_traffic": float(np.std(traffic_series)),
        "trend_slope_per_day": float(slope),
        "trend_intercept": float(intercept),
        "dow_multipliers": {int(k): float(v) for k, v in dow_multipliers.items()},
        "weekly_seasonality_strength_Fs": float(f_weekly)
    }

def extract_cluster_volatility_and_ar1():
    """Extracts AR(1) autocorrelation & Student-t noise parameters from all_datasets_by_timestamp.csv."""
    filepath = os.path.join(DATA_DIR, "all_datasets_by_timestamp.csv")
    df = pd.read_csv(filepath)
    
    # Filter out idle/zero maintenance rows (<5.23% of data)
    df_active = df[(df["cpu_util_mean"] > 0) | (df["gpu_util_mean"] > 0)].copy()
    
    cpu_series = df_active["cpu_util_mean"].values
    
    # Compute normalized residual e_t = (cpu_t - mean) / mean
    mean_cpu = np.mean(cpu_series)
    residuals = (cpu_series - mean_cpu) / mean_cpu
    
    # Fit AR(1): e_t = phi * e_{t-1} + noise_t
    e_t = residuals[1:]
    e_t_minus_1 = residuals[:-1]
    
    phi_1 = np.sum(e_t * e_t_minus_1) / np.sum(e_t_minus_1 ** 2)
    noise = e_t - phi_1 * e_t_minus_1
    
    # Fit Student-t distribution on noise
    df_t, loc_t, scale_t = stats.t.fit(noise)
    
    return {
        "dataset_source": "all_datasets_by_timestamp.csv (Microsoft OpenPAI Traces)",
        "active_rows_analyzed": len(df_active),
        "idle_rows_excluded": int(len(df) - len(df_active)),
        "mean_active_cpu_pct": float(mean_cpu),
        "std_active_cpu_pct": float(np.std(cpu_series)),
        "ar1_coefficient_phi1": float(phi_1),
        "residual_white_noise_std": float(np.std(noise)),
        "student_t_degrees_of_freedom": float(df_t),
        "student_t_scale": float(scale_t)
    }

def extract_gpu_utilization_parameters():
    """Extracts normalized per-GPU utilization metrics from all_datasets_by_timestamp.csv."""
    filepath = os.path.join(DATA_DIR, "all_datasets_by_timestamp.csv")
    df = pd.read_csv(filepath)
    
    df_active = df[df["gpu_util_mean"] > 0].copy()
    
    # Normalize gpu_util_mean by active GPUs to account for aggregate cluster sums (>100%)
    per_gpu_util = (df_active["gpu_util_mean"] / df_active["gpu_active_mean"].replace(0, 1)).values
    
    return {
        "dataset_source": "all_datasets_by_timestamp.csv (Microsoft OpenPAI Traces)",
        "raw_gpu_util_mean_max_pct": float(df["gpu_util_mean"].max()),
        "rows_exceeding_100pct_raw": int((df["gpu_util_mean"] > 100.0).sum()),
        "normalized_per_gpu_mean_pct": float(np.mean(per_gpu_util)),
        "normalized_per_gpu_std_pct": float(np.std(per_gpu_util)),
        "normalized_per_gpu_min_pct": float(np.min(per_gpu_util)),
        "normalized_per_gpu_max_pct": float(np.max(per_gpu_util)),
        "mean_active_gpus_per_step": float(df_active["gpu_active_mean"].mean())
    }

def extract_multivariate_and_request_metrics():
    """Extracts QPS, request counts, and pod reporting stats from genai_trace_aggregated.csv."""
    filepath = os.path.join(DATA_DIR, "genai_trace_aggregated.csv")
    df = pd.read_csv(filepath)
    
    req_s = df["req_count_first"].dropna()
    pods_s = df["pods_reporting"].dropna()
    
    return {
        "dataset_source": "genai_trace_aggregated.csv (GenAI Serving Trace)",
        "req_count_first_valid_rows": int(len(req_s)),
        "req_count_first_mean": float(req_s.mean()),
        "req_count_first_std": float(req_s.std()),
        "req_count_first_min": float(req_s.min()),
        "req_count_first_p50": float(req_s.median()),
        "req_count_first_p75": float(req_s.quantile(0.75)),
        "req_count_first_max": float(req_s.max()),
        "pods_reporting_mean": float(pods_s.mean()),
        "pods_reporting_max": float(pods_s.max())
    }

def extract_spike_parameters():
    """Extracts flash surge / spike arrival frequency & intensity from OpenPAI job submission spikes."""
    filepath = os.path.join(DATA_DIR, "all_datasets_by_timestamp.csv")
    df = pd.read_csv(filepath)
    
    # Define spike events as job_count > 95th percentile
    job_counts = df["job_count"].values
    threshold = np.percentile(job_counts, 95)
    
    spike_mask = job_counts > threshold
    num_spike_steps = np.sum(spike_mask)
    
    # Calculate average spike duration by contiguous blocks
    spike_blocks = pd.Series(spike_mask).groupby((~pd.Series(spike_mask)).cumsum()).sum()
    spike_durations = spike_blocks[spike_blocks > 0].values
    
    surge_multipliers = job_counts[spike_mask] / max(1.0, np.median(job_counts[job_counts > 0]))
    
    # Fit Pareto distribution on surge multipliers
    pareto_b, pareto_loc, pareto_scale = stats.pareto.fit(surge_multipliers)
    
    total_days = len(df) / 1440.0  # 1-minute steps
    spikes_per_day = len(spike_durations) / max(1.0, total_days)
    
    return {
        "dataset_source": "all_datasets_by_timestamp.csv (Job Surge Analysis)",
        "spike_threshold_job_count": float(threshold),
        "total_spikes_detected": len(spike_durations),
        "spikes_per_day_lambda": float(spikes_per_day),
        "mean_spike_duration_minutes": float(np.mean(spike_durations) if len(spike_durations) > 0 else 15.0),
        "mean_surge_multiplier": float(np.mean(surge_multipliers)),
        "max_surge_multiplier": float(np.max(surge_multipliers)),
        "pareto_shape_b": float(pareto_b),
        "pareto_scale": float(pareto_scale)
    }

def main():
    print("=" * 90)
    print("STARTING REAL PARAMETER EXTRACTION FROM REFERENCE DATASETS")
    print("=" * 90)
    
    params = {
        "wikipedia_seasonality": extract_wikipedia_seasonality(),
        "cluster_volatility_ar1": extract_cluster_volatility_and_ar1(),
        "gpu_utilization_normalized": extract_gpu_utilization_parameters(),
        "multivariate_requests": extract_multivariate_and_request_metrics(),
        "spike_events": extract_spike_parameters()
    }
    
    # Save to JSON
    with open(OUTPUT_JSON, "w") as f:
        json.dump(params, f, indent=2)
        
    print(f"\n[SUCCESS] Parameters successfully saved to: {OUTPUT_JSON}\n")
    print("=" * 90)
    print("EXTRACTED REAL-WORLD PARAMETERS SUMMARY")
    print("=" * 90)
    print(json.dumps(params, indent=2))

if __name__ == "__main__":
    main()
