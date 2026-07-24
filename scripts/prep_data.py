#!/usr/bin/env python3
import os
import shutil
import pandas as pd
import numpy as np

# Determine project root cleanly
CURRENT_DIR = os.path.abspath(os.path.dirname(__file__))
if os.path.basename(CURRENT_DIR) == "scripts":
    BASE_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
else:
    BASE_DIR = CURRENT_DIR

SOURCE_DIR = os.path.join(BASE_DIR, "hf_upload", "data")
TARGET_DIR = os.path.join(BASE_DIR, "data")

COLUMNS_TO_DROP = [
    "requests_per_5min",
    "requests_per_1min",
    "gpus_in_use",
    "is_job_churn_spike",
    "is_flash_event_spike",
    "is_outage_event",
    "is_memleak_event",
    "memory_leak_active",
    "is_overload_event",
    "spike_multiplier"
]

RENAME_MAP = {
    "cluster_name": "unique_id",
    "timestamp": "ds",
    "active_pods": "pod_count"
}

ALL_CLUSTERS = [
    "ecommerce",
    "exam_system",
    "genai_inference",
    "streaming",
    "university_portal"
]

def prep_dataset_file(file_path: str):
    print(f"---> Processing: {file_path}")
    df = pd.read_csv(file_path)
    
    # 1. Drop specified columns if present
    drop_cols = [c for c in COLUMNS_TO_DROP if c in df.columns]
    if drop_cols:
        df = df.drop(columns=drop_cols)
        print(f"     Dropped columns: {drop_cols}")
        
    # 2. Rename columns
    rename_cols = {k: v for k, v in RENAME_MAP.items() if k in df.columns}
    if rename_cols:
        df = df.rename(columns=rename_cols)
        print(f"     Renamed columns: {rename_cols}")
        
    # 3. Generate One-Hot Encoding for unique_id
    if "unique_id" in df.columns:
        for c in ALL_CLUSTERS:
            ohe_col = f"cluster_{c}"
            df[ohe_col] = (df["unique_id"] == c).astype(int)
        print(f"     Added One-Hot Encoded cluster columns for {ALL_CLUSTERS}")
        
    # 4. Order columns cleanly
    first_cols = [c for c in ["unique_id", "ds"] if c in df.columns]
    ohe_cols = [f"cluster_{c}" for c in ALL_CLUSTERS if f"cluster_{c}" in df.columns]
    other_cols = [c for c in df.columns if c not in first_cols and c not in ohe_cols]
    df = df[first_cols + ohe_cols + other_cols]
    
    # Save back
    df.to_csv(file_path, index=False)
    size_mb = os.path.getsize(file_path) / (1024 * 1024)
    print(f"     [SAVED]: {file_path} ({size_mb:.2f} MB, {len(df):,} rows)")
    print(f"     Final Columns: {list(df.columns)}")

def main():
    os.makedirs(TARGET_DIR, exist_ok=True)
    
    print("=" * 80)
    print("STEP 1: COPYING DATASETS FROM hf_upload/data TO data/")
    print("=" * 80)
    print(f"Source: {SOURCE_DIR}")
    print(f"Target: {TARGET_DIR}")
    
    if not os.path.exists(SOURCE_DIR):
        raise FileNotFoundError(f"Source directory not found: {SOURCE_DIR}")
        
    source_files = [f for f in os.listdir(SOURCE_DIR) if f.endswith(".csv")]
    for f in source_files:
        src_path = os.path.join(SOURCE_DIR, f)
        dst_path = os.path.join(TARGET_DIR, f)
        shutil.copy2(src_path, dst_path)
        print(f"Copied: {f} -> data/{f}")
        
    print("\n" + "=" * 80)
    print("STEP 2: PREPROCESSING DATASETS IN data/ (OHE + RENAME + DROPS)")
    print("=" * 80)
    
    target_files = [f for f in os.listdir(TARGET_DIR) if f.endswith(".csv")]
    for f in target_files:
        fpath = os.path.join(TARGET_DIR, f)
        prep_dataset_file(fpath)
        
    print("\n[SUCCESS] Dataset preparation complete! All preprocessed datasets available in data/")

if __name__ == "__main__":
    main()
