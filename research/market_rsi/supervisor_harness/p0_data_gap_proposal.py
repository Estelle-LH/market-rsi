"""Archive an open-ended Controller data-gap proposal without executing it.

This contract is intentionally separate from the narrow executable Gate 1
allowlist. A new source or method can be proposed, but this module cannot
grant network, purchase, code-execution, data-admission, or scoring authority.
The caller must independently authenticate the auditor's input receipts.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re

from market_rsi import digest


GAP_SCHEMA = "market_p0_data_gap_report_v1"
PROPOSAL_SCHEMA = "market_p0_data_gap_proposal_v1"
ARCHIVE_SCHEMA = "market_p0_data_gap_proposal_archive_v1"
FEEDBACK_SCHEMA = "market_p0_data_gap_feedback_v1"
NEXT_INPUT_SCHEMA = "market_p0_data_gap_next_input_v1"
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}\Z")
PROPOSAL_KINDS = frozenset({
    "new_source", "new_mapping_method", "new_quality_test",
    "new_target_proposal",
})
FEEDBACK_OUTCOMES = frozenset({
    "rejected", "inconclusive", "usable_evidence_gained", "no_usable_gain",
})


def _keys(value: object, expected: set[str], name: str) -> dict:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{name} must have exact fields")
    return value


def _text(value: object, name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not value.strip() and not allow_empty):
        raise ValueError(f"{name} must be text")
    if len(value.encode("utf-8")) > 1000:
        raise ValueError(f"{name} is oversized")
    return value


def _hash(value: object, name: str) -> str:
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        raise ValueError(f"{name} must be a SHA-256 digest")
    return value


def _money(value: object, name: str, ceiling: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a decimal string")
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{name} is invalid") from exc
    if not amount.is_finite() or amount < 0 or amount > Decimal(ceiling):
        raise ValueError(f"{name} exceeds its bound")
    return value


def archive_proposal(gap: dict, proposal: dict) -> dict:
    """Keep a novel idea visible without promoting it to an executable task."""
    _keys(gap, {"schema", "gap_id", "evidence_sha256", "summary",
                "scope", "sealed_values_exposed"}, "gap")
    if gap["schema"] != GAP_SCHEMA or gap["scope"] != "public_or_opened_train":
        raise ValueError("gap has no permitted data scope")
    if gap["sealed_values_exposed"] is not False:
        raise ValueError("sealed values cannot enter Controller input")
    if not isinstance(gap["gap_id"], str) or not IDENTIFIER.fullmatch(gap["gap_id"]):
        raise ValueError("invalid gap ID")
    _hash(gap["evidence_sha256"], "gap evidence")
    _text(gap["summary"], "gap summary")

    _keys(proposal, {"schema", "proposal_id", "gap_sha256", "kind",
                     "hypothesis", "candidate_source", "method",
                     "fixed_sample_rule", "expected_evidence", "stop_rule",
                     "max_requests", "max_bytes", "max_minutes",
                     "max_provider_cost_usd"}, "proposal")
    if proposal["schema"] != PROPOSAL_SCHEMA:
        raise ValueError("wrong proposal schema")
    if (not isinstance(proposal["proposal_id"], str)
            or not IDENTIFIER.fullmatch(proposal["proposal_id"])):
        raise ValueError("invalid proposal ID")
    if proposal["gap_sha256"] != digest(gap):
        raise ValueError("proposal is not bound to the exact gap")
    if proposal["kind"] not in PROPOSAL_KINDS:
        raise ValueError("unsupported proposal kind")
    for name in ("hypothesis", "method", "fixed_sample_rule",
                 "expected_evidence", "stop_rule"):
        _text(proposal[name], name)
    _text(proposal["candidate_source"], "candidate source", allow_empty=True)
    if proposal["kind"] == "new_source" and not proposal["candidate_source"].strip():
        raise ValueError("new source proposal must name a candidate")
    for name, ceiling in (("max_requests", 20), ("max_bytes", 5_000_000),
                          ("max_minutes", 30)):
        value = proposal[name]
        if type(value) is not int or not 0 < value <= ceiling:
            raise ValueError(f"{name} exceeds proposal bound")
    _money(proposal["max_provider_cost_usd"], "provider cost", "0.05")
    return {
        "schema": ARCHIVE_SCHEMA,
        "gap_sha256": digest(gap),
        "gap": dict(gap),
        "evidence_sha256": gap["evidence_sha256"],
        "proposal_sha256": digest(proposal),
        "proposal": dict(proposal),
        "status": "review_required",
        "executable": False,
        "network_authorized": False,
        "purchase_authorized": False,
        "formal_data_admitted": False,
        "dev_or_final_access_authorized": False,
    }


def next_controller_input(archive: dict, feedback: dict) -> dict:
    """Bind a trusted audit result to the next turn, without admitting data."""
    _keys(archive, {"schema", "gap_sha256", "gap", "evidence_sha256",
                    "proposal_sha256", "proposal", "status", "executable",
                    "network_authorized", "purchase_authorized",
                    "formal_data_admitted", "dev_or_final_access_authorized"},
          "archive")
    if (archive.get("schema") != ARCHIVE_SCHEMA
            or archive.get("status") != "review_required"
            or archive.get("executable") is not False
            or archive.get("network_authorized") is not False
            or archive.get("purchase_authorized") is not False
            or archive.get("formal_data_admitted") is not False
            or archive.get("dev_or_final_access_authorized") is not False
            or not isinstance(archive.get("gap"), dict)
            or archive.get("gap_sha256") != digest(archive["gap"])
            or not isinstance(archive.get("proposal"), dict)
            or archive.get("proposal_sha256") != digest(archive["proposal"])):
        raise ValueError("proposal archive is not intact")
    _hash(archive["gap_sha256"], "archived gap")
    _hash(archive["evidence_sha256"], "archived gap evidence")
    if archive_proposal(archive["gap"], archive["proposal"]) != archive:
        raise ValueError("proposal archive differs from trusted compiler output")
    _keys(feedback, {"schema", "proposal_sha256", "auditor_receipt_sha256",
                     "outcome", "summary", "actual_cost_usd",
                     "sealed_values_exposed"}, "feedback")
    if feedback["schema"] != FEEDBACK_SCHEMA:
        raise ValueError("wrong feedback schema")
    if (feedback["proposal_sha256"] != archive["proposal_sha256"]
            or feedback["outcome"] not in FEEDBACK_OUTCOMES
            or feedback["sealed_values_exposed"] is not False):
        raise ValueError("feedback is unbound or exposes sealed values")
    _hash(feedback["auditor_receipt_sha256"], "feedback auditor receipt")
    _text(feedback["summary"], "feedback summary")
    _money(feedback["actual_cost_usd"], "actual cost",
           archive["proposal"]["max_provider_cost_usd"])
    return {
        "schema": NEXT_INPUT_SCHEMA,
        "previous_gap_sha256": archive["gap_sha256"],
        "previous_gap": dict(archive["gap"]),
        "previous_proposal_sha256": archive["proposal_sha256"],
        "previous_proposal": dict(archive["proposal"]),
        "feedback_sha256": digest(feedback),
        "feedback": dict(feedback),
        "formal_data_admitted": False,
        "next_controller_decision_required": True,
    }
