import sys
import os
from typing import Dict, List, Any
import pandas as pd
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
        self.feature_cols = []
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    def fit(self, train_df: pd.DataFrame, feature_cols: List[str], target_col: str = "requests_per_second", epochs: int = 10, batch_size: int = 128, lr: float = 3e-4, **kwargs) -> Dict[str, Any]:
        """
        Fits PSA-Net on the training dataframe.
        """
        self.feature_cols = feature_cols
        cfg = PSANetConfig(
            n_features=len(feature_cols),
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
            use_spike_bank=True
        )

        train_ds, val_ds = make_splits(train_df, feature_cols, cfg, val_fraction=kwargs.get("val_fraction", 0.15))
        self.mean, self.std = train_ds.mean, train_ds.std

        train_loader = torch.utils.data.DataLoader(train_ds, batch_size=batch_size, shuffle=True, drop_last=True)
        val_loader = torch.utils.data.DataLoader(val_ds, batch_size=min(batch_size, len(val_ds)), shuffle=False)

        self.model = PSANet(cfg).to(self.device)
        optimizer = torch.optim.AdamW(self.model.parameters(), lr=lr)

        from rich.console import Console
        from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
        from rich.table import Table

        console = Console()
        console.print(f"[bold green]▶ [PSA-Net][/bold green] Initializing model on [cyan]{self.device}[/cyan] (Parameters: [bold]{self.model.param_count():,}[/bold])...")
        history = {"train_loss": [], "val_loss": []}

        table = Table(title="[bold yellow]PSA-Net Training Metrics[/bold yellow]", header_style="bold magenta")
        table.add_column("Epoch", justify="center", style="cyan")
        table.add_column("Train Loss", justify="right", style="green")
        table.add_column("Val Loss", justify="right", style="blue")
        table.add_column("Status", justify="center", style="dim")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console
        ) as progress:
            epoch_task = progress.add_task("[yellow]Training Epochs...", total=epochs)
            for ep in range(epochs):
                self.model.train()
                train_loss = 0.0
                batch_task = progress.add_task(f"[cyan]Epoch {ep+1}/{epochs}", total=len(train_loader))
                for hist, tod, dow, target in train_loader:
                    hist, tod, dow, target = hist.to(self.device), tod.to(self.device), dow.to(self.device), target.to(self.device)
                    optimizer.zero_grad()
                    pred = self.model(hist, tod, dow)
                    loss = quantile_loss(pred, target, [0.1, 0.5, 0.9])
                    loss.backward()
                    torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
                    optimizer.step()
                    train_loss += loss.item()
                    progress.update(batch_task, advance=1)

                train_loss /= len(train_loader)
                progress.remove_task(batch_task)

                self.model.eval()
                val_loss = 0.0
                with torch.no_grad():
                    for hist, tod, dow, target in val_loader:
                        hist, tod, dow, target = hist.to(self.device), tod.to(self.device), dow.to(self.device), target.to(self.device)
                        pred = self.model(hist, tod, dow)
                        val_loss += quantile_loss(pred, target, [0.1, 0.5, 0.9]).item()
                val_loss /= len(val_loader)

                history["train_loss"].append(train_loss)
                history["val_loss"].append(val_loss)
                table.add_row(f"{ep+1}/{epochs}", f"{train_loss:.5f}", f"{val_loss:.5f}", "✔")
                progress.update(epoch_task, advance=1)

        console.print(table)
        return history

    def predict(self, context_df: pd.DataFrame, horizon: int = 15) -> pd.DataFrame:
        """
        Generates forecast for future horizon steps.
        """
        if self.model is None:
            raise RuntimeError("Model has not been trained yet. Call fit() first.")
        self.model.eval()
        # Extract features and scale
        vals = (context_df[self.feature_cols].values[-self.input_window:] - self.mean) / self.std
        hist_tensor = torch.tensor(vals, dtype=torch.float32).unsqueeze(0).to(self.device)
        
        with torch.no_grad():
            preds = self.model(hist_tensor) # [1, horizon, F, 3]
            preds_unscaled = preds[0, :, :, 1].cpu().numpy() * self.std + self.mean # median quantile (q=0.5)

        res_df = pd.DataFrame(preds_unscaled, columns=self.feature_cols)
        return res_df

    def save(self, filepath: str) -> None:
        if self.model is not None:
            torch.save({
                "model_state": self.model.state_dict(),
                "mean": self.mean,
                "std": self.std,
                "feature_cols": self.feature_cols,
                "config": self.model.cfg
            }, filepath)
            print(f"[PSA-Net] Saved checkpoint to {filepath}")

    def load(self, filepath: str) -> None:
        checkpoint = torch.load(filepath, map_location=self.device, weights_only=False)
        cfg = checkpoint["config"]
        self.model = PSANet(cfg).to(self.device)
        self.model.load_state_dict(checkpoint["model_state"])
        self.mean = checkpoint["mean"]
        self.std = checkpoint["std"]
        self.feature_cols = checkpoint["feature_cols"]
        print(f"[PSA-Net] Loaded checkpoint from {filepath}")
