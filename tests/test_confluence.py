import pandas as pd
from conftest import make_ohlcv

from mgc_backtest.strategy.confluence import evaluate_confluence
from mgc_backtest.strategy.rules import ConfluenceConfig


def _zone_df(bottom, top):
    return pd.DataFrame([{"bottom": bottom, "top": top}])


def _empty_zone_df():
    return pd.DataFrame(columns=["bottom", "top"])


def test_full_confluence_scores_all_conditions():
    cfg = ConfluenceConfig(proximity_atr_mult=0.5, min_score=4)
    check = evaluate_confluence(
        price=100.0,
        atr_ltf=1.0,
        has_recent_sweep=True,
        active_obs=_zone_df(99.5, 100.5),
        active_fvgs=_zone_df(99.8, 100.2),
        poc=100.1,
        vwap=None,
        cfg=cfg,
    )
    assert check.score == 4
    assert set(check.setup_tags) == {"sweep", "order_block", "fvg", "poc"}


def test_missing_conditions_lower_score():
    cfg = ConfluenceConfig(proximity_atr_mult=0.5, min_score=4)
    check = evaluate_confluence(
        price=100.0,
        atr_ltf=1.0,
        has_recent_sweep=True,
        active_obs=_empty_zone_df(),
        active_fvgs=_empty_zone_df(),
        poc=None,
        vwap=None,
        cfg=cfg,
    )
    assert check.score == 1
    assert check.setup_tags == ["sweep"]


def test_disabled_condition_is_excluded_from_scoring():
    cfg = ConfluenceConfig(
        proximity_atr_mult=0.5,
        min_score=3,
        required={"sweep": True, "order_block": True, "fvg": False, "poc_or_avwap": True},
    )
    check = evaluate_confluence(
        price=100.0,
        atr_ltf=1.0,
        has_recent_sweep=True,
        active_obs=_zone_df(99.5, 100.5),
        active_fvgs=_empty_zone_df(),
        poc=100.0,
        vwap=None,
        cfg=cfg,
    )
    # fvg désactivé -> 3 conditions évaluées, toutes vraies
    assert check.score == 3
    assert "fvg" not in check.checks
