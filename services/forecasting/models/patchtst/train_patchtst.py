"""
Training script for the PatchTST baseline. Self-contained within this folder
— uses dataset.py (a dependency-free copy of the same windowing/normalization
logic used in the psanet/ folder) so the train/val split and normalization
match PSA-Net's exactly, without importing across folders.

Usage:
    python train_patchtst.py --csv path/to/hpa_data.csv --features col1 col2 ...
"""

import argparse

import pandas as pd
import torch
from torch.utils.data import DataLoader

from dataset import TelemetryDataset
from patchtst import PatchTST, PatchTSTConfig


def quantile_loss(preds: torch.Tensor, target: torch.Tensor, quantiles: list) -> torch.Tensor:
    """Pinball / quantile loss. preds: [B, horizon, F, n_quantiles], target: [B, horizon, F]."""
    target = target.unsqueeze(-1)
    losses = []
    for i, q in enumerate(quantiles):
        err = target[..., 0] - preds[..., i]
        losses.append(torch.max((q - 1) * err, q * err))
    return torch.stack(losses, dim=-1).mean()


def train(args):
    df = pd.read_csv(args.csv)
    feature_cols = args.features

    n = len(df)
    split = int(n * 0.85)
    train_df, val_df = df.iloc[:split], df.iloc[split:]

    train_ds = TelemetryDataset(train_df, feature_cols, args.input_window, args.horizon,
                                 args.patch_stride, steps_per_day=args.steps_per_day)
    val_ds = TelemetryDataset(val_df, feature_cols, args.input_window, args.horizon,
                               args.patch_stride, steps_per_day=args.steps_per_day,
                               mean=train_ds.mean, std=train_ds.std)

    if len(train_ds) == 0 or len(val_ds) == 0:
        raise ValueError(
            f"Empty train or val split (train={len(train_ds)}, val={len(val_ds)}). "
            f"Need >= input_window+horizon = {args.input_window + args.horizon} rows per split."
        )

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True, drop_last=True)
    val_loader = DataLoader(val_ds, batch_size=min(args.batch_size, len(val_ds)), shuffle=False)

    cfg = PatchTSTConfig(
        n_features=len(feature_cols), input_window=args.input_window,
        forecast_horizon=args.horizon, patch_len=args.patch_len,
        patch_stride=args.patch_stride, d_model=args.d_model, n_heads=args.n_heads,
        n_layers=args.n_layers, n_quantiles=3,
    )

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = PatchTST(cfg).to(device)
    print(f"PatchTST params: {model.param_count():,}  |  device: {device}")

    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    quantiles = [0.1, 0.5, 0.9]

    for epoch in range(args.epochs):
        model.train()
        train_loss = 0.0
        for hist, tod, dow, target in train_loader:  # tod/dow unused by PatchTST (no seasonal embed)
            hist, target = hist.to(device), target.to(device)
            opt.zero_grad()
            pred = model(hist)
            loss = quantile_loss(pred, target, quantiles)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            train_loss += loss.item()
        train_loss /= len(train_loader)

        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for hist, tod, dow, target in val_loader:
                hist, target = hist.to(device), target.to(device)
                pred = model(hist)
                val_loss += quantile_loss(pred, target, quantiles).item()
        val_loss /= len(val_loader)

        print(f"epoch {epoch+1:3d}/{args.epochs}  train_loss={train_loss:.4f}  val_loss={val_loss:.4f}")

    torch.save({"model_state": model.state_dict(), "config": cfg, "mean": train_ds.mean, "std": train_ds.std},
               args.out)
    print(f"Saved to {args.out}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--csv", type=str, default="data/synthetic_hpa_traffic_all_clusters_365d.csv")
    p.add_argument("--features", nargs="+", default=["requests_per_second", "cpu_utilization_pct", "memory_utilization_pct", "gpu_utilization_pct", "pod_count"])
    p.add_argument("--steps_per_day", type=int, default=1440)
    p.add_argument("--input_window", type=int, default=1440)
    p.add_argument("--horizon", type=int, default=60)
    p.add_argument("--patch_len", type=int, default=60)
    p.add_argument("--patch_stride", type=int, default=30)
    p.add_argument("--d_model", type=int, default=128)
    p.add_argument("--n_heads", type=int, default=4)
    p.add_argument("--n_layers", type=int, default=3)
    p.add_argument("--batch_size", type=int, default=64)
    p.add_argument("--lr", type=float, default=1e-4)  # PatchTST typically wants a lower LR than PSA-Net
    p.add_argument("--epochs", type=int, default=30)
    p.add_argument("--out", type=str, default="patchtst_checkpoint.pt")
    args = p.parse_args()
    train(args)
