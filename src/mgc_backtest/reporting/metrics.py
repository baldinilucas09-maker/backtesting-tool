"""Calcul des métriques de performance à partir des trades clôturés.

Deux jeux de chiffres sont exposés : "brut" (mouvement de prix seul, le
slippage est déjà inclus dans les prix d'exécution mais pas les
commissions) et "net" (après commissions) — c'est le net qui reflète ce qui
se passe réellement dans le portefeuille (``equity_curve``, ``net_pnl``,
``final_equity``)."""

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


def _group_win_rate(trades: list, key_fn, is_win_fn) -> dict:
    stats = defaultdict(lambda: {"count": 0, "wins": 0})
    for t in trades:
        for key in key_fn(t):
            stats[key]["count"] += 1
            if is_win_fn(t):
                stats[key]["wins"] += 1
    return {
        k: {"count": v["count"], "win_rate_pct": (v["wins"] / v["count"] * 100) if v["count"] else 0.0}
        for k, v in stats.items()
    }


def _profit_factor(pnls: list) -> float:
    gross_profit = sum(p for p in pnls if p > 0)
    gross_loss = -sum(p for p in pnls if p <= 0)
    if gross_loss > 0:
        return gross_profit / gross_loss
    return float("inf") if gross_profit > 0 else 0.0


def compute_metrics(trades: list, equity_curve: pd.Series, risk_cfg: RiskConfig) -> dict:
    gross_pnls = [t.realized_pnl(risk_cfg.tick_size, risk_cfg.tick_value) for t in trades]
    net_pnls = [
        t.net_pnl(risk_cfg.tick_size, risk_cfg.tick_value, risk_cfg.commission_per_contract, risk_cfg.commission_pct)
        for t in trades
    ]
    total_commission = sum(
        t.total_commission(risk_cfg.commission_per_contract, risk_cfg.commission_pct) for t in trades
    )
    rs = [t.realized_r() for t in trades]
    num_trades = len(trades)

    win_rate_gross_pct = (sum(1 for p in gross_pnls if p > 0) / num_trades * 100) if num_trades else 0.0
    win_rate_net_pct = (sum(1 for p in net_pnls if p > 0) / num_trades * 100) if num_trades else 0.0
    avg_r_realized = (sum(rs) / num_trades) if num_trades else 0.0

    dd = _max_drawdown(equity_curve)

    return {
        "num_trades": num_trades,
        "win_rate_pct": win_rate_net_pct,  # net = ce qui compte réellement pour juger la stratégie
        "win_rate_gross_pct": win_rate_gross_pct,
        "avg_r_realized": avg_r_realized,
        "profit_factor": _profit_factor(net_pnls),
        "profit_factor_gross": _profit_factor(gross_pnls),
        "gross_pnl": sum(gross_pnls),
        "net_pnl": sum(net_pnls),
        "total_commission": total_commission,
        "max_drawdown_pct": dd["pct"],
        "max_drawdown_abs": dd["abs"],
        "final_equity": float(equity_curve.iloc[-1]) if not equity_curve.empty else risk_cfg.initial_capital,
        "per_setup_tag": _group_win_rate(trades, lambda t: set(t.setup_tags), lambda t: t.is_win()),
        "per_direction": _group_win_rate(trades, lambda t: [t.direction], lambda t: t.is_win()),
    }
