"""
Data loader utility: แปลง Parquet จาก mft_engine → Nautilus Bar format
"""

from pathlib import Path
import pandas as pd
import numpy as np


def load_parquet_as_bars_df(parquet_path: str | Path) -> pd.DataFrame:
    """
    โหลด parquet และ normalize column names ให้พร้อมสำหรับ Nautilus

    Nautilus ต้องการ columns:
        timestamp (index, UTC, nanoseconds int64)
        open, high, low, close  (float)
        volume                  (float)
    """
    df = pd.read_parquet(parquet_path)
    print(f"[loader] Raw columns: {list(df.columns)}")
    print(f"[loader] Shape: {df.shape}")
    print(f"[loader] dtypes:\n{df.dtypes}")

    # Normalize column names (lowercase)
    df.columns = [c.lower() for c in df.columns]

    # ถ้า timestamp ยังไม่เป็น index ให้ set
    if "timestamp" in df.columns and df.index.name != "timestamp":
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.set_index("timestamp")
    elif not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index, utc=True)

    df = df.sort_index()

    # ตรวจสอบ required columns
    required = ["open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"Missing columns: {missing}\n"
            f"Available: {list(df.columns)}\n"
            "กรุณาปรับ column names ใน parquet ให้ตรง"
        )

    df[required] = df[required].astype(float)
    print(f"[loader] Loaded {len(df)} bars from {df.index[0]} to {df.index[-1]}")
    return df[required]
