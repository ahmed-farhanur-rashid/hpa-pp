import os
import json
import numpy as np
import pandas as pd
from scipy import stats

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(BASE_DIR, "data")
PARAMS_JSON = os.path.join(DATA_DIR, "extracted_parameters.json")

def load_extracted_parameters():
    if os.path.exists(PARAMS_JSON):
        with open(PARAMS_JSON, "r") as f:
            return json.load(f)
    else:
        raise FileNotFoundError(f"Parameters file not found at {PARAMS_JSON}. Run extract_real_parameters.py first.")

# ------------------------------------------------------------------------------
# CLUSTER PROFILE PARAMETERS (Step 1)
# ------------------------------------------------------------------------------
CLUSTER_PROFILES = {
    "ecommerce": {
        "description": "E-Commerce Cluster: Short, intense flash sales, moderate baseline",
        "base_qps": 600.0,
        "gpu_weight": 0.25,
        "cpu_weight": 0.85,
        "churn_spike_lambda": 15.0,  # background job churn spikes/day
        "flash_spike_lambda": 0.35,  # flash sale events/day
        "flash_duration_range": (12, 24), # 1 to 2 hours
        "flash_peak_range": (3.0, 5.0),
        "jitter_amplitude": 0.10,
    },
    "university_portal": {
        "description": "University Portal Cluster: Predictable, massive result/admission day spikes",
        "base_qps": 250.0,
        "gpu_weight": 0.05,
        "cpu_weight": 0.95,
        "churn_spike_lambda": 8.0,
        "flash_spike_lambda": 0.08,  # ~2 large events per month
        "flash_duration_range": (24, 48), # 2 to 4 hours
        "flash_peak_range": (4.5, 7.0),
        "jitter_amplitude": 0.05,
    },
    "streaming": {
        "description": "Live Streaming Cluster: Occasional large live-event spikes, flat baseline",
        "base_qps": 800.0,
        "gpu_weight": 0.60,
        "cpu_weight": 0.70,
        "churn_spike_lambda": 20.0,
        "flash_spike_lambda": 0.15,
        "flash_duration_range": (18, 36), # 1.5 to 3 hours
        "flash_peak_range": (3.0, 6.0),
        "jitter_amplitude": 0.12,
    },
    "exam_system": {
        "description": "Exam System Cluster: Synchronized login waves at exam times, CPU-heavy, GPU-light",
        "base_qps": 300.0,
        "gpu_weight": 0.02,
        "cpu_weight": 1.00,
        "churn_spike_lambda": 10.0,
        "flash_spike_lambda": 0.50, # frequent exam session starts
        "flash_duration_range": (12, 24), # 1 to 2 hours
        "flash_peak_range": (2.5, 4.0),
        "jitter_amplitude": 0.08,
    },
    "genai_inference": {
        "description": "GenAI Serving Cluster: GPU-heavy baseline matching OpenPAI/GenAI trace",
        "base_qps": 450.0,
        "gpu_weight": 1.00,
        "cpu_weight": 0.60,
        "churn_spike_lambda": 25.0,
        "flash_spike_lambda": 0.20,
        "flash_duration_range": (12, 36),
        "flash_peak_range": (2.5, 4.5),
        "jitter_amplitude": 0.15,
    }
}

# ------------------------------------------------------------------------------
# GENERATOR CORE ENGINE WITH JITTER & ANOMALIES (Steps 1, 2, 3)
# ------------------------------------------------------------------------------
def generate_cluster_dataset(
    cluster_name: str,
    days: int = 365,
    start_date: str = "2025-01-01",
    freq: str = "5min",
    random_seed: int = 42,
    enable_jitter: bool = True
) -> pd.DataFrame:
    np.random.seed(random_seed)
    params = load_extracted_parameters()
    prof = CLUSTER_PROFILES[cluster_name]
    
    timestamps = pd.date_range(start=start_date, periods=days * 288, freq=freq)
    n_steps = len(timestamps)
    
    t_hours = (timestamps - timestamps[0]).total_seconds() / 3600.0
    t_days = t_hours / 24.0
    
    # 1. Base Macro Traffic & Seasonality
    wiki_p = params["wikipedia_seasonality"]
    dow_map = wiki_p["dow_multipliers"]
    
    # Step 3: Seasonal Jitter (Weekly amplitude variation & Daily phase drift)
    n_weeks = int(np.ceil(days / 7.0))
    if enable_jitter:
        weekly_jitters = 1.0 + np.clip(np.random.normal(0, prof["jitter_amplitude"], n_weeks), -0.15, 0.15)
        week_indices = (t_days / 7.0).astype(int)
        week_indices = np.clip(week_indices, 0, n_weeks - 1)
        jitter_multiplier = weekly_jitters[week_indices]
        
        phase_drift_hours = np.random.normal(0, 0.25, n_weeks)[week_indices]
    else:
        jitter_multiplier = np.ones(n_steps)
        phase_drift_hours = np.zeros(n_steps)
        
    daily_h1 = np.sin(2 * np.pi * (t_hours - 7.0 + phase_drift_hours) / 24.0)
    daily_h2 = 0.35 * np.sin(4 * np.pi * (t_hours - 4.0 + phase_drift_hours) / 24.0)
    daily_seasonality = 1.0 + 0.55 * (daily_h1 + daily_h2)
    
    dow_indices = timestamps.dayofweek
    weekly_seasonality = np.array([dow_map[str(d)] for d in dow_indices])
    yearly_seasonality = 1.0 + 0.08 * np.sin(2 * np.pi * t_days / 365.25)
    
    base_rps = prof["base_qps"] * daily_seasonality * weekly_seasonality * yearly_seasonality * jitter_multiplier
    
    # 2. Stationary Mean-Reverting AR(1) Volatility
    ar1_params = params["cluster_volatility_ar1"]
    phi_5min = ar1_params["ar1_5min_phi5"]
    noise_std = ar1_params["residual_white_noise_std_5min"]
    nu_deg = ar1_params["student_t_degrees_of_freedom"]
    
    ar_noise = np.zeros(n_steps)
    white_shocks = np.random.normal(0, noise_std, n_steps)
    for i in range(1, n_steps):
        ar_noise[i] = phi_5min * ar_noise[i-1] + white_shocks[i]
        
    heavy_tail = stats.t.rvs(df=nu_deg, loc=0, scale=0.005, size=n_steps)
    volatility = np.exp(np.clip(ar_noise + heavy_tail, -0.25, 0.25))
    rps = base_rps * volatility
    
    # 3. SPIKE GENERATORS
    # (a) Background Job Churn Spikes (FITTED)
    num_job_spikes = int(prof["churn_spike_lambda"] * days)
    churn_mult = np.ones(n_steps)
    churn_indices = np.random.choice(n_steps, size=num_job_spikes, replace=False)
    pareto_b = params["spike_generators"]["background_job_churn_spikes_FITTED"]["pareto_shape_b"]
    for c_idx in churn_indices:
        churn_mult[c_idx] = min(3.0, 1.0 + 0.12 * stats.pareto.rvs(b=pareto_b, scale=1.0))
        
    # (b) Flash-Event Demand Spikes (ASSUMPTION-BASED)
    num_flash_spikes = max(1, int(prof["flash_spike_lambda"] * days))
    flash_mult = np.ones(n_steps)
    flash_mask = np.zeros(n_steps, dtype=bool)
    flash_centers = np.random.choice(np.arange(288, n_steps - 288), size=num_flash_spikes, replace=False)
    
    for f_idx in flash_centers:
        duration = np.random.randint(*prof["flash_duration_range"])
        peak_mult = np.random.uniform(*prof["flash_peak_range"])
        
        rise = max(1, int(duration * 0.25))
        decay = duration - rise
        start_idx = max(0, f_idx - rise)
        end_idx = min(n_steps, f_idx + decay)
        
        t_seq = np.arange(end_idx - start_idx)
        peak_off = f_idx - start_idx
        
        profile = np.zeros(len(t_seq))
        r_mask = t_seq <= peak_off
        profile[r_mask] = np.exp(-((t_seq[r_mask] - peak_off) ** 2) / (2 * (rise / 2) ** 2))
        d_mask = t_seq > peak_off
        profile[d_mask] = np.exp(-(t_seq[d_mask] - peak_off) / (decay / 2.5))
        
        effect = 1.0 + (peak_mult - 1.0) * profile
        flash_mult[start_idx:end_idx] = np.maximum(flash_mult[start_idx:end_idx], effect)
        flash_mask[start_idx:end_idx] = True

    rps = rps * churn_mult * flash_mult

    # 4. STEP 2 ANOMALIES (ASSUMPTION-BASED)
    outage_mask = np.zeros(n_steps, dtype=bool)
    memleak_mask = np.zeros(n_steps, dtype=bool)
    overload_mask = np.zeros(n_steps, dtype=bool)
    
    outage_mult = np.ones(n_steps)
    overload_mult = np.ones(n_steps)
    mem_leak_bias = np.zeros(n_steps)
    
    # (a) Partial Outage
    num_outages = max(1, int(0.05 * days))
    outage_centers = np.random.choice(np.arange(288, n_steps - 288), size=num_outages, replace=False)
    for o_idx in outage_centers:
        dur = np.random.randint(6, 18)
        drop = np.random.uniform(0.10, 0.30)
        end_idx = min(n_steps, o_idx + dur)
        t_drop = np.arange(end_idx - o_idx)
        ramp = drop + (1.0 - drop) * (t_drop / len(t_drop))
        outage_mult[o_idx:end_idx] = ramp
        outage_mask[o_idx:end_idx] = True
        
    # (b) Memory Leak
    num_memleaks = max(1, int(0.03 * days))
    memleak_centers = np.random.choice(np.arange(288, n_steps - 288), size=num_memleaks, replace=False)
    for m_idx in memleak_centers:
        dur = np.random.randint(24, 72)
        end_idx = min(n_steps, m_idx + dur)
        t_leak = np.arange(end_idx - m_idx)
        leak_climb = 0.8 * (t_leak / len(t_leak)) * 50.0
        mem_leak_bias[m_idx:end_idx] = leak_climb
        memleak_mask[m_idx:end_idx] = True
        
    # (c) Sustained Overload Plateau
    num_overloads = max(1, int(0.04 * days))
    overload_centers = np.random.choice(np.arange(288, n_steps - 288), size=num_overloads, replace=False)
    for ov_idx in overload_centers:
        dur = np.random.randint(24, 72)
        end_idx = min(n_steps, ov_idx + dur)
        overload_mult[ov_idx:end_idx] = 4.5
        overload_mask[ov_idx:end_idx] = True

    rps = rps * outage_mult * overload_mult

    # 5. Multivariate System Relationships
    users_per_req = 1.80 + np.random.normal(0, 0.04, n_steps)
    concurrent_users = np.maximum(10, rps * users_per_req + np.random.normal(0, 20, n_steps))
    
    raw_cpu_load = (rps / (35.0 / prof["cpu_weight"])) + (concurrent_users / 100.0)
    cpu_utilization_pct = 100.0 / (1.0 + np.exp(-(raw_cpu_load - 50.0) / 12.0))
    cpu_utilization_pct = np.clip(cpu_utilization_pct + np.random.normal(0, 1.0, n_steps), 5.0, 99.5)
    
    mem_base = 32.0
    mem_load = np.zeros(n_steps)
    mem_load[0] = mem_base
    for i in range(1, n_steps):
        target_mem = mem_base + (rps[i] / 70.0) + (concurrent_users[i] / 160.0) + mem_leak_bias[i]
        decay = 0.995 if memleak_mask[i] else (0.985 if target_mem < mem_load[i-1] else 0.65)
        mem_load[i] = decay * mem_load[i-1] + (1.0 - decay) * target_mem
    memory_utilization_pct = np.clip(mem_load + np.random.normal(0, 0.7, n_steps), 10.0, 98.0)
    
    gpu_demand = (rps * 0.40 * prof["gpu_weight"]) + (concurrent_users * 0.08 * prof["gpu_weight"])
    gpus_in_use = np.maximum(1, np.ceil(gpu_demand / (200.0 * max(0.1, prof["gpu_weight"])))).astype(int)
    
    mean_rps = np.mean(rps)
    gpu_utilization_pct = 20.0 + 55.0 * (rps / (mean_rps * 1.8)) * prof["gpu_weight"]
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

    df = pd.DataFrame({
        "timestamp": timestamps,
        "cluster_name": cluster_name,
        "requests_per_second": np.round(rps, 2),
        "requests_per_5min": np.round(rps * 300, 0).astype(int),
        "concurrent_users": np.round(concurrent_users, 0).astype(int),
        "cpu_utilization_pct": np.round(cpu_utilization_pct, 2),
        "memory_utilization_pct": np.round(memory_utilization_pct, 2),
        "gpu_utilization_pct": np.round(gpu_utilization_pct, 2),
        "gpus_in_use": gpus_in_use,
        "active_pods": active_pods,
        "is_job_churn_spike": churn_mult > 1.05,
        "is_flash_event_spike": flash_mask,
        "is_outage_event": outage_mask,
        "is_memleak_event": memleak_mask,
        "memory_leak_active": mem_leak_bias > 5.0,
        "is_overload_event": overload_mask,
        "spike_multiplier": np.round(churn_mult * flash_mult * outage_mult * overload_mult, 2)
    })
    
    return df

# ------------------------------------------------------------------------------
# STEP 4: DISTRIBUTION-SHIFTED TEST SET GENERATOR
# ------------------------------------------------------------------------------
def generate_shifted_test_dataset(days: int = 30, random_seed: int = 999) -> pd.DataFrame:
    """
    Generates a 30-day held-out test set with deliberately shifted parameters:
      - 35% higher baseline traffic
      - 2.5x higher flash event frequency
      - Inverted weekly seasonality multiplier
    This evaluates model generalization vs overfitting.
    """
    np.random.seed(random_seed)
    params = load_extracted_parameters()
    
    timestamps = pd.date_range(start="2026-01-01", periods=days * 288, freq="5min")
    n_steps = len(timestamps)
    
    t_hours = (timestamps - timestamps[0]).total_seconds() / 3600.0
    t_days = t_hours / 24.0
    
    base_qps = 950.0 + 0.20 * t_days + 35.0 * np.sin(2 * np.pi * t_days / 180.0)
    
    daily_h1 = np.sin(2 * np.pi * (t_hours - 8.5) / 24.0)
    daily_seasonality = 1.0 + 0.60 * daily_h1
    
    dow_indices = timestamps.dayofweek
    weekly_seasonality = np.where(dow_indices >= 5, 1.25, 0.85)
    
    rps = base_qps * daily_seasonality * weekly_seasonality
    
    num_spikes = int(0.50 * days)
    flash_mask = np.zeros(n_steps, dtype=bool)
    flash_mult = np.ones(n_steps)
    centers = np.random.choice(np.arange(288, n_steps - 288), size=num_spikes, replace=False)
    for c in centers:
        dur = np.random.randint(12, 36)
        start, end = c, min(n_steps, c + dur)
        flash_mult[start:end] = np.random.uniform(3.0, 6.0)
        flash_mask[start:end] = True
        
    rps = rps * flash_mult
    
    users = np.maximum(10, rps * 2.1 + np.random.normal(0, 25, n_steps))
    cpu = np.clip(100.0 / (1.0 + np.exp(-(rps/30.0 - 45.0)/10.0)) + np.random.normal(0, 1.0, n_steps), 5.0, 99.5)
    mem = np.clip(35.0 + rps / 60.0 + np.random.normal(0, 1.0, n_steps), 10.0, 98.0)
    mean_rps = np.mean(rps)
    gpu = np.clip(25.0 + 55.0 * (rps / (mean_rps * 1.5)), 5.0, 98.5)
    gpus_in_use = np.maximum(1, np.ceil(rps / 300.0)).astype(int)
    
    active_pods = np.zeros(n_steps, dtype=int)
    active_pods[0] = 10
    for i in range(1, n_steps):
        desired = int(np.ceil(active_pods[i-1] * (cpu[i-1] / 70.0)))
        active_pods[i] = np.clip(desired if desired > active_pods[i-1] else active_pods[i-1] - 2, 5, 120)
        
    df = pd.DataFrame({
        "timestamp": timestamps,
        "cluster_name": "shifted_test_cluster",
        "requests_per_second": np.round(rps, 2),
        "requests_per_5min": np.round(rps * 300, 0).astype(int),
        "concurrent_users": np.round(users, 0).astype(int),
        "cpu_utilization_pct": np.round(cpu, 2),
        "memory_utilization_pct": np.round(mem, 2),
        "gpu_utilization_pct": np.round(gpu, 2),
        "gpus_in_use": gpus_in_use,
        "active_pods": active_pods,
        "is_job_churn_spike": False,
        "is_flash_event_spike": flash_mask,
        "is_outage_event": False,
        "is_memleak_event": False,
        "memory_leak_active": False,
        "is_overload_event": False,
        "spike_multiplier": np.round(flash_mult, 2)
    })
    
    return df

# ------------------------------------------------------------------------------
# MAIN EXECUTION PIPELINE (Steps 1, 2, 3, 4)
# ------------------------------------------------------------------------------
def main():
    print("=" * 90)
    print("EXECUTING PLAN V2 — MULTI-CLUSTER SYNTHETIC DATASET PIPELINE")
    print("=" * 90)
    
    all_cluster_dfs = []
    
    for c_name, c_prof in CLUSTER_PROFILES.items():
        print(f"\n---> Generating {c_name} cluster (365 days / 105,120 rows)...")
        df_c = generate_cluster_dataset(cluster_name=c_name, days=365, random_seed=42 + len(all_cluster_dfs))
        
        filename = f"synthetic_hpa_traffic_{c_name}_365d.csv"
        out_path = os.path.join(DATA_DIR, filename)
        df_c.to_csv(out_path, index=False)
        size_mb = os.path.getsize(out_path) / (1024 * 1024)
        
        all_cluster_dfs.append(df_c)
        
        rps = df_c["requests_per_second"]
        print(f"  [FILE WRITTEN]: {out_path} ({size_mb:.2f} MB)")
        print(f"  Rows: {len(df_c):,} | RPS Min: {rps.min():.2f}, Mean: {rps.mean():.2f}, Max: {rps.max():.2f}")
        print(f"  Anomalies Injected:")
        print(f"    - Flash Spikes:    {df_c['is_flash_event_spike'].sum():,}")
        print(f"    - Outage Events:   {df_c['is_outage_event'].sum():,}")
        print(f"    - Memory Leaks:    {df_c['is_memleak_event'].sum():,}")
        print(f"    - Overload Events: {df_c['is_overload_event'].sum():,}")

    # Concatenate all 5 clusters into combined dataset
    df_combined = pd.concat(all_cluster_dfs, ignore_index=True)
    comb_path = os.path.join(DATA_DIR, "synthetic_hpa_traffic_all_clusters_365d.csv")
    df_combined.to_csv(comb_path, index=False)
    comb_size = os.path.getsize(comb_path) / (1024 * 1024)
    print(f"\n---> [FILE WRITTEN]: Combined Dataset: {comb_path} ({comb_size:.2f} MB, {len(df_combined):,} total rows)")

    # Step 4: Generate Distribution-Shifted Test Set
    print("\n---> Generating Distribution-Shifted Test Set (30 days / 8,640 rows)...")
    df_shifted = generate_shifted_test_dataset(days=30, random_seed=999)
    shift_path = os.path.join(DATA_DIR, "synthetic_hpa_traffic_shifted_test.csv")
    df_shifted.to_csv(shift_path, index=False)
    shift_size = os.path.getsize(shift_path) / (1024 * 1024)
    print(f"  [FILE WRITTEN]: {shift_path} ({shift_size:.2f} MB, {len(df_shifted):,} rows)")
    
    print("\n[SUCCESS] Steps 1, 2, 3, and 4 complete!")

if __name__ == "__main__":
    main()
