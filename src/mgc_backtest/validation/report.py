"""Rapport de validation walk-forward : tableau par fenêtre, métriques
out-of-sample agrégées, indicateur de surapprentissage (in-sample vs
out-of-sample)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from mgc_backtest.reporting.plots import plot_equity_curve
from mgc_backtest.validation.walk_forward import WalkForwardReport


def _folds_to_dataframe(report: WalkForwardReport) -> pd.DataFrame:
    rows = []
    for f in report.folds:
        rows.append(
            {
                "fold": f.fold_index,
                "train_start": f.train_start,
                "train_end": f.train_end,
                "test_start": f.test_start,
                "test_end": f.test_end,
                "chosen_min_score": f.chosen_min_score,
                "train_trades": f.train_metrics.get("num_trades", 0),
                "train_win_rate_pct": f.train_metrics.get("win_rate_pct", 0.0),
                "train_profit_factor": f.train_metrics.get("profit_factor", 0.0),
                "train_net_pnl": f.train_metrics.get("net_pnl", 0.0),
                "test_trades": f.test_metrics.get("num_trades", 0),
                "test_win_rate_pct": f.test_metrics.get("win_rate_pct", 0.0),
                "test_profit_factor": f.test_metrics.get("profit_factor", 0.0),
                "test_net_pnl": f.test_metrics.get("net_pnl", 0.0),
            }
        )
    return pd.DataFrame(rows)


_PF_CAP = 10.0  # plafond appliqué aux profit factors infinis (0 perte) pour que les moyennes restent lisibles


def _finite_mean_pf(series: pd.Series) -> float:
    if series.empty:
        return 0.0
    capped = series.replace([float("inf")], _PF_CAP)
    return float(capped.mean())


def _format_summary(report: WalkForwardReport, folds_df: pd.DataFrame) -> str:
    n_folds = len(report.folds)
    n_with_trades = int((folds_df["test_trades"] > 0).sum()) if n_folds else 0
    n_profitable = int((folds_df["test_net_pnl"] > 0).sum()) if n_folds else 0
    avg_train_pf = _finite_mean_pf(folds_df.loc[folds_df["train_trades"] > 0, "train_profit_factor"]) if n_folds else 0.0
    avg_test_pf = _finite_mean_pf(folds_df.loc[folds_df["test_trades"] > 0, "test_profit_factor"]) if n_folds else 0.0

    pooled = report.pooled_test_metrics
    lines = [
        "=== Validation walk-forward (out-of-sample) ===",
        f"Fenêtres testées         : {n_folds}",
        f"Fenêtres avec des trades : {n_with_trades}",
        f"Fenêtres profitables (OOS) : {n_profitable}/{n_with_trades if n_with_trades else n_folds}",
        "",
        "--- Performance agrégée out-of-sample (tous les folds combinés) ---",
        f"Trades              : {pooled['num_trades']}",
        f"Win rate (net)      : {pooled['win_rate_pct']:.1f}%",
        f"Profit factor (net) : {pooled['profit_factor']:.2f}",
        f"PnL net             : {pooled['net_pnl']:.2f} $",
        f"Max drawdown        : {pooled['max_drawdown_pct']:.2f}% ({pooled['max_drawdown_abs']:.2f} $)",
        "",
        "--- Indicateur de surapprentissage ---",
        f"Profit factor moyen in-sample (train)  : {avg_train_pf:.2f}",
        f"Profit factor moyen out-of-sample (test): {avg_test_pf:.2f}",
    ]
    if avg_train_pf > 0 and avg_test_pf < avg_train_pf * 0.5:
        lines.append(
            "ATTENTION : le profit factor out-of-sample est nettement inférieur à l'in-sample "
            "-> signe probable de surapprentissage (le paramètre choisi sur le train ne généralise pas)."
        )
    if pooled["num_trades"] < 30:
        lines.append(
            f"ATTENTION : seulement {pooled['num_trades']} trades out-of-sample au total -> "
            f"échantillon trop faible pour tirer une conclusion statistique fiable (visez plusieurs centaines)."
        )
    return "\n".join(lines)


def generate_walk_forward_report(report: WalkForwardReport, output_dir: str | Path) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    folds_df = _folds_to_dataframe(report)
    folds_df.to_csv(output_dir / "walk_forward_folds.csv", index=False)

    if not report.pooled_test_equity.empty:
        plot_equity_curve(report.pooled_test_equity, output_dir / "walk_forward_oos_equity.png")

    summary_text = _format_summary(report, folds_df)
    (output_dir / "walk_forward_summary.txt").write_text(summary_text + "\n")

    print(summary_text)
    print(f"\nRapport walk-forward écrit dans : {output_dir}/")

    return report.pooled_test_metrics
