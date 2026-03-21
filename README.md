# Productivity Decomposition

Small reproducible workflow for two Fernald TFP-based charts built from the
quarterly workbook in `data/quarterly_tfp.xlsx`.

## Contents

- `scripts/reproduce_tfp_decomposition.py`
  Builds the stacked bar decomposition for average contributions to U.S. output
  per hour. By default it uses the custom period buckets:
  `1995-2004`, `2004-07`, `2010-19`, `2020-2022`, and `2023-latest`.
- `scripts/replicate_productivity_chart.py`
  Builds the quarterly labor-productivity growth drivers chart with a clean,
  unbranded style and exports the plotted data to CSV.
- `output/`
  Default destination for generated charts and CSVs.

## Data

- Source workbook: `data/quarterly_tfp.xlsx`
- The workbook is the Fernald quarterly TFP file from the San Francisco Fed.
- Both scripts refresh this workbook from the official SF Fed download URL by
  default before running.

## Usage

Run the TFP decomposition chart:

```bash
python scripts/reproduce_tfp_decomposition.py
```

Use workbook summary periods instead of the custom chart buckets:

```bash
python scripts/reproduce_tfp_decomposition.py --period-source workbook
```

Run the quarterly productivity drivers chart:

```bash
python scripts/replicate_productivity_chart.py
```

Use the cached local workbook instead of refreshing from SF Fed:

```bash
python scripts/reproduce_tfp_decomposition.py --no-refresh-data
python scripts/replicate_productivity_chart.py --no-refresh-data
```

## Outputs

Default files written to `output/`:

- `output/tfp_decomposition.png`
- `output/tfp_decomposition.csv`
- `output/productivity_growth_drivers.png`
- `output/productivity_growth_drivers.csv`

## Notes

- Both scripts read the `quarterly` sheet with `header=1`, matching the Fernald
  workbook layout.
- The productivity drivers chart uses 4-quarter rolling averages by default.
- The decomposition script automatically extends the final custom bar from
  `2023Q1` through the latest quarter in the workbook.
