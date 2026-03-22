You are preparing the environment so that newly generated hypotheses can actually execute.

HYPOTHESES ADDED: {hypotheses_hypotheses_added}
CHANGES MADE: {hypotheses_changes_made}

Your job: make sure every new hypothesis will run successfully. Do NOT skip any check.

## Step 1: Read the current state

Read these files:

- research/hypothesis_queue.yaml — find the newly added hypotheses (IDs listed above)
- research/project.yaml — check search_space and levers
- The experiment script (e.g., train.py) — check what --model values and CLI flags it accepts

## Step 2: For each new hypothesis, verify and fix

For each newly added hypothesis:

### 2a. Model/approach support

- Check `project.yaml` `approaches:` section — does the approach have a `model` mapping?
  - If YES → the actual `--model` value is `approaches.{approach}.model` (not the approach name)
  - If NO → the approach name is used directly as `--model` value
- Does the experiment script support `--model {model_value}`?
- If NOT → **add the model implementation to the script**
- Example: if approach is `lgbm_tuned` with `model: lgbm`, check train.py supports `--model lgbm`
- If a new approach needs to be registered → **add it to `approaches:` in project.yaml** with the correct `model` and `description`

### 2b. Package dependencies

- Does the new model need packages not yet installed?
- If YES → **install them**: `pip install catboost`, `pip install torch`, etc.
- Verify installation: `python -c "import catboost"` (must exit 0)

### 2c. CLI flags (argparse)

- Does the hypothesis's search_space reference parameters that the script doesn't accept?
- Check: for each param in `search_space.{approach}`, is there a matching argparse flag?
- If NOT → **add the argparse flag** to the script with a sensible default
- Example: search_space has `min_child_samples` but script has no `--min_child_samples` → add it

### 2d. Levers mapping

- Is each search_space parameter mapped to a lever in project.yaml?
- If NOT → **add the lever** to project.yaml
- Example: `min_child_samples` needs `levers.min_child_samples.flag: "--min_child_samples"`

### 2e. Smoke test

- Run the experiment script with the new approach and default params to verify it works:
  ```bash
  python train.py --model {approach_name}
  ```
- If it fails → diagnose and fix before continuing
- If it prints valid JSON with the metric → confirmed working

## Step 3: Report

Write results as JSON to research/.step_prepare.json with:

- verified: list of approach names that were verified working
- installed_packages: list of packages installed (empty if none)
- code_changes: list of changes made to train.py or other files
- lever_changes: list of levers added to project.yaml
- failed: list of approaches that could not be made to work (with reason)
