"""Génération du rapport de backtest : métriques, graphiques, export CSV."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from mgc_backtest.backtest.engine import BacktestResult
from mgc_backtest.reporting.metrics import compute_metrics
from mgc_backtest.reporting.plots import plot_equity_curve, plot_r_distribution
from mgc_backtest.strategy.rules import StrategyConfig


def _trades_to_dataframe(trades: list, risk_cfg) -> pd.DataFrame:
    rows = []
    for t in trades:
        rows.append(
            {
                "id": t.id,
                "direction": t.direction,
                "entry_time": t.entry_time,
                "entry_price": t.entry_price,
                "size": t.size,
                "stop_loss": t.stop_loss,
                "setup_tags": ",".join(sorted(set(t.setup_tags))),
                "score": t.score,
                "num_exits": len(t.exits),
                "exit_time": t.exits[-1].time if t.exits else None,
                "realized_r": t.realized_r(),
                "gross_pnl": t.realized_pnl(risk_cfg.tick_size, risk_cfg.tick_value),
                "commission": t.total_commission(risk_cfg.commission_per_contract, risk_cfg.commission_pct),
                "net_pnl": t.net_pnl(
                    risk_cfg.tick_size, risk_cfg.tick_value, risk_cfg.commission_per_contract, risk_cfg.commission_pct
                ),
                "win": t.is_win(),
            }
        )
    return pd.DataFrame(rows)


def _format_summary(metrics: dict) -> str:
    lines = [
        "=== Résumé du backtest ===",
        f"Trades              : {metrics['num_trades']}",
        f"Win rate (net)      : {metrics['win_rate_pct']:.1f}%  (brut, avant commissions : {metrics['win_rate_gross_pct']:.1f}%)",
        f"R moyen réalisé      : {metrics['avg_r_realized']:.2f}",
        f"Profit factor (net) : {metrics['profit_factor']:.2f}  (brut : {metrics['profit_factor_gross']:.2f})",
        f"PnL net             : {metrics['net_pnl']:.2f} $  (brut : {metrics['gross_pnl']:.2f} $)",
        f"Commissions totales : {metrics['total_commission']:.2f} $",
        f"Capital final       : {metrics['final_equity']:.2f} $",
        f"Max drawdown        : {metrics['max_drawdown_pct']:.2f}% ({metrics['max_drawdown_abs']:.2f} $)",
        "",
        "Win rate par direction :",
    ]
    for k, v in metrics["per_direction"].items():
        lines.append(f"  {k:10s} n={v['count']:4d}  win_rate={v['win_rate_pct']:.1f}%")
    lines.append("")
    lines.append("Win rate par tag de setup :")
    for k, v in metrics["per_setup_tag"].items():
        lines.append(f"  {k:15s} n={v['count']:4d}  win_rate={v['win_rate_pct']:.1f}%")
    return "\n".join(lines)


def generate_report(result: BacktestResult, config: StrategyConfig, output_dir: str | Path) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    metrics = compute_metrics(result.trades, result.equity_curve, config.risk)

    trades_df = _trades_to_dataframe(result.trades, config.risk)
    trades_df.to_csv(output_dir / "trades.csv", index=False)

    plot_equity_curve(result.equity_curve, output_dir / "equity_curve.png")
    plot_r_distribution(result.trades, output_dir / "r_distribution.png")

    summary_text = _format_summary(metrics)
    (output_dir / "summary.txt").write_text(summary_text + "\n")

    print(summary_text)
    print(f"\nRapport écrit dans : {output_dir}/")

    return metrics
