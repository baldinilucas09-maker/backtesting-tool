from conftest import make_ohlcv

from mgc_backtest.patterns.order_blocks import active_order_blocks, detect_order_blocks


def _baseline_rows(n):
    return [(100.0, 100.1, 99.95, 100.05, 10) for _ in range(n)]


def test_detects_bullish_order_block():
    rows = _baseline_rows(10)
    rows.append((100.05, 100.1, 99.85, 99.9, 12))   # bougie baissière -> deviendra l'OB
    rows.append((99.9, 105.1, 99.85, 105.0, 50))     # bougie impulsive haussière
    df = make_ohlcv(rows)

    obs = detect_order_blocks(df, atr_period=5, impulse_atr_mult=1.5, max_age_bars=10)

    assert len(obs) == 1
    ob = obs.iloc[0]
    assert ob["direction"] == "bullish"
    assert ob["time"] == df.index[10]
    assert ob["top"] == 100.1
    assert ob["bottom"] == 99.85
    assert ob["available_at"] == df.index[11]
    assert ob["mitigated_at"] is None or str(ob["mitigated_at"]) == "NaT"


def test_no_order_block_without_impulsive_move():
    rows = _baseline_rows(15)
    df = make_ohlcv(rows)
    obs = detect_order_blocks(df, atr_period=5, impulse_atr_mult=1.5, max_age_bars=10)
    assert obs.empty


def test_active_order_blocks_respects_availability_and_mitigation():
    rows = _baseline_rows(10)
    rows.append((100.05, 100.1, 99.85, 99.9, 12))
    rows.append((99.9, 105.1, 99.85, 105.0, 50))
    rows.append((105.0, 105.2, 99.8, 100.0, 30))  # revient mitiger la zone [99.85, 100.1]
    df = make_ohlcv(rows)

    obs = detect_order_blocks(df, atr_period=5, impulse_atr_mult=1.5, max_age_bars=10)
    ob_time = df.index[10]
    available_at = df.index[11]
    mitigated_at = df.index[12]

    # avant disponibilité : rien d'exploitable
    before = active_order_blocks(obs, df.index[9], direction="bullish")
    assert before.empty

    # juste après confirmation, avant mitigation : exploitable
    just_after = active_order_blocks(obs, available_at, direction="bullish")
    assert len(just_after) == 1

    # après mitigation : plus exploitable
    after_mitigation = active_order_blocks(obs, mitigated_at, direction="bullish")
    assert after_mitigation.empty
