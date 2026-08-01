"""Détection des Order Blocks HTF.

Un order block est la dernière bougie de sens opposé avant un mouvement
impulsif (déplacement dont l'amplitude excède ``impulse_atr_mult`` x ATR).
L'OB n'est "disponible" pour la stratégie qu'à partir de la clôture de la
bougie impulsive (``available_at``) : c'est cette bougie qui confirme
rétroactivement que la précédente était un order block, donc l'utiliser
avant cette date serait du look-ahead.

Le statut de mitigation (``mitigated_at``) est calculé en balayant les
bougies suivantes jusqu'à un retour de prix dans la zone [bottom, top] : ce
n'est pas du look-ahead, la mitigation à l'instant t ne dépend que du passé
jusqu'à t.
"""

from __future__ import annotations

import pandas as pd

from mgc_backtest.utils.indicators import atr


def detect_order_blocks(
    df: pd.DataFrame,
    atr_period: int = 14,
    impulse_atr_mult: float = 1.5,
    max_age_bars: int = 40,
) -> pd.DataFrame:
    """Retourne un DataFrame des order blocks détectés avec colonnes :

    - ``time`` : timestamp de la bougie OB elle-même
    - ``direction`` : "bullish" ou "bearish"
    - ``top`` / ``bottom`` : bornes de la zone
    - ``available_at`` : timestamp à partir duquel l'OB est exploitable
    - ``mitigated_at`` : timestamp de première mitigation (NaT si jamais)
    - ``expires_at`` : timestamp au-delà duquel l'OB est considéré caduc
      s'il n'a pas été mitigé
    """
    if len(df) < atr_period + 2:
        return pd.DataFrame(
            columns=["time", "direction", "top", "bottom", "available_at", "mitigated_at", "expires_at"]
        )

    atr_series = atr(df, period=atr_period)
    opens = df["open"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()
    idx = df.index
    n = len(df)

    records = []
    for i in range(atr_period, n):
        a = atr_series.iloc[i]
        if pd.isna(a) or a == 0:
            continue
        move = closes[i] - opens[i]
        if abs(move) < impulse_atr_mult * a:
            continue

        impulsive_bullish = move > 0
        j = i - 1
        ob_idx = None
        while j >= 0:
            is_bearish = closes[j] < opens[j]
            is_bullish = closes[j] > opens[j]
            if impulsive_bullish and is_bearish:
                ob_idx = j
                break
            if (not impulsive_bullish) and is_bullish:
                ob_idx = j
                break
            j -= 1
        if ob_idx is None:
            continue

        top = highs[ob_idx]
        bottom = lows[ob_idx]
        direction = "bullish" if impulsive_bullish else "bearish"
        available_at = idx[i]

        mitigated_at = pd.NaT
        for k in range(i + 1, min(n, i + 1 + max_age_bars)):
            if lows[k] <= top and highs[k] >= bottom:
                mitigated_at = idx[k]
                break

        expires_at = idx[min(n - 1, i + max_age_bars)]

        records.append(
            (idx[ob_idx], direction, top, bottom, available_at, mitigated_at, expires_at)
        )

    out = pd.DataFrame(
        records,
        columns=["time", "direction", "top", "bottom", "available_at", "mitigated_at", "expires_at"],
    )
    for col in ("time", "available_at", "mitigated_at", "expires_at"):
        out[col] = pd.to_datetime(out[col], utc=True)
    return out.sort_values("time").reset_index(drop=True)


def active_order_blocks(order_blocks: pd.DataFrame, as_of, direction: str | None = None) -> pd.DataFrame:
    """OB exploitables à l'instant ``as_of`` : déjà disponibles, non mitigés
    (ou mitigés après ``as_of``), et non expirés."""
    mask = (order_blocks["available_at"] <= as_of) & (order_blocks["expires_at"] >= as_of)
    mask &= order_blocks["mitigated_at"].isna() | (order_blocks["mitigated_at"] > as_of)
    if direction is not None:
        mask &= order_blocks["direction"] == direction
    return order_blocks[mask]
