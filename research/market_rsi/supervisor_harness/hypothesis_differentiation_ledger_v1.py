"""Controller-proposed pure structured hypothesis records; Supervisor persists.

Declared exact-recipe comparison is not semantic theorem proving or evidence
that this workflow outperforms the same model using existing memory.
"""
import hashlib
import json
import re

VERSION = "hypothesis_differentiation_ledger_v1"
SPEC = {"causal_inputs", "equation", "loss", "fitting_constants"}


def _text(value):
    if not isinstance(value, str) or not value.strip(): raise ValueError("nonempty declared research text required")
    return value


def _hash(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value) or value == "0" * 64:
        raise ValueError("exact nonzero source identity required")
    return value


def _copy(value):
    return json.loads(json.dumps(value, allow_nan=False))


def recipe_signature(candidate):
    if not SPEC <= set(candidate): raise ValueError("explicit inputs/equation/loss/constants required")
    inputs = candidate["causal_inputs"]
    if type(inputs) is not list or not inputs or len(set(inputs)) != len(inputs): raise ValueError("distinct causal input names required")
    value = {"causal_inputs": sorted(_text(item) for item in inputs),
        "equation": "".join(_text(candidate["equation"]).split()),
        "loss": "".join(_text(candidate["loss"]).split()), "fitting_constants": candidate["fitting_constants"]}
    if type(value["fitting_constants"]) is not dict or not value["fitting_constants"]:
        raise ValueError("explicit fixed fitting constants required")
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def create_entry(candidate, closest_recipe, scientific_difference, falsifying_observations):
    """Freeze supplied scientific details; no algorithm choice or file writing."""
    signature = recipe_signature(candidate)
    if type(closest_recipe) is not dict: raise ValueError("closest evaluated recipe record required")
    previous = recipe_signature(closest_recipe)
    if type(falsifying_observations) is not list or not falsifying_observations:
        raise ValueError("predeclared falsifying observations required")
    return {"schema": VERSION, "candidate_id": _text(candidate["candidate_id"]),
        "question_id": _text(candidate["question_id"]), "recipe": _text(candidate["recipe"]),
        "specification": _copy({key: candidate[key] for key in SPEC}), "recipe_signature_sha256": signature,
        "research_parent_sha256": _hash(candidate["actual_parent_sha256"]),
        "comparison_incumbent_sha256": _hash(candidate["comparison_incumbent_sha256"]),
        "closest_evaluated_recipe": _copy(closest_recipe), "exact_declared_repeat": signature == previous,
        "scientific_difference": _text(scientific_difference),
        "falsifying_observations": [_text(item) for item in falsifying_observations],
        "status": "proposed_unexecuted", "reviewed_feedback": None,
        "next_choice_rationale": None, "claim": "structured memory, benefit unmeasured"}


def with_feedback(entry, feedback, next_choice_rationale):
    """New record version; valid negative results stay available for exploration."""
    if entry.get("schema") != VERSION: raise ValueError("original ledger version required")
    result = _copy(entry)
    if (feedback.get("independently_reviewed") is not True
            or feedback.get("candidate_id") != entry["candidate_id"]
            or any(feedback.get(key) != entry[key] for key in
                   ("research_parent_sha256", "comparison_incumbent_sha256"))
            or feedback.get("prediction_decision") not in {"KEEP", "REVERT"}
            or feedback.get("performance_status") not in {"valid_no_leakage", "invalid"}):
        raise ValueError("factual independently reviewed feedback required")
    result.update(status="reviewed", reviewed_feedback=_copy(feedback),
        next_choice_rationale=_text(next_choice_rationale),
        valid_performance_evidence=feedback["performance_status"] == "valid_no_leakage",
        retained_for_distinct_research=feedback["performance_status"] == "valid_no_leakage")
    return result
