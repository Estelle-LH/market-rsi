"""Project trusted scorer output into label-free Controller feedback."""
import math


def project_feedback(result, score, *, task_id, cik):
    """Whitelist aggregates; do not pass raw result/score objects downstream.

    Provenance hashes and artifact bindings are the caller's responsibility.
    This function neither reads labels nor judges scientific improvement.
    """
    if (not isinstance(result, dict) or type(result.get("planned_targets")) is not int
            or result["planned_targets"] != 5):
        raise ValueError("Original five-target denominator required")
    if not isinstance(task_id, str) or not task_id or not isinstance(cik, str) or not cik:
        raise ValueError("Fixed task/company identity required")
    status = result.get("status")
    if status not in ("COMPLETED_SCORED", "FAILED_NO_RETRY"):
        raise ValueError("Terminal trusted forecast result required")
    complete = status == "COMPLETED_SCORED"
    coverage = result.get("scored_targets")
    if type(coverage) is not int or coverage != (5 if complete else 0):
        raise ValueError("Exact completion/failure coverage required")
    points = None
    if complete:
        points = score.get("score_out_of_5") if isinstance(score, dict) else None
        if (type(points) not in (int, float) or not math.isfinite(points)
                or not 0 <= points <= 5 or type(result.get("points")) not in (int, float)
                or result["points"] != points or score.get("target_count") != 5
                or score.get("prediction_count") != 5 or score.get("duplicate_prediction_ids") != []
                or score.get("unknown_prediction_ids") != []):
            raise ValueError("Aggregate original score/result mismatch")
    elif score is not None:
        # A late or rejected output can have a raw score file but is not accepted.
        raise ValueError("Failed forecast cannot be projected as a scored success")
    execution = {"status": status}
    for name in ("turns", "tool_calls"):
        value = result.get(name)
        if value is not None:
            if type(value) is not int or value < 0:
                raise ValueError("Nonnegative execution count required")
            execution[name] = value
    seconds = result.get("wall_seconds")
    if seconds is not None:
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0:
            raise ValueError("Finite nonnegative execution time required")
        execution["wall_seconds"] = seconds
    if not complete:
        kind = result.get("error_type")
        # No free-form exception message, provider body, or label-bearing path.
        if isinstance(kind, str) and kind.isidentifier() and len(kind) <= 64:
            execution["error_type"] = kind
    return {"schema": "earnings_aggregate_feedback_v1", "task_id": task_id, "cik": cik,
            "evidence_scope": "Opened historical Discovery, not heldout confirmation",
            "prediction": {"planned_targets": 5, "scored_targets": coverage,
                           "score_out_of_5": points}, "execution": execution}
