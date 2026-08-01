"""Calcul du stop loss, des take profits multi-cibles et du sizing."""

from __future__ import annotations

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


def compute_take_profits(entry: float, stop: float, direction: str, cfg: RiskConfig) -> list[TakeProfitLevel]:
    risk_per_unit = abs(entry - stop)
    levels = []
    for r, frac in zip(cfg.r_multiples, cfg.scale_out_fractions):
        price = entry + r * risk_per_unit if direction == "long" else entry - r * risk_per_unit
        levels.append(TakeProfitLevel(r_multiple=r, price=price, fraction=frac))
    return levels


def position_size(capital: float, entry: float, stop: float, cfg: RiskConfig) -> int:
    """Nombre de contrats tel que la perte au stop loss ne dépasse pas
    ``risk_per_trade_pct`` du capital courant."""
    risk_amount = capital * cfg.risk_per_trade_pct / 100.0
    risk_ticks = abs(entry - stop) / cfg.tick_size
    risk_per_contract = risk_ticks * cfg.tick_value
    if risk_per_contract <= 0:
        return 0
    return max(int(risk_amount // risk_per_contract), 0)
