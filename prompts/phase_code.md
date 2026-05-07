You are generating code for a research phase.

Current iteration: {iter}
Current phase: {current_phase_id} — {current_phase_name}
Phase type: {current_phase_type}
Project directory: {project_dir}

## Project files

{project_tree}

## Previous results

{previous_results_summary}

Use the Read tool to inspect any file above if you need more context (e.g., previous phase scripts, result JSONs, data files).

{phase_error_summary}

**If there is an EXECUTION HISTORY above**: This is a RETRY. Previous script versions failed. You MUST:

1. Study ALL previous attempts — each shows the code that was tried and why it failed
2. Do NOT repeat the same approach that already failed. If multiple attempts failed with the same error, your fix must be fundamentally different
3. Look at stdout for clues (e.g., NaN loss = data scaling issue, not a code syntax issue)
4. Common root causes by error pattern:
   - NaN loss during training → data normalization wrong, learning rate too high, or input features have inf/NaN
   - state_dict is None → model never improved during training (NaN loss), fix the training first
   - FileNotFoundError → wrong path, check TINYLAB_RESULTS_DIR env var
   - `No module named pip` → do not call `python -m pip` directly; use the robust dependency helper below with `uv pip` fallback
   - Shape mismatch → check input dimensions against what previous phases actually produced
5. Read the existing script, understand what was already tried, then write a DIFFERENT fix

## Your Task

Read the full plan at research/{iter}/research_plan.json and find the phase with id "{current_phase_id}".
Read the methodology section carefully — it tells you exactly what to implement.
Read previous phase results from research/{iter}/results/ to use as context.

## Generate the phase script

{phase_script_contract}

Create exactly this preferred script path unless an existing retry script for the
same phase must be edited in place:

`{phase_script_path}`

Do not create additional matching scripts for `{current_phase_id}`. If you need
shared helpers, put them under `shared/lib/` rather than creating alternate
phase scripts.

### Script structure

```python
#!/usr/bin/env python3
"""Phase: {current_phase_name}"""

# 1. Dependency check
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys

def ensure_deps(requirements):
    missing = [pkg for import_name, pkg in requirements if importlib.util.find_spec(import_name) is None]
    if not missing:
        return

    project_root = Path(__file__).resolve().parents[3]
    pip_cache = project_root / ".tiny_lab" / "pip-cache"
    pip_cache.mkdir(parents=True, exist_ok=True)
    pip_env = {**os.environ, "PIP_CACHE_DIR": str(pip_cache)}

    if importlib.util.find_spec("pip") is None:
        try:
            subprocess.check_call(
                [sys.executable, "-m", "ensurepip", "--upgrade", "--default-pip"],
                env=pip_env,
            )
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            print(f"ensurepip failed ({exc}); trying uv pip fallback.", file=sys.stderr)

    if importlib.util.find_spec("pip") is not None:
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", *missing, "-q"],
                env=pip_env,
            )
            return
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            print(f"pip install failed ({exc}); trying uv pip fallback.", file=sys.stderr)

    uv = shutil.which("uv")
    if uv:
        cache_dir = project_root / ".tiny_lab" / "uv-cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        env = {**os.environ, "UV_CACHE_DIR": str(cache_dir)}
        subprocess.check_call(
            [uv, "pip", "install", "--python", sys.executable, *missing, "-q"],
            env=env,
        )
        return
    raise RuntimeError(
        "Missing dependencies and no installer is available. "
        f"Install: {', '.join(missing)}"
    )

ensure_deps([
    # ("numpy", "numpy"),
    # ("sklearn", "scikit-learn"),
])

# 2. Imports
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')  # non-interactive backend
import matplotlib.pyplot as plt
from pathlib import Path
# ... domain-specific imports

# 3. Load previous phase results (if depends_on)
# results_dir = Path(os.environ.get("TINYLAB_RESULTS_DIR", "research/{iter}/results"))

# 4. Main logic — follow the methodology from research_plan.json

# 5. Visualization — MANDATORY for every phase
# Generate at least one plot per phase. Save to results_dir.
# Examples: distribution plots, training curves, prediction vs ground truth,
#           error heatmaps, feature importance bars, confusion matrices

# 6. Save results matching the expected_outputs.report.schema
results = {{
    # MUST match the schema defined in research_plan.json
    # Include "phase_id": "{current_phase_id}" so audits can detect copied or stale results
    # Include formal notation if the plan has formal_notation section
    # Include the applicable fields from the shared evidence contract below
}}
output_path = Path("research/{iter}/results/{current_phase_id}.json")
output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_text(json.dumps(results, indent=2))
print(f"Results saved to {{output_path}}")
```

### Critical rules

1. The script must be SELF-CONTAINED — check its dependencies and use the robust helper above; never assume `python -m pip` is installed
2. The output JSON MUST match the schema in research_plan.json exactly
3. Read previous phase results when the methodology references them
4. Print progress to stdout so the user can monitor
5. If the plan says "reuse phase_X's function", import from that phase's script or shared/lib/

### Visualization rules (MANDATORY)

Every phase script MUST generate at least one plot:

- Save as PNG to results dir: `results_dir / "{current_phase_id}_<plot_name>.png"`
- Use `matplotlib.use('Agg')` — no GUI
- Check the plan's "visualization" field for required plots
- Common plots by phase type:
  - **Preprocessing**: before/after distributions, correlation heatmap, missing data patterns
  - **Baseline**: prediction vs ground truth trajectory, residual plot
  - **Model training**: loss curves (train + val), learning rate schedule
  - **Evaluation**: error distribution histogram, per-sample scatter, comparison bar chart
  - **Ablation**: feature importance bar chart, component contribution

### Statistical rigor rules

- Report mean AND std (not just mean)
- If multiple runs/folds: report across runs
- Include sample sizes (n=...)
- If comparing models: note if difference is statistically significant
- Keep `statistically_significant` / `significant_improvement` flags
  consistent with p-values and comparison confidence intervals. A significant
  comparison should have p <= alpha (default 0.05) or a comparison CI that
  does not cross zero.
- If you declare `alpha` or `significance_level`, use a finite numeric value
  satisfying `0 < value < 1`.
- Cross-reference baselines: "X% improvement over phase_1 baseline (Y → Z)"
- When the plan lists baselines or claims ablation, feature importance,
  sensitivity analysis, cross-validation, multiple splits, error analysis, or
  leakage audits, write the applicable fields from the shared evidence contract:

{evidence_contract}

- Keep baseline flags and improvement values numerically consistent with the
  plan metric direction. For minimize metrics, smaller values beat baselines;
  for maximize metrics, larger values beat baselines.
- Keep target flags such as `target_achieved`, `target_met`,
  `goal_achieved`, or `success_criteria_met` numerically consistent with
  the plan metric target and direction.

### Reproducibility rules

- Set and report explicit seeds/random_state for every stochastic component.
- Record dataset path/source and a stable dataset fingerprint when practical. Fingerprint/checksum/hash fields must use `sha256:<64 hex chars>`; put version labels or row/column descriptions in `dataset_source` or a separate non-fingerprint notes field.
- Record the split protocol and split identifier so evaluation can be reproduced.
- Record environment details and code provenance using fields from the shared
  evidence contract above.
- Record leakage audit outcomes explicitly. If leakage is found, either stop with
  a clear failure or write leakage_resolved/leakage_mitigated only after the
  mitigation is actually applied.

### Domain analysis rules

When a model underperforms or fails:

- Don't just report the number — analyze WHY
- Check: is it a data issue? (distribution shift, missing features, scale mismatch)
- Check: is it a model issue? (capacity, architecture mismatch, optimization)
- Log domain-specific diagnostics to the result JSON under "analysis" key
