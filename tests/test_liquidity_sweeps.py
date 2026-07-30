from conftest import make_ohlcv

from mgc_backtest.patterns.liquidity_sweeps import detect_liquidity_sweeps
from mgc_backtest.patterns.swings import detect_swings


def test_detects_bullish_sweep_of_swing_low():
    rows = [
        (102.0, 102.5, 101.8, 102.1, 10),
        (101.0, 101.2, 100.0, 100.5, 10),
        (100.5, 100.7, 99.0, 99.5, 10),   # swing low = 99.0
        (99.5, 100.2, 99.8, 100.0, 10),   # confirme le swing low
        (100.0, 101.0, 99.9, 100.8, 10),
        (100.8, 101.0, 98.5, 100.9, 10),  # sweep : mèche sous 99.0, clôture au-dessus
        (100.9, 101.2, 100.7, 101.0, 10),
    ]
    df = make_ohlcv(rows)
    swings = detect_swings(df, left=1, right=1)
    sweeps = detect_liquidity_sweeps(df, swings, lookback_swings=20)

    assert len(sweeps) == 1
    sweep = sweeps.iloc[0]
    assert sweep["direction"] == "bullish"
    assert sweep["time"] == df.index[5]
    assert sweep["swept_level"] == 99.0
    assert sweep["swept_swing_time"] == df.index[2]


def test_no_sweep_when_price_stays_above_swing_low():
    rows = [
        (102.0, 102.5, 101.8, 102.1, 10),
        (101.0, 101.2, 100.0, 100.5, 10),
        (100.5, 100.7, 99.0, 99.5, 10),
        (99.5, 100.2, 99.8, 100.0, 10),
        (100.0, 101.0, 99.9, 100.8, 10),
        (100.8, 101.0, 99.5, 100.9, 10),  # ne casse pas 99.0
    ]
    df = make_ohlcv(rows)
    swings = detect_swings(df, left=1, right=1)
    sweeps = detect_liquidity_sweeps(df, swings, lookback_swings=20)
    assert sweeps.empty
