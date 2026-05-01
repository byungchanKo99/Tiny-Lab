You are generating mandatory data understanding visualizations.

This is the **VISUALIZE_DATA** step — runs immediately after DATA_DEEP_DIVE.
Goal: produce 3-5 PNG plots that make the data's structure and quality
visible at a glance, before idea refinement decides what to model.

Current iteration: {iter}
Project directory: {project_dir}

## Context

Read first:

- research/{iter}/.data_analysis.json — file paths, schemas, target column,
  quality issues
- research/{iter}/.domain_research.json — domain hints for what's worth
  highlighting (e.g., "gravity should be removed" → check accel_z mean
  visible in distribution plot)
- research/constraints.json — invariants/forbidden that may rule out some
  visualizations (e.g., privacy-sensitive features hidden)

## Required visualizations (5 types — auto-skip when not applicable)

Generate one PNG per applicable type. Auto-skip rules are explicit — write
a `skip_reason` for each one you don't generate.

### V1. Feature distribution grid (almost always applicable)

For every numeric column, a histogram + KDE. Use a `subplot` grid sized
`ceil(sqrt(N))` x `ceil(sqrt(N))`. Skip if N == 0 numeric columns.

- Filename: `data_viz/v1_distributions.png`
- Skip if: no numeric columns

### V2. Correlation heatmap (when 2+ numeric features)

Pearson correlation, annotate each cell, diverging colormap (e.g.,
`coolwarm`), `vmin=-1`, `vmax=1`. If a target column is identifiable,
add a separate row showing feature ↔ target correlations sorted by
magnitude.

- Filename: `data_viz/v2_correlation.png`
- Skip if: fewer than 2 numeric columns

### V3. Missing data matrix (always applicable when any column has NaN)

Heatmap of missing-value mask: rows = samples (use up to 200 evenly
spaced), columns = features. Below it, a small bar chart of `% missing`
per column.

- Filename: `data_viz/v3_missing.png`
- Skip if: no missing values across all columns

### V4. Target relationship (when target is identifiable)

For the target identified in `.data_analysis.json`:

- Regression target → scatter `target vs feature` for top 6 features by
  correlation magnitude (subplot 2x3)
- Classification target → violin/box plot of each top-6 feature grouped
  by class
- Time-series target → autocorrelation plot (ACF up to 50 lags) +
  target-vs-time line

- Filename: `data_viz/v4_target_relationship.png`
- Skip if: target not identified or has no usable features

### V5. Time-series profile (when temporal axis exists)

If any column looks like a timestamp / time index (datetime parseable, or
monotonic integer with regular delta):

- Subplot 1: target over time (or first numeric column if no target)
- Subplot 2: rolling mean (window = N/20) + rolling std overlay
- Subplot 3: simple seasonality decomposition (if `statsmodels` available)
  or hour/day-of-week boxplots if datetime

- Filename: `data_viz/v5_timeseries.png`
- Skip if: no temporal axis detected

## How to execute

You have **Bash, Read, Write** tools.

1. Use **Bash** to run a self-contained Python script that:
   - Installs deps as needed (`pip install -q pandas matplotlib seaborn`
     — and `statsmodels` only if attempting V5 decomposition)
   - Sets `matplotlib.use('Agg')` (non-interactive)
   - Reads the data files listed in `.data_analysis.json`
   - Generates each applicable PNG
2. Use **Write** to create the directory first (`mkdir -p` via Bash) and
   the manifest at the end.

Do NOT inline-edit existing files — these are read-only inputs at this
step. Only `data_viz/*.png` and `.data_viz_manifest.json` are writable.

## Manifest output

Write `research/{iter}/.data_viz_manifest.json`:

```json
{
  "generated": [
    {
      "id": "V1",
      "filename": "data_viz/v1_distributions.png",
      "what_it_shows": "1 sentence — what insight this surfaces",
      "domain_note": "anything from domain_research that this confirms or contradicts"
    }
  ],
  "skipped": [
    {
      "id": "V5",
      "skip_reason": "no temporal axis detected in any data file"
    }
  ],
  "summary": "1-2 sentences: what the data looks like at a glance"
}
```

## Hard rules

- **Every applicable plot must be generated.** Failing to produce V1
  when numeric columns exist counts as a state failure (no skip excuse).
- **Always write the manifest** even if every plot was skipped — explain
  why in the `summary`.
- **Use `matplotlib.use('Agg')`** — no GUI. If you forget, the script
  hangs on headless machines.
- **Save at 100-120 DPI**, `bbox_inches='tight'`. Each PNG should be
  legible without zoom and under 500 KB.
- **No data leaks in filenames.** Use generic names (`v1_distributions.png`,
  not `customer_age_histogram.png`) so the manifest's `what_it_shows`
  carries the meaning.
- **Self-contained script.** Install deps; don't rely on the project's
  environment.
