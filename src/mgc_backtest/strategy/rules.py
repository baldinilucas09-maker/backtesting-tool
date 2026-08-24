"""Paramètres de la stratégie, chargés depuis un fichier YAML."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class TimeframesConfig:
    ltf: str
    htf: str


@dataclass
class DataConfig:
    raw_file: str
    timezone: str = "UTC"


@dataclass
class SwingsConfig:
    left_bars: int = 2
    right_bars: int = 2


@dataclass
class LiquiditySweepsConfig:
    lookback_swings: int = 20
    max_bars_since_sweep: int = 12


@dataclass
class OrderBlocksConfig:
    impulse_atr_mult: float = 1.5
    atr_period: int = 14
    max_ob_age_bars: int = 40


@dataclass
class FVGConfig:
    min_gap_atr_mult: float = 0.0
    max_fvg_age_bars: int = 30


@dataclass
class VolumeProfileConfig:
    window_bars: int = 48
    n_bins: int = 30


@dataclass
class VWAPConfig:
    anchor: str = "session"
    session_start_utc: str = "00:00"


@dataclass
class ConfluenceConfig:
    proximity_atr_mult: float = 0.5
    min_score: int = 4
    required: dict = field(default_factory=lambda: {
        "sweep": True, "order_block": True, "fvg": True, "poc_or_avwap": True, "confirmation": False,
    })


@dataclass
class RiskConfig:
    initial_capital: float = 10000
    risk_per_trade_pct: float = 1.0
    stop_buffer_ticks: int = 2
    tick_size: float = 0.1
    tick_value: float = 1.0
    r_multiples: list = field(default_factory=lambda: [1, 2, 3])
    scale_out_fractions: list = field(default_factory=lambda: [0.34, 0.33, 0.33])
    max_concurrent_trades: int = 1
    commission_per_contract: float = 0.74  # $ fixe par unité de taille, par exécution (futures : par contrat)
    commission_pct: float = 0.0            # % du notionnel (prix x taille), par exécution (marchés type crypto perp)
    slippage_ticks: float = 1.0            # ticks de slippage défavorable appliqués à chaque exécution
    qty_step: float = 1.0                  # granularité minimale de la taille de position (1.0 = contrats entiers)
    max_leverage: float = 0.0              # plafond notionnel = max_leverage x capital (0 = pas de plafond)
    breakeven_after_tp_index: int | None = None  # après ce palier de TP (index 0 = 1er), stop ramené au point d'équilibre


@dataclass
class SessionFilterConfig:
    enabled: bool = False
    start_utc: str = "12:00"
    end_utc: str = "20:00"


@dataclass
class StrategyConfig:
    timeframes: TimeframesConfig
    data: DataConfig
    swings: SwingsConfig
    liquidity_sweeps: LiquiditySweepsConfig
    order_blocks: OrderBlocksConfig
    fair_value_gaps: FVGConfig
    volume_profile: VolumeProfileConfig
    vwap: VWAPConfig
    confluence: ConfluenceConfig
    risk: RiskConfig
    session_filter: SessionFilterConfig

    @classmethod
    def from_yaml(cls, path: str | Path) -> "StrategyConfig":
        with open(path) as f:
            raw = yaml.safe_load(f)
        return cls(
            timeframes=TimeframesConfig(**raw["timeframes"]),
            data=DataConfig(**raw["data"]),
            swings=SwingsConfig(**raw["swings"]),
            liquidity_sweeps=LiquiditySweepsConfig(**raw["liquidity_sweeps"]),
            order_blocks=OrderBlocksConfig(**raw["order_blocks"]),
            fair_value_gaps=FVGConfig(**raw["fair_value_gaps"]),
            volume_profile=VolumeProfileConfig(**raw["volume_profile"]),
            vwap=VWAPConfig(**raw["vwap"]),
            confluence=ConfluenceConfig(**raw["confluence"]),
            risk=RiskConfig(**raw["risk"]),
            session_filter=SessionFilterConfig(**raw["session_filter"]),
        )
