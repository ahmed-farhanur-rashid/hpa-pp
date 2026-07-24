"""
PatchTST baseline — the standard, well-proven time-series transformer.

Why PatchTST specifically, for "won't overfit":
  1. Patch tokenization: drastically fewer tokens than per-timestep attention
     (e.g. 1440 timesteps -> ~47 patches), less to memorize.
  2. Channel independence (the key regularizer): each feature is forecast by
     the SAME shared transformer weights, processed independently — the
     model literally cannot learn spurious cross-feature correlations that
     don't generalize, because it never sees other channels while predicting
     one. This is the specific design choice the original PatchTST paper
     credits for its strong resistance to overfitting relative to channel-
     mixing transformer forecasters.

This is deliberately close to the original published design (not a novel
variant) — it exists here as a credible, standard baseline to compare
PSA-Net against, the same role Prophet plays.

Reference: Nie et al., "A Time Series is Worth 64 Words: Long-term
Forecasting with Transformers" (PatchTST), ICLR 2023.
"""

from dataclasses import dataclass
import math

import torch
import torch.nn as nn


@dataclass
class PatchTSTConfig:
    n_features: int = 6
    input_window: int = 1440     # 24h @ 1min
    forecast_horizon: int = 60   # 1h @ 1min

    patch_len: int = 60          # 1h @ 1min
    patch_stride: int = 30       # 30min @ 1min

    d_model: int = 128
    n_heads: int = 4
    n_layers: int = 3
    d_ff: int = 256
    dropout: float = 0.2         # higher default than PSA-Net — PatchTST paper uses
                                  # relatively high dropout as part of its overfitting resistance

    n_quantiles: int = 3


class PatchTST(nn.Module):
    """
    Channel-independent patch transformer.

    Input [B, T, F] is treated as F independent univariate series of length T.
    Each is patched and embedded, run through a SHARED transformer encoder
    (weights shared across all F channels — this is what makes it channel-
    independent AND parameter-efficient), then a shared linear head maps the
    flattened patch representations to a per-channel forecast.
    """

    def __init__(self, cfg: PatchTSTConfig):
        super().__init__()
        self.cfg = cfg
        self.n_patches = (cfg.input_window - cfg.patch_len) // cfg.patch_stride + 1

        self.patch_embed = nn.Linear(cfg.patch_len, cfg.d_model)
        self.pos_embed = nn.Parameter(torch.randn(1, self.n_patches, cfg.d_model) * 0.02)
        self.dropout = nn.Dropout(cfg.dropout)

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=cfg.d_model, nhead=cfg.n_heads, dim_feedforward=cfg.d_ff,
            dropout=cfg.dropout, activation="gelu", batch_first=True,
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=cfg.n_layers)

        # SHARED head across all channels (channel independence => same weights reused)
        self.head = nn.Linear(self.n_patches * cfg.d_model, cfg.forecast_horizon * cfg.n_quantiles)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: [B, T, F]
        cfg = self.cfg
        B, T, Fdim = x.shape

        x = x.permute(0, 2, 1).reshape(B * Fdim, T)  # [B*F, T] — flatten channel into batch dim
        patches = x.unfold(dimension=1, size=cfg.patch_len, step=cfg.patch_stride)  # [B*F, n_patches, patch_len]

        tokens = self.patch_embed(patches) + self.pos_embed  # [B*F, n_patches, d_model]
        tokens = self.dropout(tokens)
        encoded = self.encoder(tokens)  # [B*F, n_patches, d_model] — SAME weights for every channel

        flat = encoded.reshape(B * Fdim, -1)
        out = self.head(flat)  # [B*F, horizon*n_quantiles]
        out = out.reshape(B, Fdim, cfg.forecast_horizon, cfg.n_quantiles)
        out = out.permute(0, 2, 1, 3)  # [B, horizon, F, n_quantiles] — match PSA-Net's output shape
        return out

    def param_count(self) -> int:
        return sum(p.numel() for p in self.parameters())


if __name__ == "__main__":
    # Smoke test: verify shapes, generic over feature count, and confirm channel
    # independence (shared weights => param count does NOT scale with n_features,
    # unlike PSA-Net's flatten-head).
    for n_feat in [3, 6, 20]:
        cfg = PatchTSTConfig(n_features=n_feat, input_window=1440, forecast_horizon=60,
                              patch_len=60, patch_stride=30, d_model=64, n_heads=4, n_layers=2,
                              n_quantiles=3)
        model = PatchTST(cfg)
        B = 4
        x = torch.randn(B, cfg.input_window, cfg.n_features)
        out = model(x)
        expected = (B, cfg.forecast_horizon, cfg.n_features, cfg.n_quantiles)
        assert out.shape == expected, f"shape mismatch: {out.shape} vs {expected}"

        target = torch.randn(B, cfg.forecast_horizon, cfg.n_features)
        target = target.unsqueeze(-1)
        loss = ((out - target) ** 2).mean()
        loss.backward()

        print(f"n_features={n_feat:3d}  params={model.param_count():,}  "
              f"out_shape={tuple(out.shape)}  grad_ok=True")

    print("\nNote params are IDENTICAL across n_features (channel-independent, shared weights) "
          "— unlike PSA-Net where param count grows with n_features due to its flatten-head. "
          "This is the expected, correct behavior for a channel-independent design.")
