"""
Training script for the PatchTST baseline. Self-contained within this folder
— uses dataset.py (a dependency-free copy of the same windowing/normalization
logic used in the psanet/ folder) so the train/val split and normalization
match PSA-Net's exactly, without importing across folders.

Usage:
    python train_patchtst.py --csv path/to/hpa_data.csv --features col1 col2 ...
"""

import argparse
import os
import time

import pandas as pd
import torch
from torch.cuda.amp import autocast, GradScaler
from torch.utils.data import DataLoader

from dataset import TelemetryDataset
from patchtst import PatchTST, PatchTSTConfig

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
DEFAULT_OUT = os.path.join(PROJECT_ROOT, "models", "patchtst.pt")

TARGET_FEATURES = [
    "requests_per_second",
    "cpu_utilization_pct",
    "memory_utilization_pct",
    "gpu_utilization_pct",
]


def quantile_loss(preds: torch.Tensor, target: torch.Tensor, quantiles: list) -> torch.Tensor:
    """Pinball / quantile loss. preds: [B, horizon, F, n_quantiles], target: [B, horizon, F]."""
    target = target.unsqueeze(-1)
    losses = []
    for i, q in enumerate(quantiles):
        err = target[..., 0] - preds[..., i]
        losses.append(torch.max((q - 1) * err, q * err))
    return torch.stack(losses, dim=-1).mean()


def train(args):
    csv_path = args.csv
    if not os.path.isabs(csv_path):
        csv_path = os.path.join(PROJECT_ROOT, csv_path)

    df = pd.read_csv(csv_path)
    feature_cols = args.features

    n = len(df)
    split = int(n * 0.85)
    train_df, val_df = df.iloc[:split], df.iloc[split:]

    train_ds = TelemetryDataset(train_df, feature_cols, args.input_window, args.horizon,
                                 args.patch_stride, patch_len=args.patch_len,
                                 steps_per_day=args.steps_per_day)
    val_ds = TelemetryDataset(val_df, feature_cols, args.input_window, args.horizon,
                               args.patch_stride, patch_len=args.patch_len,
                               steps_per_day=args.steps_per_day,
                               mean=train_ds.mean, std=train_ds.std)

    if len(train_ds) == 0 or len(val_ds) == 0:
        raise ValueError(
            f"Empty train or val split (train={len(train_ds)}, val={len(val_ds)}). "
            f"Need >= input_window+horizon = {args.input_window + args.horizon} rows per split."
        )

    num_workers = min(4, os.cpu_count() or 1)
    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True,
                               drop_last=True, num_workers=num_workers, pin_memory=True)
    val_loader = DataLoader(val_ds, batch_size=min(args.batch_size, len(val_ds)),
                             shuffle=False, num_workers=num_workers, pin_memory=True)

    cfg = PatchTSTConfig(
        n_features=len(feature_cols), input_window=args.input_window,
        forecast_horizon=args.horizon, patch_len=args.patch_len,
        patch_stride=args.patch_stride, d_model=args.d_model, n_heads=args.n_heads,
        n_layers=args.n_layers, n_quantiles=3,
    )

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = PatchTST(cfg).to(device)
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
    from rich.table import Table

    console = Console()
    console.print(f"[bold green]▶ [PatchTST][/bold green] Initializing model on [cyan]{device}[/cyan] (Parameters: [bold]{model.param_count():,}[/bold])...")

    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs, eta_min=args.lr * 0.01)
    scaler = GradScaler(enabled=device == "cuda")
    quantiles = [0.1, 0.5, 0.9]

    best_val_loss = float("inf")
    best_state = None
    best_epoch = 0
    epochs_no_improve = 0

    table = Table(title="[bold yellow]PatchTST Training Metrics[/bold yellow]", header_style="bold magenta")
    table.add_column("Epoch", justify="center", style="cyan")
    table.add_column("Train Loss", justify="right", style="green")
    table.add_column("Val Loss", justify="right", style="blue")
    table.add_column("LR", justify="right", style="dim")
    table.add_column("Status", justify="center", style="dim")

    t_start = time.time()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console
    ) as progress:
        epoch_task = progress.add_task("[yellow]Training Epochs...", total=args.epochs)
        for epoch in range(args.epochs):
            model.train()
            train_loss = 0.0
            batch_task = progress.add_task(f"[cyan]Epoch {epoch+1}/{args.epochs}", total=len(train_loader))
            for hist, tod, dow, target in train_loader:
                hist, target = hist.to(device, non_blocking=True), target.to(device, non_blocking=True)
                opt.zero_grad(set_to_none=True)
                with autocast(enabled=device == "cuda"):
                    pred = model(hist)
                    loss = quantile_loss(pred, target, quantiles)
                scaler.scale(loss).backward()
                scaler.unscale_(opt)
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                scaler.step(opt)
                scaler.update()
                train_loss += loss.item()
                progress.update(batch_task, advance=1)

            train_loss /= len(train_loader)
            progress.remove_task(batch_task)

            model.eval()
            val_loss = 0.0
            with torch.no_grad():
                for hist, tod, dow, target in val_loader:
                    hist, target = hist.to(device, non_blocking=True), target.to(device, non_blocking=True)
                    with autocast(enabled=device == "cuda"):
                        pred = model(hist)
                        val_loss += quantile_loss(pred, target, quantiles).item()
            val_loss /= len(val_loader)
            scheduler.step()

            current_lr = scheduler.get_last_lr()[0]

            if val_loss < best_val_loss:
                best_val_loss = val_loss
                best_epoch = epoch + 1
                best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
                epochs_no_improve = 0
                status = "[bold green]✔ best[/bold green]"
            else:
                epochs_no_improve += 1
                status = f"[dim]{epochs_no_improve}/{args.patience}[/dim]"

            table.add_row(
                f"{epoch+1}/{args.epochs}", f"{train_loss:.5f}", f"{val_loss:.5f}",
                f"{current_lr:.2e}", status,
            )
            progress.update(epoch_task, advance=1)

            if epochs_no_improve >= args.patience:
                console.print(f"[bold yellow]Early stopping at epoch {epoch+1}[/bold yellow]")
                break

    elapsed = time.time() - t_start
    console.print(table)
    console.print(
        f"[bold green]✔ Training complete in {elapsed:.0f}s[/bold green] "
        f"(best val_loss={best_val_loss:.5f} at epoch {best_epoch})"
    )

    if best_state is not None:
        model.load_state_dict({k: v.to(device) for k, v in best_state.items()})

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    torch.save({
        "model_state": model.state_dict(),
        "config": cfg,
        "mean": train_ds.mean,
        "std": train_ds.std,
        "feature_cols": feature_cols,
    }, args.out)
    console.print(f"[bold green]✔ Saved PatchTST checkpoint to[/bold green] [cyan]{args.out}[/cyan]")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--csv", type=str, default="data/synthetic_hpa_traffic_all_clusters_365d.csv")
    p.add_argument("--features", nargs="+", default=TARGET_FEATURES)
    p.add_argument("--steps_per_day", type=int, default=1440)
    p.add_argument("--input_window", type=int, default=120)
    p.add_argument("--horizon", type=int, default=15)
    p.add_argument("--patch_len", type=int, default=15)
    p.add_argument("--patch_stride", type=int, default=15)
    p.add_argument("--d_model", type=int, default=128)
    p.add_argument("--n_heads", type=int, default=4)
    p.add_argument("--n_layers", type=int, default=3)
    p.add_argument("--batch_size", type=int, default=64)
    p.add_argument("--lr", type=float, default=1e-4)
    p.add_argument("--epochs", type=int, default=30)
    p.add_argument("--patience", type=int, default=5)
    p.add_argument("--out", type=str, default=DEFAULT_OUT)
    args = p.parse_args()
    train(args)
