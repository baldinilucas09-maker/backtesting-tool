"""Représentation d'un trade et de son cycle de vie pendant le backtest.

Hypothèses simplificatrices (pas de données intrabar tick-level) :
- si le stop loss et un take profit sont tous deux atteints dans la même
  bougie, le stop loss est considéré prioritaire (scénario le plus
  défavorable) ;
- chaque exécution (entrée et chaque sortie) subit un slippage défavorable
  fixe (``slippage_ticks``) : on obtient toujours un prix légèrement pire
  que le niveau théorique visé, jamais meilleur ;
- ``breakeven_after_tp_index`` (optionnel) : une fois ce palier de take
  profit atteint, le stop est ramené au prix d'entrée pour le reste de la
  position — protège contre un retournement après qu'un objectif de prix a
  été atteint, plutôt que de risquer de rendre les gains jusqu'au stop
  initial.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from mgc_backtest.strategy.risk import TakeProfitLevel

_SIZE_EPSILON = 1e-9  # tolérance flottante pour les tailles fractionnaires (crypto)


def split_position_size(size: float, fractions: list[float]) -> list:
    """Répartit ``size`` entre les paliers selon ``fractions``, en
    garantissant que la somme vaut exactement ``size``.

    Pour une taille entière (contrats futures), utilise la méthode du plus
    grand reste (résultat entier). Pour une taille fractionnaire (quantité
    crypto), répartit proportionnellement et attribue le reste exact au
    dernier palier."""
    if float(size).is_integer():
        size_int = int(round(size))
        raw = [size_int * f for f in fractions]
        floors = [int(x) for x in raw]
        remainder = size_int - sum(floors)
        order = sorted(range(len(raw)), key=lambda i: raw[i] - floors[i], reverse=True)
        for i in order[:remainder]:
            floors[i] += 1
        return floors

    result: list[float] = []
    allocated = 0.0
    for i, f in enumerate(fractions):
        qty = (size - allocated) if i == len(fractions) - 1 else size * f
        result.append(qty)
        allocated += qty
    return result


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
    slippage_ticks: float = 0.0
    tick_size: float = 0.0
    breakeven_after_tp_index: int | None = None
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

    def _slipped(self, price: float) -> float:
        """Prix d'exécution après slippage défavorable (toujours pire pour
        le trader : plus bas pour une vente, plus haut pour un achat)."""
        slip = self.slippage_ticks * self.tick_size
        return price - slip if self.direction == "long" else price + slip

    def process_bar(self, time: pd.Timestamp, high: float, low: float) -> None:
        if self.status != "open" or self.remaining_size <= _SIZE_EPSILON:
            return

        sl_hit = (low <= self.stop_loss) if self.direction == "long" else (high >= self.stop_loss)
        if sl_hit:
            fill_price = self._slipped(self.stop_loss)
            self.exits.append(
                ExitFill(time, fill_price, self.remaining_size, "stop_loss", self._r_multiple(fill_price))
            )
            self.remaining_size = 0
            self.status = "closed"
            return

        for i, tp in enumerate(self.take_profits):
            if self.tp_hit_flags[i] or self.planned_sizes[i] <= _SIZE_EPSILON:
                continue
            hit = (high >= tp.price) if self.direction == "long" else (low <= tp.price)
            if not hit:
                continue
            exit_size = min(self.planned_sizes[i], self.remaining_size)
            if exit_size <= _SIZE_EPSILON:
                continue
            fill_price = self._slipped(tp.price)
            self.exits.append(ExitFill(time, fill_price, exit_size, "take_profit", tp.r_multiple))
            self.remaining_size -= exit_size
            self.tp_hit_flags[i] = True

            if self.breakeven_after_tp_index is not None and i == self.breakeven_after_tp_index:
                # "invalidation" : une fois cet objectif atteint, on protège le
                # trade contre un retournement en ramenant le stop au point
                # d'équilibre plutôt que de risquer de rendre les gains
                self.stop_loss = self.entry_price

        if self.remaining_size <= _SIZE_EPSILON:
            self.status = "closed"

    def force_close(self, time: pd.Timestamp, price: float) -> None:
        if self.remaining_size > _SIZE_EPSILON:
            fill_price = self._slipped(price)
            self.exits.append(
                ExitFill(time, fill_price, self.remaining_size, "forced_close", self._r_multiple(fill_price))
            )
            self.remaining_size = 0
        self.status = "closed"

    def realized_r(self) -> float:
        if self.size == 0:
            return 0.0
        return sum(e.r_multiple * (e.size / self.size) for e in self.exits)

    def realized_pnl(self, tick_size: float, tick_value: float) -> float:
        """PnL brut (avant commissions), slippage déjà inclus dans les prix
        d'exécution enregistrés dans ``exits``."""
        total = 0.0
        for e in self.exits:
            diff = (e.price - self.entry_price) if self.direction == "long" else (self.entry_price - e.price)
            total += (diff / tick_size) * tick_value * e.size
        return total

    def total_commission(self, commission_per_contract: float = 0.0, commission_pct: float = 0.0) -> float:
        """Commission totale du trade : une exécution à l'entrée plus une
        exécution par sortie (partielle ou totale). Deux modèles cumulables :
        ``commission_per_contract`` (montant fixe par unité de taille, type
        futures) et ``commission_pct`` (% du notionnel prix x taille, type
        crypto perpetual)."""
        exited_size = sum(e.size for e in self.exits)
        flat = commission_per_contract * (self.size + exited_size)

        pct_cost = 0.0
        if commission_pct:
            entry_notional = self.entry_price * self.size
            exit_notional = sum(e.price * e.size for e in self.exits)
            pct_cost = (commission_pct / 100.0) * (entry_notional + exit_notional)

        return flat + pct_cost

    def net_pnl(
        self,
        tick_size: float,
        tick_value: float,
        commission_per_contract: float = 0.0,
        commission_pct: float = 0.0,
    ) -> float:
        return self.realized_pnl(tick_size, tick_value) - self.total_commission(commission_per_contract, commission_pct)

    def is_win(self) -> bool:
        return self.realized_r() > 0
