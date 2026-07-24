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
if not os.path.exists(PSANET_SRC):
    PSANET_SRC = os.path.join(PROJECT_ROOT, "temp", "psa-net", "src")

CUSTOM_MODEL_DIR = os.path.join(PROJECT_ROOT, "services", "forecasting", "models", "custom_model")
PATCHTST_DIR = os.path.join(PROJECT_ROOT, "services", "forecasting", "models", "patchtst")
PROPHET_DIR = os.path.join(PROJECT_ROOT, "services", "forecasting", "models", "prophet")

# Ensure imports resolve correctly — order matters: most-specific first
for d in [PROPHET_DIR, PATCHTST_DIR, CUSTOM_MODEL_DIR, PSANET_SRC]:
    if d not in sys.path:
        sys.path.insert(0, d)

from rich.console import Console
from rich.table import Table

from psanet.model import PSANet, PSANetConfig
from psanet.dataset import TelemetryDataset


# Features that should NOT be evaluated as forecast targets
NON_TARGET_SKIP = {"cluster_ecommerce", "cluster_exam_system", "cluster_genai_inference",
                   "cluster_streaming", "cluster_university_portal", "pod_count"}

DEFAULT_TARGET_FEATURES = [
    "requests_per_second",
    "concurrent_users",
    "cpu_utilization_pct",
    "memory_utilization_pct",
    "gpu_utilization_pct",
]


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
    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)

    cfg = checkpoint["config"]
    is_patchtst = (type(cfg).__name__ == "PatchTSTConfig")

    # --- Resolve feature columns ---
    if "feature_cols" in checkpoint:
        feature_cols = checkpoint["feature_cols"]
    elif "all_feature_cols" in checkpoint:
        feature_cols = checkpoint["all_feature_cols"]
    else:
        # Fallback: infer from config
        if cfg.n_features == 12:
            feature_cols = [
                "cluster_ecommerce", "cluster_exam_system", "cluster_genai_inference",
                "cluster_streaming", "cluster_university_portal",
                "requests_per_second", "concurrent_users", "cpu_utilization_pct",
                "memory_utilization_pct", "gpu_utilization_pct", "requests_per_1min", "pod_count"
            ]
        elif cfg.n_features == 11:
            feature_cols = [
                "cluster_ecommerce", "cluster_exam_system", "cluster_genai_inference",
                "cluster_streaming", "cluster_university_portal",
                "requests_per_second", "concurrent_users", "cpu_utilization_pct",
                "memory_utilization_pct", "gpu_utilization_pct", "pod_count"
            ]
        elif cfg.n_features == 5:
            feature_cols = ["requests_per_second", "concurrent_users",
                            "cpu_utilization_pct", "memory_utilization_pct",
                            "gpu_utilization_pct"]
        else:
            df_sample = pd.read_csv(test_csv, nrows=5)
            num_cols = [c for c in df_sample.columns if c not in ["unique_id", "ds"]]
            feature_cols = num_cols[:cfg.n_features]

    # --- Resolve n_targets and target feature names ---
    if is_patchtst:
        target_cols = feature_cols  # PatchTST predicts all its input features
    else:
        n_targets = getattr(cfg, "n_targets", len(feature_cols))
        target_cols = feature_cols[:n_targets]

    mean_all = checkpoint["mean"]
    std_all = checkpoint["std"]
    df_test = pd.read_csv(test_csv)

    # --- Build model & dataset ---
    if is_patchtst:
        # PatchTST imports (self-contained in patchtst dir)
        patchtst_spec = __import__("patchtst")
        PatchTST = patchtst_spec.PatchTST
        patchtst_ds = __import__("dataset")

        model = PatchTST(cfg).to(device)
        test_ds = patchtst_ds.TelemetryDataset(
            df_test, feature_cols,
            input_window=cfg.input_window,
            forecast_horizon=cfg.forecast_horizon,
            patch_stride=cfg.patch_stride,
            patch_len=cfg.patch_len,
            mean=mean_all, std=std_all,
        )
        # For PatchTST, all features are targets
        mean_targets = mean_all
        std_targets = std_all
    else:
        model = PSANet(cfg).to(device)
        test_ds = TelemetryDataset(df_test, feature_cols, cfg, mean=mean_all, std=std_all)
        # For PSA-Net, only first n_targets features are predicted
        mean_targets = mean_all[:len(target_cols)]
        std_targets = std_all[:len(target_cols)]

    model.load_state_dict(checkpoint["model_state"])
    model.eval()

    console.print(
        f"[dim]Model: {'PatchTST' if is_patchtst else 'PSA-Net'}  |  "
        f"Features: {len(feature_cols)}  |  Targets: {len(target_cols)}  |  "
        f"Window: {cfg.input_window}  |  Horizon: {cfg.forecast_horizon}[/dim]"
    )

    test_loader = torch.utils.data.DataLoader(test_ds, batch_size=128, shuffle=False)

    all_actuals = []
    all_preds_lo = []
    all_preds_med = []
    all_preds_hi = []

    with torch.no_grad():
        for hist, tod, dow, target in test_loader:
            hist = hist.to(device, non_blocking=True)
            tod = tod.to(device, non_blocking=True)
            dow = dow.to(device, non_blocking=True)
            target = target.to(device, non_blocking=True)

            if is_patchtst:
                preds = model(hist)  # [B, horizon, F, 3]
            else:
                preds = model(hist, tod, dow)  # [B, horizon, n_targets, 3]

            # Unscale: target is [B, horizon, n_targets], preds is [B, horizon, n_targets, 3]
            target_np = target.cpu().numpy()
            preds_np = preds.cpu().numpy()

            target_unscaled = target_np * std_targets[None, None, :] + mean_targets[None, None, :]
            pred_unscaled = preds_np * std_targets[None, None, :, None] + mean_targets[None, None, :, None]

            all_actuals.append(target_unscaled)
            all_preds_lo.append(pred_unscaled[..., 0])   # q=0.1
            all_preds_med.append(pred_unscaled[..., 1])  # q=0.5
            all_preds_hi.append(pred_unscaled[..., 2])   # q=0.9

    actuals = np.concatenate(all_actuals, axis=0)      # [N, horizon, n_targets]
    preds_lo = np.concatenate(all_preds_lo, axis=0)
    preds_med = np.concatenate(all_preds_med, axis=0)
    preds_hi = np.concatenate(all_preds_hi, axis=0)

    # --- Display results ---
    table = Table(
        title=f"[bold yellow]Model Evaluation — {os.path.basename(checkpoint_path)}[/bold yellow]"
              f" (Test: {os.path.basename(test_csv)})",
        header_style="bold magenta",
    )
    table.add_column("Feature", style="cyan")
    table.add_column("MAE", justify="right", style="green")
    table.add_column("RMSE", justify="right", style="yellow")
    table.add_column("WAPE (%)", justify="right", style="magenta")
    table.add_column("80% Coverage (%)", justify="right", style="blue")

    for idx, fcol in enumerate(target_cols):
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

    # Aggregate row
    agg_mae = np.mean([np.mean(np.abs(actuals[..., i] - preds_med[..., i])) for i in range(len(target_cols))])
    agg_rmse = np.mean([np.sqrt(np.mean((actuals[..., i] - preds_med[..., i]) ** 2)) for i in range(len(target_cols))])
    table.add_section()
    table.add_row("[bold]Average[/bold]", f"{agg_mae:.4f}", f"{agg_rmse:.4f}", "", "")

    console.print(table)


def evaluate_prophet(test_csv: str, checkpoint_path: str = None, horizon: int = 15):
    console = Console()
    console.print(f"[bold green]▶ Evaluating Prophet Baseline on Test Set:[/bold green] [cyan]{test_csv}[/cyan]")

    df = pd.read_csv(test_csv)
    ts_col = "timestamp" if "timestamp" in df.columns else "ds"

    if checkpoint_path and os.path.exists(checkpoint_path):
        console.print(f"[bold yellow]▶ Loading Prophet checkpoint from:[/bold yellow] [cyan]{checkpoint_path}[/cyan]")
        # Prophet model import from prophet dir
        sys.path.insert(0, PROPHET_DIR)
        from model import ProphetForecaster
        forecaster = ProphetForecaster()
        forecaster.load(checkpoint_path)
        features = forecaster.feature_cols
    else:
        features = DEFAULT_TARGET_FEATURES
        forecaster = None

    table = Table(
        title=f"[bold yellow]Prophet Baseline Evaluation (Test: {os.path.basename(test_csv)})[/bold yellow]",
        header_style="bold magenta",
    )
    table.add_column("Feature Column", style="cyan")
    table.add_column("MAE", justify="right", style="green")
    table.add_column("RMSE", justify="right", style="yellow")
    table.add_column("WAPE (%)", justify="right", style="magenta")
    table.add_column("80% Coverage (%)", justify="right", style="blue")

    if forecaster is not None:
        preds = forecaster.predict(df, horizon=horizon)
        for fcol in features:
            if fcol not in df.columns or fcol not in preds.columns:
                continue
            actual = df[fcol].values[-horizon:]
            pred_med = preds[fcol].values[:horizon]
            pred_lo = preds[f"{fcol}_lower"].values[:horizon] if f"{fcol}_lower" in preds.columns else None
            pred_hi = preds[f"{fcol}_upper"].values[:horizon] if f"{fcol}_upper" in preds.columns else None

            m = calculate_metrics(actual, pred_med, pred_lo, pred_hi)
            table.add_row(
                fcol,
                f"{m['mae']:.4f}",
                f"{m['rmse']:.4f}",
                f"{m['wape']:.2f}%",
                f"{m['coverage']:.2f}%" if m['coverage'] is not None else "N/A"
            )
    else:
        from prophet import Prophet as ProphetModel
        for fcol in features:
            if fcol not in df.columns:
                continue
            train_slice = df[["ds" if "ds" in df.columns else ts_col, fcol]].rename(
                columns={ts_col: "ds", "ds": "ds", fcol: "y"}
            )
            m_prophet = ProphetModel(daily_seasonality=True, weekly_seasonality=True, interval_width=0.8)
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
    parser.add_argument("--model", type=str, default="auto", choices=["auto", "psanet", "patchtst", "prophet"])
    parser.add_argument("--checkpoint", type=str, default=os.path.join(PROJECT_ROOT, "models", "psa-net.pt"))
    parser.add_argument("--test_csv", type=str, default=os.path.join(PROJECT_ROOT, "data", "synthetic_hpa_traffic_shifted_test.csv"))
    args = parser.parse_args()

    # Auto-detect model type
    model_type = args.model
    if model_type == "auto":
        if args.checkpoint.endswith(".json") or "prophet" in args.checkpoint.lower():
            model_type = "prophet"
        else:
            # Try to detect from checkpoint config
            try:
                ckpt = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
                cfg = ckpt.get("config")
                if cfg is not None:
                    if type(cfg).__name__ == "PatchTSTConfig":
                        model_type = "patchtst"
                    else:
                        model_type = "psanet"
                else:
                    model_type = "psanet"
            except Exception:
                model_type = "psanet"

    if model_type == "prophet":
        evaluate_prophet(args.test_csv, checkpoint_path=args.checkpoint if os.path.exists(args.checkpoint) else None)
    else:
        evaluate_pytorch_model(args.checkpoint, args.test_csv)


if __name__ == "__main__":
    main()
