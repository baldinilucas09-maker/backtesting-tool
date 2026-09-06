"""Backtest event-driven générique pour les stratégies "classiques" du
module ``classic`` : signal +1/-1/0 -> entrée à l'ouverture de la bougie
suivante (pas de look-ahead), stop et cible fixes basés sur l'ATR au
moment du signal (R:R paramétrable), une seule position à la fois.

Coûts réalistes : slippage défavorable à l'entrée, commission en % du
notionnel à l'entrée et à la sortie. En cas de bougie touchant stop ET
cible le même jour (rare en intraday mais possible), hypothèse
conservatrice : le stop est considéré touché en premier.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import pandas as pd


@dataclass
class ClassicTrade:
    direction: int  # 1 = long, -1 = short
    entry_time: pd.Timestamp
    entry_price: float
    size: float
    stop: float
    target: float
    exit_time: pd.Timestamp | None = None
    exit_price: float | None = None
    exit_reason: str | None = None  # "stop" | "target" | "eod_close"
    gross_pnl: float = 0.0
    net_pnl: float = 0.0
    r_realized: float = 0.0

    def is_win(self) -> bool:
        return self.net_pnl > 0


@dataclass
class ClassicBacktestResult:
    trades: list = field(default_factory=list)
    equity_curve: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))


def backtest_classic(
    df: pd.DataFrame,
    direction_signal: pd.Series,
    atr_series: pd.Series,
    *,
    atr_mult: float = 1.5,
    rr: float = 3.0,
    risk_per_trade_pct: float = 1.0,
    initial_capital: float = 10000.0,
    commission_pct: float = 0.05,
    slippage_ticks: float = 2.0,
    tick_size: float = 0.1,
    qty_step: float = 0.001,
    max_leverage: float = 5.0,
) -> ClassicBacktestResult:
    idx = df.index
    opens = df["open"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()
    atr_vals = atr_series.to_numpy()
    sig_vals = direction_signal.to_numpy()

    equity = initial_capital
    equity_times: list = []
    equity_values: list = []
    trades: list[ClassicTrade] = []

    open_trade: ClassicTrade | None = None
    pending: dict | None = None  # {"direction": int, "atr": float} queued for next bar's open
    slip = slippage_ticks * tick_size

    n = len(df)
    for i in range(n):
        t = idx[i]

        if open_trade is not None:
            if open_trade.direction == 1:
                hit_sl = lows[i] <= open_trade.stop
                hit_tp = highs[i] >= open_trade.target
            else:
                hit_sl = highs[i] >= open_trade.stop
                hit_tp = lows[i] <= open_trade.target

            if hit_sl or hit_tp:
                exit_price = open_trade.stop if hit_sl else open_trade.target
                exit_reason = "stop" if hit_sl else "target"
                gross = (
                    (exit_price - open_trade.entry_price) * open_trade.size
                    if open_trade.direction == 1
                    else (open_trade.entry_price - exit_price) * open_trade.size
                )
                exit_commission = commission_pct / 100 * exit_price * open_trade.size
                net = gross - exit_commission
                risk_amount = abs(open_trade.entry_price - open_trade.stop) * open_trade.size
                open_trade.exit_time = t
                open_trade.exit_price = exit_price
                open_trade.exit_reason = exit_reason
                open_trade.gross_pnl = gross
                open_trade.net_pnl = net
                open_trade.r_realized = gross / risk_amount if risk_amount > 0 else 0.0
                equity += net
                trades.append(open_trade)
                open_trade = None

        if pending is not None and open_trade is None:
            direction = pending["direction"]
            a = pending["atr"]
            entry_raw = opens[i]
            entry = entry_raw + slip if direction == 1 else entry_raw - slip

            if a and a > 0 and not math.isnan(a):
                stop_dist = atr_mult * a
                stop = entry - stop_dist if direction == 1 else entry + stop_dist
                target = entry + rr * stop_dist if direction == 1 else entry - rr * stop_dist

                risk_amount_cap = equity * risk_per_trade_pct / 100
                size = risk_amount_cap / stop_dist if stop_dist > 0 else 0.0
                max_notional = equity * max_leverage
                if entry * size > max_notional and entry > 0:
                    size = max_notional / entry
                size = math.floor(size / qty_step) * qty_step if qty_step > 0 else size

                if size > 0:
                    entry_commission = commission_pct / 100 * entry * size
                    equity -= entry_commission
                    open_trade = ClassicTrade(
                        direction=direction, entry_time=t, entry_price=entry,
                        size=size, stop=stop, target=target,
                    )
            pending = None

        if sig_vals[i] != 0 and open_trade is None and pending is None:
            pending = {"direction": int(sig_vals[i]), "atr": atr_vals[i]}

        equity_times.append(t)
        equity_values.append(equity)

    if open_trade is not None:
        exit_price = float(closes[-1])
        gross = (
            (exit_price - open_trade.entry_price) * open_trade.size
            if open_trade.direction == 1
            else (open_trade.entry_price - exit_price) * open_trade.size
        )
        exit_commission = commission_pct / 100 * exit_price * open_trade.size
        net = gross - exit_commission
        risk_amount = abs(open_trade.entry_price - open_trade.stop) * open_trade.size
        open_trade.exit_time = idx[-1]
        open_trade.exit_price = exit_price
        open_trade.exit_reason = "eod_close"
        open_trade.gross_pnl = gross
        open_trade.net_pnl = net
        open_trade.r_realized = gross / risk_amount if risk_amount > 0 else 0.0
        equity += net
        trades.append(open_trade)
        equity_values[-1] = equity

    return ClassicBacktestResult(
        trades=trades,
        equity_curve=pd.Series(equity_values, index=pd.DatetimeIndex(equity_times), name="equity"),
    )


def compute_classic_metrics(trades: list[ClassicTrade], equity_curve: pd.Series, initial_capital: float) -> dict:
    num_trades = len(trades)
    net_pnls = [t.net_pnl for t in trades]
    gross_pnls = [t.gross_pnl for t in trades]
    rs = [t.r_realized for t in trades]

    def profit_factor(pnls: list[float]) -> float:
        gp = sum(p for p in pnls if p > 0)
        gl = -sum(p for p in pnls if p <= 0)
        if gl > 0:
            return gp / gl
        return float("inf") if gp > 0 else 0.0

    win_rate = (sum(1 for p in net_pnls if p > 0) / num_trades * 100) if num_trades else 0.0
    avg_r = (sum(rs) / num_trades) if num_trades else 0.0

    if equity_curve.empty:
        dd_pct = 0.0
        final_equity = initial_capital
    else:
        running_max = equity_curve.cummax()
        dd_pct = float(((equity_curve - running_max) / running_max * 100).min())
        final_equity = float(equity_curve.iloc[-1])

    return {
        "num_trades": num_trades,
        "win_rate_pct": win_rate,
        "avg_r_realized": avg_r,
        "profit_factor": profit_factor(net_pnls),
        "profit_factor_gross": profit_factor(gross_pnls),
        "net_pnl": sum(net_pnls),
        "gross_pnl": sum(gross_pnls),
        "max_drawdown_pct": dd_pct,
        "final_equity": final_equity,
    }
