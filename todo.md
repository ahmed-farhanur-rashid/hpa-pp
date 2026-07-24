# Reproducing the Forecasting Pipeline

## 1. Dataset Preparation

Run the canonical dataset preparation script to copy raw data from `hf_upload/data/` to `data/`, apply One-Hot Encoding (`cluster_*`), preserve `concurrent_users`, and format the schema:

```bash
python scripts/prep_data.py
```

## 2. Model Training (All Architectures)

All model checkpoints are saved directly to `services/forecasting/checkpoints/`.

### A. Train Custom Model (PSA-Net) with Rich Console UI

```bash
# Standard 10-epoch training on 2.6M-row multi-cluster dataset
python services/forecasting/models/custom_model/train_custom.py \
  --epochs 10 \
  --batch_size 128 \
  --out services/forecasting/checkpoints/psanet_checkpoint.pt
```

### B. Train Baseline 1: PatchTST (Channel-Independent Transformer)

```bash
python services/forecasting/models/patchtst/train_patchtst.py \
  --epochs 10 \
  --batch_size 128 \
  --out services/forecasting/checkpoints/patchtst_checkpoint.pt
```

### C. Train Baseline 2: Prophet (Additive Baseline)

```bash
python services/forecasting/models/prophet/train_prophet.py \
  --horizon 15 \
  --n_eval_windows 20 \
  --out services/forecasting/checkpoints/prophet_checkpoint.json
```

## 3. Model Evaluation on Test Set

Evaluate any trained checkpoint or baseline model on the 30-day out-of-distribution test set (`data/synthetic_hpa_traffic_shifted_test.csv`) to compute MAE, RMSE, WAPE, and 80% Coverage Percentage:

```bash
# Evaluate Custom Model (PSA-Net) Checkpoint
python services/forecasting/models/evaluate.py \
  --checkpoint services/forecasting/checkpoints/psanet_checkpoint.pt \
  --test_csv data/synthetic_hpa_traffic_shifted_test.csv

# Evaluate PatchTST Baseline Checkpoint
python services/forecasting/models/evaluate.py \
  --checkpoint services/forecasting/checkpoints/patchtst_checkpoint.pt \
  --test_csv data/synthetic_hpa_traffic_shifted_test.csv

# Evaluate Prophet Baseline Checkpoint
python services/forecasting/models/evaluate.py \
  --checkpoint services/forecasting/checkpoints/prophet_checkpoint.json \
  --test_csv data/synthetic_hpa_traffic_shifted_test.csv
```