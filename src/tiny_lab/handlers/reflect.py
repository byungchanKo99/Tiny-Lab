"""REFLECT_DONE handler — enforce iteration when future seeds exist."""
from __future__ import annotations

import json

from ..logging import log
from ..paths import iter_dir
from ..state import LoopState
from ..workflow import StateSpec
from . import EngineContext, StateResult


class ReflectDoneHandler:
    """Read reflect.json and decide next state.

    If decision is 'done' but future_iteration_seeds exist,
    override to 'idea_mutation' — research should continue.
    """

    def execute(self, spec: StateSpec, ls: LoopState, ctx: EngineContext) -> StateResult:
        reflect_path = iter_dir(ctx.project_dir, ls.current_iteration) / "reflect.json"
        if not reflect_path.exists():
            log("ENGINE: reflect.json not found, stopping")
            return StateResult(transition="DONE")

        data = json.loads(reflect_path.read_text())
        decision = data.get("decision", "done")
        seeds = data.get("future_iteration_seeds", [])

        # Override: done + seeds → idea_mutation
        if decision == "done" and seeds:
            log(f"ENGINE: reflect said done but has {len(seeds)} seeds — overriding to idea_mutation")
            # Pick first seed as new_idea if not already set
            if not data.get("new_idea") and seeds:
                data["new_idea"] = seeds[0] if isinstance(seeds[0], str) else seeds[0].get("idea", str(seeds[0]))
                data["decision"] = "idea_mutation"
                reflect_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            decision = "idea_mutation"

        # Resolve next state from spec.next map
        if isinstance(spec.next, dict):
            target = spec.next.get(decision, spec.next.get("done", "DONE"))
        else:
            target = spec.next or "DONE"

        log(f"ENGINE: reflect decision={decision} → {target}")
        return StateResult(transition=target)
