"""Offline builder for a strictly bounded Polymarket Gate 1 trade query.

This module deliberately has no HTTP transport.  It validates a public Train
query envelope, resolves the endpoint from trusted code, and emits an exact
request manifest plus the receipt contract a later, separately authorized
executor must satisfy.  Selection hashes are checked against complete rows in
a precommitted catalog; the projected selection alone cannot prove provenance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from types import MappingProxyType
from urllib.parse import urlencode, urlsplit, urlunsplit

from market_rsi import canonical, digest
from supervisor_harness.p0_gate1_sample_materializer import (
    CATALOG_SCHEMA, DATA_SCOPE, RULE_ID, materialize,
)


INPUT_SCHEMA = "market_p0_gate1_trade_query_input_v1"
MANIFEST_SCHEMA = "market_p0_gate1_trade_request_manifest_v1"
RECEIPT_CONTRACT_SCHEMA = "market_p0_gate1_trade_receipt_contract_v1"
EXECUTION_RECEIPT_SCHEMA = "market_p0_gate1_trade_execution_receipt_v1"
BUILD_RECEIPT_SCHEMA = "market_p0_gate1_trade_query_build_receipt_v1"

SOURCE_ID = "polymarket_public_trades_v1"
PUBLIC_TRAIN_SCOPE = "public_train_only"
HARD_MAX_REQUESTS = 6
HARD_MAX_TOTAL_BYTES = 2_000_000
HARD_MAX_ELAPSED_SECONDS = 15 * 60
HARD_MAX_LIMIT = 100
FIXED_OFFSETS = (0, 100)
SYNTHETIC_CATALOG_COMMITMENT_ID = "gate1_synthetic_train_catalog_v1"

# The sole admitted catalog is a synthetic offline canary.  A real Train
# catalog needs its own reviewed exact-byte commitment before use.
TRUSTED_CATALOG_COMMITMENTS = MappingProxyType({
    SYNTHETIC_CATALOG_COMMITMENT_ID: MappingProxyType({
        "catalog_id": "gate1-train-canary-catalog-v1",
        "catalog_file_sha256": (
            "33722e897d13213298c00009511e962cfae3b72464cc053345e183dc21a02068"),
        "catalog_schema": CATALOG_SCHEMA,
        "source_id": SOURCE_ID,
        "data_scope": DATA_SCOPE,
        "evidence_scope": "synthetic_canary_only",
    }),
})

_ENDPOINTS = MappingProxyType({
    SOURCE_ID: MappingProxyType({
        "scheme": "https",
        "host": "data-api.polymarket.com",
        "path": "/trades",
        "method": "GET",
    }),
})
_TOP_LEVEL_FIELDS = frozenset({
    "schema", "source_id", "data_scope", "request_plan_inputs", "limit",
    "offsets", "max_requests", "max_total_bytes", "max_elapsed_seconds",
})
_SELECTION_FIELDS = frozenset({
    "sample_id", "condition_id", "asset_ids", "start_timestamp",
    "end_timestamp", "input_sha256",
})
_QUERY_FIELDS = ("market", "limit", "offset", "start", "end", "takerOnly")
_SAMPLE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}\Z")
_CONDITION_ID = re.compile(r"0x[0-9a-f]{64}\Z")
_ASSET_ID = re.compile(r"[1-9][0-9]{0,99}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _positive_int(value: object, name: str, ceiling: int | None = None) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    if ceiling is not None and value > ceiling:
        raise ValueError(f"{name} exceeds its hard ceiling")
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field in trusted catalog")
        result[key] = value
    return result


def trusted_catalog(catalog_json: bytes, commitment_id: str) -> tuple[dict, dict]:
    """Resolve exact catalog bytes against a code-owned commitment."""
    if (not isinstance(commitment_id, str)
            or commitment_id not in TRUSTED_CATALOG_COMMITMENTS):
        raise ValueError("catalog is not in the trusted commitment registry")
    commitment = dict(TRUSTED_CATALOG_COMMITMENTS[commitment_id])
    if not isinstance(catalog_json, bytes):
        raise ValueError("trusted catalog must be exact bytes")
    if hashlib.sha256(catalog_json).hexdigest() != commitment["catalog_file_sha256"]:
        raise ValueError("catalog bytes do not match the trusted commitment")

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant is forbidden: {value}")

    try:
        catalog = json.loads(catalog_json, object_pairs_hook=_unique_object,
                             parse_constant=reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("trusted catalog is not valid JSON") from exc
    if not isinstance(catalog, dict):
        raise ValueError("trusted catalog must be one JSON object")
    for field in ("catalog_id", "schema", "source_id", "data_scope"):
        expected_field = "catalog_schema" if field == "schema" else field
        if catalog.get(field) != commitment[expected_field]:
            raise ValueError("trusted catalog identity differs from commitment")
    return catalog, commitment


def _catalog_binding(catalog_json: bytes | None,
                     catalog_commitment_id: str | None) -> tuple[dict, dict, dict]:
    if catalog_json is None and catalog_commitment_id is None:
        # Preserve the existing direct offline fixture path.  It resolves
        # only this code-owned synthetic commitment and grants no fetch.
        from supervisor_harness.p0_gate1_executable_plan_canary_fixtures import (
            frozen_catalog_bytes,
        )
        catalog_json = frozen_catalog_bytes()
        catalog_commitment_id = SYNTHETIC_CATALOG_COMMITMENT_ID
    elif catalog_json is None or catalog_commitment_id is None:
        raise ValueError("catalog bytes and trusted commitment ID are both required")
    catalog, commitment = trusted_catalog(catalog_json, catalog_commitment_id)
    materialization = materialize(catalog_json, commitment["catalog_file_sha256"],
                                  RULE_ID)
    return catalog, commitment, materialization


def _validate_selection(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != _SELECTION_FIELDS:
        raise ValueError("request-plan input fields differ from the frozen schema")
    sample_id = value.get("sample_id")
    condition_id = value.get("condition_id")
    asset_ids = value.get("asset_ids")
    input_sha256 = value.get("input_sha256")
    if not isinstance(sample_id, str) or not _SAMPLE_ID.fullmatch(sample_id):
        raise ValueError("unsafe sample ID")
    if not isinstance(condition_id, str) or not _CONDITION_ID.fullmatch(condition_id):
        raise ValueError("condition ID must be a canonical 32-byte hex value")
    if (not isinstance(asset_ids, list) or not 1 <= len(asset_ids) <= 2
            or not all(isinstance(item, str) and _ASSET_ID.fullmatch(item)
                       for item in asset_ids)
            or len(set(asset_ids)) != len(asset_ids)):
        raise ValueError("asset IDs must be one or two unique canonical decimal strings")
    start = _positive_int(value.get("start_timestamp"), "start_timestamp")
    end = _positive_int(value.get("end_timestamp"), "end_timestamp")
    if start >= end:
        raise ValueError("trade window must have start_timestamp < end_timestamp")
    if not isinstance(input_sha256, str) or not _SHA256.fullmatch(input_sha256):
        raise ValueError("input_sha256 must be a lowercase SHA-256 digest")
    return {
        "sample_id": sample_id,
        "condition_id": condition_id,
        "asset_ids": list(asset_ids),
        "start_timestamp": start,
        "end_timestamp": end,
        "input_sha256": input_sha256,
    }


def validate_input(value: object, *, catalog_json: bytes | None = None,
                   catalog_commitment_id: str | None = None) -> dict:
    """Validate a query against complete rows in a precommitted catalog."""
    if not isinstance(value, dict) or set(value) != _TOP_LEVEL_FIELDS:
        raise ValueError("trade-query input fields differ from the frozen schema")
    if value.get("schema") != INPUT_SCHEMA:
        raise ValueError("wrong trade-query input schema")
    if value.get("source_id") != SOURCE_ID:
        raise ValueError("trade source is not in the trusted registry")
    if value.get("data_scope") != PUBLIC_TRAIN_SCOPE:
        raise ValueError("only fixed public Train inputs are allowed")
    limit = _positive_int(value.get("limit"), "limit", HARD_MAX_LIMIT)
    if limit != HARD_MAX_LIMIT:
        raise ValueError("limit must equal 100 for fixed offsets [0, 100]")
    offsets = value.get("offsets")
    if (not isinstance(offsets, list) or tuple(offsets) != FIXED_OFFSETS
            or any(type(item) is not int for item in offsets)):
        raise ValueError("offsets must be exactly [0, 100]")
    max_requests = _positive_int(
        value.get("max_requests"), "max_requests", HARD_MAX_REQUESTS)
    max_total_bytes = _positive_int(
        value.get("max_total_bytes"), "max_total_bytes", HARD_MAX_TOTAL_BYTES)
    max_elapsed_seconds = _positive_int(
        value.get("max_elapsed_seconds"), "max_elapsed_seconds",
        HARD_MAX_ELAPSED_SECONDS)
    raw_selections = value.get("request_plan_inputs")
    if not isinstance(raw_selections, list) or not raw_selections:
        raise ValueError("at least one fixed request-plan input is required")
    selections = [_validate_selection(item) for item in raw_selections]
    request_count = len(selections) * len(FIXED_OFFSETS)
    if request_count > max_requests:
        raise ValueError("fixed pages exceed the admitted request budget")
    sample_ids = [item["sample_id"] for item in selections]
    conditions = [item["condition_id"] for item in selections]
    assets = [asset for item in selections for asset in item["asset_ids"]]
    if len(set(sample_ids)) != len(sample_ids):
        raise ValueError("duplicate sample ID")
    if len(set(conditions)) != len(conditions):
        raise ValueError("duplicate condition ID")
    if len(set(assets)) != len(assets):
        raise ValueError("asset IDs must not cross fixed market selections")
    catalog, _, materialization = _catalog_binding(
        catalog_json, catalog_commitment_id)
    ordered = sorted(catalog["rows"],
                     key=lambda row: (row["game_date"], row["game_id"]))
    selected_rows = [ordered[0], ordered[len(ordered) // 2], ordered[-1]]
    expected = [{
        "sample_id": row["game_id"],
        "condition_id": row["condition_id"],
        "asset_ids": list(row["asset_ids"]),
        "start_timestamp": row["start_timestamp"],
        "end_timestamp": row["end_timestamp"],
        "input_sha256": digest(row),
    } for row in selected_rows]
    if (materialization["request_plan_inputs"] != expected
            or selections != expected):
        raise ValueError("selections do not match complete trusted catalog rows")
    return {
        "schema": INPUT_SCHEMA,
        "source_id": SOURCE_ID,
        "data_scope": PUBLIC_TRAIN_SCOPE,
        "request_plan_inputs": selections,
        "limit": limit,
        "offsets": list(FIXED_OFFSETS),
        "max_requests": max_requests,
        "max_total_bytes": max_total_bytes,
        "max_elapsed_seconds": max_elapsed_seconds,
    }


def _request_url(endpoint: dict, query: dict) -> str:
    pairs = [(name, query[name]) for name in _QUERY_FIELDS]
    url = urlunsplit((endpoint["scheme"], endpoint["host"], endpoint["path"],
                      urlencode(pairs), ""))
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname != endpoint["host"]
            or parsed.netloc != endpoint["host"] or parsed.path != endpoint["path"]
            or parsed.fragment):
        raise ValueError("generated URL escaped the trusted HTTPS endpoint")
    return url


def build_request_manifest(value: object, *, catalog_json: bytes | None = None,
                           catalog_commitment_id: str | None = None) -> dict:
    """Build the exact future GET list without performing any I/O."""
    validated = validate_input(
        value, catalog_json=catalog_json,
        catalog_commitment_id=catalog_commitment_id)
    endpoint = dict(_ENDPOINTS[validated["source_id"]])
    requests = []
    for selection in validated["request_plan_inputs"]:
        for offset in FIXED_OFFSETS:
            query = {
                "market": selection["condition_id"],
                "limit": validated["limit"],
                "offset": offset,
                "start": selection["start_timestamp"],
                "end": selection["end_timestamp"],
                "takerOnly": "true",
            }
            url = _request_url(endpoint, query)
            requests.append({
                "request_id": f'{selection["sample_id"]}-offset-{offset}',
                "sample_id": selection["sample_id"],
                "selection_input_sha256": selection["input_sha256"],
                "method": endpoint["method"],
                "url": url,
                "url_sha256": hashlib.sha256(url.encode("utf-8")).hexdigest(),
                "headers": {
                    "Accept": "application/json",
                    "User-Agent": "MarketRSI-Gate1-Public-Trade/1.0",
                },
                "follow_redirects": False,
                "query": query,
                "expected_response_scope": {
                    "condition_id": selection["condition_id"],
                    "asset_ids": list(selection["asset_ids"]),
                    "start_timestamp": selection["start_timestamp"],
                    "end_timestamp": selection["end_timestamp"],
                },
            })
    return {
        "schema": MANIFEST_SCHEMA,
        "source_registry_id": validated["source_id"],
        "endpoint": endpoint,
        "data_scope": PUBLIC_TRAIN_SCOPE,
        "selection_input_sha256": digest(validated),
        "request_count": len(requests),
        "requests": requests,
        "hard_budget": {
            "max_requests": validated["max_requests"],
            "max_total_response_bytes": validated["max_total_bytes"],
            "max_elapsed_seconds": validated["max_elapsed_seconds"],
        },
        "execution_policy": {
            "network_execution_authorized": False,
            "https_only": True,
            "trusted_registry_only": True,
            "redirects_allowed": False,
            "authentication_allowed": False,
            "paid_access_allowed": False,
            "write_operations_allowed": False,
            "silent_retries_allowed": False,
        },
        "claim_boundaries": {
            "data_fetched": False,
            "dev_data_read": False,
            "final_data_read": False,
            "formal_data_admitted": False,
            "prediction_improvement_proven": False,
        },
    }


def build_receipt_contract(manifest: dict, *, builder_input: object,
                           catalog_json: bytes | None = None,
                           catalog_commitment_id: str | None = None) -> dict:
    """Bind a receipt only to a freshly rebuilt trusted request manifest."""
    expected = build_request_manifest(
        builder_input, catalog_json=catalog_json,
        catalog_commitment_id=catalog_commitment_id)
    if type(manifest) is not dict or canonical(manifest) != canonical(expected):
        raise ValueError("trade request manifest differs from trusted builder output")
    manifest = expected
    return {
        "schema": RECEIPT_CONTRACT_SCHEMA,
        "execution_receipt_schema": EXECUTION_RECEIPT_SCHEMA,
        "request_manifest_sha256": digest(manifest),
        "expected_requests": [
            {"request_id": item["request_id"], "url_sha256": item["url_sha256"]}
            for item in manifest["requests"]
        ],
        "required_receipt_fields": [
            "schema", "request_manifest_sha256", "terminal_status",
            "started_utc", "completed_utc", "elapsed_seconds",
            "requests_attempted", "requests_completed", "bytes_received",
            "request_receipts", "redirects_followed", "authentication_used",
            "paid_access_used", "write_operation_used", "provider_cost_usd",
            "dev_data_read", "final_data_read", "formal_data_admitted",
            "failure_code",
        ],
        "required_request_receipt_fields": [
            "request_id", "url_sha256", "status", "content_type",
            "response_bytes", "response_sha256", "rows_received",
            "condition_id_match", "asset_ids_within_fixed_set",
            "timestamps_within_fixed_window",
        ],
        "hard_constraints": {
            "allowed_terminal_status": ["succeeded", "failed"],
            "max_requests": manifest["hard_budget"]["max_requests"],
            "max_total_response_bytes": manifest["hard_budget"][
                "max_total_response_bytes"],
            "max_elapsed_seconds": manifest["hard_budget"]["max_elapsed_seconds"],
            "redirects_followed": 0,
            "authentication_used": False,
            "paid_access_used": False,
            "write_operation_used": False,
            "provider_cost_usd": "0",
            "dev_data_read": False,
            "final_data_read": False,
            "formal_data_admitted": False,
        },
    }


def build_bundle(value: object, *, catalog_json: bytes | None = None,
                 catalog_commitment_id: str | None = None) -> dict:
    manifest = build_request_manifest(
        value, catalog_json=catalog_json,
        catalog_commitment_id=catalog_commitment_id)
    receipt_contract = build_receipt_contract(
        manifest, builder_input=value, catalog_json=catalog_json,
        catalog_commitment_id=catalog_commitment_id)
    return {
        "request_manifest": manifest,
        "request_manifest_canonical_sha256": digest(manifest),
        "execution_receipt_contract": receipt_contract,
        "execution_receipt_contract_canonical_sha256": digest(receipt_contract),
    }


def parse_unique_json(raw: str) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON member")
            result[key] = value
        return result

    if not isinstance(raw, str) or not raw or len(raw.encode("utf-8")) > 256_000:
        raise ValueError("missing or oversized trade-query input")
    value = json.loads(raw, object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise ValueError("trade-query input must be one JSON object")
    return value


def _canonical_bytes(value: dict) -> bytes:
    return (canonical(value) + "\n").encode("utf-8")


def write_bundle(value: object, output: Path, *, catalog_json: bytes | None = None,
                 catalog_commitment_id: str | None = None) -> dict:
    """Write immutable offline artifacts to a new directory."""
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise FileExistsError("trade-query output must be fresh")
    bundle = build_bundle(
        value, catalog_json=catalog_json,
        catalog_commitment_id=catalog_commitment_id)
    output.mkdir(parents=True, exist_ok=False)
    manifest_bytes = _canonical_bytes(bundle["request_manifest"])
    contract_bytes = _canonical_bytes(bundle["execution_receipt_contract"])
    (output / "request-manifest.json").write_bytes(manifest_bytes)
    (output / "execution-receipt-contract.json").write_bytes(contract_bytes)
    receipt = {
        "schema": BUILD_RECEIPT_SCHEMA,
        "input_canonical_sha256": digest(validate_input(
            value, catalog_json=catalog_json,
            catalog_commitment_id=catalog_commitment_id)),
        "request_manifest_canonical_sha256": bundle[
            "request_manifest_canonical_sha256"],
        "request_manifest_file_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "execution_receipt_contract_canonical_sha256": bundle[
            "execution_receipt_contract_canonical_sha256"],
        "execution_receipt_contract_file_sha256": hashlib.sha256(
            contract_bytes).hexdigest(),
        "requests_planned": bundle["request_manifest"]["request_count"],
        "network_requests_made": 0,
        "bytes_fetched": 0,
        "provider_cost_usd": "0",
        "dev_data_read": False,
        "final_data_read": False,
        "formal_data_admitted": False,
    }
    (output / "build-receipt.json").write_bytes(_canonical_bytes(receipt))
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = parse_unique_json(args.input.read_text())
    print(canonical(write_bundle(value, args.output)))


if __name__ == "__main__":
    main()
