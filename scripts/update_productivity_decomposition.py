#!/usr/bin/env python3
"""Build summary and quarterly labor-productivity decomposition outputs.

Outputs:
- productivity_decomposition_summary.png / .csv
- productivity_decomposition_quarterly.png / .csv
- productivity_decomposition_bridge.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np
import pandas as pd

from reproduce_tfp_decomposition import (
    build_period_table,
    load_quarterly_data,
    plot_decomposition,
)
from sf_tfp_data import DEFAULT_WORKBOOK_PATH, prepare_workbook

RECESSIONS = [
    ("1990Q3", "1991Q1"),
    ("2001Q1", "2001Q4"),
    ("2007Q4", "2009Q2"),
    ("2020Q1", "2020Q2"),
]

COLORS = {
    "tfp": "#2E6F9E",
    "capital": "#F28E2B",
    "labor": "#59A14F",
    "recession": "#E6E6E6",
    "axis": "#333333",
    "grid": "#B8B8B8",
}

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
OUTPUT_DIR = REPO_ROOT / "output"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_WORKBOOK_PATH,
        help="Path to the SF Fed quarterly_tfp workbook.",
    )
    parser.add_argument(
        "--refresh-data",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Download the latest workbook from the SF Fed before building outputs (default: enabled).",
    )
    parser.add_argument(
        "--output-prefix",
        type=Path,
        default=OUTPUT_DIR / "productivity_decomposition",
        help="Output prefix for the summary, quarterly, and bridge files.",
    )
    parser.add_argument(
        "--latest-start",
        default="2023Q1",
        help="Start quarter for the last summary bar and bridge table (default: 2023Q1).",
    )
    parser.add_argument(
        "--rolling-quarters",
        type=int,
        default=4,
        help="Rolling window in quarters for the quarterly chart.",
    )
    parser.add_argument(
        "--start-year",
        type=int,
        default=1985,
        help="First year shown in the quarterly chart.",
    )
    return parser.parse_args()


def build_quarterly_table(
    q: pd.DataFrame,
    rolling_quarters: int = 4,
    start_year: int = 1985,
) -> pd.DataFrame:
    out = q.copy()
    for column in ["tfp", "capital_deepening", "labor_composition", "total_lp"]:
        out[f"{column}_roll{rolling_quarters}"] = out[column].rolling(rolling_quarters).mean()

    out = out[out["period"].dt.year >= start_year].copy()
    out = out.dropna(
        subset=[
            f"tfp_roll{rolling_quarters}",
            f"capital_deepening_roll{rolling_quarters}",
            f"labor_composition_roll{rolling_quarters}",
            f"total_lp_roll{rolling_quarters}",
        ]
    )

    return out[
        [
            "date",
            "period",
            "x",
            f"tfp_roll{rolling_quarters}",
            f"capital_deepening_roll{rolling_quarters}",
            f"labor_composition_roll{rolling_quarters}",
            f"total_lp_roll{rolling_quarters}",
        ]
    ].rename(
        columns={
            f"tfp_roll{rolling_quarters}": "tfp",
            f"capital_deepening_roll{rolling_quarters}": "capital_deepening",
            f"labor_composition_roll{rolling_quarters}": "labor_composition",
            f"total_lp_roll{rolling_quarters}": "total_lp",
        }
    ).reset_index(drop=True)


def build_bridge_table(q: pd.DataFrame, recent_start: str = "2023Q1") -> pd.DataFrame:
    start_period = pd.Period(recent_start, freq="Q-DEC")
    subset = q[q["period"] >= start_period].copy()
    latest_period = subset["period"].max()

    rows = [
        {
            "measure": "Raw capital per hour growth (dk - dhours)",
            "average_annual_rate": subset["raw_capital_per_hour_growth"].mean(),
        },
        {
            "measure": "Capital deepening contribution",
            "average_annual_rate": subset["capital_deepening"].mean(),
        },
        {
            "measure": "Labor composition",
            "average_annual_rate": subset["labor_composition"].mean(),
        },
        {
            "measure": "TFP (unadjusted)",
            "average_annual_rate": subset["tfp"].mean(),
        },
        {
            "measure": "TFP (utilization-adjusted)",
            "average_annual_rate": subset["tfp_util_adjusted"].mean(),
        },
        {
            "measure": "Utilization",
            "average_annual_rate": subset["utilization"].mean(),
        },
        {
            "measure": "Total labor productivity growth",
            "average_annual_rate": subset["total_lp"].mean(),
        },
    ]
    bridge_df = pd.DataFrame(rows)
    bridge_df["window_start"] = str(start_period)
    bridge_df["window_end"] = str(latest_period)
    bridge_df["n_quarters"] = int(subset.shape[0])
    return bridge_df[
        ["window_start", "window_end", "n_quarters", "measure", "average_annual_rate"]
    ]


def style_axis(ax: plt.Axes) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(COLORS["axis"])
    ax.spines["bottom"].set_color(COLORS["axis"])
    ax.tick_params(colors=COLORS["axis"])
    ax.grid(axis="y", linestyle=":", linewidth=0.8, color=COLORS["grid"], alpha=0.9)


def plot_quarterly(
    quarterly_df: pd.DataFrame,
    output_png: Path,
    start_year: int = 1985,
) -> None:
    fig = plt.figure(figsize=(12.8, 6.8))
    ax = fig.add_axes([0.08, 0.12, 0.86, 0.75])

    for start, end in RECESSIONS:
        start_period = pd.Period(start, freq="Q-DEC")
        end_period = pd.Period(end, freq="Q-DEC")
        x0 = quarterly_df.loc[quarterly_df["period"] == start_period, "x"]
        x1 = quarterly_df.loc[quarterly_df["period"] == end_period, "x"]
        if x0.empty or x1.empty:
            continue
        ax.axvspan(float(x0.iloc[0]) - 0.125, float(x1.iloc[0]) + 0.125, color=COLORS["recession"], zorder=0)

    bar_width = 0.075
    x = quarterly_df["x"].to_numpy()
    ax.bar(
        x - bar_width,
        quarterly_df["tfp"],
        width=bar_width,
        color=COLORS["tfp"],
        edgecolor=COLORS["tfp"],
        linewidth=0.3,
        zorder=3,
    )
    ax.bar(
        x,
        quarterly_df["capital_deepening"],
        width=bar_width,
        color=COLORS["capital"],
        edgecolor=COLORS["capital"],
        linewidth=0.3,
        zorder=3,
    )
    ax.bar(
        x + bar_width,
        quarterly_df["labor_composition"],
        width=bar_width,
        color=COLORS["labor"],
        edgecolor=COLORS["labor"],
        linewidth=0.3,
        zorder=3,
    )

    ax.axhline(0, color=COLORS["axis"], linewidth=1.1, zorder=2)
    ax.set_xlim(start_year - 0.5, quarterly_df["period"].dt.year.max() + 0.8)
    ax.set_ylim(-4.8, 8.6)
    ax.set_xticks(np.arange(start_year, quarterly_df["period"].dt.year.max() + 1, 5))
    ax.set_yticks([-4, 0, 4, 8])
    ax.set_title(
        "Quarterly decomposition of U.S. output per hour growth\n(4-quarter average, annual rate)",
        fontsize=14,
        pad=8,
    )
    ax.set_ylabel("Percent")
    style_axis(ax)

    handles = [
        Patch(facecolor=COLORS["tfp"], label="TFP"),
        Patch(facecolor=COLORS["capital"], label="Capital deepening"),
        Patch(facecolor=COLORS["labor"], label="Labor composition"),
    ]
    ax.legend(handles=handles, frameon=False, loc="upper left", fontsize=11)

    output_png.parent.mkdir(parents=True, exist_ok=True)
    fig.text(
        0.01,
        0.01,
        "Source: SF Fed workbook; author’s calculations. Shaded areas are NBER recessions.",
        fontsize=9,
    )
    fig.savefig(output_png, dpi=220, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    args = parse_args()
    input_path = prepare_workbook(args.input, refresh_data=args.refresh_data)

    q = load_quarterly_data(input_path)
    period_df = build_period_table(q, latest_start=args.latest_start)
    quarterly_df = build_quarterly_table(
        q,
        rolling_quarters=args.rolling_quarters,
        start_year=args.start_year,
    )
    bridge_df = build_bridge_table(q, recent_start=args.latest_start)

    summary_png = args.output_prefix.with_name(args.output_prefix.name + "_summary.png")
    summary_csv = args.output_prefix.with_name(args.output_prefix.name + "_summary.csv")
    quarterly_png = args.output_prefix.with_name(args.output_prefix.name + "_quarterly.png")
    quarterly_csv = args.output_prefix.with_name(args.output_prefix.name + "_quarterly.csv")
    bridge_csv = args.output_prefix.with_name(args.output_prefix.name + "_bridge.csv")

    for path in [summary_png, summary_csv, quarterly_png, quarterly_csv, bridge_csv]:
        path.parent.mkdir(parents=True, exist_ok=True)

    period_df.to_csv(summary_csv, index=False)
    quarterly_df.to_csv(quarterly_csv, index=False)
    bridge_df.to_csv(bridge_csv, index=False)

    plot_decomposition(period_df, summary_png)
    plot_quarterly(quarterly_df, quarterly_png, start_year=args.start_year)

    latest_available = q["period"].max()
    print(f"Latest quarter in workbook: {latest_available}")
    print(f"Wrote {summary_png}")
    print(f"Wrote {summary_csv}")
    print(f"Wrote {quarterly_png}")
    print(f"Wrote {quarterly_csv}")
    print(f"Wrote {bridge_csv}")


if __name__ == "__main__":
    main()
