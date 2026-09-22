"""Fail-closed contract for one Controller-selected Gate 1 investigation.

The model may choose among frozen questions and sources and set tighter bounds.
It cannot supply a URL, path, command, code, credential, evaluation row, or a
new operation.  Trusted code resolves the selected source and constructs the
task.  This module performs no fetch, model call, or execution.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
import json
import re

from supervisor_harness.build_p0_gate1_controller_packet import (
    ALLOWED_QUESTIONS,
    DOCUMENT_SAMPLE_RULES,
    EXECUTABLE_DOCUMENTATION_CHOICES,
    RELEASE_SAMPLE_RULES,
    RIGHTS_POLICY,
    SCHEMA as PACKET_SCHEMA,
    SHORT_BOUNDED_CHOICES,
    SOURCE_REGISTRY,
)
from supervisor_harness.p0_gate1_sample_materializer import (
    CATALOG_SCHEMA as TRADE_CATALOG_SCHEMA,
    DATA_SCOPE as TRADE_DATA_SCOPE,
    RULE_ID as TRADE_SAMPLE_RULE_ID,
    SOURCE_ID as TRADE_EXECUTION_SOURCE_ID,
)
from supervisor_harness.p0_gate1_trade_query import (
    FIXED_OFFSETS as TRADE_FIXED_OFFSETS,
    HARD_MAX_ELAPSED_SECONDS as TRADE_MAX_ELAPSED_SECONDS,
    HARD_MAX_LIMIT as TRADE_PAGE_LIMIT,
    HARD_MAX_TOTAL_BYTES as TRADE_MAX_TOTAL_BYTES,
)


DECISION_SCHEMA = "market_p0_gate1_controller_decision_v2"
TASK_SCHEMA = "market_p0_gate1_broker_task_v3"
FIELD_PROVENANCE_SCHEMA = "market_p0_gate1_short_choice_provenance_v1"
EXACT_TRADE_SAMPLE_RULE = (
    "Select the first, middle, and last games by game_date and game_id "
    "from the frozen public Train catalog."
)

# Immutable-at-import snapshots keep a packet that shares nested objects with
# its builder from mutating the authority against which it is checked.
_TRUSTED_SOURCE_REGISTRY = tuple(deepcopy(SOURCE_REGISTRY))
_TRUSTED_RIGHTS_POLICY = deepcopy(RIGHTS_POLICY)
_TRUSTED_SHORT_CHOICES = deepcopy(SHORT_BOUNDED_CHOICES)
_TRUSTED_HARD_LIMITS = {
    "choose_exactly_one_question": True,
    "choose_exactly_one_source": True,
    "max_requests_ceiling": 20,
    "max_bytes_ceiling": 5_000_000,
    "max_minutes_ceiling": 30,
    "max_provider_cost_usd_ceiling": "0.05",
    "purchase_allowed": False,
    "sealed_or_scored_rows_allowed": False,
    "benchmark_prompts_or_outcomes_allowed": False,
    "source_write_allowed": False,
    "silent_retry_allowed": False,
    "formal_admission_from_this_decision": False,
}

# Keep the known vocabulary separate from executable operations.  The
# Controller tool schema imports OPERATIONS, so it must expose only handlers
# that exist now, rather than every operation we may eventually implement.
KNOWN_OPERATIONS = frozenset({
    "inspect_official_documentation",
    "query_public_metadata",
    "fetch_fixed_public_sample",
    "verify_research_use_rights",
})

# The model chooses the scientific content and a bounded execution request.
# It never authors the protocol schema, resolved source record, capability
# handler, rights policy, or execution boundary.
CONTROLLER_SCIENTIFIC_FIELDS = frozenset({
    "question_id", "hypothesis", "fixed_sample_rule", "expected_evidence",
    "stop_rule",
})
CONTROLLER_EXECUTION_FIELDS = frozenset({
    "source_id", "requested_operations", "max_requests", "max_bytes",
    "max_minutes", "max_provider_cost_usd",
})
CONTROLLER_METADATA_FIELDS = frozenset({"investigation_id"})
CONTROLLER_DECISION_FIELDS = (
    CONTROLLER_SCIENTIFIC_FIELDS
    | CONTROLLER_EXECUTION_FIELDS
    | CONTROLLER_METADATA_FIELDS
)
TRUSTED_TASK_FIELDS = frozenset({
    "schema", "source", "capability", "rights_policy", "field_authority",
    "execution_boundary",
})

def _single_document_sample_contract() -> dict:
    return {
        "rule_id": "single_registry_document_v1",
        "kind": "single_trusted_registry_document",
        "document_count": 1,
        "source_resolution": "exact_trusted_source_registry_record",
    }


_DOCUMENT_SAMPLE_CONTRACTS = {
    rule: _single_document_sample_contract()
    for rule in DOCUMENT_SAMPLE_RULES
}
_RELEASE_SAMPLE_CONTRACTS = {
    rule: _single_document_sample_contract()
    for rule in RELEASE_SAMPLE_RULES
}


def _document_capability(sample_contracts: dict[str, dict]) -> dict:
    return {
        "capability_id": "single_registry_document_snapshot_v1",
        "handler_id": "p0_gate1_public_fetch.fetch_snapshot:v1",
        "operation": "inspect_official_documentation",
        "sample_contracts": deepcopy(sample_contracts),
        "constraints": {
            "max_requests": 1,
            "max_provider_cost_usd": "0",
        },
    }


def _fixed_public_trade_capability() -> dict:
    """Describe the one tested materializer -> request-builder chain.

    These values are trusted code, not defaults that the Controller may
    override.  The Controller can request this exact operation and exact
    sample rule only by also accepting the complete fixed execution envelope.
    """
    return {
        "capability_id": "fixed_public_train_trade_request_plan_v1",
        "handler_id": "p0_gate1_plan_compiler.compile_exact_request_plan:v1",
        "operation": "fetch_fixed_public_sample",
        "allowed_question_ids": ["2025_whole_season_trade_access"],
        "sample_contracts": {
            EXACT_TRADE_SAMPLE_RULE: {
                "rule_id": TRADE_SAMPLE_RULE_ID,
                "kind": "frozen_train_catalog_first_middle_last",
                "catalog_schema": TRADE_CATALOG_SCHEMA,
                "execution_source_id": TRADE_EXECUTION_SOURCE_ID,
                "data_scope": TRADE_DATA_SCOPE,
                "sample_count": 3,
                "sort_keys": ["game_date", "game_id"],
                "materializer_handler_id": (
                    "p0_gate1_sample_materializer.materialize:v1"),
            },
        },
        "execution_contract": {
            "request_builder_handler_id": (
                "p0_gate1_trade_query.build_bundle:v1"),
            "future_executor_handler_id": None,
            "endpoint_resolution": "trusted_trade_query_registry_only",
            "method": "GET",
            "page_limit": TRADE_PAGE_LIMIT,
            "offsets": list(TRADE_FIXED_OFFSETS),
            "max_elapsed_seconds": TRADE_MAX_ELAPSED_SECONDS,
            "redirects_allowed": False,
            "authentication_allowed": False,
            "paid_access_allowed": False,
            "write_operations_allowed": False,
            "network_execution_authorized": False,
        },
        "constraints": {
            "max_requests": 3 * len(TRADE_FIXED_OFFSETS),
            "max_bytes": TRADE_MAX_TOTAL_BYTES,
            "max_minutes": TRADE_MAX_ELAPSED_SECONDS // 60,
            "max_provider_cost_usd": "0",
        },
    }


# Adding a name to KNOWN_OPERATIONS does not make it executable.  A future
# runner (for example, a trade-query runner) becomes selectable only after its
# exact source/operation/sample contract and tested handler_id are registered
# here by trusted code.
CAPABILITY_REGISTRY = {
    "polymarket_official_market_data": {
        "inspect_official_documentation":
            _document_capability(_DOCUMENT_SAMPLE_CONTRACTS),
    },
    "polymarket_official_trades": {
        "inspect_official_documentation":
            _document_capability(_DOCUMENT_SAMPLE_CONTRACTS),
        "fetch_fixed_public_sample": _fixed_public_trade_capability(),
    },
    "kalshi_official_historical_data": {
        "inspect_official_documentation":
            _document_capability(_DOCUMENT_SAMPLE_CONTRACTS),
    },
    "nflverse_official_pbp_releases": {
        "inspect_official_documentation":
            _document_capability(_RELEASE_SAMPLE_CONTRACTS),
    },
}
IMPLEMENTED_OPERATIONS = frozenset(
    operation
    for capabilities in CAPABILITY_REGISTRY.values()
    for operation in capabilities
)
# Backwards-compatible name imported by the Controller adapter's tool schema.
OPERATIONS = IMPLEMENTED_OPERATIONS
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


def short_choice_provenance(choice_id: str, claim_id: str) -> dict:
    if (not isinstance(claim_id, str) or not _IDENTIFIER.fullmatch(claim_id)
            or not isinstance(choice_id, str)
            or choice_id not in {item["choice_id"] for item in _TRUSTED_SHORT_CHOICES}):
        raise ValueError("unknown short choice or invalid run claim")
    return {
        "schema": FIELD_PROVENANCE_SCHEMA,
        "bounded_choice_id": choice_id,
        "run_claim_id": claim_id,
        "controller_authored": [
            "choice_id", "question_id", "hypothesis",
            "expected_evidence", "stop_rule",
        ],
        "trusted_derived_from_choice": [
            "source_id", "requested_operations", "fixed_sample_rule",
            "max_requests", "max_bytes", "max_minutes",
            "max_provider_cost_usd",
        ],
        "trusted_derived_from_claim": ["investigation_id"],
        "trusted_protocol": ["schema", "source", "capability", "rights_policy",
                             "execution_boundary"],
    }


def validate_and_compile(decision: dict, packet: dict, *,
                         field_provenance: dict | None = None) -> dict:
    if not isinstance(packet, dict) or packet.get("schema") != PACKET_SCHEMA:
        raise ValueError("wrong Gate 1 packet")
    if packet.get("trusted_rights_policy") != _TRUSTED_RIGHTS_POLICY:
        raise ValueError("trusted rights policy changed or is missing")
    if (packet.get("allowed_questions") != list(ALLOWED_QUESTIONS)
            or packet.get("allowed_sources") != list(_TRUSTED_SOURCE_REGISTRY)):
        raise ValueError("trusted question or source registry changed")
    if packet.get("hard_limits") != _TRUSTED_HARD_LIMITS:
        raise ValueError("trusted hard limits changed or are missing")
    boundary = packet.get("current_execution_boundary")
    if (not isinstance(boundary, dict)
            or packet.get("trusted_bounded_choices") != _TRUSTED_SHORT_CHOICES
            or packet.get("required_bounded_submission_fields") != [
                "choice_id", "question_id", "hypothesis",
                "expected_evidence", "stop_rule"]):
        raise ValueError("trusted bounded choices changed or are missing")
    required_fields = packet.get("required_decision_fields")
    if (not isinstance(required_fields, list)
            or len(required_fields) != len(CONTROLLER_DECISION_FIELDS)
            or set(required_fields) != CONTROLLER_DECISION_FIELDS):
        raise ValueError("Controller field contract changed")
    required = set(required_fields)
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
    sources = {item["source_id"]: item
               for item in _TRUSTED_SOURCE_REGISTRY}
    if decision.get("source_id") not in sources:
        raise ValueError("source is not allowlisted")
    operations = decision.get("requested_operations")
    if (not isinstance(operations, list) or not operations
            or len(operations) != len(set(operations))
            or any(operation not in KNOWN_OPERATIONS for operation in operations)):
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
    source = deepcopy(sources[decision["source_id"]])
    source_capabilities = CAPABILITY_REGISTRY.get(decision["source_id"], {})
    if len(operations) != 1 or operations[0] not in source_capabilities:
        raise ValueError("source and operation have no executable capability")
    registered = source_capabilities[operations[0]]
    allowed_question_ids = registered.get("allowed_question_ids")
    if (allowed_question_ids is not None
            and decision["question_id"] not in allowed_question_ids):
        raise ValueError("question has no executable source capability")
    sample_contract = registered["sample_contracts"].get(
        text["fixed_sample_rule"])
    if sample_contract is None:
        raise ValueError("sample rule is not executable for source and operation")
    constraints = registered["constraints"]
    for field in ("max_requests", "max_bytes", "max_minutes"):
        if field in constraints and decision[field] != constraints[field]:
            raise ValueError("requested bounds are not executable by capability")
    if proposed_cost != _exact_decimal(constraints["max_provider_cost_usd"]):
        raise ValueError("requested bounds are not executable by capability")
    if field_provenance is not None:
        if (not isinstance(field_provenance, dict)
                or field_provenance != short_choice_provenance(
                    field_provenance.get("bounded_choice_id"),
                    field_provenance.get("run_claim_id"))):
            raise ValueError("short-choice field provenance changed")
        choice = next(item for item in _TRUSTED_SHORT_CHOICES
                      if item["choice_id"] == field_provenance["bounded_choice_id"])
        if (decision["investigation_id"] != field_provenance["run_claim_id"]
                or decision["source_id"] != choice["source_id"]
                or operations != [choice["operation"]]
                or text["fixed_sample_rule"] != choice["fixed_sample_rule"]
                or any(decision[name] != choice["derived_bounds"][name]
                       for name in ("max_requests", "max_bytes", "max_minutes"))
                or proposed_cost != _exact_decimal(
                    choice["derived_bounds"]["max_provider_cost_usd"])):
            raise ValueError("expanded decision differs from trusted choice or claim")
    capability = {
        "capability_id": registered["capability_id"],
        "handler_id": registered["handler_id"],
        "source_id": decision["source_id"],
        "operation": operations[0],
        "sample_contract": deepcopy(sample_contract),
        "executable": True,
    }
    if "execution_contract" in registered:
        capability["execution_contract"] = deepcopy(
            registered["execution_contract"])
    task = {
        "schema": TASK_SCHEMA,
        "investigation_id": investigation_id,
        "question_id": decision["question_id"],
        "source": source,
        **text,
        "rights_policy": deepcopy(_TRUSTED_RIGHTS_POLICY),
        "requested_operations": list(operations),
        "capability": capability,
        "bounds": {
            "max_requests": decision["max_requests"],
            "max_bytes": decision["max_bytes"],
            "max_minutes": decision["max_minutes"],
            "max_provider_cost_usd": str(proposed_cost),
        },
        "field_authority": {
            "controller_scientific": sorted(CONTROLLER_SCIENTIFIC_FIELDS),
            "controller_execution_request": sorted(
                CONTROLLER_EXECUTION_FIELDS),
            "controller_metadata": sorted(CONTROLLER_METADATA_FIELDS),
            "trusted": sorted(TRUSTED_TASK_FIELDS),
        },
        "execution_boundary": {
            "plan_only": True,
            "network_fetch_authorized": False,
            "purchase_authorized": False,
            "sealed_or_scored_data_authorized": False,
            "formal_admission_authorized": False,
        },
    }
    if field_provenance is not None:
        task["field_authority"] = {
            "controller_scientific": ["question_id", "hypothesis",
                                      "expected_evidence", "stop_rule"],
            "controller_bounded_choice": ["choice_id"],
            "trusted_derived_from_choice": field_provenance[
                "trusted_derived_from_choice"],
            "trusted_derived_from_claim": ["investigation_id"],
            "trusted": sorted(TRUSTED_TASK_FIELDS),
        }
        task["field_provenance"] = deepcopy(field_provenance)
    return task


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
