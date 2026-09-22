"""Trusted offline compiler for one exact Gate 1 public-trade request plan.

The Controller supplies only its frozen decision fields.  Trusted code resolves
the capability, a precommitted Train-only catalog, the deterministic sampling
rule, endpoint, query parameters, pagination, and hard execution envelope.
This module performs no network, provider, model, filesystem, or data-admission
operation.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from types import MappingProxyType

from market_rsi import digest
from supervisor_harness.p0_gate1_research_contract import (
    CAPABILITY_REGISTRY,
    EXACT_TRADE_SAMPLE_RULE,
    validate_and_compile,
)
from supervisor_harness.p0_gate1_sample_materializer import (
    CATALOG_SCHEMA,
    DATA_SCOPE,
    MATERIALIZATION_SCHEMA,
    RULE_ID,
    SOURCE_ID as EXECUTION_SOURCE_ID,
    TRAIN_ROLE,
    canonical_output as canonical_materialization_output,
    materialize,
)
from supervisor_harness.p0_gate1_trade_query import (
    FIXED_OFFSETS,
    HARD_MAX_ELAPSED_SECONDS,
    HARD_MAX_LIMIT,
    HARD_MAX_TOTAL_BYTES,
    INPUT_SCHEMA as TRADE_QUERY_INPUT_SCHEMA,
    SOURCE_ID as TRADE_QUERY_SOURCE_ID,
    build_bundle as build_trade_bundle,
)


BUNDLE_SCHEMA = "market_p0_gate1_compiled_plan_bundle_v1"
EXACT_MANIFEST_SCHEMA = "market_p0_gate1_exact_request_manifest_v1"
SCIENTIFIC_SOURCE_ID = "polymarket_official_trades"
OPERATION = "fetch_fixed_public_sample"
CAPABILITY_ID = "fixed_public_train_trade_request_plan_v1"
COMPILER_HANDLER_ID = "p0_gate1_plan_compiler.compile_exact_request_plan:v1"
MATERIALIZER_HANDLER_ID = "p0_gate1_sample_materializer.materialize:v1"
REQUEST_BUILDER_HANDLER_ID = "p0_gate1_trade_query.build_bundle:v1"
SOURCE_MAPPING_ID = "polymarket_official_trades_to_public_trade_endpoint_v1"
SYNTHETIC_CATALOG_COMMITMENT_ID = "gate1_synthetic_train_catalog_v1"

_EXACT_MAX_REQUESTS = 3 * len(FIXED_OFFSETS)
_EXACT_MAX_BYTES = HARD_MAX_TOTAL_BYTES
_EXACT_MAX_MINUTES = HARD_MAX_ELAPSED_SECONDS // 60

# A catalog hash is authority only when trusted code precommits it.  The sole
# initial entry is explicitly synthetic-canary-only.  A real public Train
# catalog remains unexecutable until its separately reviewed exact hash is
# added in a later version.
TRUSTED_CATALOG_COMMITMENTS = MappingProxyType({
    SYNTHETIC_CATALOG_COMMITMENT_ID: MappingProxyType({
        "catalog_id": "gate1-train-canary-catalog-v1",
        "catalog_file_sha256": (
            "33722e897d13213298c00009511e962cfae3b72464cc053345e183dc21a02068"),
        "catalog_schema": CATALOG_SCHEMA,
        "source_id": EXECUTION_SOURCE_ID,
        "data_scope": DATA_SCOPE,
        "evidence_scope": "synthetic_canary_only",
    }),
})

_EXPECTED_SAMPLE_CONTRACT = {
    "rule_id": RULE_ID,
    "kind": "frozen_train_catalog_first_middle_last",
    "catalog_schema": CATALOG_SCHEMA,
    "execution_source_id": EXECUTION_SOURCE_ID,
    "data_scope": DATA_SCOPE,
    "sample_count": 3,
    "sort_keys": ["game_date", "game_id"],
    "materializer_handler_id": MATERIALIZER_HANDLER_ID,
}
_EXPECTED_EXECUTION_CONTRACT = {
    "request_builder_handler_id": REQUEST_BUILDER_HANDLER_ID,
    "future_executor_handler_id": None,
    "endpoint_resolution": "trusted_trade_query_registry_only",
    "method": "GET",
    "page_limit": HARD_MAX_LIMIT,
    "offsets": list(FIXED_OFFSETS),
    "max_elapsed_seconds": HARD_MAX_ELAPSED_SECONDS,
    "redirects_allowed": False,
    "authentication_allowed": False,
    "paid_access_allowed": False,
    "write_operations_allowed": False,
    "network_execution_authorized": False,
}
_EXPECTED_CONSTRAINTS = {
    "max_requests": _EXACT_MAX_REQUESTS,
    "max_bytes": _EXACT_MAX_BYTES,
    "max_minutes": _EXACT_MAX_MINUTES,
    "max_provider_cost_usd": "0",
}


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field in trusted catalog")
        result[key] = value
    return result


def _trusted_catalog(catalog_json: bytes, commitment_id: str) -> tuple[dict, dict]:
    if not isinstance(commitment_id, str) or commitment_id not in TRUSTED_CATALOG_COMMITMENTS:
        raise ValueError("catalog is not in the trusted commitment registry")
    commitment = dict(TRUSTED_CATALOG_COMMITMENTS[commitment_id])
    if not isinstance(catalog_json, bytes):
        raise ValueError("trusted catalog must be exact bytes")
    actual_sha256 = hashlib.sha256(catalog_json).hexdigest()
    if actual_sha256 != commitment["catalog_file_sha256"]:
        raise ValueError("catalog bytes do not match the trusted commitment")

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant is forbidden: {value}")

    try:
        value = json.loads(catalog_json, object_pairs_hook=_unique_object,
                           parse_constant=reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("trusted catalog is not valid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("trusted catalog must be one JSON object")
    for field in ("catalog_id", "schema", "source_id", "data_scope"):
        expected_field = "catalog_schema" if field == "schema" else field
        if value.get(field) != commitment[expected_field]:
            raise ValueError("trusted catalog identity differs from commitment")
    return value, commitment


def _registered_capability(task: dict) -> dict:
    """Fail if mutable registry/task state differs from the reviewed chain."""
    try:
        registered = CAPABILITY_REGISTRY[SCIENTIFIC_SOURCE_ID][OPERATION]
    except KeyError as exc:
        raise ValueError("trusted trade capability is not registered") from exc
    if (registered.get("capability_id") != CAPABILITY_ID
            or registered.get("handler_id") != COMPILER_HANDLER_ID
            or registered.get("operation") != OPERATION
            or registered.get("allowed_question_ids")
            != ["2025_whole_season_trade_access"]
            or registered.get("sample_contracts")
            != {EXACT_TRADE_SAMPLE_RULE: _EXPECTED_SAMPLE_CONTRACT}
            or registered.get("execution_contract")
            != _EXPECTED_EXECUTION_CONTRACT
            or registered.get("constraints") != _EXPECTED_CONSTRAINTS):
        raise ValueError("trusted trade capability registry changed")
    expected_task_capability = {
        "capability_id": CAPABILITY_ID,
        "handler_id": COMPILER_HANDLER_ID,
        "source_id": SCIENTIFIC_SOURCE_ID,
        "operation": OPERATION,
        "sample_contract": deepcopy(_EXPECTED_SAMPLE_CONTRACT),
        "execution_contract": deepcopy(_EXPECTED_EXECUTION_CONTRACT),
        "executable": True,
    }
    if task.get("capability") != expected_task_capability:
        raise ValueError("compiled task capability differs from trusted registry")
    if task.get("bounds") != _EXPECTED_CONSTRAINTS:
        raise ValueError("compiled task bounds differ from trusted capability")
    return deepcopy(registered)


def _verified_materialization(catalog: dict, materialization: dict) -> tuple[bytes, str]:
    """Independently bind materialized inputs back to complete catalog rows."""
    if (not isinstance(materialization, dict)
            or materialization.get("schema") != MATERIALIZATION_SCHEMA
            or materialization.get("source_id") != EXECUTION_SOURCE_ID
            or materialization.get("data_scope") != DATA_SCOPE
            or materialization.get("rule_id") != RULE_ID
            or materialization.get("dev_or_final_exposed") is not False):
        raise ValueError("materialization identity or boundary changed")
    canonical_bytes, canonical_file_sha256 = canonical_materialization_output(
        materialization)
    request_plan_inputs = materialization.get("request_plan_inputs")
    if (not isinstance(request_plan_inputs, list)
            or len(request_plan_inputs) != 3
            or materialization.get("request_plan_inputs_sha256")
            != digest(request_plan_inputs)):
        raise ValueError("request-plan input commitment changed")

    rows = catalog.get("rows")
    if not isinstance(rows, list):
        raise ValueError("trusted catalog rows are missing")
    rows_by_id = {
        row.get("game_id"): row for row in rows if isinstance(row, dict)
    }
    if len(rows_by_id) != len(rows):
        raise ValueError("trusted catalog sample IDs are not unique")
    ordered = sorted(rows, key=lambda row: (row["game_date"], row["game_id"]))
    expected_rows = [ordered[0], ordered[len(ordered) // 2], ordered[-1]]
    expected_inputs = []
    for row in expected_rows:
        if row.get("split_role") != TRAIN_ROLE:
            raise ValueError("trusted compiler received Dev/Final catalog data")
        expected_inputs.append({
            "sample_id": row["game_id"],
            "condition_id": row["condition_id"],
            "asset_ids": list(row["asset_ids"]),
            "start_timestamp": row["start_timestamp"],
            "end_timestamp": row["end_timestamp"],
            "input_sha256": digest(row),
        })
    if request_plan_inputs != expected_inputs:
        raise ValueError("request-plan inputs do not match complete trusted catalog rows")
    expected_sample_ids = [row["game_id"] for row in expected_rows]
    expected_commitments = [
        {"sample_id": item["sample_id"],
         "input_sha256": item["input_sha256"]}
        for item in expected_inputs
    ]
    if (materialization.get("sample_ids") != expected_sample_ids
            or materialization.get("sample_commitments")
            != expected_commitments
            or materialization.get("selected_rows_sha256")
            != digest(expected_rows)):
        raise ValueError("materialized sample commitments changed")
    return canonical_bytes, canonical_file_sha256


def compile_exact_request_plan(
        decision: dict,
        packet: dict,
        catalog_json: bytes,
        catalog_commitment_id: str,
) -> dict:
    """Compile one decision and precommitted catalog into one exact manifest."""
    task = validate_and_compile(decision, packet)
    if (task.get("question_id") != "2025_whole_season_trade_access"
            or task.get("source", {}).get("source_id") != SCIENTIFIC_SOURCE_ID
            or task.get("requested_operations") != [OPERATION]
            or task.get("fixed_sample_rule") != EXACT_TRADE_SAMPLE_RULE):
        raise ValueError("task is not the reviewed exact trade investigation")
    _registered_capability(task)
    catalog, catalog_commitment = _trusted_catalog(
        catalog_json, catalog_commitment_id)
    materialization = materialize(
        catalog_json,
        catalog_commitment["catalog_file_sha256"],
        RULE_ID,
    )
    materialization_bytes, materialization_file_sha256 = (
        _verified_materialization(catalog, materialization))

    query_input = {
        "schema": TRADE_QUERY_INPUT_SCHEMA,
        "source_id": TRADE_QUERY_SOURCE_ID,
        "data_scope": DATA_SCOPE,
        "request_plan_inputs": deepcopy(
            materialization["request_plan_inputs"]),
        "limit": HARD_MAX_LIMIT,
        "offsets": list(FIXED_OFFSETS),
        "max_requests": _EXACT_MAX_REQUESTS,
        "max_total_bytes": _EXACT_MAX_BYTES,
        "max_elapsed_seconds": HARD_MAX_ELAPSED_SECONDS,
    }
    trade_bundle = build_trade_bundle(query_input)
    trade_manifest = trade_bundle["request_manifest"]
    if (trade_bundle.get("request_manifest_canonical_sha256")
            != digest(trade_manifest)):
        raise ValueError("trade request manifest commitment changed")

    exact_manifest = {
        "schema": EXACT_MANIFEST_SCHEMA,
        "investigation_id": task["investigation_id"],
        "question_id": task["question_id"],
        "operation": OPERATION,
        "capability_id": CAPABILITY_ID,
        "broker_task_canonical_sha256": digest(task),
        "source_mapping": {
            "mapping_id": SOURCE_MAPPING_ID,
            "controller_scientific_source_id": SCIENTIFIC_SOURCE_ID,
            "execution_source_registry_id": EXECUTION_SOURCE_ID,
        },
        "handler_chain": {
            "compiler_handler_id": COMPILER_HANDLER_ID,
            "materializer_handler_id": MATERIALIZER_HANDLER_ID,
            "request_builder_handler_id": REQUEST_BUILDER_HANDLER_ID,
            "future_executor_handler_id": None,
        },
        "catalog_commitment": {
            "commitment_id": catalog_commitment_id,
            **catalog_commitment,
        },
        "materialization_binding": {
            "schema": materialization["schema"],
            "rule_id": materialization["rule_id"],
            "materialization_sha256": materialization[
                "materialization_sha256"],
            "materialization_canonical_file_sha256": (
                materialization_file_sha256),
            "request_plan_inputs_sha256": materialization[
                "request_plan_inputs_sha256"],
            "sample_ids": list(materialization["sample_ids"]),
            "sample_commitments": deepcopy(
                materialization["sample_commitments"]),
        },
        "request_source": {
            "source_registry_id": trade_manifest["source_registry_id"],
            "endpoint": deepcopy(trade_manifest["endpoint"]),
        },
        "trade_builder_manifest_canonical_sha256": digest(trade_manifest),
        "selection_input_sha256": trade_manifest[
            "selection_input_sha256"],
        "request_count": trade_manifest["request_count"],
        "requests": deepcopy(trade_manifest["requests"]),
        "hard_budget": deepcopy(trade_manifest["hard_budget"]),
        "execution_policy": deepcopy(trade_manifest["execution_policy"]),
        "claim_boundaries": deepcopy(trade_manifest["claim_boundaries"]),
    }
    exact_manifest_sha256 = digest(exact_manifest)
    receipt_contract = deepcopy(trade_bundle["execution_receipt_contract"])
    receipt_contract["request_manifest_sha256"] = exact_manifest_sha256
    receipt_contract["request_manifest_schema"] = EXACT_MANIFEST_SCHEMA
    receipt_contract["trade_builder_manifest_sha256"] = digest(trade_manifest)

    return {
        "schema": BUNDLE_SCHEMA,
        "broker_task": task,
        "broker_task_canonical_sha256": digest(task),
        "materialization": materialization,
        "materialization_canonical_file_sha256": hashlib.sha256(
            materialization_bytes).hexdigest(),
        "exact_request_manifest": exact_manifest,
        "exact_request_manifest_canonical_sha256": exact_manifest_sha256,
        "execution_receipt_contract": receipt_contract,
        "execution_receipt_contract_canonical_sha256": digest(
            receipt_contract),
        "claim_boundaries": {
            "synthetic_canary_only": (
                catalog_commitment["evidence_scope"]
                == "synthetic_canary_only"),
            "network_requests_made": 0,
            "provider_calls_made": 0,
            "data_fetched": False,
            "dev_data_read": False,
            "final_data_read": False,
            "formal_data_admitted": False,
            "prediction_improvement_proven": False,
        },
    }
