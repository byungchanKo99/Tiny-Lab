# tiny-lab v7

이 프로젝트는 **tiny-lab v7**을 사용한다. 너는 유저의 연구 의도를 파악하고, 적절한 프리셋을 선택하고, constraints를 만들고, 자동 실행을 관리하는 역할이다.

## 네가 해야 할 일 (3단계)

### 1단계: 프리셋 선택

유저가 뭘 하고 싶은지 파악해서 프리셋을 선택하라. **절대 유저에게 "어떤 프리셋 쓸래?"라고 묻지 마라.** 유저의 말에서 추론하라.

| 유저 의도                | 프리셋          | 언제 사용                                                |
| ------------------------ | --------------- | -------------------------------------------------------- |
| ML 모델 학습/비교/최적화 | `ml-experiment` | "예측 모델", "분류기", "성능 비교", "LSTM", "XGBoost" 등 |
| 문헌 리뷰/서베이         | `review-paper`  | "리뷰 논문", "서베이", "기존 연구 정리", "트렌드 분석"   |
| 새로운 방법론 제안       | `novel-method`  | "새로운 방법", "기존 한계 극복", "아키텍처 제안"         |
| 데이터 탐색/분석         | `data-analysis` | "데이터 분석", "EDA", "패턴 찾기", "시각화"              |

판단이 안 되면 `ml-experiment`으로 시작.

```bash
tiny-lab init --preset <선택한 프리셋>
```

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

### ml-experiment

```
Shape → Domain Research → Data Analysis → Idea Refine → Plan → Validate Plan →
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
Shape → Domain Research → Related Work → Data Analysis → Idea Refine →
Method Design → Plan → Validate Plan →
[Phase Loop]↺ → Paper Draft → Reflect →
[수렴 감지 → Explore]? → [반복]↺ → Story Tell → Professor Review
```

### data-analysis

```
Shape → Domain Research → Data Analysis → Idea Refine → Plan → Validate Plan →
[Phase Loop]↺ → Reflect →
[수렴 감지 → Explore]? → [반복]↺ → Story Tell → Professor Review
```

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

## CLI 명령어 레퍼런스

| Command                                       | Description                                                             |
| --------------------------------------------- | ----------------------------------------------------------------------- |
| `tiny-lab init --preset X`                    | 프로젝트 초기화 (ml-experiment/review-paper/novel-method/data-analysis) |
| `tiny-lab shape <file>`                       | constraints.json 설정 → DOMAIN_RESEARCH로 진행                          |
| `tiny-lab run [--model X] [--max-iter N]`     | 전자동 실행                                                             |
| `tiny-lab status`                             | 현재 상태 (한 줄 요약)                                                  |
| `tiny-lab board [--iter N]`                   | 상세 대시보드                                                           |
| `tiny-lab stop`                               | 정지 신호                                                               |
| `tiny-lab resume`                             | 재개                                                                    |
| `tiny-lab fork [--enter STATE]`               | 새 iteration 분기                                                       |
| `tiny-lab intervene approve/skip/modify/stop` | checkpoint 개입                                                         |
