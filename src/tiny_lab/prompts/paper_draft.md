You are writing a research paper draft based on completed experiments.

Current iteration: {iter}
Project directory: {project_dir}

Previous results:
{previous_results_summary}

## Context — Read ALL of these

1. **Domain understanding**: research/{iter}/.domain_research.json
2. **Data analysis**: research/{iter}/.data_analysis.json
3. **Refined idea**: research/{iter}/.idea_refined.json
4. **Research plan**: research/{iter}/research_plan.json
5. **All phase results**: research/{iter}/results/\*.json
6. **Phase scripts**: research/{iter}/phases/\*.py (for methodology details)

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
- Our contribution (what this work adds)
- Paper structure outline

### 3. Related Work

- From .domain_research.json: SOTA models and their limitations
- Position our approach relative to prior work
- Cite specific papers with [Author, Year] format

### 4. Data & Preprocessing

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

- Dataset statistics table (from .data_analysis.json)
- Feature list with descriptions
- Train/val/test split details
- [Figure placeholder: data distribution, correlation heatmap]

### 5. Methodology

**Mathematical formulation of each model tested:**

For each architecture in Phase 3:

- Model equation (e.g., LSTM: $h_t = f(W_h h_{t-1} + W_x x_t + b)$)
- Loss function: $\mathcal{L} = \frac{1}{N}\sum_{i=1}^{N} \|p_{pred}^i - p_{true}^i\|_2$
- Training details: optimizer, learning rate schedule, batch size, epochs
- Evaluation metric definition with formula

Read the actual phase scripts (research/{iter}/phases/) for implementation details.

### 6. Experimental Results

**From research/{iter}/results/\*.json:**

- Results comparison table (all models, all metrics)
- Best model details (hyperparameters, training curve)
- Baseline comparison (dead reckoning vs ML)
- Statistical significance if applicable
- [Figure placeholder: training curves, prediction vs ground truth, error distribution]
- [Figure placeholder: per-model comparison bar chart]

### 7. Discussion

- Why did the best model work? (connect to domain knowledge)
- Where does it fail? (error analysis from results)
- Comparison to SOTA from domain research

### 8. Conclusion & Limitations

**Conclusion**: 2-3 sentences summarizing contribution and key result
**Limitations** (be honest):

- Data limitations (dataset size, single environment, etc.)
- Methodology limitations
- Evaluation limitations (e.g., "EKF ground truth has ~1-1.5% error")
  **Future work**: 2-3 specific directions based on observed gaps

## Important Rules

1. Every claim must be backed by a specific result from results/\*.json
2. Math formulas use LaTeX notation ($...$)
3. Figures are placeholders: [Figure N: description of what to plot]
4. References use [Author, Year] from .domain_research.json
5. Be honest about limitations — this strengthens the paper
