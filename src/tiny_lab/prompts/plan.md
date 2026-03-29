You are creating a research plan for an AI experiment.

Current iteration: {iter}
Project directory: {project_dir}

## Context

Read all three understanding artifacts:

- research/{iter}/.domain_research.json — SOTA, preprocessing, metrics, pitfalls
- research/{iter}/.data_analysis.json — data characteristics, quality issues
- research/{iter}/.idea_refined.json — concrete goal, inputs, outputs, metric, constraints

## Your Task

Create research/{iter}/research_plan.json — the execution blueprint.

## Plan structure

The plan must have:

1. **name** and **description**

2. **background** — problem, goal, data info, constraints, references (from understanding artifacts)

3. **metric** — name, direction, target (from idea_refined)

   - If the research is qualitative (no numeric metric), use **goal** with success_criteria instead

4. **formal_notation** — LaTeX formulations for:

   - Problem definition: what is the input/output mapping?
   - Target variable: $\hat{y} = f_\theta(X)$ with explicit dimensions
   - Loss function: $\mathcal{L} = ...$
   - Evaluation metric: formal definition with formula
   - Example: if predicting position from IMU: $\hat{p}_t = f_\theta(X_{t-k:t})$ where $X \in \mathbb{R}^{T \times d}$

5. **phases** — ordered list of research phases. Each phase must have:

   - **id**: unique identifier (phase_0, phase_1, ...)
   - **name**: human-readable name
   - **why**: domain-grounded reason this phase is needed. No "why" = might get skipped.
   - **type**: script | optimize | manual
   - **depends_on**: list of phase IDs that must complete first
   - **methodology**: step-by-step instructions for AI to generate code
   - **expected_outputs**: files + report with JSON schema
   - **visualization**: list of plots this phase must generate (e.g., "trajectory_comparison.png", "error_distribution.png"). Every phase should have at least one visualization.
   - **status**: "pending"

6. **baselines** — explicit list of baselines to compare against:

   - Physical/statistical baselines (no ML)
   - Simple ML baselines (linear, decision tree)
   - SOTA baselines from domain research (if reproducible)
   - Each baseline must have a dedicated phase or be part of one

7. **experiment_checklist** — self-audit of experiment completeness:
   - Has a non-ML baseline? (yes/no)
   - Has statistical measures beyond mean? (std, CI, significance test)
   - Has ablation study or feature importance?
   - Has cross-validation or multiple splits?
   - Has error analysis phase?
   - Missing items should be added as phases

## Critical principles

1. Every phase MUST have a file path for its output
   BAD: "record the results"
   GOOD: "write to research/results/phase_1.json"

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

7. Results must include statistics
   Not just "ATE = 50m" but "ATE = 50.3 ± 2.1m (mean ± std over 5 runs)"
   Require std, min, max, and CI where applicable in expected_outputs schemas.

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

Write to research/{iter}/research_plan.json with at least: name, formal_notation, baselines, experiment_checklist, phases (each with id, name, why, type, methodology, expected_outputs, visualization, status).
