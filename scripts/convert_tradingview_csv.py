#!/usr/bin/env python3
"""Convertit un export CSV TradingView ("Export chart data") vers le format
attendu par le loader (``timestamp,open,high,low,close,volume``).

TradingView exporte généralement une colonne ``time`` en timestamp Unix
(secondes) et des colonnes ``open,high,low,close,Volume`` (casse variable,
parfois des colonnes supplémentaires si des indicateurs sont affichés sur le
graphique — elles sont ignorées).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def _find_column(columns: list[str], *candidates: str) -> str:
    lower_map = {c.lower(): c for c in columns}
    for candidate in candidates:
        for lc, original in lower_map.items():
            if lc == candidate or lc.startswith(candidate):
                return original
    raise KeyError(f"Aucune colonne parmi {candidates} trouvée dans {columns}")


def convert_tradingview_csv(input_path: str | Path, output_path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(input_path)
    columns = list(df.columns)

    time_col = _find_column(columns, "time", "date")
    open_col = _find_column(columns, "open")
    high_col = _find_column(columns, "high")
    low_col = _find_column(columns, "low")
    close_col = _find_column(columns, "close")
    volume_col = _find_column(columns, "volume")

    time_series = df[time_col]
    if pd.api.types.is_numeric_dtype(time_series):
        timestamps = pd.to_datetime(time_series, unit="s", utc=True)
    else:
        timestamps = pd.to_datetime(time_series, utc=True)

    out = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": df[open_col].astype(float),
            "high": df[high_col].astype(float),
            "low": df[low_col].astype(float),
            "close": df[close_col].astype(float),
            "volume": df[volume_col].astype(float),
        }
    ).sort_values("timestamp").reset_index(drop=True)

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Convertit un export CSV TradingView vers le format du loader")
    parser.add_argument("input", help="Fichier CSV exporté depuis TradingView")
    parser.add_argument(
        "--output",
        default="data/raw/MGC_5min_real.csv",
        help="Chemin du CSV converti (défaut : data/raw/MGC_5min_real.csv)",
    )
    args = parser.parse_args()

    out = convert_tradingview_csv(args.input, args.output)
    print(f"{len(out)} bougies converties -> {args.output}")
    print(f"Période couverte : {out['timestamp'].iloc[0]} -> {out['timestamp'].iloc[-1]}")


if __name__ == "__main__":
    main()
