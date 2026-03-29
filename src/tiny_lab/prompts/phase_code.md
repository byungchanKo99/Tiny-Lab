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
   - Shape mismatch → check input dimensions against what previous phases actually produced
5. Read the existing script, understand what was already tried, then write a DIFFERENT fix

## Your Task

Read the full plan at research/{iter}/research_plan.json and find the phase with id "{current_phase_id}".
Read the methodology section carefully — it tells you exactly what to implement.
Read previous phase results from research/{iter}/results/ to use as context.

## Generate the phase script

Create: research/{iter}/phases/{current*phase_id}*{current_phase_name_slug}.py

### Script structure

```python
#!/usr/bin/env python3
"""Phase: {current_phase_name}"""

# 1. Auto-install dependencies
import subprocess, sys
def ensure_deps():
    for pkg in [LIST_NEEDED_PACKAGES]:
        try:
            __import__(pkg)
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"])
ensure_deps()

# 2. Imports
import json
from pathlib import Path
# ... domain-specific imports

# 3. Load previous phase results (if depends_on)
# results_dir = Path(os.environ.get("TINYLAB_RESULTS_DIR", "research/{iter}/results"))

# 4. Main logic — follow the methodology from research_plan.json

# 5. Save results matching the expected_outputs.report.schema
results = {{
    # MUST match the schema defined in research_plan.json
}}
output_path = Path("research/{iter}/results/{current_phase_id}.json")
output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_text(json.dumps(results, indent=2))
print(f"Results saved to {{output_path}}")
```

### Critical rules

1. The script must be SELF-CONTAINED — install its own dependencies
2. The output JSON MUST match the schema in research_plan.json exactly
3. Read previous phase results when the methodology references them
4. Print progress to stdout so the user can monitor
5. If the plan says "reuse phase_X's function", import from that phase's script or shared/lib/
