"""Validation walk-forward : découpe l'historique en fenêtres séquentielles
train -> test, sélectionne le paramètre de confluence (``min_score``) le
plus performant sur chaque fenêtre d'entraînement, puis mesure la
performance hors échantillon (test, jamais vue pendant la sélection) avec ce
paramètre.

But : détecter le surapprentissage (performance in-sample très supérieure à
l'out-of-sample) et estimer une performance plus honnête que celle d'un
backtest unique sur toute la période, qui peut être trompeuse (un seul essai
peut être un coup de chance).

Limite assumée : chaque fenêtre de test repart d'un capital neuf
(``risk.initial_capital``), les fenêtres ne "compoundent" donc pas entre
elles. La courbe d'equity OOS agrégée (``pooled_test_equity``) est
reconstruite en chaînant les PnL nets des trades de test dans l'ordre
chronologique, pour donner une vision continue malgré cette limite.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

import pandas as pd

from mgc_backtest.backtest.engine import run_backtest
from mgc_backtest.data.resampler import resample_ohlcv
from mgc_backtest.reporting.metrics import compute_metrics
from mgc_backtest.strategy.rules import StrategyConfig

MIN_FOLD_BARS = 10


@dataclass
class FoldResult:
    fold_index: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    chosen_min_score: int | None
    train_metrics: dict
    test_metrics: dict
    test_trades: list = field(default_factory=list)


@dataclass
class WalkForwardReport:
    folds: list
    pooled_test_metrics: dict
    pooled_test_equity: pd.Series


def _run_slice_backtest(df_ltf_slice: pd.DataFrame, config: StrategyConfig):
    if len(df_ltf_slice) < MIN_FOLD_BARS:
        return None, None
    df_htf_slice = resample_ohlcv(df_ltf_slice, config.timeframes.htf)
    if len(df_htf_slice) < 2:
        return None, None
    result = run_backtest(df_ltf_slice, df_htf_slice, config)
    metrics = compute_metrics(result.trades, result.equity_curve, config.risk)
    return result, metrics


def _select_best_min_score(
    df_train: pd.DataFrame, base_config: StrategyConfig, candidates: tuple, selection_metric: str
):
    best_score = None
    best_value = None
    best_metrics = None
    for candidate in candidates:
        cfg = copy.deepcopy(base_config)
        cfg.confluence.min_score = candidate
        _, metrics = _run_slice_backtest(df_train, cfg)
        if metrics is None:
            continue
        value = metrics[selection_metric]
        if value == float("inf"):
            value = 1e9
        if best_value is None or value > best_value:
            best_value = value
            best_score = candidate
            best_metrics = metrics
    return best_score, best_metrics


def _build_pooled_equity(trades: list, risk_cfg) -> pd.Series:
    if not trades:
        return pd.Series(dtype=float)
    # trié par heure de sortie : c'est à ce moment-là que le PnL est réalisé
    trades_sorted = sorted(trades, key=lambda t: t.exits[-1].time if t.exits else t.entry_time)
    capital = risk_cfg.initial_capital
    times, equity = [], []
    for t in trades_sorted:
        capital += t.net_pnl(risk_cfg.tick_size, risk_cfg.tick_value, risk_cfg.commission_per_contract)
        times.append(t.exits[-1].time if t.exits else t.entry_time)
        equity.append(capital)
    return pd.Series(equity, index=pd.DatetimeIndex(times), name="equity_oos_pooled")


def walk_forward_validate(
    df_ltf: pd.DataFrame,
    config: StrategyConfig,
    train_days: int = 20,
    test_days: int = 10,
    min_score_candidates: tuple = (2, 3, 4),
    selection_metric: str = "net_pnl",
) -> WalkForwardReport:
    """Découpe ``df_ltf`` en fenêtres séquentielles [train_days | test_days],
    répétées en glissant de ``test_days`` à chaque itération (pas de
    chevauchement des fenêtres de test). Sur chaque fenêtre d'entraînement,
    sélectionne le meilleur ``min_score`` parmi ``min_score_candidates``
    selon ``selection_metric``, puis l'applique tel quel sur la fenêtre de
    test correspondante (jamais vue lors de la sélection)."""
    if df_ltf.empty:
        return WalkForwardReport(folds=[], pooled_test_metrics=compute_metrics([], pd.Series(dtype=float), config.risk), pooled_test_equity=pd.Series(dtype=float))

    start, end = df_ltf.index[0], df_ltf.index[-1]
    train_span = pd.Timedelta(days=train_days)
    test_span = pd.Timedelta(days=test_days)

    folds: list[FoldResult] = []
    pooled_trades = []

    fold_index = 0
    cursor = start
    while cursor + train_span + test_span <= end:
        train_start, train_end = cursor, cursor + train_span
        test_start, test_end = train_end, train_end + test_span

        df_train = df_ltf[(df_ltf.index >= train_start) & (df_ltf.index < train_end)]
        df_test = df_ltf[(df_ltf.index >= test_start) & (df_ltf.index < test_end)]

        chosen_score, train_metrics = _select_best_min_score(df_train, config, min_score_candidates, selection_metric)

        test_metrics: dict = {}
        test_trades: list = []
        if chosen_score is not None:
            test_config = copy.deepcopy(config)
            test_config.confluence.min_score = chosen_score
            test_result, test_metrics_computed = _run_slice_backtest(df_test, test_config)
            if test_result is not None:
                test_trades = test_result.trades
                test_metrics = test_metrics_computed
                pooled_trades.extend(test_trades)

        folds.append(
            FoldResult(
                fold_index=fold_index,
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
                chosen_min_score=chosen_score,
                train_metrics=train_metrics or {},
                test_metrics=test_metrics,
                test_trades=test_trades,
            )
        )

        fold_index += 1
        cursor = cursor + test_span

    pooled_equity = _build_pooled_equity(pooled_trades, config.risk)
    pooled_metrics = compute_metrics(pooled_trades, pooled_equity, config.risk)

    return WalkForwardReport(folds=folds, pooled_test_metrics=pooled_metrics, pooled_test_equity=pooled_equity)
