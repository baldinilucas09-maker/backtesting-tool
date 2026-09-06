#!/usr/bin/env python3
"""Scan systématique de stratégies classiques (trend-following, breakout,
mean-reversion) sur les données réelles BTC, plusieurs timeframes et
plusieurs multiplicateurs ATR de stop, avec un R:R fixe.

Étape 1 : backtest plein échantillon pour chaque combinaison (rapide) ->
filtre les candidats plausibles (profit factor net > seuil, assez de
trades). Étape 2 : ces candidats seulement sont ensuite validés en
walk-forward (script séparé) pour confirmer qu'ils tiennent hors
échantillon.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mgc_backtest.classic.backtest import backtest_classic, compute_classic_metrics  # noqa: E402
from mgc_backtest.classic.signals import STRATEGIES, compute_atr  # noqa: E402
from mgc_backtest.data.loader import load_ohlcv_csv  # noqa: E402
from mgc_backtest.data.resampler import resample_ohlcv  # noqa: E402

TIMEFRAMES = ["15min", "1h", "4h"]
ATR_MULTS = [1.0, 1.5, 2.5, 4.0]
RR = 3.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/raw/BTCUSDT_5min_real.csv")
    parser.add_argument("--min-trades", type=int, default=30)
    parser.add_argument("--min-pf", type=float, default=1.2)
    args = parser.parse_args()

    df5 = load_ohlcv_csv(args.data)
    print(f"Données natives : {len(df5)} bougies ({df5.index[0]} -> {df5.index[-1]})\n")

    rows = []
    for tf in TIMEFRAMES:
        df = resample_ohlcv(df5, tf) if tf != "5min" else df5
        a = compute_atr(df, 14)
        for strat_name, strat_fn in STRATEGIES.items():
            sig = strat_fn(df)
            for atr_mult in ATR_MULTS:
                result = backtest_classic(df, sig, a, atr_mult=atr_mult, rr=RR)
                m = compute_classic_metrics(result.trades, result.equity_curve, 10000.0)
                row = {
                    "tf": tf, "strategy": strat_name, "atr_mult": atr_mult, "rr": RR,
                    "num_trades": m["num_trades"], "win_rate": m["win_rate_pct"],
                    "profit_factor": m["profit_factor"], "profit_factor_gross": m["profit_factor_gross"],
                    "net_pnl": m["net_pnl"], "max_dd_pct": m["max_drawdown_pct"],
                }
                rows.append(row)
                print(
                    f"tf={tf:5s} {strat_name:20s} atr_mult={atr_mult:4.1f} rr={RR:.0f} -> "
                    f"n={row['num_trades']:5d} wr={row['win_rate']:5.1f}% "
                    f"pf={row['profit_factor']:5.2f} pf_gross={row['profit_factor_gross']:5.2f} "
                    f"pnl={row['net_pnl']:10.0f}$ dd={row['max_dd_pct']:7.2f}%"
                )

    candidates = [r for r in rows if r["num_trades"] >= args.min_trades and r["profit_factor"] > args.min_pf]
    candidates.sort(key=lambda r: r["profit_factor"], reverse=True)

    print(f"\n{len(candidates)} candidat(s) passent le filtre (n >= {args.min_trades}, PF net > {args.min_pf}) sur plein échantillon :")
    for c in candidates:
        print(f"  tf={c['tf']:5s} {c['strategy']:20s} atr_mult={c['atr_mult']:4.1f} -> "
              f"n={c['num_trades']} wr={c['win_rate']:.1f}% pf={c['profit_factor']:.2f} pnl={c['net_pnl']:.0f}$")

    if not candidates:
        print("\nAucune combinaison ne dépasse même le filtre plein-échantillon : "
              "pas la peine de lancer de walk-forward, aucun edge apparent sur cette grille.")


if __name__ == "__main__":
    main()
