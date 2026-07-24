"""
Model Evaluation Script for HPA++ Forecasting Checkpoints & Baselines.

Evaluates trained model checkpoints (PSA-Net, PatchTST, Prophet) on the
out-of-distribution test set (data/synthetic_hpa_traffic_shifted_test.csv).

Computes:
  - MAE (Mean Absolute Error)
  - RMSE (Root Mean Squared Error)
  - WAPE (Weighted Absolute Percentage Error)
  - 80% Coverage Percentage (Actuals inside [q_0.1, q_0.9] bounds)
"""

import sys
import os
import argparse
import warnings
import numpy as np
import pandas as pd
import torch

warnings.filterwarnings("ignore")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
PSANET_SRC = os.path.join(PROJECT_ROOT, "psa-net", "src")
CUSTOM_MODEL_DIR = os.path.join(PROJECT_ROOT, "services", "forecasting", "models", "custom_model")

if PSANET_SRC not in sys.path:
    sys.path.insert(0, PSANET_SRC)
if CUSTOM_MODEL_DIR not in sys.path:
    sys.path.insert(0, CUSTOM_MODEL_DIR)

from rich.console import Console
from rich.table import Table

from psanet.model import PSANet, PSANetConfig
from psanet.dataset import TelemetryDataset

def calculate_metrics(y_true, y_pred, y_lo=None, y_hi=None):
    mae = np.mean(np.abs(y_true - y_pred))
    rmse = np.sqrt(np.mean((y_true - y_pred) ** 2))
    wape = np.sum(np.abs(y_true - y_pred)) / (np.sum(np.abs(y_true)) + 1e-6) * 100.0
    
    coverage = None
    if y_lo is not None and y_hi is not None:
        coverage = np.mean((y_true >= y_lo) & (y_true <= y_hi)) * 100.0
        
    return {
        "mae": mae,
        "rmse": rmse,
        "wape": wape,
        "coverage": coverage
    }

def evaluate_pytorch_model(checkpoint_path: str, test_csv: str):
    console = Console()
    console.print(f"[bold green]▶ Evaluating Checkpoint:[/bold green] [cyan]{checkpoint_path}[/cyan]")
    
    if not os.path.exists(checkpoint_path):
        raise FileNotFoundError(f"Checkpoint not found at {checkpoint_path}")
    if not os.path.exists(test_csv):
        raise FileNotFoundError(f"Test CSV not found at {test_csv}")
        
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    checkpoint = torch.load(checkpoint_path, map_location=device)
    
    cfg = checkpoint["config"]
    feature_cols = checkpoint["feature_cols"]
    mean, std = checkpoint["mean"], checkpoint["std"]
    
    model = PSANet(cfg).to(device)
    model.load_state_dict(checkpoint["model_state"])
    model.eval()
    
    df_test = pd.read_csv(test_csv)
    test_ds = TelemetryDataset(df_test, feature_cols, cfg, mean=mean, std=std)
    test_loader = torch.utils.data.DataLoader(test_ds, batch_size=128, shuffle=False)
    
    all_actuals = []
    all_preds_lo = []
    all_preds_med = []
    all_preds_hi = []
    
    with torch.no_grad():
        for hist, tod, dow, target in test_loader:
            hist, tod, dow, target = hist.to(device), tod.to(device), dow.to(device), target.to(device)
            preds = model(hist, tod, dow) # [B, horizon, F, 3]
            
            # Unscale to original units
            target_unscaled = target.cpu().numpy() * std + mean
            pred_unscaled = preds.cpu().numpy() * std[:, None] + mean[:, None]
            
            all_actuals.append(target_unscaled)
            all_preds_lo.append(pred_unscaled[..., 0]) # q=0.1
            all_preds_med.append(pred_unscaled[..., 1]) # q=0.5
            all_preds_hi.append(pred_unscaled[..., 2]) # q=0.9
            
    actuals = np.concatenate(all_actuals, axis=0) # [N, horizon, F]
    preds_lo = np.concatenate(all_preds_lo, axis=0)
    preds_med = np.concatenate(all_preds_med, axis=0)
    preds_hi = np.concatenate(all_preds_hi, axis=0)
    
    table = Table(title=f"[bold yellow]Model Evaluation (Test Set: {os.path.basename(test_csv)})[/bold yellow]", header_style="bold magenta")
    table.add_column("Feature Column", style="cyan")
    table.add_column("MAE", justify="right", style="green")
    table.add_column("RMSE", justify="right", style="yellow")
    table.add_column("WAPE (%)", justify="right", style="magenta")
    table.add_column("80% Coverage (%)", justify="right", style="blue")
    
    for idx, fcol in enumerate(feature_cols):
        f_act = actuals[..., idx]
        f_med = preds_med[..., idx]
        f_lo = preds_lo[..., idx]
        f_hi = preds_hi[..., idx]
        
        m = calculate_metrics(f_act, f_med, f_lo, f_hi)
        table.add_row(
            fcol,
            f"{m['mae']:.4f}",
            f"{m['rmse']:.4f}",
            f"{m['wape']:.2f}%",
            f"{m['coverage']:.2f}%" if m['coverage'] is not None else "N/A"
        )
        
    console.print(table)

def evaluate_prophet(test_csv: str, horizon: int = 15, features=None):
    from prophet import Prophet
    console = Console()
    console.print(f"[bold green]▶ Evaluating Prophet Baseline on Test Set:[/bold green] [cyan]{test_csv}[/cyan]")
    
    if features is None:
        features = ["requests_per_second", "concurrent_users", "cpu_utilization_pct", "memory_utilization_pct", "gpu_utilization_pct"]
        
    df = pd.read_csv(test_csv)
    ts_col = "timestamp" if "timestamp" in df.columns else "ds"
    
    table = Table(title=f"[bold yellow]Prophet Baseline Evaluation (Test Set: {os.path.basename(test_csv)})[/bold yellow]", header_style="bold magenta")
    table.add_column("Feature Column", style="cyan")
    table.add_column("MAE", justify="right", style="green")
    table.add_column("RMSE", justify="right", style="yellow")
    table.add_column("WAPE (%)", justify="right", style="magenta")
    table.add_column("80% Coverage (%)", justify="right", style="blue")

    for fcol in features:
        if fcol not in df.columns:
            continue
        train_slice = df[["ds" if "ds" in df.columns else ts_col, fcol]].rename(columns={ts_col: "ds", "ds": "ds", fcol: "y"})
        m_prophet = Prophet(daily_seasonality=True, weekly_seasonality=True, interval_width=0.8)
        m_prophet.fit(train_slice.iloc[:-horizon])
        
        future = m_prophet.make_future_dataframe(periods=horizon, freq="1min", include_history=False)
        forecast = m_prophet.predict(future)
        
        actual = train_slice["y"].values[-horizon:]
        pred_med = forecast["yhat"].values[:horizon]
        pred_lo = forecast["yhat_lower"].values[:horizon]
        pred_hi = forecast["yhat_upper"].values[:horizon]
        
        m = calculate_metrics(actual, pred_med, pred_lo, pred_hi)
        table.add_row(
            fcol,
            f"{m['mae']:.4f}",
            f"{m['rmse']:.4f}",
            f"{m['wape']:.2f}%",
            f"{m['coverage']:.2f}%" if m['coverage'] is not None else "N/A"
        )

    console.print(table)

def main():
    parser = argparse.ArgumentParser(description="Evaluate Forecasting Checkpoint or Baseline")
    parser.add_argument("--model", type=str, default="psanet", choices=["psanet", "patchtst", "prophet"])
    parser.add_argument("--checkpoint", type=str, default="services/forecasting/checkpoints/psanet_checkpoint.pt")
    parser.add_argument("--test_csv", type=str, default="data/synthetic_hpa_traffic_shifted_test.csv")
    args = parser.parse_args()
    
    if args.model == "prophet":
        evaluate_prophet(args.test_csv)
    else:
        evaluate_pytorch_model(args.checkpoint, args.test_csv)

if __name__ == "__main__":
    main()
