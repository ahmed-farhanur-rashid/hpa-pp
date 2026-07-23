import numpy as np
import pandas as pd
from scipy import stats

def generate_synthetic_traffic_dataset(
    start_date="2025-01-01",
    days=90,
    freq="5min",
    random_seed=42
):
    np.random.seed(random_seed)
    
    # 1. Create Timestamp Index
    timestamps = pd.date_range(start=start_date, periods=days * 288, freq=freq)
    n_steps = len(timestamps)
    
    # Time factors (in hours/days/years)
    t_hours = (timestamps - timestamps[0]).total_seconds() / 3600.0
    t_days = t_hours / 24.0
    
    # 2. Wikipedia-derived Multi-scale Seasonality & Trend
    # Baseline macro trend (gentle growth with slight organic fluctuation)
    macro_trend = 1000 + 0.5 * t_days + 50 * np.sin(2 * np.pi * t_days / 180.0)
    
    # Daily seasonality (diurnal cycle: peak in afternoon, trough at 4 AM)
    daily_harmonic1 = np.sin(2 * np.pi * (t_hours - 7) / 24.0)
    daily_harmonic2 = 0.3 * np.sin(4 * np.pi * (t_hours - 4) / 24.0)
    daily_seasonality = 1.0 + 0.35 * (daily_harmonic1 + daily_harmonic2)
    
    # Weekly seasonality (lower load on weekends: Sat=5, Sun=6)
    day_of_week = timestamps.dayofweek
    weekly_weights = np.where(day_of_week < 5, 1.0, 0.75 + 0.05 * np.cos(2 * np.pi * day_of_week / 7.0))
    
    # Yearly/Long-term seasonality component
    yearly_seasonality = 1.0 + 0.10 * np.sin(2 * np.pi * t_days / 365.25)
    
    # Combined deterministic base request rate (requests per second)
    base_rps = macro_trend * daily_seasonality * weekly_weights * yearly_seasonality
    
    # 3. Alibaba/Azure-derived Volatility & Autocorrelated Noise (AR(1) process)
    ar1_coef = 0.85  # strong autocorrelation minute-to-minute
    white_noise = np.random.normal(0, 0.05, n_steps)
    ar_noise = np.zeros(n_steps)
    for i in range(1, n_steps):
        ar_noise[i] = ar1_coef * ar_noise[i-1] + white_noise[i]
        
    # Micro-burstiness (heavy-tailed Student-t noise for cluster jitters)
    heavy_tail_bursts = stats.t.rvs(df=4, loc=0, scale=0.02, size=n_steps)
    
    # Combined multiplicative noise factor
    volatility_factor = np.exp(ar_noise + heavy_tail_bursts)
    
    rps = base_rps * volatility_factor
    
    # 4. Flash Sale / Exam Login Spike Injection Layer
    spike_mask = np.zeros(n_steps, dtype=bool)
    spike_intensity_factor = np.ones(n_steps)
    
    # Inject approx N spike events (e.g., flash sales, exam login waves)
    num_spikes = int(days / 5)  # 1 spike every ~5 days on average
    spike_center_indices = np.random.choice(np.arange(288, n_steps - 288), size=num_spikes, replace=False)
    
    for idx in spike_center_indices:
        # Spike duration: 12 to 36 steps (1 hr to 3 hrs)
        duration = np.random.randint(12, 37)
        peak_multiplier = np.random.uniform(2.5, 5.0)  # 2.5x to 5x surge
        
        # Asymmetric spike shape: sharp rise, exponential decay
        rise_steps = int(duration * 0.25)
        decay_steps = duration - rise_steps
        
        start_idx = max(0, idx - rise_steps)
        end_idx = min(n_steps, idx + decay_steps)
        
        # Build profile
        t_spike = np.arange(end_idx - start_idx)
        peak_offset = idx - start_idx
        
        profile = np.zeros(len(t_spike))
        # Rise phase (half-Gaussian or smooth sigmoid)
        rise_mask = t_spike <= peak_offset
        profile[rise_mask] = np.exp(-((t_spike[rise_mask] - peak_offset) ** 2) / (2 * (rise_steps / 2) ** 2))
        
        # Decay phase (exponential decay)
        decay_mask = t_spike > peak_offset
        profile[decay_mask] = np.exp(-(t_spike[decay_mask] - peak_offset) / (decay_steps / 2.5))
        
        spike_effect = 1.0 + (peak_multiplier - 1.0) * profile
        spike_intensity_factor[start_idx:end_idx] = np.maximum(spike_intensity_factor[start_idx:end_idx], spike_effect)
        spike_mask[start_idx:end_idx] = True

    rps = rps * spike_intensity_factor

    # 5. Dataset 4 Multivariate Relationships (Users, CPU, Memory, GPU)
    # Concurrent Users: strong non-linear correlation with RPS + user session persistence noise
    users_per_req = 1.8 + np.random.normal(0, 0.1, n_steps)
    concurrent_users = np.maximum(10, rps * users_per_req + np.random.normal(0, 50, n_steps))
    
    # CPU Utilization (%): Non-linear saturation curve (logistic/softplus response to RPS)
    # Base CPU per 1000 RPS
    raw_cpu_load = (rps / 40.0) + (concurrent_users / 100.0)
    # Non-linear queuing delay / saturation as system approaches capacity
    cpu_utilization_pct = 100.0 / (1.0 + np.exp(-(raw_cpu_load - 50) / 15.0))
    # Add minor measurement noise
    cpu_utilization_pct = np.clip(cpu_utilization_pct + np.random.normal(0, 1.5, n_steps), 5.0, 99.5)
    
    # Memory Utilization (%): Baseline memory footprint + request-proportional buffer cache
    # Memory has high lag/retention compared to CPU (memory doesn't instantly drop after spike)
    mem_base = 35.0
    mem_load = np.zeros(n_steps)
    mem_load[0] = mem_base
    for i in range(1, n_steps):
        # Memory accumulates with load and decays slowly (leaky integrator)
        target_mem = mem_base + (rps[i] / 80.0) + (concurrent_users[i] / 200.0)
        decay_rate = 0.98 if target_mem < mem_load[i-1] else 0.70  # fast allocation, slow GC release
        mem_load[i] = decay_rate * mem_load[i-1] + (1 - decay_rate) * target_mem
    memory_utilization_pct = np.clip(mem_load + np.random.normal(0, 1.0, n_steps), 10.0, 98.0)
    
    # GPU Utilization (%) & Active GPUs: Heavy ML inference / batching behavior
    # Active GPUs scaling with GPU workload demand
    gpu_demand = (rps * 0.45) + (concurrent_users * 0.1)
    gpus_in_use = np.maximum(1, np.ceil(gpu_demand / 250.0)).astype(int)
    
    # GPU Utilization per active GPU cluster
    gpu_utilization_pct = 100.0 * (gpu_demand / (gpus_in_use * 250.0))
    gpu_utilization_pct = np.clip(gpu_utilization_pct + np.random.normal(0, 2.5, n_steps), 0.0, 100.0)
    
    # 6. Kubernetes HPA Pod Scaling Simulation
    # HPA target: 70% CPU utilization, min_pods=5, max_pods=100
    target_cpu_util = 70.0
    min_pods = 5
    max_pods = 100
    
    active_pods = np.zeros(n_steps, dtype=int)
    active_pods[0] = 10
    
    for i in range(1, n_steps):
        # Standard Kubernetes HPA algorithm: desired = ceil(current * (current_metric / target_metric))
        current_pods = active_pods[i-1]
        desired_pods = int(np.ceil(current_pods * (cpu_utilization_pct[i-1] / target_cpu_util)))
        desired_pods = np.clip(desired_pods, min_pods, max_pods)
        
        # Apply scaling stabilization window (e.g. scale up fast, scale down cautiously)
        if desired_pods > current_pods:
            active_pods[i] = desired_pods  # Immediate scale-up
        else:
            # Gradual scale-down (max 2 pods dropped per 5-min step to simulate stabilizationWindowSeconds)
            active_pods[i] = max(desired_pods, current_pods - 2)

    # 7. Assemble DataFrame
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
        "is_spike_event": spike_mask,
        "spike_multiplier": np.round(spike_intensity_factor, 2)
    })
    
    return df

if __name__ == "__main__":
    df = generate_synthetic_traffic_dataset(days=14)
    print("Generated synthetic dataset shape:", df.shape)
    print("\nHead of synthetic dataset:")
    print(df.head())
    print("\nData summary statistics:")
    print(df.describe())

