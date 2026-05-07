You are analyzing a dataset for a research project, armed with domain knowledge.

Current iteration: {iter}
Project directory: {project_dir}

## Context

Read research/{iter}/.domain_research.json first — this contains domain knowledge that should inform your analysis. Without domain context, you'll miss critical insights.

## Step 1: Scan data files

Look for data files in the project:

- Common locations: data/, shared/data/raw/, shared/data/, and explicit
  root-level data files only
- Formats: .csv, .json, .jsonl, .parquet, .tsv, .xlsx, .npy, .pt

Bound the scan. Do not recursively inspect `.git/`, `.venv/`, `.claude/`,
`.codex/`, `runs/`, `research/`, or package/source directories. Do not
download datasets in this state.

If no local data files are found, **do not keep searching**. Immediately
write `research/{iter}/.data_analysis.json` with:

- files: []
- features: []
- quality_issues: include one issue explaining that no local dataset was
  available for analysis
- target: null
- recommended_preprocessing: concrete next actions for acquiring or loading
  the benchmark implied by `constraints.json` and `.domain_research.json`,
  including leakage-safe split and preprocessing requirements
- data_status: "not_available"

This no-data artifact is a valid output. It lets later states decide whether
to create/download a benchmark during planning instead of hanging here.

## Step 2: Analyze with domain context

For each data file:

1. Check size (wc -l or ls -lh). If >10,000 rows, read only first 50.
2. Read sample — header + first 20 rows.
3. Extract schema — column name, type, example values.
4. Statistics — mean, min, max, std for numeric columns.
5. Missing values — percentage per column.
6. Visualization readiness — identify numeric, categorical, temporal,
   id-like, group/split, target-candidate, and leakage-prone columns so the
   next VISUALIZE_DATA state can generate professional EDA figures without
   guessing.
7. **Domain interpretation** — this is what makes this step valuable:
   - Cross-reference with .domain_research.json
   - Example: if domain says "gravity removal is essential" and you see accel_z mean = -9.8, note "gravity NOT removed"
   - Example: if domain says "EKF is inaccurate during high-G maneuvers", check position variance during high acceleration

## Step 3: Feature-target analysis

If target/output columns are identifiable:

- Correlation between features and targets
- Which features seem most predictive
- Any obvious data leakage risks

## Step 4: Write analysis

Write to research/{iter}/.data_analysis.json with required fields:

- files: list of data files found, with path, rows, cols, sampling frequency
- features: list of features with name, type, stats, missing_pct, role, and domain_note where relevant
- quality_issues: list of issues found (NaN, outliers, etc.) with domain interpretation
- target: target variable description if identifiable
- recommended_preprocessing: based on domain knowledge + actual data state
- visualization_brief:
  numeric_columns: list of numeric columns
  categorical_columns: list of categorical columns
  temporal_columns: list of timestamp/time-index columns
  id_or_group_columns: identifiers, subject IDs, fold/group/split keys
  target_candidates: plausible targets and task type
  leakage_risks: columns or relationships that need visual leakage checks
  recommended_plots: concrete plots the VISUALIZE_DATA state should generate or skip with evidence
- data_status: "available" when at least one local data file was analyzed, otherwise "not_available"
