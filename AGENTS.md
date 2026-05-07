# tiny-lab native runner (Codex agent)

This file is the Codex CLI counterpart to the Claude Code skill at
`.claude/skills/tiny-lab/SKILL.md`. Codex auto-loads `AGENTS.md` from
the project root, so the same orchestration logic is available without a
manual trigger.

You are operating inside a tiny-lab research project. Drive the workflow
from this Codex session — do **not** spawn the engine subprocess via
`tiny-lab run` unless the user asks for autonomous mode.

## When to engage

- A `research/.workflow.json` exists in the cwd → there is an active
  tiny-lab workflow you can advance.
- The user asks to "continue", "next step", "tiny-lab으로 진행", or
  similar → run `tiny-lab brief` and follow its current-state contract.

If no workflow exists yet, tell the user to run `tiny-lab init --preset
<name>` first.

<!-- TINY_LAB_RUNNER_CONTRACT_START -->
## Shared Runner Contract (SSOT)

This section is generated from `tiny_lab.runner_contract`. Update that module, not individual runner copies.

### Execution Rules

1. Run `tiny-lab doctor` before advancing work in a newly opened or resumed session. If it reports a failure, surface that issue and do not execute `tiny-lab prompt` or `tiny-lab step` until the readiness problem is fixed.
2. Run `tiny-lab brief` at the start of every turn and treat its state, action, command, gate, completion, condition, and next-state fields as authoritative.
3. Do not hand-parse `research/.workflow.json` unless you are debugging the workflow itself; `tiny-lab brief` and native hooks are generated from `tiny_lab.runner_contract.resolve_runner_state_snapshot` / `resolve_runner_state_contract`, the same machine-readable contract the CLI engine consumes.
4. Do not skip states or collapse multiple states unless the user explicitly asks for autonomous mode.
5. Execute the `runner_command` from `tiny-lab brief --json`: AI-session states render through `tiny-lab prompt`; deterministic/process/phase/checkpoint states execute through `tiny-lab step`.
6. Artifact completion, transition application, and conditional next-state resolution are implemented in `tiny_lab.advancement`; the CLI engine and native PostToolUse hook both use that module.
7. For process, phase-run/evaluate/record, and checkpoint states, use `tiny-lab step` so the same engine handlers apply the transition.
8. Path/tool/Bash gate policy is implemented in `tiny_lab.hooks.state_policy` and consumes `RunnerStateContract`; the native PreToolUse hook is only the runtime adapter.
9. Let hooks enforce path/tool gates and artifact advancement. Do not hand-edit `.state.json` to bypass a gate.

### Execution Modes

1. CLI engine mode runs the state machine from `tiny-lab run`, spawning the configured backend for AI-session states and applying deterministic handlers directly.
2. Native runner mode runs inside the active Claude/Codex chat session. It uses the same `.state.json`, same workflow JSON, same prompt renderer, same state gate policy, and same completion advancement logic.
3. Switching modes is allowed because both modes consume the same state and workflow files. Use `tiny-lab brief` after switching to refresh the current contract.
4. For AI-session states, native runners execute `tiny-lab prompt`, follow the rendered prompt, and write the completion artifact. For non-AI states, they execute `tiny-lab step` so engine handlers remain authoritative.
5. Per-state `"engine"` overrides are advisory in native mode and executable in CLI mode. Native runners must compare `engine`/`intended_engine` from `tiny-lab brief` before proceeding.

### Prompt Preambles

1. Load `prompts/_shared/ml_researcher_rubric.md` when present.
2. Load `research/constraints.json` when present.
3. Apply both preambles before the state prompt. The quality rubric is first; constraints are second.
4. If a project overrides the package prompt file, use the project file.

### Runtime Context

Prompts may use these placeholders:

| Placeholder | Source |
| --- | --- |
| `{iter}` | `iter_<iteration>` from `RunnerStateContract.iteration` |
| `{iteration}` | `RunnerStateContract.iteration` |
| `{project_dir}` | Current project directory |
| `{current_phase_id}` | `RunnerStateContract.current_phase_id` |
| `{current_phase}` | Matching phase object from `research/iter_N/research_plan.json` |
| `{previous_results_summary}` | Summaries of `research/iter_N/results/*.json` |
| `{plan_quality_contract}` | Experimental plan contract from `tiny_lab.plan` |
| `{reference_verification_contract}` | Reference verification contract from `tiny_lab.refs` |
| `{final_paper_contract}` | Final-paper contract from `tiny_lab.quality` |
| `{evaluation_contract}` | Professor review contract from `tiny_lab.review` |

Path fields in the runner contract, including completion artifacts and allowed/blocked path globs, resolve `{iter}`, `{iteration}`, and `{current_phase_id}` through `tiny_lab.runtime_placeholders`.

### Phase Script Artifacts

Phase script naming is governed by `tiny_lab.phase_contract`; update that module instead of copying rules into prompts or runner docs.

1. Create exactly one Python script for the active phase under `research/iter_N/phases/`.
2. Prefer `research/iter_N/phases/<current_phase_id>_<current_phase_name_slug>.py`.
3. The engine accepts only these stems for phase `<current_phase_id>`: exactly `<current_phase_id>`, `<current_phase_id>_...`, or `<current_phase_id>-...`.
4. Do not create backup, alternate, or future-phase scripts in the same step; multiple matching scripts for the active phase block execution.
5. Do not assume `python -m pip` exists. If a dependency is missing, first try `ensurepip` plus project-local `PIP_CACHE_DIR`, then fall back to `uv pip install --python <sys.executable> ...` with project-local `UV_CACHE_DIR`, or fail with a clear dependency message before doing partial work.


## Experimental Plan Quality Contract (SSOT)

This section is generated from `tiny_lab.plan`; update that module instead of copying plan-quality rules into prompts.

An experimental plan is any plan with `metric`, `baselines`, `experiment_checklist`, or `script`/`optimize` phases. For those plans:

1. Top-level fields must include `formal_notation`, `baselines`, `experiment_checklist`, `phases`; `formal_notation` and `experiment_checklist` must be non-empty.
2. `metric` must define a non-empty `name` and `direction` of `minimize` or `maximize`.
   The plan must also define either numeric `metric.target` or measurable `goal.success_criteria` / top-level `success_criteria`.
   Measurable success criteria must include a numeric threshold/percentage or an explicit all/every/no/zero condition that can be verified from result artifacts.
3. Each phase must include `id`, `why`, `type`, `depends_on`, `methodology`, `expected_outputs`, `visualization`, `status`, and `type` must be one of `script`, `optimize`, `manual`.
4. Each phase must define `expected_outputs.report.path` and `expected_outputs.report.schema`.
5. Report paths must be project-relative and under `research/iter_N/results/` for the current iteration.
6. Phase IDs must be unique, `depends_on` must reference known phase IDs, and the dependency graph must be acyclic.
7. `baselines` must explicitly include at least one non-ML or heuristic baseline entry and at least one distinct simple ML baseline entry.
8. Non-ML/heuristic baseline keywords include: `non-ml`, `non ml`, `heuristic`, `naive`, `statistical baseline`, `physical baseline`, `persistence`, `moving average`, `seasonal naive`.
9. Simple ML baseline keywords include: `simple ml`, `linear regression`, `logistic regression`, `ridge`, `lasso`, `decision tree`, `random forest`, `xgboost baseline`.
10. The plan must cover non-ML baseline, simple ML baseline, ablation or feature importance or sensitivity analysis, cross-validation or multiple splits, error analysis, and leakage or split-protocol audit.
11. At least one experimental phase schema must request the numeric primary metric named by `metric.name`, baseline-comparison collection evidence such as `baseline_results` with a baseline label and numeric metric field matching `metric.name`, SOTA/prior-work comparison evidence when SOTA/prior-work comparison is planned or claimed, ablation or feature-importance evidence when applicable, per-fold/split metric evidence when evaluation protocol evidence is applicable, causal design/identification evidence when causal effects are claimed, robustness evidence when robustness/stability is claimed, external/held-out/OOD generalization evidence when generalization is claimed, error-analysis evidence when applicable, fairness/bias-audit evidence when fairness, bias, protected-group, or parity claims are planned, efficiency/resource evidence when latency, throughput, model size, memory, FLOPs, or compute-cost claims are planned, benchmark context when latency/throughput/runtime/memory/compute-cost evidence is planned, scoped leakage-audit evidence such as `train_test_overlap`, `group_overlap`, `target_leakage`, or `group_leakage`, and goal-achievement evidence when the plan defines `metric.target` or success criteria. Baseline-comparison, SOTA/prior-work comparison, ablation, per-fold/split, error-analysis, fairness/bias-audit, robustness, and external/OOD generalization collection schemas must request both a concrete label such as baseline/prior_work/feature/fold/split/slice/run/source/scenario/protected_group and a numeric metric field.
12. Every `script` or `optimize` phase schema must request statistics and reproducibility metadata: seed, dataset fingerprint or source, split protocol, environment, script/code path, and script/code hash. At least one experimental phase schema must request concrete statistical uncertainty such as `std`, `ci95`, or `variance`, or concrete statistical significance such as `p_value` or comparison confidence intervals with prefixes such as `improvement`, `delta`, `difference`; support counts alone are not enough for this inference requirement, and uncertainty/significance fields must be paired with sample/repetition support such as `n_samples`, `n_trials`, or `fold_count`.
13. Evidence field-name families are defined by the shared Experimental Evidence Contract from `tiny_lab.evidence`.


### Experimental Evidence Contract

These field-name families are generated from `tiny_lab.evidence`; update that module instead of copying token lists into prompts.

1. Statistics: `std`, `stdev`, `standard_deviation`, `stderr`, `standard_error`, `sem`, `se`, `variance`, `ci95`, `ci`, `confidence`, `min`, `max`, `n`, `n_samples`, `n_trials`, `n_splits`, `n_folds`, `sample_count`, `split_count`, `trial_count`, `samples`, `fold`, `fold_count`, `num_samples`, `num_trials`, `num_splits`, `num_folds`, `p_value`, `pvalue`. Uncertainty evidence is limited to `std`, `stdev`, `standard_deviation`, `stderr`, `standard_error`, `sem`, `se`, `variance`, `ci95`, `ci`, `confidence_interval`; significance evidence is limited to `p_value`, `pvalue` or comparison confidence intervals using prefixes such as `improvement`, `delta`, `difference`, `diff`, `effect`, `gain`, `reduction`, `increase`, `decrease`. If a result declares a significance threshold, use `alpha` or `significance_level` with a finite numeric value satisfying `0 < value < 1`. Support counts such as `n_samples` or `fold_count` do not by themselves establish uncertainty or significance.
2. Reproducibility seed metadata: `seed`, `random_state`, `rng`
3. Reproducibility data source metadata: `dataset`, `data_source`, `fingerprint`, `hash`, `checksum`
4. Reproducibility split metadata: `split_id`, `split_protocol`, `split_scheme`, `train_test_split`, `holdout_split`, `heldout_split`, `cv_split`, `fold_assignment`, `fold_id`
5. Reproducibility environment metadata: `environment`, `python_version`, `package`, `dependencies`, `platform`
6. Code provenance: `script_path`, `code_path`, `script_sha`, `script_hash`, `code_sha`, `code_hash`, `source_hash`, `git_commit`, `commit_hash`
7. Baseline comparison evidence: `baseline_results`, `baseline_metrics`, `baseline_scores`, `baseline_mae`, `baseline_rmse`, `baseline_accuracy`, `baseline_score`, `comparison_table`, `model_comparison`, `method_comparison`, `method_results`, `leaderboard`, `improvement_over_baseline`, `delta_vs_baseline`, `relative_improvement`, `beats_baseline`, `outperforms_baseline`
8. SOTA or prior-work comparison evidence: `prior_work_results`, `previous_work_results`, `sota_results`, `state_of_the_art_results`, `published_results`, `literature_results`, `leaderboard_results`, `reference_results`, `leaderboard`, `prior_work_accuracy`, `previous_work_accuracy`, `sota_accuracy`, `prior_work_mae`, `previous_work_mae`, `sota_mae`, `prior_work_rmse`, `previous_work_rmse`, `sota_rmse`, `beats_sota`, `outperforms_sota`, `beats_prior_work`, `outperforms_prior_work`
9. Causal-effect evidence: `causal_design`, `causal_identification`, `causal_effect`, `causal_impact`, `randomized_assignment`, `randomized_control`, `randomized_trial`, `treatment_assignment`, `control_group`, `intervention`, `counterfactual`, `instrumental_variable`, `difference_in_differences`, `regression_discontinuity`, `propensity_score`, `matched_control`
10. Robustness evidence: `robustness_checks`, `robustness_results`, `robustness_metrics`, `stability_metrics`, `seed_sensitivity`, `seed_results`, `repeated_seed_results`, `stress_test_results`, `perturbation_results`, `sensitivity_results`
11. Generalization evidence: `external_validation_results`, `external_test_results`, `external_dataset_results`, `out_of_distribution_results`, `ood_results`, `cross_dataset_results`, `heldout_results`, `holdout_results`
12. Ablation, feature-importance, or sensitivity evidence: `ablation_results`, `ablation_study`, `component_ablation`, `feature_ablation`, `leave_one_feature_out`, `feature_importance`, `feature_importances`, `permutation_importance`, `sensitivity_analysis`, `sensitivity_results`, `component_contribution`, `shap_values`, `shap_importance`
13. Cross-validation or multiple-split evidence: `fold_count`, `cv_fold_count`, `cv_folds`, `n_folds`, `n_splits`, `split_count`, `num_folds`, `num_splits`, `cross_validation_results`, `cv_results`, `per_fold_metrics`, `fold_metrics`, `split_results`, `repeated_split_results`, `multiple_split_results`, `evaluation_splits`, `validation_scheme`, `holdout_results`, `heldout_results`
14. Error-analysis evidence: `error_analysis`, `error_slices`, `slice_metrics`, `subgroup_metrics`, `residual_analysis`, `residual_summary`, `failure_cases`, `worst_case_errors`, `misclassification_examples`, `confusion_matrix`, `calibration_error`, `calibration_errors`, `calibration_metric`, `calibration_metrics`, `expected_calibration_error`, `ece`, `brier_score`
15. Fairness or bias-audit evidence: `fairness_metrics`, `fairness_by_group`, `subgroup_fairness`, `group_fairness`, `protected_group_metrics`, `protected_attribute_metrics`, `bias_audit`, `bias_metrics`, `demographic_parity`, `demographic_parity_difference`, `equalized_odds`, `equalized_odds_difference`, `equal_opportunity`, `equal_opportunity_difference`, `disparate_impact`, `disparate_impact_ratio`, `max_group_gap`, `subgroup_performance_gap`
16. Efficiency or resource evidence: `latency_ms`, `inference_latency`, `inference_time_ms`, `runtime_seconds`, `wall_clock_seconds`, `training_time_seconds`, `throughput`, `samples_per_second`, `memory_mb`, `peak_memory_mb`, `model_size_mb`, `parameter_count`, `n_parameters`, `flops`, `macs`, `compute_cost`, `gpu_hours`, `cpu_seconds`, `energy_kwh`. Benchmark-style efficiency metrics such as latency, throughput, runtime, memory, compute cost, GPU hours, CPU seconds, or energy must be paired with context fields such as `benchmark_device`, `benchmark_hardware`, `hardware`, `hardware_name`, `device`, `device_name`, `accelerator`, `gpu_name`, `cpu_model`, `batch_size`, `batch_sizes`, `input_shape`, `precision`, `dtype`, `num_threads`, `warmup_runs`, `benchmark_repeats`, `profile_repeats`, `measurement_runs`, `repeat_count`, `sample_count`.
17. Leakage audit evidence: `leakage`, `data_leak`, `leakage_found`, `leakage_detected`, `target_leakage`, `temporal_leakage`, `preprocessing_leakage`, `group_leakage`, `row_id_leakage`, `train_test_overlap`, `duplicate_overlap`, `group_overlap`, `split_audit`, `leakage_resolved`, `leakage_mitigated`, `leakage_fixed`, `no_leakage_after_fix`
18. Goal-achievement evidence: `target_achieved`, `target_met`, `goal_achieved`, `goal_met`, `success_criteria_met`

## Reference Verification Contract

This section is generated from `tiny_lab.refs`. Update that module, not individual prompt copies.

Reference-bearing iteration artifacts write sidecars next to the source artifact as
`<source-stem>.ref_verification.json`, for example:

- `research/iter_1/.domain_research.json` -> `research/iter_1/.domain_research.ref_verification.json`
- `research/iter_1/.lit_scan.json` -> `research/iter_1/.lit_scan.ref_verification.json`
- `research/iter_1/.diverge.json` -> `research/iter_1/.diverge.ref_verification.json`

Status semantics:

- `verified`: identity was verified through arXiv, Crossref, or Semantic Scholar; URL HEAD checks only prove the URL is reachable.
- `unverified`: the verifier lacked enough identifiers or evidence to confirm the work.
- `not_found`: the verifier searched but could not find the work.
- `error`: the verifier hit an API, network, or parsing error.

Strict completion means every reference is `verified` and the sidecar audit has no structural issues.
`tiny-lab verify-refs --strict` exits non-zero for any `not_found`, `unverified`, or `error` reference.

For candidate scoring and literature-gap reasoning, treat `unverified`, `not_found`, and `error` as weak evidence. Apply `ref_verification_penalty` to candidate ideas whose `grounded_in` citations are not fully verified, and do not build novelty, SOTA, or superiority claims on them.

## Final Paper Contract (SSOT)

This section is generated from `tiny_lab.quality`; update that module instead of copying final-paper rules into prompts.

1. `research/final_paper.md` must be at least 500 non-whitespace characters.
2. It must include Markdown section headings with these signals:
- `abstract`: `abstract`
- `method`: `method`, `methodology`, `search strategy`
- `results_or_analysis`: `result`, `finding`, `analysis`, `taxonomy`
- `limitations`: `limitation`, `threats to validity`
3. If reference artifacts exist, the paper must include a Markdown heading for related work or references, using language such as `related work`, `references`, `literature`, `prior work`, and cite every reference-bearing `research/iter_*/*.json` artifact using the concrete project-relative path.
4. Novelty or SOTA claims such as `state-of-the-art`, `state of the art`, `sota`, `novel`, `first to`, `first method`, `first approach`, `beat prior work`, `beats prior work`, `beating prior work`, `better than prior work`, `outperforms prior work`, `superior to prior work`, `beat previous work`, `beats previous work`, `beating previous work`, `better than previous work`, `outperforms previous work`, `superior to previous work`, `outperforms published model`, `outperforms published method`, `outperforms published result`, `beats published model`, `beats published method`, `beats published result`, `better than published model`, `better than published method`, `better than published result` require reference artifacts with passing `*.ref_verification.json` sidecars.
5. The paper must cite every `research/iter_*/results/*.json` artifact at least once using the concrete project-relative path, and cited JSONs must be valid non-empty result artifacts.
6. The paper must cite every generated `research/iter_*/results/*.png` figure artifact at least once using the concrete project-relative path, and cited PNGs must be valid non-empty image artifacts.
7. Cited `research/iter_*/results/*` paths must be syntactically safe project-relative paths with no `.` or `..` path segments.
8. Metric, sample-size, repetition-count, split-ratio, statistical, baseline-superiority, and SOTA/prior-work superiority claims must cite the relevant result artifact in the same sentence so claim verification can trace them.
9. Sample-size claims such as `n=120`, `120 samples`, or `sample size of 120` must match `n_samples`, `sample_count`, `sample_size`, or row-count evidence in the cited result artifact.
10. Repetition-count claims such as `5 trials`, `3 random seeds`, or `2 runs` must match `n_trials`, `trial_count`, `repeat_count`, `run_count`, `seed_count`, or materialized repeated-measurement evidence in the cited result artifact.
11. Split-ratio claims such as `80/20 holdout` or `20% held-out test set` must match `split_protocol`, `train_test_split`, train/test fractions, or train/test row-count evidence in the cited result artifact.
12. If result artifacts include baseline comparison, SOTA/prior-work comparison, ablation/feature-importance, evaluation protocol, statistical uncertainty (std/CI/variance; support counts alone do not trigger this family), statistical significance (p-values or comparison confidence intervals), causal design, robustness/stability, generalization, external/OOD generalization, error analysis, fairness/bias audit, efficiency/resource evidence, leakage audit, target achievement, or reproducibility evidence, the paper must discuss that evidence family in a sentence that cites a result artifact containing the evidence.


## Professor Evaluation Contract (SSOT)

This section is generated from `tiny_lab.review`; update that module instead of copying review rules into prompts.

1. `scores` must contain exactly these criteria: `academic_rigor`, `experimental_sufficiency`, `novelty`, `narrative_coherence`, `goal_achievement`.
2. Every score must be numeric and between 1 and 10.
3. `total` must equal the sum of the score values.
4. Verdict thresholds are: `ACCEPT` when total >= 40, `REVISE` when 35 <= total < 40, and `REJECT` when total < 35.
5. `ACCEPT` also requires every criterion score to be at least 7.
6. `ACCEPT` must not include non-empty `required_actions`; unresolved required work means `REVISE`.
7. `REVISE` and `REJECT` must include non-empty, actionable `required_actions`.
8. Each required action, whether written as a string or structured object, must include an action verb such as `add`, `analyze`, `audit`, `collect`, `compare`, `compute`, `correct`, `document`, `evaluate`, `execute`, `fix`, `include`, `investigate`, `measure`, `recompute`, `rerun`, `replace`, `reframe`, `revise`, `run`, `validate`, `verify`, a concrete research target such as `ablation`, `artifact`, `baseline`, `claim`, `confidence interval`, `cross-validation`, `cv`, `dataset`, `effect size`, `error analysis`, `experiment`, `feature importance`, `held-out`, `leakage`, `metric`, `model`, `phase`, `p-value`, `reference`, `reproducibility`, `result`, `schema`, `seed`, `sensitivity`, `split`, `statistic`, and at least two specific details beyond the action verb and generic research target words.
9. `ACCEPT` evaluations must include `feedback`, and when `feedback` is present it must cover every required score criterion. Each `feedback` item must include substantive issue/rationale/comment/recommendation text; `ACCEPT` feedback items must cite a concrete project-relative `research/...` artifact path. `experimental_sufficiency` and `goal_achievement` feedback must cite a concrete `research/iter_*/results/*.json` artifact. If an item includes `criterion` or `score`, the criterion must be one of the required score keys and the item score must be between 1 and 10 and match `scores[criterion]`.


### ML Research Quality Gates

ML research artifacts must satisfy these blocking expectations:

1. Quantitative claims cite concrete `research/iter_*/results/*.json` artifacts in the same sentence, and final papers cite every result artifact at least once.
2. Plans include leakage checks, explicit non-ML and simple ML entries in the `baselines` list, ablation or feature importance, error analysis, and cross-validation or multiple splits when applicable.
3. Experimental result schemas and JSON payloads materialize the applicable fields from the shared Experimental Evidence Contract above.
4. Significance flags must be consistent with p-values and comparison confidence intervals.
5. Baseline comparison flags and improvement values must be numerically consistent with the plan metric direction.
6. Target achievement flags must be numerically consistent with the plan metric target and direction.
7. Experimental result schemas materialize leakage evidence and only set resolved/mitigated flags after mitigation is actually applied.
8. ACCEPT reviews must be consistent with score totals, complete feedback coverage, final-paper structure, completed planned phases, supported numeric claims, unresolved leakage checks, and reference verification sidecars.

### Completion Audit

Before reporting final completion after an ACCEPT verdict, run:

```bash
tiny-lab audit --strict --all
```

If the audit fails, the work is not complete. Convert the failures into the next plan fix, phase, or review action.

### Failure Modes

1. If the same artifact is rewritten repeatedly and the state does not advance, inspect the completion required fields and surface the mismatch.
2. If a hook blocks a path or tool that seems correct, treat it as a preset/workflow bug instead of bypassing the hook.
3. If `.state.json` reaches the workflow circuit breaker, stop and ask for a manual fix or resume action.
4. If the user asks for autonomous mode, prefer the CLI engine path: `tiny-lab run` or `tiny-lab run --engine codex`.
5. For bounded autonomous runs, use `tiny-lab run --max-iterations N --timeout-seconds 300` so the engine finishes at the requested iteration cap and then enters synthesis/review.
6. For backend smoke tests, use `tiny-lab run --max-steps 1 --timeout-seconds 300` so the engine invokes one state and pauses with a bounded backend call.

### Native Runner Commands

```bash
tiny-lab status              # one-line state summary
tiny-lab doctor              # project, workflow, hook, and backend command readiness
tiny-lab doctor --repair-runner # repair native runner hooks/docs without rewriting workflow state
tiny-lab doctor --probe-backend # verify backend login/auth before autonomous execution
tiny-lab brief               # current state action, gates, completion artifact, and next transition
tiny-lab brief --json        # machine-readable RunnerStateContract, including runner_command
tiny-lab prompt              # render the exact current ai_session prompt from the engine SSOT
tiny-lab step                # execute one deterministic/process/phase state with engine handlers
tiny-lab run --max-iterations 3 --timeout-seconds 300 # bounded autonomous run through the requested iteration cap
tiny-lab run --max-steps 1 --timeout-seconds 300 # backend smoke test: execute one state, then pause
tiny-lab board               # dashboard with artifacts and visualizations
tiny-lab audit --strict --all # research quality gates across all iterations
cat research/.state.json     # debug-only raw state file; do not use instead of brief
```
<!-- TINY_LAB_RUNNER_CONTRACT_END -->

## Tool naming differences (Codex ↔ Claude)

The hooks normalize tool names so the workflow JSON can stay
runtime-agnostic:

| Workflow JSON name | Codex tool    | Claude tool    |
| ------------------ | ------------- | -------------- |
| `Write` / `Edit`   | `apply_patch` | `Write`/`Edit`/`MultiEdit` |
| `Bash`             | `Bash`        | `Bash`         |
| `Read`             | (built-in)    | `Read`         |

When `allowed_tools` lists `Write`, you may use `apply_patch` for new
files. When it lists `Edit`, you may use `apply_patch` for updates; the
gate checks every file touched by the patch.

## Engine selection (multi-backend)

The state spec may include `"engine": "claude"` to force a specific state to run on claude instead of codex. In native agent mode you are the Codex CLI runner, so you cannot literally hand off to the other backend inside the same chat session.

- If `tiny-lab brief` reports `engine: claude` and the user wants the intended backend, suggest dropping back to CLI mode (`tiny-lab run --engine claude`) for that state, then resuming native mode.
- Otherwise execute the `runner_command` from `tiny-lab brief --json` yourself and warn the user once that the intended engine was `claude` but native mode is using `codex`.

When the user wants to switch back to autonomous mode mid-workflow, remind them they can leave the chat and run `tiny-lab run --engine codex` to let the engine drive the rest; `.state.json` carries the position over.
