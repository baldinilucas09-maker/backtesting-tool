"""Calcul des métriques de performance à partir des trades clôturés."""

from __future__ import annotations

from collections import defaultdict

import pandas as pd

from mgc_backtest.strategy.rules import RiskConfig


def _max_drawdown(equity: pd.Series) -> dict:
    if equity.empty:
        return {"pct": 0.0, "abs": 0.0}
    running_max = equity.cummax()
    dd_abs = equity - running_max
    dd_pct = dd_abs / running_max * 100
    return {"pct": float(dd_pct.min()), "abs": float(dd_abs.min())}


def _group_win_rate(trades: list, key_fn) -> dict:
    stats = defaultdict(lambda: {"count": 0, "wins": 0})
    for t in trades:
        for key in key_fn(t):
            stats[key]["count"] += 1
            if t.is_win():
                stats[key]["wins"] += 1
    return {
        k: {"count": v["count"], "win_rate_pct": (v["wins"] / v["count"] * 100) if v["count"] else 0.0}
        for k, v in stats.items()
    }


def compute_metrics(trades: list, equity_curve: pd.Series, risk_cfg: RiskConfig) -> dict:
    pnls = [t.realized_pnl(risk_cfg.tick_size, risk_cfg.tick_value) for t in trades]
    rs = [t.realized_r() for t in trades]
    num_trades = len(trades)

    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    win_rate_pct = (len(wins) / num_trades * 100) if num_trades else 0.0
    avg_r_realized = (sum(rs) / num_trades) if num_trades else 0.0

    gross_profit = sum(wins)
    gross_loss = -sum(losses)
    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    else:
        profit_factor = float("inf") if gross_profit > 0 else 0.0

    dd = _max_drawdown(equity_curve)

    return {
        "num_trades": num_trades,
        "win_rate_pct": win_rate_pct,
        "avg_r_realized": avg_r_realized,
        "profit_factor": profit_factor,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "net_pnl": sum(pnls),
        "max_drawdown_pct": dd["pct"],
        "max_drawdown_abs": dd["abs"],
        "final_equity": float(equity_curve.iloc[-1]) if not equity_curve.empty else risk_cfg.initial_capital,
        "per_setup_tag": _group_win_rate(trades, lambda t: set(t.setup_tags)),
        "per_direction": _group_win_rate(trades, lambda t: [t.direction]),
    }
