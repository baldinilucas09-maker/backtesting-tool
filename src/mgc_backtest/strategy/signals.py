"""Génération des signaux d'entrée à partir de la confluence de patterns.

Le liquidity sweep HTF sert d'événement déclencheur qui fixe le biais
directionnel (sweep haussier -> recherche d'un LONG, sweep baissier ->
recherche d'un SHORT). Pour chaque bougie LTF suivant un sweep récent, on
vérifie le retour dans un order block HTF, la présence d'un FVG (LTF) et la
proximité du POC / AVWAP dans la même direction.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from mgc_backtest.patterns.fair_value_gaps import active_fvgs, detect_fair_value_gaps
from mgc_backtest.patterns.liquidity_sweeps import detect_liquidity_sweeps
from mgc_backtest.patterns.order_blocks import active_order_blocks, detect_order_blocks
from mgc_backtest.patterns.swings import detect_swings
from mgc_backtest.patterns.volume_profile import poc_as_of, rolling_poc
from mgc_backtest.patterns.vwap import multi_anchor_vwap, session_vwap
from mgc_backtest.strategy.confluence import evaluate_confluence
from mgc_backtest.strategy.rules import StrategyConfig
from mgc_backtest.utils.indicators import atr

LTF_ATR_PERIOD = 14
_DIR_MAP = {"bullish": "long", "bearish": "short"}


@dataclass
class Signal:
    time: pd.Timestamp
    direction: str  # "long" ou "short"
    entry_price: float
    score: int
    setup_tags: list
    sweep_level: float
    ob_top: float | None
    ob_bottom: float | None
    atr: float


def _median_timedelta(index: pd.DatetimeIndex) -> pd.Timedelta:
    diffs = index.to_series().diff().dropna()
    return diffs.median()


def _in_session(t: pd.Timestamp, start_utc: str, end_utc: str) -> bool:
    start_h, start_m = (int(x) for x in start_utc.split(":"))
    end_h, end_m = (int(x) for x in end_utc.split(":"))
    start = t.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
    end = t.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
    return start <= t <= end


def generate_signals(df_ltf: pd.DataFrame, df_htf: pd.DataFrame, config: StrategyConfig) -> list[Signal]:
    swings_htf = detect_swings(df_htf, left=config.swings.left_bars, right=config.swings.right_bars)
    sweeps_htf = detect_liquidity_sweeps(
        df_htf, swings_htf, lookback_swings=config.liquidity_sweeps.lookback_swings
    )
    obs_htf = detect_order_blocks(
        df_htf,
        atr_period=config.order_blocks.atr_period,
        impulse_atr_mult=config.order_blocks.impulse_atr_mult,
        max_age_bars=config.order_blocks.max_ob_age_bars,
    )
    fvgs_ltf = detect_fair_value_gaps(
        df_ltf,
        min_gap_atr_mult=config.fair_value_gaps.min_gap_atr_mult,
        max_age_bars=config.fair_value_gaps.max_fvg_age_bars,
    )

    atr_ltf = atr(df_ltf, period=LTF_ATR_PERIOD)
    poc_htf = rolling_poc(df_htf, window_bars=config.volume_profile.window_bars, n_bins=config.volume_profile.n_bins)

    if config.vwap.anchor == "sweep":
        vwap_series = multi_anchor_vwap(df_ltf, sweeps_htf["time"].tolist())
    else:
        vwap_series = session_vwap(df_ltf, session_start_utc=config.vwap.session_start_utc)

    if sweeps_htf.empty or len(df_htf) < 2:
        return []

    htf_bar_td = _median_timedelta(df_htf.index)
    max_sweep_age = config.liquidity_sweeps.max_bars_since_sweep * htf_bar_td

    sweep_times = sweeps_htf["time"].to_numpy()

    signals: list[Signal] = []
    idx = df_ltf.index
    closes = df_ltf["close"].to_numpy()

    for i in range(len(df_ltf)):
        t = idx[i]

        if config.session_filter.enabled and not _in_session(
            t, config.session_filter.start_utc, config.session_filter.end_utc
        ):
            continue

        a = atr_ltf.iloc[i]
        if pd.isna(a) or a <= 0:
            continue

        candidates = sweeps_htf[(sweeps_htf["time"] <= t) & (sweeps_htf["time"] >= t - max_sweep_age)]
        if candidates.empty:
            continue
        last_sweep = candidates.iloc[-1]

        pattern_direction = last_sweep["direction"]  # "bullish" ou "bearish"
        price = closes[i]

        active_obs = active_order_blocks(obs_htf, t, direction=pattern_direction)
        active_fvg = active_fvgs(fvgs_ltf, t, direction=pattern_direction)
        poc_val = poc_as_of(poc_htf, t)
        vwap_val = vwap_series.loc[t] if t in vwap_series.index else None
        if pd.isna(vwap_val):
            vwap_val = None

        has_recent_sweep = True  # défini par construction (candidates non vide)

        check = evaluate_confluence(
            price=price,
            atr_ltf=a,
            has_recent_sweep=has_recent_sweep,
            active_obs=active_obs,
            active_fvgs=active_fvg,
            poc=poc_val,
            vwap=vwap_val,
            cfg=config.confluence,
        )

        if check.score < config.confluence.min_score:
            continue

        ob_row = active_obs.iloc[-1] if not active_obs.empty else None

        signals.append(
            Signal(
                time=t,
                direction=_DIR_MAP[pattern_direction],
                entry_price=float(price),
                score=check.score,
                setup_tags=check.setup_tags,
                sweep_level=float(last_sweep["swept_level"]),
                ob_top=float(ob_row["top"]) if ob_row is not None else None,
                ob_bottom=float(ob_row["bottom"]) if ob_row is not None else None,
                atr=float(a),
            )
        )

    return signals
