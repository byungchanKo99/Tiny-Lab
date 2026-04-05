# tiny-lab

AI가 자동으로 연구하는 프레임워크. 아이디어만 주면 도메인 조사 → 실험 계획 → 코드 생성 → 실행 → 분석 → 논문 작성까지 알아서 한다.

```
Shape → Gather → [Execute → Reflect → Diversify]↺ → Synthesize → Evaluate
```

## Install

```bash
pip install git+https://github.com/byungchanko/Tiny-Lab.git
```

**필수**: Python 3.10+ / [Claude Code](https://docs.anthropic.com/en/docs/claude-code)

## 30초 가이드

```bash
# 1. 프로젝트 초기화
mkdir my-research && cd my-research
tiny-lab init

# 2. 연구 목표 설정 (Claude Code에서)
# Claude에게 "tiny-lab으로 연구하고 싶다"고 말하면
# Claude가 대화를 통해 constraints.json을 만들어줌

# 3. 실행 (전자동)
tiny-lab run
```

이게 전부다. Claude Code가 CLAUDE.md를 읽고 알아서 해준다.

## Claude Code와 함께 쓰기 (권장)

Claude Code에서 이 레포를 열면 CLAUDE.md가 자동 로드된다. 이후:

```
유저: "시계열 예측 연구하고 싶어"
Claude: (대화를 통해 구체화)
  → "어떤 데이터? 어떤 메트릭? 제약 조건?"
  → constraints.json 생성
  → tiny-lab shape constraints.json
  → tiny-lab run --model sonnet
  → (전자동 실행 모니터링)
  → "iter_1 완료: LSTM MAE=3.4°C, baseline 대비 23% 개선"
```

**유저는 tiny-lab CLI를 몰라도 된다.** Claude가 대신 써준다.

## Full Workflow

```
[유저 아이디어]
    ↓
SHAPE ← 유저와 대화 → constraints.json (목표, 제약조건, 탐색 범위)
    ↓
DOMAIN_RESEARCH → DATA_DEEP_DIVE → IDEA_REFINE → PLAN
    ↓
VALIDATE_PLAN (AI가 계획 검증 — baseline 있나? 논리적인가?)
    ↓
[Phase Loop] PHASE_CODE → PHASE_RUN → PHASE_EVALUATE (전자동 반복)
    ↓
REFLECT → 수렴 감지 시 EXPLORE (새로운 방향 강제 탐색)
    ↓ (반복...)
STORY_TELL (전체 연구 서사로 논문 작성)
    ↓
REVIEW (Professor가 논문 평가 → ACCEPT/REVISE/REJECT)
```

## 핵심 기능

### Constraints (불변 조건)

연구 시작 시 `constraints.json`을 만든다. 이건 **모든 AI 세션에 자동 주입**되어 AI가 목표를 잊거나 제약을 위반하는 걸 방지한다.

### 수렴 감지 + BFS 탐색

같은 방향으로 계속 실험하면 자동 감지. `EXPLORE` state가 발동되어 **의도적으로 다른 방향**을 시도한다. DFS만 하다 막히는 문제를 해결.

### 세션 유지

같은 iteration 내에서 Claude 세션이 유지된다. 이전 단계에서 찾은 내용을 기억하고 다음 단계에 활용.

### 계획 자동 검증

AI가 만든 실험 계획을 다른 AI 세션이 검증. 선행연구 충분? Baseline 있나? Phase 논리적? 부족하면 재생성.

### 논문 + 평가

모든 실험이 끝나면 Story Teller가 전체 서사로 논문 작성. Professor가 5개 기준으로 평가. 부족하면 추가 실험.

## CLI

| Command                      | Description                        |
| ---------------------------- | ---------------------------------- |
| `tiny-lab init [--preset X]` | 프로젝트 초기화                    |
| `tiny-lab shape <file>`      | constraints.json 설정 (SHAPE 스킵) |
| `tiny-lab run [idea]`        | 전자동 실행                        |
| `tiny-lab run --model opus`  | 모델 선택 (sonnet/haiku/opus)      |
| `tiny-lab run --max-iter 20` | 최대 iteration 수                  |
| `tiny-lab status`            | 현재 상태                          |
| `tiny-lab board`             | 결과 대시보드                      |
| `tiny-lab stop`              | 정지                               |
| `tiny-lab resume`            | 재개                               |

## Presets

| Preset          | Use Case                   |
| --------------- | -------------------------- |
| `ml-experiment` | ML 모델 개발 + 실험 (기본) |
| `review-paper`  | 문헌 리뷰                  |
| `novel-method`  | 새로운 방법론 논문         |
| `data-analysis` | 데이터 탐색 + 분석         |
| `custom`        | 커스텀 워크플로우          |

## 파일 구조

```
project/
  research/
    constraints.json             # 핵심 목표 + 제약 (모든 AI에 주입)
    convergence_log.json         # 수렴 감지용 접근법 추적
    .state.json                  # 엔진 상태
    .workflow.json               # 상태 머신 정의 (preset에서 복사)
    iter_1/
      .domain_research.json      # 도메인 SOTA 조사
      .data_analysis.json        # 데이터 분석
      .idea_refined.json         # 구체화된 아이디어
      research_plan.json         # 실험 계획
      .plan_validation.json      # 계획 검증 결과
      phases/*.py                # AI 생성 실험 스크립트
      results/*.json             # 실험 결과 + 시각화
      paper_draft.md             # iteration별 논문 초안
      reflect.json               # 반성 + 다음 방향
    final_paper.md               # Story Teller의 최종 논문
    evaluation.json              # Professor의 평가
  shared/
    knowledge/                   # 축적된 선행연구 (iteration 간 공유)
    data/                        # 데이터셋
    lib/                         # 재사용 코드
```

## Architecture

See [docs/v7-design.md](docs/v7-design.md) for the full design.

## Development

```bash
pip install -e ".[dev]"
pytest tests/
```

## License

MIT
