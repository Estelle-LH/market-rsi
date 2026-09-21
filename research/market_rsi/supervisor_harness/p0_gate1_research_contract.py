"""Fail-closed contract for one Controller-selected Gate 1 investigation.

The model may choose among frozen questions and sources and set tighter bounds.
It cannot supply a URL, path, command, code, credential, evaluation row, or a
new operation.  Trusted code resolves the selected source and constructs the
task.  This module performs no fetch, model call, or execution.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json
import re

from supervisor_harness.build_p0_gate1_controller_packet import (
    RIGHTS_POLICY, SCHEMA as PACKET_SCHEMA,
)


DECISION_SCHEMA = "market_p0_gate1_controller_decision_v2"
TASK_SCHEMA = "market_p0_gate1_broker_task_v2"
OPERATIONS = frozenset({
    "inspect_official_documentation",
    "query_public_metadata",
    "fetch_fixed_public_sample",
    "verify_research_use_rights",
})
_IDENTIFIER = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,99}\Z")
_TEXT_FIELDS = (
    "hypothesis", "fixed_sample_rule", "expected_evidence",
    "stop_rule",
)
_FORBIDDEN_TEXT = (
    "api_key", "authorization", "bearer ", "password", "secret",
    "sealed_final", "route_dev", "subprocess", "shell", "sudo",
)


def _bounded_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonempty text")
    value = value.strip()
    if len(value.encode("utf-8")) > 1000:
        raise ValueError(f"{name} is oversized")
    lowered = value.lower()
    if any(token in lowered for token in _FORBIDDEN_TEXT):
        raise ValueError(f"{name} contains forbidden authority")
    return value


def _exact_decimal(value: object) -> Decimal:
    if not isinstance(value, str):
        raise ValueError("max_provider_cost_usd must be a decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("invalid provider cost") from exc
    if not parsed.is_finite() or parsed < 0:
        raise ValueError("invalid provider cost")
    return parsed


def validate_and_compile(decision: dict, packet: dict) -> dict:
    if not isinstance(packet, dict) or packet.get("schema") != PACKET_SCHEMA:
        raise ValueError("wrong Gate 1 packet")
    if packet.get("trusted_rights_policy") != RIGHTS_POLICY:
        raise ValueError("trusted rights policy changed or is missing")
    required = set(packet.get("required_decision_fields", []))
    if "schema" in required:
        raise ValueError("decision schema must be trusted protocol metadata")
    if (not isinstance(decision, dict)
            or set(decision) != required | {"schema"}):
        raise ValueError("decision fields differ from frozen contract")
    if decision.get("schema") != DECISION_SCHEMA:
        raise ValueError("wrong decision schema")
    investigation_id = decision.get("investigation_id")
    if not isinstance(investigation_id, str) or not _IDENTIFIER.fullmatch(investigation_id):
        raise ValueError("invalid investigation ID")
    if decision.get("question_id") not in packet["allowed_questions"]:
        raise ValueError("question is not allowlisted")
    sources = {item["source_id"]: item for item in packet["allowed_sources"]}
    if decision.get("source_id") not in sources:
        raise ValueError("source is not allowlisted")
    operations = decision.get("requested_operations")
    if (not isinstance(operations, list) or not operations
            or len(operations) != len(set(operations))
            or any(operation not in OPERATIONS for operation in operations)):
        raise ValueError("requested operations are invalid")
    limits = packet["hard_limits"]
    for field, ceiling in (("max_requests", limits["max_requests_ceiling"]),
                           ("max_bytes", limits["max_bytes_ceiling"]),
                           ("max_minutes", limits["max_minutes_ceiling"])):
        value = decision.get(field)
        if type(value) is not int or not 0 < value <= ceiling:
            raise ValueError(f"{field} exceeds frozen bound")
    proposed_cost = _exact_decimal(decision.get("max_provider_cost_usd"))
    if proposed_cost > _exact_decimal(limits["max_provider_cost_usd_ceiling"]):
        raise ValueError("provider cost exceeds frozen bound")
    text = {name: _bounded_text(decision.get(name), name) for name in _TEXT_FIELDS}
    source = sources[decision["source_id"]]
    return {
        "schema": TASK_SCHEMA,
        "investigation_id": investigation_id,
        "question_id": decision["question_id"],
        "source": source,
        **text,
        "rights_policy": RIGHTS_POLICY,
        "requested_operations": operations,
        "bounds": {
            "max_requests": decision["max_requests"],
            "max_bytes": decision["max_bytes"],
            "max_minutes": decision["max_minutes"],
            "max_provider_cost_usd": str(proposed_cost),
        },
        "execution_boundary": {
            "plan_only": True,
            "network_fetch_authorized": False,
            "purchase_authorized": False,
            "sealed_or_scored_data_authorized": False,
            "formal_admission_authorized": False,
        },
    }


def parse_unique_json(raw: str) -> dict:
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate decision field")
            value[key] = item
        return value

    if not isinstance(raw, str) or not raw or len(raw.encode("utf-8")) > 16 * 1024:
        raise ValueError("missing or oversized decision")
    value = json.loads(raw, object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise ValueError("decision must be one JSON object")
    return value
