"""Indicateurs additionnels pour les stratégies classiques (non SMC/ICT)."""

from __future__ import annotations

import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def rsi(series: pd.Series, period: int = 2) -> pd.Series:
    """RSI de Wilder, sans look-ahead."""
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, float("nan"))
    out = 100 - (100 / (1 + rs))
    return out.fillna(100.0).where(avg_loss != 0, 100.0)
