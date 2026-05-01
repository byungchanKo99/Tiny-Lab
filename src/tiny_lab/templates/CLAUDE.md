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
```

실행 후에는 주기적으로 진행 상황을 확인하고 유저에게 보고하라:

```bash
tiny-lab status                 # 간단 상태
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

## 실행 모드 (v7.8+)

`tiny-lab`은 두 가지 실행 모드가 있다 — **양립**한다 (같은 `.state.json`을 공유, 자유롭게 전환).

### 1) CLI 엔진 모드 (배치/자동화)

```bash
tiny-lab run                   # claude (기본)
tiny-lab run --engine codex    # codex로 전체 실행
tiny-lab run --engine claude --model opus
```

엔진이 state machine을 돌리며 각 state마다 fresh subprocess를 띄운다. 컨텍스트 격리, 가장 견고. 백그라운드 자동화에 적합.

### 2) 네이티브 모드 (인터랙티브)

**Claude Code**: 채팅창에서 `/tiny-lab` 또는 "tiny-lab으로 진행해줘" 같은 트리거. `.claude/skills/tiny-lab/SKILL.md`가 자동 로드되어 메인 세션이 직접 state machine을 진행.

**Codex CLI**: 프로젝트 루트의 `AGENTS.md`가 자동 로드되어 동일한 오케스트레이션 로직을 codex 세션에서 수행. `.codex/hooks.json`이 hook을 등록 (활성화 위해 codex config에 `[features] codex_hooks = true` 필요).

- ✅ 메인 세션이 직접 단계 진행 — subprocess 없음
- ✅ 동일한 hook이 양쪽 모두 강제 (`hook_io.py` 듀얼모드 — Claude는 env vars, Codex는 stdin JSON 자동 감지)
- ✅ 사용자가 단계마다 검토 가능
- ❌ 컨텍스트가 한 세션에 누적

전환은 자유: CLI에서 멈추고 채팅에서 이어가거나, 채팅에서 단계 진행하다 `tiny-lab run`으로 자동화 위임. 같은 `.state.json` 공유.

### 백엔드별 강점 (engine override)

preset의 state별로 `"engine": "codex"`를 지정하면 그 단계만 다른 백엔드로 돌릴 수 있다. 권장 매핑:

| 단계            | 추천 엔진 | 이유                          |
| --------------- | --------- | ----------------------------- |
| PHASE_CODE      | codex     | 코드 생성 정확도 ↑            |
| EVALUATE_MATRIX | claude    | 다축 reasoning, novelty 판단  |
| DOMAIN_RESEARCH | claude    | WebSearch 통합도 ↑            |
| 나머지          | (default) | `--engine` 플래그로 일괄 지정 |

Codex 호출 명령은 기본 `codex exec --json`. 다른 시그니처면 `TINYLAB_CODEX_CMD` 환경변수로 오버라이드.

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
| `tiny-lab run [--model X] [--engine claude\|codex] [--max-iter N]` | 전자동 실행 (engine 선택 가능)                                                 |
| `tiny-lab status`                                                  | 현재 상태 (한 줄 요약)                                                         |
| `tiny-lab board [--iter N]`                                        | 상세 대시보드                                                                  |
| `tiny-lab stop`                                                    | 정지 신호                                                                      |
| `tiny-lab resume`                                                  | 재개                                                                           |
| `tiny-lab fork [--enter STATE]`                                    | 새 iteration 분기                                                              |
| `tiny-lab intervene approve/skip/modify/stop`                      | checkpoint 개입                                                                |
| `tiny-lab report "title" [--label bug]`                            | GitHub 이슈 자동 생성 (상태+로그 첨부)                                         |
| `tiny-lab verify-refs [--iter N] [--strict]`                       | 인용된 논문이 실재하는지 검증 (arXiv/Crossref/Semantic Scholar)                |
| `tiny-lab novelty [--iter N] [--years Y] [--write]`                | ideate 후보 가설들의 novelty를 Semantic Scholar로 추정 (최근 N년 매칭 논문 수) |

## 레퍼런스 환각 방지

`DOMAIN_RESEARCH`, `DIVERGE` 등 외부 자료를 인용하는 단계는 자동으로 PostToolUse 훅(`ref_verify.py`)이 돌아 인용된 논문이 실재하는지 확인한다. 결과는 원본 옆에 `<artifact>.ref_verification.json` 사이드카로 저장된다.

- `verified` — arXiv/Crossref/Semantic Scholar 중 하나로 확인됨
- `not_found` — 어느 API에서도 찾지 못함 (환각 가능성)
- `unverified` — 검증 시도가 부족 (예: 식별자 없음)
- `error` — API 호출 실패

수동 재검증 또는 CI/사전 게이트:

```bash
tiny-lab verify-refs                  # 모든 iteration 검증
tiny-lab verify-refs --iter 2         # 특정 iteration만
tiny-lab verify-refs --strict         # not_found 있으면 exit 1
```

`EVALUATE_MATRIX` 단계는 `ref_verification.json`을 읽어 `not_found` 인용에 점수 페널티를 자동 적용한다.
