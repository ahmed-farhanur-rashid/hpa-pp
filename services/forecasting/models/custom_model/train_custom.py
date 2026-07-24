import sys
import os
import argparse

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
PSANET_SRC = os.path.join(PROJECT_ROOT, "psa-net", "src")
if not os.path.exists(PSANET_SRC):
    PSANET_SRC = os.path.join(PROJECT_ROOT, "temp", "psa-net", "src")
CUSTOM_MODEL_DIR = os.path.abspath(os.path.dirname(__file__))

if PSANET_SRC not in sys.path:
    sys.path.insert(0, PSANET_SRC)
if CUSTOM_MODEL_DIR not in sys.path:
    sys.path.insert(0, CUSTOM_MODEL_DIR)

import pandas as pd
from model import PSANetForecaster

TARGET_FEATURES = [
    "requests_per_second",
    "concurrent_users",
    "cpu_utilization_pct",
    "memory_utilization_pct",
    "gpu_utilization_pct",
]

CONTEXT_FEATURES = [
    "cluster_ecommerce",
    "cluster_exam_system",
    "cluster_genai_inference",
    "cluster_streaming",
    "cluster_university_portal",
    "pod_count",
]

DEFAULT_OUT = os.path.join(PROJECT_ROOT, "models", "psa-net.pt")


def main():
    parser = argparse.ArgumentParser(description="Train PSA-Net Custom Forecaster")
    parser.add_argument("--csv", type=str, default="data/synthetic_hpa_traffic_all_clusters_365d.csv")
    parser.add_argument("--features", nargs="+", default=TARGET_FEATURES,
                         help="Target columns: what the model forecasts.")
    parser.add_argument("--context_features", nargs="+", default=CONTEXT_FEATURES,
                         help="Input-only columns: used as context, never forecast.")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch_size", type=int, default=128)
    parser.add_argument("--input_window", type=int, default=120)
    parser.add_argument("--horizon", type=int, default=15)
    parser.add_argument("--patience", type=int, default=5)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--out", type=str, default=DEFAULT_OUT)
    args = parser.parse_args()

    csv_path = args.csv
    if not os.path.isabs(csv_path):
        csv_path = os.path.join(PROJECT_ROOT, csv_path)

    print(f"Loading preprocessed dataset from: {csv_path}")
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Dataset not found at {csv_path}. Run 'python scripts/prep_data.py' first.")

    df = pd.read_csv(csv_path)
    print(f"Dataset loaded ({len(df):,} rows, {len(df.columns)} columns).")
    print(f"Targets ({len(args.features)}): {args.features}")
    print(f"Context-only ({len(args.context_features)}): {args.context_features}")

    forecaster = PSANetForecaster(
        input_window=args.input_window,
        forecast_horizon=args.horizon,
        patch_len=15,
        patch_stride=15,
    )

    metrics = forecaster.fit(
        df,
        feature_cols=args.features,
        context_cols=args.context_features,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        patience=args.patience,
    )

    forecaster.save(args.out)
    print(f"Training completed successfully! Model checkpoint saved to {args.out}")


if __name__ == "__main__":
    main()
