"""VWAP (ancré sur la session) et AVWAP (ancré sur un point arbitraire :
sweep, événement...).

Tous les calculs sont des sommes cumulées causales (aucune information
future n'est utilisée à l'instant t).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _typical_price(df: pd.DataFrame) -> pd.Series:
    return (df["high"] + df["low"] + df["close"]) / 3.0


def session_vwap(df: pd.DataFrame, session_start_utc: str = "00:00") -> pd.Series:
    """VWAP réinitialisé à chaque début de session (par défaut minuit UTC)."""
    hh, mm = (int(x) for x in session_start_utc.split(":"))
    offset = pd.Timedelta(hours=hh, minutes=mm)
    session_id = (df.index - offset).floor("D")

    pv = _typical_price(df) * df["volume"]
    cum_pv = pv.groupby(session_id).cumsum()
    cum_vol = df["volume"].groupby(session_id).cumsum()
    return (cum_pv / cum_vol).rename("vwap")


def anchored_vwap(df: pd.DataFrame, anchor_time) -> pd.Series:
    """AVWAP ancré à ``anchor_time`` : NaN avant l'ancre, cumulatif après."""
    mask = df.index >= anchor_time
    pv = (_typical_price(df) * df["volume"]).where(mask, 0.0)
    vol = df["volume"].where(mask, 0.0)
    avwap = (pv.cumsum() / vol.cumsum()).where(mask)
    return avwap.rename("avwap")


def multi_anchor_vwap(df: pd.DataFrame, anchor_times: list) -> pd.Series:
    """AVWAP ré-ancré successivement à chaque timestamp de ``anchor_times``
    (ex: chaque liquidity sweep). Pour une bougie donnée, le calcul utilise
    l'ancre la plus récente déjà passée. NaN avant la première ancre."""
    if not anchor_times:
        return pd.Series(np.nan, index=df.index, name="avwap")

    anchor_arr = np.array(sorted(pd.Timestamp(a) for a in anchor_times))
    idx_values = df.index.values
    group_id = np.searchsorted(anchor_arr, idx_values, side="right") - 1

    pv = _typical_price(df) * df["volume"]
    tmp = pd.DataFrame({"group": group_id, "pv": pv, "vol": df["volume"]}, index=df.index)
    cum_pv = tmp.groupby("group")["pv"].cumsum()
    cum_vol = tmp.groupby("group")["vol"].cumsum()
    avwap = cum_pv / cum_vol
    avwap[group_id < 0] = np.nan
    return avwap.rename("avwap")
