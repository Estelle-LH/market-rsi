"""Pure, opt-in learning evidence checks; not a predictor judge or reward service.

Artifact hashes bind Supervisor-reviewed evidence; they do not prove its contents.
Canonical finding identities must be assigned by that independent review.
"""
from __future__ import annotations

import copy
import re
from typing import Any, Mapping

SCHEMA = "market_rsi_learning_checkpoint_v1"
EVIDENCE_SCHEMA_V4 = "market_rsi_discovery_controller_evidence_v4"


def _exact(value: object, keys: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{label} fields changed")
    return value


def _hash(value: object, label: str, *, optional: bool = False) -> None:
    if optional and value is None:
        return
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value) or value == "0" * 64:
        raise ValueError(f"{label} requires an exact nonzero SHA256")


def _reason(value: object) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > 1024 or any(ord(c) < 32 for c in value):
        raise ValueError("learning/exploration reason must be bounded nonempty text")


def validate_validity(value: object, branch: Mapping[str, Any]) -> dict:
    """Validate original independent performance classification before any KEEP."""
    validity = _exact(value, {"status", "leakage_detected", "review_sha256", "reason"}, "validity")
    if validity["status"] not in {"valid", "invalid", "inconclusive"} or type(validity["leakage_detected"]) is not bool:
        raise ValueError("invalid performance-validity classification")
    _hash(validity["review_sha256"], "validity review")
    _reason(validity["reason"])
    if validity["review_sha256"] != branch["review_sha256"]:
        raise ValueError("validity is not bound to the original result review")
    if validity["status"] == "valid" and (branch["execution_outcome"] != "succeeded" or branch["independently_reviewed"] is not True or validity["leakage_detected"]):
        raise ValueError("valid forecasts require succeeded, nonleaking independent evidence")
    if branch["review_decision"] == "KEEP" and validity["status"] != "valid":
        raise ValueError("learning cannot turn an invalid forecast into KEEP")
    return copy.deepcopy(validity)


def assess_checkpoint(value: object, branch: Mapping[str, Any], known_findings: set[str]) -> dict:
    """Validate a fresh input and compute deduplicated credit, without side effects."""
    item = _exact(value, {"schema", "validity", "prediction_decision", "learning", "exploration", "reuse", "authority_snapshot_sha256"}, "checkpoint")
    _hash(item["authority_snapshot_sha256"], "authority snapshot")
    if item["schema"] != SCHEMA or item["prediction_decision"] != branch["review_decision"]:
        raise ValueError("checkpoint schema or frozen prediction decision changed")
    validity = validate_validity(item["validity"], branch)
    if "performance_validity" in branch and validity != branch["performance_validity"]:
        raise ValueError("checkpoint changed original independent performance validity")
    learning = _exact(item["learning"], {"requested_credit", "kind", "finding_sha256", "evidence_sha256", "review_sha256", "reason"}, "learning")
    credit = learning["requested_credit"]
    if type(credit) is not int or credit not in {0, 1, 2}:
        raise ValueError("learning credit must be integer 0, 1, or 2")
    permitted = {0: {"activity"}, 1: {"finding", "failure_diagnosis"}, 2: {"hypothesis_test", "tool_validation", "failure_repair"}}
    if learning["kind"] not in permitted[credit]:
        raise ValueError("learning level requires its corresponding evidence kind")
    _reason(learning["reason"])
    for field in ("finding_sha256", "evidence_sha256", "review_sha256"):
        _hash(learning[field], field, optional=credit == 0)
    if credit and branch["independently_reviewed"] is not True:
        raise ValueError("positive learning requires independent review")
    if credit and validity["status"] != "valid" and learning["kind"] not in {"failure_diagnosis", "failure_repair"}:
        raise ValueError("invalid performance evidence supports only separately reviewed failure learning")
    exploration = _exact(item["exploration"], {"action", "reason", "allowance_id_sha256", "next_question_sha256", "followup_limit"}, "exploration")
    _reason(exploration["reason"])
    if exploration["action"] not in {"continue", "branch", "bounded_followup", "cooldown", "stop"}:
        raise ValueError("unknown exploration decision")
    bounded = exploration["action"] == "bounded_followup"
    if type(exploration["followup_limit"]) is not int or exploration["followup_limit"] != int(bounded):
        raise ValueError("bounded exploration permits exactly one follow-up")
    for field in ("allowance_id_sha256", "next_question_sha256"):
        _hash(exploration[field], field, optional=not bounded or field == "next_question_sha256")
        if not bounded and exploration[field] is not None:
            raise ValueError("unbounded/closed route cannot carry an allowance")
    if exploration["action"] in {"continue", "branch"} and validity["status"] != "valid":
        raise ValueError("invalid forecast cannot become a continuing predictor parent")
    if bounded and exploration["next_question_sha256"] == branch.get("question_digest_sha256"):
        raise ValueError("follow-up must address a distinct predeclared question")
    duplicate = credit > 0 and learning["finding_sha256"] in known_findings
    if validity["status"] == "valid" and (credit == 0 or duplicate) and exploration["action"] in {"continue", "branch"}:
        raise ValueError("zero-credit forecast requires a specifically bounded first follow-up")
    reuse = item["reuse"]
    if reuse is not None:
        reuse = _exact(reuse, {"finding_sha256", "status", "action_sha256", "evidence_sha256", "review_sha256", "benefit", "benefit_evidence_sha256"}, "reuse")
        _hash(reuse["finding_sha256"], "reused finding")
        _hash(reuse["action_sha256"], "reuse action")
        if reuse["finding_sha256"] not in known_findings:
            raise ValueError("reuse must refer to a previously accepted finding")
        if reuse["status"] not in {"proposed", "observed", "validated"} or reuse["benefit"] not in {"unmeasured", "validated"}:
            raise ValueError("reuse status or benefit classification changed")
        observed = reuse["status"] != "proposed"
        if observed and branch["independently_reviewed"] is not True:
            raise ValueError("observed reuse requires independent review of this result")
        for field in ("evidence_sha256", "review_sha256"):
            _hash(reuse[field], field, optional=not observed)
            if not observed and reuse[field] is not None:
                raise ValueError("proposed reuse is not observed evidence")
        benefit = reuse["benefit"] == "validated"
        _hash(reuse["benefit_evidence_sha256"], "reuse benefit", optional=not benefit)
        if benefit and reuse["status"] != "validated":
            raise ValueError("observed reuse alone is not a validated benefit or transfer")
        if not benefit and reuse["benefit_evidence_sha256"] is not None:
            raise ValueError("unmeasured reuse has no validated benefit receipt")
    output = copy.deepcopy(item)
    output["learning"].update(credit=0 if duplicate else credit, duplicate_finding=duplicate)
    return output


def validate_saved_checkpoint(value: object, branch: Mapping[str, Any]) -> dict:
    """Check archived normalized evidence, preserving its original dedup outcome."""
    item = copy.deepcopy(value)
    if not isinstance(item, dict) or not isinstance(item.get("learning"), dict):
        raise ValueError("saved checkpoint must be an object")
    learning = item["learning"]
    actual = learning.pop("credit", None)
    duplicate = learning.pop("duplicate_finding", None)
    if type(actual) is not int or type(duplicate) is not bool:
        raise ValueError("saved learning credit/dedup fields changed")
    known = set()
    if duplicate or item.get("reuse") is not None:
        if duplicate:
            known.add(learning.get("finding_sha256"))
        if item.get("reuse") is not None:
            known.add(item["reuse"].get("finding_sha256"))
    checked = assess_checkpoint(item, branch, known)
    if checked["learning"]["credit"] != actual or checked["learning"]["duplicate_finding"] != duplicate:
        raise ValueError("saved learning credit was inflated")
    return checked


def parent_eligibility(record: Mapping[str, Any], protocol_version: int) -> bool:
    """Pure admission of an original ranked record; never consult mutable state."""
    if type(protocol_version) is not int or protocol_version not in {1, 2, 3, 4}:
        raise ValueError("unsupported parent eligibility protocol")
    if record.get("route_action") == "batch_start":
        try:
            _hash(record.get("candidate_sha256"), "baseline candidate")
            if not isinstance(record.get("source_batch_id"), str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", record["source_batch_id"]):
                return False
        except ValueError:
            return False
        return (type(record.get("research_credit")) is int and record["research_credit"] == 0
                and record.get("research_outcome") == "baseline" and record.get("source_attempt_id") is None)
    if protocol_version < 4:
        credit, outcome, action = (record.get(k) for k in ("research_credit", "research_outcome", "route_action"))
        if type(credit) is not int:
            return False
        return ((credit == 2 and outcome == "support" and action == "continue") or
                (protocol_version == 3 and credit == 2 and outcome == "refute" and action == "branch") or
                (credit == 1 and outcome == "inconclusive" and action == "bounded_followup" and record.get("followups_remaining") == 1))
    assessment = record.get("learning_checkpoint")
    if not isinstance(assessment, dict) or assessment.get("schema") != SCHEMA:
        return False
    try:
        validate_saved_checkpoint(assessment, {
            "review_decision": assessment.get("prediction_decision"),
            "review_sha256": record.get("review_sha256"),
            "execution_outcome": record.get("execution_outcome"),
            "independently_reviewed": record.get("independently_reviewed"),
            "question_digest_sha256": record.get("question_digest_sha256"),
        })
    except (ValueError, TypeError, KeyError):
        return False
    validity, route = assessment.get("validity", {}), assessment.get("exploration", {})
    if validity.get("status") != "valid" or validity.get("leakage_detected") is not False:
        return False
    if route.get("action") in {"continue", "branch"}:
        return True
    return route.get("action") == "bounded_followup" and type(record.get("followups_remaining")) is int and record["followups_remaining"] == 1
