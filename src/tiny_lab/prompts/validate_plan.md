You are validating a research plan before execution begins.

Current iteration: {iter}
Project directory: {project_dir}

## Your Task

Read these files:

- research/{iter}/research_plan.json — the plan to validate
- research/constraints.json — invariants and goal
- shared/knowledge/ — accumulated prior research (if exists)
- research/{iter}/.domain_research.json — domain SOTA (if exists)

## Validation Criteria

## Engine-Enforced Plan Quality Contract

Use the shared plan quality contract below for all structural, baseline, DAG, schema, and evidence requirements that the engine will also enforce:

{plan_quality_contract}

### A. Constraint alignment (MUST pass)

For each phase in the plan:

1. Does it respect every invariant in constraints.json?
2. Does it stay within exploration_bounds.allowed?
3. Does it avoid exploration_bounds.forbidden?

If ANY phase violates constraints → REJECT.

### B. Goal connectivity (MUST pass)

1. Does at least one phase measure the metric defined in constraints.goal?
2. Can the final results be compared against constraints.goal.success_criteria?
3. Is there a clear path from phase_0 to goal evaluation?

If the plan cannot measure goal → REJECT.

### C. DAG validity (MUST pass)

1. Are all depends_on references valid phase IDs?
2. Is the dependency graph acyclic?
3. Does every phase have a "why" field?

If DAG is broken → REJECT.

### D. Prior research sufficiency

1. Does .domain_research.json have >= 3 SOTA references?
2. Are key methods from the literature considered in the plan?
3. Is there evidence that the plan builds on (not ignores) existing knowledge?

Score: sufficient / insufficient
If insufficient → REJECT with recommendation to return to CONTEXT_GATHER.

### E. Baseline coverage

1. Does the plan satisfy the baseline requirements from the shared plan quality contract?
2. Are baseline phases evaluated with the SAME metric as the main experiments?
3. Does the `baselines` list itself include explicit entries rather than relying only on checklist claims?

Score: complete / partial / missing
If missing → REJECT.

### F. Experimental rigor

1. Does the plan satisfy every experimental rigor requirement from the shared plan quality contract?
2. Are statistics, reproducibility metadata, code provenance, baseline comparison, ablation/feature-importance/sensitivity, evaluation protocol, error analysis, and leakage evidence materialized in result schemas where applicable?
3. Is there an explicit leakage audit for train/test, target, temporal, group, duplicate, and preprocessing leakage where applicable?

{evidence_contract}

Score: rigorous / adequate / weak
If weak → REJECT.

### G. Phase logic

1. Is the phase ordering sensible? (preprocessing before modeling, baselines before advanced)
2. Are dependencies properly declared?
3. Are phase names and descriptions clear?

Score: clear / acceptable / confused

## Output

Write research/{iter}/.plan_validation.json:

```json
{
  "verdict": "APPROVE or REJECT",
  "checks": {
    "constraint_alignment": "pass or fail",
    "goal_connectivity": "pass or fail",
    "dag_validity": "pass or fail",
    "prior_research": "sufficient or insufficient",
    "baseline_coverage": "complete or partial or missing",
    "experimental_rigor": "rigorous or adequate or weak",
    "phase_logic": "clear or acceptable or confused"
  },
  "issues": [
    {
      "criterion": "which check failed",
      "severity": "blocker or warning",
      "description": "what's wrong",
      "suggestion": "how to fix it"
    }
  ],
  "required_fixes": ["list of things that MUST change before approval"]
}
```

## Decision rules

- ANY blocker in A, B, or C → REJECT (non-negotiable)
- D insufficient → REJECT (need more research first)
- E missing → REJECT (no baselines = no valid comparison)
- F weak → REJECT (results won't be trustworthy)
- Missing reproducibility metadata, baseline comparison evidence, or leakage audit in an ML experiment → REJECT
- Leakage audit mentioned only in prose but absent from result schemas → REJECT
- All checks pass or have only warnings → APPROVE

## Important

- Be strict but fair. The goal is to catch real problems, not nitpick.
- If the plan is 90% good with one missing baseline, REJECT with a specific fix —
  don't make the author guess what's wrong.
- Warnings are informational. Only blockers cause REJECT.
