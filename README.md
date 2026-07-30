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

## Conseiller d'entrée en position

En plus du backtest historique, `scripts/advise_entry.py` analyse la
**dernière bougie disponible** avec exactement les mêmes détecteurs de
patterns et la même logique de confluence que le backtest, et affiche soit
un plan de trade (entrée / stop / take-profits / taille de position), soit
l'explication de ce qui manque pour qu'un setup se forme :

```bash
python scripts/advise_entry.py --config config/strategy.yaml
```

Options utiles :
- `--data chemin.csv` : analyser un CSV différent (ex : export récent de
  votre plateforme) sans toucher à la config.
- `--capital 15000` : sizing basé sur un capital courant différent de celui
  de la config.
- `--json-out output/latest_advice.json` (défaut) : écrit le résultat en
  JSON — c'est le point d'intégration générique pour brancher le conseil sur
  l'outil que vous utilisez déjà (alerte Discord/Telegram, webhook
  TradingView, bot d'exécution, etc.). Le JSON contient le détail de chaque
  condition de confluence (`checks`), les conditions manquantes (`missing`),
  et le plan de trade complet si un signal est actif (`entry`, `stop_loss`,
  `take_profits`, `position_size`).

Exemple de sortie quand un setup est actif :

```
[SIGNAL] SHORT sur MGC à 2025-03-25 23:55:00+00:00 (prix 2346.42)
Confluence : 4/4 (sweep, order_block, fvg, poc)
Entrée conseillée : 2346.42
Stop loss         : 2347.73
Take profits      : 1R=2345.11 (34%) | 2R=2343.80 (33%) | 3R=2342.49 (33%)
Taille de position : 7 contrat(s) (risque ≈ 100.00 $)
```

Ce conseil provient de la même règle de décision que celle validée en
backtest — ce n'est pas un signal indépendant, et il ne remplace pas une
vérification manuelle avant exécution.

## Structure du projet

```
src/mgc_backtest/
├── data/         # chargement CSV + resampling multi-timeframe
├── patterns/     # un module par pattern (swings, OB, FVG, sweeps, volume profile, VWAP)
├── strategy/     # règles, scoring de confluence, génération de signaux, gestion du risque
├── backtest/     # moteur de backtest event-driven (trade, portfolio, engine)
├── reporting/    # métriques de performance, graphiques, rapport
└── advisor.py    # conseiller d'entrée temps réel (réutilise patterns/ + strategy/)
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
