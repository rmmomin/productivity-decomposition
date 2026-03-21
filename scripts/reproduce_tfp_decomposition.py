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
    python reproduce_tfp_decomposition.py --input data/quarterly_tfp.xlsx --output-prefix tfp_decomposition
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

DATE_RE = re.compile(r"^\d{4}:Q[1-4]$")
SUMMARY_RE = re.compile(r"^(?:\d{4}:[1-4]-\d{4}:[1-4]|Since \d{4}:[1-4]|Past \d+ qtrs)$")
SUMMARY_RANGE_RE = re.compile(r"^(?P<start_year>\d{4}):(?P<start_quarter>[1-4])-(?P<end_year>\d{4}):(?P<end_quarter>[1-4])$")
SUMMARY_SINCE_RE = re.compile(r"^Since (?P<start_year>\d{4}):(?P<start_quarter>[1-4])$")
SUMMARY_PAST_RE = re.compile(r"^Past (?P<n_quarters>\d+) qtrs$")
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
OUTPUT_DIR = REPO_ROOT / "output"


def to_period(date_str: str) -> pd.Period:
    year = int(date_str[:4])
    quarter = int(date_str[-1])
    return pd.Period(year=year, quarter=quarter, freq="Q-DEC")


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


def load_quarterly_sheet(path: Path) -> pd.DataFrame:
    q = pd.read_excel(path, sheet_name="quarterly", header=1)
    if "date" not in q.columns:
        raise ValueError(f"Could not find a 'date' column in quarterly sheet: {path}")
    return q


def load_quarterly_data(path: Path) -> pd.DataFrame:
    q = load_quarterly_sheet(path)
    q = q[q["date"].astype(str).str.match(DATE_RE)].copy()
    q["period"] = q["date"].map(to_period)

    # Growth-accounting decomposition:
    # dLP = dtfp + alpha*(dk - dhours - dLQ) + dLQ
    q["capital_deepening"] = q["alpha"] * (q["dk"] - q["dhours"] - q["dLQ"])
    q["labor_composition"] = q["dLQ"]
    q["tfp"] = q["dtfp"]
    q["total_lp"] = q["capital_deepening"] + q["labor_composition"] + q["tfp"]
    q["tfp_share_pct"] = np.where(
        q["total_lp"] != 0,
        100 * q["tfp"] / q["total_lp"],
        np.nan,
    )

    return q


def build_workbook_summary_table(raw_quarterly: pd.DataFrame) -> pd.DataFrame:
    summary = raw_quarterly[raw_quarterly["date"].astype(str).str.match(SUMMARY_RE)].copy()
    if summary.empty:
        return pd.DataFrame()

    latest_available = to_period(
        raw_quarterly.loc[raw_quarterly["date"].astype(str).str.match(DATE_RE), "date"].iloc[-1]
    )
    rows = []
    for _, row in summary.iterrows():
        start, end, n_quarters = parse_summary_window(str(row["date"]), latest_available)
        total_lp = float(row["dLP"])
        tfp = float(row["dtfp"])
        labor_composition = float(row["dLQ"])
        capital_deepening = total_lp - labor_composition - tfp
        rows.append(
            {
                "period": prettify_summary_label(str(row["date"])),
                "start": start,
                "end": end,
                "labor_composition": labor_composition,
                "capital_deepening": capital_deepening,
                "tfp": tfp,
                "total_lp": total_lp,
                "tfp_share_pct": (100 * tfp / total_lp) if total_lp != 0 else np.nan,
                "n_quarters": n_quarters,
            }
        )

    return pd.DataFrame(rows)


def build_period_table(q: pd.DataFrame, latest_start: str = "2023Q1") -> pd.DataFrame:
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
        sub = q.loc[
            mask,
            ["labor_composition", "capital_deepening", "tfp", "total_lp"],
        ]
        rows.append(
            {
                "period": label,
                "start": str(start_p),
                "end": str(end_p),
                "labor_composition": sub["labor_composition"].mean(),
                "capital_deepening": sub["capital_deepening"].mean(),
                "tfp": sub["tfp"].mean(),
                "total_lp": sub["total_lp"].mean(),
                "tfp_share_pct": (100 * sub["tfp"].mean() / sub["total_lp"].mean())
                if sub["total_lp"].mean() != 0
                else np.nan,
                "n_quarters": int(sub.shape[0]),
            }
        )

    return pd.DataFrame(rows)


def resolve_input_path(path: Path) -> Path:
    if path.exists():
        return path
    candidate = REPO_ROOT / path
    if candidate.exists():
        return candidate
    return path


def plot_decomposition(period_df: pd.DataFrame, output_png: Path) -> None:
    labels = period_df["period"].tolist()
    x = np.arange(len(labels))

    fig_width = max(10.5, 1.5 * len(labels))
    fig, ax = plt.subplots(figsize=(fig_width, 5.5))

    ax.bar(x, period_df["tfp"], label="TFP")
    ax.bar(
        x,
        period_df["capital_deepening"],
        bottom=period_df["tfp"],
        label="Capital deepening",
    )
    ax.bar(
        x,
        period_df["labor_composition"],
        bottom=period_df["tfp"] + period_df["capital_deepening"],
        label="Labor composition",
    )

    totals = period_df["total_lp"].to_numpy()
    tfp_vals = period_df["tfp"].to_numpy()
    shares = period_df["tfp_share_pct"].to_numpy()

    # Labels on top of each stacked bar for total labor-productivity growth
    for xi, total in zip(x, totals):
        ax.text(xi, total + 0.05, f"{total:.2f}", ha="center", va="bottom", fontsize=10)

    # White label inside the TFP segment showing TFP as a share of the total
    for xi, tfp, share in zip(x, tfp_vals, shares):
        if np.isfinite(share):
            ax.text(
                xi,
                tfp / 2,
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
    ax.set_title("Average contributions to growth in U.S. output per hour")

    ax.legend(
        ncols=1,
        frameon=False,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.98),
        borderaxespad=0.0,
    )

    ax.grid(axis="y", linestyle=":", linewidth=0.6)
    ymax = max(0.0, float(np.nanmax(totals))) + 0.35
    ymin = min(0.0, float(np.nanmin(np.r_[0.0, period_df[["tfp", "capital_deepening", "labor_composition"]].to_numpy().ravel()]))) - 0.15
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
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/quarterly_tfp.xlsx"),
        help="Path to the SF Fed quarterly_tfp workbook.",
    )
    parser.add_argument(
        "--output-prefix",
        type=Path,
        default=OUTPUT_DIR / "tfp_decomposition",
        help="Output prefix for the PNG and CSV files.",
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
    args = parser.parse_args()

    input_path = resolve_input_path(args.input)
    raw_quarterly = load_quarterly_sheet(input_path)
    q = load_quarterly_data(input_path)

    if args.period_source == "workbook":
        period_df = build_workbook_summary_table(raw_quarterly)
        if period_df.empty:
            period_df = build_period_table(q, latest_start=args.latest_start)
            period_source_used = "custom"
        else:
            period_source_used = "workbook"
    else:
        period_df = build_period_table(q, latest_start=args.latest_start)
        period_source_used = "custom"

    output_png = args.output_prefix.with_suffix(".png")
    output_csv = args.output_prefix.with_suffix(".csv")
    output_png.parent.mkdir(parents=True, exist_ok=True)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    period_df.to_csv(output_csv, index=False)
    plot_decomposition(period_df, output_png)

    latest_available = q["period"].max()
    print(f"Latest quarter in workbook: {latest_available}")
    print(f"Period source used: {period_source_used}")
    print(f"Wrote {output_png}")
    print(f"Wrote {output_csv}")


if __name__ == "__main__":
    main()
