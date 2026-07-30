"""Détection des swing highs / swing lows (pivots fractals).

Un swing high en position ``i`` est une bougie dont le high est strictement
supérieur aux ``left`` bougies précédentes et aux ``right`` bougies
suivantes (symétrique pour un swing low). Le pivot ne devient "connu" qu'une
fois les ``right`` bougies suivantes clôturées : c'est la date
``confirmed_at`` que les modules en aval (sweeps, order blocks) doivent
utiliser pour éviter tout look-ahead.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def detect_swings(df: pd.DataFrame, left: int = 2, right: int = 2) -> pd.DataFrame:
    """Retourne un DataFrame des pivots détectés, avec colonnes :

    - ``time`` : timestamp de la bougie pivot
    - ``price`` : prix du pivot (high ou low)
    - ``type`` : "high" ou "low"
    - ``confirmed_at`` : timestamp à partir duquel le pivot est connu
    """
    if len(df) < left + right + 1:
        return pd.DataFrame(columns=["time", "price", "type", "confirmed_at"])

    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    n = len(df)
    idx = df.index

    records = []
    for i in range(left, n - right):
        h = highs[i]
        if h > highs[i - left:i].max() and h > highs[i + 1:i + right + 1].max():
            records.append((idx[i], h, "high", idx[i + right]))
        l = lows[i]
        if l < lows[i - left:i].min() and l < lows[i + 1:i + right + 1].min():
            records.append((idx[i], l, "low", idx[i + right]))

    out = pd.DataFrame(records, columns=["time", "price", "type", "confirmed_at"])
    return out.sort_values("time").reset_index(drop=True)


def swings_known_by(swings: pd.DataFrame, as_of, swing_type: str | None = None) -> pd.DataFrame:
    """Filtre les swings dont ``confirmed_at <= as_of`` (donc exploitables
    sans look-ahead à l'instant ``as_of``)."""
    mask = swings["confirmed_at"] <= as_of
    if swing_type is not None:
        mask &= swings["type"] == swing_type
    return swings[mask]
