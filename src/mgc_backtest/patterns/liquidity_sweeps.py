"""Détection des liquidity sweeps HTF (prise de liquidité au-dessus/en
dessous des swing highs/lows), sans look-ahead.

Un sweep haussier (prise de liquidité "sell-side") se produit quand une
bougie mèche sous un swing low connu puis clôture au-dessus de ce niveau
(rejet). Symétriquement pour un sweep baissier sur un swing high.
"""

from __future__ import annotations

import pandas as pd

from mgc_backtest.patterns.swings import detect_swings


def detect_liquidity_sweeps(
    df: pd.DataFrame,
    swings: pd.DataFrame | None = None,
    left: int = 2,
    right: int = 2,
    lookback_swings: int = 20,
) -> pd.DataFrame:
    """Retourne un DataFrame des sweeps détectés avec colonnes :

    - ``time`` : timestamp de la bougie qui exécute le sweep
    - ``direction`` : "bullish" (sweep de sell-side liquidity) ou "bearish"
    - ``swept_level`` : prix du swing balayé
    - ``swept_swing_time`` : timestamp du pivot balayé
    """
    if swings is None:
        swings = detect_swings(df, left=left, right=right)

    swing_lows = swings[swings["type"] == "low"].sort_values("time", kind="stable")
    swing_highs = swings[swings["type"] == "high"].sort_values("time", kind="stable")

    used_lows: set = set()
    used_highs: set = set()
    records = []

    idx = df.index
    for i in range(len(df)):
        t = idx[i]
        bar_low = df["low"].iloc[i]
        bar_high = df["high"].iloc[i]
        bar_close = df["close"].iloc[i]

        avail_lows = swing_lows[
            (swing_lows["confirmed_at"] < t) & (~swing_lows["time"].isin(used_lows))
        ].tail(lookback_swings)
        for _, sw in avail_lows.iterrows():
            if bar_low < sw["price"] and bar_close > sw["price"]:
                records.append((t, "bullish", sw["price"], sw["time"]))
                used_lows.add(sw["time"])

        avail_highs = swing_highs[
            (swing_highs["confirmed_at"] < t) & (~swing_highs["time"].isin(used_highs))
        ].tail(lookback_swings)
        for _, sw in avail_highs.iterrows():
            if bar_high > sw["price"] and bar_close < sw["price"]:
                records.append((t, "bearish", sw["price"], sw["time"]))
                used_highs.add(sw["time"])

    out = pd.DataFrame(records, columns=["time", "direction", "swept_level", "swept_swing_time"])
    return out.sort_values("time", kind="stable").reset_index(drop=True)
