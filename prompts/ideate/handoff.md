You are writing the handoff document — the bridge between ideate and the
next research preset.

Project directory: {project_dir}

## Context

Read research/hypothesis.json — the selected hypothesis with handoff_constraints.

## Your Task

Write a single markdown file research/.handoff.md that the user can read in
under a minute and act on.

## Required sections

```markdown
# Ideate → Next Preset Handoff

## Selected Hypothesis

**H1**: <one sentence>
**H0**: <one sentence>
**Metric**: <name, direction, unit>
**Minimum evidence for H1**: <one sentence>

## Why this candidate won

<2-3 sentences from rationale + evaluation matrix>

## Recommended next command

\`\`\`bash

# 1. Initialize a new project (or in-place re-init) with the next preset:

tiny-lab init --preset <next_preset>

# 2. Apply the handoff constraints (skips SHAPE_FULL):

cat > research/handoff_constraints.json <<'EOF'
<paste handoff_constraints object as JSON>
EOF
tiny-lab shape research/handoff_constraints.json

# 3. Run:

tiny-lab run --model sonnet
\`\`\`

## Carry-over checklist

- [ ] handoff_constraints.json written
- [ ] shared/knowledge/ notes carried (if any)
- [ ] hypothesis.json archived for traceability

## Rejected candidates (for traceability)

| id  | reason for rejection |
| --- | -------------------- |
| C2  | ...                  |
| C3  | ...                  |
```

## Important

- Output exactly one file: research/.handoff.md
- Use the actual values from hypothesis.json (do NOT leave placeholders).
- The bash block must be runnable as-is — embed the real next_preset name
  and the real JSON object (compact but valid).
