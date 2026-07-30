"""Conseiller d'entrée en position : réutilise exactement les mêmes
détecteurs de patterns et la même logique de confluence que le backtest
(``mgc_backtest.strategy``), mais appliqués à la toute dernière bougie
disponible pour produire une recommandation lisible (setup détecté ou non,
entrée/stop/take-profits/sizing conseillés).

Ce n'est pas un conseil en investissement : c'est la même règle de décision
que celle validée en backtest, appliquée en temps réel.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from mgc_backtest.strategy.risk import TakeProfitLevel, compute_stop_loss, compute_take_profits, position_size
from mgc_backtest.strategy.rules import StrategyConfig
from mgc_backtest.strategy.signals import (
    BarEvaluation,
    Signal,
    bar_evaluation_to_signal,
    build_market_state,
    evaluate_bar,
)

_DIR_LABEL = {"long": "LONG", "short": "SHORT"}


@dataclass
class EntryAdvice:
    time: pd.Timestamp
    price: float
    signal_fired: bool
    direction: str | None
    score: int
    max_score: int
    checks: dict
    setup_tags: list
    missing: list
    entry: float | None = None
    stop_loss: float | None = None
    take_profits: list = field(default_factory=list)
    position_size: int | None = None
    risk_amount: float | None = None
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "time": self.time.isoformat(),
            "price": self.price,
            "signal_fired": self.signal_fired,
            "direction": self.direction,
            "score": self.score,
            "max_score": self.max_score,
            "checks": self.checks,
            "setup_tags": self.setup_tags,
            "missing": self.missing,
            "entry": self.entry,
            "stop_loss": self.stop_loss,
            "take_profits": [
                {"r_multiple": tp.r_multiple, "price": tp.price, "fraction": tp.fraction}
                for tp in self.take_profits
            ],
            "position_size": self.position_size,
            "risk_amount": self.risk_amount,
            "message": self.message,
        }


def _format_signal_message(sig: Signal, stop: float, tps: list[TakeProfitLevel], size: int, risk_amount: float) -> str:
    tp_txt = " | ".join(f"{tp.r_multiple}R={tp.price:.2f} ({tp.fraction*100:.0f}%)" for tp in tps)
    return (
        f"[SIGNAL] {_DIR_LABEL[sig.direction]} sur MGC à {sig.time} (prix {sig.entry_price:.2f})\n"
        f"Confluence : {sig.score}/4 ({', '.join(sorted(set(sig.setup_tags)))})\n"
        f"Entrée conseillée : {sig.entry_price:.2f}\n"
        f"Stop loss         : {stop:.2f}\n"
        f"Take profits      : {tp_txt}\n"
        f"Taille de position : {size} contrat(s) (risque ≈ {risk_amount:.2f} $)\n"
        f"Ceci provient d'un outil de backtesting/recherche, pas d'un conseil en investissement. "
        f"À vérifier manuellement avant toute exécution."
    )


def _format_no_signal_message(ev: BarEvaluation, missing: list, min_score: int) -> str:
    if not ev.has_recent_sweep:
        return (
            f"[EN ATTENTE] Aucun liquidity sweep HTF récent à {ev.time} (prix {ev.price:.2f}) : "
            f"pas de biais directionnel actif pour l'instant."
        )
    direction_label = _DIR_LABEL.get({"bullish": "long", "bearish": "short"}.get(ev.pattern_direction), "?")
    score = ev.check.score if ev.check else 0
    return (
        f"[EN ATTENTE] Biais {direction_label} actif (sweep récent) à {ev.time} (prix {ev.price:.2f}), "
        f"mais confluence insuffisante : {score}/{min_score} requis. "
        f"Conditions manquantes : {', '.join(missing) if missing else 'aucune (score sous le seuil)'}."
    )


def evaluate_entry_advice(
    df_ltf: pd.DataFrame, df_htf: pd.DataFrame, config: StrategyConfig, capital: float | None = None
) -> EntryAdvice:
    """Analyse la dernière bougie de ``df_ltf`` et retourne une recommandation
    d'entrée (ou l'explication de ce qui manque pour qu'un setup se forme)."""
    if len(df_htf) < 2 or len(df_ltf) == 0:
        raise ValueError("Historique insuffisant pour évaluer un setup (besoin d'au moins 2 bougies HTF)")

    state = build_market_state(df_ltf, df_htf, config)
    i = len(df_ltf) - 1
    ev = evaluate_bar(df_ltf, i, state, config)

    if ev.check is None:
        return EntryAdvice(
            time=ev.time,
            price=ev.price,
            signal_fired=False,
            direction=None,
            score=0,
            max_score=0,
            checks={},
            setup_tags=[],
            missing=[],
            message=f"[INDISPONIBLE] ATR insuffisant à {ev.time} pour évaluer la confluence (historique trop court).",
        )

    missing = [k for k, v in ev.check.checks.items() if not v]
    signal_fired = ev.has_recent_sweep and ev.check.score >= config.confluence.min_score

    advice = EntryAdvice(
        time=ev.time,
        price=ev.price,
        signal_fired=signal_fired,
        direction={"bullish": "long", "bearish": "short"}.get(ev.pattern_direction),
        score=ev.check.score,
        max_score=len(ev.check.checks),
        checks=ev.check.checks,
        setup_tags=ev.check.setup_tags,
        missing=missing,
    )

    if signal_fired:
        sig = bar_evaluation_to_signal(ev)
        stop = compute_stop_loss(sig, config.risk)
        tps = compute_take_profits(sig.entry_price, stop, sig.direction, config.risk)
        cap = capital if capital is not None else config.risk.initial_capital
        size = position_size(cap, sig.entry_price, stop, config.risk)
        risk_amount = cap * config.risk.risk_per_trade_pct / 100.0

        advice.entry = sig.entry_price
        advice.stop_loss = stop
        advice.take_profits = tps
        advice.position_size = size
        advice.risk_amount = risk_amount
        advice.message = _format_signal_message(sig, stop, tps, size, risk_amount)
    else:
        advice.message = _format_no_signal_message(ev, missing, config.confluence.min_score)

    return advice
