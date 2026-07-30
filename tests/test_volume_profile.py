import math

from conftest import make_ohlcv

from mgc_backtest.patterns.volume_profile import poc_as_of, rolling_poc


def test_rolling_poc_locates_high_volume_bin():
    rows = [
        (100.0, 101.0, 100.0, 100.5, 100),  # forte activité 100-101
        (103.0, 104.0, 103.0, 103.5, 5),    # faible activité 103-104
        (100.0, 101.0, 100.0, 100.5, 80),   # forte activité 100-101
    ]
    df = make_ohlcv(rows)

    poc = rolling_poc(df, window_bars=3, n_bins=5)

    assert math.isnan(poc.iloc[0])
    assert math.isnan(poc.iloc[1])
    assert poc.iloc[2] == 100.4  # milieu du bin [100.0, 100.8[ où la majorité du volume est concentrée


def test_poc_as_of_uses_only_past_data():
    rows = [
        (100.0, 101.0, 100.0, 100.5, 100),
        (103.0, 104.0, 103.0, 103.5, 5),
        (100.0, 101.0, 100.0, 100.5, 80),
    ]
    df = make_ohlcv(rows)
    poc = rolling_poc(df, window_bars=3, n_bins=5)

    assert poc_as_of(poc, df.index[1]) is None
    assert poc_as_of(poc, df.index[2]) == 100.4
