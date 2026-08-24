#!/usr/bin/env python3
"""Convertit un ou plusieurs fichiers klines Binance (CSV ou ZIP, tels que
téléchargés depuis https://data.binance.vision/) vers le format attendu par
le loader (``timestamp,open,high,low,close,volume``).

Format brut Binance (colonnes, avec ou sans ligne d'en-tête) :
open_time, open, high, low, close, volume, close_time, quote_volume,
count, taker_buy_volume, taker_buy_quote_volume, ignore

Accepte plusieurs fichiers (ex: plusieurs mois) : ils sont concaténés,
dédupliqués et triés chronologiquement.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def _epoch_to_utc(series: pd.Series) -> pd.Series:
    """Détecte l'unité (s/ms/us/ns) à partir de la magnitude du premier
    timestamp, pour rester correct même si Binance change de précision."""
    magnitude = int(series.iloc[0])
    if magnitude > 10**17:
        unit = "ns"
    elif magnitude > 10**14:
        unit = "us"
    elif magnitude > 10**11:
        unit = "ms"
    else:
        unit = "s"
    return pd.to_datetime(series.astype(np.int64), unit=unit, utc=True)


def _read_one(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path, header=None)
    # une ligne d'en-tête peut être présente sur les exports récents -> détectée
    # et supprimée si la première cellule de la première ligne n'est pas numérique
    first_cell = str(df.iloc[0, 0])
    if not first_cell.replace(".", "", 1).lstrip("-").isdigit():
        df = df.iloc[1:].reset_index(drop=True)
    df = df.iloc[:, :6].copy()
    df.columns = ["open_time", "open", "high", "low", "close", "volume"]
    for col in df.columns:
        df[col] = pd.to_numeric(df[col])
    return df


def convert_binance_klines(input_paths: list[str | Path], output_path: str | Path) -> pd.DataFrame:
    frames = [_read_one(p) for p in input_paths]
    raw = pd.concat(frames, ignore_index=True)

    out = pd.DataFrame(
        {
            "timestamp": _epoch_to_utc(raw["open_time"]),
            "open": raw["open"],
            "high": raw["high"],
            "low": raw["low"],
            "close": raw["close"],
            "volume": raw["volume"],
        }
    )
    out = out.drop_duplicates(subset="timestamp").sort_values("timestamp").reset_index(drop=True)

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convertit un ou plusieurs fichiers klines Binance (data.binance.vision) vers le format du loader"
    )
    parser.add_argument("inputs", nargs="+", help="Fichier(s) CSV ou ZIP klines Binance (un ou plusieurs mois)")
    parser.add_argument("--output", default="data/raw/BTCUSDT_5min_real.csv")
    args = parser.parse_args()

    out = convert_binance_klines(args.inputs, args.output)
    print(f"{len(out)} bougies converties -> {args.output}")
    print(f"Période couverte : {out['timestamp'].iloc[0]} -> {out['timestamp'].iloc[-1]}")


if __name__ == "__main__":
    main()
