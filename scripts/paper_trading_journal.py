#!/usr/bin/env python3
"""Journal de paper trading (forward-test sans argent réel).

Cet environnement n'a aucun accès réseau sortant vers les flux de marché en
direct — impossible d'y faire tourner un bot connecté en continu. À la place,
ce script s'appuie sur le workflow déjà utilisé pour la recherche de données :
à chaque fois que de nouvelles bougies récentes sont ajoutées au fichier de
données (ex. un nouveau mois exporté depuis data.binance.vision), relance ce
script.

Il rejoue tout l'historique avec le moteur de backtest existant
(déterministe, sans look-ahead — mêmes règles qu'un vrai backtest) et compare
le résultat au dernier état connu (``output/paper_trading/state.json``) pour
ne signaler que ce qui est NOUVEAU depuis le dernier passage :
- les trades qui se sont clôturés entre-temps (stop loss ou take profit
  réellement touché par le prix), avec leur résultat,
- la position en cours, si une entrée a eu lieu mais n'est pas encore
  clôturée (stop/take profit à surveiller).

Chaque trade nouvellement clôturé est archivé dans
``paper_trading/journal.jsonl`` (un JSON par ligne), qui sert de piste
d'audit du suivi en conditions réelles — à ne jamais modifier à la main.

Important : ce dossier n'est PAS dans ``output/`` (qui est ignoré par git,
régénéré à chaque backtest) précisément parce qu'il doit survivre d'une
session à l'autre — pensez à commit/push après chaque passage pour ne pas
perdre le suivi.

Usage :
    python scripts/paper_trading_journal.py --config config/strategy_btc_perp_candidate_a.yaml
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mgc_backtest.backtest.engine import run_backtest  # noqa: E402
from mgc_backtest.data.loader import load_ohlcv_csv  # noqa: E402
from mgc_backtest.data.resampler import resample_ohlcv  # noqa: E402
from mgc_backtest.strategy.rules import StrategyConfig  # noqa: E402


def _trade_to_dict(t, risk_cfg) -> dict:
    last_exit = t.exits[-1] if t.exits else None
    return {
        "entry_time": str(t.entry_time),
        "direction": t.direction,
        "entry_price": t.entry_price,
        "size": t.size,
        "setup_tags": list(t.setup_tags),
        "score": t.score,
        "exit_time": str(last_exit.time) if last_exit else None,
        "exit_reason": last_exit.reason if last_exit else None,
        "exit_price": last_exit.price if last_exit else None,
        "r_realized": t.realized_r(),
        "net_pnl": t.net_pnl(
            risk_cfg.tick_size,
            risk_cfg.tick_value,
            risk_cfg.commission_per_contract,
            risk_cfg.commission_pct,
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Journal de paper trading : rejoue l'historique complet et ne signale que le nouveau depuis le dernier passage"
    )
    parser.add_argument("--config", default="config/strategy_btc_perp_candidate_a.yaml")
    parser.add_argument("--state-dir", default="paper_trading")
    args = parser.parse_args()

    state_dir = Path(args.state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / "state.json"
    journal_path = state_dir / "journal.jsonl"

    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    reported = set(state.get("reported_entry_times", []))

    config = StrategyConfig.from_yaml(args.config)
    df_ltf = load_ohlcv_csv(config.data.raw_file, timezone=config.data.timezone)
    df_htf = resample_ohlcv(df_ltf, config.timeframes.htf)

    result = run_backtest(df_ltf, df_htf, config)
    last_bar_time = df_ltf.index[-1]

    pending = None
    newly_closed = []
    for t in result.trades:
        key = str(t.entry_time)
        # Un trade encore ouvert à la fin des données connues est clôturé de
        # force par le moteur pour produire des métriques propres — mais
        # dans la réalité, cette position est toujours en cours.
        still_open = bool(t.exits) and t.exits[-1].reason == "forced_close"
        if still_open:
            pending = t
            continue
        if key not in reported:
            newly_closed.append(t)
            reported.add(key)

    print(f"Données à jour jusqu'à : {last_bar_time}")
    print(f"Config : {args.config}\n")

    if newly_closed:
        print(f"=== {len(newly_closed)} trade(s) clôturé(s) depuis le dernier passage ===")
        for t in newly_closed:
            d = _trade_to_dict(t, config.risk)
            print(
                f"  {d['entry_time']} {d['direction']:5s} entrée={d['entry_price']:.2f} "
                f"-> {d['exit_time']} ({d['exit_reason']}) R={d['r_realized']:+.2f} "
                f"PnL net={d['net_pnl']:+.2f}$"
            )
            with journal_path.open("a") as f:
                f.write(json.dumps(d) + "\n")
    else:
        print("Aucun trade clôturé depuis le dernier passage.")

    if pending is not None:
        tps = ", ".join(f"{tp.price:.2f} ({tp.r_multiple}R)" for tp in pending.take_profits)
        print("\n=== Position en cours à surveiller (pas encore clôturée) ===")
        print(f"  Entrée {pending.entry_time} {pending.direction} @ {pending.entry_price:.2f}")
        print(f"  Stop loss      : {pending.stop_loss:.2f}")
        print(f"  Take profit(s) : {tps}")
        print(f"  Setups         : {', '.join(pending.setup_tags)} (score {pending.score})")
    else:
        print("\nAucune position en cours actuellement (en attente d'un nouveau signal).")

    if journal_path.exists():
        lines = [json.loads(line) for line in journal_path.read_text().splitlines() if line.strip()]
        if lines:
            wins = sum(1 for entry in lines if entry["r_realized"] > 0)
            total_r = sum(entry["r_realized"] for entry in lines)
            total_pnl = sum(entry["net_pnl"] for entry in lines)
            print(f"\n=== Cumul paper trading ({len(lines)} trade(s) clôturé(s) depuis le début du suivi) ===")
            print(f"  Win rate : {wins / len(lines) * 100:.1f}%  |  R total : {total_r:+.2f}  |  PnL net cumulé : {total_pnl:+.2f}$")

    state["reported_entry_times"] = sorted(reported)
    state["last_bar_time"] = str(last_bar_time)
    state_path.write_text(json.dumps(state, indent=2))


if __name__ == "__main__":
    main()
