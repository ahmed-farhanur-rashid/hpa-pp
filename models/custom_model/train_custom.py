import argparse
import pandas as pd
from model import CustomForecaster

def main():
    parser = argparse.ArgumentParser(description="Train Custom Under-Construction Model")
    parser.add_argument("--csv", type=str, default="data/synthetic_hpa_traffic_all_clusters_365d.csv")
    parser.add_argument("--features", nargs="+", default=["requests_per_second", "cpu_utilization_pct", "memory_utilization_pct", "gpu_utilization_pct"])
    parser.add_argument("--target", type=str, default="requests_per_second")
    parser.add_argument("--epochs", type=int, default=10)
    args = parser.parse_args()

    print(f"Loading data from: {args.csv}")
    df = pd.read_csv(args.csv)
    
    forecaster = CustomForecaster(seq_len=60, pred_len=15)
    metrics = forecaster.fit(df, feature_cols=args.features, target_col=args.target)
    print(f"Training result: {metrics}")

if __name__ == "__main__":
    main()
