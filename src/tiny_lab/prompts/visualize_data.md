You are generating mandatory data understanding visualizations.

This is the **VISUALIZE_DATA** step — runs immediately after DATA_DEEP_DIVE.
Goal: produce a professional data-understanding visualization packet before
idea refinement decides what to model. This is not decorative plotting. Behave
like a senior empirical ML researcher doing first-pass EDA: make the data
structure, quality risks, target relationships, leakage hazards, and modeling
implications visible at a glance.

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

Before plotting, infer from `.data_analysis.json`:

- data modality: tabular, time-series, image-like, text-like, graph-like, or mixed
- numeric/categorical/temporal/id-like columns
- target candidates and task type
- leakage-prone columns, split columns, group columns, identifiers, timestamps
- domain-specific checks implied by `.domain_research.json`

Each generated figure must answer a concrete visual question and must state
what modeling decision it affects. Avoid generic "look at the data" captions.

### V1. Feature distribution grid (almost always applicable)

For every numeric column, a histogram + KDE. Use a `subplot` grid sized
`ceil(sqrt(N))` x `ceil(sqrt(N))`. Skip if N == 0 numeric columns.

- Filename: `data_viz/v1_distributions.png`
- Skip if: no numeric columns
- Research question: What scale, skew, outlier, clipping, or transformation
  problems will affect preprocessing and baseline choice?

### V2. Correlation heatmap (when 2+ numeric features)

Pearson correlation, annotate each cell, diverging colormap (e.g.,
`coolwarm`), `vmin=-1`, `vmax=1`. If a target column is identifiable,
add a separate row showing feature ↔ target correlations sorted by
magnitude.

- Filename: `data_viz/v2_correlation.png`
- Skip if: fewer than 2 numeric columns
- Research question: Which dependencies, redundancy, collinearity, or possible
  leakage relationships must the plan account for?

### V3. Missing data matrix (always applicable when any column has NaN)

Heatmap of missing-value mask: rows = samples (use up to 200 evenly
spaced), columns = features. Below it, a small bar chart of `% missing`
per column.

- Filename: `data_viz/v3_missing.png`
- Skip if: no missing values across all columns
- Research question: Is missingness random noise, structured by sample/feature,
  or a domain/process artifact that could bias evaluation?

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
- Research question: Which variables plausibly carry signal, which relationships
  are nonlinear, and which apparent signals might be leakage?

### V5. Time-series profile (when temporal axis exists)

If any column looks like a timestamp / time index (datetime parseable, or
monotonic integer with regular delta):

- Subplot 1: target over time (or first numeric column if no target)
- Subplot 2: rolling mean (window = N/20) + rolling std overlay
- Subplot 3: simple seasonality decomposition (if `statsmodels` available)
  or hour/day-of-week boxplots if datetime

- Filename: `data_viz/v5_timeseries.png`
- Skip if: no temporal axis detected
- Research question: Are trend, seasonality, autocorrelation, drift, or temporal
  split hazards visible before modeling?

## Additional professional checks

When the data modality calls for it, add extra panels inside the applicable
figure rather than creating uncontrolled extra files:

- categorical features: top-category bars, rare-category counts, class balance
- grouped or repeated observations: group-size distribution and target-by-group
- identifiers or leakage candidates: uniqueness bars and target leakage notes
- image-like arrays: sample grid plus channel/intensity histogram
- text-like records: length distribution and label-by-length view

Do not use screenshots or notebook exports. Use clean Matplotlib/Seaborn figures
with readable axis labels, titles, legends, and consistent sizing.

## How to execute

You have **Bash, Read, Write** tools.

1. Use **Bash** to run a self-contained Python script that:
   - Imports pandas, matplotlib, and seaborn if available; only install deps if
     imports fail and the environment permits it. Do not stall on package
     installation.
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
      "visual_question": "What scale, skew, outlier, or clipping issues affect preprocessing?",
      "what_it_shows": "1 sentence — what insight this surfaces",
      "why_it_matters": "1 sentence — why this matters for a rigorous ML study",
      "modeling_implication": "1 sentence — how this changes preprocessing, baselines, split, metric, or phase planning",
      "domain_note": "anything from domain_research that this confirms or contradicts",
      "supported_decision": "the concrete next research/planning decision this figure supports",
      "caveats": "what this plot cannot prove"
    }
  ],
  "skipped": [
    {
      "id": "V5",
      "skip_reason": "no temporal axis detected in any data file",
      "evidence_from_data_analysis": "which .data_analysis field supports the skip"
    }
  ],
  "researcher_readout": {
    "key_patterns": ["most important visible structures, not generic descriptions"],
    "quality_risks": ["missingness, outliers, leakage, imbalance, drift, or 'none observed' with evidence"],
    "modeling_implications": ["how the plots should shape preprocessing, baselines, metrics, and phases"],
    "followup_checks": ["specific analyses the plan should run next"],
    "recommended_first_modeling_move": "one concrete first modeling/evaluation move justified by the plots"
  },
  "summary": "1-2 sentences: what the data looks like at a glance"
}
```

## Hard rules

- **Every applicable plot must be generated.** Failing to produce V1
  when numeric columns exist counts as a state failure (no skip excuse).
- **Account for all V1-V5 IDs.** Each required visualization must appear in
  either `generated` or `skipped` with evidence-based reasoning.
- **If data is available, write `researcher_readout`.** It must connect the
  visual evidence to preprocessing, baseline, metric, split, or next-phase
  decisions.
- **Always write the manifest** even if every plot was skipped — explain
  why in the `summary`.
- **Use `matplotlib.use('Agg')`** — no GUI. If you forget, the script
  hangs on headless machines.
- **Save at 100-120 DPI**, `bbox_inches='tight'`. Each PNG should be at
  least 640x480 pixels, legible without zoom, and preferably under 500 KB.
- **No data leaks in filenames.** Use generic names (`v1_distributions.png`,
  not `customer_age_histogram.png`) so the manifest's `what_it_shows`
  carries the meaning.
- **Self-contained script.** Install deps; don't rely on the project's
  environment.
