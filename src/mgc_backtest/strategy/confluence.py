"""Scoring de confluence : sweep HTF + order block HTF + FVG + POC/AVWAP."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from mgc_backtest.strategy.rules import ConfluenceConfig


@dataclass
class ConfluenceCheck:
    checks: dict
    score: int
    setup_tags: list = field(default_factory=list)


def _price_in_any_zone(price: float, zones: pd.DataFrame) -> bool:
    if zones.empty:
        return False
    return bool(((zones["bottom"] <= price) & (price <= zones["top"])).any())


def evaluate_confluence(
    price: float,
    atr_ltf: float,
    has_recent_sweep: bool,
    active_obs: pd.DataFrame,
    active_fvgs: pd.DataFrame,
    poc: float | None,
    vwap: float | None,
    cfg: ConfluenceConfig,
) -> ConfluenceCheck:
    """Évalue les 4 conditions de confluence pour un prix/instant donnés et
    retourne le score (nb de conditions activées vérifiées) + les tags des
    setups qui ont matché (utile pour les stats de reporting par setup)."""
    required = cfg.required
    checks: dict[str, bool] = {}
    tags: list[str] = []

    if required.get("sweep", True):
        checks["sweep"] = has_recent_sweep
        if has_recent_sweep:
            tags.append("sweep")

    if required.get("order_block", True):
        ok = _price_in_any_zone(price, active_obs)
        checks["order_block"] = ok
        if ok:
            tags.append("order_block")

    if required.get("fvg", True):
        ok = _price_in_any_zone(price, active_fvgs)
        checks["fvg"] = ok
        if ok:
            tags.append("fvg")

    if required.get("poc_or_avwap", True):
        tol = cfg.proximity_atr_mult * atr_ltf if atr_ltf and atr_ltf > 0 else 0.0
        near_poc = poc is not None and abs(price - poc) <= tol
        near_vwap = vwap is not None and abs(price - vwap) <= tol
        ok = near_poc or near_vwap
        checks["poc_or_avwap"] = ok
        if near_poc:
            tags.append("poc")
        if near_vwap:
            tags.append("avwap")

    score = sum(1 for v in checks.values() if v)
    return ConfluenceCheck(checks=checks, score=score, setup_tags=tags)
