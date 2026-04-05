# Tiny-Lab v7 Design — Domain-Agnostic Adaptive Loop

## Vision

Tiny-Lab v7은 **도메인에 무관한 반복적 작업 프레임워크**다. 연구, 리뷰 논문, PRD 작성, 웹개발 등 어떤 도메인이든 동일한 엔진 위에서 preset + prompts 조합으로 동작한다.

## Problem Statement

v6의 plan-driven phase executor는 작동하지만 반복 실험에서 구조적 한계가 드러났다:

| 문제                  | 원인                                                                   | 영향                                   |
| --------------------- | ---------------------------------------------------------------------- | -------------------------------------- |
| **편향된 탐색 (DFS)** | reflect → idea_mutation이 "성능 최적화"로만 수렴                       | 참신한 아이디어가 시도되지 않음        |
| **입력 민감도**       | user_idea가 그대로 전파 — 너무 구체적이면 과적합, 너무 추상적이면 표류 | 품질이 초기 입력에 종속                |
| **핵심 목표 망각**    | .user_idea.txt가 초기에만 참조, 이후 사라짐                            | iteration 3쯤 원래 뭘 하려 했는지 모름 |
| **맥락 소실**         | 실험 무한 반복, 전체 서사 없음                                         | "그래서 뭘 알게 됐는데?"에 답 못함     |
| **선행연구 휘발**     | domain_research가 iteration마다 독립                                   | 같은 조사를 반복                       |
| **도메인 종속**       | 연구 전용 state/prompt 하드코딩                                        | 다른 도메인에 적용 불가                |

## Design Principles

1. **도메인 무관** — 엔진은 도메인을 모른다. 도메인 지식은 preset + prompts에만 존재
2. **적정 구체성** — 입력이 너무 세밀하거나 너무 거칠면 적정 수준으로 정규화
3. **Constraints** — 핵심 목표는 모든 state에서 불변으로 참조
4. **다양성 보장** — DFS만이 아닌 BFS 탐색도 강제
5. **서사 보존** — 작업의 흐름을 최종 산출물로 응축, 평가까지
6. **지식 축적** — 조사 결과와 발견을 공유 저장소에 누적

---

## Engine: Pure State Machine

**엔진은 추상 스테이지를 모른다.** 엔진이 아는 것은 오직:

1. **States** — 현재 상태, 다음 상태
2. **State types** — ai_session, process, checkpoint
3. **Transitions** — 조건부 또는 단순 전이
4. **Handlers** — state type별 실행기
5. **Error recovery** — retry, skip, stop

엔진은 "지금이 Shape인지 Gather인지 Execute인지" 전혀 모른다. 단지 preset이 정의한 states 배열을 순서대로 돌면서, 각 state의 type에 맞는 handler를 실행하고, completion 조건이 충족되면 next로 넘기는 것이 전부다.

### v6 → v7 엔진 변경점 (최소)

v6 엔진에 추가되는 것은 딱 3가지:

| 추가 기능                  | 엔진의 역할                                                              | 왜 엔진 레벨인가                |
| -------------------------- | ------------------------------------------------------------------------ | ------------------------------- |
| **constraints.json 주입**  | `constraints.json` 파일이 있으면 모든 ai_session prompt 앞에 자동 삽입   | 모든 state에 걸치는 횡단 관심사 |
| **convergence 감지**       | `is_converging()` 조건 함수 추가 (기존 `has_pending_phases`와 동일 레벨) | 조건 함수는 엔진 레벨           |
| **shared/knowledge/ 경로** | `TINYLAB_KNOWLEDGE_DIR` 환경변수 제공                                    | 경로 관리는 엔진 레벨           |

그 외 모든 것 — 어떤 state를 어떤 순서로 배치하는지, 어떤 prompt를 쓰는지, 어떤 평가 기준을 적용하는지 — 은 **preset이 결정한다.**

### constraints.json

엔진이 유일하게 "알고 있는" 도메인 무관 아티팩트. 파일이 존재하면 모든 ai_session prompt 앞에 자동 삽입한다.

**스키마:**

```json
{
  "objective": "string — 이 작업의 핵심 질문/목표",
  "goal": {
    "metric": "string | null",
    "direction": "minimize | maximize | null",
    "target": "number | null",
    "unit": "string | null",
    "success_criteria": "string — 성공 조건 (정량 or 정성)"
  },
  "invariants": ["string — 절대 위반하면 안 되는 조건들"],
  "exploration_bounds": {
    "allowed": ["string — 탐색 허용 범위"],
    "forbidden": ["string — 금지 영역"]
  }
}
```

**주입 템플릿 (엔진 하드코딩):**

```markdown
## Constraints (MUST NOT VIOLATE)

Objective: {constraints.objective}
Goal: {constraints.goal.success_criteria}
Invariants: {constraints.invariants}
Forbidden: {constraints.exploration_bounds.forbidden}
```

<details>
<summary>도메인별 constraints 예시</summary>

**ML 연구:**

```json
{
  "objective": "IMU 센서 데이터만으로 실내 위치를 추정할 수 있는가?",
  "goal": {
    "metric": "ATE",
    "direction": "minimize",
    "target": 50,
    "unit": "meters",
    "success_criteria": "ATE < 50m on test set with statistical significance"
  },
  "invariants": [
    "IMU 데이터만 사용",
    "실시간 추론 < 100ms",
    "학습/테스트 다른 건물"
  ],
  "exploration_bounds": {
    "allowed": ["any model architecture", "any feature engineering"],
    "forbidden": ["GPS 데이터 사용", "사전 학습된 위치 맵"]
  }
}
```

**리뷰 논문:**

```json
{
  "objective": "2020-2025 LLM 기반 코드 생성 연구의 체계적 리뷰",
  "goal": {
    "metric": null,
    "direction": null,
    "target": null,
    "unit": null,
    "success_criteria": "50편 이상 논문을 분류 체계에 따라 분석, 연구 gap 3개 이상 도출"
  },
  "invariants": ["peer-reviewed 논문만", "2020년 이전은 background로만"],
  "exploration_bounds": {
    "allowed": ["any classification taxonomy"],
    "forbidden": ["non-peer-reviewed blog posts as primary source"]
  }
}
```

**웹개발 PRD:**

```json
{
  "objective": "실시간 협업 화이트보드 SaaS 제품 PRD 작성",
  "goal": {
    "metric": null,
    "direction": null,
    "target": null,
    "unit": null,
    "success_criteria": "MVP 기능 정의 완료, 기술 아키텍처 결정, 3개월 로드맵 수립"
  },
  "invariants": ["동시 사용자 100명+", "모바일 웹 필수", "월 운영비 $500 이하"],
  "exploration_bounds": {
    "allowed": ["any frontend framework", "any cloud provider"],
    "forbidden": ["native app only"]
  }
}
```

</details>

### convergence 감지

기존 `has_pending_phases` 같은 조건 함수에 `is_converging`을 추가한다.

```python
# conditions.py에 추가
def is_converging(state: LoopState, config: dict) -> bool:
    """convergence_log.json을 읽고 수렴 여부를 판단한다."""
    log = load_convergence_log(state.work_dir)
    if not log or len(log.entries) < config.get("convergence_window", 3):
        return False

    window = config.get("convergence_window", 3)
    recent = log.entries[-window:]

    # 키워드 기반 Jaccard similarity
    threshold = config.get("similarity_threshold", 0.7)
    if avg_jaccard_similarity([e.seed_keywords for e in recent]) > threshold:
        return True

    # 같은 approach_category 연속
    force_after = config.get("force_explore_after", 5)
    categories = [e.approach_category for e in log.entries]
    if len(categories) >= force_after and len(set(categories[-force_after:])) == 1:
        return True

    return False
```

preset의 state 정의에서 기존 조건 함수와 동일하게 사용:

```json
{
  "id": "SHAPE_SEED",
  "type": "process",
  "condition": { "check": "is_converging" },
  "next": {
    "true": "EXPLORE",
    "false": "ROUTE"
  }
}
```

### convergence_log.json

```json
{
  "entries": [
    {
      "iteration": 1,
      "seed_summary": "string",
      "seed_keywords": ["keyword1", "keyword2"],
      "outcome_summary": "string",
      "approach_category": "string"
    }
  ],
  "convergence_detected_at": [],
  "explorer_triggered_at": []
}
```

이 파일은 **엔진이 직접 쓰지 않는다.** REFLECT state의 prompt가 AI에게 이 파일에 기록하도록 지시한다. 엔진은 `is_converging` 조건 함수에서 읽기만 한다.

### shared/knowledge/

```
shared/knowledge/
├── context_{topic}.json       # 주제별 조사 결과
├── methods_{category}.json    # 방법론/접근법 정리
└── findings.jsonl             # iteration에서 발견한 것들 (append-only)
```

엔진은 `TINYLAB_KNOWLEDGE_DIR` 환경변수를 제공할 뿐, 파일의 내용이나 구조는 모른다. prompt가 AI에게 이 경로에 저장하도록 지시한다.

---

## Preset Layer: Everything Else

엔진이 모르는 모든 것은 preset이 정의한다. Stage 개념도 preset 내부의 조직화 메타데이터일 뿐이다.

### 5 Stages (Preset 조직화용 — 엔진은 모름)

Preset 작성자가 state를 논리적으로 그룹화하기 위한 분류. 엔진 실행에는 영향 없음.

| Stage          | 역할                                      | 핵심 질문                  |
| -------------- | ----------------------------------------- | -------------------------- |
| **Shape**      | 입력 정규화, constraints 확립             | "정확히 뭘 하려는 건가?"   |
| **Gather**     | 맥락 수집, 지식 축적                      | "이미 뭐가 알려져 있는가?" |
| **Execute**    | 계획 → 검증 → 실행 → 반성 → 다양화 (loop) | "어떻게 달성하는가?"       |
| **Synthesize** | 전체 과정을 최종 산출물로 응축            | "그래서 뭘 알게 됐는가?"   |
| **Evaluate**   | 산출물 품질 평가, 재작업 결정             | "충분한가?"                |

**도메인별 구체화:**

| Stage          | ML 연구                       | 리뷰 논문                 | 웹개발 PRD                   |
| -------------- | ----------------------------- | ------------------------- | ---------------------------- |
| **Shape**      | 연구 질문 정규화, 목표 metric | 리뷰 범위, 포함/제외 기준 | 요구사항 정규화, 기능 범위   |
| **Gather**     | SOTA 조사, 데이터 분석        | 논문 검색, 분류 체계      | 경쟁사 분석, 기술 조사       |
| **Execute**    | 실험 plan → code → run        | 논문 분석 → 비교 → 종합   | 아키텍처 → 프로토타입 → 검증 |
| **Synthesize** | 연구 논문 (서사)              | 리뷰 논문                 | PRD 문서                     |
| **Evaluate**   | 엄밀성, novelty, 충분성       | 커버리지, 일관성, 통찰    | feasibility, 완전성          |

### Preset Schema (v7)

```json
{
  "$schema": "tiny-lab/preset/v7",
  "meta": {
    "name": "string",
    "domain": "string",
    "description": "string",
    "version": "7.0"
  },
  "autonomy": {
    "mode": "autonomous | supervised | checkpoint",
    "max_iterations": "number",
    "stop_on_target": "boolean",
    "circuit_breaker": {
      "max_consecutive_failures": "number"
    }
  },
  "exploration": {
    "convergence_window": "number (default 3)",
    "similarity_threshold": "number (default 0.7)",
    "force_explore_after": "number (default 5)"
  },
  "states": [
    {
      "id": "string",
      "type": "ai_session | process | checkpoint",
      "prompt": "string (path) — optional",
      "allowed_tools": ["string"],
      "allowed_write_globs": ["string"],
      "completion": { "artifact": "string", "required_fields": ["string"] },
      "error": { "max_retries": "number", "retry_to": "string", "on_exhaust": "string" },
      "condition": { "check": "string" } | { "source": "string", "field": "string" },
      "next": "string | { condition_value: state_id }"
    }
  ]
}
```

**v6 대비 변경점:**

- `exploration` 필드 추가 — 수렴 감지 설정 (엔진의 `is_converging`에 전달)
- `stages` 필드 **없음** — 엔진은 stage를 모르므로 preset에도 불필요. states 배열의 순서와 next가 흐름을 결정
- `evaluate.criteria` / `thresholds` — preset에 있지 않음. 이것은 EVALUATE state의 prompt가 AI에게 지시하는 내용

### Prompt 공유 전략

Shape, Validate, Explore 관련 prompts는 범용 로직이 90%이므로 **공유 기본 + preset 오버라이드** 방식:

```
prompts/
├── _shared/                    # 도메인 무관 공유 prompts
│   ├── shape_full.md           # 입력 정규화, constraints 생성
│   ├── shape_seed.md           # seed 자동 검증
│   ├── validate_plan.md        # plan 검증 (constraint, DAG)
│   └── explore.md              # BFS 다양화
├── ml-experiment/              # ML 연구 전용
│   ├── domain_research.md
│   ├── data_deep_dive.md
│   ├── idea_refine.md
│   ├── plan.md
│   ├── phase_code.md
│   ├── reflect.md
│   ├── story_tell.md           # Synthesizer
│   └── professor.md            # Evaluator
├── review-paper/               # 리뷰 논문 전용
│   ├── literature_search.md
│   ├── scope_refine.md
│   ├── ...
└── product-prd/                # PRD 전용
    ├── market_research.md
    ├── ...
```

Preset의 state가 `"prompt": "prompts/_shared/shape_full.md"`로 공유 prompt를 참조하거나, `"prompt": "prompts/ml-experiment/plan.md"`로 도메인 전용 prompt를 참조.

---

## Preset Example: ml-experiment (v7)

기존 v6 preset에 새 states를 추가하고, 기존 states의 next를 수정한 것.

### 흐름

```
SHAPE_FULL → DOMAIN_RESEARCH → DATA_DEEP_DIVE →
  ┌── Execute Loop ──────────────────────────────────┐
  │ IDEA_REFINE → PLAN → VALIDATE_PLAN →             │
  │   ┌── Phase Loop ─────────────────┐              │
  │   │ PHASE_SELECT → PHASE_CODE →   │              │
  │   │ PHASE_RUN → PHASE_EVALUATE →  │              │
  │   │ PHASE_RECORD → CHECKPOINT     │              │
  │   └───────────────────────────────┘              │
  │ → PAPER_DRAFT → REFLECT → SHAPE_SEED →           │
  │   ├─ converging → EXPLORE → IDEA_REFINE          │
  │   └─ pass → ROUTE                                │
  │     ├─ done → Exit                               │
  │     ├─ idea_mutation → IDEA_REFINE               │
  │     ├─ add_phases → PLAN                         │
  │     └─ domain_pivot → DOMAIN_RESEARCH            │
  └──────────────────────────────────────────────────┘
→ STORY_TELL → REVIEW
  ├─ ACCEPT → DONE
  ├─ REVISE → IDEA_REFINE (새 full iteration)
  └─ REJECT → SHAPE_FULL
```

### 신규 States (v6에 추가)

```json
[
  {
    "id": "SHAPE_FULL",
    "type": "ai_session",
    "prompt": "prompts/_shared/shape_full.md",
    "allowed_tools": ["Read", "Write", "AskUserQuestion"],
    "interactive": true,
    "allowed_write_globs": [
      "research/.shaped_input.json",
      "research/constraints.json"
    ],
    "completion": {
      "artifact": "research/constraints.json",
      "required_fields": ["objective", "goal", "invariants"]
    },
    "error": { "max_retries": 5, "on_exhaust": "stop" },
    "next": "DOMAIN_RESEARCH"
  },
  {
    "id": "VALIDATE_PLAN",
    "type": "ai_session",
    "prompt": "prompts/ml-experiment/validate_plan.md",
    "allowed_tools": ["Read", "Write"],
    "allowed_write_globs": ["research/{iter}/.plan_validation.json"],
    "completion": {
      "artifact": "research/{iter}/.plan_validation.json",
      "required_fields": ["verdict"]
    },
    "condition": {
      "source": "{iter}/.plan_validation.json",
      "field": "verdict"
    },
    "next": { "APPROVE": "PHASE_SELECT", "REJECT": "PLAN" },
    "error": { "max_retries": 3, "on_exhaust": "stop" }
  },
  {
    "id": "SHAPE_SEED",
    "type": "process",
    "condition": { "check": "is_converging" },
    "next": { "true": "EXPLORE", "false": "ROUTE" }
  },
  {
    "id": "EXPLORE",
    "type": "ai_session",
    "prompt": "prompts/_shared/explore.md",
    "allowed_tools": ["Read", "Write"],
    "allowed_write_globs": ["research/{iter}/.explore_seed.json"],
    "completion": {
      "artifact": "research/{iter}/.explore_seed.json",
      "required_fields": ["new_seed", "rationale"]
    },
    "error": { "max_retries": 3, "on_exhaust": "skip" },
    "next": "IDEA_REFINE"
  },
  {
    "id": "ROUTE",
    "type": "process",
    "condition": { "source": "{iter}/reflect.json", "field": "decision" },
    "next": {
      "done": "STORY_TELL",
      "add_phases": "PLAN",
      "idea_mutation": "IDEA_REFINE",
      "domain_pivot": "DOMAIN_RESEARCH"
    }
  },
  {
    "id": "STORY_TELL",
    "type": "ai_session",
    "prompt": "prompts/ml-experiment/story_tell.md",
    "allowed_tools": ["Read", "Write"],
    "allowed_write_globs": ["research/final_paper.md"],
    "completion": { "artifact": "research/final_paper.md" },
    "error": { "max_retries": 5, "on_exhaust": "stop" },
    "next": "REVIEW"
  },
  {
    "id": "REVIEW",
    "type": "ai_session",
    "prompt": "prompts/ml-experiment/professor.md",
    "allowed_tools": ["Read", "Write"],
    "allowed_write_globs": ["research/evaluation.json"],
    "completion": {
      "artifact": "research/evaluation.json",
      "required_fields": ["verdict", "scores"]
    },
    "condition": { "source": "evaluation.json", "field": "verdict" },
    "next": {
      "ACCEPT": "DONE",
      "REVISE": "IDEA_REFINE",
      "REJECT": "SHAPE_FULL"
    },
    "error": { "max_retries": 3, "on_exhaust": "stop" }
  }
]
```

### 변경된 기존 States

```diff
  {
    "id": "PLAN",
    ...
-   "next": "PLAN_REVIEW"
+   "next": "VALIDATE_PLAN"
  },
- {
-   "id": "PLAN_REVIEW",
-   "type": "checkpoint",
-   ...
- },
  {
    "id": "REFLECT",
    ...
-   "next": "REFLECT_DONE"
+   "next": "SHAPE_SEED"
  },
- {
-   "id": "REFLECT_DONE",
-   ...
- }
```

**REFLECT_DONE → SHAPE_SEED + ROUTE로 분리:**

- SHAPE_SEED: 수렴 감지 (엔진의 is_converging)
- ROUTE: reflect.json의 decision으로 분기 (기존 REFLECT_DONE과 동일)

---

## Role별 Prompt 설계

### Shaper — `prompts/_shared/shape_full.md`

```markdown
You are shaping the user's input into a well-defined task with clear constraints.

## Your Task

Read the user's input from {work_dir}/.user_idea.txt

## Step 1: Analyze specificity (1-10)

- > 7: Too specific — extract core intent, move details to exploration_bounds.allowed
- <3: Too vague — list decisions that need to be made
- 3-7: Good range — proceed

## Step 2: Iterate with user (max 3 rounds)

Ask targeted questions:

1. "What MUST be true throughout this entire project?" → invariants
2. "What does success look like? Be as concrete as possible." → goal
3. "What approaches are you open to exploring? What's off-limits?" → exploration_bounds

## Step 3: Write outputs

Write {work_dir}/constraints.json (schema: objective, goal, invariants, exploration_bounds)
Write {work_dir}/.shaped_input.json (normalized input)
```

### Shaper — `prompts/_shared/shape_seed.md`

```markdown
You are validating a seed idea for the next iteration.

Read:

- {work_dir}/{iter}/reflect.json — the seed from reflection
- {work_dir}/constraints.json — invariants that must hold
- {work_dir}/convergence_log.json — history of past approaches

## Validate

1. Does the seed violate any constraint in constraints.json? → ALERT
2. Is the seed's approach_category the same as the last N entries? → (engine handles via is_converging)
3. Is the seed at appropriate specificity (3-7)? → adjust if needed

## Output

Write {work_dir}/{iter}/.seed_validation.json with:

- status: "pass" | "alert"
- adjustments: any modifications made
- alert_reason: (if status is alert)
```

### Diversifier — `prompts/_shared/explore.md`

```markdown
You are forcing exploration in a new direction. The system has detected convergence —
recent iterations have been too similar.

Read:

- {work_dir}/convergence_log.json — what has been tried
- {work_dir}/constraints.json — boundaries
- shared/knowledge/ — accumulated knowledge

## Your Task

1. List ALL approach_categories tried so far
2. Identify directions NOT yet explored that are within exploration_bounds
3. Pick the most promising untried direction
4. Generate a concrete seed that is FUNDAMENTALLY DIFFERENT from recent iterations
   - Different methodology, different framing, different assumptions
   - NOT a variation of what was tried — a genuine alternative

## Output

Write {work_dir}/{iter}/.explore_seed.json:

- new_seed: concrete description of the new direction
- rationale: why this direction is worth trying
- difference_from_recent: how this differs from the last 3 iterations
```

### Validator — `prompts/ml-experiment/validate_plan.md`

```markdown
You are validating a research plan before execution.

Read:

- {work_dir}/{iter}/research_plan.json — the plan to validate
- {work_dir}/constraints.json — invariants and goal
- shared/knowledge/ — prior research

## Validation Criteria

### Engine-level (MUST pass)

1. All phases respect constraints.invariants
2. Final phase measures constraints.goal.metric (if defined)
3. depends_on forms a valid DAG (no cycles)

### Domain-level (ML research specific)

4. Prior research: domain_research has ≥3 SOTA references
5. Baselines: plan includes non-ML baseline + simple ML baseline phases
6. Phase logic: every phase has a "why" field with domain justification
7. Ablation: plan includes feature importance or ablation phase
8. Statistics: expected_outputs schemas include std/CI, not just mean

## Output

Write {work_dir}/{iter}/.plan_validation.json:

- verdict: "APPROVE" or "REJECT"
- checks: { criterion: pass/fail for each }
- issues: [ specific problems found ]
- required_fixes: [ what must change before approval ]
```

### Synthesizer — `prompts/ml-experiment/story_tell.md`

```markdown
You are writing the final research paper that tells the story of this entire research journey.

Read ALL of these:

- {work_dir}/constraints.json — the original objective and goal
- {work_dir}/.iterations.json — iteration history
- {work*dir}/iter*\*/reflect.json — each iteration's reflection
- {work*dir}/iter*\*/results/ — all experiment results
- {work*dir}/iter*\*/paper_draft.md — iteration-level drafts
- shared/knowledge/ — accumulated prior research

## Paper Structure

# [Title]

## Abstract

[3-5 sentences summarizing the entire research journey and key findings]

## 1. Introduction

[Motivation from constraints.objective, problem definition]

## 2. Related Work

[Synthesize from shared/knowledge/, not just list]

## 3. Method

[Tell the story: "We first tried A (iter_1), which revealed B. This led us to C (iter_2)..."
Show the evolution of thinking, not just the final method]

## 4. Experiments & Results

[Comparison table across ALL iterations' best results]

## 5. Analysis

[Why did the winning approach work? What failed and why?]

## 6. Discussion

[Contributions, limitations, broader implications]

## 7. Conclusion

[Goal achievement vs constraints.goal.success_criteria]

## References

## Write to {work_dir}/final_paper.md
```

### Evaluator — `prompts/ml-experiment/professor.md`

```markdown
You are a professor evaluating a research paper.

Read:

- {work_dir}/final_paper.md — the paper to evaluate
- {work_dir}/constraints.json — the original objective and goal
- {work_dir}/.iterations.json — iteration history (to verify claims)
- {work*dir}/iter*\*/results/ — raw results (to verify numbers)

## Evaluation Criteria (each /10)

1. **Academic Rigor**: Is the experimental design sound? Are results statistically significant?
   Are claims supported by evidence? Is the methodology reproducible?

2. **Experimental Sufficiency**: Are there enough baselines? Is there ablation?
   Error analysis? Cross-validation? Multiple metrics?

3. **Novelty**: What is genuinely new? Is the contribution clear?
   Is it methodological, empirical, or analytical?

4. **Narrative Coherence**: Does Introduction → Conclusion flow logically?
   Is the story of discovery compelling and honest?

5. **Goal Achievement**: Did the research achieve constraints.goal.success_criteria?
   If not, is the shortfall explained and the partial results valuable?

## Scoring

- ACCEPT: total ≥ 40 — research is complete
- REVISE: 35 ≤ total < 40 — needs more experiments (new full iteration)
- REJECT: total < 35 — fundamental issues, restart from SHAPE

## Output

Write {work_dir}/evaluation.json:

- verdict: "ACCEPT" | "REVISE" | "REJECT"
- scores: { criterion: score }
- total: sum
- feedback: [{ criterion, issue, suggestion }]
- required_actions: [what must be done if REVISE]
```

---

## Decisions (resolved)

| Question             | Decision                               | Rationale                                 |
| -------------------- | -------------------------------------- | ----------------------------------------- |
| **유사도 측정**      | Jaccard similarity (키워드 기반)       | Phase 1에서 충분. 임베딩은 나중에 upgrade |
| **REVISE 시 범위**   | 새 full iteration (IDEA_REFINE부터)    | 부분 패치보다 전체 재고가 품질 높음       |
| **DIVERSIFY 자율성** | 자동 (유저 확인 없이 Diversifier 위임) | 자율 실행 맥락에서 유저 개입 최소화       |
| **Prompt 공유**      | 공유 기본 + preset 오버라이드          | shape/validate/explore는 90% 범용         |
| **엔진과 stage**     | 엔진은 stage를 모름                    | 순수 상태 머신. stage는 preset 조직화용   |

---

## Implementation Priority

### Phase 1: Engine Core (엔진 최소 변경)

1. **constraints.json 스키마 정의** + ai_session prompt 자동 주입 로직
2. **`is_converging` 조건 함수** — conditions.py에 추가
3. **`TINYLAB_KNOWLEDGE_DIR` 환경변수** — paths.py에 추가
4. **Prompt 디렉토리 구조** — `prompts/_shared/` 경로 지원

### Phase 2: Shared Prompts + New States

5. **shape_full.md, shape_seed.md** — 공유 프롬프트 작성
6. **explore.md** — Diversifier 공유 프롬프트
7. **validate_plan.md** — ML 연구용 (도메인 특화)
8. **ml-experiment preset 업데이트** — 새 states 추가, 기존 states next 수정

### Phase 3: Narrative

9. **story_tell.md** — ML 연구용 Synthesizer 프롬프트
10. **professor.md** — ML 연구용 Evaluator 프롬프트
11. **STORY_TELL, REVIEW states** — preset에 추가

### Phase 4: New Presets (별도)

12. **review-paper preset** v7 재설계
13. **product-prd preset** 신규

---

## Migration from v6

### 하위호환

- `constraints.json` 없으면 → 주입 스킵 (기존 동작)
- `exploration` 필드 없으면 → `is_converging` 항상 false (Diversifier 비활성)
- `SHAPE_SEED` state 없으면 → REFLECT 직후 기존 REFLECT_DONE 동작
- 기존 v6 preset은 그대로 동작

### 마이그레이션

- v6 `PLAN_REVIEW` (checkpoint) → v7 `VALIDATE_PLAN` (ai_session)으로 수동 변경
- v6 `REFLECT_DONE` → v7 `SHAPE_SEED` + `ROUTE` 두 state로 분리
