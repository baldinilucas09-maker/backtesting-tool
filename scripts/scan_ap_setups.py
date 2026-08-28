#!/usr/bin/env python3
"""Scanner de setups A+ : repère rapidement les setups à confluence
MAXIMALE (toutes les conditions activées réunies, pas juste le seuil
minimum utilisé pour trader) sur les deux styles suivis dans ce projet —
intraday (5min/4h, ``candidate_a``) et swing façon institutionnelle (4h/1D,
sans FVG, avec confirmation).

Un setup "A+" ici = score de confluence == score maximum possible pour la
config (toutes les conditions activées sont réunies), pas seulement le
``min_score`` utilisé pour déclencher un trade en backtest — c'est
volontairement plus strict, pensé pour repérer les meilleurs setups
rapidement plutôt que tout signal tradable.

Génère un rapport HTML autonome (aucune dépendance externe) résumant, pour
chaque style : le statut actuel (setup A+ en cours, biais actif en attente,
ou rien), et les setups A+ des N derniers jours avec leurs niveaux
d'entrée/stop/take-profits.

Usage :
    python scripts/scan_ap_setups.py --output /tmp/setups_ap.html
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mgc_backtest.advisor import evaluate_entry_advice  # noqa: E402
from mgc_backtest.data.loader import load_ohlcv_csv  # noqa: E402
from mgc_backtest.data.resampler import resample_ohlcv  # noqa: E402
from mgc_backtest.strategy.rules import StrategyConfig  # noqa: E402
from mgc_backtest.strategy.signals import generate_signals  # noqa: E402

STYLES = [
    {
        "key": "intraday",
        "label": "Intraday (5min / 4h)",
        "config": "config/strategy_btc_perp_candidate_a.yaml",
        "lookback_days": 45,
    },
    {
        "key": "swing",
        "label": "Swing institutionnel (4h / 1D, sans FVG)",
        "config": "config/strategy_btc_perp_swing.yaml",
        "lookback_days": 270,
    },
]


def _max_score(config: StrategyConfig) -> int:
    return sum(1 for v in config.confluence.required.values() if v)


def _analyze(style: dict) -> dict:
    config = StrategyConfig.from_yaml(style["config"])
    df_ltf = load_ohlcv_csv(config.data.raw_file, timezone=config.data.timezone)
    df_htf = resample_ohlcv(df_ltf, config.timeframes.htf)

    max_score = _max_score(config)
    advice = evaluate_entry_advice(df_ltf, df_htf, config)

    all_signals = generate_signals(df_ltf, df_htf, config)
    cutoff = df_ltf.index[-1] - __import__("pandas").Timedelta(days=style["lookback_days"])
    ap_signals = [s for s in all_signals if s.score == max_score and s.time >= cutoff]
    ap_signals.sort(key=lambda s: s.time, reverse=True)

    return {
        "style": style,
        "max_score": max_score,
        "advice": advice,
        "ap_signals": ap_signals,
        "last_bar_time": df_ltf.index[-1],
    }


def _fmt_setups_rows(ap_signals: list, max_score: int) -> str:
    if not ap_signals:
        return '<p class="empty">Aucun setup A+ sur la période analysée.</p>'
    rows = []
    for s in ap_signals:
        dir_class = "long" if s.direction == "long" else "short"
        dir_label = "LONG" if s.direction == "long" else "SHORT"
        tags = ", ".join(sorted(set(s.setup_tags)))
        rows.append(
            f'<tr><td>{s.time:%Y-%m-%d %H:%M} UTC</td>'
            f'<td><span class="badge {dir_class}">{dir_label}</span></td>'
            f'<td>{s.entry_price:,.2f}</td>'
            f'<td>{s.score}/{max_score}</td>'
            f'<td class="tags">{tags}</td></tr>'
        )
    return (
        '<table><thead><tr><th>Date</th><th>Direction</th><th>Prix signal</th>'
        '<th>Score</th><th>Confluence</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table>"
    )


def _status_card(result: dict) -> str:
    advice = result["advice"]
    max_score = result["max_score"]
    if advice.signal_fired and advice.score == max_score:
        status_class, status_label = "status-ap", "SETUP A+ EN COURS"
    elif advice.signal_fired:
        status_class, status_label = "status-ok", f"Setup tradable ({advice.score}/{max_score})"
    elif advice.direction is not None:
        status_class, status_label = "status-wait", f"Biais {advice.direction.upper()} actif, en attente ({advice.score}/{max_score})"
    else:
        status_class, status_label = "status-none", "Aucun biais actif"

    detail = advice.message.replace("\n", "<br>")
    return f'<div class="status {status_class}"><div class="status-label">{status_label}</div><div class="status-detail">{detail}</div></div>'


def build_html(results: list) -> str:
    sections = []
    for r in results:
        style = r["style"]
        sections.append(
            f'''
            <section>
              <h2>{style["label"]}</h2>
              <p class="meta">Données à jour jusqu'à {r["last_bar_time"]:%Y-%m-%d %H:%M} UTC &middot; setups A+ des {style["lookback_days"]} derniers jours</p>
              {_status_card(r)}
              <h3>Setups A+ récents ({len(r["ap_signals"])})</h3>
              {_fmt_setups_rows(r["ap_signals"], r["max_score"])}
            </section>
            '''
        )

    return f'''<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Setups A+ — BTC</title>
<style>
  :root {{
    --bg: #0f1115; --card: #171a21; --border: #2a2f3a; --text: #e6e8eb;
    --muted: #9aa2af; --long: #34d399; --short: #f87171;
    --ap: #34d399; --ok: #60a5fa; --wait: #fbbf24; --none: #6b7280;
  }}
  @media (prefers-color-scheme: light) {{
    :root {{
      --bg: #f7f8fa; --card: #ffffff; --border: #e2e5ea; --text: #16181d;
      --muted: #5b6370;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; padding: 24px; background: var(--bg); color: var(--text);
         font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
  h1 {{ font-size: 1.4rem; margin: 0 0 4px; }}
  .subtitle {{ color: var(--muted); margin: 0 0 24px; font-size: 0.9rem; }}
  section {{ background: var(--card); border: 1px solid var(--border); border-radius: 12px;
            padding: 20px; margin-bottom: 20px; }}
  h2 {{ margin: 0 0 4px; font-size: 1.1rem; }}
  h3 {{ margin: 20px 0 10px; font-size: 0.95rem; color: var(--muted); }}
  .meta {{ color: var(--muted); font-size: 0.82rem; margin: 0 0 16px; }}
  .status {{ border-radius: 10px; padding: 14px 16px; border: 1px solid var(--border); }}
  .status-label {{ font-weight: 600; margin-bottom: 6px; }}
  .status-detail {{ font-size: 0.85rem; color: var(--muted); line-height: 1.5; }}
  .status-ap {{ border-color: var(--ap); }}
  .status-ap .status-label {{ color: var(--ap); }}
  .status-ok {{ border-color: var(--ok); }}
  .status-ok .status-label {{ color: var(--ok); }}
  .status-wait {{ border-color: var(--wait); }}
  .status-wait .status-label {{ color: var(--wait); }}
  .status-none .status-label {{ color: var(--none); }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
  th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--border); }}
  th {{ color: var(--muted); font-weight: 500; font-size: 0.78rem; text-transform: uppercase; }}
  .badge {{ padding: 2px 8px; border-radius: 6px; font-size: 0.75rem; font-weight: 600; }}
  .badge.long {{ background: rgba(52,211,153,0.15); color: var(--long); }}
  .badge.short {{ background: rgba(248,113,113,0.15); color: var(--short); }}
  .tags {{ color: var(--muted); }}
  .empty {{ color: var(--muted); font-size: 0.85rem; }}
</style>
</head>
<body>
  <h1>Setups A+ — BTC Perpetual</h1>
  <p class="subtitle">Confluence maximale uniquement (toutes les conditions réunies) — régénère ce rapport après chaque ajout de données.</p>
  {"".join(sections)}
</body>
</html>'''


def main() -> None:
    parser = argparse.ArgumentParser(description="Scanner de setups A+ (confluence maximale) intraday + swing")
    parser.add_argument("--output", default="output/setups_ap.html")
    args = parser.parse_args()

    results = [_analyze(style) for style in STYLES]

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_html(results))

    for r in results:
        print(f"{r['style']['label']}: {len(r['ap_signals'])} setup(s) A+ sur {r['style']['lookback_days']}j, "
              f"statut actuel = {r['advice'].score}/{r['max_score']}")
    print(f"\nRapport écrit dans : {output_path}")


if __name__ == "__main__":
    main()
