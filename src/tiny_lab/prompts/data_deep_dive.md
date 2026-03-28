You are analyzing a dataset for a research project, armed with domain knowledge.

Current iteration: {iter}
Project directory: {project_dir}

## Context

Read research/{iter}/.domain_research.yaml first — this contains domain knowledge that should inform your analysis. Without domain context, you'll miss critical insights.

## Step 1: Scan data files

Look for data files in the project:

- Common locations: data/, shared/data/raw/, the project root
- Formats: .csv, .json, .jsonl, .parquet, .tsv, .xlsx, .npy, .pt

## Step 2: Analyze with domain context

For each data file:

1. Check size (wc -l or ls -lh). If >10,000 rows, read only first 50.
2. Read sample — header + first 20 rows.
3. Extract schema — column name, type, example values.
4. Statistics — mean, min, max, std for numeric columns.
5. Missing values — percentage per column.
6. **Domain interpretation** — this is what makes this step valuable:
   - Cross-reference with .domain_research.yaml
   - Example: if domain says "gravity removal is essential" and you see accel_z mean = -9.8, note "gravity NOT removed"
   - Example: if domain says "EKF is inaccurate during high-G maneuvers", check position variance during high acceleration

## Step 3: Feature-target analysis

If target/output columns are identifiable:

- Correlation between features and targets
- Which features seem most predictive
- Any obvious data leakage risks

## Step 4: Write analysis

Write to research/{iter}/.data_analysis.yaml with required fields:

- files: list of data files found, with path, rows, cols, sampling frequency
- features: list of features with name, type, stats, and domain_note where relevant
- quality_issues: list of issues found (NaN, outliers, etc.) with domain interpretation
- target: target variable description if identifiable
- recommended_preprocessing: based on domain knowledge + actual data state
