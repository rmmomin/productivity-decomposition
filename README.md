# Productivity Decomposition

Small reproducible workflow for two Fernald TFP-based charts built from the
quarterly workbook in `data/quarterly_tfp.xlsx`.

## Contents

- `scripts/reproduce_tfp_decomposition.py`
  Builds the stacked bar decomposition for average contributions to U.S. output
  per hour. By default it uses the custom period buckets:
  `1995-2004`, `2004-07`, `2010-19`, `2020-2022`, and `2023-latest`.
  It supports both the existing raw decomposition and a parallel
  utilization-adjusted decomposition via `--mode util_adjusted`.
- `scripts/replicate_productivity_chart.py`
  Builds the quarterly labor-productivity growth drivers chart with a clean,
  unbranded style and exports the plotted data to CSV.
- `scripts/update_productivity_decomposition.py`
  Builds the summary decomposition chart, a quarterly decomposition chart, and
  a bridge table that reconciles the recent-period decomposition measures. It
  now writes both the raw and utilization-adjusted decomposition outputs plus
  annual raw/adjusted TFP charts.
- `scripts/plot_annual_tfp_series.py`
  Builds annual raw TFP and utilization-adjusted TFP charts directly from the
  workbook's `annual` tab and exports matching CSVs.
- `output/`
  Default destination for generated charts and CSVs.

## Data

- Source workbook: `data/quarterly_tfp.xlsx`
- The workbook is the Fernald quarterly TFP file from the San Francisco Fed.
- Both scripts refresh this workbook from the official SF Fed download URL by
  default before running.

## Usage

The raw decomposition keeps the existing three-part identity:

```text
total_lp = capital_deepening + labor_composition + tfp
```

The utilization-adjusted decomposition keeps the accounting identity explicit by
separating utilization from adjusted TFP:

```text
total_lp = capital_deepening + labor_composition + utilization + tfp_util_adjusted
```

Run the TFP decomposition chart:

```bash
python scripts/reproduce_tfp_decomposition.py
```

Run the utilization-adjusted TFP decomposition chart:

```bash
python scripts/reproduce_tfp_decomposition.py --mode util_adjusted
```

Use workbook summary periods instead of the custom chart buckets:

```bash
python scripts/reproduce_tfp_decomposition.py --period-source workbook
python scripts/reproduce_tfp_decomposition.py --period-source workbook --mode util_adjusted
```

Run the quarterly productivity drivers chart:

```bash
python scripts/replicate_productivity_chart.py
```

Run the annual raw and utilization-adjusted TFP charts:

```bash
python scripts/plot_annual_tfp_series.py
```

Run the merged summary + quarterly decomposition workflow:

```bash
python scripts/update_productivity_decomposition.py
```

That merged workflow writes both the raw and utilization-adjusted summary and
quarterly decomposition outputs, plus the annual raw and utilization-adjusted
TFP charts, in one run.

Use the cached local workbook instead of refreshing from SF Fed:

```bash
python scripts/reproduce_tfp_decomposition.py --no-refresh-data
python scripts/replicate_productivity_chart.py --no-refresh-data
python scripts/update_productivity_decomposition.py --no-refresh-data
```

## Outputs

Default files written to `output/`:

- `output/tfp_decomposition.png`
- `output/tfp_decomposition.csv`
- `output/tfp_decomposition_util_adjusted.png`
- `output/tfp_decomposition_util_adjusted.csv`
- `output/productivity_growth_drivers.png`
- `output/productivity_growth_drivers.csv`
- `output/productivity_decomposition_summary.png`
- `output/productivity_decomposition_summary.csv`
- `output/productivity_decomposition_summary_util_adjusted.png`
- `output/productivity_decomposition_summary_util_adjusted.csv`
- `output/productivity_decomposition_quarterly.png`
- `output/productivity_decomposition_quarterly.csv`
- `output/productivity_decomposition_quarterly_util_adjusted.png`
- `output/productivity_decomposition_quarterly_util_adjusted.csv`
- `output/tfp_annual_raw.png`
- `output/tfp_annual_raw.csv`
- `output/tfp_annual_util_adjusted.png`
- `output/tfp_annual_util_adjusted.csv`
- `output/productivity_decomposition_bridge.csv`

## Notes

- Both scripts read the `quarterly` sheet with `header=1`, matching the Fernald
  workbook layout.
- The productivity drivers chart uses 4-quarter rolling averages by default.
- The decomposition script automatically extends the final custom bar from
  `2023Q1` through the latest quarter in the workbook.
- The adjusted figure separates utilization from utilization-adjusted TFP
  instead of folding utilization back into the TFP bar.
- The annual TFP charts use the workbook's `annual` tab directly rather than
  annualizing the quarterly data inside this repo.
