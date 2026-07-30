"""Chargement et validation de données OHLCV depuis un fichier CSV."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = ["open", "high", "low", "close", "volume"]


def load_ohlcv_csv(path: str | Path, timezone: str = "UTC") -> pd.DataFrame:
    """Charge un CSV OHLCV et retourne un DataFrame trié, indexé par timestamp.

    Le CSV doit contenir une colonne ``timestamp`` (parsable par pandas) et
    les colonnes ``open, high, low, close, volume``. Les lignes dupliquées
    ou hors ordre sont supprimées/triées ; les prix incohérents (high < low,
    etc.) lèvent une erreur explicite.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Fichier de données introuvable : {path}")

    df = pd.read_csv(path)

    if "timestamp" not in df.columns:
        raise ValueError("Le CSV doit contenir une colonne 'timestamp'")
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Colonnes manquantes dans le CSV : {missing}")

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    if timezone != "UTC":
        df["timestamp"] = df["timestamp"].dt.tz_convert(timezone)

    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="first")]
    df = df[REQUIRED_COLUMNS].astype(float)

    _validate_ohlcv(df)
    return df


def _validate_ohlcv(df: pd.DataFrame) -> None:
    if df.empty:
        raise ValueError("Le jeu de données OHLCV est vide")
    bad_hl = df["high"] < df["low"]
    if bad_hl.any():
        raise ValueError(f"{bad_hl.sum()} lignes ont high < low")
    bad_oc = (
        (df["open"] > df["high"]) | (df["open"] < df["low"])
        | (df["close"] > df["high"]) | (df["close"] < df["low"])
    )
    if bad_oc.any():
        raise ValueError(f"{bad_oc.sum()} lignes ont open/close hors du range [low, high]")
    if (df["volume"] < 0).any():
        raise ValueError("Volume négatif détecté")
