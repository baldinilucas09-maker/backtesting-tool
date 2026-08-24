#!/usr/bin/env python3
"""Recherche de paramètres : balaie une grille de seuils de détection,
présélectionne les configurations prometteuses sur un backtest période
complète (rapide), puis valide seulement les meilleures en walk-forward
(rigoureux mais coûteux) pour ne retenir que celles qui tiennent réellement
hors échantillon.

Un balayage walk-forward complet sur toute la grille serait bien trop
coûteux (chaque walk-forward prend déjà ~20-25 min sur ~19 mois de
données) : la présélection rapide sert à ne pas gaspiller ce temps sur des
combinaisons clairement mauvaises.
"""

from __future__ import annotations

import argparse
import copy
import itertools
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mgc_backtest.backtest.engine import run_backtest  # noqa: E402
from mgc_backtest.data.loader import load_ohlcv_csv  # noqa: E402
from mgc_backtest.data.resampler import resample_ohlcv  # noqa: E402
from mgc_backtest.reporting.metrics import compute_metrics  # noqa: E402
from mgc_backtest.strategy.rules import StrategyConfig  # noqa: E402
from mgc_backtest.validation.walk_forward import walk_forward_validate  # noqa: E402

IMPULSE_MULTS = [1.0, 1.5, 2.0]
PROXIMITY_MULTS = [0.3, 0.5, 0.75]
SWEEP_WINDOWS = [12]  # fixé à la valeur par défaut (variation testée séparément si besoin)
SWING_LENGTHS = [(2, 2), (4, 4)]  # (2,2)=sensible, (4,4)=niveaux plus "importants"/significatifs
TP_MODES = ["scaled_123r", "single_3r"]  # scale-out 1/2/3R vs objectif unique RR=3


def make_variant(base_config: StrategyConfig, impulse_mult, proximity_mult, sweep_window, swing_len, tp_mode):
    cfg = copy.deepcopy(base_config)
    cfg.order_blocks.impulse_atr_mult = impulse_mult
    cfg.confluence.proximity_atr_mult = proximity_mult
    cfg.liquidity_sweeps.max_bars_since_sweep = sweep_window
    cfg.swings.left_bars, cfg.swings.right_bars = swing_len
    if tp_mode == "single_3r":
        cfg.risk.r_multiples = [3]
        cfg.risk.scale_out_fractions = [1.0]
    else:
        cfg.risk.r_multiples = [1, 2, 3]
        cfg.risk.scale_out_fractions = [0.34, 0.33, 0.33]
    return cfg


def label(im, pm, sw, sl, tp) -> str:
    return f"impulse={im} prox={pm} sweep_win={sw} swing={sl} tp={tp}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Recherche de paramètres avec présélection + validation walk-forward")
    parser.add_argument("--config", default="config/strategy_btc_perp_relaxed_real.yaml")
    parser.add_argument("--min-trades", type=int, default=30, help="Trades minimum (plein échantillon) pour être candidat")
    parser.add_argument("--min-pf", type=float, default=1.3, help="Profit factor net minimum (plein échantillon) pour être candidat")
    parser.add_argument("--top-n", type=int, default=5, help="Nombre de candidats validés en walk-forward")
    parser.add_argument("--train-days", type=int, default=20)
    parser.add_argument("--test-days", type=int, default=10)
    parser.add_argument(
        "--screen-last-days", type=int, default=0,
        help="Limiter l'étape de présélection (rapide) aux N derniers jours de données, pour rester dans un temps de calcul raisonnable. 0 = toutes les données. La validation walk-forward finale utilise toujours l'historique complet.",
    )
    args = parser.parse_args()

    base_config = StrategyConfig.from_yaml(args.config)
    df_ltf_full = load_ohlcv_csv(base_config.data.raw_file, timezone=base_config.data.timezone)
    print(f"Données complètes : {len(df_ltf_full)} bougies {base_config.timeframes.ltf} "
          f"({df_ltf_full.index[0]} -> {df_ltf_full.index[-1]})\n")

    if args.screen_last_days > 0:
        cutoff = df_ltf_full.index[-1] - pd.Timedelta(days=args.screen_last_days)
        df_ltf_screen = df_ltf_full[df_ltf_full.index >= cutoff]
    else:
        df_ltf_screen = df_ltf_full
    df_htf_screen = resample_ohlcv(df_ltf_screen, base_config.timeframes.htf)
    print(f"Données de présélection : {len(df_ltf_screen)} bougies "
          f"({df_ltf_screen.index[0]} -> {df_ltf_screen.index[-1]})\n")

    combos = list(itertools.product(IMPULSE_MULTS, PROXIMITY_MULTS, SWEEP_WINDOWS, SWING_LENGTHS, TP_MODES))
    print(f"=== Étape 1/2 : présélection ({len(combos)} combinaisons) ===\n")

    results = []
    for i, (im, pm, sw, sl, tp) in enumerate(combos):
        cfg = make_variant(base_config, im, pm, sw, sl, tp)
        result = run_backtest(df_ltf_screen, df_htf_screen, cfg)
        metrics = compute_metrics(result.trades, result.equity_curve, cfg.risk)
        row = {
            "impulse_mult": im, "proximity_mult": pm, "sweep_window": sw, "swing_len": sl, "tp_mode": tp,
            "num_trades": metrics["num_trades"], "win_rate": metrics["win_rate_pct"],
            "profit_factor": metrics["profit_factor"], "net_pnl": metrics["net_pnl"],
            "max_dd_pct": metrics["max_drawdown_pct"],
        }
        results.append(row)
        print(f"[{i + 1}/{len(combos)}] {label(im, pm, sw, sl, tp)} -> "
              f"n={row['num_trades']:3d} wr={row['win_rate']:5.1f}% pf={row['profit_factor']:5.2f} "
              f"pnl={row['net_pnl']:9.0f}$ dd={row['max_dd_pct']:6.2f}%")

    candidates = [r for r in results if r["num_trades"] >= args.min_trades and r["profit_factor"] > args.min_pf]
    candidates.sort(key=lambda r: r["profit_factor"], reverse=True)
    top = candidates[: args.top_n]

    print(f"\n{len(candidates)} candidat(s) passent le filtre (>= {args.min_trades} trades, PF > {args.min_pf}).")

    if not top:
        print("Aucun candidat à valider en walk-forward : aucune combinaison ne dépasse le filtre sur période complète.")
        print("=> Sur cette grille et cette donnée, aucune configuration ne montre même une performance brute suffisante pour justifier une validation plus poussée.")
        return

    print(f"\n=== Étape 2/2 : validation walk-forward des {len(top)} meilleurs candidats ===")
    print("(chaque walk-forward prend plusieurs minutes)\n")

    final = []
    for i, cand in enumerate(top):
        cfg = make_variant(base_config, cand["impulse_mult"], cand["proximity_mult"], cand["sweep_window"], cand["swing_len"], cand["tp_mode"])
        report = walk_forward_validate(df_ltf_full, cfg, train_days=args.train_days, test_days=args.test_days, min_score_candidates=(2, 3, 4))
        pm_ = report.pooled_test_metrics
        n_profitable = sum(1 for f in report.folds if f.test_metrics.get("net_pnl", 0) > 0)
        n_with_trades = sum(1 for f in report.folds if f.test_trades)
        print(f"\n--- Candidat {i + 1}/{len(top)} : {label(cand['impulse_mult'], cand['proximity_mult'], cand['sweep_window'], cand['swing_len'], cand['tp_mode'])} ---")
        print(f"  Plein échantillon : n={cand['num_trades']} wr={cand['win_rate']:.1f}% pf={cand['profit_factor']:.2f} pnl={cand['net_pnl']:.0f}$")
        print(f"  Walk-forward OOS  : n={pm_['num_trades']} wr={pm_['win_rate_pct']:.1f}% pf={pm_['profit_factor']:.2f} "
              f"pnl={pm_['net_pnl']:.0f}$ dd={pm_['max_drawdown_pct']:.2f}% ({n_profitable}/{n_with_trades} fenêtres profitables)")
        final.append({"candidate": cand, "oos_metrics": pm_})

    final.sort(key=lambda r: r["oos_metrics"]["profit_factor"], reverse=True)
    print("\n=== Classement final par profit factor out-of-sample ===")
    for r in final:
        c = r["candidate"]
        m = r["oos_metrics"]
        verdict = "EDGE PLAUSIBLE" if m["profit_factor"] > 1.2 and m["num_trades"] >= 20 else "PAS D'EDGE DÉMONTRÉ"
        print(f"  [{verdict}] {label(c['impulse_mult'], c['proximity_mult'], c['sweep_window'], c['swing_len'], c['tp_mode'])} "
              f"-> PF OOS={m['profit_factor']:.2f}, n OOS={m['num_trades']}, pnl OOS={m['net_pnl']:.0f}$")


if __name__ == "__main__":
    main()
