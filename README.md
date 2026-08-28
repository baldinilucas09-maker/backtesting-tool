# mgc-backtest

Outil de backtesting pour une stratégie de trading intraday **SMC/ICT**,
basée sur la confluence de plusieurs signaux techniques : liquidity sweep
HTF, order block HTF, Fair Value Gap, et proximité du Point of Control (POC)
ou d'un AVWAP.

La logique de détection est agnostique de l'actif (n'importe quel CSV OHLCV
convient). **Actif principal actuel : BTC Perpetual** (`config/strategy_btc_perp.yaml`,
hypothèse par défaut Binance BTCUSDT USDT-M — à corriger si vous utilisez un
autre exchange/contrat). Le projet a démarré sur Micro Gold Futures (MGC),
dont la config (`config/strategy.yaml`) reste disponible et fonctionnelle.
Le nom du package (`mgc_backtest`) est un reliquat historique, pas une
limitation.

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

2. Lancer le backtest (remplacez `config/strategy.yaml` par
   `config/strategy_btc_perp.yaml` pour l'actif principal actuel, BTC
   Perpetual — nécessite d'abord un jeu de données BTC, voir plus bas) :

   ```bash
   python scripts/run_backtest.py --config config/strategy.yaml
   ```

3. Le rapport (métriques + courbe d'equity) est écrit dans `output/`.

## Importer de vraies données

### Option recommandée : historique gratuit Binance (aucun compte requis)

Binance publie tout son historique de klines (chandelles) gratuitement, en
téléchargement direct, sans compte ni abonnement :
[data.binance.vision](https://data.binance.vision/?prefix=data/futures/um/monthly/klines/BTCUSDT/5m/)

1. Sur cette page, cliquez sur un ou plusieurs fichiers `BTCUSDT-5m-AAAA-MM.zip`
   (un par mois) pour les télécharger.
2. Convertissez-les (plusieurs fichiers acceptés en une commande, ils sont
   fusionnés et triés) :

   ```bash
   python scripts/convert_binance_klines.py chemin/vers/*.zip \
       --output data/raw/BTCUSDT_5min_real.csv
   ```

### Alternative : export TradingView (nécessite un plan payant)

1. Ouvrez un graphique **BINANCE:BTCUSDT.P** (BTC Perpetual ; pour MGC :
   **MGC1!**, Micro Gold Futures contrat continu) sur TradingView, timeframe
   **5 minutes**.
2. Scrollez vers la gauche pour charger un maximum d'historique (TradingView
   charge plus de bougies au fur et à mesure que vous remontez dans le
   temps, dans la limite de votre plan).
3. Clic droit sur le graphique → **"Export chart data"** (fonctionnalité
   réservée aux plans payants Essential/Plus/Premium) → exporter en CSV.
4. Convertissez le fichier exporté au format attendu par l'outil :

   ```bash
   python scripts/convert_tradingview_csv.py chemin/vers/export_tradingview.csv \
       --output data/raw/BTCUSDT_5min_real.csv
   ```

Dans les deux cas, le chemin par défaut de `config/strategy_btc_perp.yaml`
pointe déjà sur `data/raw/BTCUSDT_5min_real.csv` — déposez le fichier converti à cet
   emplacement et relancez le backtest (ou ajustez `data.raw_file` si vous
   utilisez un autre nom).

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
> utilisez la config assouplie (seuil 3/4) correspondante :
> ```bash
> python scripts/run_backtest.py --config config/strategy_relaxed_demo.yaml            # MGC
> python scripts/run_backtest.py --config config/strategy_btc_perp_relaxed_demo.yaml    # BTC perp
> ```
> (le jeu BTC synthétique se génère avec
> `python scripts/generate_synthetic_data.py --start-price 60000 --base-vol 0.0018 \
> --include-weekends --out data/raw/BTCUSDT_5min_synthetic.csv`)
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

Tous les seuils sont paramétrables dans `config/strategy.yaml` (ou
`config/strategy_btc_perp.yaml`).

> **Garde-fou** : le sweep utilisé pour placer le stop peut dater de
> plusieurs bougies HTF (`max_bars_since_sweep`). Si le prix a suffisamment
> dérivé entre-temps, le stop calculé peut se retrouver du mauvais côté du
> prix d'entrée (ex : stop au-dessus de l'entrée pour un long) — un cas
> détecté en testant sur données BTC plus volatiles que le jeu MGC initial.
> Un tel setup est désormais automatiquement rejeté (`is_stop_valid` dans
> `strategy/risk.py`), aussi bien en backtest qu'en conseil d'entrée.

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

## Indicateur TradingView (Pine Script)

`pine/smc_ict_entry_advisor.pine` porte la même logique de confluence
directement sur un graphique TradingView : liquidity sweep HTF, order block
HTF, FVG, **volume profile HTF (POC)** et **AVWAP ancré sur le dernier sweep
HTF** (pas un simple reset de session), avec des labels LONG/SHORT quand le
score de confluence est atteint. Utile pour une vérification visuelle
rapide, ou pour qu'un trader expérimenté confirme si les zones détectées
correspondent à sa lecture du graphique.

**Installation** : TradingView → Pine Editor (en bas de l'écran) → coller
le contenu du fichier → "Add to chart".

**Limites à connaître** :
- Le **POC** est calculé par binning manuel sur une fenêtre glissante de
  bougies HTF (paramétrable). Approximation par rapport au Python : chaque
  bougie contribue tout son volume au bin de son prix typique (H+L+C)/3,
  sans distribuer le volume sur son range [low, high] comme le fait le
  backtest (données intrabar non disponibles côté Pine).
- Ce script n'a pas pu être testé dans un compilateur Pine réel dans cet
  environnement (aucun accès à TradingView). S'il y a une erreur de
  compilation au premier collage dans l'éditeur Pine, copiez le message
  d'erreur exact et renvoyez-le pour correction immédiate.
- C'est un outil de **visualisation/aide à la décision**, pas un signal de
  trading autonome — les mêmes réserves que pour le conseiller d'entrée
  Python s'appliquent (edge candidat mais non confirmé à ce jour, voir
  "Recherche de paramètres" et "Avertissement" plus bas).

## Coûts réalistes (slippage + commissions)

Le backtest applique par défaut des coûts de transaction réalistes,
paramétrables dans la section `risk` de la config :
- `slippage_ticks` : slippage défavorable appliqué à **chaque** exécution
  (entrée, chaque sortie partielle/totale) — le fill est toujours pire que
  le niveau théorique visé, jamais meilleur.
- `commission_per_contract` : commission fixe par unité de taille, facturée
  à l'entrée et à chaque sortie (modèle futures — MGC : $/contrat).
- `commission_pct` : commission en % du notionnel (prix x taille), facturée
  à l'entrée et à chaque sortie (modèle crypto perpetual — ex : taker fee
  Binance ~0.05%). Les deux modèles sont cumulables mais un seul est utile
  par actif (l'autre à 0).
- `qty_step` : granularité minimale de la taille de position — `1.0` pour
  des contrats entiers (futures), `0.001` par exemple pour du BTC (la taille
  de position devient alors une quantité fractionnaire, pas un nombre de
  contrats).

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

## Recherche de paramètres (recherche d'edge)

`scripts/parameter_search.py` automatise la recherche systématique d'un jeu
de paramètres qui tient en walk-forward, plutôt que d'ajuster les seuils à la
main. Fonctionnement en 2 étapes pour rester dans un temps de calcul
raisonnable :

1. **Présélection** : toutes les combinaisons d'une grille (seuil
   d'impulsion ATR des order blocks, tolérance de proximité de confluence,
   longueur des swings, mode de take-profit) sont testées avec un backtest
   simple sur une sous-période récente (`--screen-last-days`), et filtrées
   par nombre de trades minimum / profit factor minimum.
2. **Validation** : les meilleurs candidats de l'étape 1 sont ensuite testés
   en walk-forward complet (`validation/walk_forward.py`) sur tout
   l'historique disponible, ce qui donne la métrique qui compte vraiment :
   le profit factor **out-of-sample**.

```bash
python scripts/parameter_search.py --config config/strategy_btc_perp_relaxed_real.yaml \
    --screen-last-days 90 --top-n 3
```

Sur les 19 mois de données BTC réelles disponibles (mars 2024 - juillet
2026, fragmentés), cette recherche (36 combinaisons testées) a fait
émerger deux configurations dont le profit factor walk-forward
out-of-sample dépasse 1.3 avec un échantillon de plus de 100 trades :

| Config | Trades OOS | Win rate | PF net OOS | PnL net OOS | Max DD | Fenêtres profitables |
|---|---|---|---|---|---|---|
| `config/strategy_btc_perp_candidate_a.yaml` | 131 | 38.2% | **1.50** | +3699 $ | -5.71% | 23/35 |
| `config/strategy_btc_perp_candidate_b.yaml` | 126 | 37.3% | **1.34** | +2518 $ | -5.97% | 21/35 |

(Chiffres recalculés le 26/08/2026 après correction d'un bug de tri non
stable — voir la note dans "Avertissement" — sur ~19.5 mois de données
jusqu'au 25/08/2026 ; quasiment identiques aux chiffres d'origine sur 19
mois, ce qui est plutôt rassurant sur la stabilité du résultat.)

Les deux utilisent un objectif unique à RR=3 (pas de scale-out), des swings
"importants" (4 bougies de chaque côté) et un seuil d'impulsion ATR bas
(1.0x) pour les order blocks — cohérent avec la lecture "grands niveaux,
peu de trades, RR élevé" plutôt qu'un scalping à haute fréquence.

**Ces deux résultats sont prometteurs mais ne constituent pas une preuve
d'edge.** Deux biais methodologiques concrets s'appliquent :

- **Biais de sélection** : la présélection (étape 1) porte sur les 90
  derniers jours de l'historique, qui font aussi partie de la fenêtre
  walk-forward complète (étape 2) — le jeu de test n'est donc pas
  totalement indépendant de la sélection.
- **Comparaisons multiples** : 36 combinaisons ont été testées ; avec un
  tel nombre d'essais, retrouver 2-3 combinaisons "correctes" par pur
  hasard reste plausible même sans edge réel sous-jacent.

Avant d'y accorder une réelle confiance : valider sur des données futures
jamais vues pendant cette recherche, et faire confirmer par un trader
expérimenté (les réglages numériques ci-dessus correspondent-ils à une
lecture de marché sensée, ou juste à un ajustement statistique ?). Voir les
commentaires en tête de chaque fichier `candidate_*.yaml` pour le détail.

## Paper trading (suivi en conditions réelles, sans argent)

Cet environnement n'a pas d'accès réseau sortant vers un flux de marché en
direct — impossible d'y faire tourner un bot connecté en continu. À la
place, `scripts/paper_trading_journal.py` s'appuie sur le même workflow que
pour la recherche de données : à chaque nouvel export récent ajouté au
fichier de données (ex. un nouveau mois Binance dans `data/raw/`), relancez
le script.

Il rejoue tout l'historique avec le moteur de backtest existant
(déterministe, sans look-ahead) et ne signale que ce qui est nouveau depuis
le dernier passage : trades réellement clôturés (stop loss ou take profit
touché) et position en cours à surveiller (stop/take profit).

```bash
python scripts/paper_trading_journal.py --config config/strategy_btc_perp_candidate_a.yaml
```

L'état (`paper_trading/state.json`) et l'historique des trades clôturés
(`paper_trading/journal.jsonl`) sont **commités dans le dépôt** (contrairement
à `output/`, régénéré et ignoré par git) car ils doivent survivre d'une
session à l'autre dans cet environnement éphémère — pensez à commit/push
après chaque passage.

> Au 26/08/2026, le fichier de données couvre jusqu'au 25/08/2026 (mois
> d'août complet à ce jour). Le suivi devient statistiquement intéressant à
> mesure que s'accumulent des bougies réelles jamais vues par la recherche
> de paramètres (celle-ci s'est arrêtée sur des données jusqu'à fin juillet
> 2026) — pour l'instant quelques jours seulement, trop peu pour conclure.

> **Important (26/08/2026)** : un bug de tri non stable a été découvert et
> corrigé pendant la mise en place de ce suivi — voir la note dans
> "Avertissement" plus bas. Le journal a été régénéré en entier avec le
> code corrigé ; les entrées commitées avant cette date reflétaient
> potentiellement des trades légèrement différents.

## Scanner de setups A+

`scripts/scan_ap_setups.py` répond à un besoin différent du backtest ou du
paper trading : repérer rapidement, sans tout relire à la main, les setups
à confluence **maximale** (toutes les conditions activées réunies — pas
juste le seuil minimum utilisé pour trader en backtest) sur les deux styles
suivis dans ce projet :

- **Intraday** (`strategy_btc_perp_candidate_a.yaml`, 5min/4h) : score max
  4/4 (sweep + order block + FVG + POC/AVWAP).
- **Swing institutionnel** (`strategy_btc_perp_swing.yaml`, 4h/1D, sans
  FVG, avec confirmation) : score max 4/4 (sweep + order block +
  POC/AVWAP + confirmation).

```bash
python scripts/scan_ap_setups.py --output output/setups_ap.html
```

Génère un rapport HTML autonome (à ouvrir dans un navigateur) avec, pour
chaque style : le statut actuel (setup A+ en cours / biais actif en
attente / rien) et la liste des setups A+ récents (date, direction,
niveaux, tags de confluence). À relancer après chaque ajout de données,
comme le paper trading.

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
conseil en investissement.

Sur 19 mois de données réelles BTC (Binance, mars 2024 - juillet 2026,
fragmentés), une recherche systématique de paramètres (voir "Recherche de
paramètres" ci-dessus) a fait émerger deux configurations dont le profit
factor **out-of-sample** (walk-forward) dépasse 1.3 sur un échantillon de
120+ trades — c'est la première fois, après de nombreux tests précédents
(MGC synthétique, BTC synthétique, BTC réel à 4/9/14 mois) systématiquement
négatifs ou neutres, qu'un résultat de cette ampleur apparaît. C'est un
signal encourageant, **pas une preuve d'edge confirmée** :

- La présélection des candidats a partiellement chevauché la fenêtre de
  test walk-forward (biais de sélection).
- 36 combinaisons ont été testées, ce qui augmente la probabilité de tomber
  sur un résultat positif par hasard (comparaisons multiples).
- Aucune validation n'a encore été faite sur des données strictement
  postérieures à cette recherche, ni de relecture par un trader expérimenté
  pour confirmer que la logique (grands niveaux, RR=3, faible risque) est
  cohérente avec une lecture de marché réelle et pas seulement un
  ajustement statistique.

Les coûts réalistes (slippage, commissions) et la validation walk-forward
sont implémentés et utilisés tout au long de cette recherche pour limiter
le surapprentissage, mais tant que les points ci-dessus ne sont pas
adressés, considérez ces deux configurations comme des **candidats à
tester en conditions réelles (paper trading) avant tout usage avec du
capital réel** — pas comme une stratégie validée.

**Bug corrigé le 26/08/2026** : les modules de détection de patterns
(`patterns/*.py`) triaient leurs résultats par timestamp avec l'algorithme
par défaut de pandas (quicksort), qui n'est pas stable. Quand deux patterns
partageaient exactement le même timestamp (ex. un sweep bullish et un
bearish sur la même bougie HTF), l'ordre retenu entre les deux pouvait
changer selon la taille totale du jeu de données — donc en ajoutant des
données plus récentes, un signal sur une bougie **passée** pouvait changer
rétroactivement, avec un effet en cascade sur les trades suivants. Corrigé
en forçant un tri stable (`kind="stable"`) partout où c'est trié par
timestamp. Les résultats de la recherche de paramètres et des deux
candidats ont été recalculés après correction (voir "Recherche de
paramètres" ci-dessus) : quasiment inchangés, ce qui est rassurant, mais ce
type de bug rappelle qu'un pipeline de backtest doit être traité avec la
même rigueur qu'un logiciel de production, pas juste comme un script
jetable.
