"""Fixed Range Volume Profile et Point of Control (POC).

Le POC est recalculé en glissant sur une fenêtre fixe de ``window_bars``
bougies se terminant à la bougie courante (fenêtre "fixed range" glissante),
ce qui garantit qu'à l'instant t seules les bougies <= t sont utilisées
(pas de look-ahead).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _poc_for_window(highs: np.ndarray, lows: np.ndarray, volumes: np.ndarray, n_bins: int) -> float:
    price_min = lows.min()
    price_max = highs.max()
    if price_max <= price_min:
        return float((price_min + price_max) / 2)

    bin_edges = np.linspace(price_min, price_max, n_bins + 1)
    bin_vol = np.zeros(n_bins)

    for h, l, v in zip(highs, lows, volumes):
        bar_range = h - l
        if bar_range <= 0:
            b = int(np.clip(np.searchsorted(bin_edges, l, side="right") - 1, 0, n_bins - 1))
            bin_vol[b] += v
            continue
        b_start = int(np.clip(np.searchsorted(bin_edges, l, side="right") - 1, 0, n_bins - 1))
        b_end = int(np.clip(np.searchsorted(bin_edges, h, side="left"), 0, n_bins - 1))
        for b in range(b_start, b_end + 1):
            bin_lo, bin_hi = bin_edges[b], bin_edges[b + 1]
            overlap = min(h, bin_hi) - max(l, bin_lo)
            if overlap > 0:
                bin_vol[b] += v * (overlap / bar_range)

    poc_bin = int(np.argmax(bin_vol))
    return float((bin_edges[poc_bin] + bin_edges[poc_bin + 1]) / 2)


def rolling_poc(df: pd.DataFrame, window_bars: int = 48, n_bins: int = 30) -> pd.Series:
    """POC glissant (Fixed Range Volume Profile), indexé comme ``df``.
    NaN tant que la fenêtre n'est pas remplie."""
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    volumes = df["volume"].to_numpy()
    n = len(df)

    poc = np.full(n, np.nan)
    for i in range(window_bars - 1, n):
        start = i - window_bars + 1
        poc[i] = _poc_for_window(highs[start:i + 1], lows[start:i + 1], volumes[start:i + 1], n_bins)

    return pd.Series(poc, index=df.index, name="poc")


def poc_as_of(poc_series: pd.Series, as_of) -> float | None:
    """Dernière valeur de POC connue à l'instant ``as_of`` (pas de look-ahead
    car ``poc_series`` est déjà calculée en glissant causal)."""
    valid = poc_series[poc_series.index <= as_of].dropna()
    if valid.empty:
        return None
    return float(valid.iloc[-1])
