from conftest import make_ohlcv

from mgc_backtest.patterns.fair_value_gaps import active_fvgs, detect_fair_value_gaps


def test_detects_bullish_fvg_and_mitigation():
    rows = [
        (99.8, 100.0, 99.7, 99.9, 10),     # high=100.0 -> borne basse du gap
        (100.0, 100.7, 99.95, 100.6, 20),  # bougie impulsive centrale
        (100.6, 100.8, 100.5, 100.65, 15), # low=100.5 -> borne haute du gap (100.5>100.0 : gap confirmé)
        (100.65, 100.6, 100.2, 100.3, 10), # revient mitiger la zone [100.0, 100.5]
    ]
    df = make_ohlcv(rows)

    fvgs = detect_fair_value_gaps(df, min_gap_atr_mult=0.0, max_age_bars=10)

    assert len(fvgs) == 1
    fvg = fvgs.iloc[0]
    assert fvg["direction"] == "bullish"
    assert fvg["bottom"] == 100.0
    assert fvg["top"] == 100.5
    assert fvg["available_at"] == df.index[2]
    assert fvg["mitigated_at"] == df.index[3]

    active_before = active_fvgs(fvgs, df.index[2], direction="bullish")
    assert len(active_before) == 1
    active_after = active_fvgs(fvgs, df.index[3], direction="bullish")
    assert active_after.empty


def test_no_fvg_on_overlapping_candles():
    rows = [
        (100.0, 100.5, 99.5, 100.2, 10),
        (100.2, 100.6, 99.8, 100.4, 10),
        (100.4, 100.7, 99.9, 100.5, 10),
    ]
    df = make_ohlcv(rows)
    fvgs = detect_fair_value_gaps(df, min_gap_atr_mult=0.0, max_age_bars=10)
    assert fvgs.empty
