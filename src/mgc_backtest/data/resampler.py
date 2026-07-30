"""Agrégation OHLCV d'un timeframe fin vers un timeframe plus large (HTF)."""

from __future__ import annotations

import pandas as pd

_AGG = {
    "open": "first",
    "high": "max",
    "low": "min",
    "close": "last",
    "volume": "sum",
}


def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Ré-échantillonne un DataFrame OHLCV (index datetime) vers ``rule``
    (ex: "4h", "1h"). Les bougies vides (pas de trade) sont supprimées.
    """
    out = df.resample(rule, label="left", closed="left").agg(_AGG)
    out = out.dropna(subset=["open", "high", "low", "close"])
    return out
