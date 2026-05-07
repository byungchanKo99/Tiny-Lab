# SCM Codex Clean Run Issues

Captured: 2026-05-05 KST

## Context

Project path:

`/Users/byungchanko/Downloads/scm_research`

Intent:

Reset previous Tiny-Lab progress, preserve `data/` and `prior_research/`, then run Tiny-Lab from scratch with the Codex backend. Record runtime failures and repair points so Tiny-Lab can be improved in one pass.

Preserved inputs:

- `data/sds_sales_history_daily_all_-_복사본.xlsx`
- `data/sdc_item_master.xlsx`
- `data/ST_SCM.SDM_EMRO_OUTPUT_FCST_all_-_복사본.xlsx`
- `data/ST_SCM.SDM_EMRO_OUTPUT_FCST_명세서.xlsx`
- `data/sds_sales_history_daily_all_명세서.xlsx`
- `prior_research/research.md`
- `prior_research/KakaoTalk_Photo_2026-05-05-00-34-28.png`
- `prior_research/KakaoTalk_Photo_2026-05-05-00-34-49.png`
- `prior_research/KakaoTalk_Photo_2026-05-05-00-34-57.png`

## Run Log

- Reset completed: removed previous `research/`, `prompts/`, `shared/`, `.claude/`, `.codex/`, `.tiny_lab/`, `.tiny_lab_backups/`, `AGENTS.md`, `CLAUDE.md`, and `check_plan.py`; preserved `data/` and `prior_research/`.
- Init completed with `tiny-lab init --preset ml-experiment`.
- `tiny-lab doctor --engine codex` before writing the idea failed only on missing initial idea, and passed workflow, constraints, hooks, runner docs, and Codex command discovery.

## Issues

### 1. Codex produced SHAPE_FULL artifacts but stayed alive and blocked parent progress

Observed during the clean Codex run:

- `research/constraints.json` and `research/.shaped_input.json` were written.
- `research/.state.json` advanced to `DOMAIN_RESEARCH`.
- The active backend record still showed the original Codex child alive:
  `codex exec --json --skip-git-repo-check --sandbox <value> --cd <value>`.
- `ps` showed the Codex node process sleeping at 0% CPU after the artifacts were present.

Impact:

- Hook/state advancement can happen while the parent `tiny-lab run` remains blocked inside the backend `communicate()` call.
- The run cannot continue to the next state until the Codex child exits or is interrupted.

Candidate Tiny-Lab fix:

- Add artifact polling while backend processes are alive.
- If a completion artifact validates and state has advanced, gracefully signal the backend child and return control to the engine.
- At minimum, add a heartbeat that reports "artifact exists but backend child is still running" and suggests `tiny-lab ps` / `tiny-lab stop`.

Observed outcome:

- The Codex process eventually exited normally after roughly three minutes, and the parent engine continued to `DOMAIN_RESEARCH`.
- This was not a hard failure, but the lack of heartbeat made it look stalled while the artifact already existed.

### 2. Parent `tiny-lab run "<idea>"` command still exposes the user idea in process listings

The backend prompt itself is no longer visible in `ps`, but the parent command was:

```text
tiny-lab run --engine codex --max-iter 3 --timeout-seconds 900 <full research idea>
```

Impact:

- Sensitive user research intent can still appear in process listings even though backend prompts are now stdin-based.

Candidate Tiny-Lab fix:

- Prefer a `--idea-file` path or stdin input mode for long research goals.
- When a positional idea is provided, rewrite the parent process title if feasible or document that `research/.user_idea.txt` is the privacy-preserving path.

### 3. Codex `DOMAIN_RESEARCH` ran for more than five minutes without visible progress or artifact output

Observed during the clean Codex run:

- State: `DOMAIN_RESEARCH`
- Active backend pid: `10596`
- Elapsed time: more than five minutes
- CPU: `0.0`
- No `research/iter_1/.domain_research.json` or other domain-research artifact was written.
- `research/loop.log` had no heartbeat or intermediate backend events after `ENGINE: running codex session for DOMAIN_RESEARCH`.

Interpretation:

- This is not enough evidence to conclude that Codex was hung. Codex may have been doing long-running reasoning or internal tool planning.
- The concrete Tiny-Lab issue is that the user cannot distinguish productive long reasoning from an idle/stuck backend because no heartbeat, streamed event, or expected-artifact status is visible.

Impact:

- The run cannot autonomously progress past `DOMAIN_RESEARCH` under Codex.
- The user can only estimate whether the backend is productive by manually checking `ps`, artifacts, and logs.

Candidate Tiny-Lab fix:

- Add state-level soft timeout for bounded literature/domain states.
- Add deterministic offline fallback for `DOMAIN_RESEARCH` when no artifact appears by the soft timeout.
- Stream Codex JSON events or backend stderr/stdout into `research/loop.log`.
- Record an active-backend heartbeat with expected artifact path, elapsed time, artifact existence, and last artifact mtime.

Observed outcome:

- The state eventually completed after roughly seven to eight minutes and wrote `research/iter_1/.domain_research.json`.
- The issue is therefore not "hard hang" in this case; it is "no heartbeat or visible progress for a long-running bounded state."

### 4. `tiny-lab stop` can fail in Codex harness when the project is outside writable roots

Observed while trying to stop the stalled `DOMAIN_RESEARCH` run:

```text
PermissionError: [Errno 1] Operation not permitted: '/Users/byungchanko/Downloads/scm_research/research/.intervention.json'
```

Impact:

- In the Codex harness, a project under `/Users/byungchanko/Downloads` may be runnable via approved command prefixes but `stop` still cannot write the intervention file without escalation.
- The recovery path becomes inconsistent: status/ps can read the active backend, but stop cannot write or signal from the sandboxed command path.

Candidate Tiny-Lab/Codex-runner fix:

- Document that external project roots need writable-root permission or elevated execution for `stop`.
- Add a fallback mode to `stop` that still attempts to signal the active backend pid if writing `.intervention.json` fails.
- Surface a clearer error suggesting `tiny-lab ps` plus manual `kill -INT <pid>` when intervention write is blocked.

### 5. Stopping PLAN left an invalid partial plan artifact and a misleading backend-unavailable summary

After `DOMAIN_RESEARCH`, `DATA_DEEP_DIVE`, `VISUALIZE_DATA`, and `IDEA_REFINE` completed, `PLAN` was interrupted by `tiny-lab stop`. The parent run ended with:

```text
ENGINE: codex session finished (exit=1)
ENGINE: backend error: Reading prompt from stdin...
ENGINE: backend unavailable in PLAN: codex backend is unavailable for PLAN: Reading prompt from stdin...
```

The state remained:

```json
{
  "state": "PLAN",
  "consecutive_failures": 0,
  "phase_retries": 0
}
```

but `research/iter_1/research_plan.json` existed and failed the plan quality audit, including missing `experiment_checklist`, invalid `metric.target`, weak success criteria, and missing required evidence categories.

Impact:

- User-initiated stop is classified as backend unavailable with an unhelpful error summary.
- A partial invalid completion artifact remains and must be repaired or overwritten on resume.

Candidate Tiny-Lab fix:

- Distinguish user stop/SIGINT from backend unavailable.
- If a stopped backend leaves a completion artifact, immediately validate it and log whether resume will repair or overwrite it.
- Improve Codex stderr summary extraction so `Reading prompt from stdin...` is not treated as the root cause.

### 6. Deterministic plan-quality fallback did not fully repair one evidence requirement

On resume from the interrupted PLAN state, Tiny-Lab correctly detected quality issues in the existing `research/iter_1/research_plan.json`. The plan-quality fallback reduced the issue list, but still left:

```text
p0_data_understanding_mapping expected output schema must request statistics such as std, CI, min/max, n, sample counts, or fold counts; support counts alone do not satisfy the statistical inference requirement
```

The engine then had to ask Codex to fix the artifact.

Impact:

- The deterministic fallback helps but is not complete for structural/data-understanding phases.
- AI artifact repair is still needed for a mechanical schema/evidence-placement issue that Tiny-Lab can probably repair itself.

Candidate Tiny-Lab fix:

- Extend the plan-quality fallback so every phase with required statistical evidence gets at least one explicit numeric dispersion/range field such as `WGT_SUM_mean`, `WGT_SUM_std`, `WGT_SUM_min`, `WGT_SUM_max`, and `n_samples`.
- Ensure preprocessing/data-understanding phases satisfy statistical evidence with descriptive statistics rather than model-comparison metrics.

### 7. Codex artifact-fix prompt timed out on plan repair

After deterministic fallback left one plan-quality issue, Tiny-Lab invoked Codex to fix the existing `research_plan.json`. That artifact-fix path timed out:

```text
ENGINE: artifact fix timed out after 120s
ENGINE: starting stateless codex session; previous id ... is informational
ENGINE: running codex session for PLAN
```

Impact:

- The short artifact-fix path did not resolve a narrow mechanical plan issue.
- Tiny-Lab had to fall back to a full PLAN backend session, which is slower and may overwrite more of the plan than necessary.

Candidate Tiny-Lab fix:

- For known plan-quality issues, prefer deterministic patching over a general Codex artifact-fix prompt.
- If AI repair is still needed, pass a narrower JSON Patch style prompt and enforce an explicit "edit only this field" contract.
- Record artifact-fix timeout as a distinct repair failure event, not only in `loop.log`.

### 8. Codex `PHASE_CODE` for the first phase showed another long no-visible-progress period

At `PHASE_CODE` for `p0_data_understanding_mapping`, the active Codex child had been alive for more than five minutes with no script in `research/iter_1/phases/`.

Interpretation:

- This may still be legitimate long Codex reasoning.
- The issue is not "Codex is definitely hung"; the issue is that Tiny-Lab gives no progress signal while the expected artifact is still absent.

Impact:

- The first executable phase may block before any script exists, even after plan validation succeeds.
- Without backend event streaming, it is unclear whether Codex is thinking, blocked on tooling, or idle after an internal failure.

Candidate Tiny-Lab fix:

- Add heartbeat logging for `PHASE_CODE` with expected script path and elapsed time.
- Consider splitting phase-code prompts into smaller "write script contract only" and "implementation" prompts for Codex.
- Add a soft timeout that asks for a minimal executable script matching the phase contract before the hard backend timeout.

Observed outcome:

- Waiting was the correct choice. Codex eventually wrote the p0 phase script and the script produced `p0_data_understanding_mapping.json`, CSV artifacts, and PNG plots.
- The subsequent blocker was not Codex thinking time; it was Tiny-Lab schema shorthand validation.

### 9. Result schema shorthand parser rejected "type plus description" strings

The generated p0 report schema used properties such as:

```json
{
  "data_source": "array of local Excel source paths",
  "dataset_fingerprint": "object with source path, size_bytes, sheet names, row counts, and checksum or hash when practical",
  "n_samples": "integer count of weekly ITEM_CODE x target-week rows materialized for downstream splitting",
  "WGT_SUM_std": "number standard deviation of weekly WGT_SUM after aggregation"
}
```

Tiny-Lab only recognized exact shorthand strings like `"array"` or `"number"`, so these fields were dropped from the interpreted `properties` map. `PHASE_EVALUATE` then repeatedly failed with:

```text
report.required references undeclared fields: ['data_source', 'dataset_fingerprint', ...]
```

Impact:

- Valid generated result JSON was rejected before type-checking the actual values.
- The engine retried `PHASE_CODE` four times even though the script and result already satisfied the intended contract.

Fix implemented:

- The schema shorthand parser now accepts strings whose first token is a known type, e.g. `"array of ..."`, `"object with ..."`, `"integer count ..."`, `"number standard ..."`, and `"string path ..."`.
- Added a regression test for these type-description shorthand schemas.

### 10. Substantive validator over-applied reproducibility and statistics checks inside metadata containers

After the shorthand fix, p0 evaluation reached substantive validation and failed on valid metadata:

```text
dataset_fingerprint.sources[0].size_bytes sha256 reproducibility metadata must use sha256:<64 hex chars>
weekly_target_table.date_min statistic must be numeric or a numeric list/object
```

Root cause:

- Any nested path under `dataset_fingerprint` inherited the fingerprint semantics, so ordinary metadata like `size_bytes`, `sheets`, and row counts were treated as sha256 values.
- Temporal boundary fields such as `date_min`, `date_max`, `target_week_start_min`, and `target_week_start_max` were treated as statistical min/max fields because their leaf names contain `min` or `max`.

Impact:

- Valid p0 data-understanding artifacts were rejected even though they contained the required sha256 fields and useful temporal metadata.
- The engine retried `PHASE_CODE` repeatedly even though the failure was in Tiny-Lab validation heuristics.

Fix implemented:

- Reproducibility semantics now apply to the leaf key, not every descendant path under a reproducibility container.
- `dataset_fingerprint` containers are accepted when they include at least one nested valid sha256 digest plus metadata.
- Temporal boundary fields are excluded from numeric-statistics validation.
- Added regression tests for dataset fingerprint manifests with metadata and temporal boundary fields.

Observed outcome:

- After the fix, the existing p0 result artifact validated successfully and Tiny-Lab advanced from `PHASE_EVALUATE` to `PHASE_RECORD`.

### 11. Backend hard timeout ended the hypothesis-update cycle without a fast second attempt

After p0 was recorded, `HYPOTHESIS_UPDATE` invoked Codex to append
`research/iter_1/phases/.hypothesis_log.json`. Codex produced no visible
completion artifact before the configured 900 second hard timeout:

```text
ENGINE: codex session finished (exit=124)
ENGINE: backend error: Backend command timed out after 900s: codex
ENGINE: backend unavailable in HYPOTHESIS_UPDATE: codex backend is unavailable for HYPOTHESIS_UPDATE: Backend command timed out after 900s: codex
```

Interpretation:

- This is different from a short no-progress window. The run reached the
  hard backend timeout, so the state was left resumable with no hypothesis
  log entry for the current phase.
- The next attempt should not repeat the same broad prompt shape without a
  stronger instruction to produce the minimal valid artifact quickly.

Impact:

- The researcher loop can lose its phase-to-phase interpretation trail even
  when the preceding result artifact is valid.
- The engine stops before the checkpoint, so autonomous phase iteration is
  interrupted by an interpretive bookkeeping step.

Fix implemented:

- AI-session states now make one accelerated retry after a retryable backend
  failure or after a successful backend call that still did not write the
  expected completion artifact.
- If a process was stopped after a backend timeout, a resumed run detects the
  previous unadvanced failure in `research/loop.log` and starts that state
  directly with the accelerated prompt.
- The retry appends a prompt section instructing the backend to think faster,
  avoid broad exploration, read only required files, write the completion
  artifact immediately, validate the schema, and stop.
- The engine now attempts artifact detection before classifying a nonzero
  backend exit as unavailable, so a slow CLI that times out after writing a
  valid artifact can still advance.
- Non-retryable backend failures such as login, quota, usage-limit, and rate
  limit errors still stop without consuming phase retries.

Follow-up fix:

- The first implementation detected previous failures from too-large log
  windows and incorrectly applied the accelerated prompt to a later
  `PHASE_CODE` state. Log scanning now isolates each state entry segment up
  to the next `ENGINE: entering ...` line, so a timeout in one state does not
  leak into another state.

### 12. Split-ratio validator treated optional zero validation rows as an invalid holdout split

p1 produced a leakage-safe temporal holdout split with train and test rows
and explicitly reported no validation split in p1:

```json
{
  "evaluation_splits": [{
    "train_rows": 149,
    "validation_rows": 0,
    "test_rows": 130
  }]
}
```

Tiny-Lab's split-ratio validator paired `train_rows` with
`validation_rows` and failed with:

```text
evaluation_splits[0].train_rows/evaluation_splits[0].validation_rows split counts/ratios must be positive
```

Root cause:

- `validation_rows` was grouped with test/holdout fields for ratio checks.
  That is correct when validation is the active holdout, but `0` can also
  be a legitimate "no validation split in this phase" marker when `test_rows`
  carries the actual evaluation holdout.

Impact:

- A valid p1 artifact was rejected and the engine unnecessarily retried
  `PHASE_CODE`.

Fix implemented:

- Zero-valued validation split fields are ignored by split-ratio pairing.
  Positive validation counts still participate in ratio consistency checks,
  and `test_rows`/holdout rows remain validated.
- Added a regression test for temporal holdout artifacts with
  `validation_rows: 0` and positive `test_rows`.

### 13. Artifact-fix timeout could hide a valid artifact written before timeout

While appending the p1 hypothesis-log entry, the artifact fixer timed out
after 120 seconds:

```text
ENGINE: asking codex to fix artifact: stale hypothesis log ...
ENGINE: artifact fix timed out after 120s
```

The file had actually been updated with a valid latest p1 entry before the
backend timeout, but Tiny-Lab treated the timeout as a failed fix and started
a full `HYPOTHESIS_UPDATE` backend call anyway.

Impact:

- Valid artifacts written by a slow backend could be ignored.
- For append-only artifacts such as `.hypothesis_log.json`, the follow-up
  backend call could append duplicate entries or waste another long timeout.

Fix implemented:

- After any artifact-fix backend error or timeout, Tiny-Lab now re-runs the
  shared completion resolver. If the artifact is valid, the fix is accepted
  despite the backend error.
- Added a regression test where the backend writes a valid hypothesis log and
  then returns a timeout.

Follow-up fix:

- Codex JSON artifact-fix timeout was increased from 120 seconds to 300
  seconds. Claude keeps the shorter 120 second JSON repair default, and final
  paper repair remains 600 seconds.

### 14. Claude hook registration used legacy `command` fields instead of `hooks[]`

Claude Code reported `.claude/settings.json` schema errors:

```text
PostToolUse[0].hooks: Expected array, but received undefined
PostToolUse[1].hooks: Expected array, but received undefined
PreToolUse[0].hooks: Expected array, but received undefined
```

Root cause:

- Tiny-Lab generated Claude hook entries as `{"matcher": "...", "command":
  "..."}` while current Claude Code expects each matcher block to contain a
  `hooks` array, e.g. `{"matcher": "...", "hooks": [{"type": "command",
  "command": "..."}]}`.
- Codex hook generation already used the correct nested shape; Claude hook
  generation had drifted.

Impact:

- Native Claude runner hooks were rejected before `state_gate`,
  `state_advance`, or `ref_verify` could run.
- This broke the intended engine/native-runner SSOT enforcement path.

Fix implemented:

- `claude_hooks_config()` now emits Claude Code's `matcher + hooks[]` schema.
- `tiny-lab init` and `tiny-lab doctor --repair-runner` upgrade legacy
  direct-`command` hook entries into the nested schema while preserving matcher
  tools.
- `tiny-lab init` also normalizes pre-existing Claude hook blocks, including
  unmanaged hooks, so missing `matcher` values become `""` and direct
  `command` entries become `hooks[]` command entries.
- `tiny-lab doctor` now fails legacy Claude hook entries that are missing a
  `hooks` array, so this drift is visible before running a native session.

### 15. Required-only object item schemas were rejected as undeclared fields

Iter 3 p0 generated result schema entries where array items were objects with
`required` fields but no explicit `properties` block, for example
`metadata_missingness[]` and `leakage_risk_columns[]`.

Tiny-Lab rejected those schemas with errors like:

```text
report.metadata_missingness[].required references undeclared fields: [...]
report.leakage_risk_columns[].required references undeclared fields: [...]
```

Root cause:

- The validator treated every `required` key as invalid unless matching
  `properties` were declared.
- For Tiny-Lab's lightweight schema subset, a required-only object item is a
  useful contract: require those fields to exist, but do not type-check their
  child values.

Impact:

- Valid research metadata rows were rejected before evaluating the actual
  result contents.
- The run retried `PHASE_CODE` even though the existing result artifact was
  structurally usable.

Fix implemented:

- Required fields are checked against declared properties only when a
  `properties` object is present.
- Required-only object item schemas now validate actual field presence without
  inventing child type constraints.
- Added a regression test that accepts the required-only schema shape and still
  rejects missing required fields.

Follow-up fix:

- Iter 3 p2 showed that the same false assumption also fails when an item has
  some `properties` but leaves additional required fields untyped. JSON Schema
  allows this: `required` enforces presence independently of `properties`.
- Tiny-Lab no longer reports `required references undeclared fields` at all.
  It enforces required-field presence and validates types only for fields that
  have a declared schema.

### 16. Codex hard timeouts could leave orphan vendor child processes

During repeated Codex timeouts, `pgrep` showed multiple old Codex vendor
processes with parent pid `1` even after the parent Tiny-Lab process had been
interrupted.

Root cause:

- Tiny-Lab started `codex exec` as a normal subprocess and, on timeout, called
  `proc.kill()` on that direct child.
- The Codex node process can spawn a separate vendor executable. Killing only
  the parent can leave that child detached and still running.

Impact:

- Old Codex workers can keep consuming resources after the Tiny-Lab run has
  stopped.
- `tiny-lab ps` only tracks the direct backend pid, so these orphan children
  are invisible to Tiny-Lab's normal active-backend record.

Fix implemented:

- The Codex backend now starts `codex exec` in its own process session on
  POSIX systems.
- On hard timeout, Tiny-Lab sends termination to the whole process group and
  escalates to a kill signal if the group does not exit promptly.
- Added regression coverage for the Codex process-session flag and timeout
  process-group signaling.

### 17. Zero split/fold counts in an explicit no-split EDA phase were treated as failed support counts

After the required-only schema fix, iter 3 p0 reached substantive validation
and failed with:

```text
Report substantive value errors: ['fold_count count must be > 0', 'split_count count must be > 0']
```

Root cause:

- Tiny-Lab correctly requires positive sample, trial, split, and fold counts
  when those fields are used as statistical support evidence.
- p0 is a preprocessing/EDA phase whose `split_protocol` explicitly says no
  train/test split is performed yet, and it reports top-level `split_count: 0`
  and `fold_count: 0` as provenance, not as repeated-evaluation evidence.

Impact:

- A valid no-split EDA/preprocessing artifact was rejected after schema
  validation passed.
- The engine would unnecessarily retry phase code instead of recording the
  completed p0 audit.

Fix implemented:

- Top-level `split_count`, `fold_count`, `n_splits`, and `n_folds` may be zero
  only when the artifact explicitly identifies itself as no-split,
  no-cross-validation, EDA-only, or preprocessing-only.
- Nested split/fold counts and sample/trial counts still require positive
  values when they are used as evidence.
- Added a regression test for explicit no-split EDA phase metadata.

### 18. `p_value_resolution` was treated as an actual p-value in significance consistency checks

p2 validation failed with:

```text
comparison_table[0].statistically_significant=false contradicts p_value 0.00049975 <= alpha 0.05
```

The actual comparison p-value in that row was `p_value: 0.347`, with
`statistically_significant: false`. The small value was
`p_value_resolution`, a bootstrap/permutation resolution metadata field, not
the result p-value.

Root cause:

- Tiny-Lab identified p-value fields by token matching and included
  `p_value_resolution` in the set used for significance flag consistency.
- The consistency check chose the minimum p-value in scope, so the resolution
  metadata overrode the actual row p-value.

Impact:

- A consistent non-significant result was rejected as contradictory.
- The engine retried p2 even though the p2 report had coherent inferential
  metadata.

Fix implemented:

- `p_value_resolution` and other p-value fields containing a `resolution`
  token are ignored by significance flag consistency checks.
- Added a regression test for a row with `p_value: 0.347`,
  `p_value_resolution: 0.000499...`, and
  `statistically_significant: false`.

### 19. Model hyperparameters were interpreted as significance thresholds and probability metrics

p3 validation failed after the simple ML control phase completed:

```text
selected_hyperparameters.b4_simple_ml_decision_tree_sensitivity metric value must be between 0 and 1
cv_results[0].params.alpha significance threshold must be > 0 and < 1
selected_hyperparameters.b3_simple_ml_no_regular_features_ridge.alpha significance threshold must be > 0 and < 1
```

Root cause:

- `alpha` is both a common significance threshold name and a common model
  hyperparameter name, e.g. ridge regularization strength.
- Tiny-Lab validated every leaf named `alpha` as a significance threshold,
  even under `params` or `selected_hyperparameters`.
- The model id `b4_simple_ml_decision_tree_sensitivity` contains the word
  `sensitivity`, so metric heuristics treated the selected-hyperparameter
  object as a bounded probability-style metric.

Impact:

- Valid model-selection metadata was rejected even though it was not a
  statistical-significance claim.
- The engine retried p3 after a completed script and result artifact.

Fix implemented:

- Alpha/significance-threshold validation now ignores paths under model
  `params` and `selected_hyperparameters`.
- Metric value validation also ignores selected hyperparameter paths.
- Added regression tests for ridge `alpha` hyperparameters and model names
  containing metric-like words such as `sensitivity`.

### 20. Baseline consistency checks ignored row-level `comparator_WAPE`

p3 then failed report consistency on a comparison row where ridge was compared
against the p2 shifted moving-average baseline:

```text
comparison_table[5].beats_baseline=true contradicts wape=0.569458 vs best baseline 0.526594
```

The row itself had:

```json
{
  "comparator": "b1_non_ml_shifted_moving_average",
  "WAPE": 0.569458,
  "comparator_WAPE": 0.574904,
  "delta_vs_baseline": 0.005445,
  "beats_baseline": true
}
```

Root cause:

- Tiny-Lab validated every nested comparison against the globally best
  inherited baseline value.
- It ignored explicit row-level comparator metrics such as `comparator_WAPE`.

Impact:

- Valid pairwise comparator rows were rejected whenever the selected comparator
  was not the globally best baseline.
- This matters for research narratives that separately compare against EMRO,
  non-ML, and simple-ML controls.

Fix implemented:

- Baseline consistency checks now prefer direct row-level comparator/baseline
  metric fields such as `comparator_WAPE` or `baseline_MAE` before falling back
  to inherited global baseline values.
- Added a regression test for a `comparison_table` row that beats a local
  comparator while still not beating the global best baseline.

### 21. Generic significance flags were mixed with comparator-specific p-values and CIs

p4 validation failed with:

```text
statistically_significant=false contradicts p_value 0.001 <= alpha 0.05
statistically_significant=false contradicts improvement_vs_simple_ml_ci95 excluding zero
```

The artifact separately reported:

- Generic/EMRO-oriented evidence: `p_value: 0.62`,
  `improvement_ci95: [-0.0719, 0.1257]`,
  `statistically_significant: false`.
- Simple-ML comparator evidence: `p_value_vs_simple_ml: 0.001`,
  `improvement_vs_simple_ml_ci95: [0.0250, 0.1178]`.

Root cause:

- The significance checker treated generic `statistically_significant` as if it
  applied to all p-values and comparison intervals in the same object.
- Comparator-specific fields such as `p_value_vs_simple_ml` were therefore
  mixed with generic significance flags.

Impact:

- A report could correctly say "not significant versus EMRO, significant
  versus simple ML" but still fail validation.
- This blocks multi-comparator research artifacts where each comparator has
  different uncertainty evidence.

Fix implemented:

- Generic significance flags now prefer generic `p_value` and generic
  comparison intervals.
- Comparator-specific intervals/fields such as
  `improvement_vs_simple_ml_ci95` no longer force generic
  `statistically_significant`.
- Added a regression test for mixed generic and `vs_simple_ml` significance
  evidence.

Follow-up fix:

- A nested flag under `comparison_table[6]` was still treated as
  comparator-specific because the full path contains `comparison_table`.
- Significance flag scoping now classifies the flag by its leaf key, not by
  parent container names.
- Specific flags such as `significant_improvement_vs_simple_ml` are recognized
  and validated against the matching comparator-specific p-value/interval.

### 22. `significant_improvement=false` was rejected for statistically significant degradation

After Codex retried p4, the artifact included a row for a much worse family
analog baseline:

```json
{
  "p_value": 0.0004997501249375312,
  "improvement_ci95": [-5.5283, -2.8748],
  "significant_improvement": false
}
```

Root cause:

- Tiny-Lab interpreted low p-values and CIs excluding zero as requiring
  `significant_improvement=true`.
- That is only valid when the interval is positive in the configured
  improvement direction. A negative interval means statistically significant
  degradation, not significant improvement.

Impact:

- Correct "significant difference but not significant improvement" rows failed
  validation.
- This is common in ablation/model-comparison artifacts where some methods are
  significantly worse than the comparator.

Fix implemented:

- Directional improvement flags now distinguish positive and negative
  non-zero intervals.
- `significant_improvement=false` is accepted when the relevant interval is
  significantly below zero.
- `significant_improvement=true` is rejected when the interval is below zero.
- Added regression tests for both cases.

### 23. p4 consistency checks treated candidate rows as inherited baselines and raw WAPE target

After significance fixes, p4 failed consistency checks because Tiny-Lab used
the p4 candidate method's own WAPE as the inherited "best baseline" and
interpreted the plan target `0.02` as a raw WAPE threshold.

Root cause:

- Baseline consistency inherited baseline metric values from broad comparison
  collections including `model_comparison` and `method_results`, so candidate
  rows could become baselines for later checks.
- The plan target was a minimum useful WAPE reduction/delta threshold, but
  target-flag consistency compared `target_achieved=true` against raw
  `WAPE <= 0.02`.

Impact:

- Correct pairwise comparisons and target-achievement flags for delta-based
  objectives were rejected.
- Regular-product candidate rows can invalidate themselves as "best baseline"
  if all model-comparison rows are treated as inherited baselines.

Fix implemented:

- Inherited baseline values now come from explicit baseline collections such as
  `baseline_results`, `baseline_metrics`, and `baseline_scores`; row-level
  comparator checks still use `comparator_WAPE` / `baseline_MAE` when present.
- Raw metric target-flag consistency is skipped when the plan explicitly
  describes the target as an improvement/delta/reduction threshold.
- Added regression coverage for delta target interpretation.

### 24. Explicit `baseline_results` can still contain candidate rows

p4 continued to fail after broad comparison collections were excluded because
the artifact placed the regular-product candidate inside `baseline_results`:

```json
{
  "baseline": "m1_regular_product_aware_ridge",
  "baseline_type": "regular_product_aware_candidate",
  "WAPE": 0.5033807545501182
}
```

Root cause:

- Tiny-Lab treated every metric row inside `baseline_results` as an actual
  baseline, even when the row itself was labeled as a candidate/proposed
  method.
- The same candidate can appear again in a sibling explicit baseline
  collection such as `baseline_metrics` without repeating the candidate role
  metadata.
- The candidate's own WAPE then became the inherited best baseline, causing
  `beats_baseline=true`, `delta_vs_baseline`, and `relative_improvement` to be
  checked against itself.

Impact:

- A runner can emit a common comparison-table shape where candidate and
  baseline rows are colocated, and Tiny-Lab may reject otherwise coherent
  pairwise comparisons.
- The failure mode is especially confusing because the reported best baseline
  exactly equals the candidate metric.

Fix implemented:

- Explicit baseline collections now skip rows whose role/type metadata marks
  them as `candidate`, `proposed`, `treatment`, or `under_test`.
- Candidate names found in one explicit baseline collection are also excluded
  from sibling baseline collections in the same result payload.
- Prefix variants such as `non_ml_baseline_results` are still accepted as
  explicit baseline collections.
- Added regression tests for candidate rows inside `baseline_results`.

Follow-up fix:

- p6 placed the regular-aware candidate inside `baseline_results` without a
  `candidate` role/type marker.
- Tiny-Lab now also infers candidate names from `method_results`,
  `model_comparison`, and `comparison_table` rows where a method is compared
  against a different baseline and reports `beats_baseline=true` or positive
  baseline improvement.
- Added regression coverage for this unlabeled candidate-row shape.

### 25. Method row-count dictionaries can be misread as probability metrics

p6 first failed with:

```text
same_rows_audit.method_row_counts.b4_simple_ml_decision_tree_sensitivity metric value must be between 0 and 1
```

Root cause:

- The substantive value validator only inspected the leaf key.
- The leaf `b4_simple_ml_decision_tree_sensitivity` contains `sensitivity`,
  which is normally a probability metric.
- In context, however, the value was under `method_row_counts` and represented
  an integer row count of 85.

Impact:

- Method names containing metric-like words such as `sensitivity`,
  `specificity`, `precision`, or `recall` can be rejected when they appear as
  keys in count dictionaries.

Fix implemented:

- Metric-value validation now checks the full field path for count/support
  context before applying probability metric bounds.
- Count detection recognizes plural row-count containers such as
  `method_row_counts` and `row_method_counts`.
- Added a regression test for method row counts keyed by metric-like method
  names.

### 26. Codex artifact repair can leave top-level comparison metrics stale

After p6 retried, Codex changed nested rows so the regular-aware model was
treated as the best baseline itself, but left top-level
`delta_vs_baseline=0.0232133`.

Root cause:

- The repair focused on nested `method_results` / `comparison_table` rows and
  did not update duplicated top-level summary fields.
- Tiny-Lab correctly rejected the remaining top-level contradiction because the
  artifact simultaneously said `beats_baseline=false`,
  `relative_improvement=0`, and `delta_vs_baseline>0` against a self baseline.

Impact:

- Retried artifacts can become internally inconsistent when summary metrics are
  duplicated at multiple levels.
- This is a runner prompt/repair weakness rather than just a validator issue:
  retries should update every duplicated summary field or remove ambiguous
  top-level duplicates.

### 27. Final-paper scope used every planned iteration, including stale failed runs

The final paper initially cited `iter_1`, `iter_2`, and `iter_3` artifacts.
That pulled invalid historical `iter_2` result JSON files into the final-paper
gate even though `iter_3` had valid replacement evidence.

Root cause:

- `final_artifact_reference_iterations()` treated every planned iteration in
  the project folder as the final-paper scope.
- The deterministic final-paper writer cited every result artifact in that
  scope, including stale or superseded artifacts.
- The final-paper audit then repeatedly revalidated invalid historical result
  artifacts instead of treating the current iteration as the canonical SSOT.

Impact:

- A successful current iteration can be blocked by old failed attempts in the
  same project directory.
- Final-paper validation becomes slow and noisy because the same invalid
  historical paths are reported multiple times.

Fix implemented:

- Final artifacts now use the current iteration when its plan exists; otherwise
  they fall back to the latest planned iteration at or below the state
  iteration.
- Deterministic final papers cite only valid, substantive result JSON artifacts.
- Scoped final-paper audits reject out-of-scope result/figure citations quickly
  instead of validating stale files.
- Traceable final-paper fallback now handles invalid, non-substantive, and
  out-of-scope citations.

### 28. Final-paper repair performed expensive quality matching before fallback

When `final_paper.md` failed validation, `_try_fix_artifact()` first called the
quality-backed completion resolver to find the artifact path. That resolver
re-ran the same slow final-paper gates before the deterministic fallback could
rewrite the paper.

Root cause:

- Artifact repair used `resolve_runner_completion_advance()` as a path lookup.
- For `STORY_TELL`, path lookup and quality validation were coupled.
- Evidence-ledger generation also revalidated the same result artifacts across
  evidence families.

Impact:

- A repairable final-paper issue could spend minutes validating stale artifacts
  before deterministic repair started.
- Interrupting the parent process during Codex artifact repair could leave
  Codex child processes alive, requiring manual cleanup.

Fix implemented:

- Added raw completion-artifact matching that checks file existence without
  running quality gates.
- Final-paper fallback now runs before expensive completion matching.
- Citable result-artifact checks are cached by path, mtime, and size so changed
  artifacts invalidate the cache naturally.

Follow-up:

- Parent interruption should terminate any active backend process group just as
  timeout cleanup does.

### 29. Completion audit applied global requirements to phase-specific artifacts

After `final_paper.md` was rewritten, `STORY_TELL` still failed because the
completion audit applied global requirements to `iter_3` artifacts:

```text
p0_weekly_panel_eda_preprocessing split_count must declare at least 2 folds/splits
experimental results missing planned baseline comparisons: ['simple ML ridge regression no-regular-feature control', 'SOTA/literature baselines not reproduced']
```

Root cause:

- No-split EDA/preprocessing phases declared `split_count=0` and
  `fold_count=0`, but the aggregate evaluation-protocol audit still required at
  least two folds/splits.
- Planned baselines were matched mostly by display name, while artifacts often
  reported baseline IDs.
- Context-only SOTA/literature entries marked as "not reproduced" were treated
  as required baselines and as mandatory prior-work comparison evidence.

Impact:

- Valid EDA artifacts were rejected for not having train/test splits they were
  explicitly not supposed to create.
- Controlled experiments that intentionally exclude SOTA reproduction were
  blocked by the presence of context-only SOTA text in the plan.

Fix implemented:

- Aggregate fold/split count checks now respect explicit no-split EDA context.
- Planned baseline matching accepts both baseline names and IDs.
- Context-only or "not reproduced" SOTA/literature baselines are excluded from
  required baseline and SOTA comparison gates.

### 30. REVIEW validation ignored final-artifact scope

The deterministic review initially wrote `evaluation.json`, then failed because
evaluation/result consistency scanned every result JSON in the project,
including stale `iter_1` and `iter_2` artifacts.

Root cause:

- `audit_final_artifacts()` passed unscoped evaluation checks.
- Deterministic review also called `audit_research_completion()` over all
  planned iterations instead of the final-artifact iteration scope.

Impact:

- Old false target flags and old missing-evidence markers could invalidate the
  current iteration's review.
- Deterministic REVIEW fell through to a Codex review session even when the
  current final artifacts were already valid.

Fix implemented:

- Evaluation/result consistency accepts an iteration scope and
  `audit_final_artifacts()` passes the final-artifact scope through.
- Deterministic review uses the same scoped completion audit as final-paper
  validation.

### 31. Evaluation consistency treated negative results as missing evidence

Even within `iter_3`, high review scores were rejected because the audit treated
valid negative/limitation signals as contradictions:

- `target_achieved=false` was treated as contradicting ACCEPT even when the
  evaluation did not claim the target was achieved.
- `random_row_split_used=false`, `preprocessing_objects_fitted=false`,
  `statistically_significant=false`, and `beats_emro=false` were interpreted as
  missing evidence.
- Empty `prior_work_results` / `reference_results` were treated as missing
  evidence even when SOTA reproduction was explicitly context-only.

Root cause:

- The evaluation audit conflated absence of evidence with negative evidence.
- It used score/verdict alone as an implicit claim that every target was met.

Impact:

- Conservative final papers and reviews were penalized for honestly recording
  negative or inconclusive results.

Fix implemented:

- False goal flags only block evaluation when the evaluation text explicitly
  claims the goal/target was achieved.
- Boolean `false` no longer means missing evidence unless the key is a genuine
  presence field such as `baseline_results=false`.
- Context-only `prior_work_results` / `reference_results` and optional
  `failure_cases` fields are not treated as missing evidence.

### 32. Max-iteration cap did not stop revision/reject branches at the cap

The final review produced a `REJECT` verdict and `REVIEW_DONE` routed into
`SHAPE_FULL`, starting another research-shaping loop even though
`--max-iter 3` had already been reached.

Root cause:

- The review cap stopped revision/reject loops only when
  `current_iteration > max_iterations`.
- At exactly `current_iteration == max_iterations`, the engine still followed
  `REVISE -> IDEA_REFINE` or `REJECT -> SHAPE_FULL`.

Impact:

- A max-iteration run could continue into a new research loop instead of
  stopping after final review.

Fix implemented:

- Review transitions now stop at `DONE` when
  `current_iteration >= max_iterations` and the review requests any non-DONE
  branch.
