"""Moteur de backtest event-driven : parcourt les bougies LTF, gère les
trades ouverts (SL/TP/scaling out) et ouvre de nouveaux trades sur signal.

Coûts réalistes : chaque entrée subit un slippage défavorable (le fill est
toujours pire que le prix du signal) avant même le calcul du stop/des take
profits, et une commission par contrat est prélevée à chaque exécution
(entrée + chaque sortie), pas seulement en fin de trade.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from mgc_backtest.backtest.portfolio import Portfolio
from mgc_backtest.backtest.trade import Trade
from mgc_backtest.strategy.risk import compute_stop_loss, compute_take_profits, entry_fill_price, position_size
from mgc_backtest.strategy.rules import StrategyConfig
from mgc_backtest.strategy.signals import Signal, generate_signals


@dataclass
class BacktestResult:
    trades: list
    equity_curve: pd.Series
    signals: list = field(default_factory=list)


def _apply_exit_pnl(portfolio: Portfolio, trade: Trade, new_exits: list, cfg) -> None:
    for e in new_exits:
        diff = (e.price - trade.entry_price) if trade.direction == "long" else (trade.entry_price - e.price)
        portfolio.apply_pnl((diff / cfg.tick_size) * cfg.tick_value * e.size)
        portfolio.apply_pnl(-cfg.commission_per_contract * e.size)


def run_backtest(df_ltf: pd.DataFrame, df_htf: pd.DataFrame, config: StrategyConfig) -> BacktestResult:
    signals: list[Signal] = generate_signals(df_ltf, df_htf, config)

    portfolio = Portfolio(config.risk.initial_capital)
    open_trades: list[Trade] = []
    closed_trades: list[Trade] = []
    trade_id = 0
    signal_ptr = 0

    idx = df_ltf.index
    highs = df_ltf["high"].to_numpy()
    lows = df_ltf["low"].to_numpy()

    for i in range(len(df_ltf)):
        t = idx[i]
        high, low = highs[i], lows[i]

        for trade in list(open_trades):
            n_exits_before = len(trade.exits)
            trade.process_bar(t, high, low)
            _apply_exit_pnl(portfolio, trade, trade.exits[n_exits_before:], config.risk)
            if trade.status == "closed":
                open_trades.remove(trade)
                closed_trades.append(trade)

        while signal_ptr < len(signals) and signals[signal_ptr].time == t:
            sig = signals[signal_ptr]
            signal_ptr += 1
            if len(open_trades) >= config.risk.max_concurrent_trades:
                continue

            entry_price = entry_fill_price(sig, config.risk)
            stop = compute_stop_loss(sig, config.risk)
            tps = compute_take_profits(entry_price, stop, sig.direction, config.risk)
            size = position_size(portfolio.capital, entry_price, stop, config.risk)
            if size <= 0:
                continue

            trade_id += 1
            trade = Trade(
                id=trade_id,
                direction=sig.direction,
                entry_time=t,
                entry_price=entry_price,
                size=size,
                stop_loss=stop,
                take_profits=tps,
                setup_tags=sig.setup_tags,
                score=sig.score,
                slippage_ticks=config.risk.slippage_ticks,
                tick_size=config.risk.tick_size,
            )
            open_trades.append(trade)
            portfolio.apply_pnl(-config.risk.commission_per_contract * size)

        portfolio.record(t)

    if open_trades:
        last_time = idx[-1]
        last_price = float(df_ltf["close"].iloc[-1])
        for trade in list(open_trades):
            n_exits_before = len(trade.exits)
            trade.force_close(last_time, last_price)
            _apply_exit_pnl(portfolio, trade, trade.exits[n_exits_before:], config.risk)
            closed_trades.append(trade)
        portfolio.record(last_time)

    return BacktestResult(trades=closed_trades, equity_curve=portfolio.to_series(), signals=signals)
