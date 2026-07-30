import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))


def make_ohlcv(rows, start="2025-01-01", freq="1h") -> pd.DataFrame:
    """Construit un DataFrame OHLCV à partir d'une liste de tuples
    (open, high, low, close, volume)."""
    idx = pd.date_range(start, periods=len(rows), freq=freq, tz="UTC")
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"], index=idx)
    return df.astype(float)
