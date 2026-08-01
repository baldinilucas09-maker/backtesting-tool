from conftest import ROOT

from generate_synthetic_data import generate_synthetic_ohlcv

from mgc_backtest.strategy.rules import StrategyConfig
from mgc_backtest.validation.walk_forward import walk_forward_validate


def _load_test_df(n_days=30, seed=3):
    df = generate_synthetic_ohlcv(n_days=n_days, seed=seed)
    return df.set_index("timestamp")[["open", "high", "low", "close", "volume"]].astype(float)


def test_walk_forward_builds_sequential_non_overlapping_folds():
    config = StrategyConfig.from_yaml(str(ROOT / "config" / "strategy.yaml"))
    df_ltf = _load_test_df()

    report = walk_forward_validate(
        df_ltf, config, train_days=10, test_days=5, min_score_candidates=(2, 3, 4)
    )

    assert len(report.folds) > 0
    for fold in report.folds:
        assert fold.train_start < fold.train_end == fold.test_start < fold.test_end
        if fold.chosen_min_score is not None:
            assert fold.chosen_min_score in (2, 3, 4)

    # les fenêtres de test ne se chevauchent jamais
    for a, b in zip(report.folds, report.folds[1:]):
        assert a.test_end <= b.test_start


def test_walk_forward_pooled_metrics_have_expected_shape():
    config = StrategyConfig.from_yaml(str(ROOT / "config" / "strategy.yaml"))
    df_ltf = _load_test_df()

    report = walk_forward_validate(
        df_ltf, config, train_days=10, test_days=5, min_score_candidates=(2, 3, 4)
    )

    metrics = report.pooled_test_metrics
    assert "num_trades" in metrics
    assert "win_rate_pct" in metrics
    assert "profit_factor" in metrics
    assert 0.0 <= metrics["win_rate_pct"] <= 100.0

    total_test_trades = sum(len(f.test_trades) for f in report.folds)
    assert metrics["num_trades"] == total_test_trades

    if total_test_trades > 0:
        assert not report.pooled_test_equity.empty
        assert report.pooled_test_equity.index.is_monotonic_increasing
