#!/usr/bin/env python3
"""
Reproduce a productivity-decomposition chart from the Fernald quarterly TFP workbook.

By default, the script reads the checked-in workbook at ``data/quarterly_tfp.xlsx``.
By default, the script uses the custom period buckets shown in the target chart,
with a final bar that automatically extends from 2023Q1 to the latest available
quarter. The workbook's built-in summary periods remain available via
``--period-source workbook``.

Usage:
    python reproduce_tfp_decomposition.py
    python reproduce_tfp_decomposition.py --period-source workbook
    python reproduce_tfp_decomposition.py --mode util_adjusted
    python reproduce_tfp_decomposition.py --input data/quarterly_tfp.xlsx --output-prefix tfp_decomposition
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sf_tfp_data import DEFAULT_WORKBOOK_PATH, prepare_workbook

DATE_RE = re.compile(r"^\d{4}:Q[1-4]$")
SUMMARY_RE = re.compile(r"^(?:\d{4}:[1-4]-\d{4}:[1-4]|Since \d{4}:[1-4]|Past \d+ qtrs)$")
SUMMARY_RANGE_RE = re.compile(r"^(?P<start_year>\d{4}):(?P<start_quarter>[1-4])-(?P<end_year>\d{4}):(?P<end_quarter>[1-4])$")
SUMMARY_SINCE_RE = re.compile(r"^Since (?P<start_year>\d{4}):(?P<start_quarter>[1-4])$")
SUMMARY_PAST_RE = re.compile(r"^Past (?P<n_quarters>\d+) qtrs$")
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
OUTPUT_DIR = REPO_ROOT / "output"

MODE_SPECS: dict[str, dict[str, Any]] = {
    "raw": {
        "table_components": ["labor_composition", "capital_deepening", "tfp"],
        "plot_components": ["tfp", "capital_deepening", "labor_composition"],
        "share_component": "tfp",
        "share_column": "tfp_share_pct",
        "labels": {
            "labor_composition": "Labor composition",
            "capital_deepening": "Capital deepening",
            "tfp": "TFP",
        },
        "colors": {
            "tfp": "#1f77b4",
            "capital_deepening": "#ff7f0e",
            "labor_composition": "#2ca02c",
        },
        "title": "Average contributions to growth in U.S. output per hour",
    },
    "util_adjusted": {
        "table_components": [
            "labor_composition",
            "capital_deepening",
            "utilization",
            "tfp_util_adjusted",
        ],
        "plot_components": [
            "tfp_util_adjusted",
            "capital_deepening",
            "labor_composition",
            "utilization",
        ],
        "share_component": "tfp_util_adjusted",
        "share_column": "tfp_util_adjusted_share_pct",
        "labels": {
            "labor_composition": "Labor composition",
            "capital_deepening": "Capital deepening",
            "utilization": "Utilization",
            "tfp_util_adjusted": "Utilization-adjusted TFP",
        },
        "colors": {
            "tfp_util_adjusted": "#1f77b4",
            "capital_deepening": "#ff7f0e",
            "labor_composition": "#2ca02c",
            "utilization": "#e15759",
        },
        "title": "Average contributions to growth in U.S. output per hour\n(utilization-adjusted TFP separated)",
    },
}


def to_period(date_str: str) -> pd.Period:
    year = int(date_str[:4])
    quarter = int(date_str[-1])
    return pd.Period(year=year, quarter=quarter, freq="Q-DEC")


def period_to_year_float(period: pd.Period) -> float:
    return period.year + (period.quarter - 1) / 4.0


def format_last_label(start: pd.Period, end: pd.Period) -> str:
    """Return a compact label for the final period."""
    if end.year == start.year:
        if end.quarter == 4:
            return f"{start.year}"
        if end.quarter == start.quarter:
            return f"{start.year}Q{start.quarter}"
        return f"{start.year}Q{start.quarter}-{end.year}Q{end.quarter}"
    if end.quarter == 4:
        return f"{start.year}-{end.year}"
    return f"{start.year}-{end.year}Q{end.quarter}"


def prettify_summary_label(label: str) -> str:
    if label.startswith("Since "):
        return label.replace(":", "Q")
    if label.startswith("Past "):
        return label
    return label.replace(":", "Q")


def parse_summary_window(label: str, latest_available: pd.Period) -> tuple[str | pd.NA, str | pd.NA, int | pd.NA]:
    range_match = SUMMARY_RANGE_RE.match(label)
    if range_match:
        start = pd.Period(
            year=int(range_match["start_year"]),
            quarter=int(range_match["start_quarter"]),
            freq="Q-DEC",
        )
        end = pd.Period(
            year=int(range_match["end_year"]),
            quarter=int(range_match["end_quarter"]),
            freq="Q-DEC",
        )
        n_quarters = end.ordinal - start.ordinal + 1
        return str(start), str(end), n_quarters

    since_match = SUMMARY_SINCE_RE.match(label)
    if since_match:
        start = pd.Period(
            year=int(since_match["start_year"]),
            quarter=int(since_match["start_quarter"]),
            freq="Q-DEC",
        )
        n_quarters = latest_available.ordinal - start.ordinal + 1
        return str(start), str(latest_available), n_quarters

    past_match = SUMMARY_PAST_RE.match(label)
    if past_match:
        n_quarters = int(past_match["n_quarters"])
        start = latest_available - (n_quarters - 1)
        return str(start), str(latest_available), n_quarters

    return pd.NA, pd.NA, pd.NA


def get_mode_spec(mode: str) -> dict[str, Any]:
    try:
        return MODE_SPECS[mode]
    except KeyError as exc:
        raise ValueError(f"Unsupported decomposition mode: {mode}") from exc


def period_table_columns(mode: str) -> list[str]:
    spec = get_mode_spec(mode)
    return [
        "period",
        "start",
        "end",
        *spec["table_components"],
        "total_lp",
        spec["share_column"],
        "n_quarters",
    ]


def compute_share(component_value: float, total_lp: float) -> float:
    if total_lp == 0:
        return np.nan
    return 100 * component_value / total_lp


def default_output_prefix(mode: str) -> Path:
    suffix = "" if mode == "raw" else "_util_adjusted"
    return OUTPUT_DIR / f"tfp_decomposition{suffix}"


def validate_decomposition_identity(
    df: pd.DataFrame,
    mode: str,
    total_column: str = "total_lp",
    atol: float = 1e-10,
) -> float:
    if df.empty:
        return 0.0

    spec = get_mode_spec(mode)
    components = spec["table_components"]
    gap = (df[total_column] - df[components].sum(axis=1)).abs().max()
    gap = 0.0 if pd.isna(gap) else float(gap)
    if gap > atol:
        raise ValueError(
            f"Decomposition identity failed for mode={mode}: max |gap| = {gap:.3e} exceeds {atol:.1e}."
        )
    return gap


def load_quarterly_sheet(path: Path) -> pd.DataFrame:
    q = pd.read_excel(path, sheet_name="quarterly", header=1)
    if "date" not in q.columns:
        raise ValueError(f"Could not find a 'date' column in quarterly sheet: {path}")
    return q


def load_quarterly_data(path: Path) -> pd.DataFrame:
    q = load_quarterly_sheet(path)
    q = q[q["date"].astype(str).str.match(DATE_RE)].copy()
    q["period"] = q["date"].map(to_period)
    q.sort_values("period", inplace=True)

    # Growth-accounting decomposition:
    # dLP = dtfp + alpha*(dk - dhours - dLQ) + dLQ
    q["capital_deepening"] = q["alpha"] * (q["dk"] - q["dhours"] - q["dLQ"])
    q["labor_composition"] = q["dLQ"]
    q["tfp"] = q["dtfp"]
    q["tfp_util_adjusted"] = q["dtfp_util"]
    q["utilization"] = q["dutil"]
    q["total_lp"] = q["capital_deepening"] + q["labor_composition"] + q["tfp"]
    q["raw_capital_per_hour_growth"] = q["dk"] - q["dhours"]
    q["x"] = q["period"].map(period_to_year_float)
    q["tfp_share_pct"] = np.where(
        q["total_lp"] != 0,
        100 * q["tfp"] / q["total_lp"],
        np.nan,
    )
    q["tfp_util_adjusted_share_pct"] = np.where(
        q["total_lp"] != 0,
        100 * q["tfp_util_adjusted"] / q["total_lp"],
        np.nan,
    )

    validate_decomposition_identity(q, mode="raw")
    validate_decomposition_identity(q, mode="util_adjusted")
    return q.reset_index(drop=True)


def build_summary_row(
    *,
    label: str,
    start: str | pd.NA,
    end: str | pd.NA,
    component_values: dict[str, float],
    total_lp: float,
    n_quarters: int | pd.NA,
    mode: str,
) -> dict[str, Any]:
    spec = get_mode_spec(mode)
    share_component = spec["share_component"]
    row: dict[str, Any] = {
        "period": label,
        "start": start,
        "end": end,
        "total_lp": total_lp,
        spec["share_column"]: compute_share(component_values[share_component], total_lp),
        "n_quarters": n_quarters,
    }
    for component in spec["table_components"]:
        row[component] = component_values[component]
    return row


def build_workbook_summary_table(raw_quarterly: pd.DataFrame, mode: str = "raw") -> pd.DataFrame:
    summary = raw_quarterly[raw_quarterly["date"].astype(str).str.match(SUMMARY_RE)].copy()
    if summary.empty:
        return pd.DataFrame(columns=period_table_columns(mode))

    latest_available = to_period(
        raw_quarterly.loc[raw_quarterly["date"].astype(str).str.match(DATE_RE), "date"].iloc[-1]
    )
    rows = []
    for _, row in summary.iterrows():
        start, end, n_quarters = parse_summary_window(str(row["date"]), latest_available)
        total_lp = float(row["dLP"])
        labor_composition = float(row["dLQ"])
        component_values = {
            "labor_composition": labor_composition,
            "capital_deepening": 0.0,
            "tfp": float(row["dtfp"]),
            "tfp_util_adjusted": float(row["dtfp_util"]),
            "utilization": float(row["dutil"]),
        }
        if mode == "raw":
            component_values["capital_deepening"] = (
                total_lp - component_values["labor_composition"] - component_values["tfp"]
            )
        else:
            component_values["capital_deepening"] = (
                total_lp
                - component_values["labor_composition"]
                - component_values["utilization"]
                - component_values["tfp_util_adjusted"]
            )

        rows.append(
            build_summary_row(
                label=prettify_summary_label(str(row["date"])),
                start=start,
                end=end,
                component_values=component_values,
                total_lp=total_lp,
                n_quarters=n_quarters,
                mode=mode,
            )
        )

    period_df = pd.DataFrame(rows, columns=period_table_columns(mode))
    validate_decomposition_identity(period_df, mode=mode)
    return period_df


def build_period_table(q: pd.DataFrame, latest_start: str = "2023Q1", mode: str = "raw") -> pd.DataFrame:
    spec = get_mode_spec(mode)
    latest_available = q["period"].max()
    latest_start_period = pd.Period(latest_start, freq="Q-DEC")
    latest_label = format_last_label(latest_start_period, latest_available)

    periods = [
        ("1995-2004", "1995Q1", "2004Q4"),
        ("2004-07", "2004Q1", "2007Q4"),
        ("2010-19", "2010Q1", "2019Q4"),
        ("2020-2022", "2020Q1", "2022Q4"),
        (latest_label, latest_start, str(latest_available)),
    ]

    rows = []
    for label, start, end in periods:
        start_p = pd.Period(start, freq="Q-DEC")
        end_p = pd.Period(end, freq="Q-DEC")
        mask = (q["period"] >= start_p) & (q["period"] <= end_p)
        sub = q.loc[mask, [*spec["table_components"], "total_lp"]]
        component_values = {
            component: float(sub[component].mean()) for component in spec["table_components"]
        }
        total_lp = float(sub["total_lp"].mean())
        rows.append(
            build_summary_row(
                label=label,
                start=str(start_p),
                end=str(end_p),
                component_values=component_values,
                total_lp=total_lp,
                n_quarters=int(sub.shape[0]),
                mode=mode,
            )
        )

    period_df = pd.DataFrame(rows, columns=period_table_columns(mode))
    validate_decomposition_identity(period_df, mode=mode)
    return period_df


def resolve_input_path(path: Path) -> Path:
    if path.exists():
        return path
    candidate = REPO_ROOT / path
    if candidate.exists():
        return candidate
    return path


def plot_decomposition(period_df: pd.DataFrame, output_png: Path, mode: str = "raw") -> None:
    spec = get_mode_spec(mode)
    labels = period_df["period"].tolist()
    x = np.arange(len(labels))

    fig_width = max(10.5, 1.5 * len(labels))
    fig, ax = plt.subplots(figsize=(fig_width, 5.5))

    cumulative = np.zeros(len(period_df))
    stack_levels = [cumulative.copy()]
    share_bottoms = np.zeros(len(period_df))
    for component in spec["plot_components"]:
        values = period_df[component].to_numpy()
        if component == spec["share_component"]:
            share_bottoms = cumulative.copy()
        ax.bar(
            x,
            values,
            bottom=cumulative,
            label=spec["labels"][component],
            color=spec["colors"][component],
        )
        cumulative = cumulative + values
        stack_levels.append(cumulative.copy())

    totals = period_df["total_lp"].to_numpy()
    share_values = period_df[spec["share_component"]].to_numpy()
    shares = period_df[spec["share_column"]].to_numpy()

    for xi, total in zip(x, totals):
        if total >= 0:
            y = total + 0.05
            va = "bottom"
        else:
            y = total - 0.05
            va = "top"
        ax.text(xi, y, f"{total:.2f}", ha="center", va=va, fontsize=10)

    for xi, share_value, share, share_bottom in zip(x, share_values, shares, share_bottoms):
        if np.isfinite(share):
            ax.text(
                xi,
                share_bottom + share_value / 2,
                f"{share:.0f}%",
                ha="center",
                va="center",
                fontsize=10,
                color="white",
                fontweight="bold",
            )

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=20, ha="right")
    ax.set_ylabel("Percent (annual rate)")
    ax.set_title(spec["title"])

    ax.legend(
        ncols=1,
        frameon=False,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.98),
        borderaxespad=0.0,
    )

    ax.grid(axis="y", linestyle=":", linewidth=0.6)
    stack_extents = np.concatenate(stack_levels) if stack_levels else np.array([0.0])
    ymax = max(0.0, float(np.nanmax(np.r_[totals, stack_extents]))) + 0.35
    ymin = min(0.0, float(np.nanmin(np.r_[totals, stack_extents]))) - 0.15
    ax.set_ylim(ymin, ymax)

    fig.text(
        0.01,
        0.01,
        "Source: SF Fed; author’s calculations.",
        ha="left",
        va="bottom",
        fontsize=9,
    )

    fig.tight_layout(rect=[0, 0.04, 1, 1])
    fig.savefig(output_png, dpi=200, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
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
        default=None,
        help=(
            "Output prefix for the PNG and CSV files. Defaults to "
            "output/tfp_decomposition for raw mode and "
            "output/tfp_decomposition_util_adjusted for util_adjusted mode."
        ),
    )
    parser.add_argument(
        "--latest-start",
        default="2023Q1",
        help="Start quarter for the final, automatically expanding bar (default: 2023Q1).",
    )
    parser.add_argument(
        "--period-source",
        choices=("workbook", "custom"),
        default="custom",
        help="Use custom quarter aggregation or workbook summary periods.",
    )
    parser.add_argument(
        "--mode",
        choices=tuple(MODE_SPECS),
        default="raw",
        help="Choose the raw or utilization-adjusted decomposition.",
    )
    args = parser.parse_args()

    input_path = prepare_workbook(args.input, refresh_data=args.refresh_data)
    raw_quarterly = load_quarterly_sheet(input_path)
    q = load_quarterly_data(input_path)

    if args.period_source == "workbook":
        period_df = build_workbook_summary_table(raw_quarterly, mode=args.mode)
        if period_df.empty:
            period_df = build_period_table(q, latest_start=args.latest_start, mode=args.mode)
            period_source_used = "custom"
        else:
            period_source_used = "workbook"
    else:
        period_df = build_period_table(q, latest_start=args.latest_start, mode=args.mode)
        period_source_used = "custom"

    output_prefix = args.output_prefix if args.output_prefix is not None else default_output_prefix(args.mode)
    output_png = output_prefix.with_suffix(".png")
    output_csv = output_prefix.with_suffix(".csv")
    output_png.parent.mkdir(parents=True, exist_ok=True)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    period_df.to_csv(output_csv, index=False)
    plot_decomposition(period_df, output_png, mode=args.mode)

    latest_available = q["period"].max()
    print(f"Latest quarter in workbook: {latest_available}")
    print(f"Period source used: {period_source_used}")
    print(f"Mode used: {args.mode}")
    print(f"Wrote {output_png}")
    print(f"Wrote {output_csv}")


if __name__ == "__main__":
    main()
