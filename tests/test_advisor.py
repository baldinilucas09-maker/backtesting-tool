from conftest import ROOT

from generate_synthetic_data import generate_synthetic_ohlcv

from mgc_backtest.advisor import evaluate_entry_advice
from mgc_backtest.data.resampler import resample_ohlcv
from mgc_backtest.strategy.rules import StrategyConfig


def _load_test_df(n_days=30, seed=7):
    df = generate_synthetic_ohlcv(n_days=n_days, seed=seed)
    return df.set_index("timestamp")[["open", "high", "low", "close", "volume"]].astype(float)


def test_advice_reports_no_signal_when_confluence_incomplete():
    config = StrategyConfig.from_yaml(str(ROOT / "config" / "strategy.yaml"))
    df_ltf = _load_test_df()
    df_htf = resample_ohlcv(df_ltf, config.timeframes.htf)

    advice = evaluate_entry_advice(df_ltf, df_htf, config)

    assert advice.signal_fired is False
    assert advice.entry is None
    assert advice.stop_loss is None
    assert advice.message  # un message explicatif est toujours produit
    assert advice.time == df_ltf.index[-1]


def test_advice_computes_full_trade_plan_when_signal_fires():
    config = StrategyConfig.from_yaml(str(ROOT / "config" / "strategy.yaml"))
    config.confluence.min_score = 1  # force un signal sur la dernière bougie pour valider le calcul du plan
    df_ltf = _load_test_df()
    df_htf = resample_ohlcv(df_ltf, config.timeframes.htf)

    advice = evaluate_entry_advice(df_ltf, df_htf, config, capital=10000)

    if advice.signal_fired:
        assert advice.entry is not None
        assert advice.stop_loss is not None
        assert len(advice.take_profits) == len(config.risk.r_multiples)
        assert advice.position_size is not None
        assert advice.risk_amount == 10000 * config.risk.risk_per_trade_pct / 100
        d = advice.to_dict()
        assert d["signal_fired"] is True
        assert len(d["take_profits"]) == len(config.risk.r_multiples)


def test_advice_handles_no_recent_sweep_gracefully():
    config = StrategyConfig.from_yaml(str(ROOT / "config" / "strategy.yaml"))
    df_ltf = _load_test_df(n_days=3, seed=1)  # historique très court -> peu/pas de sweeps HTF
    df_htf = resample_ohlcv(df_ltf, config.timeframes.htf)

    advice = evaluate_entry_advice(df_ltf, df_htf, config)

    assert advice.signal_fired is False
    assert isinstance(advice.message, str) and len(advice.message) > 0
