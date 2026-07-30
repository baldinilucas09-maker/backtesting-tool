import pandas as pd
from conftest import make_ohlcv

from mgc_backtest.backtest.trade import Trade, split_position_size
from mgc_backtest.strategy.risk import TakeProfitLevel


def test_split_position_size_sums_exactly():
    sizes = split_position_size(5, [0.34, 0.33, 0.33])
    assert sum(sizes) == 5
    assert all(s >= 0 for s in sizes)


def test_split_position_size_small_size_no_overallocation():
    sizes = split_position_size(1, [0.34, 0.33, 0.33])
    assert sum(sizes) == 1


def test_take_profit_scales_out_across_levels():
    t = pd.Timestamp("2025-01-01", tz="UTC")
    trade = Trade(
        id=1,
        direction="long",
        entry_time=t,
        entry_price=100.0,
        size=3,
        stop_loss=98.0,
        take_profits=[
            TakeProfitLevel(r_multiple=1, price=102.0, fraction=1 / 3),
            TakeProfitLevel(r_multiple=2, price=104.0, fraction=1 / 3),
            TakeProfitLevel(r_multiple=3, price=106.0, fraction=1 / 3),
        ],
        setup_tags=["sweep"],
        score=4,
    )

    trade.process_bar(t + pd.Timedelta(hours=1), high=102.5, low=101.0)
    assert trade.remaining_size == 2
    assert trade.status == "open"

    trade.process_bar(t + pd.Timedelta(hours=2), high=107.0, low=103.5)
    assert trade.remaining_size == 0
    assert trade.status == "closed"
    assert len(trade.exits) == 3
    assert trade.realized_r() > 0


def test_stop_loss_takes_priority_within_same_bar():
    t = pd.Timestamp("2025-01-01", tz="UTC")
    trade = Trade(
        id=2,
        direction="long",
        entry_time=t,
        entry_price=100.0,
        size=1,
        stop_loss=98.0,
        take_profits=[TakeProfitLevel(r_multiple=1, price=102.0, fraction=1.0)],
        setup_tags=[],
        score=4,
    )
    # la bougie touche à la fois le stop et le take profit -> le stop prime
    trade.process_bar(t + pd.Timedelta(hours=1), high=103.0, low=97.0)

    assert trade.status == "closed"
    assert trade.exits[0].reason == "stop_loss"
    assert trade.realized_r() == -1.0


def test_realized_pnl_matches_direction():
    t = pd.Timestamp("2025-01-01", tz="UTC")
    trade = Trade(
        id=3,
        direction="short",
        entry_time=t,
        entry_price=100.0,
        size=2,
        stop_loss=101.0,
        take_profits=[TakeProfitLevel(r_multiple=1, price=99.0, fraction=1.0)],
        setup_tags=[],
        score=4,
    )
    trade.process_bar(t + pd.Timedelta(hours=1), high=99.5, low=98.5)

    assert trade.status == "closed"
    pnl = trade.realized_pnl(tick_size=0.1, tick_value=1.0)
    # entry 100 -> exit 99 sur un short = +1.0 de gain unitaire = 10 ticks * 2 contrats
    assert pnl == 20.0
