from pathlib import Path

import pandas as pd

from convert_tradingview_csv import convert_tradingview_csv


def test_converts_unix_timestamp_and_normalizes_columns(tmp_path: Path):
    src = tmp_path / "tv_export.csv"
    pd.DataFrame(
        [
            {"time": 1700000000, "open": 2000.1, "high": 2001.5, "low": 1999.8, "close": 2000.9, "Volume": 120},
            {"time": 1700000300, "open": 2000.9, "high": 2002.0, "low": 2000.5, "close": 2001.8, "Volume": 95},
        ]
    ).to_csv(src, index=False)

    dst = tmp_path / "converted.csv"
    out = convert_tradingview_csv(src, dst)

    assert list(out.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    assert len(out) == 2
    assert out["timestamp"].is_monotonic_increasing
    assert dst.exists()


def test_handles_extra_indicator_columns():
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "tv_export.csv"
        pd.DataFrame(
            [
                {
                    "time": 1700000000,
                    "open": 2000.1,
                    "high": 2001.5,
                    "low": 1999.8,
                    "close": 2000.9,
                    "Volume": 120,
                    "Volume MA": 110,
                    "RSI": 55.2,
                }
            ]
        ).to_csv(src, index=False)

        dst = Path(d) / "converted.csv"
        out = convert_tradingview_csv(src, dst)

        assert set(out.columns) == {"timestamp", "open", "high", "low", "close", "volume"}
        assert out["volume"].iloc[0] == 120
