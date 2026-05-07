"""Review artifact validation helpers."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .paths import (
    safe_research_artifact_paths_in_text,
    safe_research_result_json_paths_in_text,
    unsafe_research_artifact_paths_in_text,
)


REQUIRED_SCORE_KEYS = (
    "academic_rigor",
    "experimental_sufficiency",
    "novelty",
    "narrative_coherence",
    "goal_achievement",
)
ALLOWED_VERDICTS = ("ACCEPT", "REVISE", "REJECT")
ACCEPT_TOTAL_THRESHOLD = 40
REVISE_TOTAL_THRESHOLD = 35
MIN_ACCEPT_CRITERION_SCORE = 7
RESULT_GROUNDED_ACCEPT_FEEDBACK_CRITERIA = (
    "experimental_sufficiency",
    "goal_achievement",
)


def render_evaluation_contract() -> str:
    """Return the shared professor review contract for prompts and runner docs."""
    criteria = ", ".join(f"`{key}`" for key in REQUIRED_SCORE_KEYS)
    verbs = ", ".join(f"`{verb}`" for verb in _ACTION_VERBS)
    targets = ", ".join(f"`{target}`" for target in _RESEARCH_TARGET_TERMS)
    return f"""## Professor Evaluation Contract (SSOT)

This section is generated from `tiny_lab.review`; update that module instead of copying review rules into prompts.

1. `scores` must contain exactly these criteria: {criteria}.
2. Every score must be numeric and between 1 and 10.
3. `total` must equal the sum of the score values.
4. Verdict thresholds are: `ACCEPT` when total >= {ACCEPT_TOTAL_THRESHOLD}, `REVISE` when {REVISE_TOTAL_THRESHOLD} <= total < {ACCEPT_TOTAL_THRESHOLD}, and `REJECT` when total < {REVISE_TOTAL_THRESHOLD}.
5. `ACCEPT` also requires every criterion score to be at least {MIN_ACCEPT_CRITERION_SCORE}.
6. `ACCEPT` must not include non-empty `required_actions`; unresolved required work means `REVISE`.
7. `REVISE` and `REJECT` must include non-empty, actionable `required_actions`.
8. Each required action, whether written as a string or structured object, must include an action verb such as {verbs}, a concrete research target such as {targets}, and at least two specific details beyond the action verb and generic research target words.
9. `ACCEPT` evaluations must include `feedback`, and when `feedback` is present it must cover every required score criterion. Each `feedback` item must include substantive issue/rationale/comment/recommendation text; `ACCEPT` feedback items must cite a concrete project-relative `research/...` artifact path. `experimental_sufficiency` and `goal_achievement` feedback must cite a concrete `research/iter_*/results/*.json` artifact. If an item includes `criterion` or `score`, the criterion must be one of the required score keys and the item score must be between 1 and 10 and match `scores[criterion]`.
"""


def validate_evaluation_consistency(evaluation: dict[str, Any]) -> list[str]:
    """Validate professor review score totals and verdict thresholds."""
    issues: list[str] = []
    scores = evaluation.get("scores")
    if not isinstance(scores, dict) or not scores:
        return ["evaluation.scores must be a non-empty object"]

    missing_keys = [key for key in REQUIRED_SCORE_KEYS if key not in scores]
    if missing_keys:
        issues.append(f"evaluation.scores missing required criteria: {missing_keys}")
    unknown_keys = [key for key in scores if key not in REQUIRED_SCORE_KEYS]
    if unknown_keys:
        issues.append(f"evaluation.scores contains unknown criteria: {unknown_keys}")

    numeric_scores: list[float] = []
    score_by_name: dict[str, float] = {}
    for name, value in scores.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            issues.append(f"score {name} must be numeric")
            continue
        if not 1 <= float(value) <= 10:
            issues.append(f"score {name} must be between 1 and 10")
        numeric_scores.append(float(value))
        score_by_name[name] = float(value)

    if issues:
        return issues

    actual_total = sum(numeric_scores)
    declared_total = evaluation.get("total")
    if declared_total is None:
        issues.append("evaluation.total is required")
    elif not isinstance(declared_total, (int, float)) or isinstance(declared_total, bool):
        issues.append("evaluation.total must be numeric")
    elif abs(float(declared_total) - actual_total) > 1e-9:
        issues.append(f"evaluation.total {declared_total} does not equal score sum {actual_total:g}")

    verdict = str(evaluation.get("verdict", "")).upper()
    expected = _expected_verdict(actual_total)
    if verdict not in ALLOWED_VERDICTS:
        issues.append(f"invalid verdict: {verdict or '<missing>'}")
    elif verdict != expected:
        issues.append(f"verdict {verdict} contradicts score total {actual_total:g}; expected {expected}")
    elif verdict == "ACCEPT":
        low_scores = {
            name: score
            for name, score in score_by_name.items()
            if name in REQUIRED_SCORE_KEYS and score < MIN_ACCEPT_CRITERION_SCORE
        }
        if low_scores:
            issues.append(
                "ACCEPT evaluation requires every criterion score "
                f">= {MIN_ACCEPT_CRITERION_SCORE}; low scores: {low_scores}"
            )
        if _has_any_required_actions(evaluation):
            issues.append("ACCEPT evaluation must not include required_actions; use REVISE if required work remains")
        if "feedback" not in evaluation:
            issues.append("ACCEPT evaluation must include feedback covering every score criterion")

    issues.extend(_feedback_consistency_issues(evaluation, score_by_name, verdict))
    if verdict in {"REVISE", "REJECT"} and not _has_actionable_required_actions(evaluation):
        issues.append(f"{verdict} evaluation must include non-empty required_actions")

    return issues


def validate_review_feedback_response(
    project_dir: Path,
    state_id: str,
    artifact_data: dict[str, Any],
) -> list[str]:
    """Require revision/restart artifacts to address prior review actions."""
    expected_verdict = {
        "IDEA_REFINE": "REVISE",
        "SHAPE_FULL": "REJECT",
    }.get(state_id)
    if expected_verdict is None:
        return []

    evaluation = _load_previous_evaluation(project_dir)
    if not evaluation:
        return []
    verdict = str(evaluation.get("verdict", "")).upper()
    if verdict != expected_verdict:
        return []

    raw_required_actions = evaluation.get("required_actions", [])
    if not isinstance(raw_required_actions, list):
        raw_required_actions = [raw_required_actions]
    required_actions = [
        text
        for action in raw_required_actions
        if (text := _required_action_text(action).strip())
    ]
    if not required_actions:
        return [f"previous {verdict} evaluation has no required_actions to address"]

    response = _review_response(artifact_data)
    if not isinstance(response, dict):
        return [f"{state_id} must include review_response addressing previous {verdict} required_actions"]

    addressed = response.get("addressed_required_actions") or response.get("required_actions_addressed")
    if not isinstance(addressed, list):
        addressed = []
    deferred = response.get("intentionally_deferred") or response.get("deferred_required_actions")
    if not isinstance(deferred, list):
        deferred = []
    if not addressed and not deferred:
        return [
            f"{state_id}.review_response must include addressed_required_actions "
            "or intentionally_deferred"
        ]

    addressed_texts = [_addressed_action_text(item) for item in addressed]
    deferred_items = [_deferred_action_parts(item) for item in deferred]
    missing = [
        action
        for action in required_actions
        if not any(_addresses_required_action(action, text) for text in addressed_texts)
        and not any(_defers_required_action(action, text, reason) for text, reason in deferred_items)
    ]
    if missing:
        return [f"{state_id}.review_response does not address previous required_actions: {missing}"]
    return []


def _expected_verdict(total: float) -> str:
    if total >= ACCEPT_TOTAL_THRESHOLD:
        return "ACCEPT"
    if total >= REVISE_TOTAL_THRESHOLD:
        return "REVISE"
    return "REJECT"


def _feedback_consistency_issues(
    evaluation: dict[str, Any],
    score_by_name: dict[str, float],
    verdict: str,
) -> list[str]:
    feedback = evaluation.get("feedback")
    if feedback is None:
        return []
    if not isinstance(feedback, list):
        return ["evaluation.feedback must be a list when present"]

    issues: list[str] = []
    covered_criteria: set[str] = set()
    for idx, item in enumerate(feedback):
        if not isinstance(item, dict):
            issues.append(f"evaluation.feedback[{idx}] must be an object")
            continue
        if not _has_substantive_feedback_text(item):
            issues.append(
                f"evaluation.feedback[{idx}] must include a substantive issue, "
                "rationale, comment, or recommendation"
            )
        if verdict == "ACCEPT" and not _feedback_item_cites_artifact(item):
            issues.append(
                f"evaluation.feedback[{idx}] must cite a concrete project-relative research artifact path"
            )

        criterion = item.get("criterion")
        if criterion is not None:
            if not isinstance(criterion, str) or not criterion.strip():
                issues.append(f"evaluation.feedback[{idx}].criterion must be a non-empty string")
            elif criterion not in REQUIRED_SCORE_KEYS:
                issues.append(f"evaluation.feedback[{idx}].criterion is unknown: {criterion}")
            else:
                covered_criteria.add(criterion)
                if (
                    verdict == "ACCEPT"
                    and criterion in RESULT_GROUNDED_ACCEPT_FEEDBACK_CRITERIA
                    and not _feedback_item_cites_result_artifact(item)
                ):
                    issues.append(
                        f"evaluation.feedback[{idx}] for {criterion} must cite a concrete "
                        "research/iter_*/results/*.json artifact path"
                    )

        item_score = item.get("score")
        if item_score is None:
            continue
        if not isinstance(item_score, (int, float)) or isinstance(item_score, bool):
            issues.append(f"evaluation.feedback[{idx}].score must be numeric")
            continue
        if not 1 <= float(item_score) <= 10:
            issues.append(f"evaluation.feedback[{idx}].score must be between 1 and 10")
        if isinstance(criterion, str) and criterion in score_by_name:
            expected = score_by_name[criterion]
            if abs(float(item_score) - expected) > 1e-9:
                issues.append(
                    f"evaluation.feedback[{idx}].score {item_score} does not match "
                    f"scores.{criterion} {expected:g}"
                )
    missing_criteria = [key for key in REQUIRED_SCORE_KEYS if key not in covered_criteria]
    if missing_criteria:
        issues.append(f"evaluation.feedback must cover every score criterion; missing: {missing_criteria}")
    return issues


def _has_substantive_feedback_text(item: dict[str, Any]) -> bool:
    fields = (
        "issue",
        "rationale",
        "comment",
        "recommendation",
        "evidence",
        "required_action",
    )
    for field in fields:
        value = item.get(field)
        if isinstance(value, str) and len(value.strip()) >= 12:
            return True
        if isinstance(value, list) and any(isinstance(entry, str) and len(entry.strip()) >= 12 for entry in value):
            return True
    return False


def _feedback_item_cites_artifact(item: dict[str, Any]) -> bool:
    return bool(safe_research_artifact_paths_in_text(_feedback_item_text(item)))


def _feedback_item_cites_result_artifact(item: dict[str, Any]) -> bool:
    return bool(safe_research_result_json_paths_in_text(_feedback_item_text(item)))


def evaluation_feedback_artifact_paths(evaluation: dict[str, Any]) -> list[str]:
    """Return concrete research artifact paths cited by evaluation feedback."""
    feedback = evaluation.get("feedback")
    if not isinstance(feedback, list):
        return []
    paths: list[str] = []
    for item in feedback:
        if isinstance(item, dict):
            paths.extend(safe_research_artifact_paths_in_text(_feedback_item_text(item)))
    return list(dict.fromkeys(paths))


def evaluation_feedback_unsafe_artifact_paths(evaluation: dict[str, Any]) -> list[str]:
    """Return feedback artifact path citations that are syntactically unsafe."""
    feedback = evaluation.get("feedback")
    if not isinstance(feedback, list):
        return []
    paths: list[str] = []
    for item in feedback:
        if isinstance(item, dict):
            paths.extend(unsafe_research_artifact_paths_in_text(_feedback_item_text(item)))
    return list(dict.fromkeys(paths))


def _feedback_item_text(item: dict[str, Any]) -> str:
    parts: list[str] = []
    for value in item.values():
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            parts.extend(str(entry) for entry in value if isinstance(entry, str))
    return " ".join(parts)


def _load_previous_evaluation(project_dir: Path) -> dict[str, Any] | None:
    path = project_dir / "research" / "evaluation.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def _review_response(artifact_data: dict[str, Any]) -> Any:
    return (
        artifact_data.get("review_response")
        or artifact_data.get("revision_response")
        or artifact_data.get("review_feedback_response")
    )


def _addressed_action_text(item: Any) -> str:
    if isinstance(item, str):
        return item.lower()
    if not isinstance(item, dict):
        return ""
    parts: list[str] = []
    for key in (
        "action",
        "required_action",
        "status",
        "response",
        "how_addressed",
        "planned_change",
        "evidence",
    ):
        value = item.get(key)
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            parts.extend(str(v) for v in value if isinstance(v, str))
    return " ".join(parts).lower()


def _deferred_action_parts(item: Any) -> tuple[str, str]:
    if isinstance(item, str):
        return item.lower(), ""
    if not isinstance(item, dict):
        return "", ""
    text_parts: list[str] = []
    for key in ("action", "required_action", "replacement", "planned_change"):
        value = item.get(key)
        if isinstance(value, str):
            text_parts.append(value)
    reason = item.get("reason") or item.get("why_not_applicable") or item.get("justification")
    reason_text = reason if isinstance(reason, str) else ""
    return " ".join(text_parts).lower(), reason_text.lower()


def _addresses_required_action(required_action: str, addressed_text: str) -> bool:
    terms = _distinctive_terms(required_action)
    if not terms:
        return False
    matches = sum(1 for term in terms if _contains_term(addressed_text, term))
    threshold = min(2, len(terms))
    return matches >= threshold and any(_contains_term(addressed_text, verb) for verb in _ACTION_VERBS)


def _defers_required_action(required_action: str, deferred_text: str, reason: str) -> bool:
    return (
        _addresses_required_action(required_action, deferred_text)
        and _has_substantive_deferral_reason(reason)
    )


def _has_substantive_deferral_reason(reason: str) -> bool:
    if len(reason.strip()) < 24:
        return False
    return any(term in reason for term in _DEFERRAL_REASON_TERMS)


def _distinctive_terms(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    stop_words = {
        "about",
        "after",
        "again",
        "over",
        "the",
        "and",
        "for",
        "from",
        "into",
        "that",
        "this",
        "with",
        "without",
    }
    return [
        word
        for word in words
        if len(word) >= 4 and word not in stop_words and word not in _ACTION_VERBS
    ]


def _has_actionable_required_actions(evaluation: dict[str, Any]) -> bool:
    actions = evaluation.get("required_actions")
    if not isinstance(actions, list) or not actions:
        return False
    return all(_is_actionable_required_action(action) for action in actions)


def _has_any_required_actions(evaluation: dict[str, Any]) -> bool:
    actions = evaluation.get("required_actions")
    if actions is None:
        return False
    if not isinstance(actions, list):
        return True
    return any(_required_action_has_content(action) for action in actions)


def _required_action_has_content(action: Any) -> bool:
    if isinstance(action, str):
        return bool(action.strip())
    if isinstance(action, dict):
        return any(_required_action_has_content(value) for value in action.values())
    if isinstance(action, list):
        return any(_required_action_has_content(value) for value in action)
    return action is not None


def _required_action_text(action: Any) -> str:
    if isinstance(action, str):
        return action.strip()
    if isinstance(action, dict):
        return " ".join(
            text
            for value in action.values()
            if (text := _required_action_text(value))
        )
    if isinstance(action, list):
        return " ".join(
            text
            for value in action
            if (text := _required_action_text(value))
        )
    return ""


_ACTION_VERBS = (
    "add",
    "analyze",
    "audit",
    "collect",
    "compare",
    "compute",
    "correct",
    "document",
    "evaluate",
    "execute",
    "fix",
    "include",
    "investigate",
    "measure",
    "recompute",
    "rerun",
    "replace",
    "reframe",
    "revise",
    "run",
    "validate",
    "verify",
)

_DEFERRAL_REASON_TERMS = (
    "no longer applicable",
    "not applicable",
    "superseded",
    "reframed",
    "replaced",
    "out of scope",
    "infeasible",
    "invalid",
    "contradicts",
)

_RESEARCH_TARGET_TERMS = (
    "ablation",
    "artifact",
    "baseline",
    "claim",
    "confidence interval",
    "cross-validation",
    "cv",
    "dataset",
    "effect size",
    "error analysis",
    "experiment",
    "feature importance",
    "held-out",
    "leakage",
    "metric",
    "model",
    "phase",
    "p-value",
    "reference",
    "reproducibility",
    "result",
    "schema",
    "seed",
    "sensitivity",
    "split",
    "statistic",
)


def _is_actionable_required_action(action: Any) -> bool:
    text = _required_action_text(action).lower()
    if len(text) < 12:
        return False
    has_action_verb = any(_contains_term(text, verb) for verb in _ACTION_VERBS)
    has_research_target = any(_contains_term(text, term) for term in _RESEARCH_TARGET_TERMS)
    return has_action_verb and has_research_target and len(_required_action_specific_terms(text)) >= 2


def _required_action_specific_terms(text: str) -> list[str]:
    generic_target_words = {
        word
        for term in _RESEARCH_TARGET_TERMS
        if " " not in term and "-" not in term
        for word in re.findall(r"[a-z0-9]+", term.lower())
    }
    generic_target_words.update({
        "analysis",
        "artifact",
        "experiment",
        "metric",
        "model",
        "phase",
        "result",
        "schema",
        "study",
    })
    return [
        term
        for term in _distinctive_terms(text)
        if term not in generic_target_words
    ]


def _contains_term(text: str, term: str) -> bool:
    if " " in term or "-" in term:
        return term in text
    return re.search(rf"\b{re.escape(term)}\b", text) is not None
