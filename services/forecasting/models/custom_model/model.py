import sys
import os
import time
from typing import Dict, List, Any, Optional
import pandas as pd
import numpy as np
import torch

# Ensure psa-net/src is accessible
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
PSANET_SRC = os.path.join(PROJECT_ROOT, "psa-net", "src")
if not os.path.exists(PSANET_SRC):
    PSANET_SRC = os.path.join(PROJECT_ROOT, "temp", "psa-net", "src")
if PSANET_SRC not in sys.path:
    sys.path.insert(0, PSANET_SRC)

from psanet.model import PSANet, PSANetConfig
from psanet.dataset import TelemetryDataset, make_splits
from psanet.losses import quantile_loss

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from base_model import BaseForecaster


class PSANetForecaster(BaseForecaster):
    """
    Forecaster Wrapper for PSA-Net (Patch-Spectral Attention Network).
    Implements the unified BaseForecaster interface.

    feature_cols: target columns to forecast (n_targets).
    context_cols: input-only columns (not forecast, but seen by model as context).
    full feature list for the model = feature_cols + context_cols (targets first).
    """
    def __init__(
        self,
        input_window: int = 120,
        forecast_horizon: int = 15,
        patch_len: int = 15,
        patch_stride: int = 15,
        d_model: int = 128,
        n_heads: int = 4,
        n_layers: int = 3,
        steps_per_day: int = 1440
    ):
        self.input_window = input_window
        self.forecast_horizon = forecast_horizon
        self.patch_len = patch_len
        self.patch_stride = patch_stride
        self.d_model = d_model
        self.n_heads = n_heads
        self.n_layers = n_layers
        self.steps_per_day = steps_per_day

        self.model = None
        self.mean = None
        self.std = None
        self.feature_cols: List[str] = []
        self.context_cols: List[str] = []
        self.all_feature_cols: List[str] = []
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    def fit(
        self,
        train_df: pd.DataFrame,
        feature_cols: List[str],
        target_col: str = "requests_per_second",
        epochs: int = 30,
        batch_size: int = 128,
        lr: float = 3e-4,
        patience: int = 5,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Fits PSA-Net on the training dataframe.

        feature_cols: target columns (what the model forecasts).
        context_cols (via kwargs): input-only columns (not forecast).
        """
        from torch.cuda.amp import autocast, GradScaler

        self.feature_cols = list(feature_cols)
        self.context_cols = list(kwargs.get("context_cols", []))
        self.all_feature_cols = self.feature_cols + self.context_cols

        cfg = PSANetConfig(
            n_features=len(self.all_feature_cols),
            n_targets=len(self.feature_cols),
            input_window=self.input_window,
            forecast_horizon=self.forecast_horizon,
            patch_len=self.patch_len,
            patch_stride=self.patch_stride,
            d_model=self.d_model,
            n_heads=self.n_heads,
            n_layers=self.n_layers,
            steps_per_day=self.steps_per_day,
            use_spectral_branch=True,
            use_seasonal_embed=True,
            use_spike_bank=True,
        )

        train_ds, val_ds = make_splits(
            train_df, self.all_feature_cols, cfg,
            val_fraction=kwargs.get("val_fraction", 0.15),
        )
        self.mean, self.std = train_ds.mean, train_ds.std

        num_workers = min(4, os.cpu_count() or 1)
        train_loader = torch.utils.data.DataLoader(
            train_ds, batch_size=batch_size, shuffle=True, drop_last=True,
            num_workers=num_workers, pin_memory=True, persistent_workers=True,
            prefetch_factor=4,
        )
        val_loader = torch.utils.data.DataLoader(
            val_ds, batch_size=min(batch_size, len(val_ds)), shuffle=False,
            num_workers=num_workers, pin_memory=True, persistent_workers=True,
        )

        self.model = PSANet(cfg).to(self.device)

        # GPU optimizations
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.benchmark = True
        if hasattr(torch, "compile"):
            self.model = torch.compile(self.model, mode="reduce-overhead")

        optimizer = torch.optim.AdamW(self.model.parameters(), lr=lr, weight_decay=0.01)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs, eta_min=lr * 0.01)
        scaler = GradScaler(enabled=self.device.type == "cuda")
        quantiles = [0.1, 0.5, 0.9]

        from rich.console import Console
        from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
        from rich.table import Table

        console = Console()
        console.print(
            f"[bold green]▶ [PSA-Net][/bold green] Initializing model on [cyan]{self.device}[/cyan] "
            f"(Parameters: [bold]{self.model.param_count():,}[/bold], "
            f"Targets: [bold]{len(self.feature_cols)}[/bold], "
            f"Context: [bold]{len(self.context_cols)}[/bold])..."
        )

        history = {"train_loss": [], "val_loss": []}
        best_val_loss = float("inf")
        best_state = None
        best_epoch = 0
        epochs_no_improve = 0

        table = Table(
            title="[bold yellow]PSA-Net Training Metrics[/bold yellow]",
            header_style="bold magenta",
        )
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
            console=console,
        ) as progress:
            epoch_task = progress.add_task("[yellow]Training Epochs...", total=epochs)
            for ep in range(epochs):
                # --- Train ---
                self.model.train()
                train_loss = 0.0
                batch_task = progress.add_task(f"[cyan]Epoch {ep+1}/{epochs}", total=len(train_loader))
                for hist, tod, dow, target in train_loader:
                    hist = hist.to(self.device, non_blocking=True)
                    tod = tod.to(self.device, non_blocking=True)
                    dow = dow.to(self.device, non_blocking=True)
                    target = target.to(self.device, non_blocking=True)

                    optimizer.zero_grad(set_to_none=True)
                    with autocast(enabled=self.device.type == "cuda"):
                        pred = self.model(hist, tod, dow)
                        loss = quantile_loss(pred, target, quantiles)
                    scaler.scale(loss).backward()
                    scaler.unscale_(optimizer)
                    torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
                    scaler.step(optimizer)
                    scaler.update()
                    train_loss += loss.item()
                    progress.update(batch_task, advance=1)

                train_loss /= len(train_loader)
                progress.remove_task(batch_task)

                # --- Validate ---
                self.model.eval()
                val_loss = 0.0
                with torch.no_grad():
                    for hist, tod, dow, target in val_loader:
                        hist = hist.to(self.device, non_blocking=True)
                        tod = tod.to(self.device, non_blocking=True)
                        dow = dow.to(self.device, non_blocking=True)
                        target = target.to(self.device, non_blocking=True)
                        with autocast(enabled=self.device.type == "cuda"):
                            pred = self.model(hist, tod, dow)
                            val_loss += quantile_loss(pred, target, quantiles).item()
                val_loss /= len(val_loader)
                scheduler.step()

                current_lr = scheduler.get_last_lr()[0]
                history["train_loss"].append(train_loss)
                history["val_loss"].append(val_loss)

                # --- Early stopping check ---
                if val_loss < best_val_loss:
                    best_val_loss = val_loss
                    best_epoch = ep + 1
                    best_state = {k: v.cpu().clone() for k, v in self.model.state_dict().items()}
                    epochs_no_improve = 0
                    status = "[bold green]✔ best[/bold green]"
                else:
                    epochs_no_improve += 1
                    status = f"[dim]{epochs_no_improve}/{patience}[/dim]"

                table.add_row(
                    f"{ep+1}/{epochs}",
                    f"{train_loss:.5f}",
                    f"{val_loss:.5f}",
                    f"{current_lr:.2e}",
                    status,
                )
                progress.update(epoch_task, advance=1)

                if epochs_no_improve >= patience:
                    console.print(f"[bold yellow]Early stopping at epoch {ep+1}[/bold yellow]")
                    break

        elapsed = time.time() - t_start
        console.print(table)
        console.print(
            f"[bold green]✔ Training complete in {elapsed:.0f}s[/bold green] "
            f"(best val_loss={best_val_loss:.5f} at epoch {best_epoch})"
        )

        # Restore best weights
        if best_state is not None:
            self.model.load_state_dict({k: v.to(self.device) for k, v in best_state.items()})

        history["best_epoch"] = best_epoch
        history["best_val_loss"] = best_val_loss
        return history

    def predict(self, context_df: pd.DataFrame, horizon: int = 15) -> pd.DataFrame:
        if self.model is None:
            raise RuntimeError("Model has not been trained yet. Call fit() first.")
        self.model.eval()
        vals = (context_df[self.all_feature_cols].values[-self.input_window:] - self.mean) / self.std
        hist_tensor = torch.tensor(vals, dtype=torch.float32).unsqueeze(0).to(self.device)

        with torch.no_grad():
            preds = self.model(hist_tensor)  # [1, horizon, n_targets, 3]
            # median quantile (q=0.5)
            preds_unscaled = preds[0, :, :, 1].cpu().numpy() * self.std[:len(self.feature_cols)] + self.mean[:len(self.feature_cols)]

        res_df = pd.DataFrame(preds_unscaled, columns=self.feature_cols)
        return res_df

    def save(self, filepath: str) -> None:
        if self.model is not None:
            os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
            torch.save({
                "model_state": self.model.state_dict(),
                "mean": self.mean,
                "std": self.std,
                "feature_cols": self.feature_cols,
                "context_cols": self.context_cols,
                "all_feature_cols": self.all_feature_cols,
                "config": self.model.cfg,
            }, filepath)
            print(f"[PSA-Net] Saved checkpoint to {filepath}")

    def load(self, filepath: str) -> None:
        checkpoint = torch.load(filepath, map_location=self.device, weights_only=False)
        cfg = checkpoint["config"]
        self.model = PSANet(cfg).to(self.device)
        self.model.load_state_dict(checkpoint["model_state"])
        self.mean = checkpoint["mean"]
        self.std = checkpoint["std"]
        self.feature_cols = checkpoint.get("feature_cols", [])
        self.context_cols = checkpoint.get("context_cols", [])
        self.all_feature_cols = checkpoint.get("all_feature_cols", self.feature_cols + self.context_cols)
        print(f"[PSA-Net] Loaded checkpoint from {filepath}")
