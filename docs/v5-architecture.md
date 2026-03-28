# tiny-lab v5 Architecture — Plan-Driven Phase Executor

## 핵심 변경

v4: hypothesis queue → optimizer loop (모든 실험이 같은 구조)
v5: RESEARCH_PLAN → phase별 코드 생성·실행 (각 phase가 다른 종류의 실험)

```
v4:  [hypothesis queue] → BUILD(flag) → OPTIMIZE → EVALUATE → repeat
v5:  [RESEARCH_PLAN]    → PHASE_CODE(AI writes script) → RUN → EVALUATE → next phase
```

**Breaking changes:**

- Claude Code only (Codex 지원 제거). Hook, Tool을 네이티브로 사용.
- v4 하위호환 없음.

---

## 1. 핵심 개념

### 두 개의 YAML — 역할 분리

|          | workflow.yaml                          | research_plan.yaml                   |
| -------- | -------------------------------------- | ------------------------------------ |
| **정의** | 시스템이 어떻게 움직이나 (상태 머신)   | 실험을 뭘 하나 (연구 내용)           |
| **생성** | `tiny-lab init --preset`에서 복사      | PLAN 상태에서 AI가 생성              |
| **시점** | 실행 전                                | 실행 중 (Understanding 이후)         |
| **수정** | 사용자/프리셋                          | AI + 사용자                          |
| **예시** | DOMAIN_RESEARCH → DATA_DEEP_DIVE → ... | phase_0: 전처리, phase_1: 베이스라인 |

**workflow가 외부 루프, research_plan이 내부 데이터.**

```
workflow.yaml (공장 라인)          research_plan.yaml (작업 지시서)
──────────────────────────        ──────────────────────────────

DOMAIN_RESEARCH                   (아직 없음)
DATA_DEEP_DIVE                    (아직 없음)
IDEA_REFINE                       (아직 없음)
PLAN ──────────────────────────→  여기서 생성됨:
PLAN_REVIEW                         phase_0: 전처리
                                    phase_1: 베이스라인
┌─ PHASE_SELECT ──────────────→    "다음?" → phase_0 꺼냄
│  PHASE_CODE ─────────────────→   phase_0.methodology 보고 코드 생성
│  PHASE_RUN ──────────────────→   스크립트 실행
│  PHASE_EVALUATE ─────────────→   phase_0.expected_outputs.schema로 검증
│  PHASE_RECORD
│  CHECKPOINT
│  PHASE_SELECT ──────────────→    "다음?" → phase_1 꺼냄
│  ... 반복 ...
│  PHASE_SELECT ──────────────→    "다음?" → 없음 → REFLECT
└──
REFLECT
```

### Phase 유형

연구 작업의 단위. 각 phase는 독립적인 종류의 실험.

| Phase 유형 | 설명                     | 예시                             |
| ---------- | ------------------------ | -------------------------------- |
| `script`   | AI가 코드 생성·실행      | dead reckoning, ablation, 전처리 |
| `optimize` | optimizer 내부 루프 사용 | 하이퍼파라미터 튜닝, 모델 비교   |
| `manual`   | 외부 입력 대기           | 데이터 수집, 사람 평가           |

### 각 Phase는 자기 환경을 스스로 만든다

ai-lab에서 검증된 패턴: 각 phase 스크립트가 필요한 도구를 직접 설치하고 사용.

```python
# phase3_architecture.py
import subprocess, sys

def ensure_deps():
    for pkg in ["torch", "scikit-learn", "matplotlib"]:
        try:
            __import__(pkg)
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])

ensure_deps()
import torch
import torch.nn as nn
```

- Phase 0(전처리)은 pandas + numpy면 충분
- Phase 3(아키텍처 비교)은 torch + sklearn
- AI가 methodology에 맞는 도구를 선택·설치
- 스크립트 하나로 재현 가능

---

## 2. 상태 머신

```
         ┌──────────── UNDERSTANDING ────────────────┐
         │                                            │
  INIT ──→ DOMAIN_RESEARCH → DATA_DEEP_DIVE → IDEA_REFINE → PLAN
  (부트)                                        ↑     ↓        │
  (하드코딩)                                    └(질문)┘        │
                                                                │
         ┌─ PLAN_REVIEW ←──────────────────────────────────────┘
         │       │
         │ ┌─────┴──── EXECUTION LOOP ────────────┐
         │ │                                       │
         │ │   PHASE_SELECT                        │
         │ │       │                               │
         │ │   PHASE_CODE                          │
         │ │       │                               │
         │ │   PHASE_RUN                           │
         │ │       │                               │
         │ │   PHASE_EVALUATE                      │
         │ │       │                               │
         │ │   PHASE_RECORD                        │
         │ │       │                               │
         │ │   CHECKPOINT ─────────────────────────┘
         │ │       │
         │ └───────┤ (plan modified → PLAN_REVIEW)
         │         │
         └─────────┤ (all phases done)
                   │
                REFLECT
                   │
     ┌─────────────┼──────────────────┐
     ▼             ▼                  ▼
   DONE     PLAN (phase 추가)   IDEA_REFINE (아이디어 수정)
              │                   │
              └→ PLAN_REVIEW      └→ PLAN → ...
                                  (극단: DOMAIN_RESEARCH부터)
```

### INIT — 부트스트랩 (workflow 외부)

INIT은 workflow.yaml을 로드하는 행위 자체이므로 workflow 안에 정의하면 순환.
tiny-lab process가 하드코딩으로 처리하고, workflow의 첫 상태부터 시작.

```
1. research/ 디렉토리 존재 확인 (없으면 생성)
2. workflow.yaml 로드 + 검증 (상태 이름 중복, 순환 참조, 필수 필드)
3. .state.json 확인:
   ├─ 없음 → 첫 실행. workflow 첫 상태로 전이
   ├─ 있음 + resumable → crash recovery. 마지막 상태에서 재개
   └─ 있음 + DONE → fork/resume 명시적으로 해야 재시작
4. shared/ 디렉토리 생성 (없으면)
5. iter_1/ 디렉토리 생성 (첫 실행 시)
6. lock 획득 (동시 실행 방지)
```

### Understanding — 계획 전에 깊이 이해한다

사용자가 아이디어와 데이터셋을 제공하면, 바로 계획을 짜지 않고 3단계를 거친다.

#### DOMAIN_RESEARCH — 도메인 선행 연구 조사

```
입력: 사용자 아이디어 + 데이터셋 위치 + 도메인 문서 (선택)

수행:
  1. 도메인 키워드 추출
  2. 선행 연구 검색 (WebSearch)
  3. 논문/벤치마크에서 SOTA, 필수 전처리, 표준 메트릭, 알려진 함정 추출
  4. 사용자 도메인 문서 분석

산출물: research/{iter}/.domain_research.yaml
  domain_type, sota_models, required_preprocessing,
  standard_metrics, known_pitfalls, references
```

#### DATA_DEEP_DIVE — 도메인 지식 기반 데이터 분석

도메인 지식 없이 EDA를 하면 "column X has 50% NaN"만 보이지만,
도메인 지식이 있으면 "airspeed 50% NaN은 정상 — 이착륙 시 안 켜짐"을 알 수 있다.

```
수행: 스키마 분석, 통계, 도메인 기반 해석, 피처-타겟 상관관계, 품질 이슈

산출물: research/{iter}/.data_analysis.yaml
  files, features (with domain_note), quality_issues
```

#### IDEA_REFINE — Socratic 질문으로 아이디어 구체화

Socrates Protocol 차용:

```
Step 1: 아이디어를 검증 가능한 명제로 분해
Step 2: 결정 가능성 검증 (정의/관찰/평가/재현 가능?)
Step 3: 결정 불가능한 점마다 질문 (1-3개, 임팩트 순)
Step 4: 모든 명제가 결정 가능하면 → PLAN

산출물: research/{iter}/.idea_refined.yaml
  goal, inputs, outputs, metric (with target), constraints,
  preprocessing_required, gap_analysis
```

자율 모드에서 `interactive: true`인 상태의 동작은 `interactive_fallback`으로 결정:

| 값            | 동작                                       | 시나리오                    |
| ------------- | ------------------------------------------ | --------------------------- |
| `wait`        | intervention 대기                          | nanoclaw lab manager가 답변 |
| `self_answer` | AI가 도메인 연구 결과를 근거로 스스로 판단 | 완전 자율 모드              |
| `skip`        | 현재까지 아는 것으로 PLAN 진행             | 아이디어가 이미 구체적      |

`autonomy.mode: autonomous`이면 기본 `self_answer`, `supervised`이면 기본 `wait`.

### REFLECT — 학습 루프의 핵심

REFLECT는 터미널이 아니다. 결과에서 학습하고 다음 행동을 결정하는 상태.

```
REFLECT 분기:
  ├─ 목표 달성 → DONE
  ├─ 현재 방향 유지, phase 추가 → PLAN
  ├─ 아이디어 자체 수정 → IDEA_REFINE (새 iteration)
  └─ 도메인 이해 부족 → DOMAIN_RESEARCH (새 iteration)
```

RL 구조:

```
State:   누적 연구 지식 (도메인 + 데이터 + 실험 결과)
Action:  다음 실험 선택 (plan phases)
Reward:  메트릭 개선 또는 새 지식
Policy:  REFLECT가 전략 업데이트

Episode:
  Understanding → Plan → Execute → Reflect
    → (learn) → Plan' → Execute' → Reflect'
    → (idea mutation) → Understanding' → Plan'' → ...
```

### 상태 요약

| 상태                | type       | 역할                          | 산출물                  |
| ------------------- | ---------- | ----------------------------- | ----------------------- |
| **DOMAIN_RESEARCH** | ai_session | 도메인 선행 연구              | `.domain_research.yaml` |
| **DATA_DEEP_DIVE**  | ai_session | 도메인 기반 데이터 분석       | `.data_analysis.yaml`   |
| **IDEA_REFINE**     | ai_session | Socratic 아이디어 구체화      | `.idea_refined.yaml`    |
| **PLAN**            | ai_session | research_plan.yaml 생성       | `research_plan.yaml`    |
| **PLAN_REVIEW**     | checkpoint | 승인 대기                     | —                       |
| **PHASE_SELECT**    | process    | plan에서 다음 phase 선택      | —                       |
| **PHASE_CODE**      | ai_session | phase 스크립트 생성           | `phases/phase_*.py`     |
| **PHASE_RUN**       | process    | 스크립트 실행                 | stdout/stderr           |
| **PHASE_EVALUATE**  | process    | 산출물 스키마 검증            | pass/fail               |
| **PHASE_RECORD**    | process    | 결과 기록, plan 상태 업데이트 | `results/phase_*.json`  |
| **CHECKPOINT**      | checkpoint | intervention 확인             | —                       |
| **REFLECT**         | ai_session | 결과 분석, 다음 행동 결정     | `reflect.yaml`          |
| **REFLECT_DONE**    | process    | iteration 전이 결정           | —                       |

---

## 3. research_plan.yaml 스키마

```yaml
name: uav-gnss-denied
description: "GPS-denied UAV position estimation"
created_at: 2026-03-29T00:00:00Z
status: in_progress # draft | reviewing | in_progress | completed

background:
  problem: "GPS 재밍 시 자율비행 불가"
  goal: "IMU/자세/기속도 → NED 위치 추정"
  data:
    source: "IDF-DS (Holybro Pixhawk, 120 flights)"
    rows: 60000
    sampling_hz: 2000
  inputs:
    ["IMU delta (8)", "accelerometer (3)", "quaternion (4)", "airspeed (2)"]
  outputs: ["NED position: x, y, z (meters)"]
  domain_constraints:
    - "EKF 추정값 ~1-1.5% 오차"
    - "두 하드웨어 혼합 금지"
  references:
    - "García-Gascón et al., Scientific Data, 2026"

# 메트릭 — optional (data-analysis 프리셋은 없을 수 있음)
metric:
  name: ate_30s_m
  description: "30초 구간 ATE (meters)"
  direction: minimize
  target: 50 # REFLECT에서 달성 여부 판단

# metric이 없으면 qualitative goal 사용
goal:
  description: "호텔 취소율의 주요 요인 3개 이상 식별"
  success_criteria:
    - "각 요인의 통계적 유의성 p < 0.05"

# Phase 정의
phases:
  - id: phase_0
    name: "데이터 파이프라인"
    why: "raw IMU에 중력 포함, body frame → 노이즈를 패턴으로 학습"
    type: script
    depends_on: []
    methodology:
      - "중력 제거: 쿼터니언으로 body→NED 변환 후 [0,0,9.81] 차감"
      - "다중 주파수 정렬: airspeed 선형 보간"
    expected_outputs:
      files: ["data/preprocessed/{flight_id}_processed.csv"]
      report:
        path: "research/results/phase_0.json"
        schema:
          gravity_removed: { type: boolean }
          rows_after: { type: integer }
    status: pending # pending | running | done | failed | skipped

  - id: phase_3
    name: "아키텍처 비교"
    why: "어떤 모델 구조가 최적인지 공정 비교"
    type: optimize
    depends_on: [phase_0, phase_1]
    methodology: ["동일 데이터, 동일 split, 동일 time budget"]
    optimize:
      type: random
      time_budget: 300
      n_trials: 20
      approaches:
        lstm: { model: lstm }
        gru: { model: gru }
      search_space:
        lstm:
          hidden_size: { type: int, low: 64, high: 512 }
    expected_outputs:
      report:
        path: "research/results/phase_3.json"
        schema:
          best_model: { type: string }
          best_ate_30s_m: { type: number }
    status: pending
```

### Plan 생성 원칙 (RESEARCH_PLAN_WORKFLOW.md에서 검증)

```
1. 모든 Phase에 파일 경로가 있어야 한다
2. JSON 스키마를 미리 정의한다 — 스키마가 AI의 행동을 결정
3. "왜"가 실행 순서를 결정한다 — 없으면 스킵될 수 있음
4. 리포트 간 참조 관계가 있어야 한다
5. Phase 간 코드 재사용을 명시한다
```

---

## 4. 파일 구조 — Iteration 관리

각 Understanding → Plan → Execute → Reflect 사이클이 하나의 iteration.

```
project/
  research/
    .workflow.yaml                  # 상태 머신 정의 (프리셋에서 복사)
    .state.json                     # 현재 상태 (iteration, phase, crash recovery)
    .intervention.yaml              # lab manager 개입 파일
    .iterations.yaml                # iteration 인덱스

    iter_1/                         # ── 첫 번째 연구 사이클 ──
      research_plan.yaml
      .domain_research.yaml
      .data_analysis.yaml
      .idea_refined.yaml
      reflect.yaml
      phases/
        phase_0_data_pipeline.py
        phase_1_dead_reckoning.py
      results/
        phase_0.json
        phase_1.json

    iter_2/                         # ── 두 번째 사이클 (아이디어 수정) ──
      research_plan.yaml
      .idea_refined.yaml
      reflect.yaml
      phases/
        phase_4_velocity_model.py
      results/
        phase_4.json

  shared/                           # ── iteration 간 공유 ──
    data/
      raw/                          # 원본 (불변)
      preprocessed/                 # 전처리 결과
    models/                         # 체크포인트
    lib/                            # 재사용 코드
```

### 교차 참조

```yaml
# iter_2/research_plan.yaml
phases:
  - id: phase_0
    reuse_from: "iter_1/phases/phase_0_data_pipeline.py" # 코드 재사용

  - id: phase_4
    context_refs:
      baseline_ate: "iter_1/results/phase_1.json#ate_30s_mean_m"
```

### .iterations.yaml

```yaml
current_iteration: 2
iterations:
  - id: 1
    idea: "IMU → 위치 직접 추정"
    best_result: { model: resnet_tcn, ate_30s: 19.6 }
    decision: idea_mutation
    reason: "velocity 피처가 position보다 예측력이 높음"
  - id: 2
    idea: "IMU → 속도 추정 → 적분으로 위치"
    idea_diff: "위치 직접 추정 → 속도 추정 + 적분"
    best_result: { model: lstm_velocity, ate_30s: 12.3 }
    decision: done
```

---

## 5. Intervention Protocol

lab manager(nanoclaw)가 tiny-lab에 개입하는 인터페이스.

```yaml
# research/.intervention.yaml
action: modify_plan # approve | modify_plan | skip_phase | add_phase | stop
timestamp: 2026-03-29T10:00:00Z
source: lab_manager

modify_plan:
  phase_id: phase_3
  changes:
    - field: methodology
      value: "TCN 제외, ResNet-TCN 추가"
```

checkpoint 동작:

```
CHECKPOINT
  ├─ .intervention.yaml 존재?
  │   ├─ approve → 다음 phase
  │   ├─ modify_plan → PLAN
  │   ├─ skip_phase → phase skipped → 다음 phase
  │   ├─ add_phase → plan에 추가
  │   └─ stop → DONE
  └─ 없음?
      ├─ timeout 이내 → 대기
      └─ timeout 초과 → 자동 approve
```

---

## 6. Phase 실행 상세

### type: script (범용)

```
PHASE_CODE:
  AI에게 전달하는 컨텍스트 (하이브리드 주입):
    - 주입: iter, current_phase_id, current_phase_name, current_phase_type
    - AI가 Read: research_plan.yaml (methodology), results/*.json (이전 결과)

  AI가 생성:
    - research/{iter}/phases/phase_{n}_{name}.py
      - 상단: 의존성 자동 설치 (ensure_deps)
      - 중단: 이전 phase 결과 로딩
      - 하단: plan의 schema에 맞춰 JSON 저장

PHASE_RUN:
  python research/{iter}/phases/phase_{n}_{name}.py

PHASE_EVALUATE:
  - results/phase_{n}.json 존재 + plan schema 매칭 확인
```

### type: optimize (튜닝)

v4의 optimizer 루프를 phase 단위로 재사용.

```
PHASE_CODE: AI가 CLI flags 받는 train script 생성
PHASE_RUN: optimizer 내부 루프 (random/grid/custom)
  for approach in approaches:
    for trial in range(n_trials):
      cmd = inject_flag(base_cmd, params) → run → extract_metric
PHASE_EVALUATE: best 결과를 results/phase_{n}.json에 기록
```

### type: manual (대기)

```
PHASE_RUN: .intervention.yaml에 complete action 올 때까지 대기
```

---

## 7. 실행 아키텍처 — 3-Layer

```
┌─────────────────────────────────────────────────────┐
│  tiny-lab process (Python, 결정론적 outer loop)      │
│  - iteration 생명주기, carry-over, 대기 상태 관리    │
│  - 각 상태마다 AI 세션 호출                          │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │  AI 세션 (Claude Code, 한 상태씩 실행)        │   │
│  │                                                │   │
│  │  ┌────────────────────────────────────────┐   │   │
│  │  │  Hook (Shell, 결정론적 강제)            │   │   │
│  │  │  - 현재 상태 밖 행동 차단               │   │   │
│  │  │  - 산출물 검증 → 상태 전이              │   │   │
│  │  └────────────────────────────────────────┘   │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

| 누가                          | 무엇을                                        | 왜                           |
| ----------------------------- | --------------------------------------------- | ---------------------------- |
| **Hook** (shell)              | 상태 안에서 행동 제한 + 산출물 기반 상태 전이 | 결정론적, AI 우회 불가       |
| **tiny-lab process** (Python) | iteration 생성, carry-over, 조건부 전이, 대기 | 파일시스템 작업, 복잡한 로직 |
| **AI** (Claude Code)          | 각 상태의 실제 작업 수행                      | 추론, 코드 생성, 분석        |

### Claude Code Native

Codex 지원 제거. Hook이 상태 강제의 핵심이므로 Claude Code만 지원.

```
Claude Code 기능          │ v5에서의 역할
─────────────────────────┼───────────────────────────
PreToolUse hook          │ 상태 기반 행동 차단
PostToolUse hook         │ 산출물 검증 → 자동 상태 전이
CLAUDE.md                │ 상태별 AI 행동 가이드
Tool: Read/Write/Edit    │ plan, code, 산출물 작성
Tool: Bash               │ phase 스크립트 실행, pip install
Tool: WebSearch          │ DOMAIN_RESEARCH 논문 검색
Agent (subagent)         │ 병렬 phase 실행
```

### AI 세션 호출

```python
# v5 — Claude Code 직접 호출
def run_state(state: str, context: dict) -> subprocess.CompletedProcess:
    prompt = build_state_prompt(state, context)
    return subprocess.run(
        ["claude", "--print", "--prompt", prompt,
         "--allowedTools", ",".join(ALLOWED_TOOLS[state])],
        capture_output=True, text=True, cwd=str(project_dir),
    )
```

### 프롬프트 컨텍스트 주입 (하이브리드)

```yaml
# workflow.yaml
- id: PHASE_CODE
  type: ai_session
  prompt: "prompts/phase_code.md"
  context: # 프롬프트에 변수로 주입
    - iter # 현재 iteration
    - current_phase # PHASE_SELECT가 설정한 phase 정보
    - previous_results_summary # 이전 phase 결과 요약
```

핵심 컨텍스트는 변수로 주입, 상세 데이터(methodology 전문, 결과)는 AI가 Read로 직접 읽음.

### tiny-lab process outer loop

```python
while not done:
    state = load_state()

    if state in AI_STATES:
        run_state(state, context)
        # hook이 산출물 검증 → 상태 전이

    elif state in PROCESS_STATES:
        next_state = handle_process_state(state, workflow)
        set_state(next_state)

    elif state in CHECKPOINT_STATES:
        next_state = handle_checkpoint(state, timeout)
        set_state(next_state)
```

### Auto mode — REFLECT 이후 iteration 전이

```python
# REFLECT_DONE 처리 (process)
decision = read_reflect_yaml()

if decision == "done":
    break
elif decision == "add_phases":
    set_state("PLAN")
elif decision == "idea_mutation":
    create_iteration_dir(iter_n + 1)
    carry_over(from=iter_n, artifacts=[domain_research, data_analysis])
    set_state("IDEA_REFINE")
elif decision == "domain_pivot":
    create_iteration_dir(iter_n + 1)
    set_state("DOMAIN_RESEARCH")
```

---

## 8. 메타 워크플로우 — workflow.yaml

상태 머신을 코드에 하드코딩하지 않는다. workflow.yaml이 정의.
Hook은 이 YAML을 읽고 범용적으로 강제한다.

### 상태 정의 스키마

```yaml
# research/.workflow.yaml

autonomy:
  mode: autonomous # autonomous | supervised
  max_iterations: 5
  allow_idea_mutation: true
  stop_on_target: true
  circuit_breaker:
    max_consecutive_failures: 3

intervention:
  checkpoint: between_phases # between_phases | on_failure | never
  timeout_seconds: 3600

states:
  # ── Understanding ──
  - id: DOMAIN_RESEARCH
    type: ai_session
    prompt: "prompts/domain_research.md"
    allowed_tools: [WebSearch, WebFetch, Read, Write]
    allowed_write_globs:
      - "research/{iter}/.domain_research.yaml"
    completion:
      artifact: "research/{iter}/.domain_research.yaml"
      required_fields: [domain_type, sota_models, references]
    error:
      max_retries: 2
      on_exhaust: skip
    next: DATA_DEEP_DIVE

  - id: DATA_DEEP_DIVE
    type: ai_session
    prompt: "prompts/data_deep_dive.md"
    allowed_tools: [Read, Bash, Write]
    allowed_write_globs:
      - "research/{iter}/.data_analysis.yaml"
    completion:
      artifact: "research/{iter}/.data_analysis.yaml"
      required_fields: [files, features]
    next: IDEA_REFINE

  - id: IDEA_REFINE
    type: ai_session
    prompt: "prompts/idea_refine.md"
    allowed_tools: [Read, Write]
    interactive: true
    interactive_fallback: self_answer # self_answer | wait | skip
    allowed_write_globs:
      - "research/{iter}/.idea_refined.yaml"
    completion:
      artifact: "research/{iter}/.idea_refined.yaml"
      required_fields: [goal, inputs, outputs, metric]
    next: PLAN

  # ── Planning ──
  - id: PLAN
    type: ai_session
    prompt: "prompts/plan.md"
    allowed_tools: [Read, Write]
    allowed_write_globs:
      - "research/{iter}/research_plan.yaml"
    context: [iter, domain_research, data_analysis, idea_refined]
    completion:
      artifact: "research/{iter}/research_plan.yaml"
      required_fields: [name, phases]
    next: PLAN_REVIEW

  - id: PLAN_REVIEW
    type: checkpoint
    condition:
      source: "research/.intervention.yaml"
      field: action
    next:
      approve: PHASE_SELECT
      modify_plan: PLAN
      stop: DONE

  # ── Execution Loop ──
  - id: PHASE_SELECT
    type: process
    condition:
      check: has_pending_phases
    next:
      "true": PHASE_CODE
      "false": REFLECT

  - id: PHASE_CODE
    type: ai_session
    prompt: "prompts/phase_code.md"
    allowed_tools: [Read, Write, Edit, Bash]
    allowed_write_globs:
      - "research/{iter}/phases/*"
      - "shared/lib/*"
    blocked_bash_patterns:
      - "python research/*/phases/*"
    context: [iter, current_phase, previous_results_summary]
    completion:
      artifact: "research/{iter}/phases/phase_*.py"
    error:
      max_retries: 2
      on_exhaust: skip_phase
    next: PHASE_RUN

  - id: PHASE_RUN
    type: process
    blocked_write_globs:
      - "research/{iter}/phases/*"
    error:
      max_retries: 1
      on_exhaust: ask
    next: PHASE_EVALUATE

  - id: PHASE_EVALUATE
    type: process
    error:
      max_retries: 2
      retry_to: PHASE_CODE
      on_exhaust: skip_phase
    next: PHASE_RECORD

  - id: PHASE_RECORD
    type: process
    next: CHECKPOINT

  - id: CHECKPOINT
    type: checkpoint
    condition:
      source: "research/.intervention.yaml"
      field: action
    next:
      approve: PHASE_SELECT
      modify_plan: PLAN
      skip_phase: PHASE_SELECT
      add_phase: PHASE_SELECT
      stop: DONE

  # ── Reflection ──
  - id: REFLECT
    type: ai_session
    prompt: "prompts/reflect.md"
    allowed_tools: [Read, Write]
    allowed_write_globs:
      - "research/{iter}/reflect.yaml"
    context: [iter, all_results, iterations_history]
    completion:
      artifact: "research/{iter}/reflect.yaml"
      required_fields: [decision, reason]
    next: REFLECT_DONE

  - id: REFLECT_DONE
    type: process
    condition:
      source: "research/{iter}/reflect.yaml"
      field: decision
    next:
      done: DONE
      add_phases: PLAN
      idea_mutation: IDEA_REFINE
      domain_pivot: DOMAIN_RESEARCH
```

### 상태 전이 규칙

```
type: ai_session  → next는 단일 값. hook이 산출물 감지 → 자동 전이.
type: process     → next는 dict. condition으로 파일/필드 읽기 → Python이 분기.
type: checkpoint  → next는 dict. intervention 파일 읽기 → Python이 분기.
```

조건부 전이 범용 처리:

```python
def handle_conditional_next(state_def, iter_dir):
    condition = state_def["condition"]

    # 빌트인 체크
    if "check" in condition:
        value = str(run_builtin_check(condition["check"]))
    # 파일 필드 읽기
    else:
        source = condition["source"].replace("{iter}", iter_dir)
        data = yaml.safe_load(open(source))
        value = data[condition["field"]]

    return state_def["next"].get(value, state_def["next"].get("default", "DONE"))
```

빌트인 체크 (소수):

- `has_pending_phases` — plan에 pending phase 남았는지
- `timeout_exceeded` — checkpoint 타임아웃
- `max_iterations_reached` — 자율 모드 반복 제한

### 범용 Hook

Hook은 workflow.yaml을 읽고 동적으로 규칙 적용. 상태별 case 문 없음.

**PreToolUse — 범용 게이트:**

```bash
#!/bin/bash
# workflow.yaml에서 현재 상태의 allowed_write_globs, blocked_bash_patterns 읽기
# 매칭 안 되면 BLOCKED
```

**PostToolUse — 범용 전이:**

```bash
#!/bin/bash
# workflow.yaml에서 현재 상태의 completion.artifact + required_fields 읽기
# 산출물 존재 + 필드 검증 → state.json 업데이트
```

---

## 9. 프리셋

연구 유형마다 워크플로우가 다르다.

```bash
tiny-lab init --preset ml-experiment    # ML 실험 (기본)
tiny-lab init --preset review-paper     # 리뷰 논문
tiny-lab init --preset novel-method     # 새 방법론 논문
tiny-lab init --preset data-analysis    # 데이터 분석
tiny-lab init --preset custom           # 빈 워크플로우
```

### ml-experiment (기본)

```
DOMAIN_RESEARCH → DATA_DEEP_DIVE → IDEA_REFINE
  → PLAN → PLAN_REVIEW
  → [PHASE: 전처리 → 베이스라인 → 아키텍처비교 → 튜닝 → 평가]
  → REFLECT
```

(위 섹션 8의 전체 workflow.yaml)

### review-paper

코드 실행 없이 문헌 분석만.

```yaml
states:
  - id: SCOPE_DEFINITION
    type: ai_session
    prompt: "prompts/review/scope.md"
    completion:
      artifact: "research/{iter}/.scope.yaml"
      required_fields:
        [research_questions, inclusion_criteria, exclusion_criteria]
    next: LITERATURE_SEARCH

  - id: LITERATURE_SEARCH
    type: ai_session
    allowed_tools: [WebSearch, WebFetch, Read, Write]
    completion:
      artifact: "research/{iter}/.papers_collected.yaml"
      required_fields: [papers, total_found, after_screening]
    next: PAPER_ANALYSIS

  - id: PAPER_ANALYSIS
    type: ai_session
    completion:
      artifact: "research/{iter}/.paper_analysis.yaml"
      required_fields: [themes, comparisons, gaps]
    next: TAXONOMY

  - id: TAXONOMY
    type: ai_session
    completion:
      artifact: "research/{iter}/.taxonomy.yaml"
      required_fields: [categories, classification_criteria]
    next: SYNTHESIS

  - id: SYNTHESIS
    type: ai_session
    completion:
      artifact: "research/{iter}/review_draft.md"
    next: REFLECT

  - id: REFLECT
    # ... 동일
  - id: REFLECT_DONE
    type: process
    condition:
      source: "research/{iter}/reflect.yaml"
      field: decision
    next:
      done: DONE
      more_search: LITERATURE_SEARCH
```

### novel-method

기존 연구 조사 + 방법론 설계 + 구현 + 비교 실험 + 논문 작성.
ml-experiment 대비 추가: RELATED_WORK, METHOD_DESIGN, PAPER_DRAFT.

```yaml
states:
  - id: DOMAIN_RESEARCH
    next: RELATED_WORK
  - id: RELATED_WORK
    type: ai_session
    allowed_tools: [WebSearch, WebFetch, Read, Write]
    completion:
      artifact: "research/{iter}/.related_work.yaml"
      required_fields: [papers, limitations_of_existing, research_gap]
    next: DATA_DEEP_DIVE
  - id: DATA_DEEP_DIVE
    next: IDEA_REFINE
  - id: IDEA_REFINE
    completion:
      required_fields: [goal, inputs, outputs, metric, novelty_claim]
    next: METHOD_DESIGN
  - id: METHOD_DESIGN
    type: ai_session
    prompt: "prompts/novel/method_design.md"
    completion:
      artifact: "research/{iter}/.method_design.yaml"
      required_fields:
        [
          architecture,
          training_procedure,
          loss_function,
          theoretical_justification,
        ]
    next: PLAN
  # ... PLAN → execution loop → REFLECT
  - id: REFLECT
    next: PAPER_DRAFT
  - id: PAPER_DRAFT
    type: ai_session
    prompt: "prompts/novel/paper_draft.md"
    completion:
      artifact: "research/{iter}/paper_draft.md"
    next: REFLECT_DONE
```

### data-analysis

EDA + 통계 + 시각화 + 인사이트. metric 대신 qualitative goal.

```yaml
states:
  - id: DOMAIN_RESEARCH
    next: DATA_DEEP_DIVE
  - id: DATA_DEEP_DIVE
    next: IDEA_REFINE
  - id: IDEA_REFINE
    completion:
      required_fields: [goal, inputs, success_criteria] # metric 대신 success_criteria
    next: PLAN
  # PLAN → execution loop (script type만, optimize 없음)
  - id: PHASE_SELECT
    # ...
  - id: PHASE_CODE
    # ...
  - id: PHASE_RUN
    # ...
  - id: PHASE_EVALUATE
    # ...
  - id: PHASE_RECORD
    next: CHECKPOINT
  - id: CHECKPOINT
    # ...
  - id: REFLECT
    # goal.success_criteria로 판단
    next: REFLECT_DONE
```

### 프리셋 파일 구조

```
src/tiny_lab/presets/
  ml-experiment.yaml
  review-paper.yaml
  novel-method.yaml
  data-analysis.yaml
  custom.yaml
```

`tiny-lab init --preset X` → `presets/X.yaml`을 `research/.workflow.yaml`로 복사.

### 커스터마이징 예시

```yaml
# 경쟁사 분석 추가
- id: DOMAIN_RESEARCH
  next: COMPETITOR_ANALYSIS # 변경

- id: COMPETITOR_ANALYSIS # 새 상태
  type: ai_session
  prompt: "prompts/competitor_analysis.md"
  allowed_tools: [WebSearch, WebFetch, Read, Write]
  completion:
    artifact: "research/{iter}/.competitor_analysis.yaml"
    required_fields: [competitors, market_position]
  next: DATA_DEEP_DIVE
```

코드 변경 0줄. YAML만 수정.

---

## 10. 재진입 (Resume & Fork)

### 시나리오별 동작

| 시나리오                      | 명령                                    | 동작                              |
| ----------------------------- | --------------------------------------- | --------------------------------- |
| "Deep-MLP도 돌려봐"           | `tiny-lab resume --add-phase "..."`     | 같은 iteration에 phase 추가       |
| "전처리 재사용, 다른 모델"    | `tiny-lab fork --enter PLAN`            | 새 iter, understanding carry-over |
| "아이디어 자체를 바꾸고 싶어" | `tiny-lab fork --enter IDEA_REFINE`     | 새 iter, domain+data carry-over   |
| "도메인 조사부터 다시"        | `tiny-lab fork --enter DOMAIN_RESEARCH` | 새 iter, shared/만 유지           |

### fork carry-over 규칙

```
--enter DOMAIN_RESEARCH  → carry-over 없음
--enter DATA_DEEP_DIVE   → .domain_research.yaml
--enter IDEA_REFINE      → .domain_research + .data_analysis
--enter PLAN             → 위 전부 + .idea_refined + 이전 results 참조 가능
```

### CLI

```bash
# 처음부터
tiny-lab run
tiny-lab run "호텔 취소 예측 최적화"

# 재개
tiny-lab resume
tiny-lab resume --add-phase "Deep-MLP 비교"
tiny-lab resume --from phase_3

# fork
tiny-lab fork
tiny-lab fork --enter IDEA_REFINE
tiny-lab fork --enter PLAN --idea "속도 추정"
tiny-lab fork iter_1 --enter DOMAIN_RESEARCH

# 모니터링
tiny-lab status
tiny-lab board
tiny-lab board --iter 1

# 개입
tiny-lab intervene skip phase_2
tiny-lab intervene modify phase_3 time_budget=600
tiny-lab stop
```

---

## 11. nanoclaw 연동

```
nanoclaw ai-lab agent                    tiny-lab (host process)
  │                                         │
  ├─ "Start UAV experiment"                 │
  │   └─ schedule_task: tiny-lab run ────→  │ INIT → Understanding → PLAN
  │                                         │
  │ (reads mounted research/)               │ PLAN_REVIEW (checkpoint)
  │   └─ reads research_plan.yaml           │   ← waiting
  │   └─ writes .intervention.yaml ───────→ │   approve
  │                                         │ PHASE_SELECT → PHASE_CODE → ...
  │                                         │
  │ (periodic check)                        │ CHECKPOINT
  │   └─ reads results/phase_0.json         │   ← waiting
  │   └─ writes .intervention.yaml ───────→ │   approve
  │                                         │
  │ (user: "skip ablation")                 │
  │   └─ writes .intervention.yaml ───────→ │   skip_phase
  │                                         │
  │ (final)                                 │ REFLECT → DONE
  │   └─ reads report.md → user에게 요약    │
```

---

## 12. v4에서 보존/삭제

### 보존

| v4 모듈         | v5에서의 역할                    |
| --------------- | -------------------------------- |
| `optimize.py`   | phase type=optimize의 실행 엔진  |
| `inject_flag()` | optimize phase에서 CLI flag 주입 |
| `evaluate.py`   | phase 결과 metric 추출           |
| `events.py`     | nanoclaw 연동용 이벤트           |
| `lock.py`       | 단일 인스턴스 보장               |
| `schemas.py`    | plan/result 검증                 |
| `server.py`     | 대시보드/API                     |

### 삭제

| v4 모듈             | 이유                     |
| ------------------- | ------------------------ |
| `providers/` (전체) | Claude Code only         |
| `pipeline.py`       | Claude Code 세션이 대체  |
| `envutil.py`        | provider 감지 불필요     |
| `queue.py`          | plan phases로 대체       |
| `generate.py`       | plan generation으로 대체 |
| `build.py` (대부분) | inject_flag만 보존       |
| `baseline.py`       | plan phase로 흡수        |
| `migrate.py`        | v4 호환 불필요           |
| `templates/codex/`  | Codex 제거               |

---

## 13. 구현 순서

```
Step 1:  workflow.yaml 파서 + 스키마 검증 + 조건부 전이 엔진
Step 2:  상태 머신 코어 (outer loop, crash recovery, lock)
Step 3:  범용 Hook (state-gate.sh, state-advance.sh)
Step 4:  DOMAIN_RESEARCH (WebSearch + 논문 분석)
Step 5:  DATA_DEEP_DIVE (EDA + 도메인 해석)
Step 6:  IDEA_REFINE (Socratic 질문 + interactive_fallback)
Step 7:  PLAN 생성 (3개 산출물 → research_plan.yaml)
Step 8:  PHASE_CODE — AI 코드 생성 (ensure_deps 포함)
Step 9:  PHASE_RUN + PHASE_EVALUATE + PHASE_RECORD
Step 10: PHASE_RUN optimize type — v4 optimizer 재사용
Step 11: Intervention protocol (checkpoint + .intervention.yaml)
Step 12: REFLECT + REFLECT_DONE (iteration 전이)
Step 13: Resume & Fork
Step 14: 프리셋 (ml-experiment, review-paper, novel-method, data-analysis)
Step 15: CLI
Step 16: nanoclaw 연동 테스트
Step 17: 대시보드 (iteration + phase 진행률)
```
