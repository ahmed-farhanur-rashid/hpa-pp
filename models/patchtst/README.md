# PatchTST — Channel-Independent Patch Transformer

The standard, well-proven time-series transformer baseline. Chosen
specifically for overfitting resistance: each feature is forecast by the
SAME shared transformer weights, processed independently (channel
independence) — the model can't learn spurious cross-feature correlations
that don't generalize. Params stay constant regardless of feature count
(confirmed: 3/6/20 features all give identical param count).

Reference: Nie et al., "A Time Series is Worth 64 Words" (PatchTST), ICLR 2023.

**Files:** `patchtst.py` (architecture), `train_patchtst.py` (training script),
`dataset.py` (self-contained windowing/normalization — a dependency-free copy
of the same logic used in `../psanet/`, kept identical so the comparison is
fair; if you change one, change the other).

This folder has no dependency on `../psanet/` or `../prophet/` — fully
standalone.

**Data resolution:** defaults assume 1-minute resolution (`steps_per_day=1440`).
Same caveat as PSA-Net: must match your actual data resolution.

**Usage:**
```
python train_patchtst.py --csv data.csv --features requests_per_second cpu_utilization_pct ...
```

Verified: shape-generic, gradients flow correctly, training loss decreases
on synthetic data, fully isolated from the other two folders.
