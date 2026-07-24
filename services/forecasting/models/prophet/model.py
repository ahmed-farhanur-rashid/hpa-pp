import os
import sys
import json
from typing import Dict, List, Any
import pandas as pd
from prophet import Prophet
from prophet.serialize import model_to_json, model_from_json

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
MODELS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if MODELS_DIR not in sys.path:
    sys.path.insert(0, MODELS_DIR)

from base_model import BaseForecaster


class ProphetForecaster(BaseForecaster):
    """
    Univariate Prophet ensemble for multivariate telemetry forecasting.
    Trains one Facebook Prophet model per numeric feature column and packages
    them into a unified BaseForecaster interface.
    """
    def __init__(self, interval_width: float = 0.8):
        self.interval_width = interval_width
        self.models: Dict[str, Prophet] = {}
        self.feature_cols: List[str] = []

    def fit(self, train_df: pd.DataFrame, feature_cols: List[str], target_col: str = None, **kwargs) -> Dict[str, Any]:
        """
        Fits one Prophet model per feature in feature_cols.
        """
        ts_col = "timestamp" if "timestamp" in train_df.columns else ("ds" if "ds" in train_df.columns else train_df.columns[0])
        df_clean = train_df.copy()
        df_clean[ts_col] = pd.to_datetime(df_clean[ts_col])
        
        # Exclude one-hot cluster_ columns if needed
        self.feature_cols = [f for f in feature_cols if f in df_clean.columns and not f.startswith("cluster_")]
        metrics = {}

        for fcol in self.feature_cols:
            sub_df = df_clean[[ts_col, fcol]].rename(columns={ts_col: "ds", fcol: "y"})
            m = Prophet(
                daily_seasonality=True,
                weekly_seasonality=True,
                yearly_seasonality=False,
                interval_width=self.interval_width
            )
            m.fit(sub_df)
            self.models[fcol] = m

        return {"fitted_features": len(self.models)}

    def predict(self, context_df: pd.DataFrame, horizon: int = 60) -> pd.DataFrame:
        """
        Generates forecasts for all fitted features for the specified horizon (minutes).
        Returns a DataFrame with predicted columns and confidence bounds.
        """
        if not self.models:
            raise RuntimeError("ProphetForecaster has not been fitted or loaded yet.")

        ts_col = "timestamp" if "timestamp" in context_df.columns else ("ds" if "ds" in context_df.columns else context_df.columns[0])
        last_timestamp = pd.to_datetime(context_df[ts_col].iloc[-1])
        future_dates = pd.date_range(start=last_timestamp + pd.Timedelta(minutes=1), periods=horizon, freq="1min")
        future_df = pd.DataFrame({"ds": future_dates})

        predictions = {"ds": future_dates}
        for fcol, m in self.models.items():
            forecast = m.predict(future_df)
            predictions[fcol] = forecast["yhat"].values
            predictions[f"{fcol}_lower"] = forecast["yhat_lower"].values
            predictions[f"{fcol}_upper"] = forecast["yhat_upper"].values

        res_df = pd.DataFrame(predictions)
        return res_df

    def save(self, filepath: str) -> None:
        """
        Serializes all fitted Prophet models to disk (JSON file format).
        """
        if not self.models:
            raise RuntimeError("No trained Prophet models to save.")
        
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        serialized_data = {
            "feature_cols": self.feature_cols,
            "interval_width": self.interval_width,
            "models": {fcol: model_to_json(m) for fcol, m in self.models.items()}
        }
        with open(filepath, "w") as f:
            json.dump(serialized_data, f)
        print(f"[Prophet] Saved model checkpoint to {filepath}")

    def load(self, filepath: str) -> None:
        """
        Deserializes Prophet model checkpoint from JSON file on disk.
        """
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Prophet checkpoint not found at {filepath}")
        
        with open(filepath, "r") as f:
            data = json.load(f)
        
        self.feature_cols = data.get("feature_cols", [])
        self.interval_width = data.get("interval_width", 0.8)
        self.models = {fcol: model_from_json(json_str) for fcol, json_str in data["models"].items()}
        print(f"[Prophet] Loaded checkpoint with {len(self.models)} features from {filepath}")
