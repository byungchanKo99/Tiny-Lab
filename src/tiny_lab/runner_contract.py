"""Shared contract between the CLI engine and native chat runners.

The engine enforces this contract in code where it can. Native runners
receive the same contract rendered into their installed instructions so
Claude and Codex do not drift apart.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from .evidence import render_evidence_contract
from .phase_contract import PHASE_SCRIPT_CONTRACT_MARKDOWN
from .plan import render_plan_quality_contract
from .quality import render_final_paper_contract
from .refs import render_reference_verification_contract
from .review import render_evaluation_contract
from .runtime_placeholders import resolve_runtime_placeholders
from .workflow import CompletionSpec, ConditionSpec, StateSpec


QUALITY_RUBRIC_REL = Path("prompts") / "_shared" / "ml_researcher_rubric.md"
RUNNER_CONTRACT_PLACEHOLDER = "{{TINY_LAB_RUNNER_CONTRACT}}"
NATIVE_ENGINE_SELECTION_PLACEHOLDER = "{{TINY_LAB_NATIVE_ENGINE_SELECTION}}"
RUNNER_CONTRACT_START_MARKER = "<!-- TINY_LAB_RUNNER_CONTRACT_START -->"
RUNNER_CONTRACT_END_MARKER = "<!-- TINY_LAB_RUNNER_CONTRACT_END -->"
CLAUDE_NATIVE_HOOK_MATCHER = "Write|Edit|MultiEdit|Bash"
CODEX_NATIVE_HOOK_MATCHER = "apply_patch|Bash"
STATE_GATE_COMMAND = "python3 .claude/hooks/state_gate.py"
STATE_ADVANCE_COMMAND = "python3 .claude/hooks/state_advance.py"
REF_VERIFY_COMMAND = "python3 .claude/hooks/ref_verify.py"
RUNNER_STATE_REL = Path("research") / ".state.json"
RUNNER_WORKFLOW_REL = Path("research") / ".workflow.json"


@dataclass(frozen=True)
class RunnerStateContract:
    """Machine-readable state contract shared by engine and native runners."""

    state: str
    iteration: int
    current_phase_id: str | None
    state_type: str
    action: str
    runner_command: str | None
    intended_engine: str
    prompt_path: str | None
    allowed_tools: tuple[str, ...]
    allowed_write_globs: tuple[str, ...]
    blocked_write_globs: tuple[str, ...]
    blocked_bash_patterns: tuple[str, ...]
    completion_artifact: str | None
    completion_required_fields: tuple[str, ...]
    condition: dict[str, Any] | None
    next: str | dict[str, str] | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RunnerStateSnapshot:
    """Resolved current-state view shared by engine helpers and native hooks."""

    contract: RunnerStateContract
    state_data: Mapping[str, Any]
    workflow_data: Mapping[str, Any]
    state_spec: StateSpec | Mapping[str, Any] | None


def find_runner_state_spec(workflow_data: Mapping[str, Any], state_id: str) -> Mapping[str, Any] | None:
    """Return a raw workflow state spec by id."""
    for spec in workflow_data.get("states", []):
        if isinstance(spec, Mapping) and spec.get("id") == state_id:
            return spec
    return None


def load_runner_state_snapshot(
    project_dir: Path,
    *,
    default_engine: str | None = None,
) -> RunnerStateSnapshot | None:
    """Load and resolve the current project state into the runner SSOT shape.

    Native hooks fail open on missing or malformed state files, so this helper
    returns None for unreadable runtime inputs instead of raising.
    """
    state_path = project_dir / RUNNER_STATE_REL
    workflow_path = project_dir / RUNNER_WORKFLOW_REL
    if not state_path.exists() or not workflow_path.exists():
        return None

    try:
        state_data = json.loads(state_path.read_text())
        workflow_data = json.loads(workflow_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    if not isinstance(state_data, Mapping) or not isinstance(workflow_data, Mapping):
        return None
    if not isinstance(workflow_data.get("states", []), list):
        return None

    return resolve_runner_state_snapshot(
        state_data=state_data,
        workflow_data=workflow_data,
        default_engine=default_engine,
    )


def resolve_runner_state_snapshot(
    *,
    state_data: Mapping[str, Any],
    workflow_data: Mapping[str, Any],
    default_engine: str | None = None,
) -> RunnerStateSnapshot:
    """Resolve raw `.state.json` and workflow data into the runner SSOT shape."""
    state_id = str(state_data.get("state") or "INIT")
    iteration = _coerce_iteration(state_data.get("current_iteration"))
    current_phase_id = _optional_str(state_data.get("current_phase_id"))
    spec = None if state_id == "DONE" else find_runner_state_spec(workflow_data, state_id)
    effective_default_engine = str(default_engine or workflow_data.get("engine") or "claude")
    contract = resolve_runner_state_contract(
        state_id=state_id,
        iteration=iteration,
        current_phase_id=current_phase_id,
        spec=spec,
        default_engine=effective_default_engine,
    )
    return RunnerStateSnapshot(
        contract=contract,
        state_data=state_data,
        workflow_data=workflow_data,
        state_spec=spec,
    )


def resolve_runner_state_contract(
    *,
    state_id: str,
    iteration: int,
    current_phase_id: str | None,
    spec: StateSpec | Mapping[str, Any] | None,
    default_engine: str,
) -> RunnerStateContract:
    """Resolve the current-state runner contract from workflow/state SSOT.

    The CLI engine and native runner helpers should consume this shape instead
    of re-deriving prompt, gate, completion, and transition fields.
    """
    if state_id == "DONE":
        return RunnerStateContract(
            state="DONE",
            iteration=iteration,
            current_phase_id=current_phase_id,
            state_type="terminal",
            action="No action required.",
            runner_command=None,
            intended_engine=default_engine,
            prompt_path=None,
            allowed_tools=(),
            allowed_write_globs=(),
            blocked_write_globs=(),
            blocked_bash_patterns=(),
            completion_artifact=None,
            completion_required_fields=(),
            condition=None,
            next=None,
        )
    if spec is None:
        return RunnerStateContract(
            state=state_id,
            iteration=iteration,
            current_phase_id=current_phase_id,
            state_type="unknown",
            action=(
                f"State `{state_id}` is missing from research/.workflow.json. "
                "Inspect or repair the workflow before continuing."
            ),
            runner_command=None,
            intended_engine=default_engine,
            prompt_path=None,
            allowed_tools=(),
            allowed_write_globs=(),
            blocked_write_globs=(),
            blocked_bash_patterns=(),
            completion_artifact=None,
            completion_required_fields=(),
            condition=None,
            next=None,
        )

    completion = _completion(spec)
    completion_artifact = None
    completion_required_fields: tuple[str, ...] = ()
    if completion is not None:
        completion_artifact = _resolve_contract_placeholders(
            completion.artifact,
            iteration=iteration,
            current_phase_id=current_phase_id,
        )
        completion_required_fields = tuple(completion.required_fields)

    state_type = str(_get_spec_field(spec, "type", "ai_session"))
    if state_type == "ai_session":
        action = "Run tiny-lab prompt, follow the rendered prompt natively, then write the completion artifact."
        runner_command = "tiny-lab prompt"
    else:
        action = "Run tiny-lab step so the engine handler applies this state."
        runner_command = "tiny-lab step"

    return RunnerStateContract(
        state=state_id,
        iteration=iteration,
        current_phase_id=current_phase_id,
        state_type=state_type,
        action=action,
        runner_command=runner_command,
        intended_engine=str(_get_spec_field(spec, "engine") or default_engine),
        prompt_path=_optional_str(_get_spec_field(spec, "prompt")),
        allowed_tools=tuple(_list_spec_field(spec, "allowed_tools")),
        allowed_write_globs=tuple(
            _resolve_contract_placeholders(item, iteration=iteration, current_phase_id=current_phase_id)
            for item in _list_spec_field(spec, "allowed_write_globs")
        ),
        blocked_write_globs=tuple(
            _resolve_contract_placeholders(item, iteration=iteration, current_phase_id=current_phase_id)
            for item in _list_spec_field(spec, "blocked_write_globs")
        ),
        blocked_bash_patterns=tuple(
            _resolve_contract_placeholders(item, iteration=iteration, current_phase_id=current_phase_id)
            for item in _list_spec_field(spec, "blocked_bash_patterns")
        ),
        completion_artifact=completion_artifact,
        completion_required_fields=completion_required_fields,
        condition=_condition_to_dict(_condition(spec)),
        next=_next(spec),
    )


RUNNER_CONTRACT_MARKDOWN = (
    """## Shared Runner Contract (SSOT)

This section is generated from `tiny_lab.runner_contract`. Update that module, not individual runner copies.

### Execution Rules

1. Run `tiny-lab doctor` before advancing work in a newly opened or resumed session. If it reports a failure, surface that issue and do not execute `tiny-lab prompt` or `tiny-lab step` until the readiness problem is fixed.
2. Run `tiny-lab brief` at the start of every turn and treat its state, action, command, gate, completion, condition, and next-state fields as authoritative.
3. Do not hand-parse `research/.workflow.json` unless you are debugging the workflow itself; `tiny-lab brief` and native hooks are generated from `tiny_lab.runner_contract.resolve_runner_state_snapshot` / `resolve_runner_state_contract`, the same machine-readable contract the CLI engine consumes.
4. Do not skip states or collapse multiple states unless the user explicitly asks for autonomous mode.
5. Execute the `runner_command` from `tiny-lab brief --json`: AI-session states render through `tiny-lab prompt`; deterministic/process/phase/checkpoint states execute through `tiny-lab step`.
6. Artifact completion, transition application, and conditional next-state resolution are implemented in `tiny_lab.advancement`; the CLI engine and native PostToolUse hook both use that module.
7. For process, phase-run/evaluate/record, and checkpoint states, use `tiny-lab step` so the same engine handlers apply the transition.
8. Path/tool/Bash gate policy is implemented in `tiny_lab.hooks.state_policy` and consumes `RunnerStateContract`; the native PreToolUse hook is only the runtime adapter.
9. Let hooks enforce path/tool gates and artifact advancement. Do not hand-edit `.state.json` to bypass a gate.

### Execution Modes

1. CLI engine mode runs the state machine from `tiny-lab run`, spawning the configured backend for AI-session states and applying deterministic handlers directly.
2. Native runner mode runs inside the active Claude/Codex chat session. It uses the same `.state.json`, same workflow JSON, same prompt renderer, same state gate policy, and same completion advancement logic.
3. Switching modes is allowed because both modes consume the same state and workflow files. Use `tiny-lab brief` after switching to refresh the current contract.
4. For AI-session states, native runners execute `tiny-lab prompt`, follow the rendered prompt, and write the completion artifact. For non-AI states, they execute `tiny-lab step` so engine handlers remain authoritative.
5. Per-state `"engine"` overrides are advisory in native mode and executable in CLI mode. Native runners must compare `engine`/`intended_engine` from `tiny-lab brief` before proceeding.

### Prompt Preambles

1. Load `prompts/_shared/ml_researcher_rubric.md` when present.
2. Load `research/constraints.json` when present.
3. Apply both preambles before the state prompt. The quality rubric is first; constraints are second.
4. If a project overrides the package prompt file, use the project file.

### Runtime Context

Prompts may use these placeholders:

| Placeholder | Source |
| --- | --- |
| `{iter}` | `iter_<iteration>` from `RunnerStateContract.iteration` |
| `{iteration}` | `RunnerStateContract.iteration` |
| `{project_dir}` | Current project directory |
| `{current_phase_id}` | `RunnerStateContract.current_phase_id` |
| `{current_phase}` | Matching phase object from `research/iter_N/research_plan.json` |
| `{previous_results_summary}` | Summaries of `research/iter_N/results/*.json` |
| `{plan_quality_contract}` | Experimental plan contract from `tiny_lab.plan` |
| `{reference_verification_contract}` | Reference verification contract from `tiny_lab.refs` |
| `{final_paper_contract}` | Final-paper contract from `tiny_lab.quality` |
| `{evaluation_contract}` | Professor review contract from `tiny_lab.review` |

Path fields in the runner contract, including completion artifacts and allowed/blocked path globs, resolve `{iter}`, `{iteration}`, and `{current_phase_id}` through `tiny_lab.runtime_placeholders`.
"""
    + "\n"
    + PHASE_SCRIPT_CONTRACT_MARKDOWN
    + "\n\n"
    + render_plan_quality_contract()
    + "\n\n"
    + render_evidence_contract()
    + "\n\n"
    + render_reference_verification_contract()
    + "\n\n"
    + render_final_paper_contract()
    + "\n\n"
    + render_evaluation_contract()
    + """

### ML Research Quality Gates

ML research artifacts must satisfy these blocking expectations:

1. Quantitative claims cite concrete `research/iter_*/results/*.json` artifacts in the same sentence, and final papers cite every result artifact at least once.
2. Plans include leakage checks, explicit non-ML and simple ML entries in the `baselines` list, ablation or feature importance, error analysis, and cross-validation or multiple splits when applicable.
3. Experimental result schemas and JSON payloads materialize the applicable fields from the shared Experimental Evidence Contract above.
4. Significance flags must be consistent with p-values and comparison confidence intervals.
5. Baseline comparison flags and improvement values must be numerically consistent with the plan metric direction.
6. Target achievement flags must be numerically consistent with the plan metric target and direction.
7. Experimental result schemas materialize leakage evidence and only set resolved/mitigated flags after mitigation is actually applied.
8. ACCEPT reviews must be consistent with score totals, complete feedback coverage, final-paper structure, completed planned phases, supported numeric claims, unresolved leakage checks, and reference verification sidecars.

### Completion Audit

Before reporting final completion after an ACCEPT verdict, run:

```bash
tiny-lab audit --strict --all
```

If the audit fails, the work is not complete. Convert the failures into the next plan fix, phase, or review action.

### Failure Modes

1. If the same artifact is rewritten repeatedly and the state does not advance, inspect the completion required fields and surface the mismatch.
2. If a hook blocks a path or tool that seems correct, treat it as a preset/workflow bug instead of bypassing the hook.
3. If `.state.json` reaches the workflow circuit breaker, stop and ask for a manual fix or resume action.
4. If the user asks for autonomous mode, prefer the CLI engine path: `tiny-lab run` or `tiny-lab run --engine codex`.
5. For bounded autonomous runs, use `tiny-lab run --max-iterations N --timeout-seconds 300` so the engine finishes at the requested iteration cap and then enters synthesis/review.
6. For backend smoke tests, use `tiny-lab run --max-steps 1 --timeout-seconds 300` so the engine invokes one state and pauses with a bounded backend call.

### Native Runner Commands

```bash
tiny-lab status              # one-line state summary
tiny-lab doctor              # project, workflow, hook, and backend command readiness
tiny-lab doctor --repair-runner # repair native runner hooks/docs without rewriting workflow state
tiny-lab doctor --probe-backend # verify backend login/auth before autonomous execution
tiny-lab brief               # current state action, gates, completion artifact, and next transition
tiny-lab brief --json        # machine-readable RunnerStateContract, including runner_command
tiny-lab prompt              # render the exact current ai_session prompt from the engine SSOT
tiny-lab step                # execute one deterministic/process/phase state with engine handlers
tiny-lab run --max-iterations 3 --timeout-seconds 300 # bounded autonomous run through the requested iteration cap
tiny-lab run --max-steps 1 --timeout-seconds 300 # backend smoke test: execute one state, then pause
tiny-lab board               # dashboard with artifacts and visualizations
tiny-lab audit --strict --all # research quality gates across all iterations
cat research/.state.json     # debug-only raw state file; do not use instead of brief
```
"""
)


@dataclass(frozen=True)
class NativeRunnerProfile:
    """Rendered native-runner instructions that differ only by local agent identity."""

    name: str
    local_engine: str
    other_engine: str
    autonomous_command: str


NATIVE_RUNNER_PROFILES: dict[str, NativeRunnerProfile] = {
    "claude": NativeRunnerProfile(
        name="Claude Code",
        local_engine="claude",
        other_engine="codex",
        autonomous_command="tiny-lab run",
    ),
    "codex": NativeRunnerProfile(
        name="Codex CLI",
        local_engine="codex",
        other_engine="claude",
        autonomous_command="tiny-lab run --engine codex",
    ),
}


def render_native_engine_selection(runner: str | NativeRunnerProfile) -> str:
    """Render provider-specific native engine-selection guidance from SSOT."""
    profile = _native_runner_profile(runner)
    return f"""## Engine selection (multi-backend)

The state spec may include `"engine": "{profile.other_engine}"` to force a specific state to run on {profile.other_engine} instead of {profile.local_engine}. In native agent mode you are the {profile.name} runner, so you cannot literally hand off to the other backend inside the same chat session.

- If `tiny-lab brief` reports `engine: {profile.other_engine}` and the user wants the intended backend, suggest dropping back to CLI mode (`tiny-lab run --engine {profile.other_engine}`) for that state, then resuming native mode.
- Otherwise execute the `runner_command` from `tiny-lab brief --json` yourself and warn the user once that the intended engine was `{profile.other_engine}` but native mode is using `{profile.local_engine}`.

When the user wants to switch back to autonomous mode mid-workflow, remind them they can leave the chat and run `{profile.autonomous_command}` to let the engine drive the rest; `.state.json` carries the position over."""


def _native_runner_profile(runner: str | NativeRunnerProfile) -> NativeRunnerProfile:
    if isinstance(runner, NativeRunnerProfile):
        return runner
    key = str(runner).strip().lower()
    if key not in NATIVE_RUNNER_PROFILES:
        raise ValueError(f"unknown native runner profile: {runner}")
    return NATIVE_RUNNER_PROFILES[key]


def _infer_native_runner(text: str) -> str:
    lowered = text.lower()
    if "codex" in lowered and "agents.md" in lowered:
        return "codex"
    if "codex agent" in lowered:
        return "codex"
    return "claude"


def _resolve_contract_placeholders(
    value: str,
    *,
    iteration: int,
    current_phase_id: str | None,
) -> str:
    return resolve_runtime_placeholders(
        value,
        iteration=iteration,
        current_phase_id=current_phase_id,
    )


def _get_spec_field(spec: StateSpec | Mapping[str, Any], key: str, default: Any = None) -> Any:
    if isinstance(spec, Mapping):
        return spec.get(key, default)
    return getattr(spec, key, default)


def _list_spec_field(spec: StateSpec | Mapping[str, Any], key: str) -> list[str]:
    value = _get_spec_field(spec, key, [])
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _coerce_iteration(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 1


def _completion(spec: StateSpec | Mapping[str, Any]) -> CompletionSpec | None:
    raw = _get_spec_field(spec, "completion")
    if raw is None:
        return None
    if isinstance(raw, CompletionSpec):
        return raw
    if isinstance(raw, Mapping):
        return CompletionSpec(
            artifact=str(raw.get("artifact", "")),
            required_fields=list(raw.get("required_fields", [])),
        )
    return None


def _condition(spec: StateSpec | Mapping[str, Any]) -> ConditionSpec | None:
    raw = _get_spec_field(spec, "condition")
    if raw is None:
        return None
    if isinstance(raw, ConditionSpec):
        return raw
    if isinstance(raw, Mapping):
        return ConditionSpec(
            source=raw.get("source"),
            field=raw.get("field"),
            check=raw.get("check"),
        )
    return None


def _condition_to_dict(condition: ConditionSpec | None) -> dict[str, Any] | None:
    if condition is None:
        return None
    data = asdict(condition)
    return {key: value for key, value in data.items() if value is not None}


def _next(spec: StateSpec | Mapping[str, Any]) -> str | dict[str, str] | None:
    value = _get_spec_field(spec, "next")
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return {str(key): str(target) for key, target in value.items()}
    return None


def render_runner_contract() -> str:
    """Return the shared runner contract rendered for installation."""
    return RUNNER_CONTRACT_MARKDOWN.strip()


def render_contract_template(text: str, *, native_runner: str | None = None) -> str:
    """Replace shared runner placeholders in a template string."""
    rendered = text.replace(RUNNER_CONTRACT_PLACEHOLDER, render_runner_contract_block())
    if NATIVE_ENGINE_SELECTION_PLACEHOLDER in rendered:
        rendered = rendered.replace(
            NATIVE_ENGINE_SELECTION_PLACEHOLDER,
            render_native_engine_selection(native_runner or _infer_native_runner(text)),
        )
    return rendered


def render_runner_contract_block() -> str:
    """Render the managed runner contract block embedded in runner docs."""
    return (
        f"{RUNNER_CONTRACT_START_MARKER}\n"
        f"{render_runner_contract().rstrip()}\n"
        f"{RUNNER_CONTRACT_END_MARKER}"
    )


def claude_hooks_config() -> dict[str, list[dict[str, Any]]]:
    """Return the Claude Code hook registration generated from SSOT values."""
    return {
        "PreToolUse": [
            {
                "matcher": CLAUDE_NATIVE_HOOK_MATCHER,
                "hooks": [
                    {
                        "type": "command",
                        "command": STATE_GATE_COMMAND,
                        "timeout": 30,
                    },
                ],
            },
        ],
        "PostToolUse": [
            {
                "matcher": CLAUDE_NATIVE_HOOK_MATCHER,
                "hooks": [
                    {
                        "type": "command",
                        "command": STATE_ADVANCE_COMMAND,
                        "timeout": 30,
                    },
                ],
            },
            {
                "matcher": CLAUDE_NATIVE_HOOK_MATCHER,
                "hooks": [
                    {
                        "type": "command",
                        "command": REF_VERIFY_COMMAND,
                        "timeout": 60,
                    },
                ],
            },
        ],
    }


def codex_hooks_config() -> dict[str, Any]:
    """Return the Codex native hook registration generated from SSOT values."""
    return {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": CODEX_NATIVE_HOOK_MATCHER,
                    "hooks": [
                        {
                            "type": "command",
                            "command": STATE_GATE_COMMAND,
                            "statusMessage": "tiny-lab: checking state gate",
                            "timeout": 30,
                        },
                    ],
                },
            ],
            "PostToolUse": [
                {
                    "matcher": CODEX_NATIVE_HOOK_MATCHER,
                    "hooks": [
                        {
                            "type": "command",
                            "command": STATE_ADVANCE_COMMAND,
                            "statusMessage": "tiny-lab: checking state advance",
                            "timeout": 30,
                        },
                        {
                            "type": "command",
                            "command": REF_VERIFY_COMMAND,
                            "statusMessage": "tiny-lab: verifying references",
                            "timeout": 60,
                        },
                    ],
                },
            ],
        },
    }


def render_codex_hooks_json() -> str:
    """Render the Codex hooks JSON generated from the shared runner contract."""
    return json.dumps(codex_hooks_config(), indent=2) + "\n"


def ensure_matcher_tools(matcher: str, required_tools: list[str]) -> str:
    """Return a pipe matcher containing all required tools, preserving order."""
    parts = [part for part in str(matcher).split("|") if part]
    for tool in required_tools:
        if tool not in parts:
            parts.append(tool)
    return "|".join(dict.fromkeys(parts))


def load_quality_preamble(project_dir: Path) -> str:
    """Load the shared ML research quality standard, if available.

    Project-local prompts take precedence over the packaged default so an
    initialized project can intentionally customize the rubric.
    """
    candidates = [
        project_dir / QUALITY_RUBRIC_REL,
        Path(__file__).parent / QUALITY_RUBRIC_REL,
    ]
    for path in candidates:
        try:
            if path.exists():
                return path.read_text()
        except OSError:
            continue
    return ""
