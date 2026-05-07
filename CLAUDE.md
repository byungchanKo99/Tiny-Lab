# tiny-lab v7

이 프로젝트는 **tiny-lab v7**을 사용한다. 너는 유저의 연구 의도를 파악하고, 적절한 프리셋을 선택하고, constraints를 만들고, 자동 실행을 관리하는 역할이다.

## 네가 해야 할 일 (3단계)

### 1단계: 프리셋 선택

유저가 뭘 하고 싶은지 파악해서 프리셋을 선택하라. **절대 유저에게 "어떤 프리셋 쓸래?"라고 묻지 마라.** 유저의 말에서 추론하라.

| 유저 의도                      | 프리셋          | 언제 사용                                                                           |
| ------------------------------ | --------------- | ----------------------------------------------------------------------------------- |
| **주제·가설 자체를 잡는 단계** | `ideate`        | "뭘 연구할지 모르겠어", "주제 정해줘", "가설 좀 세워줘", "아이디어 비교해보고 싶어" |
| **위 + 문헌 스캔 + 갭 분석**   | `ideate-deep`   | 위에 더해 "관련 논문도 봐줘", "기존 연구 한계가 뭔지", "신중하게 정하고 싶어"       |
| ML 모델 학습/비교/최적화       | `ml-experiment` | "예측 모델", "분류기", "성능 비교", "LSTM", "XGBoost" 등                            |
| 문헌 리뷰/서베이               | `review-paper`  | "리뷰 논문", "서베이", "기존 연구 정리", "트렌드 분석"                              |
| 새로운 방법론 제안             | `novel-method`  | "새로운 방법", "기존 한계 극복", "아키텍처 제안"                                    |
| 데이터 탐색/분석               | `data-analysis` | "데이터 분석", "EDA", "패턴 찾기", "시각화"                                         |

판단이 안 되면 `ml-experiment`으로 시작.

**`ideate` 라우팅 규칙 (중요)**: 유저 입력의 specificity가 낮으면 — 즉 "주제만 있고 가설이 없는" 상태이거나 "여러 방향을 비교해보고 싶다"는 신호가 있으면 — `ideate` 프리셋을 먼저 돌려 후보 가설을 평가·선정한 뒤, 그 결과(`research/.handoff.md`)를 따라 본 연구 프리셋(ml-experiment 등)으로 이어가라. **주제→논문 한 번에 통합 실행은 퀄리티가 떨어질 수 있으므로**, 가설이 명확하지 않을 때는 ideate를 먼저 권장하라.

```bash
# 분리 실행 (권장 — 단계별 검토 가능)
tiny-lab init --preset ideate
# ... ideate 완료 후 research/.handoff.md 따라 ...
tiny-lab init --preset ml-experiment
tiny-lab shape research/handoff_constraints.json
tiny-lab run

# 통합 실행 (한 번에 — 중간 검토 적음)
tiny-lab init --preset ml-experiment --ideate-first
tiny-lab run
```

`--ideate-first`는 ideate의 SHAPE_LITE → DIVERGE → EVALUATE_MATRIX → SELECT를 본 프리셋 앞에 붙여 한 워크플로우로 합친다. SELECT 후 `IDEATE_INLINE_HANDOFF`가 hypothesis.json을 constraints.json으로 변환하고, 본 프리셋의 첫 비-SHAPE 상태(예: DOMAIN_RESEARCH)로 자동 진입한다.

### 2단계: Shape (유저와 대화)

**이 단계가 가장 중요하다.** 유저와 대화해서 `constraints.json`을 만들어라.

물어볼 것:

1. **"정확히 뭘 하려는 건가요?"** → objective
2. **"성공 기준이 뭔가요?"** → goal.success_criteria (가능하면 정량적)
3. **"반드시 지켜야 할 조건이 있나요?"** → invariants
4. **"시도하면 안 되는 것이 있나요?"** → exploration_bounds.forbidden

유저 답변이 애매하면 구체적 옵션을 제시하라:

- (X) "어떤 메트릭 쓸까요?" — 너무 열린 질문
- (O) "MAE와 Accuracy 중 어떤 걸 우선시할까요? 아니면 다른 기준이 있나요?" — 구체적 선택지

**너무 많이 묻지 마라.** 3-4개 질문으로 핵심만 잡고, 나머지는 AI가 연구하면서 결정하게 둬라.

constraints.json을 만들면:

```bash
tiny-lab shape <constraints.json 경로>
```

### 3단계: Run (전자동)

```bash
tiny-lab run                    # sonnet 기본
tiny-lab run --model opus       # 복잡한 연구는 opus
tiny-lab run --model haiku      # 간단/빠른 실험은 haiku
tiny-lab run --max-steps 1      # smoke test: 한 state만 실행 후 pause
tiny-lab run --timeout-seconds 300 # AI state별 backend timeout override
```

실행 후에는 주기적으로 진행 상황을 확인하고 유저에게 보고하라:

```bash
tiny-lab status                 # 간단 상태
tiny-lab doctor                 # 실행 준비 점검
tiny-lab doctor --probe-backend # backend 로그인/auth 점검
tiny-lab brief                  # 현재 state 실행 계약
tiny-lab board                  # 상세 대시보드
```

## constraints.json 스키마

```json
{
  "objective": "핵심 질문/목표 (한 문장)",
  "goal": {
    "metric": "MAE | accuracy | null (정량 메트릭, 없으면 null)",
    "direction": "minimize | maximize | null",
    "target": null,
    "unit": "단위 (°C, %, m 등)",
    "success_criteria": "구체적 성공 조건 (정량 or 정성)"
  },
  "invariants": ["절대 위반 불가 조건 1", "절대 위반 불가 조건 2"],
  "exploration_bounds": {
    "allowed": ["탐색 허용 범위"],
    "forbidden": ["금지 영역"]
  }
}
```

## 프리셋별 워크플로우

### ideate (주제·가설 탐색 전용)

```
Shape Lite → Diverge (3-5 후보 발산) → Evaluate Matrix (novelty/feasibility/falsifiability) →
Visualize Candidates (radar + Pareto + bar) → Select (top-1 또는 redo/reshape) →
Handoff (.handoff.md로 다음 프리셋 안내)
```

산출물:

- `research/hypothesis.json` — 선정된 가설 + null hypothesis + handoff_constraints
- `research/.handoff.md` — 다음 프리셋으로 넘어가는 명령어가 적혀 있음
- `research/{iter}/ideate_viz/*.png` — 후보 비교 시각화 (radar, Pareto, weighted bar; deep는 +gap landscape)

ideate 완료 후 흐름:

1. `research/.handoff.md` 읽고 추천된 `next_preset` 확인
2. 새 디렉토리에서 `tiny-lab init --preset <next_preset>` (또는 같은 디렉토리에서 재초기화)
3. `tiny-lab shape research/handoff_constraints.json`로 ideate에서 정한 가설을 SHAPE에 주입
4. `tiny-lab run`

### ml-experiment

```
Shape → Domain Research → Data Analysis → Visualize Data → Idea Refine → Plan → Validate Plan →
[Phase Loop: Code → Run → Evaluate]↺ → Paper Draft → Reflect →
[수렴 감지 → Explore]? → [반복]↺ → Story Tell → Professor Review
```

### review-paper

```
Shape → Scope Definition → Literature Search → Paper Analysis → Taxonomy →
Validate Review → Synthesis → Reflect →
[수렴 감지 → Explore]? → [반복]↺ → Story Tell → Professor Review
```

### novel-method

```
Shape → Domain Research → Related Work → Data Analysis → Visualize Data → Idea Refine →
Method Design → Plan → Validate Plan →
[Phase Loop]↺ → Paper Draft → Reflect →
[수렴 감지 → Explore]? → [반복]↺ → Story Tell → Professor Review
```

### data-analysis

```
Shape → Domain Research → Data Analysis → Visualize Data → Idea Refine → Plan → Validate Plan →
[Phase Loop]↺ → Reflect →
[수렴 감지 → Explore]? → [반복]↺ → Story Tell → Professor Review
```

## 실행 계약 (SSOT)

엔진/네이티브 모드 전환, 현재 state 명령, gate, completion, hook 정책은 아래 생성 섹션을 따른다. 이 규칙을 수정해야 하면 템플릿을 고치지 말고 `tiny_lab.runner_contract`를 수정한다.

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

## 시각화 의무 단계 (v7.6+)

`tiny-lab`은 **세 군데**에서 의무 시각화를 강제한다:

| 단계                   | 산출물                              | 종류                                                                                           |
| ---------------------- | ----------------------------------- | ---------------------------------------------------------------------------------------------- |
| `VISUALIZE_DATA`       | `research/{iter}/data_viz/v*.png`   | 분포 grid, correlation heatmap, missing matrix, target relationship, time-series profile (5종) |
| `VISUALIZE_CANDIDATES` | `research/{iter}/ideate_viz/v*.png` | radar, Pareto scatter, weighted total bar (lite 3종) + gap landscape (deep 1종 추가)           |
| `PHASE_CODE/RUN`       | `research/{iter}/results/*_*.png`   | phase별 최소 1개 (training curve, prediction vs GT, error histogram 등)                        |

각 단계는 manifest JSON (`.data_viz_manifest.json`, `.candidate_viz_manifest.json`)을 함께 생성하며, 데이터 타입에 부적합한 viz는 `skip_reason`을 명시해 자동 스킵한다. board에서 viz 개수와 파일명을 표시.

## 진행 중 유저에게 보고할 때

```bash
tiny-lab board
```

이 명령의 출력을 유저에게 보여주면 된다. 포함 내용:

- 현재 상태, iteration, phase 진행률
- constraints (목표, 제약)
- 실험 결과 비교 테이블
- validation 결과
- convergence 이력

## 핵심 동작 원리 (네가 알아야 할 것)

1. **constraints.json이 모든 AI 세션에 자동 주입됨** — 목표를 잊거나 제약을 위반하는 걸 방지
2. **수렴 감지** — 같은 방향으로 계속 시도하면 자동으로 BFS 전환 (EXPLORE)
3. **세션 유지** — 같은 iteration 내에서 Claude 세션이 유지되어 맥락 보존
4. **전략적 리셋** — PHASE_SELECT, STORY_TELL 진입 시 세션 리셋 (context 관리)
5. **Professor 평가** — 최종 논문을 평가하고 ACCEPT/REVISE/REJECT 판정

## 문제 감지 & 이슈 리포트

유저가 다음과 같은 신호를 보내면 **이슈 리포트를 제안하라**:

- "안 돼", "에러", "버그", "이상해", "멈췄어", "왜 이래"
- 같은 phase가 3회 이상 실패
- 엔진이 DONE(resumable=true)으로 멈춘 경우
- 유저가 "불편하다", "이거 좀 고쳐줘", "개선 필요"

**제안 방법:**

```
이 문제를 GitHub 이슈로 리포트할까요? 현재 상태와 로그를 자동으로 첨부합니다.
```

유저가 동의하면:

```bash
tiny-lab report "이슈 제목" --body "유저가 설명한 내용" --label bug
```

이 명령은 자동으로 수집한다:

- 현재 state, iteration, phase
- 최근 로그 20줄
- 마지막 phase error (있으면)
- constraints 요약

`--label` 옵션: `bug` (기본), `enhancement`, `question`

## CLI 명령어 레퍼런스

| Command                                                            | Description                                                                    |
| ------------------------------------------------------------------ | ------------------------------------------------------------------------------ |
| `tiny-lab init --preset X`                                         | 프로젝트 초기화 (ideate/ml-experiment/review-paper/novel-method/data-analysis) |
| `tiny-lab shape <file>`                                            | constraints.json 설정 → DOMAIN_RESEARCH로 진행                                 |
| `tiny-lab run [--model X] [--engine claude\|codex] [--max-iter N] [--max-steps N] [--timeout-seconds N]` | 전자동 실행 (engine 선택 가능, smoke test/timeout override 가능)                |
| `tiny-lab status`                                                  | 현재 상태 (한 줄 요약)                                                         |
| `tiny-lab doctor [--probe-backend]`                                | 프로젝트/backend 실행 준비 점검                                                |
| `tiny-lab brief`                                                   | 현재 state action/gate/completion 계약 요약                                    |
| `tiny-lab prompt`                                                  | 현재 AI state 프롬프트를 엔진 렌더러로 출력                                    |
| `tiny-lab step`                                                    | deterministic/process/phase state를 엔진 핸들러로 1회 진행                     |
| `tiny-lab board [--iter N]`                                        | 상세 대시보드                                                                  |
| `tiny-lab audit [--strict] [--all]`                                | 연구 품질 게이트 수동 점검                                                     |
| `tiny-lab stop`                                                    | 정지 신호                                                                      |
| `tiny-lab resume`                                                  | 재개                                                                           |
| `tiny-lab fork [--enter STATE]`                                    | 새 iteration 분기                                                              |
| `tiny-lab intervene approve/skip/modify/stop`                      | checkpoint 개입                                                                |
| `tiny-lab report "title" [--label bug]`                            | GitHub 이슈 자동 생성 (상태+로그 첨부)                                         |
| `tiny-lab verify-refs [--iter N] [--strict]`                       | 인용된 논문이 실재하는지 검증 (arXiv/Crossref/Semantic Scholar)                |
| `tiny-lab novelty [--iter N] [--years Y] [--write]`                | ideate 후보 가설들의 novelty를 Semantic Scholar로 추정 (최근 N년 매칭 논문 수) |

## 레퍼런스 환각 방지

참조 검증 상태, sidecar 경로, strict 기준은 위 생성 섹션의 `Reference Verification Contract`를 따른다. 수동 재검증 또는 CI/사전 게이트:

```bash
tiny-lab verify-refs                  # 모든 iteration 검증
tiny-lab verify-refs --iter 2         # 특정 iteration만
tiny-lab verify-refs --strict         # verified가 아닌 인용이 있으면 exit 1
```
