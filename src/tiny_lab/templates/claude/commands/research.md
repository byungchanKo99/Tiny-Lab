---
allowed-tools: Bash(tiny-lab *), Bash(CYCLE_SLEEP*), Bash(cat research/*), Bash(tail *), Read, Write, Edit, Glob, Grep
---

# /research — Research Loop Control & Discovery

Manage the deterministic research loop for the current project, or start a new research from scratch.

## Usage

The user will invoke this as `/research <subcommand or natural language>`.

Parse `$ARGUMENTS` for the subcommand:

- If `$ARGUMENTS` is `start` → go to **start**
- If `$ARGUMENTS` is `status` or empty → go to **status**
- If `$ARGUMENTS` is `stop` → go to **stop**
- If `$ARGUMENTS` is `generate` → go to **generate**
- If `$ARGUMENTS` is `board` → go to **board**
- **Otherwise** → go to **Discovery Mode** (treat `$ARGUMENTS` as a natural language research intent)

---

### `start`

Determine the right mode based on user intent:

- **Finite comparison** ("compare N models", "test these configs") → `--until-idle`
- **Open-ended optimization** ("optimize", "improve", "find best") → default (infinite)

```bash
# Infinite mode (default)
CYCLE_SLEEP=1 tiny-lab run > research/tiny_lab_run.out 2>&1 &

# Finite mode — stops when queue is empty
CYCLE_SLEEP=1 tiny-lab run --until-idle > research/tiny_lab_run.out 2>&1 &
```

Report the PID and how to stop it (`tiny-lab stop`).

**After starting:**

1. Run `tiny-lab status` to confirm the loop is alive
2. The loop is fully autonomous — it generates new hypotheses, escalates when stuck, and keeps running (infinite mode)
3. In `--until-idle` mode, the loop stops automatically when the queue is exhausted
4. Do NOT run `tiny-lab stop` unless the user explicitly asks — use `--until-idle` for finite tasks
5. When the user returns, run `tiny-lab board` to summarize all results

### `status`

```bash
tiny-lab status          # human-readable
tiny-lab status --json   # structured JSON output
```

### `stop`

```bash
tiny-lab stop
```

### `generate`

```bash
tiny-lab generate
```

### `board`

```bash
tiny-lab board
```

---

## Discovery Mode

The user said something that isn't a known subcommand. Treat `$ARGUMENTS` as a natural language research intent.

**Execute phases strictly in order. Do not skip phases. Do not combine phases.**

Be conversational, not robotic. But follow the state machine below exactly.

### State File (CRITICAL)

A `PreToolUse` hook enforces phase ordering. You MUST update `research/.discovery_state.yaml` at the **end of each phase** before moving to the next. If you don't, the hook will block Write/Edit to research config files and block `tiny-lab run`.

**Update the state file using the Write tool at the end of every phase:**

```yaml
# research/.discovery_state.yaml
phase: SCAN # Current completed phase: SCAN | ANALYZE | ASK_DATA | CONCRETIZE | SETUP | CONFIRM | DONE
scan:
  data_files: []
  script_files: []
  has_project_yaml: false
  is_initialized: false
  user_intent: ""
analyze: # null if skipped
  metric_candidates: []
  lever_candidates: []
concretize: # null until Phase 3
  fields_filled: []
  fields_missing: []
```

The hook checks this file before allowing writes to `research/project.yaml`, `research/questions.yaml`, `research/hypothesis_queue.yaml`, and before allowing `tiny-lab run`. Phase must be `SETUP` to write config files, `CONFIRM` to run the loop.

```
SCAN ──→ data found? ──→ YES ──→ ANALYZE ──→ CONCRETIZE
  │                       NO ──→ ASK_DATA ──→ user provides path ──→ ANALYZE
  │                                           user will add later ──→ (wait, re-SCAN)
  │                                           proceed without data ──→ CONCRETIZE
  │
  ├─ project.yaml exists? ──→ ASK: modify or fresh?
  │
  └─ script found? ──→ read in ANALYZE phase

CONCRETIZE ──→ all 7 fields filled? ──→ YES ──→ SETUP
                                         NO ──→ ask missing → loop

SETUP ──→ baseline works? ──→ YES ──→ CONFIRM
                              NO ──→ fix (max 2 retries) → ask user

CONFIRM ──→ user approves ──→ tiny-lab run
             user wants changes ──→ back to relevant phase
```

---

### Phase 1: SCAN

**Actions (do all of these):**

1. Check if `research/project.yaml` exists
2. Search for script files: `*.py`, `*.sh`, `*.R` (exclude `__pycache__`, `.venv`, `node_modules`)
3. Search for data files: `*.csv`, `*.json`, `*.jsonl`, `*.parquet`, `*.tsv`, `*.xlsx`
4. Check if already initialized: `research/` dir, `.claude/agents/` dir

**After scanning, determine your internal state:**

```
scan_result:
  has_project_yaml: true/false
  is_initialized: true/false
  data_files: [list of paths]
  script_files: [list of paths]
  user_intent: "extracted from user's natural language input"
```

**Before branching — write state file:**

Write `research/.discovery_state.yaml` with `phase: SCAN` and the scan results.

**Branching:**

- If `has_project_yaml` is true → ask user: "기존 프로젝트가 있습니다. 수정할까요, 새로 시작할까요?" Wait for answer before continuing.
- If `data_files` is non-empty → go to **Phase 2: ANALYZE**
- If `data_files` is empty → go to **Phase 2-ALT: ASK_DATA**

---

### Phase 2: ANALYZE

**Entry condition:** At least 1 data file found (from SCAN or from user-provided path)

**Actions (in this order):**

1. **Check file size** — run `wc -l` or `ls -lh` on each data file. If >10,000 rows, only read first 50 rows.
2. **Read sample** — use Read tool. CSV: header + first 20 rows. JSON/JSONL: first 5 objects.
3. **Extract schema** — for each column: name, inferred type (numeric/categorical/text/date), example values.
4. **Identify metric candidates** — numeric columns that look like optimization targets. For each: compute or estimate mean, min, max.
5. **Identify lever candidates** — columns/parameters that could be varied:
   - Categorical with ≤20 unique values → list all unique values
   - Numeric with clear range → note the range
6. **Check for issues** — missing values (%), obvious outliers, columns that need preprocessing.

**If script files were also found, analyze them too:**

- Read each script and look for `argparse`, `click`, `typer`, or CLI flag patterns
- Extract flag names, default values, help text
- Check if the script references any of the data files

**Required output to user (show ALL of this):**

```
I analyzed your environment:

📊 Data: {filename} ({rows} rows, {cols} columns)
  - Metric candidates: {col1} (mean: X, range: Y-Z), {col2} (mean: X, range: Y-Z)
  - Lever candidates: {col3} ({n} categories: [val1, val2, ...]), {col4} (numeric, range: X-Y)
  - Issues: {missing values, etc. or "none"}

📝 Script: {filename}
  - CLI flags: {--flag1 (default: X), --flag2 (default: Y), ...}
  - References data: {yes/no, which file}

Which metric do you want to optimize? Are these the right levers?
```

**Before presenting to user — update state file:** Set `phase: ANALYZE` with metric/lever candidates.

**After user responds** → go to **Phase 3: CONCRETIZE**

---

### Phase 2-ALT: ASK_DATA

**Entry condition:** No data files found in SCAN

**Required output to user (say exactly this):**

```
이 디렉토리에서 데이터 파일을 찾지 못했습니다.

1. 데이터가 다른 경로에 있다 → 경로를 알려주세요
2. 데이터를 아직 준비 안 했다 → 이 디렉토리에 넣어주면 분석해드릴게요
3. 데이터 없이 진행하고 싶다 → 스크립트/명령어 기반으로 세팅할게요
```

**Update state file:** Set `phase: ASK_DATA`.

**Branching (based on user response):**

- User provides a path → read data from that path → go to **Phase 2: ANALYZE**
- User says they'll add data → tell them to let you know when ready. When they respond, re-run **Phase 1: SCAN**
- User wants to proceed without data → go to **Phase 3: CONCRETIZE** (skip data analysis, rely on user input and script analysis only)

---

### Phase 3: CONCRETIZE

**Entry condition:** Phase 2 or 2-ALT complete

**Required fields checklist:**

| #   | Field                                           | How to fill                                                                                                                         |
| --- | ----------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `name` (experiment name)                        | Infer from user intent. Propose, let user confirm.                                                                                  |
| 2   | `description`                                   | Generate from intent. One sentence.                                                                                                 |
| 3   | `metric.name` + `metric.direction`              | From ANALYZE metric candidates + user choice. Direction: "accuracy"/"score"/"revenue" → maximize, "loss"/"error"/"cost" → minimize. |
| 4   | `baseline.command`                              | From script analysis (flags + defaults). If no script → ask user.                                                                   |
| 5   | `levers` (name, flag, baseline, space for each) | From ANALYZE lever candidates + script flags. Propose search spaces from data ranges.                                               |
| 6   | `run.type`                                      | Default: `command`. Only ask if user mentioned pipeline.                                                                            |
| 7   | `evaluate.type`                                 | Default: `stdout_json`. Only ask if output isn't JSON (e.g., screenshots → `llm`).                                                  |

**Actions:**

1. Check which fields are already filled from Phase 2 results + user responses
2. For unfilled fields: **ask all missing fields in a single grouped question**. Do NOT ask one at a time.
3. Fields 6 and 7 have safe defaults — do NOT ask about them unless the user's situation clearly needs a non-default value.
4. If no baseline script exists and user has data, offer: "baseline 스크립트를 만들어 드릴까요?"

**Inference rules for auto-filling:**

- Script with argparse flags → `build.type: flag`, extract levers from flags
- Script without flags but user wants code changes → `build.type: code`
- User mentions "accuracy" or "score" → `metric.direction: maximize`
- User mentions "loss" or "error" or "cost" → `metric.direction: minimize`
- ANALYZE found categorical column with ≤10 values → `space: [all unique values]`
- ANALYZE found numeric parameter → propose 4-5 values around the baseline (e.g., baseline=0.5 → space: [0.3, 0.5, 0.7, 1.0])

**Exit condition:** All 7 fields filled → **update state file** with `phase: CONCRETIZE` and filled fields → go to **Phase 4: SETUP**

---

### Phase 4: SETUP

**Entry condition:** All 7 fields confirmed, state file shows `phase: CONCRETIZE`

**First action:** Update state file to `phase: SETUP`. This unlocks Write/Edit to research config files.

**Actions (execute in this exact order):**

1. **Initialize** — run `tiny-lab init` if `is_initialized` is false. Skip if already initialized.

2. **Write `research/project.yaml`** — use the confirmed field values:

   ```yaml
   name: { name }
   description: "{description}"

   build:
     type: { flag|script|code }

   run:
     type: { command|pipeline }

   evaluate:
     type: { stdout_json|script|llm }

   baseline:
     command: "{baseline_command}"

   metric:
     name: { metric_name }
     direction: { maximize|minimize }

   levers:
     { lever_name }:
       flag: "{flag}"
       baseline: { baseline_value }
       space: [{ values }]

   rules:
     - "Change command-line flags only"
     - "Do not install packages"
   ```

3. **Write `research/questions.yaml`** — generate 2-3 research questions from levers:

   ```yaml
   - id: Q0.1
     question: "Does the baseline command produce valid metric output?"
     depends_on: []
     resolved_by: []
   - id: Q1.1
     question: "{question about first lever}"
     depends_on: [Q0.1]
     resolved_by: []
   ```

4. **Write `research/hypothesis_queue.yaml`** — generate 3-5 hypotheses.

   **If `optimize:` is configured in project.yaml → use v2 format:**

   Parameter types are already defined in `project.yaml` `search_space:`. Hypotheses only pick the approach — do NOT repeat search_space per hypothesis.

   ```yaml
   hypotheses:
     - id: H-001
       status: pending
       approach: logistic_regression
       description: "Logistic Regression baseline for interpretability"
       reasoning: "Start with a simple linear model before trying complex approaches"
     - id: H-002
       status: pending
       approach: random_forest
       description: "Random Forest with tree depth search"
       reasoning: "Nonlinear model to capture feature interactions"
   ```

   v2 key principle: YOU pick the **strategy** (approach), the **optimizer** picks the **parameters** from `project.yaml` `search_space:`. Same approach + different ranges is NOT a new hypothesis.

   **Otherwise → use v1 format:**

   ```yaml
   hypotheses:
     - id: H-001
       status: pending
       lever: { lever_name }
       value: { value_from_space }
       description: "{one line description}"
   ```

5. **Verify baseline** — run the baseline command and check output:
   - Parse stdout for JSON containing `metric.name`
   - **If success** (metric found in output) → record baseline value, go to **Phase 5: CONFIRM**
   - **If failure** (error or no metric in output):
     - Show the error to the user
     - Attempt to fix (max 2 retries: adjust command, fix script, etc.)
     - If still failing after 2 retries → ask user for help: "baseline 명령어가 동작하지 않습니다. 직접 확인해주시겠어요?"

---

### Phase 5: CONFIRM

**Entry condition:** Phase 4 complete, baseline verified

**First action:** Update state file to `phase: CONFIRM`. This unlocks `tiny-lab run`.

**Required output (show ALL of this):**

```
Setup complete:
- Project: {name}
- Metric: {metric_name} ({direction})
- Levers: {lever1} ({n} values), {lever2} ({n} values), ...
- Data: {data_path} ({rows} rows)  — or "none"
- Initial hypotheses: {n}
- Baseline verified: {metric_name} = {baseline_value} ✓

Start the research loop? (tiny-lab run)
```

**Branching:**

- User approves → update state file to `phase: DONE` → run `CYCLE_SLEEP=1 tiny-lab run > research/tiny_lab_run.out 2>&1 &`, report PID, then enter monitoring mode (see `start` section)
- User wants changes → update state file back to the relevant phase → revisit that phase
