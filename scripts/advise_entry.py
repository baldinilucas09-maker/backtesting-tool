#!/usr/bin/env python3
"""Analyse la dernière bougie disponible et affiche une recommandation
d'entrée (setup détecté ou non) basée sur les mêmes règles que le backtest.

Écrit aussi un JSON (``output/latest_advice.json`` par défaut) pour brancher
facilement le résultat sur un outil externe (alerte Discord/Telegram,
webhook, script de trading, etc.).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mgc_backtest.advisor import evaluate_entry_advice  # noqa: E402
from mgc_backtest.data.loader import load_ohlcv_csv  # noqa: E402
from mgc_backtest.data.resampler import resample_ohlcv  # noqa: E402
from mgc_backtest.strategy.rules import StrategyConfig  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Conseil d'entrée en position sur MGC (SMC/ICT)")
    parser.add_argument("--config", default="config/strategy.yaml", help="Chemin du fichier de config YAML")
    parser.add_argument("--data", default=None, help="Chemin CSV OHLCV à analyser (défaut : celui de la config)")
    parser.add_argument("--capital", type=float, default=None, help="Capital courant pour le sizing (défaut : config)")
    parser.add_argument("--json-out", default="output/latest_advice.json", help="Chemin d'export JSON")
    args = parser.parse_args()

    config = StrategyConfig.from_yaml(args.config)
    data_path = args.data or config.data.raw_file

    df_ltf = load_ohlcv_csv(data_path, timezone=config.data.timezone)
    df_htf = resample_ohlcv(df_ltf, config.timeframes.htf)

    advice = evaluate_entry_advice(df_ltf, df_htf, config, capital=args.capital)

    print(advice.message)

    out_path = Path(args.json_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(advice.to_dict(), indent=2, ensure_ascii=False))
    print(f"\nDétail JSON écrit dans : {out_path}")


if __name__ == "__main__":
    main()
