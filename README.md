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

## Importer de vraies données depuis TradingView (Pro)

1. Ouvrez un graphique **MGC1!** (Micro Gold Futures, contrat continu) sur
   TradingView, timeframe **5 minutes**.
2. Scrollez vers la gauche pour charger un maximum d'historique (TradingView
   charge plus de bougies au fur et à mesure que vous remontez dans le
   temps, dans la limite de votre plan).
3. Clic droit sur le graphique → **"Export chart data"** (ou icône
   *appareil photo/export* dans la barre d'outils du graphique) → exporter
   en CSV.
4. Convertissez le fichier exporté au format attendu par l'outil :

   ```bash
   python scripts/convert_tradingview_csv.py chemin/vers/export_tradingview.csv \
       --output data/raw/MGC_5min_real.csv
   ```

5. Pointez la config dessus (`config/strategy.yaml` → `data.raw_file:
   data/raw/MGC_5min_real.csv`) et relancez le backtest.

> **Limite à connaître** : l'export TradingView ne couvre que les bougies
> chargées dans le graphique au moment de l'export (quelques milliers de
> bougies selon votre plan, souvent 1 à 3 semaines en 5min). C'est un bon
> point de départ pour valider le pipeline sur du réel, mais un échantillon
> aussi court reste insuffisant pour juger statistiquement d'un edge — il
> faudra répéter l'export périodiquement (ou trouver une source
> d'historique plus longue) pour accumuler assez de trades.

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
[SIGNAL] SHORT sur MGC à 2025-03-25 23:55:00+00:00 (prix signal 2346.42)
Confluence : 4/4 (sweep, order_block, fvg, poc)
Entrée conseillée : 2346.52 (slippage inclus)
Stop loss         : 2347.73
Take profits      : 1R=2345.11 (34%) | 2R=2343.80 (33%) | 3R=2342.49 (33%)
Taille de position : 7 contrat(s) (risque ≈ 100.00 $, commission d'entrée ≈ 5.18 $)
```

Ce conseil provient de la même règle de décision que celle validée en
backtest — ce n'est pas un signal indépendant, et il ne remplace pas une
vérification manuelle avant exécution.

## Coûts réalistes (slippage + commissions)

Le backtest applique par défaut des coûts de transaction réalistes,
paramétrables dans `config/strategy.yaml` (section `risk`) :
- `slippage_ticks` : slippage défavorable appliqué à **chaque** exécution
  (entrée, chaque sortie partielle/totale) — le fill est toujours pire que
  le niveau théorique visé, jamais meilleur.
- `commission_per_contract` : commission par contrat, facturée à l'entrée
  et à chaque sortie (à ajuster selon votre broker réel).

Le rapport distingue systématiquement performance **brute** (mouvement de
prix seul) et **nette** (après commissions) — c'est le net qui reflète ce
qui se passerait réellement sur votre compte.

## Validation walk-forward

Un backtest unique sur toute la période peut être trompeur (coup de chance,
seuils surajustés aux données). `scripts/run_walk_forward.py` découpe
l'historique en fenêtres séquentielles **train → test** : le seuil de
confluence (`min_score`) est choisi sur chaque fenêtre d'entraînement, puis
appliqué tel quel sur la fenêtre de test suivante (jamais vue pendant la
sélection). Les résultats out-of-sample de toutes les fenêtres sont ensuite
agrégés pour donner une estimation de performance plus honnête, avec un
indicateur explicite de surapprentissage (in-sample vs out-of-sample).

```bash
python scripts/run_walk_forward.py --config config/strategy.yaml \
    --train-days 20 --test-days 10 --min-score-candidates 2,3,4
```

Le rapport (`output/walk_forward/`) contient un tableau par fenêtre
(`walk_forward_folds.csv`), les métriques agrégées out-of-sample, et une
alerte automatique si la performance s'effondre hors échantillon ou si
l'échantillon de trades est trop faible pour conclure statistiquement.

> Sur le jeu de données synthétique fourni par défaut, le walk-forward
> révèle typiquement une performance instable et incohérente d'une fenêtre
> à l'autre — c'est attendu (une marche aléatoire n'a par construction
> aucun edge stable à trouver) et démontre que l'outil détecte bien
> l'absence de robustesse plutôt que de la masquer.

## Structure du projet

```
src/mgc_backtest/
├── data/         # chargement CSV + resampling multi-timeframe
├── patterns/     # un module par pattern (swings, OB, FVG, sweeps, volume profile, VWAP)
├── strategy/     # règles, scoring de confluence, génération de signaux, gestion du risque
├── backtest/     # moteur de backtest event-driven (trade, portfolio, engine, coûts réalistes)
├── reporting/    # métriques de performance (brut/net), graphiques, rapport
├── validation/   # validation walk-forward (fenêtres train/test, agrégation OOS)
└── advisor.py    # conseiller d'entrée temps réel (réutilise patterns/ + strategy/)
```

## Tests

```bash
pytest
```

## Avertissement

Ce projet est un outil de recherche/backtesting. Il ne constitue pas un
conseil en investissement. **Tout ce qu'il a produit jusqu'ici tourne sur
des données synthétiques (marche aléatoire)** — aucune conclusion sur une
quelconque rentabilité ne peut en être tirée. Les coûts réalistes
(slippage, commissions) et la validation walk-forward sont implémentés,
mais la pièce manquante reste un historique de **vraies données de marché**
(le loader CSV est prêt à les recevoir, voir `data/loader.py`). Sans ça,
tout backtest ou conseil produit par cet outil n'a qu'une valeur
démonstrative du pipeline, pas prédictive.
