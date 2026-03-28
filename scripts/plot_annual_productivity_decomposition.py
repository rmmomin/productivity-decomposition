#!/usr/bin/env python3
"""Build annual analogues of the summary TFP decomposition charts.

These outputs mirror the stacked-bar summary charts in
``tfp_decomposition.png`` and ``tfp_decomposition_util_adjusted.png``, but use
the workbook's ``annual`` tab directly. The annual workbook notes that
identities only hold approximately at annual frequency, so capital deepening is
computed residually to keep the plotted decomposition exactly additive.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from plot_annual_tfp_series import load_annual_data
from reproduce_tfp_decomposition import (
    get_mode_spec,
    plot_decomposition,
    validate_decomposition_identity,
)
from sf_tfp_data import DEFAULT_WORKBOOK_PATH, prepare_workbook

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
        default=OUTPUT_DIR / "tfp_decomposition_annual",
        help=(
            "Base output prefix. Produces annual raw decomposition PNG/CSV files "
            "and parallel *_util_adjusted outputs."
        ),
    )
    parser.add_argument(
        "--latest-start-year",
        type=int,
        default=2023,
        help="Start year for the final, automatically extending annual bar (default: 2023).",
    )
    parser.add_argument(
        "--mode",
        choices=("both", "raw", "util_adjusted"),
        default="both",
        help="Generate both annual decomposition variants or only one of them.",
    )
    return parser.parse_args()


def annual_decomposition_output_paths(output_prefix: Path) -> dict[str, Path]:
    return {
        "raw_png": output_prefix.with_suffix(".png"),
        "raw_csv": output_prefix.with_suffix(".csv"),
        "util_adjusted_png": output_prefix.with_name(output_prefix.name + "_util_adjusted.png"),
        "util_adjusted_csv": output_prefix.with_name(output_prefix.name + "_util_adjusted.csv"),
    }


def format_last_year_label(start_year: int, end_year: int) -> str:
    if start_year == end_year:
        return str(start_year)
    return f"{start_year}-{end_year}"


def build_annual_decomposition_data(annual_df: pd.DataFrame, mode: str = "raw") -> pd.DataFrame:
    out = annual_df.copy()
    out["labor_composition"] = out["dLQ"]
    out["capital_deepening_formula"] = out["alpha"] * (out["dk"] - out["dhours"] - out["dLQ"])
    out["total_lp"] = out["dLP"]

    if mode == "raw":
        out["tfp"] = out["dtfp"]
        out["capital_deepening"] = out["total_lp"] - out["labor_composition"] - out["tfp"]
        out["identity_gap_formula"] = (
            out["total_lp"] - (out["capital_deepening_formula"] + out["labor_composition"] + out["tfp"])
        )
    else:
        out["tfp_util_adjusted"] = out["dtfp_util"]
        out["utilization"] = out["dutil"]
        out["capital_deepening"] = (
            out["total_lp"]
            - out["labor_composition"]
            - out["utilization"]
            - out["tfp_util_adjusted"]
        )
        out["identity_gap_formula"] = (
            out["total_lp"]
            - (
                out["capital_deepening_formula"]
                + out["labor_composition"]
                + out["utilization"]
                + out["tfp_util_adjusted"]
            )
        )

    validate_decomposition_identity(out, mode=mode)
    return out.reset_index(drop=True)


def build_annual_period_table(
    annual_df: pd.DataFrame,
    latest_start_year: int = 2023,
    mode: str = "raw",
) -> pd.DataFrame:
    spec = get_mode_spec(mode)
    annual_decomp = build_annual_decomposition_data(annual_df, mode=mode)
    latest_year = int(annual_decomp["year"].max())
    latest_label = format_last_year_label(latest_start_year, latest_year)

    periods = [
        ("1995-2004", 1995, 2004),
        ("2004-07", 2004, 2007),
        ("2010-19", 2010, 2019),
        ("2020-2022", 2020, 2022),
        (latest_label, latest_start_year, latest_year),
    ]

    rows = []
    for label, start_year, end_year in periods:
        sub = annual_decomp[(annual_decomp["year"] >= start_year) & (annual_decomp["year"] <= end_year)].copy()
        if sub.empty:
            continue
        component_means = {
            component: float(sub[component].mean()) for component in spec["table_components"]
        }
        total_lp = float(sub["total_lp"].mean())
        share_component = spec["share_component"]
        rows.append(
            {
                "period": label,
                "start": str(start_year),
                "end": str(end_year),
                **component_means,
                "total_lp": total_lp,
                spec["share_column"]: (
                    100 * component_means[share_component] / total_lp if total_lp != 0 else np.nan
                ),
                "capital_deepening_formula": float(sub["capital_deepening_formula"].mean()),
                "identity_gap_formula_mean": float(sub["identity_gap_formula"].mean()),
                "identity_gap_formula_max_abs": float(sub["identity_gap_formula"].abs().max()),
                "n_years": int(sub.shape[0]),
            }
        )

    period_df = pd.DataFrame(rows)
    validate_decomposition_identity(period_df, mode=mode)
    return period_df


def write_annual_decomposition_outputs(
    annual_df: pd.DataFrame,
    output_prefix: Path,
    latest_start_year: int = 2023,
    mode: str = "both",
) -> dict[str, Path]:
    output_paths = annual_decomposition_output_paths(output_prefix)
    modes = ["raw", "util_adjusted"] if mode == "both" else [mode]

    for selected_mode in modes:
        period_df = build_annual_period_table(
            annual_df,
            latest_start_year=latest_start_year,
            mode=selected_mode,
        )
        period_df.to_csv(output_paths[f"{selected_mode}_csv"], index=False)
        plot_decomposition(
            period_df,
            output_png=output_paths[f"{selected_mode}_png"],
            mode=selected_mode,
        )

    return {
        key: path
        for key, path in output_paths.items()
        if mode == "both" or key.startswith(mode)
    }


def main() -> None:
    args = parse_args()
    input_path = prepare_workbook(args.input, refresh_data=args.refresh_data)
    annual_df = load_annual_data(input_path)
    written = write_annual_decomposition_outputs(
        annual_df,
        output_prefix=args.output_prefix,
        latest_start_year=args.latest_start_year,
        mode=args.mode,
    )

    print(f"Latest annual observation in workbook: {annual_df['year'].max()}")
    for path in written.values():
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
