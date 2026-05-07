# Codex Backend Run Issues

Captured: 2026-05-05 00:55 KST
Updated: 2026-05-05 04:31 KST

## Context

Real project path:

`/Users/byungchanko/Downloads/scm_research`

Command intent:

Run `tiny-lab` with the Codex backend on an SCM forecasting project that has local Excel data and prior-research images/notes.

Core command:

```bash
tiny-lab run --engine codex --max-iter 3 --timeout-seconds 900
```

The project had been initialized with:

```bash
tiny-lab init --preset ml-experiment
```

## Fix Pass Status

Implemented after this run:

- Codex now defaults to `codex exec --json --skip-git-repo-check`, so normal initialized projects outside git repos no longer fail the default Codex path.
- Codex and Claude prompts are sent through stdin instead of argv in backend invocations; the interactive Claude path was moved to stdin as well.
- Tiny-Lab records the active backend child in `research/.active_backend.json` with redacted argv, and `tiny-lab status`, `tiny-lab ps`, and `tiny-lab stop` expose or interrupt that child.
- Codex declares `supports_resume = False`, so logs no longer imply true Codex session resume.
- Known backend-unavailable failures, including Codex trusted-directory, skip-git, auth, quota, usage-limit, rate-limit, timeout, and missing-command failures, stop the loop without consuming research retry counters.
- `tiny-lab repair-state --to <STATE> [--phase <PHASE>] --clear-failures --clear-session` records an auditable state repair event instead of requiring direct `.state.json` edits.

Still open or only partially mitigated:

- Backend stdout/event streaming, artifact polling while a backend process is still running, and soft-timeout fallback are not implemented yet.
- Manual artifact provenance and a first-class `repair-artifact` command remain follow-up work.
- `tiny-lab stop` now signals the recorded backend child, but full state-aware SIGINT handling that advances completed artifacts and then pauses before the next backend is still open.

## Observed Issues

### 1. Codex CLI rejects non-git / untrusted project directories

The first Codex run failed immediately with:

```text
Not inside a trusted directory and --skip-git-repo-check was not specified.
```

The backend already documents the workaround:

```bash
TINYLAB_CODEX_CMD="codex exec --json --skip-git-repo-check"
```

But `tiny-lab run --engine codex` does not apply this automatically, so a normal initialized project outside a git repo can fail before producing any artifact.

Candidate improvements:

- Add `--skip-git-repo-check` to the default Codex backend command when running inside a tiny-lab project.
- Or detect this specific stderr and retry once with `--skip-git-repo-check`.
- Or have `tiny-lab doctor --engine codex` warn that the project is not trusted and show the exact fix.

### 2. A backend configuration error exhausts state retries too quickly

The trusted-directory failure repeated through all `SHAPE_FULL` retries and left state as `DONE` with `consecutive_failures=6`.

Impact:

- A configuration/runtime issue looked like a research-state failure.
- The user had to manually reset `.state.json` to retry after fixing the backend command.

Candidate improvements:

- Classify Codex trusted-directory errors as `BackendUnavailableError`.
- Do not consume state retries for backend configuration failures.
- Stop in the current state with a clear repair message instead of transitioning to `DONE`.

### 3. Codex writes the completion artifact before the engine can advance

During `SHAPE_FULL`, Codex wrote:

- `research/.shaped_input.json`
- `research/constraints.json`

The parent `tiny-lab run` process did not advance until the Codex subprocess fully exited. This makes progress look stalled even when the completion artifact already exists.

Candidate improvements:

- Poll for the completion artifact while the backend process is running.
- If the artifact validates, allow a graceful backend cancellation and advance.
- Or stream Codex JSON events into the Tiny-Lab log so artifact-producing tool calls are visible in real time.

### 4. Interrupting a hung parent can race with the next state

After `SHAPE_FULL` eventually exited successfully, the engine advanced to `DOMAIN_RESEARCH` and immediately launched the next Codex session. Interrupting the parent at that moment caused a `KeyboardInterrupt` inside the next backend invocation.

Candidate improvements:

- On SIGINT, finish any just-completed artifact advancement before starting the next AI session.
- Add a `--max-steps 1` recommendation or automatic mode when recovering Codex backend failures.
- Make interrupt handling state-aware: if an artifact just advanced the state, stop cleanly before launching the next session.

### 5. State recovery needs a first-class command

After the failed Codex retries, the practical recovery was to edit:

`research/.state.json`

back to:

```json
{
  "state": "SHAPE_FULL",
  "current_iteration": 1,
  "consecutive_failures": 0,
  "phase_retries": 0
}
```

Candidate improvements:

- Add `tiny-lab resume --state SHAPE_FULL`.
- Add `tiny-lab repair-state --to SHAPE_FULL --clear-failures`.
- Let `tiny-lab resume` recover from `DONE` when `resumable=true` and no final artifacts exist.

### 6. Long-running Codex states can produce no artifact and no visible progress

`DOMAIN_RESEARCH` was run with:

```bash
TINYLAB_CODEX_CMD="codex exec --json --skip-git-repo-check" \
tiny-lab run --engine codex --max-iter 3 --timeout-seconds 900 --max-steps 1
```

After more than five minutes, the Codex subprocess was still alive, but no
`research/iter_1/.domain_research.json` artifact had been written. Because
Tiny-Lab captures Codex stdout/stderr until process exit, the loop log did not
show intermediate reasoning, tool events, or whether Codex was stuck on
web/literature search, filesystem work, approval, or model latency.

Candidate improvements:

- Stream Codex JSON events into `research/loop.log`.
- Add per-state artifact heartbeat logging: "still waiting, artifact missing".
- For bounded states like `DOMAIN_RESEARCH`, add a soft timeout before the hard
  backend timeout and fall back to the prompt's offline artifact path.
- Let `tiny-lab run --engine codex` pass a "write artifact now if tools are
  unavailable" nudge when no artifact appears after N seconds.
- Consider smaller per-state Codex prompts or explicit no-network/offline mode
  for local-data projects.

### 7. Prompt says to fall back offline, but Codex did not write the offline artifact

The `DOMAIN_RESEARCH` prompt explicitly says that if WebSearch/WebFetch is
unavailable, slow, or unnecessary, the model should not stall and should write
a conservative artifact with:

```json
{
  "literature_search_status": "offline_or_unavailable",
  "references": []
}
```

In the observed run, Codex remained alive for more than five minutes without
writing `research/iter_1/.domain_research.json`. The fallback instruction was
there, but the backend did not reliably complete the state.

Candidate improvements:

- Make bounded/offline fallback a deterministic engine fallback for states that
  permit it, rather than relying only on prompt compliance.
- Add a state-level `soft_timeout_seconds` that triggers a deterministic repair
  prompt or fallback artifact.
- Add a completion watchdog that sends a shorter "write the artifact now"
  prompt when no artifact appears after N seconds.

### 8. Manual artifact injection became necessary, which breaks autonomous-run purity

To keep the experiment moving, `research/iter_1/.domain_research.json` was
manually written after the stalled Codex `DOMAIN_RESEARCH` run. Tiny-Lab then
advanced correctly from `DOMAIN_RESEARCH` to `DATA_DEEP_DIVE`.

Impact:

- The resulting project is no longer a clean "Codex backend autonomously
  completed every state" run.
- This makes it harder to evaluate whether Tiny-Lab itself can complete the
  research loop under Codex.

Candidate improvements:

- Record artifact provenance: backend-generated, deterministic fallback,
  manual repair, or user-provided.
- Surface a warning in `tiny-lab board/status/audit` when a state was manually
  repaired.
- Provide a first-class `tiny-lab repair-artifact` command that records the
  repair reason and source.

### 9. Background backend processes can survive user interruption

After user interruption / manual cancellation, active `tiny-lab run`, `claude
-p`, or `codex exec` processes had to be checked with:

```bash
pgrep -fl 'tiny-lab run|codex exec|claude -p ## ML Researcher Quality Standard'
```

Then interrupted with `kill -INT`.

Impact:

- A user can believe a run has stopped while a backend process is still holding
  the state lock or writing artifacts.
- Follow-up commands such as `tiny-lab brief` or `tiny-lab run` may race with
  a still-running parent process.

Candidate improvements:

- Add `tiny-lab ps` to list Tiny-Lab parent/backend child processes for the
  current project.
- Make `tiny-lab stop` signal both the loop and active backend child process.
- Persist active backend pid in `research/.state.json` or a sidecar file.
- On startup, detect stale active backend children for the same project and
  refuse or offer cleanup.

### 10. Full prompts are visible in process listings

`pgrep -fl 'codex exec'` and `ps` showed the entire rendered prompt on the
command line, including project constraints and user-provided research details.

Impact:

- Long prompts make process inspection noisy.
- Sensitive project details can leak through process listings.
- Debugging commands become hard to read because the command line contains the
  complete Tiny-Lab prompt.

Candidate improvements:

- Pass prompts to Codex through stdin or a temporary prompt file instead of a
  trailing command-line argument.
- If Codex requires a positional prompt, write a short wrapper command that
  reads the prompt from a file.
- Redact or hash prompt previews in process/debug output.

### 11. Codex session logging is misleading because Codex backend is stateless

The engine logged:

```text
ENGINE: resuming codex session 019df3ad…
```

But `src/tiny_lab/backends/codex.py` says the Codex backend is stateless and
does not use resume semantics. The session id is extracted from Codex JSON
events, but it is informational.

Impact:

- Logs imply continuity that the backend may not actually provide.
- Debugging state carryover becomes confusing when a new `codex exec` prompt is
  launched but the log says "resuming".

Candidate improvements:

- Change log wording for stateless backends: "previous codex session id
  observed" or "new codex exec; previous session id ..."
- Add backend capability metadata: `supports_resume`, `supports_streaming`,
  `supports_tools`, `supports_prompt_stdin`.

### 12. Engine switch and partial run contamination is easy

The project first briefly started with the default Claude backend, then was
interrupted and resumed with Codex. The resulting `research/loop.log` contains
both Claude and Codex attempts.

Impact:

- Mixed-backend logs make it harder to tell which backend produced which
  artifact.
- If the first backend writes an artifact before interruption, the second
  backend may inherit a partially completed state.

Candidate improvements:

- Record `artifact_writer_backend` in completion events.
- Add `tiny-lab reset-run --keep-inputs` for clean restarts that remove
  generated state/artifacts but preserve `data/`, `prior_research/`, and
  `research/.user_idea.txt`.
- Make `tiny-lab run --engine X` warn when the current state or recent events
  were produced by a different backend.

### 13. `--max-steps 1` still blocks on a single long AI session

`--max-steps 1` prevents the engine from continuing to the next state after a
state completes, but it does not cap the time spent inside the current
AI-session state. A stuck `DOMAIN_RESEARCH` still blocked until manual
interrupt or hard timeout.

Candidate improvements:

- Add `--max-state-seconds` or use state-level soft timeouts.
- Add `tiny-lab run --max-steps 1 --watch-artifact` to exit once a valid
  completion artifact appears.
- For bounded preparatory states, prefer deterministic fallback over waiting for
  the full backend timeout.

## Reproduction Notes

1. Initialize a tiny-lab project in a normal directory that is not a git repo.
2. On Tiny-Lab versions before the 2026-05-05 fix pass, run with `--engine codex` and observe the trusted-directory failure.
3. On current Tiny-Lab, run a bounded state such as `DOMAIN_RESEARCH` and observe that artifacts may appear before the parent process logs completion or advances.
4. If the backend stalls, use `tiny-lab ps` or `tiny-lab status` to inspect the recorded child process.
5. Run a bounded state such as `DOMAIN_RESEARCH` and observe whether no artifact or
   progress appears for several minutes.
6. On Tiny-Lab versions before the 2026-05-05 fix pass, inspect processes and observe the full rendered prompt in `ps`/`pgrep` output.

## Current Workaround

The old workaround was:

```bash
TINYLAB_CODEX_CMD="codex exec --json --skip-git-repo-check" \
tiny-lab run --engine codex --max-steps 1
```

Current Tiny-Lab does not need that `TINYLAB_CODEX_CMD` override for the default trusted-directory issue. For bounded debugging, use:

```bash
tiny-lab run --engine codex --max-steps 1
tiny-lab ps
tiny-lab stop
```

Run one state at a time until Codex backend streaming and soft-timeout behavior is more predictable.

If a state stalls without producing an artifact, do not silently repair it when
evaluating Tiny-Lab quality. Record the stall, kill the parent/backend process,
and restart the run with a more stable backend or a deterministic fallback that
records provenance.
