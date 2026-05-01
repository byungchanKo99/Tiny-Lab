You are generating mandatory candidate-comparison visualizations.

This is the **VISUALIZE_CANDIDATES** step — runs after EVALUATE_MATRIX,
before SELECT. Goal: make the tradeoff structure of the candidate set
visible so the user (or the autonomous selector) can decide with full
information, not just a weighted scalar.

Current iteration: {iter}
Project directory: {project_dir}

## Context

Read first:

- research/{iter}/.diverge.json — candidate definitions (id, label,
  hypothesis, methodology_family, risk_payoff)
- research/{iter}/.evaluation_matrix.json — scored_candidates,
  pareto_optimal_ids, ranking, recommendation
- research/{iter}/.gap_analysis.json (optional, only present in
  ideate-deep) — ranked_opportunities; if present, generate V4

## Required visualizations

Generate one PNG per applicable type. Lite path produces V1-V3, deep path
adds V4.

### V1. Score radar chart (always)

For every candidate, plot novelty/feasibility/falsifiability on a 3-axis
radar (polar plot). Overlay all candidates with low alpha; highlight
Pareto-optimal candidates with thick stroke; annotate the recommended top-1.

- Filename: `ideate_viz/v1_radar.png`
- Required: yes (no skip)

### V2. Pareto scatter matrix (always)

A 1x3 row of 2D scatters: (novelty × feasibility), (novelty ×
falsifiability), (feasibility × falsifiability). Each point labeled with
candidate id. Pareto-optimal candidates marked with a star marker;
non-Pareto with circle. The recommended top-1 colored distinctly.

- Filename: `ideate_viz/v2_pareto.png`
- Required: yes (no skip)

### V3. Weighted total bar (always)

Horizontal bar chart, candidates ordered by `weighted_total` descending.
Each bar shows the total; overlay a darker segment for
`ref_verification_penalty` so reviewers see how much of the score was
deducted for unverified citations. Annotate Pareto-optimal candidates
with `⌬` and the top-1 with `★` next to the label.

- Filename: `ideate_viz/v3_weighted_total.png`
- Required: yes (no skip)

### V4. Gap landscape (deep only — when .gap_analysis.json exists)

Bubble chart:

- X axis: opportunity_score from gap_analysis
- Y axis: gap type ordering (`explicit` at bottom, `implicit` at top)
- Bubble size: number of candidates targeting that gap (count from
  `candidates[].targeted_gap_id`)
- Bubble color: average novelty of candidates targeting it (or grey if
  uncovered)

Overlay text annotations: gap_id and 4-5 word truncation of the
research_question. Mark uncovered gaps with an empty (white-fill) bubble.

- Filename: `ideate_viz/v4_gap_landscape.png`
- Skip if: `.gap_analysis.json` does not exist (lite ideate run)

## How to execute

You have **Bash, Read, Write** tools.

1. Use **Bash** to run a self-contained Python script that:
   - Installs deps (`pip install -q matplotlib numpy`) — no seaborn needed
   - Sets `matplotlib.use('Agg')`
   - Reads the JSON inputs
   - Generates the required PNGs
2. Create the directory first via Bash `mkdir -p research/{iter}/ideate_viz`.
3. Write the manifest at the end.

## Manifest output

Write `research/{iter}/.candidate_viz_manifest.json`:

```json
{
  "generated": [
    {
      "id": "V1",
      "filename": "ideate_viz/v1_radar.png",
      "what_it_shows": "1 sentence",
      "key_takeaway": "biggest tradeoff visible in this view"
    }
  ],
  "skipped": [
    {
      "id": "V4",
      "skip_reason": "no gap_analysis.json (lite ideate)"
    }
  ],
  "viewer_summary": "2-3 sentences distilling what the viewer should notice across all charts"
}
```

## Hard rules

- **V1, V2, V3 are mandatory.** Failing any of them is a state failure.
- **V4 must be generated whenever `.gap_analysis.json` exists.** Skip
  only when the file is genuinely absent (lite ideate run).
- **Use `matplotlib.use('Agg')`.**
- **DPI 100-120, `bbox_inches='tight'`, under 500 KB each.**
- **Color choices**: use a colorblind-safe palette (e.g., `viridis` /
  `tab10`). The recommended top-1 should use a distinct hue (not just
  size or marker — accessibility).
- **Self-contained script** with its own `pip install`.
- **No invented scores.** Use only the values present in
  `.evaluation_matrix.json`. If a candidate has missing axis scores, plot
  it but mark with `?` in legend.
