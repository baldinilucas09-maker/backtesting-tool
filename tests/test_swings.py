from conftest import make_ohlcv

from mgc_backtest.patterns.swings import detect_swings


def test_detects_swing_low():
    rows = [
        (102.0, 102.5, 101.8, 102.1, 10),
        (101.0, 101.2, 100.0, 100.5, 10),
        (100.5, 100.7, 99.0, 99.5, 10),   # pivot low
        (99.5, 100.2, 99.8, 100.0, 10),
        (100.0, 101.0, 99.9, 100.8, 10),
    ]
    df = make_ohlcv(rows)
    swings = detect_swings(df, left=1, right=1)

    lows = swings[swings["type"] == "low"]
    assert len(lows) == 1
    assert lows.iloc[0]["price"] == 99.0
    assert lows.iloc[0]["time"] == df.index[2]
    assert lows.iloc[0]["confirmed_at"] == df.index[3]


def test_no_swing_on_monotonic_series():
    rows = [(100 + i, 100.5 + i, 99.8 + i, 100.2 + i, 10) for i in range(6)]
    df = make_ohlcv(rows)
    swings = detect_swings(df, left=1, right=1)
    assert swings.empty
