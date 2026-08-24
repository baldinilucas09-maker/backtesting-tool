import pandas as pd

from mgc_backtest.strategy.risk import (
    compute_stop_loss,
    compute_take_profits,
    entry_fill_price,
    is_stop_valid,
    position_size,
)
from mgc_backtest.strategy.rules import RiskConfig
from mgc_backtest.strategy.signals import Signal


def _signal(direction, entry_price, sweep_level, ob_top=None, ob_bottom=None):
    return Signal(
        time=pd.Timestamp("2025-01-01", tz="UTC"),
        direction=direction,
        entry_price=entry_price,
        score=4,
        setup_tags=["sweep", "order_block", "fvg", "poc"],
        sweep_level=sweep_level,
        ob_top=ob_top,
        ob_bottom=ob_bottom,
        atr=1.0,
    )


def test_stop_loss_long_uses_lowest_protective_level():
    cfg = RiskConfig(stop_buffer_ticks=2, tick_size=0.1)
    sig = _signal("long", entry_price=100.0, sweep_level=98.5, ob_top=99.5, ob_bottom=99.0)
    stop = compute_stop_loss(sig, cfg)
    assert stop == 98.5 - 0.2  # min(sweep_level, ob_bottom) - buffer


def test_stop_loss_short_uses_highest_protective_level():
    cfg = RiskConfig(stop_buffer_ticks=2, tick_size=0.1)
    sig = _signal("short", entry_price=100.0, sweep_level=101.5, ob_top=101.0, ob_bottom=100.5)
    stop = compute_stop_loss(sig, cfg)
    assert stop == 101.5 + 0.2  # max(sweep_level, ob_top) + buffer


def test_take_profits_respect_r_multiples():
    cfg = RiskConfig(r_multiples=[1, 2, 3], scale_out_fractions=[0.34, 0.33, 0.33])
    tps = compute_take_profits(entry=100.0, stop=98.0, direction="long", cfg=cfg)
    assert [tp.price for tp in tps] == [102.0, 104.0, 106.0]
    assert sum(tp.fraction for tp in tps) == 1.0


def test_position_size_respects_risk_budget():
    cfg = RiskConfig(risk_per_trade_pct=1.0, tick_size=0.1, tick_value=1.0)
    # risque = 100$ (1% de 10000), risque par contrat = 20 ticks * 1$ = 20$ -> 5 contrats
    size = position_size(capital=10000, entry=100.0, stop=98.0, cfg=cfg)
    assert size == 5


def test_position_size_zero_when_no_risk_distance():
    cfg = RiskConfig(risk_per_trade_pct=1.0, tick_size=0.1, tick_value=1.0)
    size = position_size(capital=10000, entry=100.0, stop=100.0, cfg=cfg)
    assert size == 0


def test_entry_fill_price_is_always_worse_than_signal():
    cfg = RiskConfig(slippage_ticks=3, tick_size=0.1)
    long_sig = _signal("long", entry_price=100.0, sweep_level=98.0)
    short_sig = _signal("short", entry_price=100.0, sweep_level=102.0)

    assert entry_fill_price(long_sig, cfg) == 100.0 + 0.3
    assert entry_fill_price(short_sig, cfg) == 100.0 - 0.3


def test_is_stop_valid_rejects_stop_on_wrong_side_of_entry():
    # cas normal : stop du bon côté
    assert is_stop_valid("long", entry=100.0, stop=98.0) is True
    assert is_stop_valid("short", entry=100.0, stop=102.0) is True
    # sweep obsolète : le prix a dérivé, le stop se retrouve du mauvais côté
    assert is_stop_valid("long", entry=100.0, stop=101.0) is False
    assert is_stop_valid("short", entry=100.0, stop=99.0) is False


def test_fractional_position_size_respects_qty_step():
    cfg = RiskConfig(risk_per_trade_pct=1.0, tick_size=0.1, tick_value=0.1, qty_step=0.001)
    # risque = 100$ (1% de 10000), risque par unité = |entry-stop| = 100 -> 1.0 BTC
    size = position_size(capital=10000, entry=50000.0, stop=49900.0, cfg=cfg)
    assert size == 1.0

    # taille non-ronde : arrondie à la baisse au multiple de qty_step
    size2 = position_size(capital=10000, entry=50000.0, stop=49837.5, cfg=cfg)
    assert size2 == 0.615  # 100/162.5 = 0.6153... -> floor à 0.615


def test_max_leverage_caps_position_size_on_tight_stop():
    # stop anormalement proche de l'entrée -> sans plafond, la formule de
    # risque fixe impliquerait un levier énorme (100/4.8 = ~20.8 BTC, soit
    # ~137x de levier sur 10000$ à 65829.5$/BTC)
    cfg_uncapped = RiskConfig(risk_per_trade_pct=1.0, tick_size=0.1, tick_value=0.1, qty_step=0.001, max_leverage=0.0)
    size_uncapped = position_size(capital=10000, entry=65829.5, stop=65834.3, cfg=cfg_uncapped)
    assert size_uncapped > 20  # confirme le comportement dangereux sans plafond

    cfg_capped = RiskConfig(risk_per_trade_pct=1.0, tick_size=0.1, tick_value=0.1, qty_step=0.001, max_leverage=5.0)
    size_capped = position_size(capital=10000, entry=65829.5, stop=65834.3, cfg=cfg_capped)
    notional = size_capped * 65829.5
    assert notional <= 5.0 * 10000 + 1e-6
    assert size_capped == 0.759
