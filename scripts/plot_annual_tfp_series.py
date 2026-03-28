#!/usr/bin/env python3
"""Plot annual raw and utilization-adjusted TFP growth from the SF Fed workbook.

By default, this script reads the ``annual`` sheet in the checked-in workbook and
produces additive raw and utilization-adjusted annual TFP charts and CSVs.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from sf_tfp_data import DEFAULT_WORKBOOK_PATH, prepare_workbook

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
OUTPUT_DIR = REPO_ROOT / "output"

SERIES_SPECS: dict[str, dict[str, Any]] = {
    "raw": {
        "column": "dtfp",
        "csv_column": "tfp",
        "label": "Raw TFP",
        "color": "#2E6F9E",
        "title": "Annual raw TFP growth",
        "suffix": "raw",
    },
    "util_adjusted": {
        "column": "dtfp_util",
        "csv_column": "tfp_util_adjusted",
        "label": "Utilization-adjusted TFP",
        "color": "#E15759",
        "title": "Annual utilization-adjusted TFP growth",
        "suffix": "util_adjusted",
    },
}

COLORS = {
    "axis": "#333333",
    "grid": "#B8B8B8",
}


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
        default=OUTPUT_DIR / "tfp_annual",
        help="Base output prefix. Produces *_raw and *_util_adjusted PNG/CSV files.",
    )
    parser.add_argument(
        "--start-year",
        type=int,
        default=1948,
        help="First annual observation to include in the charts (default: 1948).",
    )
    parser.add_argument(
        "--series",
        choices=("both", "raw", "util_adjusted"),
        default="both",
        help="Generate both annual series or only one of them.",
    )
    return parser.parse_args()


def annual_output_paths(output_prefix: Path) -> dict[str, Path]:
    return {
        "raw_png": output_prefix.with_name(output_prefix.name + "_raw.png"),
        "raw_csv": output_prefix.with_name(output_prefix.name + "_raw.csv"),
        "util_adjusted_png": output_prefix.with_name(output_prefix.name + "_util_adjusted.png"),
        "util_adjusted_csv": output_prefix.with_name(output_prefix.name + "_util_adjusted.csv"),
    }


def load_annual_data(path: Path) -> pd.DataFrame:
    annual = pd.read_excel(path, sheet_name="annual", header=0)
    if "date" not in annual.columns:
        raise ValueError(f"Could not find a 'date' column in annual sheet: {path}")

    annual["date"] = pd.to_numeric(annual["date"], errors="coerce")
    annual = annual.dropna(subset=["date"]).copy()
    annual["year"] = annual["date"].astype(int)
    annual = annual.dropna(subset=["dtfp", "dtfp_util"], how="all").copy()
    annual.sort_values("year", inplace=True)
    return annual.reset_index(drop=True)


def annual_axis_limits(annual_df: pd.DataFrame) -> tuple[float, float]:
    values = annual_df[[spec["column"] for spec in SERIES_SPECS.values()]].to_numpy().ravel()
    ymax = max(0.0, float(np.nanmax(values))) + 0.75
    ymin = min(0.0, float(np.nanmin(values))) - 0.75
    return ymin, ymax


def style_axis(ax: plt.Axes) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(COLORS["axis"])
    ax.spines["bottom"].set_color(COLORS["axis"])
    ax.tick_params(colors=COLORS["axis"])
    ax.grid(axis="y", linestyle=":", linewidth=0.8, color=COLORS["grid"], alpha=0.9)


def plot_annual_series(
    annual_df: pd.DataFrame,
    series_key: str,
    output_png: Path,
    y_limits: tuple[float, float],
    start_year: int = 1948,
) -> None:
    spec = SERIES_SPECS[series_key]
    plot_df = annual_df[annual_df["year"] >= start_year].copy()
    if plot_df.empty:
        raise ValueError(f"No annual data available after start_year={start_year}.")

    years = plot_df["year"].to_numpy()
    values = plot_df[spec["column"]].to_numpy()

    fig, ax = plt.subplots(figsize=(12.8, 5.6))
    ax.bar(
        years,
        values,
        width=0.82,
        color=spec["color"],
        edgecolor=spec["color"],
        linewidth=0.35,
        zorder=3,
    )
    ax.axhline(0, color=COLORS["axis"], linewidth=1.0, zorder=2)
    ax.set_xlim(years.min() - 0.9, years.max() + 0.9)
    ax.set_ylim(*y_limits)
    tick_start = int(5 * np.floor(years.min() / 5))
    ax.set_xticks(np.arange(tick_start, years.max() + 1, 5))
    ax.set_ylabel("Percent")
    ax.set_title(spec["title"])
    style_axis(ax)

    fig.text(
        0.01,
        0.01,
        "Source: SF Fed annual tab; author’s calculations.",
        fontsize=9,
    )
    output_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_png, dpi=220, bbox_inches="tight")
    plt.close(fig)


def export_annual_series_csv(
    annual_df: pd.DataFrame,
    series_key: str,
    output_csv: Path,
    start_year: int = 1948,
) -> None:
    spec = SERIES_SPECS[series_key]
    export_df = annual_df.loc[annual_df["year"] >= start_year, ["date", "year", spec["column"]]].copy()
    export_df.rename(columns={spec["column"]: spec["csv_column"]}, inplace=True)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    export_df.to_csv(output_csv, index=False)


def write_annual_tfp_outputs(
    annual_df: pd.DataFrame,
    output_prefix: Path,
    start_year: int = 1948,
    series: str = "both",
) -> dict[str, Path]:
    output_paths = annual_output_paths(output_prefix)
    requested_series = list(SERIES_SPECS) if series == "both" else [series]
    y_limits = annual_axis_limits(annual_df[annual_df["year"] >= start_year])

    for series_key in requested_series:
        plot_annual_series(
            annual_df,
            series_key=series_key,
            output_png=output_paths[f"{series_key}_png"],
            y_limits=y_limits,
            start_year=start_year,
        )
        export_annual_series_csv(
            annual_df,
            series_key=series_key,
            output_csv=output_paths[f"{series_key}_csv"],
            start_year=start_year,
        )

    return {
        key: path
        for key, path in output_paths.items()
        if series == "both" or key.startswith(series)
    }


def main() -> None:
    args = parse_args()
    input_path = prepare_workbook(args.input, refresh_data=args.refresh_data)
    annual_df = load_annual_data(input_path)
    written = write_annual_tfp_outputs(
        annual_df,
        output_prefix=args.output_prefix,
        start_year=args.start_year,
        series=args.series,
    )

    print(f"Latest annual observation in workbook: {annual_df['year'].max()}")
    for path in written.values():
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
