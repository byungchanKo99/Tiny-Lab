You are designing a novel method for a research paper.

Current iteration: {iter}

## Context

Read all prior artifacts:

- research/{iter}/.domain_research.yaml — SOTA
- research/{iter}/.related_work.yaml — limitations and gap
- research/{iter}/.data_analysis.yaml — data characteristics
- research/{iter}/.idea_refined.yaml — concrete goal and novelty claim

## Your Task

Design the method architecture:

1. **Architecture**: model structure, components, data flow
2. **Training procedure**: loss function, optimizer, schedule, regularization
3. **Theoretical justification**: why this design should work better
4. **Novelty**: what specifically is new vs existing approaches

Be specific — include dimensions, layer types, mathematical formulations where relevant.

## Output

Write to research/{iter}/.method_design.yaml:

- architecture: detailed architecture description
- training_procedure: optimizer, learning rate, batch size, epochs
- loss_function: mathematical formulation
- theoretical_justification: why this should improve over SOTA
- novelty_summary: 1-2 sentences of what's new
- complexity_analysis: parameter count estimate, inference time
