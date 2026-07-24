"""
Self-contained windowing dataset for PatchTST training.

This is intentionally a plain copy of the same windowing/normalization logic
used by the PSA-Net folder's train.py (same train/val split, same z-score
normalization, same time-of-day/day-of-week indexing) — kept as a separate,
dependency-free copy here so this folder does not import anything from the
psanet/ folder. Keeping the logic identical (not just similar) is what makes
a PatchTST-vs-PSA-Net comparison fair; if you change one, change the other.
"""

import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset


class TelemetryDataset(Dataset):
    def __init__(self, df: pd.DataFrame, feature_cols, input_window: int, forecast_horizon: int,
                 patch_stride: int, patch_len: int = 15, steps_per_day: int = 1440,
                 days_per_week: int = 7, mean=None, std=None):
        self.input_window = input_window
        self.forecast_horizon = forecast_horizon
        self.steps_per_day = steps_per_day
        self.days_per_week = days_per_week
        self.feature_cols = feature_cols

        values = df[feature_cols].values.astype(np.float32)
        if mean is None:
            mean = values.mean(axis=0)
            std = values.std(axis=0) + 1e-6
        self.mean, self.std = mean, std
        self.values = (values - mean) / std

        ts_col = "timestamp" if "timestamp" in df.columns else ("ds" if "ds" in df.columns else df.columns[0])
        dt = pd.to_datetime(df[ts_col])
        # step-of-day, generic over resolution: minutes-since-midnight / minutes-per-step.
        # minutes_per_step derived from steps_per_day (1440 => 1 min/step, 288 => 5 min/step).
        minutes_per_step = 1440 // steps_per_day
        self.tod = ((dt.dt.hour * 60 + dt.dt.minute) // minutes_per_step).values
        self.dow = dt.dt.dayofweek.values

        self.n_patches = (input_window - patch_len) // patch_stride + 1
        self.patch_stride = patch_stride
        self.valid_starts = len(self.values) - input_window - forecast_horizon

    def __len__(self):
        return max(0, self.valid_starts)

    def __getitem__(self, idx):
        hist = self.values[idx: idx + self.input_window]
        target = self.values[idx + self.input_window: idx + self.input_window + self.forecast_horizon]

        patch_starts = np.arange(0, self.n_patches) * self.patch_stride
        patch_starts = patch_starts[patch_starts < self.input_window]
        tod_idx = self.tod[idx + patch_starts] % self.steps_per_day
        dow_idx = self.dow[idx + patch_starts] % self.days_per_week

        return (
            torch.tensor(hist, dtype=torch.float32),
            torch.tensor(tod_idx, dtype=torch.long),   # unused by PatchTST; kept for interface parity
            torch.tensor(dow_idx, dtype=torch.long),   # unused by PatchTST; kept for interface parity
            torch.tensor(target, dtype=torch.float32),
        )
