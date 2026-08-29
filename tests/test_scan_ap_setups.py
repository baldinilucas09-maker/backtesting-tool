from conftest import ROOT

from scan_ap_setups import _analyze, _fmt_setups_rows, _max_score, build_html

from mgc_backtest.strategy.rules import StrategyConfig
from mgc_backtest.strategy.signals import Signal


def test_max_score_counts_only_enabled_required_checks():
    config = StrategyConfig.from_yaml(str(ROOT / "config" / "strategy_btc_perp_candidate_a.yaml"))
    assert _max_score(config) == 4  # sweep, order_block, fvg, poc_or_avwap

    swing_config = StrategyConfig.from_yaml(str(ROOT / "config" / "strategy_btc_perp_swing.yaml"))
    assert _max_score(swing_config) == 4  # sweep, order_block, poc_or_avwap, confirmation (fvg désactivé)


def test_fmt_setups_rows_empty():
    html = _fmt_setups_rows([], max_score=4)
    assert "Aucun setup A+" in html


def test_fmt_setups_rows_renders_signal_details():
    import pandas as pd

    sig = Signal(
        time=pd.Timestamp("2026-01-01 00:00", tz="UTC"),
        direction="long",
        entry_price=12345.6,
        score=4,
        setup_tags=["sweep", "order_block", "avwap"],
        sweep_level=12000.0,
        ob_top=12100.0,
        ob_bottom=12050.0,
        atr=50.0,
    )
    html = _fmt_setups_rows([sig], max_score=4)
    assert "LONG" in html
    assert "12,345.60" in html
    assert "4/4" in html
    assert "sweep" in html and "order_block" in html


def test_analyze_runs_end_to_end_on_synthetic_data():
    style = {
        "key": "test",
        "label": "Test synthétique",
        "config": str(ROOT / "config" / "strategy.yaml"),
        "lookback_days": 30,
    }
    result = _analyze(style)

    assert result["style"] == style
    assert result["max_score"] > 0
    assert result["advice"].time == result["last_bar_time"]
    assert isinstance(result["ap_signals"], list)
    for sig in result["ap_signals"]:
        assert sig.score == result["max_score"]
        assert sig.time >= result["last_bar_time"] - __import__("pandas").Timedelta(days=30)


def test_build_html_includes_each_style_section():
    style = {
        "key": "test",
        "label": "Test synthétique",
        "config": str(ROOT / "config" / "strategy.yaml"),
        "lookback_days": 30,
    }
    result = _analyze(style)

    html = build_html([result])

    assert "Test synthétique" in html
    assert "<!doctype html>" in html.lower()
    assert "Setups A+ récents" in html
