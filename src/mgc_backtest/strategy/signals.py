"""Génération des signaux d'entrée à partir de la confluence de patterns.

Le liquidity sweep HTF sert d'événement déclencheur qui fixe le biais
directionnel (sweep haussier -> recherche d'un LONG, sweep baissier ->
recherche d'un SHORT). Pour chaque bougie LTF suivant un sweep récent, on
vérifie le retour dans un order block HTF, la présence d'un FVG (LTF) et la
proximité du POC / AVWAP dans la même direction.

Le calcul des patterns (``build_market_state``) et l'évaluation d'une bougie
(``evaluate_bar``) sont exposés séparément pour être réutilisés à la fois par
le backtest historique (``generate_signals``) et par le conseiller d'entrée
temps réel (``mgc_backtest.advisor``), qui n'évalue que la dernière bougie.
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
from mgc_backtest.strategy.confluence import ConfluenceCheck, evaluate_confluence
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


@dataclass
class MarketState:
    swings_htf: pd.DataFrame
    sweeps_htf: pd.DataFrame
    obs_htf: pd.DataFrame
    fvgs_ltf: pd.DataFrame
    atr_ltf: pd.Series
    poc_htf: pd.Series
    vwap_series: pd.Series
    max_sweep_age: pd.Timedelta


@dataclass
class BarEvaluation:
    time: pd.Timestamp
    price: float
    has_recent_sweep: bool
    pattern_direction: str | None  # "bullish" / "bearish" / None
    last_sweep: pd.Series | None
    active_obs: pd.DataFrame
    active_fvg: pd.DataFrame
    poc: float | None
    vwap: float | None
    atr: float | None
    check: ConfluenceCheck | None


def _median_timedelta(index: pd.DatetimeIndex) -> pd.Timedelta:
    diffs = index.to_series().diff().dropna()
    return diffs.median()


def _in_session(t: pd.Timestamp, start_utc: str, end_utc: str) -> bool:
    start_h, start_m = (int(x) for x in start_utc.split(":"))
    end_h, end_m = (int(x) for x in end_utc.split(":"))
    start = t.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
    end = t.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
    return start <= t <= end


def build_market_state(df_ltf: pd.DataFrame, df_htf: pd.DataFrame, config: StrategyConfig) -> MarketState:
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

    htf_bar_td = _median_timedelta(df_htf.index) if len(df_htf) >= 2 else pd.Timedelta(0)
    max_sweep_age = config.liquidity_sweeps.max_bars_since_sweep * htf_bar_td

    return MarketState(
        swings_htf=swings_htf,
        sweeps_htf=sweeps_htf,
        obs_htf=obs_htf,
        fvgs_ltf=fvgs_ltf,
        atr_ltf=atr_ltf,
        poc_htf=poc_htf,
        vwap_series=vwap_series,
        max_sweep_age=max_sweep_age,
    )


def evaluate_bar(df_ltf: pd.DataFrame, i: int, state: MarketState, config: StrategyConfig) -> BarEvaluation:
    """Évalue la confluence à la bougie LTF d'indice ``i``. Fonctionne même
    sans sweep récent (utile pour le conseiller d'entrée, qui doit pouvoir
    expliquer "aucun biais directionnel actif" plutôt que planter)."""
    t = df_ltf.index[i]
    price = float(df_ltf["close"].iloc[i])
    a = state.atr_ltf.iloc[i]
    a = float(a) if pd.notna(a) and a > 0 else None

    candidates = state.sweeps_htf[
        (state.sweeps_htf["time"] <= t) & (state.sweeps_htf["time"] >= t - state.max_sweep_age)
    ]
    has_recent_sweep = not candidates.empty
    last_sweep = candidates.iloc[-1] if has_recent_sweep else None
    pattern_direction = last_sweep["direction"] if has_recent_sweep else None

    if pattern_direction is not None:
        active_obs = active_order_blocks(state.obs_htf, t, direction=pattern_direction)
        active_fvg = active_fvgs(state.fvgs_ltf, t, direction=pattern_direction)
    else:
        active_obs = state.obs_htf.iloc[0:0]
        active_fvg = state.fvgs_ltf.iloc[0:0]

    poc_val = poc_as_of(state.poc_htf, t)
    vwap_val = state.vwap_series.loc[t] if t in state.vwap_series.index else None
    if vwap_val is not None and pd.isna(vwap_val):
        vwap_val = None
    elif vwap_val is not None:
        vwap_val = float(vwap_val)

    check = None
    if a is not None:
        check = evaluate_confluence(
            price=price,
            atr_ltf=a,
            has_recent_sweep=has_recent_sweep,
            active_obs=active_obs,
            active_fvgs=active_fvg,
            poc=poc_val,
            vwap=vwap_val,
            cfg=config.confluence,
            direction=_DIR_MAP.get(pattern_direction),
            bar_open=float(df_ltf["open"].iloc[i]),
            bar_close=price,
        )

    return BarEvaluation(
        time=t,
        price=price,
        has_recent_sweep=has_recent_sweep,
        pattern_direction=pattern_direction,
        last_sweep=last_sweep,
        active_obs=active_obs,
        active_fvg=active_fvg,
        poc=poc_val,
        vwap=vwap_val,
        atr=a,
        check=check,
    )


def bar_evaluation_to_signal(ev: BarEvaluation) -> Signal:
    ob_row = ev.active_obs.iloc[-1] if not ev.active_obs.empty else None
    return Signal(
        time=ev.time,
        direction=_DIR_MAP[ev.pattern_direction],
        entry_price=ev.price,
        score=ev.check.score,
        setup_tags=ev.check.setup_tags,
        sweep_level=float(ev.last_sweep["swept_level"]),
        ob_top=float(ob_row["top"]) if ob_row is not None else None,
        ob_bottom=float(ob_row["bottom"]) if ob_row is not None else None,
        atr=ev.atr,
    )


def generate_signals(df_ltf: pd.DataFrame, df_htf: pd.DataFrame, config: StrategyConfig) -> list[Signal]:
    if len(df_htf) < 2:
        return []

    state = build_market_state(df_ltf, df_htf, config)
    if state.sweeps_htf.empty:
        return []

    signals: list[Signal] = []
    for i in range(len(df_ltf)):
        t = df_ltf.index[i]
        if config.session_filter.enabled and not _in_session(
            t, config.session_filter.start_utc, config.session_filter.end_utc
        ):
            continue

        ev = evaluate_bar(df_ltf, i, state, config)
        if not ev.has_recent_sweep or ev.check is None:
            continue
        if ev.check.score < config.confluence.min_score:
            continue

        signals.append(bar_evaluation_to_signal(ev))

    return signals
