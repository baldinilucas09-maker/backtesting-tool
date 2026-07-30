"""Représentation d'un trade et de son cycle de vie pendant le backtest.

Hypothèse simplificatrice (pas de données intrabar tick-level) : si le stop
loss et un take profit sont tous deux atteints dans la même bougie, le stop
loss est considéré prioritaire (scénario le plus défavorable).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from mgc_backtest.strategy.risk import TakeProfitLevel


def split_position_size(size: int, fractions: list[float]) -> list[int]:
    """Répartit ``size`` contrats entre les paliers selon ``fractions``,
    en garantissant que la somme vaut exactement ``size`` (méthode du plus
    grand reste)."""
    raw = [size * f for f in fractions]
    floors = [int(x) for x in raw]
    remainder = size - sum(floors)
    order = sorted(range(len(raw)), key=lambda i: raw[i] - floors[i], reverse=True)
    for i in order[:remainder]:
        floors[i] += 1
    return floors


@dataclass
class ExitFill:
    time: pd.Timestamp
    price: float
    size: int
    reason: str  # "stop_loss" | "take_profit" | "forced_close"
    r_multiple: float


@dataclass
class Trade:
    id: int
    direction: str  # "long" ou "short"
    entry_time: pd.Timestamp
    entry_price: float
    size: int
    stop_loss: float
    take_profits: list[TakeProfitLevel]
    setup_tags: list
    score: int
    planned_sizes: list = field(default_factory=list)
    remaining_size: int = field(init=False)
    exits: list = field(default_factory=list)
    status: str = "open"
    tp_hit_flags: list = field(init=False)

    def __post_init__(self):
        self.remaining_size = self.size
        if not self.planned_sizes:
            self.planned_sizes = split_position_size(
                self.size, [tp.fraction for tp in self.take_profits]
            )
        self.tp_hit_flags = [False] * len(self.take_profits)

    def _r_multiple(self, exit_price: float) -> float:
        risk_per_unit = abs(self.entry_price - self.stop_loss)
        if risk_per_unit == 0:
            return 0.0
        move = (
            (exit_price - self.entry_price)
            if self.direction == "long"
            else (self.entry_price - exit_price)
        )
        return move / risk_per_unit

    def process_bar(self, time: pd.Timestamp, high: float, low: float) -> None:
        if self.status != "open" or self.remaining_size <= 0:
            return

        sl_hit = (low <= self.stop_loss) if self.direction == "long" else (high >= self.stop_loss)
        if sl_hit:
            self.exits.append(
                ExitFill(time, self.stop_loss, self.remaining_size, "stop_loss", self._r_multiple(self.stop_loss))
            )
            self.remaining_size = 0
            self.status = "closed"
            return

        for i, tp in enumerate(self.take_profits):
            if self.tp_hit_flags[i] or self.planned_sizes[i] <= 0:
                continue
            hit = (high >= tp.price) if self.direction == "long" else (low <= tp.price)
            if not hit:
                continue
            exit_size = min(self.planned_sizes[i], self.remaining_size)
            if exit_size <= 0:
                continue
            self.exits.append(ExitFill(time, tp.price, exit_size, "take_profit", tp.r_multiple))
            self.remaining_size -= exit_size
            self.tp_hit_flags[i] = True

        if self.remaining_size <= 0:
            self.status = "closed"

    def force_close(self, time: pd.Timestamp, price: float) -> None:
        if self.remaining_size > 0:
            self.exits.append(
                ExitFill(time, price, self.remaining_size, "forced_close", self._r_multiple(price))
            )
            self.remaining_size = 0
        self.status = "closed"

    def realized_r(self) -> float:
        if self.size == 0:
            return 0.0
        return sum(e.r_multiple * (e.size / self.size) for e in self.exits)

    def realized_pnl(self, tick_size: float, tick_value: float) -> float:
        total = 0.0
        for e in self.exits:
            diff = (e.price - self.entry_price) if self.direction == "long" else (self.entry_price - e.price)
            total += (diff / tick_size) * tick_value * e.size
        return total

    def is_win(self) -> bool:
        return self.realized_r() > 0
