import sys
import os
import argparse

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
PSANET_SRC = os.path.join(PROJECT_ROOT, "psa-net", "src")
CUSTOM_MODEL_DIR = os.path.abspath(os.path.dirname(__file__))

if PSANET_SRC not in sys.path:
    sys.path.insert(0, PSANET_SRC)
if CUSTOM_MODEL_DIR not in sys.path:
    sys.path.insert(0, CUSTOM_MODEL_DIR)

import pandas as pd
from model import PSANetForecaster

DEFAULT_FEATURES = [
    "cluster_ecommerce",
    "cluster_exam_system",
    "cluster_genai_inference",
    "cluster_streaming",
    "cluster_university_portal",
    "requests_per_second",
    "concurrent_users",
    "cpu_utilization_pct",
    "memory_utilization_pct",
    "gpu_utilization_pct",
    "pod_count"
]

def main():
    parser = argparse.ArgumentParser(description="Train PSA-Net Custom Forecaster")
    parser.add_argument("--csv", type=str, default="data/synthetic_hpa_traffic_all_clusters_365d.csv")
    parser.add_argument("--features", nargs="+", default=DEFAULT_FEATURES)
    parser.add_argument("--target", type=str, default="requests_per_second")
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch_size", type=int, default=128)
    parser.add_argument("--input_window", type=int, default=120)
    parser.add_argument("--horizon", type=int, default=15)
    parser.add_argument("--out", type=str, default="services/forecasting/checkpoints/psanet_checkpoint.pt")
    args = parser.parse_args()

    print(f"Loading preprocessed dataset from: {args.csv}")
    if not os.path.exists(args.csv):
        raise FileNotFoundError(f"Dataset not found at {args.csv}. Run 'python prep_data.py' first.")
        
    df = pd.read_csv(args.csv)
    print(f"Dataset loaded ({len(df):,} rows, {len(df.columns)} columns).")
    
    forecaster = PSANetForecaster(
        input_window=args.input_window,
        forecast_horizon=args.horizon,
        patch_len=15,
        patch_stride=15
    )
    
    metrics = forecaster.fit(
        df,
        feature_cols=args.features,
        target_col=args.target,
        epochs=args.epochs,
        batch_size=args.batch_size
    )
    
    forecaster.save(args.out)
    print(f"Training completed successfully! Model checkpoint saved to {args.out}")

if __name__ == "__main__":
    main()
