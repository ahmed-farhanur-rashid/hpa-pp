import os
import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import acf
from statsmodels.tsa.seasonal import STL

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(BASE_DIR, "data")

FILES_TO_VALIDATE = [
    "synthetic_hpa_traffic_ecommerce_365d.csv",
    "synthetic_hpa_traffic_university_portal_365d.csv",
    "synthetic_hpa_traffic_streaming_365d.csv",
    "synthetic_hpa_traffic_exam_system_365d.csv",
    "synthetic_hpa_traffic_genai_inference_365d.csv",
    "synthetic_hpa_traffic_all_clusters_365d.csv",
    "synthetic_hpa_traffic_shifted_test.csv"
]

def validate_single_file(filename: str):
    fpath = os.path.join(DATA_DIR, filename)
    if not os.path.exists(fpath):
        print(f"[ERROR] File not found: {fpath}")
        return
        
    df = pd.read_csv(fpath)
    rps = df["requests_per_second"].values
    n_rows = len(df)
    
    print("\n" + "=" * 90)
    print(f"VALIDATION REPORT FOR: {filename} ({n_rows:,} rows)")
    print("=" * 90)
    
    # 1. ACF Metrics
    acf_vals = acf(rps, nlags=300, fft=True)
    rho_1 = acf_vals[1]
    rho_12 = acf_vals[12]
    rho_288 = acf_vals[288]
    
    print("\n--- 1. AUTOCORRELATION FUNCTION (ACF) ---")
    print(f"  Lag 1  (5 mins):  {rho_1:.4f}  | Target: [0.85, 0.98]")
    print(f"  Lag 12 (1 hour):  {rho_12:.4f}  | Target: > 0.50")
    print(f"  Lag 288 (24h):    {rho_288:.4f}  | Target: >= 0.65")
    
    # 2. Fast STL Decomposition (robust=False)
    stl = STL(rps, period=288, robust=False)
    res = stl.fit()
    var_resid = np.var(res.resid)
    var_seas_resid = np.var(res.seasonal + res.resid)
    f_s = max(0.0, 1.0 - (var_resid / max(1e-6, var_seas_resid)))
    
    print("\n--- 2. SEASONALITY STRENGTH (F_S) ---")
    print(f"  Daily F_S: {f_s:.4f}  | Target: >= 0.65  | Status: {'PASSED' if f_s >= 0.65 else 'SHIFTED / LOW'}")
    
    # 3. Multivariate Cross-Correlation Matrix
    cols = ["requests_per_second", "concurrent_users", "cpu_utilization_pct", "memory_utilization_pct", "gpu_utilization_pct"]
    df_sub = df[cols]
    pearson = df_sub.corr(method="pearson")
    
    print("\n--- 3. CROSS-CORRELATION MATRIX (PEARSON) ---")
    print(pearson.round(4).to_string())
    
    c_users = pearson.loc["requests_per_second", "concurrent_users"]
    c_cpu = pearson.loc["requests_per_second", "cpu_utilization_pct"]
    c_mem = pearson.loc["requests_per_second", "memory_utilization_pct"]
    c_gpu = pearson.loc["requests_per_second", "gpu_utilization_pct"]
    
    print(f"\n  Corr(RPS, Users): {c_users:.4f}  | Target: >= 0.90")
    print(f"  Corr(RPS, CPU):   {c_cpu:.4f}  | Target: >= 0.80")
    print(f"  Corr(RPS, Mem):   {c_mem:.4f}  | Target: >= 0.50")
    print(f"  Corr(RPS, GPU):   {c_gpu:.4f}  | Target: >= 0.50")
    
    # 4. HPA Lag Analysis
    cpu_vals = df["cpu_utilization_pct"].values
    pods_vals = df["active_pods"].values
    lags = np.arange(-3, 4)
    corrs = []
    for k in lags:
        if k > 0:
            c = np.corrcoef(cpu_vals[:-k], pods_vals[k:])[0, 1]
        elif k < 0:
            c = np.corrcoef(cpu_vals[-k:], pods_vals[:k])[0, 1]
        else:
            c = np.corrcoef(cpu_vals, pods_vals)[0, 1]
        corrs.append(c)
        
    peak_k = lags[np.argmax(corrs)]
    print("\n--- 4. HPA CPU -> ACTIVE PODS LAG ---")
    print(f"  Peak Correlation Lag: {peak_k:+d} steps ({peak_k*5:+d} mins) with correlation {np.max(corrs):.4f}")
    
    # 5. Pod Distribution Cap
    max_p = df["active_pods"].max()
    print("\n--- 5. POD CAP VERIFICATION ---")
    print(f"  Max Active Pods: {max_p}  | Target Cap: 120  | Status: {'PASSED' if max_p <= 120 else 'FAILED'}")

def main():
    print("=" * 90)
    print("EXECUTING PLAN V2 — MULTI-FILE VALIDATION SUITE (STEP 5)")
    print("=" * 90)
    
    for fname in FILES_TO_VALIDATE:
        validate_single_file(fname)
        
    print("\n" + "=" * 90)
    print("[SUCCESS] Step 5 Multi-File Validation Complete!")
    print("=" * 90)

if __name__ == "__main__":
    main()
