You are creating a research plan for an AI experiment.

Current iteration: {iter}
Project directory: {project_dir}

## Context

Read all three understanding artifacts:

- research/{iter}/.domain_research.json — SOTA, preprocessing, metrics, pitfalls
- research/{iter}/.data_analysis.json — data characteristics, quality issues
- research/{iter}/.data_viz_manifest.json and research/{iter}/data_viz/*.png —
  first-pass EDA evidence, quality risks, and modeling implications
- research/{iter}/.idea_refined.json — concrete goal, inputs, outputs, metric, constraints

## Your Task

Create research/{iter}/research_plan.json — the execution blueprint.

## Plan structure

Use the shared plan quality contract below for all engine-enforced structural, baseline, DAG, schema, and evidence requirements:

{plan_quality_contract}

The plan must also have:

1. **name** and **description**

2. **background** — problem, goal, data info, constraints, references (from understanding artifacts)

   - Include the most important visual patterns from `.data_viz_manifest.json`
     and explain how they shaped preprocessing, split, baseline, metric, or
     error-analysis phases.

3. **metric** — name, direction, target (from idea_refined)

   - If the research is qualitative (no numeric metric), use **goal** with success_criteria instead

4. **formal_notation** — LaTeX formulations for:

   - Problem definition: what is the input/output mapping?
   - Target variable: $\hat{y} = f_\theta(X)$ with explicit dimensions
   - Loss function: $\mathcal{L} = ...$
   - Evaluation metric: formal definition with formula
   - Example: if predicting position from IMU: $\hat{p}_t = f_\theta(X_{t-k:t})$ where $X \in \mathbb{R}^{T \times d}$

5. **phases** — ordered list of research phases following the shared plan quality contract.

   - Every new executable phase must start with `"status": "pending"` so PHASE_SELECT will run it.

6. **baselines** — explicit list of baselines to compare against, following the shared plan quality contract:

   - Physical/statistical baselines (no ML)
   - Simple ML baselines (linear, decision tree)
   - SOTA baselines from domain research (if reproducible)
   - Each baseline must have a dedicated phase or be part of one

7. **experiment_checklist** — self-audit of experiment completeness:
   - Follow every checklist item named by the shared plan quality contract.
   - Missing items should be added as phases, schemas, or baseline entries.

## Critical principles

1. Every phase MUST have a file path for its output
   BAD: "record the results"
   GOOD: "write to research/{iter}/results/phase_1.json"

2. JSON schema MUST be defined for every report
   The schema determines what the AI measures. If "n_params" is in the schema, it counts parameters. If not, it doesn't.

3. "Why" determines execution priority
   A phase without "why" can be skipped. Every phase needs domain justification.

4. Reports must cross-reference
   phase_1.json has baseline = 518m → phase_3.json references this value.

5. Code reuse must be explicit
   If phase_3 needs phase_0's preprocessing function, say so in methodology.

6. Every phase MUST have visualization
   Even preprocessing: show before/after distributions, correlation heatmaps, etc.

7. The plan must react to initial EDA visual evidence
   If `.data_viz_manifest.json` reports quality risks, target relationships,
   leakage candidates, imbalance, drift, or missingness, include phases or
   schema fields that directly test those risks. Do not ignore the
   `researcher_readout`.

8. Results must materialize the shared evidence contract
   Not just "ATE = 50m" but "ATE = 50.3 ± 2.1m (mean ± std over 5 runs)".
   Every experimental report schema must request the applicable fields from this shared contract:

{evidence_contract}

## Phase ordering guidance

Typical ML experiment order:

1. Data preprocessing (always first if data needs cleaning)
2. Physical/statistical baseline (ML-free reference point)
3. Simple ML baseline (linear regression, etc.)
4. Feature importance / ablation (understand what matters)
5. Architecture comparison (which model family works best)
6. Hyperparameter tuning (optimize the winner)
7. Final evaluation / cross-validation
8. Error analysis (where does it fail? domain shift? edge cases?)
9. Robustness checks (different data splits, hardware, etc.)

Not all phases are needed. The domain research and idea determine which are relevant.

## Write the plan

Write to research/{iter}/research_plan.json with at least: name, formal_notation, baselines, experiment_checklist, phases (each with id, name, why, type, methodology, expected_outputs, visualization, status). Use `"status": "pending"` for phases that still need execution; do not use `"todo"` unless you are preserving an existing plan that already used it.
