"""Générateurs de signaux pour des familles de stratégies classiques
(trend-following, breakout, mean-reversion), en alternative au SMC/ICT.

Chaque fonction retourne une ``pd.Series`` alignée sur l'index de ``df``,
valant +1 (signal long), -1 (signal short) ou 0 (rien) au moment précis où
le setup se déclenche (pas d'état "maintenu" : un seul événement par
setup, jamais deux signaux consécutifs identiques tant que les conditions
restent vraies en continu)."""

from __future__ import annotations

import pandas as pd

from mgc_backtest.classic.indicators import ema, rsi
from mgc_backtest.utils.indicators import atr


def _edge_trigger(cond: pd.Series) -> pd.Series:
    """Ne garde que les transitions False->True (évite les signaux répétés
    tant qu'une condition reste vraie plusieurs bougies de suite)."""
    return cond & ~cond.shift(1, fill_value=False)


def ema_trend_pullback(df: pd.DataFrame, fast: int = 20, trend: int = 200) -> pd.Series:
    """Tendance (prix vs EMA longue) + retour toucher/traverser l'EMA rapide
    dans le sens de la tendance = signal de continuation."""
    close = df["close"]
    ema_fast = ema(close, fast)
    ema_trend = ema(close, trend)

    uptrend = close > ema_trend
    downtrend = close < ema_trend

    cross_up = (close > ema_fast) & (close.shift(1) <= ema_fast.shift(1))
    cross_down = (close < ema_fast) & (close.shift(1) >= ema_fast.shift(1))

    long_sig = _edge_trigger(cross_up & uptrend)
    short_sig = _edge_trigger(cross_down & downtrend)

    out = pd.Series(0, index=df.index, dtype=int)
    out[long_sig] = 1
    out[short_sig] = -1
    return out


def donchian_breakout(df: pd.DataFrame, n: int = 20) -> pd.Series:
    """Cassure d'un plus haut/plus bas sur N bougies (style turtle)."""
    upper = df["high"].rolling(n).max().shift(1)
    lower = df["low"].rolling(n).min().shift(1)
    close = df["close"]

    long_sig = _edge_trigger(close > upper)
    short_sig = _edge_trigger(close < lower)

    out = pd.Series(0, index=df.index, dtype=int)
    out[long_sig] = 1
    out[short_sig] = -1
    return out


def rsi2_mean_reversion(
    df: pd.DataFrame, rsi_period: int = 2, lower: float = 10.0, upper: float = 90.0, trend: int = 200,
) -> pd.Series:
    """RSI(2) extrême (Larry Connors) filtré par la tendance de fond :
    n'achète le creux qu'en tendance haussière, ne vend le pic qu'en
    tendance baissière."""
    close = df["close"]
    ema_trend = ema(close, trend)
    r = rsi(close, rsi_period)

    uptrend = close > ema_trend
    downtrend = close < ema_trend

    long_sig = _edge_trigger((r < lower) & uptrend)
    short_sig = _edge_trigger((r > upper) & downtrend)

    out = pd.Series(0, index=df.index, dtype=int)
    out[long_sig] = 1
    out[short_sig] = -1
    return out


STRATEGIES = {
    "ema_trend_pullback": ema_trend_pullback,
    "donchian_breakout": donchian_breakout,
    "rsi2_mean_reversion": rsi2_mean_reversion,
}


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    return atr(df, period)
