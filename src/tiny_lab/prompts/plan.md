You are creating a research plan for an AI experiment.

Current iteration: {iter}
Project directory: {project_dir}

## Context

Read all three understanding artifacts:

- research/{iter}/.domain_research.yaml — SOTA, preprocessing, metrics, pitfalls
- research/{iter}/.data_analysis.yaml — data characteristics, quality issues
- research/{iter}/.idea_refined.yaml — concrete goal, inputs, outputs, metric, constraints

## Your Task

Create research/{iter}/research_plan.yaml — the execution blueprint.

## Plan structure

The plan must have:

1. **name** and **description**

2. **background** — problem, goal, data info, constraints, references (from understanding artifacts)

3. **metric** — name, direction, target (from idea_refined)

   - If the research is qualitative (no numeric metric), use **goal** with success_criteria instead

4. **phases** — ordered list of research phases. Each phase must have:
   - **id**: unique identifier (phase_0, phase_1, ...)
   - **name**: human-readable name
   - **why**: domain-grounded reason this phase is needed. No "why" = might get skipped.
   - **type**: script | optimize | manual
   - **depends_on**: list of phase IDs that must complete first
   - **methodology**: step-by-step instructions for AI to generate code
   - **expected_outputs**: files + report with JSON schema
   - **status**: "pending"

## Critical principles (from RESEARCH_PLAN_WORKFLOW.md)

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

## Phase ordering guidance

Typical ML experiment order:

1. Data preprocessing (always first if data needs cleaning)
2. Physical/statistical baseline (ML-free reference point)
3. Feature importance / ablation (understand what matters)
4. Architecture comparison (which model family works best)
5. Hyperparameter tuning (optimize the winner)
6. Final evaluation / cross-validation
7. Robustness checks (different data splits, hardware, etc.)

Not all phases are needed. The domain research and idea determine which are relevant.

## Write the plan

Write to research/{iter}/research_plan.yaml with at least: name, phases (each with id, name, why, type, methodology, expected_outputs, status).
