from abc import ABC, abstractmethod
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Tuple

class BaseForecaster(ABC):
    """
    Abstract Base Class for all HPA++ time-series forecasting models.
    All models (Prophet, PatchTST, custom models) should implement this interface.
    """
    
    @abstractmethod
    def fit(self, train_df: pd.DataFrame, feature_cols: List[str], target_col: str, **kwargs) -> Dict[str, Any]:
        """
        Fits the model on the training dataframe.
        
        Args:
            train_df: Dataframe with 'ds', 'unique_id', and feature/target columns.
            feature_cols: List of input feature column names.
            target_col: Name of column to forecast (e.g. 'requests_per_second' or 'cpu_utilization_pct').
            
        Returns:
            Dictionary of training metrics (loss, duration, etc.)
        """
        pass
        
    @abstractmethod
    def predict(self, context_df: pd.DataFrame, horizon: int) -> pd.DataFrame:
        """
        Generates forecasts for the specified horizon steps into the future.
        
        Args:
            context_df: Historical context dataframe (containing recent window).
            horizon: Number of future timesteps to forecast.
            
        Returns:
            Dataframe containing 'unique_id', 'ds', and predicted target values.
        """
        pass

    @abstractmethod
    def save(self, filepath: str) -> None:
        """Saves model weights/artifacts to disk."""
        pass

    @abstractmethod
    def load(self, filepath: str) -> None:
        """Loads model weights/artifacts from disk."""
        pass
