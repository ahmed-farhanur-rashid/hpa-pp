import os
import json
import numpy as np
import pandas as pd
from scipy import stats

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(BASE_DIR, "data")
PARAMS_JSON = os.path.join(DATA_DIR, "extracted_parameters.json")

def load_extracted_parameters():
    """Loads fitted and assumption-based parameters from JSON."""
    if os.path.exists(PARAMS_JSON):
        with open(PARAMS_JSON, "r") as f:
            return json.load(f)
    else:
        raise FileNotFoundError(f"Parameters file not found at {PARAMS_JSON}. Run extract_real_parameters.py first.")

def generate_hpa_synthetic_dataset(
    start_date: str = "2025-01-01",
    days: int = 90,
    freq: str = "5min",
    random_seed: int = 42,
    output_filename: str = "synthetic_hpa_traffic_5min.csv"
) -> pd.DataFrame:
    """
    Generates a 5-minute interval synthetic traffic dataset for HPA++ forecasting evaluation.
    Integrates empirical parameters extracted from Wikipedia, Microsoft OpenPAI, Google Borg, and GenAI traces.
    Features:
      - Multi-scale Wikipedia seasonality tuned for F_S >= 0.65 & rho_288 >= 0.70
      - Stationary mean-reverting AR(1) residual noise
      - Dual Spike Generators: (a) Fitted background job churn, (b) Assumption-based flash events
      - Non-linear CPU/Memory/GPU multivariate saturation
      - Simulated Kubernetes HPA pod scaling with strict max_pods=120 cap
    """
    np.random.seed(random_seed)
    params = load_extracted_parameters()
    
    # 1. Timeline Setup (5-min intervals)
    timestamps = pd.date_range(start=start_date, periods=days * 288, freq=freq)
    n_steps = len(timestamps)
    
    t_hours = (timestamps - timestamps[0]).total_seconds() / 3600.0
    t_days = t_hours / 24.0
    
    # 2. Wikipedia Multi-Scale Seasonality & Macro Trend
    wiki_p = params["wikipedia_seasonality"]
    dow_map = wiki_p["dow_multipliers"]
    
    base_qps = 500.0 + 0.15 * t_days + 25.0 * np.sin(2 * np.pi * t_days / 180.0)
    
    # Enhanced Diurnal Daily Cycle (Amplitude tuned to 0.55 for F_S >= 0.65 & rho_288 >= 0.70)
    daily_h1 = np.sin(2 * np.pi * (t_hours - 7) / 24.0)
    daily_h2 = 0.35 * np.sin(4 * np.pi * (t_hours - 4) / 24.0)
    daily_seasonality = 1.0 + 0.55 * (daily_h1 + daily_h2)
    
    # Weekly seasonality using extracted DOW multipliers
    dow_indices = timestamps.dayofweek
    weekly_seasonality = np.array([dow_map[str(d)] for d in dow_indices])
    
    # Yearly seasonality
    yearly_seasonality = 1.0 + 0.08 * np.sin(2 * np.pi * t_days / 365.25)
    
    base_rps = base_qps * daily_seasonality * weekly_seasonality * yearly_seasonality
    
    # 3. Stationary Mean-Reverting AR(1) Volatility Engine
    ar1_params = params["cluster_volatility_ar1"]
    phi_5min = ar1_params["ar1_5min_phi5"]
    noise_std = ar1_params["residual_white_noise_std_5min"]
    nu_deg = ar1_params["student_t_degrees_of_freedom"]
    
    ar_noise = np.zeros(n_steps)
    white_shocks = np.random.normal(0, noise_std, n_steps)
    
    for i in range(1, n_steps):
        ar_noise[i] = phi_5min * ar_noise[i-1] + white_shocks[i]
        
    heavy_tail_bursts = stats.t.rvs(df=nu_deg, loc=0, scale=0.005, size=n_steps)
    volatility_factor = np.exp(np.clip(ar_noise + heavy_tail_bursts, -0.25, 0.25))
    rps = base_rps * volatility_factor
    
    # 4. DUAL SPIKE GENERATORS
    # (a) Background Job Churn Spikes (FITTED)
    job_spikes = params["spike_generators"]["background_job_churn_spikes_FITTED"]
    job_lambda = job_spikes["spikes_per_day_lambda"]
    num_job_spikes = int(job_lambda * days)
    
    churn_multiplier = np.ones(n_steps)
    churn_indices = np.random.choice(n_steps, size=num_job_spikes, replace=False)
    pareto_b = job_spikes["pareto_shape_b"]
    
    for c_idx in churn_indices:
        intensity = 1.0 + 0.12 * stats.pareto.rvs(b=pareto_b, scale=1.0)
        churn_multiplier[c_idx] = min(3.0, intensity)
        
    # (b) Flash-Event Demand Spikes (ASSUMPTION-BASED)
    flash_spikes = params["spike_generators"]["flash_event_demand_spikes_ASSUMPTION_BASED"]
    flash_lambda = flash_spikes["spikes_per_day_lambda"]
    num_flash_spikes = max(1, int(flash_lambda * days))
    
    flash_multiplier = np.ones(n_steps)
    flash_mask = np.zeros(n_steps, dtype=bool)
    flash_centers = np.random.choice(np.arange(288, n_steps - 288), size=num_flash_spikes, replace=False)
    
    for f_idx in flash_centers:
        duration_steps = np.random.randint(12, 36)
        peak_mult = np.random.uniform(2.5, 4.5)
        
        rise_steps = int(duration_steps * 0.25)
        decay_steps = duration_steps - rise_steps
        
        start_idx = max(0, f_idx - rise_steps)
        end_idx = min(n_steps, f_idx + decay_steps)
        
        t_seq = np.arange(end_idx - start_idx)
        peak_offset = f_idx - start_idx
        
        profile = np.zeros(len(t_seq))
        rise_m = t_seq <= peak_offset
        profile[rise_m] = np.exp(-((t_seq[rise_m] - peak_offset) ** 2) / (2 * (max(1, rise_steps / 2)) ** 2))
        decay_m = t_seq > peak_offset
        profile[decay_m] = np.exp(-(t_seq[decay_m] - peak_offset) / (max(1, decay_steps / 2.5)))
        
        effect = 1.0 + (peak_mult - 1.0) * profile
        flash_multiplier[start_idx:end_idx] = np.maximum(flash_multiplier[start_idx:end_idx], effect)
        flash_mask[start_idx:end_idx] = True

    rps = rps * churn_multiplier * flash_multiplier

    # 5. Multivariate System Relationships
    users_per_req = 1.80 + np.random.normal(0, 0.04, n_steps)
    concurrent_users = np.maximum(10, rps * users_per_req + np.random.normal(0, 20, n_steps))
    
    # Non-Linear CPU Saturation Curve
    raw_cpu_load = (rps / 35.0) + (concurrent_users / 100.0)
    cpu_utilization_pct = 100.0 / (1.0 + np.exp(-(raw_cpu_load - 50.0) / 12.0))
    cpu_utilization_pct = np.clip(cpu_utilization_pct + np.random.normal(0, 1.0, n_steps), 5.0, 99.5)
    
    # Memory Utilization with GC Hysteresis Decay
    mem_base = 32.0
    mem_load = np.zeros(n_steps)
    mem_load[0] = mem_base
    for i in range(1, n_steps):
        target_mem = mem_base + (rps[i] / 70.0) + (concurrent_users[i] / 160.0)
        decay = 0.985 if target_mem < mem_load[i-1] else 0.65
        mem_load[i] = decay * mem_load[i-1] + (1.0 - decay) * target_mem
    memory_utilization_pct = np.clip(mem_load + np.random.normal(0, 0.7, n_steps), 10.0, 98.0)
    
    # GPU Utilization dynamically scaling with RPS and GPU demand
    gpu_demand = (rps * 0.40) + (concurrent_users * 0.08)
    gpus_in_use = np.maximum(1, np.ceil(gpu_demand / 220.0)).astype(int)
    
    mean_rps = np.mean(rps)
    gpu_utilization_pct = 30.0 + 45.0 * (rps / (mean_rps * 1.8))
    gpu_utilization_pct = np.clip(gpu_utilization_pct + np.random.normal(0, 1.8, n_steps), 5.0, 98.5)
    
    # 6. Kubernetes HPA Pod Scaling Engine (STRICT MAX_PODS = 120)
    target_cpu_util = 70.0
    min_pods, max_pods = 5, 120
    
    active_pods = np.zeros(n_steps, dtype=int)
    active_pods[0] = 10
    
    for i in range(1, n_steps):
        current_pods = active_pods[i-1]
        desired = int(np.ceil(current_pods * (cpu_utilization_pct[i-1] / target_cpu_util)))
        desired = np.clip(desired, min_pods, max_pods)
        
        if desired > current_pods:
            active_pods[i] = desired
        else:
            active_pods[i] = max(desired, current_pods - 2)

    # 7. Assemble Final DataFrame
    df = pd.DataFrame({
        "timestamp": timestamps,
        "requests_per_second": np.round(rps, 2),
        "requests_per_5min": np.round(rps * 300, 0).astype(int),
        "concurrent_users": np.round(concurrent_users, 0).astype(int),
        "cpu_utilization_pct": np.round(cpu_utilization_pct, 2),
        "memory_utilization_pct": np.round(memory_utilization_pct, 2),
        "gpu_utilization_pct": np.round(gpu_utilization_pct, 2),
        "gpus_in_use": gpus_in_use,
        "active_pods": active_pods,
        "is_job_churn_spike": churn_multiplier > 1.05,
        "is_flash_event_spike": flash_mask,
        "spike_multiplier": np.round(churn_multiplier * flash_multiplier, 2)
    })
    
    out_path = os.path.join(DATA_DIR, output_filename)
    df.to_csv(out_path, index=False)
    print(f"[SUCCESS] Synthetic dataset generated ({len(df):,} rows). Saved to: {out_path}")
    
    return df

if __name__ == "__main__":
    df = generate_hpa_synthetic_dataset(days=90)
