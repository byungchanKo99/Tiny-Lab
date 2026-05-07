# Tiny-Lab Runtime Research Issues

Captured: 2026-05-05 04:10 KST
Updated: 2026-05-05 04:31 KST

## Context

Real project path:

`/Users/byungchanko/Downloads/scm_research`

Run intent:

Use default Tiny-Lab with the Claude backend to run an SCM forecasting research
loop. The run should analyze local data, inspect prior research artifacts, create
rich visualizations, iterate on hypotheses, and continue until the configured
max iteration limit instead of stopping after one cycle.

Current paused state after manual deterministic repair:

```json
{
  "current_iteration": 1,
  "state": "PHASE_RUN",
  "current_phase_id": "phase_3_lgbm_ablation",
  "resumable": true,
  "consecutive_failures": 0,
  "phase_retries": 0,
  "session_id": null
}
```

Completed in this run:

- `phase_0_preprocess`
- `phase_1_heuristic_baselines`
- `phase_2_simple_ml_baseline`

Currently repaired but not yet rerun:

- `phase_3_lgbm_ablation`

## Fix Pass Status

Implemented after this run:

- Codex and Claude backend prompts now travel through stdin instead of argv, including the interactive Claude path.
- Active backend child tracking was added via `research/.active_backend.json`; `status` shows it, `ps` reports it, and `stop` sends SIGINT to it.
- `repair-state` provides auditable state repair without direct `.state.json` edits.
- Repeated `HYPOTHESIS_UPDATE` completion now checks freshness against the current phase id and rejects stale `.hypothesis_log.json` reuse.
- Previous-results prompt context now uses canonical planned report artifacts and excludes duplicate `phase_*.json` aliases that do not match the plan's expected report path.
- Result validation now accepts diagnostic zero counts, permits non-probability sensitivity comparison values above 1, and type-checks Tiny-Lab shorthand schemas such as `{"table": [{"metric_std": "float"}]}`.
- Malformed explicit schema definitions such as `items: []` still remain errors after shorthand normalization.
- Backend-unavailable failures are separated from research failures, so auth/quota/rate-limit/timeout/trusted-directory failures stop without consuming research retries.
- Engine tests were updated to fake backend registry calls instead of relying on obsolete `subprocess.run` monkeypatches after the backend moved to `Popen + stdin`.

Still open or only partially mitigated:

- Field-name heuristics are narrower but still exist; a fully typed evidence-contract validator remains the better long-term fix.
- Generic `beats_baseline` remains semantically risky. Prompts and plan/schema repair should prefer explicit scoped fields such as `beats_emro`, `beats_reference_baseline`, or `beats_best_baseline`.
- Mechanical JSON repair exists through targeted artifact-fix prompts and deterministic fallbacks for some artifacts, but there is not yet a general `repair-artifact` command with provenance.
- Backend streaming, artifact polling while the backend is still running, and heartbeat logs are not implemented yet.
- Visualization validation now checks manifest structure, applicability, dimensions for data-understanding plots, and invalid/empty PNGs, but it still does not judge semantic usefulness or visual contrast.

## Issues

### 1. Plan evidence fields can be assigned to the wrong phase

The generated/repaired plan placed evidence fields such as `WAPE` and
`baseline_results` on a preprocessing phase. That made `phase_0_preprocess`
responsible for model-comparison evidence it could not produce.

Impact:

- Early structural phases can receive impossible report contracts.
- The research loop retries or fails even when the phase did the correct
  preprocessing work.
- This points to a missing single source of truth for phase intent, report
  schema, and evidence contract assignment.

Status:

- A repair was implemented to move metric/comparison evidence to experimental or
  final evaluation phases instead of preprocessing-like phases.
- Root follow-up remains: make evidence placement explicit in the plan model
  rather than inferred from field-name heuristics.

Candidate improvements:

- Represent phase role and evidence ownership as structured plan data.
- Keep report schema generation, plan quality repair, and native runner
  contracts behind one shared resolver.
- Add a plan audit that rejects impossible metric/comparison fields on
  structural phases before the run starts.

### 2. Result validation is too dependent on field-name heuristics

Several valid or at least plausible research fields were rejected because the
validator inferred semantics from names:

- Boolean diagnostic flags were treated as numeric statistics.
- Composite SHA256 fingerprint metadata encoded as a JSON string was rejected.
- Diagnostic counts of zero were rejected, even when zero was the point of the
  fallback log.
- `sensitivity_comparison_origins_1_2` was interpreted as a probability-like
  metric that must be between 0 and 1.
- `comparison_table[*].WAPE_std` set to `null` was rejected later by substantive
  value validation rather than being corrected or rejected early by schema
  validation.

Impact:

- The AI spends retries changing field names or deleting useful diagnostics
  instead of improving research logic.
- The same dataset/model code can be valid while the run fails on naming.
- The validator behaves like a global lint pass instead of a typed contract
  validator.

Status:

- Boolean statistical flags and composite SHA256 fingerprint handling were
  fixed.
- The deeper problem remains: field-name inference is still too broad.

Candidate improvements:

- Prefer typed schema annotations over global substring rules.
- Validate only fields that the active phase schema marks as evidence fields.
- Treat optional numeric evidence as either omitted or numeric, and reject
  `null` at schema validation time with a targeted message.
- Add a deterministic JSON sanitizer for safe mechanical fixes, such as removing
  optional `null` fields or filling known prior-phase stats from referenced
  artifacts.

### 3. `beats_baseline` has ambiguous semantics

Generated phase scripts used `beats_baseline` to mean "beats EMRO". Tiny-Lab's
consistency checker interprets `beats_baseline` as "beats the best baseline
metric available in this local comparison scope." In a table that includes EMRO,
seasonal naive, moving average, and model rows, this led to contradictions such
as:

```text
beats_baseline=true contradicts wape=5811.22 vs best baseline 5811.22
```

Impact:

- Valid EMRO-relative comparisons failed because the field name implied a
  different scope.
- Claude retried the same conceptual mistake multiple times.
- Leaderboards and baseline collections become semantically unstable.

Status:

- The SCM phase 1 script was manually repaired to use `beats_emro` for
  EMRO-relative claims and not emit `beats_baseline` inside that baseline
  collection.
- The SCM phase 3 script was manually repaired so leaderboard
  `beats_baseline` values do not claim impossible local self-comparisons.

Candidate improvements:

- Split comparison flags into explicit names:
  - `beats_emro`
  - `beats_reference_baseline`
  - `beats_best_baseline`
  - `beats_previous_phase_best`
- Add optional comparison scope metadata, such as
  `comparison_reference: "emro"`.
- Update prompts and schema repair to avoid generic `beats_baseline` unless the
  scope is unambiguous.

### 4. AI retry loops repeat deterministic schema mistakes

In `phase_3_lgbm_ablation`, the model repeatedly produced:

```json
"WAPE_std": null
```

for prior-method rows in `comparison_table`. Tiny-Lab retried the Claude code
session three times, and the same validation error recurred each time:

```text
comparison_table[0].WAPE_std statistic must be numeric or a numeric list/object
```

Impact:

- Expensive AI retries are consumed for mechanical JSON/schema fixes.
- The run can churn until retry exhaustion even when a deterministic repair is
  obvious.
- The user has to interrupt the run and patch generated artifacts/scripts.

Candidate improvements:

- Add deterministic artifact repair before invoking AI retries for known
  mechanical schema issues.
- Pass the exact failing JSON path and expected value type into a smaller repair
  prompt.
- Track repeated identical validation failures and switch strategy after the
  second repeat.
- Add `tiny-lab repair-artifact --phase <id>` with provenance recording.

### 5. `PHASE_CODE` artifact matching previously used the wrong script scope

When the active phase script was missing, the engine could find a previous
phase script via a broad `phase_*.py` pattern and attempt to fix or advance
using the wrong artifact.

Impact:

- A missing `phase_1` script could cause the engine to revise `phase_0`.
- Active phase identity became dependent on filename glob behavior.
- Native runner and engine completion rules could drift.

Status:

- The artifact matching path was changed to use the shared advancement resolver
  filtered to the active phase.
- A regression test was added.

Candidate improvements:

- Make active phase artifact resolution a single shared API for engine, hooks,
  native runner, and prompts.
- Reject multiple matching scripts and non-matching scripts with a clear
  diagnostic before AI repair starts.

### 6. Backend unavailable errors were counted as research failures

Claude usage-limit or quota-like failures were previously handled like normal
phase failures. In one observed case, the run could be marked `DONE` even though
the research was not complete.

Impact:

- Backend availability was conflated with research validity.
- State retries and consecutive failures were consumed incorrectly.
- Recovery required manual `.state.json` editing.

Status:

- Additional backend-unavailable patterns were added for usage limits, rate
  limits, quota, and too many requests.

Candidate improvements:

- Centralize backend error taxonomy across Claude, Codex, and future backends.
- Preserve current state on backend unavailability.
- Add `tiny-lab doctor --backend <name>` checks for quota/auth before a long run.

### 7. Repeated state artifacts can be stale

After phase completion, `HYPOTHESIS_UPDATE` advanced immediately because
`research/iter_1/phases/.hypothesis_log.json` already existed. This happened
after later phases as well.

Impact:

- The researcher loop can appear to update hypotheses while reusing a stale
  artifact.
- Creative direction changes may not actually happen after each phase.
- A single fixed completion path is unsafe for repeated state executions.

Candidate improvements:

- Validate artifact freshness against the last completed phase id and event
  timestamp.
- Store hypothesis updates as append-only entries keyed by phase id.
- Require `HYPOTHESIS_UPDATE` artifacts to mention the phase/result artifacts
  they used.
- Add stale-artifact detection for all repeated states.

### 8. Long AI sessions have poor progress visibility

Claude phase generation ran for several minutes with no Tiny-Lab log updates
until the subprocess exited. Process inspection showed the backend was alive,
but Tiny-Lab did not expose intermediate tool activity, artifact writes, or a
heartbeat.

Impact:

- Users cannot distinguish slow model work from a stuck process.
- Interrupt decisions are guesswork.
- Debugging requires `pgrep`, `ps`, `tail`, and manual state inspection.

Candidate improvements:

- Stream backend stdout/stderr or structured events into `research/loop.log`.
- Add heartbeat logs while waiting for AI-session completion.
- Poll for completion artifacts while the backend is still running.
- Add `tiny-lab status --watch` with active state, backend pid, elapsed time,
  expected artifact, and last artifact mtime.

### 9. Prompt contents leak into process listings

Both Claude and Codex invocations pass the full rendered prompt on the command
line. `pgrep -fl` and `ps` show project constraints, file names, and user
research details.

Impact:

- Process listings become extremely noisy.
- Sensitive project context can leak to local process observers.
- Debug output is hard to read.

Candidate improvements:

- Pass prompts through stdin or a temporary prompt file.
- Log a short prompt hash and state id instead of the full prompt command.
- Add backend capability metadata for prompt transport.

### 10. Manual state recovery is still a normal part of debugging

Several recovery actions required direct edits to:

`research/.state.json`

Examples:

- Restoring a backend-unavailable state.
- Moving from `PHASE_CODE` to `PHASE_RUN` after deterministic generated-script
  repair.
- Clearing retry counters after fixing a mechanical script issue.

Impact:

- Recovery is fragile and not auditable.
- Manual edits can accidentally skip necessary states.
- The final research provenance does not show which repairs were manual.

Candidate improvements:

- Add `tiny-lab repair-state --to <state> --phase <id> --clear-failures`.
- Record repair provenance in `.events.jsonl`.
- Add `tiny-lab resume --from-current-artifacts` to recompute the correct next
  state from validated artifacts.

### 11. Extra artifacts can contaminate later context

Phase 2 produced both:

- `phase_2_linear_regression.json`
- `phase_2_simple_ml_baseline.json`

Later prompts included both as previous results.

Impact:

- The model may treat duplicate or alias artifacts as separate evidence.
- Later phases can inherit confusing context.
- Result summaries become less clear.

Candidate improvements:

- Enforce one canonical report artifact per phase.
- Mark auxiliary artifacts with explicit `artifact_role`.
- Exclude non-canonical aliases from "Previous results" prompt summaries.

### 12. Visualization quantity improved, but visual audit is still artifact-existence based

The SCM run produced several useful plots:

- Initial data visualizations in `research/iter_1/data_viz/`
- `phase_0_preprocess_viz.png`
- `phase_1_heuristic_viz.png`
- `phase_2_linear_regression_viz.png`
- `phase_3_lgbm_viz.png`

Impact:

- Tiny-Lab validates that planned visualization files exist, but not whether
  they are legible, non-empty, correctly scoped, or useful for research
  decisions.

Candidate improvements:

- Add image sanity checks for dimensions, nonblank pixels, and basic contrast.
- Record visualization intent, source data, and linked claim ids.
- Require data-understanding states to produce a manifest that maps each plot to
  the research question it answers.

## Current Workaround

For the SCM run, after deterministic script repair:

```bash
tiny-lab run --max-iter 3 --timeout-seconds 900 "<research goal>"
```

can be resumed from:

```json
{
  "state": "PHASE_RUN",
  "current_phase_id": "phase_3_lgbm_ablation"
}
```

Do not restart from scratch unless the goal is to evaluate a clean run. This
run already contains useful artifacts and documented repair points.

If state repair is needed again, prefer:

```bash
tiny-lab repair-state --to PHASE_RUN --phase phase_3_lgbm_ablation --clear-failures --clear-session
```

over direct edits to `research/.state.json`.

## Priority Fix List

1. Create a single artifact/phase contract resolver used by engine, native
   runner, hooks, and prompts.
2. Replace broad field-name validation with typed evidence semantics from the
   active phase schema.
3. Make comparison flags scope-explicit and avoid generic `beats_baseline`
   unless the reference is unambiguous.
4. Extend stale-artifact detection beyond `HYPOTHESIS_UPDATE` to other repeated states.
5. Add deterministic repair paths for mechanical JSON/schema issues before AI
   retries.
6. Add first-class artifact repair provenance.
7. Stream backend progress and poll completion artifacts while backend processes are still alive.

Completed from the previous priority list:

- `status` now includes active backend process information.
- `ps`, `stop`, and `repair-state` now exist.
- Backend prompts have been moved off process command lines.
- `HYPOTHESIS_UPDATE` stale artifact reuse is blocked for phase-keyed updates.
