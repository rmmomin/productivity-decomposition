#!/usr/bin/env python3
"""Build summary and quarterly labor-productivity decomposition outputs.

Outputs:
- productivity_decomposition_summary.png / .csv
- productivity_decomposition_summary_util_adjusted.png / .csv
- productivity_decomposition_quarterly.png / .csv
- productivity_decomposition_quarterly_util_adjusted.png / .csv
- tfp_decomposition_annual.png / .csv
- tfp_decomposition_annual_util_adjusted.png / .csv
- tfp_annual_raw.png / .csv
- tfp_annual_util_adjusted.png / .csv
- productivity_decomposition_bridge.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np
import pandas as pd

from plot_annual_productivity_decomposition import write_annual_decomposition_outputs
from plot_annual_tfp_series import (
    load_annual_data as load_annual_tfp_data,
    write_annual_tfp_outputs,
)
from reproduce_tfp_decomposition import (
    build_period_table,
    get_mode_spec,
    load_quarterly_data,
    plot_decomposition,
    validate_decomposition_identity,
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
    "tfp_util_adjusted": "#2E6F9E",
    "capital_deepening": "#F28E2B",
    "labor_composition": "#59A14F",
    "utilization": "#E15759",
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
    parser.add_argument(
        "--annual-start-year",
        type=int,
        default=1948,
        help="First year shown in the annual TFP series charts.",
    )
    parser.add_argument(
        "--annual-latest-start-year",
        type=int,
        default=2023,
        help="Start year for the final annual summary bar in the annual decomposition charts.",
    )
    return parser.parse_args()


def build_quarterly_table(
    q: pd.DataFrame,
    rolling_quarters: int = 4,
    start_year: int = 1985,
    mode: str = "raw",
) -> pd.DataFrame:
    spec = get_mode_spec(mode)
    components = list(dict.fromkeys([*spec["table_components"], *spec["plot_components"]]))
    out = q.copy()

    for column in [*components, "total_lp"]:
        out[f"{column}_roll{rolling_quarters}"] = out[column].rolling(rolling_quarters).mean()

    out = out[out["period"].dt.year >= start_year].copy()
    out = out.dropna(
        subset=[f"{column}_roll{rolling_quarters}" for column in [*components, "total_lp"]]
    )

    selected = out[
        [
            "date",
            "period",
            "x",
            *[f"{column}_roll{rolling_quarters}" for column in spec["plot_components"]],
            f"total_lp_roll{rolling_quarters}",
        ]
    ].rename(
        columns={
            **{
                f"{column}_roll{rolling_quarters}": column
                for column in spec["plot_components"]
            },
            f"total_lp_roll{rolling_quarters}": "total_lp",
        }
    )

    validate_decomposition_identity(selected, mode=mode)
    return selected.reset_index(drop=True)


def build_bridge_table(q: pd.DataFrame, recent_start: str = "2023Q1") -> pd.DataFrame:
    start_period = pd.Period(recent_start, freq="Q-DEC")
    subset = q[q["period"] >= start_period].copy()
    latest_period = subset["period"].max()

    averages = {
        "raw_capital_per_hour_growth": float(subset["raw_capital_per_hour_growth"].mean()),
        "capital_deepening": float(subset["capital_deepening"].mean()),
        "labor_composition": float(subset["labor_composition"].mean()),
        "tfp": float(subset["tfp"].mean()),
        "tfp_util_adjusted": float(subset["tfp_util_adjusted"].mean()),
        "utilization": float(subset["utilization"].mean()),
        "total_lp": float(subset["total_lp"].mean()),
    }
    raw_tfp_identity_gap = averages["tfp"] - (
        averages["tfp_util_adjusted"] + averages["utilization"]
    )
    total_lp_identity_gap = averages["total_lp"] - (
        averages["capital_deepening"]
        + averages["labor_composition"]
        + averages["utilization"]
        + averages["tfp_util_adjusted"]
    )

    rows = [
        {
            "sort_order": 1,
            "identity_group": "capital_input",
            "measure": "Raw capital per hour growth (dk - dhours)",
            "formula": "Input to capital deepening contribution",
            "average_annual_rate": averages["raw_capital_per_hour_growth"],
            "identity_gap": np.nan,
        },
        {
            "sort_order": 2,
            "identity_group": "total_lp_components",
            "measure": "Capital deepening contribution",
            "formula": "Component of total labor productivity growth",
            "average_annual_rate": averages["capital_deepening"],
            "identity_gap": np.nan,
        },
        {
            "sort_order": 3,
            "identity_group": "total_lp_components",
            "measure": "Labor composition",
            "formula": "Component of total labor productivity growth",
            "average_annual_rate": averages["labor_composition"],
            "identity_gap": np.nan,
        },
        {
            "sort_order": 4,
            "identity_group": "raw_tfp_components",
            "measure": "TFP (utilization-adjusted)",
            "formula": "Component of raw TFP and total labor productivity growth",
            "average_annual_rate": averages["tfp_util_adjusted"],
            "identity_gap": np.nan,
        },
        {
            "sort_order": 5,
            "identity_group": "raw_tfp_components",
            "measure": "Utilization",
            "formula": "Component of raw TFP and total labor productivity growth",
            "average_annual_rate": averages["utilization"],
            "identity_gap": np.nan,
        },
        {
            "sort_order": 6,
            "identity_group": "raw_tfp_identity",
            "measure": "TFP (unadjusted)",
            "formula": "TFP (utilization-adjusted) + Utilization",
            "average_annual_rate": averages["tfp"],
            "identity_gap": raw_tfp_identity_gap,
        },
        {
            "sort_order": 7,
            "identity_group": "total_lp_identity",
            "measure": "Total labor productivity growth",
            "formula": (
                "Capital deepening contribution + Labor composition + "
                "TFP (utilization-adjusted) + Utilization"
            ),
            "average_annual_rate": averages["total_lp"],
            "identity_gap": total_lp_identity_gap,
        },
    ]
    bridge_df = pd.DataFrame(rows)
    bridge_df["window_start"] = str(start_period)
    bridge_df["window_end"] = str(latest_period)
    bridge_df["n_quarters"] = int(subset.shape[0])
    return bridge_df[
        [
            "window_start",
            "window_end",
            "n_quarters",
            "sort_order",
            "identity_group",
            "measure",
            "formula",
            "average_annual_rate",
            "identity_gap",
        ]
    ]


def style_axis(ax: plt.Axes) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(COLORS["axis"])
    ax.spines["bottom"].set_color(COLORS["axis"])
    ax.tick_params(colors=COLORS["axis"])
    ax.grid(axis="y", linestyle=":", linewidth=0.8, color=COLORS["grid"], alpha=0.9)


def quarterly_title(mode: str, rolling_quarters: int) -> str:
    base = (
        "Quarterly decomposition of U.S. output per hour growth\n"
        f"({rolling_quarters}-quarter average, annual rate)"
    )
    if mode == "util_adjusted":
        return (
            "Quarterly decomposition of U.S. output per hour growth\n"
            f"({rolling_quarters}-quarter average, annual rate; utilization-adjusted TFP separated)"
        )
    return base


def plot_quarterly(
    quarterly_df: pd.DataFrame,
    output_png: Path,
    start_year: int = 1985,
    rolling_quarters: int = 4,
    mode: str = "raw",
) -> None:
    spec = get_mode_spec(mode)
    components = spec["plot_components"]

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

    x = quarterly_df["x"].to_numpy()
    if mode == "raw":
        bar_width = 0.075
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
            color=COLORS["capital_deepening"],
            edgecolor=COLORS["capital_deepening"],
            linewidth=0.3,
            zorder=3,
        )
        ax.bar(
            x + bar_width,
            quarterly_df["labor_composition"],
            width=bar_width,
            color=COLORS["labor_composition"],
            edgecolor=COLORS["labor_composition"],
            linewidth=0.3,
            zorder=3,
        )
    else:
        cluster_width = 0.22
        bar_width = cluster_width / len(components)
        offsets = np.linspace(
            -cluster_width / 2 + bar_width / 2,
            cluster_width / 2 - bar_width / 2,
            len(components),
        )
        for offset, component in zip(offsets, components):
            ax.bar(
                x + offset,
                quarterly_df[component],
                width=bar_width,
                color=COLORS[component],
                edgecolor=COLORS[component],
                linewidth=0.3,
                zorder=3,
            )

    ax.axhline(0, color=COLORS["axis"], linewidth=1.1, zorder=2)
    ax.set_xlim(start_year - 0.5, quarterly_df["period"].dt.year.max() + 0.8)
    if mode == "raw":
        ax.set_ylim(-4.8, 8.6)
    else:
        ax.set_ylim(
            min(-4.8, float(np.nanmin(quarterly_df[components].to_numpy())) - 0.6),
            max(8.6, float(np.nanmax(quarterly_df[components].to_numpy())) + 0.6),
        )
    ax.set_xticks(np.arange(start_year, quarterly_df["period"].dt.year.max() + 1, 5))
    ax.set_yticks([-4, 0, 4, 8])
    ax.set_title(quarterly_title(mode=mode, rolling_quarters=rolling_quarters), fontsize=14, pad=8)
    ax.set_ylabel("Percent")
    style_axis(ax)

    handles = [
        Patch(facecolor=COLORS[component], label=spec["labels"][component])
        for component in components
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


def output_paths(output_prefix: Path) -> dict[str, Path]:
    return {
        "summary_png": output_prefix.with_name(output_prefix.name + "_summary.png"),
        "summary_csv": output_prefix.with_name(output_prefix.name + "_summary.csv"),
        "summary_util_adjusted_png": output_prefix.with_name(
            output_prefix.name + "_summary_util_adjusted.png"
        ),
        "summary_util_adjusted_csv": output_prefix.with_name(
            output_prefix.name + "_summary_util_adjusted.csv"
        ),
        "quarterly_png": output_prefix.with_name(output_prefix.name + "_quarterly.png"),
        "quarterly_csv": output_prefix.with_name(output_prefix.name + "_quarterly.csv"),
        "quarterly_util_adjusted_png": output_prefix.with_name(
            output_prefix.name + "_quarterly_util_adjusted.png"
        ),
        "quarterly_util_adjusted_csv": output_prefix.with_name(
            output_prefix.name + "_quarterly_util_adjusted.csv"
        ),
        "bridge_csv": output_prefix.with_name(output_prefix.name + "_bridge.csv"),
    }


def main() -> None:
    args = parse_args()
    input_path = prepare_workbook(args.input, refresh_data=args.refresh_data)

    q = load_quarterly_data(input_path)
    annual_df = load_annual_tfp_data(input_path)
    period_df_raw = build_period_table(q, latest_start=args.latest_start, mode="raw")
    period_df_util_adjusted = build_period_table(
        q,
        latest_start=args.latest_start,
        mode="util_adjusted",
    )
    quarterly_df_raw = build_quarterly_table(
        q,
        rolling_quarters=args.rolling_quarters,
        start_year=args.start_year,
        mode="raw",
    )
    quarterly_df_util_adjusted = build_quarterly_table(
        q,
        rolling_quarters=args.rolling_quarters,
        start_year=args.start_year,
        mode="util_adjusted",
    )
    bridge_df = build_bridge_table(q, recent_start=args.latest_start)
    annual_prefix = args.output_prefix.with_name("tfp_annual")
    annual_decomp_prefix = args.output_prefix.with_name("tfp_decomposition_annual")

    paths = output_paths(args.output_prefix)
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)

    period_df_raw.to_csv(paths["summary_csv"], index=False)
    period_df_util_adjusted.to_csv(paths["summary_util_adjusted_csv"], index=False)
    quarterly_df_raw.to_csv(paths["quarterly_csv"], index=False)
    quarterly_df_util_adjusted.to_csv(paths["quarterly_util_adjusted_csv"], index=False)
    bridge_df.to_csv(paths["bridge_csv"], index=False)
    annual_written = write_annual_tfp_outputs(
        annual_df,
        output_prefix=annual_prefix,
        start_year=args.annual_start_year,
    )
    annual_decomp_written = write_annual_decomposition_outputs(
        annual_df,
        output_prefix=annual_decomp_prefix,
        latest_start_year=args.annual_latest_start_year,
    )

    plot_decomposition(period_df_raw, paths["summary_png"], mode="raw")
    plot_decomposition(
        period_df_util_adjusted,
        paths["summary_util_adjusted_png"],
        mode="util_adjusted",
    )
    plot_quarterly(
        quarterly_df_raw,
        paths["quarterly_png"],
        start_year=args.start_year,
        rolling_quarters=args.rolling_quarters,
        mode="raw",
    )
    plot_quarterly(
        quarterly_df_util_adjusted,
        paths["quarterly_util_adjusted_png"],
        start_year=args.start_year,
        rolling_quarters=args.rolling_quarters,
        mode="util_adjusted",
    )

    latest_available = q["period"].max()
    print(f"Latest quarter in workbook: {latest_available}")
    for key in [
        "summary_png",
        "summary_csv",
        "summary_util_adjusted_png",
        "summary_util_adjusted_csv",
        "quarterly_png",
        "quarterly_csv",
        "quarterly_util_adjusted_png",
        "quarterly_util_adjusted_csv",
        "bridge_csv",
    ]:
        print(f"Wrote {paths[key]}")
    for key in ["raw_png", "raw_csv", "util_adjusted_png", "util_adjusted_csv"]:
        print(f"Wrote {annual_written[key]}")
    for key in ["raw_png", "raw_csv", "util_adjusted_png", "util_adjusted_csv"]:
        print(f"Wrote {annual_decomp_written[key]}")


if __name__ == "__main__":
    main()
