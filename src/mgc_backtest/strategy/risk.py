"""Calcul du stop loss, des take profits multi-cibles et du sizing."""

from __future__ import annotations

import math
from dataclasses import dataclass

from mgc_backtest.strategy.rules import RiskConfig
from mgc_backtest.strategy.signals import Signal


@dataclass
class TakeProfitLevel:
    r_multiple: float
    price: float
    fraction: float


def entry_fill_price(signal: Signal, cfg: RiskConfig) -> float:
    """Prix d'entrée réaliste après slippage défavorable (toujours pire que
    le prix théorique du signal)."""
    slip = cfg.slippage_ticks * cfg.tick_size
    return signal.entry_price + slip if signal.direction == "long" else signal.entry_price - slip


def compute_stop_loss(signal: Signal, cfg: RiskConfig) -> float:
    """SL sous (long) / au-dessus (short) du niveau le plus protecteur entre
    l'order block et le sweep, avec un buffer de sécurité en ticks."""
    buffer = cfg.stop_buffer_ticks * cfg.tick_size
    if signal.direction == "long":
        base = signal.sweep_level
        if signal.ob_bottom is not None:
            base = min(base, signal.ob_bottom)
        return base - buffer
    else:
        base = signal.sweep_level
        if signal.ob_top is not None:
            base = max(base, signal.ob_top)
        return base + buffer


def is_stop_valid(direction: str, entry: float, stop: float) -> bool:
    """Le sweep/order block utilisé pour placer le stop peut dater de
    plusieurs bougies HTF (``max_bars_since_sweep``) : si le prix a dérivé
    entre-temps, le stop calculé peut se retrouver du mauvais côté du prix
    d'entrée réel (ex: stop au-dessus de l'entrée pour un long). Un tel
    setup est invalide et ne doit pas être tradé."""
    return stop < entry if direction == "long" else stop > entry


def compute_take_profits(entry: float, stop: float, direction: str, cfg: RiskConfig) -> list[TakeProfitLevel]:
    risk_per_unit = abs(entry - stop)
    levels = []
    for r, frac in zip(cfg.r_multiples, cfg.scale_out_fractions):
        price = entry + r * risk_per_unit if direction == "long" else entry - r * risk_per_unit
        levels.append(TakeProfitLevel(r_multiple=r, price=price, fraction=frac))
    return levels


def position_size(capital: float, entry: float, stop: float, cfg: RiskConfig) -> float:
    """Taille de position (contrats entiers pour un future, quantité
    fractionnaire pour un perpetual crypto via ``qty_step``) telle que la
    perte au stop loss ne dépasse pas ``risk_per_trade_pct`` du capital
    courant, arrondie à la baisse au multiple de ``qty_step`` le plus proche.

    Quand le stop calculé est anormalement proche du prix d'entrée (sweep/OB
    très serré), la formule "risque fixe" implique une taille de position
    énorme (donc un levier énorme) pour respecter ce risque en $ : sans
    plafond, ce serait irréaliste (aucun exchange n'offre un levier
    illimité) et dangereux. ``max_leverage`` (0 = pas de plafond) borne le
    notionnel de la position à ``max_leverage x capital``."""
    risk_amount = capital * cfg.risk_per_trade_pct / 100.0
    risk_ticks = abs(entry - stop) / cfg.tick_size
    risk_per_unit = risk_ticks * cfg.tick_value
    if risk_per_unit <= 0:
        return 0.0
    raw_size = risk_amount / risk_per_unit

    if cfg.max_leverage > 0 and entry > 0:
        max_size_by_leverage = (cfg.max_leverage * capital) / entry
        raw_size = min(raw_size, max_size_by_leverage)

    steps = math.floor(raw_size / cfg.qty_step + 1e-9)
    return max(steps, 0) * cfg.qty_step
