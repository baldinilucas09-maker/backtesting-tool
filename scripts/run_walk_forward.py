#!/usr/bin/env python3
"""Validation walk-forward : sélectionne le seuil de confluence sur des
fenêtres d'entraînement successives et mesure la performance out-of-sample
sur les fenêtres de test correspondantes (jamais vues pendant la sélection).

À utiliser avant de faire confiance à un backtest unique sur toute la
période : un seul backtest peut être un coup de chance ou un surapprentissage
des seuils. Le walk-forward donne une estimation plus honnête.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mgc_backtest.data.loader import load_ohlcv_csv  # noqa: E402
from mgc_backtest.strategy.rules import StrategyConfig  # noqa: E402
from mgc_backtest.validation.report import generate_walk_forward_report  # noqa: E402
from mgc_backtest.validation.walk_forward import walk_forward_validate  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Validation walk-forward de la stratégie SMC/ICT sur MGC")
    parser.add_argument("--config", default="config/strategy.yaml", help="Chemin du fichier de config YAML")
    parser.add_argument("--output", default="output/walk_forward", help="Dossier de sortie du rapport")
    parser.add_argument("--train-days", type=int, default=20, help="Taille de la fenêtre d'entraînement (jours)")
    parser.add_argument("--test-days", type=int, default=10, help="Taille de la fenêtre de test (jours)")
    parser.add_argument(
        "--min-score-candidates",
        default="2,3,4",
        help="Valeurs de confluence.min_score testées sur chaque fenêtre d'entraînement (séparées par des virgules)",
    )
    parser.add_argument(
        "--selection-metric",
        default="net_pnl",
        choices=["net_pnl", "profit_factor", "win_rate_pct"],
        help="Métrique utilisée pour choisir le meilleur min_score sur l'entraînement",
    )
    args = parser.parse_args()

    config = StrategyConfig.from_yaml(args.config)
    df_ltf = load_ohlcv_csv(config.data.raw_file, timezone=config.data.timezone)
    candidates = tuple(int(x) for x in args.min_score_candidates.split(","))

    print(
        f"Walk-forward : {len(df_ltf)} bougies {config.timeframes.ltf}, "
        f"fenêtres train={args.train_days}j / test={args.test_days}j, "
        f"candidats min_score={candidates}\n"
    )

    report = walk_forward_validate(
        df_ltf,
        config,
        train_days=args.train_days,
        test_days=args.test_days,
        min_score_candidates=candidates,
        selection_metric=args.selection_metric,
    )

    generate_walk_forward_report(report, args.output)


if __name__ == "__main__":
    main()
