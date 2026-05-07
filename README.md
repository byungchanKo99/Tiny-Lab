# tiny-lab

AI가 자동으로 연구하는 프레임워크. 아이디어만 주면 도메인 조사 → 실험 계획 → 코드 생성 → 실행 → 분석 → 논문 작성까지 알아서 한다.

```
Shape → Gather → [Execute → Reflect → Diversify]↺ → Synthesize → Evaluate
```

## Install

```bash
pip install git+https://github.com/byungchanKo99/Tiny-Lab.git
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

### ML 연구자 품질 기준

모든 AI 세션에 공통 연구 품질 기준이 자동 주입된다. 정량 claim은 같은 문장에서 `research/iter_*/results/*.json` artifact로 추적 가능해야 하고, citation은 ref verification sidecar로 확인되어야 한다. data leakage 점검, non-ML/simple ML baseline, baseline comparison evidence, ablation/error analysis, 반복 실험 통계, seed, dataset fingerprint/source, split id, environment metadata, code provenance도 기본 요구사항이다. 실험 계획이 이 기준을 구조적으로 빠뜨리거나 planned phase가 `done`까지 완료되지 않으면 엔진이 거절한다.

### 논문 + 평가

모든 실험이 끝나면 Story Teller가 전체 서사로 논문 작성. Professor가 5개 기준으로 평가. 부족하면 추가 실험. 최종 논문이 없거나 기본 논문 구조가 부족한데 `ACCEPT`를 받으면 엔진이 이를 차단한다. raw results에 없는 metric 숫자를 주장하거나, 평가 점수 합계와 `ACCEPT`/`REVISE`/`REJECT` 판정이 모순되는 경우도 통과하지 않는다.

## CLI

| Command                      | Description                        |
| ---------------------------- | ---------------------------------- |
| `tiny-lab init [--preset X]` | 프로젝트 초기화                    |
| `tiny-lab shape <file>`      | constraints.json 설정 (SHAPE 스킵) |
| `tiny-lab run [idea]`        | 전자동 실행                        |
| `tiny-lab run --model opus`  | 모델 선택 (sonnet/haiku/opus)      |
| `tiny-lab run --max-iter 20` | 최대 iteration 수                  |
| `tiny-lab run --max-steps 1` | 제한된 상태 수만 실행하는 smoke test |
| `tiny-lab run --timeout-seconds 300` | AI state별 backend timeout override |
| `tiny-lab status`            | 현재 상태                          |
| `tiny-lab doctor [--probe-backend] [--repair-runner]` | 프로젝트/backend 실행 준비 점검 및 native runner 복구 |
| `tiny-lab brief`             | 현재 state의 실행 계약 요약        |
| `tiny-lab prompt`            | 현재 AI state 프롬프트 렌더링      |
| `tiny-lab step`              | 엔진 핸들러로 한 state 진행        |
| `tiny-lab board`             | 결과 대시보드                      |
| `tiny-lab audit [--strict] [--all]` | 연구 품질 게이트 수동 점검         |
| `tiny-lab stop`              | 정지                               |
| `tiny-lab resume`            | 재개                               |

## Presets

| Preset          | Use Case                                                                                    |
| --------------- | ------------------------------------------------------------------------------------------- |
| `ideate`        | 주제·가설 탐색 (후보 발산 → novelty/feasibility 평가 → 1개 선정 → 다음 프리셋으로 핸드오프) |
| `ideate-deep`   | 위 + 문헌 스캔 + 갭 분석 (신중한 주제 선정용)                                               |
| `ml-experiment` | ML 모델 개발 + 실험 (기본)                                                                  |
| `review-paper`  | 문헌 리뷰                                                                                   |
| `novel-method`  | 새로운 방법론 논문                                                                          |
| `data-analysis` | 데이터 탐색 + 분석                                                                          |
| `custom`        | 커스텀 워크플로우                                                                           |

**가설부터 잡고 싶을 때**: `tiny-lab init --preset ideate` → 후보 가설들을 평가하고 한 개를 선정한 뒤, 출력된 `research/.handoff.md`를 따라 본 연구 프리셋으로 이어가라. 주제→논문 한 번에 가는 것보다 연구 퀄리티가 올라간다.

## 레퍼런스 검증

외부 논문을 인용하는 단계(`DOMAIN_RESEARCH`, `DIVERGE` 등)는 자동으로 인용 검증 훅이 돌아 환각된 인용을 잡아낸다. 수동 재검증은 `tiny-lab verify-refs` (옵션: `--iter N`, `--strict`).

## 실행 모드 (v7.8+)

두 가지 양립 가능한 모드:

```bash
# CLI 엔진 모드 — 자동화/배치
tiny-lab run                       # claude 기본
tiny-lab run --engine codex        # codex 백엔드
tiny-lab run --engine claude --model opus
tiny-lab run --max-steps 1         # 한 state만 실행하고 pause
tiny-lab run --timeout-seconds 300 # AI state별 backend timeout override

# 네이티브 모드 — Claude Code OR Codex CLI 채팅에서 인터랙티브
#   Claude: .claude/skills/tiny-lab/SKILL.md 자동 로드
#   Codex:  AGENTS.md 자동 로드 + .codex/hooks.json 등록
# 메인 세션이 직접 state machine 진행 (subprocess 없음)
# Hook은 듀얼모드 — Claude env vars / Codex stdin JSON 자동 감지
```

같은 `.state.json`을 공유 — 자유롭게 전환 가능. preset의 state별 `"engine": "codex"` 필드로 단계마다 다른 백엔드 사용도 가능.

## 의무 시각화 (v7.6+)

데이터 이해 단계와 가설 선정 단계는 시각화를 의무로 만든다 — 텍스트 JSON만으로는 놓치기 쉬운 패턴/트레이드오프를 PNG로 강제 노출.

- `VISUALIZE_DATA` (ml-experiment, novel-method, data-analysis): 분포 grid, correlation heatmap, missing matrix, target relationship, time-series profile — 데이터 타입 부적합 시 자동 skip → `research/{iter}/data_viz/`
- `VISUALIZE_CANDIDATES` (ideate, ideate-deep): score radar, Pareto scatter, weighted total bar + (deep만) gap landscape → `research/{iter}/ideate_viz/`
- `PHASE_CODE/RUN`: phase별 최소 1개 PNG → `research/{iter}/results/`

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
