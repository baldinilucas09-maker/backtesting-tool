import math

from conftest import make_ohlcv

from mgc_backtest.patterns.vwap import anchored_vwap, session_vwap


def test_session_vwap_cumulative_calculation():
    rows = [
        (100.0, 101.0, 99.0, 100.0, 10),  # typical = 100.0
        (100.0, 103.0, 101.0, 102.0, 20),  # typical = 102.0
    ]
    df = make_ohlcv(rows, start="2025-01-01 01:00", freq="1h")

    vwap = session_vwap(df, session_start_utc="00:00")

    assert vwap.iloc[0] == 100.0
    assert math.isclose(vwap.iloc[1], (100.0 * 10 + 102.0 * 20) / 30, rel_tol=1e-9)


def test_anchored_vwap_nan_before_anchor():
    rows = [
        (100.0, 101.0, 99.0, 100.0, 10),
        (100.0, 103.0, 101.0, 102.0, 20),
        (102.0, 102.5, 101.5, 102.0, 15),  # typical = 102.0
    ]
    df = make_ohlcv(rows)

    avwap = anchored_vwap(df, anchor_time=df.index[1])

    assert math.isnan(avwap.iloc[0])
    assert avwap.iloc[1] == 102.0
    assert math.isclose(avwap.iloc[2], (102.0 * 20 + 102.0 * 15) / 35, rel_tol=1e-9)
