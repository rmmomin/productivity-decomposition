#!/usr/bin/env python3
"""Plot quarterly labor-productivity growth drivers from the Fernald workbook.

This version removes external branding and uses the same restrained visual
style as the TFP decomposition chart in this repo.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Sequence

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

RECESSIONS = [
    (pd.Period("1990Q3", freq="Q-DEC"), pd.Period("1991Q1", freq="Q-DEC")),
    (pd.Period("2001Q1", freq="Q-DEC"), pd.Period("2001Q4", freq="Q-DEC")),
    (pd.Period("2007Q4", freq="Q-DEC"), pd.Period("2009Q2", freq="Q-DEC")),
    (pd.Period("2020Q1", freq="Q-DEC"), pd.Period("2020Q2", freq="Q-DEC")),
]

COLORS = {
    "tfp": "#1f77b4",
    "util": "#2ca02c",
    "cap": "#ff7f0e",
    "recession": "#e6e6e6",
}

QUARTER_RE = re.compile(r"^(\d{4}):Q([1-4])$")
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
OUTPUT_DIR = REPO_ROOT / "output"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/quarterly_tfp.xlsx"),
        help="Path to the Fernald quarterly_tfp workbook.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_DIR / "productivity_growth_drivers.png",
        help="Output image path.",
    )
    parser.add_argument(
        "--export-data",
        type=Path,
        default=None,
        help="CSV path for the plotted data. Defaults to the output path with a .csv suffix.",
    )
    parser.add_argument(
        "--sheet",
        default="quarterly",
        help="Workbook sheet with Fernald quarterly data.",
    )
    parser.add_argument(
        "--capital-mode",
        choices=("raw", "contribution"),
        default="raw",
        help=(
            "'raw' plots dk - dhours; 'contribution' plots "
            "alpha*(dk-dhours) + (1-alpha)*dLQ."
        ),
    )
    parser.add_argument(
        "--rolling-quarters",
        type=int,
        default=4,
        help="Rolling window in quarters.",
    )
    parser.add_argument(
        "--start-year",
        type=int,
        default=1985,
        help="First year to show on the x-axis.",
    )
    parser.add_argument(
        "--end-year",
        type=int,
        default=None,
        help="Optional last year to show on the x-axis.",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=200,
        help="Image DPI.",
    )
    return parser.parse_args()


def resolve_input_path(path: Path) -> Path:
    if path.exists():
        return path
    candidate = REPO_ROOT / path
    if candidate.exists():
        return candidate
    return path


def quarter_to_period(value: str) -> pd.Period | None:
    match = QUARTER_RE.match(str(value).strip())
    if not match:
        return None
    year, quarter = match.groups()
    return pd.Period(f"{year}Q{quarter}", freq="Q-DEC")


def period_to_year_float(period: pd.Period) -> float:
    return period.year + (period.quarter - 1) / 4.0


def load_quarterly_data(xlsx_path: Path, sheet_name: str = "quarterly") -> pd.DataFrame:
    df = pd.read_excel(xlsx_path, sheet_name=sheet_name, header=1)
    if "date" not in df.columns:
        raise ValueError(f"Could not find a 'date' column in sheet '{sheet_name}': {xlsx_path}")

    df["period"] = df["date"].apply(quarter_to_period)
    df = df[df["period"].notna()].copy()
    df.sort_values("period", inplace=True)
    df.reset_index(drop=True, inplace=True)

    # Fernald data are already annualized quarterly growth rates, so a
    # rolling mean across 4 quarters approximates a 4-quarter growth rate.
    df["capital_deepening_raw"] = df["dk"] - df["dhours"]
    df["capital_deepening_contribution"] = (
        df["alpha"] * (df["dk"] - df["dhours"]) + (1.0 - df["alpha"]) * df["dLQ"]
    )
    df["x"] = df["period"].apply(period_to_year_float)
    return df


def add_rolling_growth(df: pd.DataFrame, columns: Sequence[str], window: int) -> pd.DataFrame:
    out = df.copy()
    for column in columns:
        out[f"{column}_roll{window}"] = out[column].rolling(window).mean()
    return out


def shade_recessions(ax: plt.Axes) -> None:
    for start, end in RECESSIONS:
        x0 = period_to_year_float(start) - 0.125
        x1 = period_to_year_float(end) + 0.125
        ax.axvspan(x0, x1, color=COLORS["recession"], alpha=0.9, zorder=0)


def build_plot_data(
    data: pd.DataFrame,
    capital_mode: str,
    window: int,
    start_year: int,
    end_year: int | None,
) -> pd.DataFrame:
    tfp_col = f"dtfp_util_roll{window}"
    util_col = f"dutil_roll{window}"
    cap_col = (
        f"capital_deepening_raw_roll{window}"
        if capital_mode == "raw"
        else f"capital_deepening_contribution_roll{window}"
    )

    plot_df = data[["period", "x", tfp_col, util_col, cap_col]].copy()
    plot_df.rename(
        columns={
            tfp_col: "tfp_growth",
            util_col: "utilization_growth",
            cap_col: "capital_deepening",
        },
        inplace=True,
    )
    plot_df = plot_df[plot_df["period"].dt.year >= start_year].copy()
    if end_year is not None:
        plot_df = plot_df[plot_df["period"].dt.year <= end_year].copy()
    plot_df.dropna(
        subset=["tfp_growth", "utilization_growth", "capital_deepening"],
        inplace=True,
    )

    if plot_df.empty:
        raise ValueError("No data left to plot after applying the date filters.")

    return plot_df


def plot_productivity_chart(
    plot_df: pd.DataFrame,
    output_path: Path,
    capital_mode: str,
    dpi: int,
) -> None:
    fig, ax = plt.subplots(figsize=(12.0, 5.8))

    shade_recessions(ax)

    bar_width = 0.07
    x = plot_df["x"].to_numpy()
    ax.bar(
        x - bar_width,
        plot_df["tfp_growth"],
        width=bar_width,
        color=COLORS["tfp"],
        label="TFP growth",
        zorder=3,
    )
    ax.bar(
        x,
        plot_df["utilization_growth"],
        width=bar_width,
        color=COLORS["util"],
        label="Utilization growth",
        zorder=3,
    )
    ax.bar(
        x + bar_width,
        plot_df["capital_deepening"],
        width=bar_width,
        color=COLORS["cap"],
        label="Capital deepening" if capital_mode == "raw" else "Capital deepening contribution",
        zorder=3,
    )

    xmin = np.floor(plot_df["x"].min()) - 0.5
    xmax = np.ceil(plot_df["x"].max()) + 0.5
    y_values = plot_df[["tfp_growth", "utilization_growth", "capital_deepening"]].to_numpy().ravel()
    ymax = max(0.0, float(np.nanmax(y_values))) + 0.6
    ymin = min(0.0, float(np.nanmin(y_values))) - 0.6

    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.set_xticks(np.arange(int(np.ceil(xmin)), int(np.floor(xmax)) + 1, 5))
    ax.set_ylabel("Percent (annual rate)")
    ax.set_title("Quarterly drivers of U.S. labor productivity growth")
    ax.axhline(0, color="#333333", linewidth=0.9, zorder=2)
    ax.grid(axis="y", linestyle=":", linewidth=0.6)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)

    ax.legend(
        ncols=3,
        frameon=False,
        loc="upper center",
        bbox_to_anchor=(0.5, 1.02),
        borderaxespad=0.0,
    )

    fig.text(
        0.01,
        0.01,
        "Source: SF Fed quarterly TFP workbook; shaded bars denote NBER recessions.",
        ha="left",
        va="bottom",
        fontsize=9,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=[0, 0.04, 1, 1])
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    args = parse_args()
    input_path = resolve_input_path(args.input)
    export_path = args.export_data if args.export_data is not None else args.output.with_suffix(".csv")

    df = load_quarterly_data(input_path, sheet_name=args.sheet)
    df = add_rolling_growth(
        df,
        columns=[
            "dtfp_util",
            "dutil",
            "capital_deepening_raw",
            "capital_deepening_contribution",
        ],
        window=args.rolling_quarters,
    )

    plot_df = build_plot_data(
        data=df,
        capital_mode=args.capital_mode,
        window=args.rolling_quarters,
        start_year=args.start_year,
        end_year=args.end_year,
    )

    plot_productivity_chart(
        plot_df=plot_df,
        output_path=args.output,
        capital_mode=args.capital_mode,
        dpi=args.dpi,
    )

    export_df = plot_df.copy()
    export_df["date"] = export_df["period"].astype(str)
    export_df = export_df[
        ["date", "tfp_growth", "utilization_growth", "capital_deepening"]
    ]
    export_path.parent.mkdir(parents=True, exist_ok=True)
    export_df.to_csv(export_path, index=False)

    print(f"Saved chart to: {args.output}")
    print(f"Saved plotted data to: {export_path}")


if __name__ == "__main__":
    main()
