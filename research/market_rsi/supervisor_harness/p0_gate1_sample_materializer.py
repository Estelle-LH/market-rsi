"""Deterministically materialize a fixed Train-only Gate 1 trade sample.

The input is an already-frozen, outcome-free catalog encoded as JSON bytes.
This module performs no file reads, network calls, provider calls, or data
fetches.  It only validates the catalog, selects first/middle/last after the
frozen sort, and emits hash-bound inputs for a separately admitted runner.
"""
from __future__ import annotations

from datetime import date
import hashlib
import json
import re

from market_rsi import canonical, digest


CATALOG_SCHEMA = "market_p0_gate1_train_catalog_v1"
MATERIALIZATION_SCHEMA = "market_p0_gate1_fixed_sample_materialization_v1"
RULE_ID = "first_middle_last_by_game_date_game_id_v1"
SOURCE_ID = "polymarket_public_trades_v1"
DATA_SCOPE = "public_train_only"
TRAIN_ROLE = "market_train"

_CATALOG_FIELDS = {"schema", "catalog_id", "source_id", "data_scope", "rows"}
_ROW_FIELDS = {
    "game_date", "game_id", "split_role", "condition_id", "asset_ids",
    "start_timestamp", "end_timestamp",
}
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}\Z")
_CONDITION_ID = re.compile(r"0x[0-9a-f]{64}\Z")
_ASSET_ID = re.compile(r"[1-9][0-9]{0,99}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_MAX_CATALOG_BYTES = 5_000_000
_MAX_UNIX_SECONDS = 253_402_300_799


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON field in frozen Train catalog")
        value[key] = item
    return value


def _parse_catalog(raw: bytes, frozen_catalog_sha256: str) -> dict:
    if not isinstance(raw, bytes) or not 0 < len(raw) <= _MAX_CATALOG_BYTES:
        raise ValueError("frozen Train catalog must be nonempty bounded bytes")
    if (not isinstance(frozen_catalog_sha256, str)
            or not _SHA256.fullmatch(frozen_catalog_sha256)):
        raise ValueError("frozen catalog SHA-256 is invalid")
    if _sha256(raw) != frozen_catalog_sha256:
        raise ValueError("frozen Train catalog hash changed")

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant is forbidden: {value}")

    try:
        value = json.loads(raw, object_pairs_hook=_unique_object,
                           parse_constant=reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("frozen Train catalog is not valid JSON") from exc
    if not isinstance(value, dict) or set(value) != _CATALOG_FIELDS:
        raise ValueError("frozen Train catalog fields differ from contract")
    return value


def _positive_timestamp(value: object, name: str) -> int:
    if type(value) is not int or not 0 < value <= _MAX_UNIX_SECONDS:
        raise ValueError(f"{name} is out of range")
    return value


def _validate_row(row: object) -> dict:
    if not isinstance(row, dict) or set(row) != _ROW_FIELDS:
        raise ValueError("Train catalog row fields differ from contract")
    game_id = row["game_id"]
    if not isinstance(game_id, str) or not _IDENTIFIER.fullmatch(game_id):
        raise ValueError("game_id is not a safe exact sample ID")
    game_date = row["game_date"]
    if not isinstance(game_date, str):
        raise ValueError("game_date must be canonical ISO text")
    try:
        parsed_date = date.fromisoformat(game_date)
    except ValueError as exc:
        raise ValueError("game_date is not a valid ISO date") from exc
    if parsed_date.isoformat() != game_date:
        raise ValueError("game_date is not canonical ISO text")
    if row["split_role"] != TRAIN_ROLE:
        raise ValueError("Dev/Final exposure is forbidden; expected market_train")
    condition_id = row["condition_id"]
    if not isinstance(condition_id, str) or not _CONDITION_ID.fullmatch(condition_id):
        raise ValueError("condition_id must be exact lowercase 0x-prefixed SHA-width hex")
    asset_ids = row["asset_ids"]
    if (not isinstance(asset_ids, list) or not 1 <= len(asset_ids) <= 2
            or any(not isinstance(item, str) or not _ASSET_ID.fullmatch(item)
                   for item in asset_ids)
            or len(asset_ids) != len(set(asset_ids))):
        raise ValueError("asset_ids must contain one or two distinct decimal token IDs")
    start = _positive_timestamp(row["start_timestamp"], "start_timestamp")
    end = _positive_timestamp(row["end_timestamp"], "end_timestamp")
    if start >= end:
        raise ValueError("sample time window is empty or reversed")
    # Return a fresh JSON-only value so callers cannot mutate the input through
    # the materialization result.
    return {
        "game_date": game_date,
        "game_id": game_id,
        "split_role": TRAIN_ROLE,
        "condition_id": condition_id,
        "asset_ids": list(asset_ids),
        "start_timestamp": start,
        "end_timestamp": end,
    }


def materialize(catalog_json: bytes, frozen_catalog_sha256: str,
                rule_id: str = RULE_ID) -> dict:
    """Return exact hash-bound runner inputs from one frozen Train catalog.

    ``frozen_catalog_sha256`` commits the exact input bytes, while each
    ``input_sha256`` commits the canonical full catalog row.  The only accepted
    selection rule intentionally has no prose parser or aliases: similar but
    ambiguous Controller text must be rejected by an upstream capability
    contract rather than guessed here.
    """
    if rule_id != RULE_ID:
        raise ValueError("ambiguous or unsupported fixed sample rule")
    catalog = _parse_catalog(catalog_json, frozen_catalog_sha256)
    if catalog["schema"] != CATALOG_SCHEMA:
        raise ValueError("wrong frozen Train catalog schema")
    catalog_id = catalog["catalog_id"]
    if not isinstance(catalog_id, str) or not _IDENTIFIER.fullmatch(catalog_id):
        raise ValueError("catalog_id is invalid")
    if catalog["source_id"] != SOURCE_ID:
        raise ValueError("frozen catalog source is not the admitted public trade source")
    if catalog["data_scope"] != DATA_SCOPE:
        raise ValueError("Dev/Final exposure is forbidden; expected public_train_only")
    rows = catalog["rows"]
    if not isinstance(rows, list) or not rows:
        raise ValueError("fixed sample cannot be empty")
    validated = [_validate_row(row) for row in rows]
    game_ids = [row["game_id"] for row in validated]
    conditions = [row["condition_id"] for row in validated]
    if len(game_ids) != len(set(game_ids)):
        raise ValueError("duplicate exact sample ID in frozen Train catalog")
    if len(conditions) != len(set(conditions)):
        raise ValueError("duplicate condition_id in frozen Train catalog")

    ordered = sorted(validated, key=lambda row: (row["game_date"], row["game_id"]))
    positions = (0, len(ordered) // 2, len(ordered) - 1)
    if any(position < 0 or position >= len(ordered) for position in positions):
        raise ValueError("fixed sample position is out of range")
    selected = [ordered[position] for position in positions]
    selected_ids = [row["game_id"] for row in selected]
    if len(selected_ids) != 3 or len(set(selected_ids)) != 3:
        raise ValueError("fixed sample positions are out of range or duplicate")

    request_plan_inputs = []
    sample_commitments = []
    for row in selected:
        input_sha256 = digest(row)
        sample_id = row["game_id"]
        request_plan_inputs.append({
            "sample_id": sample_id,
            "condition_id": row["condition_id"],
            "asset_ids": list(row["asset_ids"]),
            "start_timestamp": row["start_timestamp"],
            "end_timestamp": row["end_timestamp"],
            "input_sha256": input_sha256,
        })
        sample_commitments.append({"sample_id": sample_id,
                                   "input_sha256": input_sha256})

    result = {
        "schema": MATERIALIZATION_SCHEMA,
        "catalog_id": catalog_id,
        "catalog_file_sha256": frozen_catalog_sha256,
        "catalog_canonical_sha256": digest(catalog),
        "catalog_row_count": len(ordered),
        "source_id": SOURCE_ID,
        "data_scope": DATA_SCOPE,
        "rule_id": RULE_ID,
        "sort_keys": ["game_date", "game_id"],
        "selectors": ["first", "middle", "last"],
        "middle_index": len(ordered) // 2,
        "sample_ids": selected_ids,
        "sample_commitments": sample_commitments,
        "selected_rows_sha256": digest(selected),
        "request_plan_inputs": request_plan_inputs,
        "request_plan_inputs_sha256": digest(request_plan_inputs),
        "dev_or_final_exposed": False,
    }
    # This commitment covers every preceding result field.  The exact bytes of
    # the full returned object (including this field) are available through
    # canonical_output below.
    result["materialization_sha256"] = digest(result)
    return result


def canonical_output(materialization: dict) -> tuple[bytes, str]:
    """Return newline-terminated canonical JSON and its exact byte SHA-256."""
    if (not isinstance(materialization, dict)
            or materialization.get("schema") != MATERIALIZATION_SCHEMA):
        raise ValueError("wrong fixed sample materialization")
    commitment = materialization.get("materialization_sha256")
    body = {key: value for key, value in materialization.items()
            if key != "materialization_sha256"}
    if not isinstance(commitment, str) or commitment != digest(body):
        raise ValueError("fixed sample materialization commitment changed")
    raw = (canonical(materialization) + "\n").encode("utf-8")
    return raw, _sha256(raw)
