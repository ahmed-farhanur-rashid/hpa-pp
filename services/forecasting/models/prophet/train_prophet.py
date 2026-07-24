"""
Prophet baseline for HPA++ telemetry forecasting.

Prophet forecasts ONE univariate series at a time (it has no native
multivariate mode), so this script trains one Prophet model per feature
column and reports per-feature + averaged metrics — structured to be
directly comparable to PSA-Net's multivariate output.

This is deliberately the "boring, credible baseline" a hackathon judge
would expect to see beaten: interpretable, well-known, no architecture
novelty, sets a real bar.

Usage:
    python train_prophet.py --csv path/to/hpa_data.csv \
        --features requests_per_second cpu_utilization_pct ... \
        --horizon 12
"""

import argparse
import warnings

import numpy as np
import pandas as pd
from prophet import Prophet

warnings.filterwarnings("ignore")  # Prophet is noisy on stdout/cmdstanpy logs


def rolling_eval(df: pd.DataFrame, feature: str, horizon: int, input_window: int,
                  n_eval_windows: int = 20, freq: str = "1min", max_train_history: int = None):
    """
    Fair comparison to PSA-Net: evaluate on the SAME kind of rolling-origin
    windows (predict `horizon` steps ahead from a cutoff, slide the cutoff),
    not Prophet's usual single train/future split.

    max_train_history: cap on how many rows of history to fit on per window.
    Prophet refits from scratch on every window; at large row counts (e.g.
    2.5M rows @ 1-min resolution) fitting on ALL prior history every time is
    needlessly slow and not how Prophet is normally used in practice. If set,
    each fit uses only the most recent `max_train_history` rows before the
    cutoff (still gives Prophet's seasonality components plenty of cycles to
    fit — e.g. 100k rows @ 1-min is still ~69 days of history).
    """
    n = len(df)
    val_start = int(n * 0.85)  # match PSA-Net's 85/15 split
    errors = []

    # sample n_eval_windows cutoff points spread across the validation region
    max_start = n - horizon
    cutoffs = np.linspace(val_start, max_start - 1, num=n_eval_windows, dtype=int)

    for cutoff in cutoffs:
        train_start = max(0, cutoff - max_train_history) if max_train_history else 0
        ts_col = "timestamp" if "timestamp" in df.columns else "ds"
        train_slice = df.iloc[train_start:cutoff][[ts_col, feature]].rename(
            columns={ts_col: "ds", feature: "y"}
        )
        # Prophet needs enough history to fit seasonality; skip degenerate windows
        if len(train_slice) < input_window:
            continue

        m = Prophet(
            daily_seasonality=True,
            weekly_seasonality=True,
            yearly_seasonality=False,
            interval_width=0.8,  # gives 10/90 quantile-equivalent bounds, comparable to PSA-Net
        )
        m.fit(train_slice)

        future = m.make_future_dataframe(periods=horizon, freq=freq, include_history=False)
        forecast = m.predict(future)

        actual = df.iloc[cutoff: cutoff + horizon][feature].values
        pred_median = forecast["yhat"].values[: len(actual)]
        pred_lo = forecast["yhat_lower"].values[: len(actual)]
        pred_hi = forecast["yhat_upper"].values[: len(actual)]

        mae = np.mean(np.abs(actual - pred_median))
        rmse = np.sqrt(np.mean((actual - pred_median) ** 2))
        # pinball loss at q=0.5 (median) for direct comparability with PSA-Net's quantile_loss
        pinball_median = np.mean(np.maximum(0.5 * (actual - pred_median), -0.5 * (actual - pred_median)))
        coverage = np.mean((actual >= pred_lo) & (actual <= pred_hi))  # should be ~0.8 if calibrated

        errors.append({"mae": mae, "rmse": rmse, "pinball_median": pinball_median, "coverage": coverage})

    return pd.DataFrame(errors)


def main(args):
    df = pd.read_csv(args.csv)
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    all_results = {}
    for feature in args.features:
        print(f"\nFitting Prophet for '{feature}' ({args.n_eval_windows} rolling-origin windows)...")
        res = rolling_eval(
            df, feature, horizon=args.horizon, input_window=args.input_window,
            n_eval_windows=args.n_eval_windows, freq=args.freq,
            max_train_history=args.max_train_history,
        )
        if len(res) == 0:
            print(f"  Skipped: not enough data for '{feature}'.")
            continue
        all_results[feature] = res
        print(f"  MAE={res['mae'].mean():.3f}  RMSE={res['rmse'].mean():.3f}  "
              f"Pinball(median)={res['pinball_median'].mean():.3f}  "
              f"80% interval coverage={res['coverage'].mean():.2%}")

    print("\n=== Summary (averaged across features) ===")
    combined = pd.concat(all_results.values())
    print(f"MAE:      {combined['mae'].mean():.3f}")
    print(f"RMSE:     {combined['rmse'].mean():.3f}")
    print(f"Pinball:  {combined['pinball_median'].mean():.3f}   <-- compare directly against")
    print(f"                                                        PSA-Net's quantile_loss at q=0.5")
    print(f"Coverage: {combined['coverage'].mean():.2%}  (target ~80% for a well-calibrated 80% interval)")

    print("\nNote: metrics are on the ORIGINAL (unnormalized) scale, unlike PSA-Net's "
          "normalized training loss. For an apples-to-apples comparison, either "
          "denormalize PSA-Net's predictions before computing MAE/RMSE/pinball, "
          "or normalize these features before running Prophet.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--csv", type=str, default="data/synthetic_hpa_traffic_all_clusters_365d.csv")
    p.add_argument("--features", nargs="+", default=["requests_per_second", "cpu_utilization_pct", "memory_utilization_pct", "gpu_utilization_pct", "pod_count"])
    p.add_argument("--horizon", type=int, default=60,  # 1h @ 1min
                    help="Forecast horizon in timesteps. Default = 1h at 1-min resolution.")
    p.add_argument("--input_window", type=int, default=1440,  # 24h @ 1min
                    help="Used only to skip degenerate early windows with too little history.")
    p.add_argument("--freq", type=str, default="1min",
                    help="Pandas frequency string matching your data's resolution "
                         "(e.g. '1min' or '5min'). MUST match your data.")
    p.add_argument("--max_train_history", type=int, default=100_000,
                    help="Cap on rows of history used per fit. Important at large row counts "
                         "(e.g. 2.5M rows) since Prophet refits from scratch every window — "
                         "fitting on all prior history every time is slow and unnecessary. "
                         "100k rows @ 1-min resolution is ~69 days, plenty for daily/weekly "
                         "seasonality. Set to None/0 to use full history (slow at scale).")
    p.add_argument("--n_eval_windows", type=int, default=20,
                    help="Number of rolling-origin windows to evaluate on. Prophet refits per "
                         "window, so this is the main cost knob — Prophet is slow (~seconds "
                         "per fit), keep this modest for a hackathon timeline.")
    args = p.parse_args()
    if args.max_train_history == 0:
        args.max_train_history = None
    main(args)
