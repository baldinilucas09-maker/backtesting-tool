#!/usr/bin/env python3
"""Point d'entrée CLI : charge les données, lance le backtest, génère le rapport."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mgc_backtest.backtest.engine import run_backtest  # noqa: E402
from mgc_backtest.data.loader import load_ohlcv_csv  # noqa: E402
from mgc_backtest.data.resampler import resample_ohlcv  # noqa: E402
from mgc_backtest.reporting.report import generate_report  # noqa: E402
from mgc_backtest.strategy.rules import StrategyConfig  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest SMC/ICT sur Micro Gold Futures (MGC)")
    parser.add_argument("--config", default="config/strategy.yaml", help="Chemin du fichier de config YAML")
    parser.add_argument("--output", default="output", help="Dossier de sortie du rapport")
    args = parser.parse_args()

    config = StrategyConfig.from_yaml(args.config)

    df_ltf = load_ohlcv_csv(config.data.raw_file, timezone=config.data.timezone)
    df_htf = resample_ohlcv(df_ltf, config.timeframes.htf)

    print(f"Données chargées : {len(df_ltf)} bougies {config.timeframes.ltf} / {len(df_htf)} bougies {config.timeframes.htf}")

    result = run_backtest(df_ltf, df_htf, config)
    print(f"{len(result.signals)} signaux détectés, {len(result.trades)} trades exécutés\n")

    generate_report(result, config, args.output)


if __name__ == "__main__":
    main()
