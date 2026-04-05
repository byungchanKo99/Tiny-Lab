# tiny-lab v7 Research Project

This project uses **tiny-lab v7** — a domain-agnostic adaptive loop that automates: shape → gather → execute → synthesize → evaluate.

## IMPORTANT: How to Use (2-step process)

### Step 1: Shape (유저와 대화 필요)

연구를 시작하기 전에 반드시 **constraints.json**을 먼저 만들어야 한다. 유저와 대화해서 다음을 확정한다:

1. **objective** — 이 연구의 핵심 질문/목표
2. **goal** — 성공 기준 (metric, target, success_criteria)
3. **invariants** — 절대 위반하면 안 되는 조건
4. **exploration_bounds** — 허용/금지 범위

유저의 입력이 애매하면 질문하라. 너무 구체적이면 핵심만 추출하라.

```bash
# constraints.json을 작성한 후:
tiny-lab shape /path/to/constraints.json

# 또는 stdin으로:
echo '{"objective": "...", ...}' | tiny-lab shape -
```

### Step 2: Run (Full Auto)

Shape이 완료되면 나머지는 자동으로 돌아간다:

```bash
tiny-lab run                          # sonnet (기본), preset의 max_iter
tiny-lab run --model opus             # opus 모델
tiny-lab run --model haiku            # haiku (빠르고 저렴)
tiny-lab run --max-iter 20            # max iteration 오버라이드
```

## Full Workflow

```
[유저 입력]
    ↓
SHAPE_FULL ← tiny-lab shape (유저와 대화 후 constraints.json 작성)
    ↓
DOMAIN_RESEARCH → DATA_DEEP_DIVE → IDEA_REFINE → PLAN
    ↓
VALIDATE_PLAN (AI가 plan 검증 — 선행연구, baseline, 논리성 체크)
    ├─ REJECT → PLAN 재생성
    └─ APPROVE ↓
    ↓
[Phase Loop]
  PHASE_SELECT → PHASE_CODE → PHASE_RUN → PHASE_EVALUATE → PHASE_RECORD → CHECKPOINT
  (모든 phase 완료까지 반복)
    ↓
PAPER_DRAFT → REFLECT → SHAPE_SEED
    ├─ 수렴 감지 → EXPLORE (BFS — 새로운 방향 탐색)
    └─ 정상 → ROUTE
        ├─ done → STORY_TELL (최종 논문)
        ├─ idea_mutation → IDEA_REFINE (새 iteration)
        ├─ add_phases → PLAN
        └─ domain_pivot → DOMAIN_RESEARCH
    ↓
STORY_TELL → REVIEW (Professor가 논문 평가)
    ├─ ACCEPT → DONE
    ├─ REVISE → 추가 실험 (새 iteration)
    └─ REJECT → SHAPE_FULL (재시작)
```

## Key Features (v7)

### Constraints 자동 주입

`constraints.json`이 있으면 **모든 AI 세션**에 자동 삽입된다. AI가 constraints를 위반하는 계획이나 코드를 만들 수 없다.

### 수렴 감지 + BFS 탐색

`convergence_log.json`에 매 iteration의 접근법을 기록한다. 최근 iteration들이 너무 비슷하면 EXPLORE state가 발동되어 의도적으로 다른 방향을 시도한다.

### 세션 유지

같은 iteration 내에서 Claude 세션이 유지된다. DOMAIN_RESEARCH에서 찾은 내용을 IDEA_REFINE이 기억하고, PLAN에서 참조한다.

### 지식 축적

`shared/knowledge/`에 선행연구와 발견을 저장한다. 새 iteration에서도 이전에 조사한 내용을 재활용한다.

## Commands

| Command                                       | Description                             |
| --------------------------------------------- | --------------------------------------- |
| `tiny-lab init [--preset X]`                  | 프로젝트 초기화                         |
| `tiny-lab shape <file>`                       | constraints.json 작성 + SHAPE_FULL 스킵 |
| `tiny-lab run [idea]`                         | Full auto 실행                          |
| `tiny-lab run --model opus`                   | 모델 선택 (sonnet/haiku/opus)           |
| `tiny-lab run --max-iter N`                   | max iteration 오버라이드                |
| `tiny-lab status`                             | 현재 상태 확인                          |
| `tiny-lab board [--iter N]`                   | 결과 대시보드                           |
| `tiny-lab stop`                               | 정지 신호                               |
| `tiny-lab resume`                             | 마지막 상태에서 재개                    |
| `tiny-lab fork`                               | 새 iteration 분기                       |
| `tiny-lab intervene approve/skip/modify/stop` | checkpoint 개입                         |

## Key Files

| File                                    | Purpose                                     |
| --------------------------------------- | ------------------------------------------- |
| `research/constraints.json`             | 핵심 목표 + 불변 조건 (모든 AI 세션에 주입) |
| `research/convergence_log.json`         | iteration별 접근법 추적 (수렴 감지용)       |
| `research/.state.json`                  | 현재 엔진 상태                              |
| `research/.workflow.json`               | 상태 머신 정의                              |
| `research/iter_N/research_plan.json`    | 실험 계획                                   |
| `research/iter_N/.plan_validation.json` | 계획 검증 결과                              |
| `research/iter_N/phases/*.py`           | AI 생성 실험 스크립트                       |
| `research/iter_N/results/*.json`        | phase 결과 + 시각화                         |
| `research/iter_N/reflect.json`          | iteration 반성 + 다음 방향                  |
| `research/final_paper.md`               | Story Teller가 작성한 최종 논문             |
| `research/evaluation.json`              | Professor의 논문 평가                       |
| `shared/knowledge/`                     | 축적된 선행연구 + 발견                      |

## constraints.json Schema

```json
{
  "objective": "핵심 질문/목표",
  "goal": {
    "metric": "MAE | accuracy | null",
    "direction": "minimize | maximize | null",
    "target": null,
    "unit": "단위",
    "success_criteria": "구체적 성공 조건"
  },
  "invariants": ["절대 위반 불가 조건"],
  "exploration_bounds": {
    "allowed": ["탐색 가능 범위"],
    "forbidden": ["금지 영역"]
  }
}
```
