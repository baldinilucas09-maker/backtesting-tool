#!/usr/bin/env python3
"""Génère un jeu de données OHLCV 5min synthétique réaliste pour le MGC,
utile pour développer/tester le pipeline sans dépendre d'une source de
données externe. Remplacez ensuite ``data/raw/MGC_5min_synthetic.csv`` (ou
le chemin configuré dans ``config/strategy.yaml``) par vos propres données
réelles : le loader attend les colonnes
``timestamp,open,high,low,close,volume``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def generate_synthetic_ohlcv(
    start: str = "2025-01-01",
    n_days: int = 60,
    bar_minutes: int = 5,
    start_price: float = 2400.0,
    seed: int = 42,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    bars_per_day = int(24 * 60 / bar_minutes)

    timestamps = []
    day = pd.Timestamp(start, tz="UTC")
    days_added = 0
    while days_added < n_days:
        if day.weekday() < 5:  # lun-ven, marché fermé le week-end
            timestamps.extend(pd.date_range(day, periods=bars_per_day, freq=f"{bar_minutes}min", tz="UTC"))
            days_added += 1
        day += pd.Timedelta(days=1)
    idx = pd.DatetimeIndex(timestamps)
    n = len(idx)

    base_vol = 0.0006
    returns = rng.normal(0, base_vol, n)
    jump_mask = rng.random(n) < 0.01  # ~1% de bougies avec un mouvement impulsif
    returns += rng.normal(0, 0.004, n) * jump_mask

    ny_session = (idx.hour >= 12) & (idx.hour < 20)  # volatilité plus forte en session NY
    returns = np.where(ny_session, returns * 1.6, returns * 0.7)

    close = np.exp(np.log(start_price) + np.cumsum(returns))
    open_ = np.empty(n)
    open_[0] = start_price
    open_[1:] = close[:-1]

    intrabar_vol = base_vol * 0.6
    high = np.maximum(open_, close) + np.abs(rng.normal(0, intrabar_vol, n)) * close
    low = np.minimum(open_, close) - np.abs(rng.normal(0, intrabar_vol, n)) * close

    base_volume = rng.lognormal(mean=4.0, sigma=0.6, size=n)
    volume_spike = 1 + 4 * jump_mask.astype(float)
    volume = np.maximum((base_volume * volume_spike * np.where(ny_session, 1.5, 0.8)).round(), 1).astype(int)

    return pd.DataFrame(
        {
            "timestamp": idx,
            "open": np.round(open_, 2),
            "high": np.round(high, 2),
            "low": np.round(low, 2),
            "close": np.round(close, 2),
            "volume": volume,
        }
    )


def main() -> None:
    df = generate_synthetic_ohlcv()
    out_path = Path(__file__).resolve().parent.parent / "data" / "raw" / "MGC_5min_synthetic.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    print(f"{len(df)} bougies synthétiques écrites dans {out_path}")


if __name__ == "__main__":
    main()
