# mgc-backtest

Outil de backtesting pour une stratégie de trading intraday **SMC/ICT** sur le
**Micro Gold Futures (MGC)**, basée sur la confluence de plusieurs signaux
techniques : liquidity sweep HTF, order block HTF, Fair Value Gap, et
proximité du Point of Control (POC) ou d'un AVWAP.

## Installation

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

## Démarrage rapide

1. Générer un jeu de données synthétique (ou déposer votre propre CSV OHLCV
   5min dans `data/raw/`, colonnes attendues : `timestamp,open,high,low,close,volume`) :

   ```bash
   python scripts/generate_synthetic_data.py
   ```

2. Lancer le backtest :

   ```bash
   python scripts/run_backtest.py --config config/strategy.yaml
   ```

3. Le rapport (métriques + courbe d'equity) est écrit dans `output/`.

> **Note sur les données synthétiques** : la config par défaut applique la
> logique de confluence stricte du brief (les 4 conditions — sweep + OB +
> FVG + POC/AVWAP — doivent être vraies simultanément). Sur une marche
> aléatoire synthétique, cet alignement complet est rare (peu de trades,
> voire aucun) car le générateur ne reproduit pas la structure d'ordre
> réelle des marchés. Pour voir le pipeline produire des trades en démo,
> utilisez `config/strategy_relaxed_demo.yaml` (seuil 3/4) :
> ```bash
> python scripts/run_backtest.py --config config/strategy_relaxed_demo.yaml
> ```
> Sur de vraies données de marché, la confluence stricte 4/4 redevient
> pertinente.

## Stratégie

**Entrée** : confluence entre
- un *liquidity sweep* sur le timeframe HTF (prise de liquidité au-dessus/en
  dessous d'un swing high/low),
- un retour de prix dans un *order block* HTF non mitigé dans la même
  direction,
- la présence d'un *Fair Value Gap* (imbalance 3 bougies) dans la zone,
- la proximité du prix avec le *POC* (Fixed Range Volume Profile) ou un
  *AVWAP*.

**Sortie** :
- Stop loss sous/au-dessus de l'order block ou du sweep.
- Take profit multi-cibles (1R/2R/3R par défaut) avec scaling out.

Tous les seuils sont paramétrables dans `config/strategy.yaml`.

## Structure du projet

```
src/mgc_backtest/
├── data/         # chargement CSV + resampling multi-timeframe
├── patterns/     # un module par pattern (swings, OB, FVG, sweeps, volume profile, VWAP)
├── strategy/     # règles, scoring de confluence, génération de signaux, gestion du risque
├── backtest/     # moteur de backtest event-driven (trade, portfolio, engine)
└── reporting/    # métriques de performance, graphiques, rapport
```

## Tests

```bash
pytest
```

## Avertissement

Ce projet est un outil de recherche/backtesting. Il ne constitue pas un
conseil en investissement et ne doit pas être utilisé tel quel pour du
trading en argent réel sans validation approfondie (walk-forward, données
réelles tick-level, coûts de transaction/slippage réalistes).
