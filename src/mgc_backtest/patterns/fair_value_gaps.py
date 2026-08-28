"""Détection des Fair Value Gaps (FVG) — imbalance sur 3 bougies.

Un FVG haussier apparaît quand le low de la bougie i+1 est strictement
au-dessus du high de la bougie i-1 (la bougie i, impulsive, a "sauté" cette
zone de prix). Symétrique pour un FVG baissier. Le gap n'est confirmé qu'à
la clôture de la 3e bougie (``available_at``), ce qui évite tout look-ahead.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from mgc_backtest.utils.indicators import atr


def detect_fair_value_gaps(
    df: pd.DataFrame,
    min_gap_atr_mult: float = 0.0,
    atr_period: int = 14,
    max_age_bars: int = 30,
) -> pd.DataFrame:
    """Retourne un DataFrame des FVG détectés avec colonnes :

    - ``time`` : timestamp de la bougie centrale (impulsive) du FVG
    - ``direction`` : "bullish" ou "bearish"
    - ``top`` / ``bottom`` : bornes de la zone d'imbalance
    - ``available_at`` : timestamp de clôture de la 3e bougie (confirmation)
    - ``mitigated_at`` : timestamp de premier retour dans la zone (NaT si jamais)
    - ``expires_at`` : timestamp au-delà duquel le FVG est considéré caduc
    """
    n = len(df)
    if n < 3:
        return pd.DataFrame(
            columns=["time", "direction", "top", "bottom", "available_at", "mitigated_at", "expires_at"]
        )

    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    idx = df.index
    atr_series = atr(df, period=atr_period) if min_gap_atr_mult > 0 else None

    records = []
    for i in range(1, n - 1):
        bullish_gap = lows[i + 1] > highs[i - 1]
        bearish_gap = highs[i + 1] < lows[i - 1]
        if not (bullish_gap or bearish_gap):
            continue

        if bullish_gap:
            bottom, top, direction = highs[i - 1], lows[i + 1], "bullish"
        else:
            bottom, top, direction = highs[i + 1], lows[i - 1], "bearish"

        if min_gap_atr_mult > 0:
            a = atr_series.iloc[i]
            if pd.isna(a) or a == 0 or (top - bottom) < min_gap_atr_mult * a:
                continue

        available_at = idx[i + 1]
        mitigated_at = pd.NaT
        for k in range(i + 2, min(n, i + 2 + max_age_bars)):
            if lows[k] <= top and highs[k] >= bottom:
                mitigated_at = idx[k]
                break

        expires_at = idx[min(n - 1, i + 1 + max_age_bars)]

        records.append((idx[i], direction, top, bottom, available_at, mitigated_at, expires_at))

    out = pd.DataFrame(
        records,
        columns=["time", "direction", "top", "bottom", "available_at", "mitigated_at", "expires_at"],
    )
    for col in ("time", "available_at", "mitigated_at", "expires_at"):
        out[col] = pd.to_datetime(out[col], utc=True)
    return out.sort_values("time", kind="stable").reset_index(drop=True)


def active_fvgs(fvgs: pd.DataFrame, as_of, direction: str | None = None) -> pd.DataFrame:
    """FVG exploitables à l'instant ``as_of``.

    Implémenté avec des tableaux numpy plutôt que des comparaisons pandas
    Series : cette fonction est appelée une fois par bougie LTF pendant le
    backtest (potentiellement des dizaines de milliers de fois), et le
    surcoût fixe par appel de pandas devient alors le goulot d'étranglement
    dominant malgré la petite taille des données."""
    if fvgs.empty:
        return fvgs
    as_of_ts = pd.Timestamp(as_of)
    if as_of_ts.tzinfo is not None:
        as_of_ts = as_of_ts.tz_convert("UTC").tz_localize(None)
    as_of_np = np.datetime64(as_of_ts)
    available_at = fvgs["available_at"].to_numpy(dtype="datetime64[ns]")
    expires_at = fvgs["expires_at"].to_numpy(dtype="datetime64[ns]")
    mitigated_at = fvgs["mitigated_at"].to_numpy(dtype="datetime64[ns]")

    mask = (available_at <= as_of_np) & (expires_at >= as_of_np)
    mask &= pd.isna(mitigated_at) | (mitigated_at > as_of_np)
    if direction is not None:
        mask &= fvgs["direction"].to_numpy() == direction
    return fvgs.iloc[mask]
