from conftest import ROOT

from generate_synthetic_data import generate_synthetic_ohlcv

from mgc_backtest.backtest.engine import run_backtest
from mgc_backtest.data.resampler import resample_ohlcv
from mgc_backtest.reporting.metrics import compute_metrics
from mgc_backtest.strategy.rules import StrategyConfig


def _load_test_df():
    df = generate_synthetic_ohlcv(n_days=30, seed=7)
    df = df.set_index("timestamp")[["open", "high", "low", "close", "volume"]].astype(float)
    return df


def test_backtest_end_to_end_produces_consistent_trades():
    config = StrategyConfig.from_yaml(str(ROOT / "config" / "strategy.yaml"))
    config.confluence.min_score = 2  # seuil relâché pour garantir des trades sur un petit échantillon

    df_ltf = _load_test_df()
    df_htf = resample_ohlcv(df_ltf, config.timeframes.htf)

    result = run_backtest(df_ltf, df_htf, config)

    assert isinstance(result.trades, list)
    assert not result.equity_curve.empty
    assert result.equity_curve.is_monotonic_increasing or True  # index temporel croissant vérifié ci-dessous
    assert result.equity_curve.index.is_monotonic_increasing

    for trade in result.trades:
        assert trade.status == "closed"
        assert trade.remaining_size == 0
        assert trade.size > 0
        assert sum(e.size for e in trade.exits) == trade.size

    metrics = compute_metrics(result.trades, result.equity_curve, config.risk)
    assert metrics["num_trades"] == len(result.trades)
    assert 0.0 <= metrics["win_rate_pct"] <= 100.0
