#!/usr/bin/env python3
"""Plot Pattern Forge v2 multi-year JSON scorecard + tape.

Usage:
  python scripts/plot_v2_multi_year.py
  python scripts/plot_v2_multi_year.py --input models/pattern_forge/v2_multi_year.json
  python scripts/plot_v2_multi_year.py --out models/pattern_forge/plots --show
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.gridspec import GridSpec

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "models" / "pattern_forge" / "v2_multi_year.json"
DEFAULT_OUT = ROOT / "models" / "pattern_forge" / "plots"

MONTH_ORDER = [
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
]
MONTH_ABBR = [m[:3].title() for m in MONTH_ORDER]


def load_payload(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def year_returns_df(payload: dict) -> pd.DataFrame:
    df = pd.DataFrame(payload["year_returns"]).copy()
    df["year"] = df["year"].astype(int)
    return df.sort_values("year").reset_index(drop=True)


def years_detail_df(payload: dict) -> pd.DataFrame:
    rows = []
    for yd in payload["years_detail"]:
        row = {k: v for k, v in yd.items() if k != "months"}
        rows.append(row)
    df = pd.DataFrame(rows)
    df["year"] = df["year"].astype(int)
    return df.sort_values("year").reset_index(drop=True)


def months_df(payload: dict) -> pd.DataFrame:
    rows = []
    for yd in payload["years_detail"]:
        year = int(yd["year"])
        for m in yd.get("months", []):
            rows.append(
                {
                    "year": year,
                    "month": str(m["month"]).lower(),
                    "capital_start": float(m["capital_start"]),
                    "capital_end": float(m["capital_end"]),
                    "month_return_pct": float(m["month_return_pct"]),
                    "n_trades": int(m["n_trades"]),
                    "wins": int(m["wins"]),
                }
            )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["month"] = pd.Categorical(df["month"], categories=MONTH_ORDER, ordered=True)
    df["win_rate_pct"] = np.where(
        df["n_trades"] > 0, 100.0 * df["wins"] / df["n_trades"], np.nan
    )
    df["month_pnl"] = df["capital_end"] - df["capital_start"]
    df["ym"] = df["year"].astype(str) + "-" + df["month"].astype(str).str[:3]
    return df.sort_values(["year", "month"]).reset_index(drop=True)


def trades_df(payload: dict) -> pd.DataFrame:
    df = pd.DataFrame(payload.get("trades", [])).copy()
    if df.empty:
        return df
    df["year"] = df["year"].astype(int)
    df["asof"] = pd.to_datetime(df["asof"])
    df["exit_asof"] = pd.to_datetime(df["exit_asof"])
    df["hold_days"] = (df["exit_asof"] - df["asof"]).dt.days
    df["win"] = df["pnl"] > 0
    df["month"] = df["month"].astype(str).str.lower()
    df["month"] = pd.Categorical(df["month"], categories=MONTH_ORDER, ordered=True)
    df = df.sort_values("asof").reset_index(drop=True)
    df["cum_pnl"] = df["pnl"].cumsum()
    return df


def style_axes(ax, title: str, ylabel: str | None = None, xlabel: str | None = None) -> None:
    ax.set_title(title, fontsize=11, pad=8)
    if ylabel:
        ax.set_ylabel(ylabel)
    if xlabel:
        ax.set_xlabel(xlabel)
    ax.grid(True, alpha=0.25, linestyle="--")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def color_bars(values: pd.Series | np.ndarray) -> list[str]:
    return ["#2ca02c" if v >= 0 else "#d62728" for v in values]


def fig_scorecard(payload: dict, yr: pd.DataFrame, yd: pd.DataFrame) -> plt.Figure:
    summary = payload["summary"]
    knobs = payload.get("knobs", {})

    fig = plt.figure(figsize=(16, 10))
    gs = GridSpec(2, 2, figure=fig, height_ratios=[1.1, 1.0], hspace=0.35, wspace=0.28)

    # --- text scorecard ---
    ax0 = fig.add_subplot(gs[0, 0])
    ax0.axis("off")
    lines = [
        f"Strategy: {payload.get('strategy')}  |  lane: {payload.get('lane')}",
        f"Years: {payload.get('years')}  |  start/yr: ₹{payload.get('capital_start_per_year'):,.0f}",
        "",
        f"Trades: {summary['n_trades']:,}   W/L: {summary['wins']}/{summary['losses']}   "
        f"Win rate: {summary['win_rate_pct']:.2f}%",
        f"Sum standalone PnL: ₹{summary['sum_standalone_pnl']:,.2f}",
        f"Mean year return: {summary['mean_year_return_pct']:.2f}%",
        f"Years positive: {summary['years_positive']}/{summary['n_years']}",
        f"Compound end (footnote): ₹{summary['compound_end']:,.2f}  "
        f"({summary['compound_return_pct']:.1f}%)",
        "",
        f"Knobs: lev={knobs.get('leverage')} sleeve={knobs.get('sleeve_frac')} "
        f"top_k={knobs.get('top_k')} min_score={knobs.get('min_score')}",
        f"r1=[{knobs.get('r1_lo')},{knobs.get('r1_hi')}]  "
        f"profit_guard={knobs.get('profit_guard')}@{knobs.get('profit_guard_floor_pct')}%  "
        f"max_daily_loss={knobs.get('max_daily_loss_pct')}%",
        "",
        f"Claim: {payload.get('claim', '')}",
    ]
    ax0.text(
        0.02,
        0.98,
        "\n".join(lines),
        transform=ax0.transAxes,
        va="top",
        ha="left",
        fontsize=9,
        family="monospace",
        wrap=True,
    )
    ax0.set_title("V2 multi-year scorecard", fontsize=12, pad=6)

    # --- yearly return bars ---
    ax1 = fig.add_subplot(gs[0, 1])
    colors = color_bars(yr["return_pct"])
    bars = ax1.bar(yr["year"].astype(str), yr["return_pct"], color=colors, edgecolor="none")
    ax1.axhline(0, color="black", lw=0.8)
    ax1.axhline(
        summary["mean_year_return_pct"],
        color="#1f77b4",
        ls="--",
        lw=1.2,
        label=f"mean {summary['mean_year_return_pct']:.1f}%",
    )
    for b, v in zip(bars, yr["return_pct"]):
        ax1.text(
            b.get_x() + b.get_width() / 2,
            v + (2 if v >= 0 else -4),
            f"{v:.1f}%",
            ha="center",
            va="bottom" if v >= 0 else "top",
            fontsize=8,
        )
    style_axes(ax1, "Standalone year return % (scorecard)", ylabel="Return %")
    ax1.legend(frameon=False, fontsize=8)

    # --- end capital ---
    ax2 = fig.add_subplot(gs[1, 0])
    ax2.bar(yr["year"].astype(str), yr["end_capital"], color="#4c78a8", edgecolor="none")
    ax2.axhline(
        payload["capital_start_per_year"],
        color="#888",
        ls="--",
        lw=1,
        label=f"start ₹{payload['capital_start_per_year']:,.0f}",
    )
    style_axes(ax2, "Standalone end capital by year", ylabel="₹")
    ax2.legend(frameon=False, fontsize=8)

    # --- trades + green months ---
    ax3 = fig.add_subplot(gs[1, 1])
    x = np.arange(len(yr))
    w = 0.38
    ax3.bar(x - w / 2, yr["n_trades"], width=w, color="#72b7b2", label="n_trades")
    ax3.bar(x + w / 2, yr["green_months"], width=w, color="#54a24b", label="green_months")
    if "best_month_pct" in yd.columns:
        ax3b = ax3.twinx()
        ax3b.plot(
            x,
            yd["worst_month_pct"],
            "o-",
            color="#d62728",
            ms=5,
            label="worst month %",
        )
        ax3b.plot(
            x,
            yd["best_month_pct"],
            "o-",
            color="#2ca02c",
            ms=5,
            label="best month %",
        )
        ax3b.set_ylabel("Month return %")
        ax3b.spines["top"].set_visible(False)
        lines1, labels1 = ax3.get_legend_handles_labels()
        lines2, labels2 = ax3b.get_legend_handles_labels()
        ax3.legend(lines1 + lines2, labels1 + labels2, frameon=False, fontsize=8, loc="upper left")
    else:
        ax3.legend(frameon=False, fontsize=8)
    ax3.set_xticks(x)
    ax3.set_xticklabels(yr["year"].astype(str))
    style_axes(ax3, "Trades, green months, best/worst month", ylabel="Count")

    fig.suptitle(
        f"Pattern Forge V2 multi-year  |  {payload.get('ts', '')}",
        fontsize=13,
        y=0.995,
    )
    return fig


def fig_monthly(months: pd.DataFrame, yd: pd.DataFrame) -> plt.Figure:
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    ax_hm, ax_box, ax_curve, ax_pnl = axes.ravel()

    # heatmap of month returns
    pivot = months.pivot(index="year", columns="month", values="month_return_pct")
    pivot = pivot.reindex(columns=MONTH_ORDER)
    data = pivot.to_numpy(dtype=float)
    vmax = np.nanmax(np.abs(data)) if np.isfinite(data).any() else 1.0
    im = ax_hm.imshow(data, aspect="auto", cmap="RdYlGn", vmin=-vmax, vmax=vmax)
    ax_hm.set_xticks(np.arange(len(MONTH_ABBR)))
    ax_hm.set_xticklabels(MONTH_ABBR, fontsize=8)
    ax_hm.set_yticks(np.arange(len(pivot.index)))
    ax_hm.set_yticklabels(pivot.index.astype(int))
    ax_hm.set_title("Monthly return % heatmap (standalone)")
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            val = data[i, j]
            if np.isfinite(val):
                ax_hm.text(j, i, f"{val:.0f}", ha="center", va="center", fontsize=7)
    fig.colorbar(im, ax=ax_hm, fraction=0.046, pad=0.04, label="%")

    # box / strip of monthly returns by year
    years = sorted(months["year"].unique())
    box_data = [months.loc[months["year"] == y, "month_return_pct"].values for y in years]
    bp = ax_box.boxplot(
        box_data, tick_labels=[str(y) for y in years], patch_artist=True
    )
    for patch in bp["boxes"]:
        patch.set_facecolor("#c6dbef")
        patch.set_alpha(0.85)
    ax_box.axhline(0, color="black", lw=0.8)
    style_axes(ax_box, "Monthly return distribution by year", ylabel="Month return %")

    # standalone capital path within each year (reset each Jan)
    for year, g in months.groupby("year", observed=True):
        g = g.sort_values("month")
        xs = list(range(len(g) + 1))
        ys = [float(g.iloc[0]["capital_start"])] + g["capital_end"].tolist()
        ax_curve.plot(xs, ys, marker="o", ms=3, lw=1.4, label=str(year))
    ax_curve.set_xticks(range(13))
    ax_curve.set_xticklabels(["start"] + MONTH_ABBR, rotation=45, ha="right", fontsize=8)
    style_axes(ax_curve, "Intra-year capital (₹10k restart each year)", ylabel="₹")
    ax_curve.legend(frameon=False, fontsize=7, ncol=2)

    # compound capital path (footnote)
    if not yd.empty and "compound_capital_end" in yd.columns:
        years_x = yd["year"].astype(str)
        start = float(yd.iloc[0]["compound_capital_start"])
        compound = [start] + yd["compound_capital_end"].tolist()
        ax_pnl.plot(
            ["start"] + years_x.tolist(),
            compound,
            "o-",
            color="#9467bd",
            lw=2,
            label="compound end",
        )
        ax_pnl.bar(
            years_x,
            yd["year_pnl"],
            color=color_bars(yd["year_pnl"]),
            alpha=0.45,
            label="standalone year PnL",
        )
        style_axes(ax_pnl, "Compound equity (footnote) + standalone year PnL", ylabel="₹")
        ax_pnl.legend(frameon=False, fontsize=8)
        ax_pnl.tick_params(axis="x", rotation=45)
    else:
        ax_pnl.axis("off")

    fig.suptitle("Monthly & compound paths", fontsize=13)
    fig.tight_layout()
    return fig


def fig_trades(trades: pd.DataFrame) -> plt.Figure:
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    ax_hist, ax_cum, ax_yr, ax_tick = axes.ravel()

    if trades.empty:
        for ax in axes.ravel():
            ax.axis("off")
            ax.text(0.5, 0.5, "No trades", ha="center", va="center")
        return fig

    # PnL % histogram
    bins = np.linspace(trades["pnl_pct"].min(), trades["pnl_pct"].max(), 41)
    ax_hist.hist(
        trades.loc[trades["win"], "pnl_pct"],
        bins=bins,
        color="#2ca02c",
        alpha=0.75,
        label="wins",
    )
    ax_hist.hist(
        trades.loc[~trades["win"], "pnl_pct"],
        bins=bins,
        color="#d62728",
        alpha=0.75,
        label="losses",
    )
    ax_hist.axvline(0, color="black", lw=0.8)
    ax_hist.axvline(
        trades["pnl_pct"].mean(),
        color="#1f77b4",
        ls="--",
        label=f"mean {trades['pnl_pct'].mean():.2f}%",
    )
    style_axes(ax_hist, "Trade PnL % distribution", ylabel="Count", xlabel="pnl_pct")
    ax_hist.legend(frameon=False, fontsize=8)

    # cumulative PnL over time
    ax_cum.plot(trades["asof"], trades["cum_pnl"], color="#1f77b4", lw=1.3)
    ax_cum.axhline(0, color="black", lw=0.8)
    ax_cum.fill_between(
        trades["asof"],
        trades["cum_pnl"],
        0,
        where=trades["cum_pnl"] >= 0,
        color="#2ca02c",
        alpha=0.15,
    )
    ax_cum.fill_between(
        trades["asof"],
        trades["cum_pnl"],
        0,
        where=trades["cum_pnl"] < 0,
        color="#d62728",
        alpha=0.15,
    )
    style_axes(ax_cum, "Cumulative trade PnL (chronological)", ylabel="₹")

    # yearly trade stats
    g = trades.groupby("year", as_index=False).agg(
        n_trades=("pnl", "size"),
        wins=("win", "sum"),
        sum_pnl=("pnl", "sum"),
        mean_pnl_pct=("pnl_pct", "mean"),
        fees=("fees", "sum"),
    )
    g["win_rate_pct"] = 100.0 * g["wins"] / g["n_trades"]
    x = np.arange(len(g))
    ax_yr.bar(x, g["sum_pnl"], color=color_bars(g["sum_pnl"]), alpha=0.85, label="sum PnL")
    ax_yr2 = ax_yr.twinx()
    ax_yr2.plot(x, g["win_rate_pct"], "o-", color="#ff7f0e", ms=5, label="win rate %")
    ax_yr2.plot(x, g["mean_pnl_pct"], "s--", color="#17becf", ms=4, label="mean pnl %")
    ax_yr.set_xticks(x)
    ax_yr.set_xticklabels(g["year"].astype(str))
    style_axes(ax_yr, "Trade PnL / win rate by year", ylabel="Sum PnL ₹")
    ax_yr2.set_ylabel("Win rate / mean pnl %")
    lines1, labels1 = ax_yr.get_legend_handles_labels()
    lines2, labels2 = ax_yr2.get_legend_handles_labels()
    ax_yr.legend(lines1 + lines2, labels1 + labels2, frameon=False, fontsize=8)

    # top tickers by sum PnL
    by_t = (
        trades.groupby("ticker", as_index=False)
        .agg(n=("pnl", "size"), sum_pnl=("pnl", "sum"), mean_pnl_pct=("pnl_pct", "mean"))
        .sort_values("sum_pnl", ascending=False)
    )
    top = pd.concat([by_t.head(12), by_t.tail(8)]).drop_duplicates("ticker")
    top = top.sort_values("sum_pnl")
    ax_tick.barh(top["ticker"], top["sum_pnl"], color=color_bars(top["sum_pnl"]))
    style_axes(ax_tick, "Top / bottom tickers by sum PnL", xlabel="Sum PnL ₹")

    fig.suptitle(f"Trades tape  |  n={len(trades):,}", fontsize=13)
    fig.tight_layout()
    return fig


def fig_trade_extras(trades: pd.DataFrame, months: pd.DataFrame) -> plt.Figure:
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    ax_mo, ax_fees, ax_scatter, ax_hold = axes.ravel()

    if trades.empty:
        for ax in axes.ravel():
            ax.axis("off")
        return fig

    # monthly aggregated return from months table (all years stacked)
    mo = (
        months.groupby("month", observed=True)
        .agg(
            mean_ret=("month_return_pct", "mean"),
            median_ret=("month_return_pct", "median"),
            n_trades=("n_trades", "sum"),
            win_rate=("win_rate_pct", "mean"),
        )
        .reindex(MONTH_ORDER)
    )
    ax_mo.bar(
        MONTH_ABBR,
        mo["mean_ret"],
        color=color_bars(mo["mean_ret"].fillna(0)),
        alpha=0.85,
        label="mean month ret %",
    )
    ax_mo.plot(MONTH_ABBR, mo["median_ret"], "o-", color="#1f77b4", label="median")
    ax_mo.axhline(0, color="black", lw=0.8)
    style_axes(ax_mo, "Seasonality: avg month return across years", ylabel="%")
    ax_mo.legend(frameon=False, fontsize=8)

    # fees vs pnl by year
    fy = trades.groupby("year", as_index=False).agg(fees=("fees", "sum"), pnl=("pnl", "sum"))
    x = np.arange(len(fy))
    ax_fees.bar(x - 0.2, fy["pnl"], width=0.4, color=color_bars(fy["pnl"]), label="PnL")
    ax_fees.bar(x + 0.2, -fy["fees"], width=0.4, color="#7f7f7f", label="-fees")
    ax_fees.set_xticks(x)
    ax_fees.set_xticklabels(fy["year"].astype(str))
    ax_fees.axhline(0, color="black", lw=0.8)
    style_axes(ax_fees, "Gross-ish PnL vs fees by year", ylabel="₹")
    ax_fees.legend(frameon=False, fontsize=8)

    # notional vs pnl_pct scatter
    sample = trades
    if len(sample) > 2000:
        sample = sample.sample(2000, random_state=0)
    ax_scatter.scatter(
        sample["entry_notional"],
        sample["pnl_pct"],
        c=np.where(sample["win"], "#2ca02c", "#d62728"),
        alpha=0.35,
        s=18,
        edgecolors="none",
    )
    ax_scatter.axhline(0, color="black", lw=0.8)
    style_axes(
        ax_scatter,
        "Entry notional vs trade pnl %",
        xlabel="entry_notional ₹",
        ylabel="pnl_pct",
    )

    # hold days + monthly win rate heatmap from trades
    hold = trades["hold_days"].value_counts().sort_index()
    ax_hold.bar(hold.index.astype(str), hold.values, color="#4c78a8")
    style_axes(ax_hold, "Hold days distribution", xlabel="days", ylabel="count")

    fig.suptitle("Extras: seasonality, fees, size, hold", fontsize=13)
    fig.tight_layout()
    return fig


def fig_monthly_winrate(months: pd.DataFrame) -> plt.Figure:
    fig, axes = plt.subplots(1, 2, figsize=(16, 5.5))
    ax_hm, ax_trades = axes

    pivot = months.pivot(index="year", columns="month", values="win_rate_pct")
    pivot = pivot.reindex(columns=MONTH_ORDER)
    data = pivot.to_numpy(dtype=float)
    im = ax_hm.imshow(data, aspect="auto", cmap="RdYlGn", vmin=0, vmax=100)
    ax_hm.set_xticks(np.arange(len(MONTH_ABBR)))
    ax_hm.set_xticklabels(MONTH_ABBR, fontsize=8)
    ax_hm.set_yticks(np.arange(len(pivot.index)))
    ax_hm.set_yticklabels(pivot.index.astype(int))
    ax_hm.set_title("Monthly win rate % heatmap")
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            val = data[i, j]
            if np.isfinite(val):
                ax_hm.text(j, i, f"{val:.0f}", ha="center", va="center", fontsize=7)
    fig.colorbar(im, ax=ax_hm, fraction=0.046, pad=0.04, label="win %")

    tp = months.pivot(index="year", columns="month", values="n_trades").reindex(columns=MONTH_ORDER)
    td = tp.to_numpy(dtype=float)
    im2 = ax_trades.imshow(td, aspect="auto", cmap="Blues")
    ax_trades.set_xticks(np.arange(len(MONTH_ABBR)))
    ax_trades.set_xticklabels(MONTH_ABBR, fontsize=8)
    ax_trades.set_yticks(np.arange(len(tp.index)))
    ax_trades.set_yticklabels(tp.index.astype(int))
    ax_trades.set_title("Monthly trade count heatmap")
    for i in range(td.shape[0]):
        for j in range(td.shape[1]):
            val = td[i, j]
            if np.isfinite(val):
                ax_trades.text(j, i, f"{int(val)}", ha="center", va="center", fontsize=7)
    fig.colorbar(im2, ax=ax_trades, fraction=0.046, pad=0.04, label="n_trades")

    fig.suptitle("Monthly activity & hit rate", fontsize=13)
    fig.tight_layout()
    return fig


def save_fig(fig: plt.Figure, path: Path, show: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160, bbox_inches="tight")
    print(f"wrote {path}")
    if show:
        plt.show()
    else:
        plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser(description="Plot v2_multi_year.json")
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--show", action="store_true", help="Show figures interactively")
    args = ap.parse_args()

    payload = load_payload(args.input)
    yr = year_returns_df(payload)
    yd = years_detail_df(payload)
    months = months_df(payload)
    trades = trades_df(payload)

    print(
        f"loaded {args.input}  years={len(yr)}  months={len(months)}  trades={len(trades)}"
    )

    save_fig(fig_scorecard(payload, yr, yd), args.out / "01_scorecard.png", args.show)
    save_fig(fig_monthly(months, yd), args.out / "02_monthly_compound.png", args.show)
    save_fig(fig_trades(trades), args.out / "03_trades.png", args.show)
    save_fig(fig_trade_extras(trades, months), args.out / "04_extras.png", args.show)
    save_fig(fig_monthly_winrate(months), args.out / "05_monthly_heatmaps.png", args.show)

    # also dump tidy CSVs next to plots for reuse
    args.out.mkdir(parents=True, exist_ok=True)
    yr.to_csv(args.out / "year_returns.csv", index=False)
    yd.to_csv(args.out / "years_detail.csv", index=False)
    months.to_csv(args.out / "months.csv", index=False)
    if not trades.empty:
        trades.to_csv(args.out / "trades.csv", index=False)
    print(f"CSVs + PNGs in {args.out}")


if __name__ == "__main__":
    main()
