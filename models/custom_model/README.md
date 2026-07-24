# Custom Time Series Model (Under Construction)

This directory is reserved for your custom time-series forecasting architecture.

## Files
* **`model.py`**: Architecture definition (`CustomTimeStepModel`) and forecaster wrapper (`CustomForecaster`) implementing `BaseForecaster`.
* **`train_custom.py`**: Training & evaluation entry point.

## Usage
```bash
python models/custom_model/train_custom.py --csv data/synthetic_hpa_traffic_all_clusters_365d.csv
```
