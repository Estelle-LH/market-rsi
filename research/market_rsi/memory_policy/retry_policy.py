"""Fail-closed decision policy for resume, recovery, skip, and invalidation."""
from __future__ import annotations


PHASES = {
    "manifest_construction", "preflight", "paid_controller", "training",
    "final_evaluation",
}
CAUSES = {
    "source_integrity", "source_semantics", "resource_envelope",
    "transient_transport", "runtime_dependency", "valid_scientific_outcome",
    "budget_gate", "unknown",
}


def decide(event):
    required = {
        "phase", "cause", "manifest_frozen", "valid_scores_written",
        "target_statistics_computed", "valid_controller_response_written",
        "scientific_inputs_unchanged", "causal_fix_tested",
        "idempotent_checkpoint",
    }
    if not isinstance(event, dict) or set(event) != required:
        raise ValueError("exact retry-decision evidence required")
    if event["phase"] not in PHASES or event["cause"] not in CAUSES:
        raise ValueError("unknown phase or cause")
    for key in required - {"phase", "cause", "valid_scores_written"}:
        if type(event[key]) is not bool:
            raise ValueError("retry evidence booleans must be explicit")
    if type(event["valid_scores_written"]) is not int or event["valid_scores_written"] < 0:
        raise ValueError("valid score count must be a nonnegative integer")

    cause = event["cause"]
    if cause == "valid_scientific_outcome":
        return {
            "decision": "accept_outcome_and_stop",
            "reason": "low reward, no improvement, valid timeout, or valid model failure is a result",
            "same_run_retry": False,
            "fresh_id_required": False,
        }

    if cause == "budget_gate":
        return {
            "decision": "stop_before_spend",
            "reason": "an atomic unit that does not fit may not start",
            "same_run_retry": False,
            "fresh_id_required": False,
        }

    if cause in {"source_integrity", "source_semantics"}:
        if (not event["manifest_frozen"]
                and event["phase"] in {"manifest_construction", "preflight"}
                and event["valid_scores_written"] == 0
                and not event["target_statistics_computed"]):
            return {
                "decision": "skip_source_before_freeze",
                "reason": "data-quality selection is allowed only before the manifest is frozen",
                "same_run_retry": False,
                "fresh_id_required": False,
            }
        return {
            "decision": "invalidate_run_and_redesign",
            "reason": "a frozen source cannot be filtered or replaced after the experiment begins",
            "same_run_retry": False,
            "fresh_id_required": True,
        }

    result_exposed = (
        event["valid_scores_written"] > 0
        or event["target_statistics_computed"]
    )
    if result_exposed or not event["scientific_inputs_unchanged"]:
        return {
            "decision": "invalidate_run_and_redesign",
            "reason": "recovery after result exposure or a scientific change would be adaptive",
            "same_run_retry": False,
            "fresh_id_required": True,
        }

    if cause in {"resource_envelope", "transient_transport", "runtime_dependency"}:
        if (event["idempotent_checkpoint"] and event["causal_fix_tested"]):
            return {
                "decision": "resume_same_run",
                "reason": "the exact saved next atomic unit is checkpointed and has no uncertain side effect",
                "same_run_retry": True,
                "fresh_id_required": False,
            }
        if event["valid_controller_response_written"]:
            return {
                "decision": "invalidate_run_and_redesign",
                "reason": "a saved controller decision may be resumed exactly but never resampled in a recovery run",
                "same_run_retry": False,
                "fresh_id_required": True,
            }
        if event["causal_fix_tested"]:
            return {
                "decision": "fresh_id_recovery",
                "reason": "mechanical failure occurred before any scientific result and the isolated fix passed",
                "same_run_retry": False,
                "fresh_id_required": True,
            }

    return {
        "decision": "stop_and_investigate",
        "reason": "unknown or untested failures are not retryable evidence",
        "same_run_retry": False,
        "fresh_id_required": False,
    }
