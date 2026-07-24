# Prophet Baseline

The credible "standard classical" forecasting baseline. Fits one univariate
Prophet model per feature column (Prophet has no native multivariate mode),
evaluated on rolling-origin windows matched to the same 85/15 split and
horizon used by the other two folders, for a fair comparison.

**Files:** `train_prophet.py`

**Data resolution:** pass `--freq 1min` (default) or `--freq 5min` to match
your data. At large row counts (e.g. 2.5M rows), `--max_train_history`
(default 100k rows ≈ 69 days at 1-min resolution) caps how much history each
rolling-origin fit uses — Prophet refits from scratch per window, so fitting
on all rows every time is slow and unnecessary; 100k rows is already plenty
for daily/weekly seasonality.

**Usage:**
```
python train_prophet.py --csv data.csv --features requests_per_second cpu_utilization_pct ...
```

**Important:** reports MAE/RMSE/pinball loss in the ORIGINAL (unnormalized)
scale, unlike PSA-Net/PatchTST which train on z-score normalized data. To
compare fairly, denormalize their predictions first, or normalize before
running Prophet — don't compare raw printed numbers across folders directly.

Verified: runs end-to-end on synthetic data, ~0.7s per fit at realistic
per-window data size.
