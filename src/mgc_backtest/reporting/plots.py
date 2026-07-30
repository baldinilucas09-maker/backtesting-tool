"""Graphiques de reporting : courbe d'equity et distribution des trades."""

from __future__ import annotations

from pathlib import Path

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def plot_equity_curve(equity: pd.Series, save_path: str | Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 5))
    equity.plot(ax=ax, color="#1f77b4", linewidth=1.5)
    ax.set_title("Courbe d'equity")
    ax.set_xlabel("Date")
    ax.set_ylabel("Capital ($)")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(save_path, dpi=120)
    plt.close(fig)


def plot_r_distribution(trades: list, save_path: str | Path) -> None:
    rs = [t.realized_r() for t in trades]
    fig, ax = plt.subplots(figsize=(8, 5))
    if rs:
        ax.hist(rs, bins=20, color="#2ca02c", edgecolor="white")
    ax.axvline(0, color="black", linewidth=1)
    ax.set_title("Distribution des R réalisés par trade")
    ax.set_xlabel("R multiple")
    ax.set_ylabel("Nombre de trades")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(save_path, dpi=120)
    plt.close(fig)
