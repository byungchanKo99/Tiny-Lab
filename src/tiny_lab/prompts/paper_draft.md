You are writing a research paper draft based on completed experiments.

Current iteration: {iter}
Project directory: {project_dir}

Previous results:
{previous_results_summary}

## Context — Read ALL of these

1. **Domain understanding**: research/{iter}/.domain_research.json
2. **Data analysis**: research/{iter}/.data_analysis.json
3. **Refined idea**: research/{iter}/.idea_refined.json
4. **Research plan**: research/{iter}/research_plan.json (especially formal_notation and baselines)
5. **All phase results**: research/{iter}/results/\*.json
6. **Phase scripts**: research/{iter}/phases/\*.py (for methodology details)
7. **Generated plots**: research/{iter}/results/\*.png (reference these as figures)

## Paper Structure

Write to research/{iter}/paper_draft.md with these sections:

### 1. Abstract (150-250 words)

- Problem: one sentence
- Approach: what we did (method + data)
- Key result: best metric value and comparison to baseline
- Conclusion: one sentence takeaway

### 2. Introduction

- Problem motivation (from domain research)
- Research gap (what existing methods lack)
- **Contributions** (explicit numbered list):
  ```
  The main contributions of this work are:
  1. [First/Novel contribution] ...
  2. [Systematic/Empirical contribution] ...
  3. [Practical contribution] ...
  ```
- Paper structure outline

### 3. Problem Definition

**Formal mathematical formulation (REQUIRED):**

Use the formal_notation from research_plan.json as a starting point, then expand:

- Input space: $X \in \mathbb{R}^{T \times d}$ with explicit description of each dimension
- Output space: $Y \in \mathbb{R}^{T \times k}$
- Objective: $\min_\theta \mathcal{L}(f_\theta(X), Y)$
- Evaluation metric: formal definition with formula
- Constraints: formal statement of any constraints

Every variable must be defined. Every formula must use consistent notation throughout the paper.

### 4. Related Work

- From .domain_research.json: SOTA models and their limitations
- Position our approach relative to prior work
- Cite specific papers with [Author, Year] format
- Organize by theme (e.g., "Classical approaches", "Deep learning approaches", "Domain-specific methods")

### 5. Data & Preprocessing

**This must be detailed with mathematical formulations:**

For each preprocessing step in Phase 0:

- **What**: describe the transformation
- **Why**: domain justification (from .domain_research.json)
- **How**: mathematical formula

Example level of detail:

- Gravity removal: $a_{free} = a_{raw} - R^T \cdot g_{NED}$ where $R = R(q)$ is the rotation matrix from quaternion
- Coordinate transform: $v_{NED} = R(q) \cdot v_{body}$
- Normalization: $x_{norm} = (x - \mu_{train}) / \sigma_{train}$

Include:

- **Table 1**: Dataset statistics (samples, features, duration, splits) from .data_analysis.json
- Feature list with descriptions and units
- Train/val/test split details with rationale
- Reference preprocessing visualizations from results/\*.png:
  - Figure: data distribution before/after preprocessing
  - Figure: feature correlation heatmap
  - Figure: missing data patterns (if applicable)

### 6. Methodology

**Mathematical formulation of each model tested (REQUIRED):**

For each architecture:

- Full model equation with all terms defined
- Loss function with formula
- Training details: optimizer, learning rate schedule, batch size, epochs
- Hyperparameter choices with justification

For example:

- LSTM: $h_t = \sigma(W_{ih} x_t + W_{hh} h_{t-1} + b_h)$, $\hat{y}_t = W_{ho} h_t + b_o$
- Attention: $\alpha_t = \text{softmax}(q_t^T K / \sqrt{d_k})$, $c_t = \alpha_t V$

Read the actual phase scripts (research/{iter}/phases/) for implementation details. Convert code to math.

### 7. Experimental Results

**From research/{iter}/results/\*.json:**

- **Table 2**: Main results comparison (all models, all metrics, with std)
  - Include ALL baselines (non-ML + simple ML + proposed)
  - Report: mean +/- std, best, and sample size
  - Bold the best result per metric
- Best model details (hyperparameters, training curve)
- Statistical significance tests where applicable
- Reference visualizations from results/\*.png:
  - Figure: training curves (loss + metric over epochs)
  - Figure: prediction vs ground truth
  - Figure: error distribution / residual analysis
  - Figure: model comparison bar chart
  - Figure: per-sample or per-segment performance scatter

### 8. Analysis & Discussion

**This section must go beyond restating numbers:**

- **Why did the best model work?** Connect to domain knowledge and data characteristics
- **Where does it fail?** Error analysis with specific examples
  - Which samples/segments have highest error? Why?
  - Is there a pattern? (e.g., during turns, at high speed, etc.)
- **Domain shift analysis** (if multiple data sources):
  - Feature distribution comparison between sources
  - Performance degradation quantification
  - Root cause (scale mismatch, missing features, etc.)
- **Ablation insights**: which components matter most and why?
- **Comparison to SOTA** from domain research: how do our results compare?
- **Unexpected findings**: anything surprising in the results?

### 9. Conclusion

- **Summary**: 2-3 sentences summarizing the approach and key result
- **Contributions revisited**: restate the numbered contributions with supporting evidence
- **Limitations** (be honest and specific):
  - Data limitations (dataset size, single environment, sensor quality, etc.)
  - Methodology limitations (assumptions, simplifications)
  - Evaluation limitations (e.g., "EKF ground truth has ~1-1.5% error")
- **Future work**: 2-3 specific, actionable directions based on observed gaps

## Important Rules

1. Every claim must be backed by a specific result from results/\*.json
2. Math formulas use LaTeX notation ($...$) — every model, loss, and metric must have a formula
3. Reference actual generated plots: "As shown in Figure N (results/{current_phase_id}\_plot.png), ..."
4. References use [Author, Year] from .domain_research.json
5. Be honest about limitations — this strengthens the paper
6. Tables must include std/CI, not just mean values
7. Contributions must be explicitly stated in Introduction and revisited in Conclusion
