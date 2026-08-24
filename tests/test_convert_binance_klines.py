from pathlib import Path

import pandas as pd

from convert_binance_klines import convert_binance_klines


def _write_raw_klines(path: Path, rows: list) -> None:
    pd.DataFrame(rows).to_csv(path, index=False, header=False)


def test_converts_ms_epoch_and_drops_extra_columns(tmp_path: Path):
    src = tmp_path / "BTCUSDT-5m-2024-01.csv"
    _write_raw_klines(
        src,
        [
            [1700000000000, "2000.10", "2001.50", "1999.80", "2000.90", "120.5", 1700000299999, "241000", 500, "60.2", "120500", "0"],
            [1700000300000, "2000.90", "2002.00", "2000.50", "2001.80", "95.3", 1700000599999, "190800", 400, "47.6", "95400", "0"],
        ],
    )
    dst = tmp_path / "converted.csv"

    out = convert_binance_klines([src], dst)

    assert list(out.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    assert len(out) == 2
    assert out["timestamp"].is_monotonic_increasing
    assert dst.exists()


def test_merges_multiple_files_deduplicated_and_sorted(tmp_path: Path):
    src1 = tmp_path / "month1.csv"
    src2 = tmp_path / "month2.csv"
    _write_raw_klines(src1, [[1700000300000, "2000.9", "2002.0", "2000.5", "2001.8", "95.3", 0, "0", 0, "0", "0", "0"]])
    _write_raw_klines(
        src2,
        [
            [1700000000000, "2000.1", "2001.5", "1999.8", "2000.9", "120.5", 0, "0", 0, "0", "0", "0"],
            [1700000300000, "2000.9", "2002.0", "2000.5", "2001.8", "95.3", 0, "0", 0, "0", "0", "0"],  # doublon
        ],
    )
    dst = tmp_path / "converted.csv"

    out = convert_binance_klines([src1, src2], dst)

    assert len(out) == 2  # doublon supprimé
    assert out["timestamp"].is_monotonic_increasing


def test_skips_header_row_if_present(tmp_path: Path):
    src = tmp_path / "with_header.csv"
    with open(src, "w") as f:
        f.write("open_time,open,high,low,close,volume,close_time,qav,trades,tbbav,tbqav,ignore\n")
        f.write("1700000000000,2000.1,2001.5,1999.8,2000.9,120.5,0,0,0,0,0,0\n")
    dst = tmp_path / "converted.csv"

    out = convert_binance_klines([src], dst)

    assert len(out) == 1
    assert out["open"].iloc[0] == 2000.1
