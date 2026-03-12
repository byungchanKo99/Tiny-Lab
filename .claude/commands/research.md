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

Start the research loop:

```bash
tiny-lab run
```

Report the PID and how to stop it.

### `status`

```bash
tiny-lab status
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

The user said something that isn't a known subcommand. This means they want to **start or set up a new research**. Their input is a natural language description of what they want to research/optimize/experiment with.

Follow these phases **in order**. Be conversational, not robotic. Skip questions when the answer is obvious from context.

### Phase 1: Understand Intent

Read the user's input and extract:

- What they want to optimize or study
- Any mentioned scripts, files, or data
- Any mentioned metrics or success criteria

Check if `research/project.yaml` already exists:

- If yes: ask if they want to modify the existing project or start fresh
- If no: proceed to Phase 2

Also scan the current directory for clues:

- Look for Python scripts, config files, data directories
- Check if `tiny-lab` is already initialized (`.claude/agents/`, `research/` dirs)

### Phase 2: Concretize (Ask Questions)

You need to fill in these fields for `research/project.yaml`. Ask about anything you can't confidently infer. **Group related questions together** — don't ask one at a time.

**Must determine:**

1. **Experiment name** — a short identifier (e.g., `hotel-pricing-revpar`)
2. **Description** — one sentence about the goal
3. **Metric** — what number to optimize (name, minimize or maximize)
4. **Baseline command** — the command that runs the experiment with default settings. Must produce the metric as JSON in stdout like `{"metric_name": 1.23}`
5. **Levers** — which variables to experiment with. For each lever:
   - Name (e.g., `learning_rate`)
   - How it's controlled: CLI flag (e.g., `--lr`) or code modification
   - Current default value (baseline)
   - Values to try (search space)
6. **Run method** — `command` (direct shell), `surface` (via surface tool), or `pipeline` (multi-step)
7. **Evaluation method** — `stdout_json` (parse stdout), `script` (separate eval script), or `llm` (AI scoring)

**Can often infer:**

- If the user mentions a Python script with `argparse` → read it to find CLI flags → suggest `build.type: flag` and extract levers automatically
- If they mention a metric name → set `metric.name` and guess `direction`
- If they say "accuracy" or "score" → `direction: maximize`
- If they say "loss" or "error" or "cost" → `direction: minimize`

**Smart behavior:**

- If you see a script file, **read it** to discover CLI arguments and suggest levers
- If there's a data file, confirm its location and whether it needs preprocessing
- Propose reasonable search spaces based on the baseline values (e.g., if baseline LR is 0.01, suggest [0.005, 0.01, 0.02, 0.05])

### Phase 3: Set Up Environment

Once you have all the information, do these steps:

1. **Initialize** if needed:

   ```bash
   tiny-lab init
   ```

   (Skip if already initialized — check for `research/` directory)

2. **Write `research/project.yaml`** with the concretized configuration. Use the Edit or Write tool. Example:

   ```yaml
   name: hotel-pricing-revpar
   description: "Optimize hotel RevPAR by adjusting pricing parameters"

   build:
     type: flag

   run:
     type: command

   evaluate:
     type: stdout_json

   baseline:
     command: "python3 pricing_model.py --data data/bookings.csv --rate-adj 1.0 --season-weight 0.5"

   metric:
     name: revpar
     source: stdout_json
     direction: maximize

   levers:
     rate_adjustment:
       flag: "--rate-adj"
       baseline: 1.0
       space: [0.8, 0.9, 1.0, 1.1, 1.2]
     season_weight:
       flag: "--season-weight"
       baseline: 0.5
       space: [0.3, 0.5, 0.7, 1.0]

   rules:
     - "Change command-line flags only"
     - "Do not install packages"
   ```

3. **Verify baseline runs** — execute the baseline command once to confirm it works and produces the expected metric:

   ```bash
   # Run the baseline command and check output
   ```

   If it fails, help the user fix it before proceeding.

4. **Write `research/questions.yaml`** — create 2-3 research questions based on the levers:

   ```yaml
   - id: Q0.1
     question: "Does the baseline command produce valid metric output?"
     depends_on: []
     resolved_by: []
   - id: Q1.1
     question: "Does increasing rate_adjustment above 1.0 improve RevPAR?"
     depends_on: [Q0.1]
     resolved_by: []
   ```

5. **Write `research/hypothesis_queue.yaml`** — generate 3-5 initial hypotheses from the levers:

   ```yaml
   hypotheses:
     - id: H-001
       status: pending
       lever: rate_adjustment
       value: 1.1
       description: "Increase rate adjustment from 1.0 to 1.1"
     - id: H-002
       status: pending
       lever: season_weight
       value: 0.7
       description: "Increase season weight from 0.5 to 0.7"
   ```

6. **Handle data** — if the user mentioned a dataset:
   - Confirm the file exists at the specified path
   - If it's elsewhere, suggest moving/linking it
   - If preprocessing is needed, help set it up

### Phase 4: Confirm & Launch

Show a summary of what was set up:

```
Setup complete:
- Project: hotel-pricing-revpar
- Metric: revpar (maximize)
- Levers: rate_adjustment (5 values), season_weight (4 values)
- Initial hypotheses: 3
- Baseline verified: ✓

Start the research loop? (tiny-lab run)
```

If the user agrees, run `tiny-lab run`.
If they want changes, go back and adjust.
