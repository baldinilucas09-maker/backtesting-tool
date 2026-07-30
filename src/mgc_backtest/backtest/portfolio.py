"""Suivi du capital et de la courbe d'equity pendant le backtest."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class Portfolio:
    initial_capital: float
    capital: float = field(init=False)
    _times: list = field(default_factory=list)
    _equity: list = field(default_factory=list)

    def __post_init__(self):
        self.capital = self.initial_capital

    def apply_pnl(self, pnl: float) -> None:
        self.capital += pnl

    def record(self, time: pd.Timestamp) -> None:
        self._times.append(time)
        self._equity.append(self.capital)

    def to_series(self) -> pd.Series:
        return pd.Series(self._equity, index=pd.DatetimeIndex(self._times), name="equity")
