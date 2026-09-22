"""Offline Polymarket Data API v2 cursor manifest and receipt validator.

This module has no transport and grants no network or data-admission authority.
It freezes the shape of a future v2 acquisition and validates exact raw response
bytes supplied by a separately authorized executor.  Cursors remain opaque:
trusted code may only copy a validated ``next_cursor`` into the next request's
single ``cursor`` query field while every other request component stays fixed.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import hashlib
import json
import re
from types import MappingProxyType
from urllib.parse import urlencode, urlsplit, urlunsplit

from market_rsi import canonical, digest


MANIFEST_SCHEMA = "market_polymarket_v2_cursor_manifest_v1"
RECEIPT_CONTRACT_SCHEMA = "market_polymarket_v2_cursor_receipt_contract_v1"
EXECUTION_RECEIPT_SCHEMA = "market_polymarket_v2_cursor_execution_receipt_v1"
VALIDATION_SCHEMA = "market_polymarket_v2_cursor_validation_v1"

SOURCE_ID = "polymarket_public_trades_v2"
API_VERSION = "polymarket_data_api_v2"
DOCUMENTATION_URL = "https://docs.polymarket.com/api-reference/feeds/list-trades"
PUBLIC_TRAIN_SCOPE = "public_train_candidate_only"

LIMIT = 1000
TAKER_ONLY = "true"
FILTER_AMOUNT = "0.01"
HARD_MAX_STREAMS = 300
HARD_MAX_REQUESTS = 3000
HARD_MAX_PAGES = 3000
HARD_MAX_PAGES_PER_STREAM = 100
HARD_MAX_PAGE_RESPONSE_BYTES = 2_000_000
HARD_MAX_TOTAL_RESPONSE_BYTES = 500_000_000
HARD_MAX_ELAPSED_SECONDS = 3 * 60 * 60
MAX_CURSOR_BYTES = 4096

ENDPOINT = MappingProxyType({
    "scheme": "https",
    "host": "data-api.polymarket.com",
    "path": "/v2/trades",
    "method": "GET",
})
INVARIANT_QUERY = MappingProxyType({
    "limit": LIMIT,
    "taker_only": TAKER_ONLY,
    "filter_amount": FILTER_AMOUNT,
})
HEADERS = MappingProxyType({
    "Accept": "application/json",
    "User-Agent": "MarketRSI-Polymarket-v2-Cursor/1.0",
})

_MANIFEST_FIELDS = frozenset({
    "schema", "source_id", "documentation_url", "api_version", "endpoint",
    "data_scope", "invariant_query", "cursor_transition", "stream_count",
    "streams", "hard_caps", "execution_policy", "claim_boundaries",
})
_STREAM_INPUT_FIELDS = frozenset({"stream_id", "condition_id", "asset_ids"})
_STREAM_FIELDS = frozenset({
    "stream_id", "condition_id", "asset_ids", "selection_sha256",
    "initial_request",
})
_REQUEST_FIELDS = frozenset({
    "method", "url", "url_sha256", "headers", "headers_sha256",
    "follow_redirects", "query",
})
_CAP_FIELDS = frozenset({
    "max_requests", "max_pages", "max_pages_per_stream",
    "max_page_response_bytes", "max_total_response_bytes",
    "max_elapsed_seconds",
})
_RECEIPT_FIELDS = frozenset({
    "schema", "request_manifest_sha256", "terminal_status", "failure_code",
    "started_utc", "completed_utc", "elapsed_milliseconds",
    "requests_attempted", "requests_completed", "pages_completed",
    "response_bytes", "rows_received", "page_receipts",
    "redirects_followed", "authentication_used", "paid_access_used",
    "write_operation_used", "retries_used", "provider_cost_usd",
    "dev_data_read", "final_data_read", "formal_data_admitted",
})
_PAGE_FIELDS = frozenset({
    "page_id", "request_ordinal", "stream_id", "page_index",
    "request_cursor", "method", "url", "url_sha256", "query",
    "headers_sha256", "follow_redirects", "status_code", "content_type",
    "request_started_ms", "request_completed_ms", "response_bytes",
    "response_sha256", "rows_received", "response_has_more",
    "response_next_cursor",
})
_ENVELOPE_FIELDS = frozenset({"data", "pagination"})
_PAGINATION_FIELDS = frozenset({"limit", "offset", "has_more", "next_cursor"})
_STREAM_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}\Z")
_CONDITION_ID = re.compile(r"0x[0-9a-f]{64}\Z")
_ASSET_ID = re.compile(r"[1-9][0-9]{0,99}\Z")
_OPAQUE_CURSOR = re.compile(r"[A-Za-z0-9._~+/=-]{1,4096}\Z")


def _positive_int(value: object, label: str, ceiling: int) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    if value > ceiling:
        raise ValueError(f"{label} exceeds its hard ceiling")
    return value


def _opaque_cursor(value: object) -> str:
    """Validate transport safety without interpreting cursor contents."""
    if (not isinstance(value, str) or not _OPAQUE_CURSOR.fullmatch(value)
            or len(value.encode("utf-8")) > MAX_CURSOR_BYTES):
        raise ValueError("next cursor must be one nonempty allowlisted opaque token")
    return value


def _normalized_stream(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != _STREAM_INPUT_FIELDS:
        raise ValueError("v2 stream fields differ from the frozen schema")
    stream_id = value.get("stream_id")
    condition_id = value.get("condition_id")
    asset_ids = value.get("asset_ids")
    if not isinstance(stream_id, str) or not _STREAM_ID.fullmatch(stream_id):
        raise ValueError("unsafe v2 stream ID")
    if (not isinstance(condition_id, str)
            or not _CONDITION_ID.fullmatch(condition_id)):
        raise ValueError("v2 condition ID must be canonical lowercase hex")
    if (not isinstance(asset_ids, list) or len(asset_ids) != 2
            or any(not isinstance(item, str) or not _ASSET_ID.fullmatch(item)
                   for item in asset_ids)
            or len(set(asset_ids)) != len(asset_ids)):
        raise ValueError(
            "v2 stream requires exactly two unique canonical decimal asset IDs")
    return {
        "stream_id": stream_id,
        "condition_id": condition_id,
        "asset_ids": sorted(asset_ids),
    }


def _normalized_caps(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != _CAP_FIELDS:
        raise ValueError("v2 acquisition caps differ from the frozen schema")
    caps = {
        "max_requests": _positive_int(
            value.get("max_requests"), "max_requests", HARD_MAX_REQUESTS),
        "max_pages": _positive_int(
            value.get("max_pages"), "max_pages", HARD_MAX_PAGES),
        "max_pages_per_stream": _positive_int(
            value.get("max_pages_per_stream"), "max_pages_per_stream",
            HARD_MAX_PAGES_PER_STREAM),
        "max_page_response_bytes": _positive_int(
            value.get("max_page_response_bytes"), "max_page_response_bytes",
            HARD_MAX_PAGE_RESPONSE_BYTES),
        "max_total_response_bytes": _positive_int(
            value.get("max_total_response_bytes"), "max_total_response_bytes",
            HARD_MAX_TOTAL_RESPONSE_BYTES),
        "max_elapsed_seconds": _positive_int(
            value.get("max_elapsed_seconds"), "max_elapsed_seconds",
            HARD_MAX_ELAPSED_SECONDS),
    }
    if caps["max_pages_per_stream"] > caps["max_pages"]:
        raise ValueError("per-stream page cap exceeds total page cap")
    if caps["max_page_response_bytes"] > caps["max_total_response_bytes"]:
        raise ValueError("per-page byte cap exceeds total byte cap")
    return caps


def _query(condition_id: str, cursor: str | None) -> dict:
    value = {"condition": condition_id, **dict(INVARIANT_QUERY)}
    if cursor is not None:
        value["cursor"] = _opaque_cursor(cursor)
    return value


def _request(condition_id: str, cursor: str | None) -> dict:
    query = _query(condition_id, cursor)
    ordered_names = ("condition", "limit", "taker_only", "filter_amount")
    pairs = [(name, query[name]) for name in ordered_names]
    if cursor is not None:
        pairs.append(("cursor", query["cursor"]))
    url = urlunsplit((ENDPOINT["scheme"], ENDPOINT["host"], ENDPOINT["path"],
                      urlencode(pairs), ""))
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.netloc != ENDPOINT["host"]
            or parsed.hostname != ENDPOINT["host"]
            or parsed.path != ENDPOINT["path"] or parsed.fragment):
        raise ValueError("v2 request escaped the trusted HTTPS endpoint")
    return {
        "method": ENDPOINT["method"],
        "url": url,
        "url_sha256": hashlib.sha256(url.encode("utf-8")).hexdigest(),
        "headers": dict(HEADERS),
        "headers_sha256": digest(dict(HEADERS)),
        "follow_redirects": False,
        "query": query,
    }


def build_manifest(streams: object, caps: object) -> dict:
    """Build a deterministic v2 state-machine manifest without I/O."""
    if not isinstance(streams, list) or not streams:
        raise ValueError("at least one v2 cursor stream is required")
    if len(streams) > HARD_MAX_STREAMS:
        raise ValueError("v2 stream count exceeds its hard ceiling")
    normalized = sorted((_normalized_stream(item) for item in streams),
                        key=lambda item: item["stream_id"])
    stream_ids = [item["stream_id"] for item in normalized]
    conditions = [item["condition_id"] for item in normalized]
    assets = [asset for item in normalized for asset in item["asset_ids"]]
    if len(set(stream_ids)) != len(stream_ids):
        raise ValueError("duplicate v2 stream ID")
    if len(set(conditions)) != len(conditions):
        raise ValueError("duplicate v2 condition stream")
    if len(set(assets)) != len(assets):
        raise ValueError("v2 asset IDs cannot cross fixed streams")
    caps = _normalized_caps(caps)
    if (len(normalized) > caps["max_requests"]
            or len(normalized) > caps["max_pages"]):
        raise ValueError("v2 caps cannot complete one initial page per stream")
    manifested = []
    for item in normalized:
        manifested.append({
            **item,
            "selection_sha256": digest(item),
            "initial_request": _request(item["condition_id"], None),
        })
    return {
        "schema": MANIFEST_SCHEMA,
        "source_id": SOURCE_ID,
        "documentation_url": DOCUMENTATION_URL,
        "api_version": API_VERSION,
        "endpoint": dict(ENDPOINT),
        "data_scope": PUBLIC_TRAIN_SCOPE,
        "invariant_query": dict(INVARIANT_QUERY),
        "cursor_transition": {
            "response_envelope_fields": sorted(_ENVELOPE_FIELDS),
            "pagination_fields": sorted(_PAGINATION_FIELDS),
            "response_cursor_path": ["pagination", "next_cursor"],
            "request_cursor_field": "cursor",
            "copy_cursor_without_decoding": True,
            "only_cursor_may_change_within_stream": True,
            "empty_cursor_allowed": False,
            "repeated_cursor_allowed": False,
            "continuing_page_must_have_rows": True,
            "termination": {"has_more": False, "next_cursor": None},
        },
        "stream_count": len(manifested),
        "streams": manifested,
        "hard_caps": caps,
        "execution_policy": {
            "network_execution_authorized": False,
            "https_only": True,
            "trusted_endpoint_only": True,
            "redirects_allowed": False,
            "authentication_allowed": False,
            "paid_access_allowed": False,
            "write_operations_allowed": False,
            "retries_allowed": False,
        },
        "claim_boundaries": {
            "manifest_only": True,
            "data_fetched": False,
            "source_rights_verified": False,
            "provider_origin_authenticated": False,
            "dev_data_read": False,
            "final_data_read": False,
            "formal_data_admitted": False,
            "prediction_improvement_proven": False,
        },
    }


def validate_manifest(value: object) -> dict:
    """Rebuild every derived field from strict stream inputs and caps."""
    if not isinstance(value, dict) or set(value) != _MANIFEST_FIELDS:
        raise ValueError("v2 cursor manifest fields differ from the frozen schema")
    streams = value.get("streams")
    if not isinstance(streams, list) or not streams:
        raise ValueError("v2 cursor manifest has no streams")
    inputs = []
    for stream in streams:
        if not isinstance(stream, dict) or set(stream) != _STREAM_FIELDS:
            raise ValueError("v2 manifested stream fields differ from schema")
        request = stream.get("initial_request")
        if not isinstance(request, dict) or set(request) != _REQUEST_FIELDS:
            raise ValueError("v2 initial request fields differ from schema")
        inputs.append({key: stream[key] for key in _STREAM_INPUT_FIELDS})
    expected = build_manifest(inputs, value.get("hard_caps"))
    if canonical(value) != canonical(expected):
        raise ValueError("v2 cursor manifest differs from trusted builder output")
    return expected


def realize_next_request(manifest: object, stream_id: str,
                         cursor: str | None) -> dict:
    """Realize only the allowlisted cursor transition for one fixed stream."""
    manifest = validate_manifest(manifest)
    matches = [item for item in manifest["streams"]
               if item["stream_id"] == stream_id]
    if len(matches) != 1:
        raise ValueError("v2 stream is not in the fixed manifest")
    request = _request(matches[0]["condition_id"], cursor)
    if cursor is None and request != matches[0]["initial_request"]:
        raise ValueError("v2 initial request changed")
    return request


def build_receipt_contract(manifest: object) -> dict:
    manifest = validate_manifest(manifest)
    return {
        "schema": RECEIPT_CONTRACT_SCHEMA,
        "execution_receipt_schema": EXECUTION_RECEIPT_SCHEMA,
        "validation_schema": VALIDATION_SCHEMA,
        "request_manifest_sha256": digest(manifest),
        "required_receipt_fields": sorted(_RECEIPT_FIELDS),
        "required_page_receipt_fields": sorted(_PAGE_FIELDS),
        "api_version": API_VERSION,
        "endpoint": dict(ENDPOINT),
        "invariant_query": dict(INVARIANT_QUERY),
        "cursor_transition": manifest["cursor_transition"],
        "hard_caps": manifest["hard_caps"],
        "claim_boundaries": {
            "receipt_validation_authorizes_network": False,
            "source_rights_verified": False,
            "provider_origin_authenticated": False,
            "formal_data_admitted": False,
        },
    }


def _unique_json(raw: bytes, page_id: str) -> dict:
    if not isinstance(raw, bytes):
        raise ValueError("raw v2 pages must be exact bytes")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON member in raw v2 page")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant in raw v2 page: {value}")

    try:
        value = json.loads(raw, object_pairs_hook=unique,
                           parse_constant=reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid raw v2 JSON page: {page_id}") from exc
    if not isinstance(value, dict) or set(value) != _ENVELOPE_FIELDS:
        raise ValueError("raw v2 response envelope differs from contract")
    return value


def _utc_milliseconds(value: object, label: str) -> tuple[datetime, int]:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{label} must be canonical UTC milliseconds")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"{label} must be canonical UTC milliseconds") from exc
    canonical_value = parsed.astimezone(timezone.utc).isoformat(
        timespec="milliseconds").replace("+00:00", "Z")
    if value != canonical_value:
        raise ValueError(f"{label} must be canonical UTC milliseconds")
    milliseconds = ((parsed.toordinal() * 86400 + parsed.hour * 3600
                     + parsed.minute * 60 + parsed.second) * 1000
                    + parsed.microsecond // 1000)
    return parsed, milliseconds


def _receipt_scalar_checks(receipt: dict, manifest: dict) -> None:
    caps = manifest["hard_caps"]
    if (receipt.get("schema") != EXECUTION_RECEIPT_SCHEMA
            or receipt.get("request_manifest_sha256") != digest(manifest)
            or receipt.get("terminal_status") != "succeeded"
            or receipt.get("failure_code") is not None
            or type(receipt.get("redirects_followed")) is not int
            or receipt.get("redirects_followed") != 0
            or receipt.get("authentication_used") is not False
            or receipt.get("paid_access_used") is not False
            or receipt.get("write_operation_used") is not False
            or type(receipt.get("retries_used")) is not int
            or receipt.get("retries_used") != 0
            or receipt.get("provider_cost_usd") != "0"
            or receipt.get("dev_data_read") is not False
            or receipt.get("final_data_read") is not False
            or receipt.get("formal_data_admitted") is not False):
        raise ValueError("v2 execution receipt violates fixed terminal boundaries")
    for field, ceiling in (
        ("requests_attempted", caps["max_requests"]),
        ("requests_completed", caps["max_requests"]),
        ("pages_completed", caps["max_pages"]),
        ("response_bytes", caps["max_total_response_bytes"]),
        ("rows_received", 100_000_000),
    ):
        value = receipt.get(field)
        if type(value) is not int or value < 0 or value > ceiling:
            raise ValueError(f"v2 receipt {field} exceeds its contract")
    page_receipts = receipt.get("page_receipts")
    if (not isinstance(page_receipts, list) or not page_receipts
            or len(page_receipts) > caps["max_pages"]
            or receipt["requests_attempted"] != len(page_receipts)
            or receipt["requests_completed"] != len(page_receipts)
            or receipt["pages_completed"] != len(page_receipts)):
        raise ValueError("v2 receipt request/page counts are inconsistent")
    _, started_ms = _utc_milliseconds(receipt.get("started_utc"), "started_utc")
    _, completed_ms = _utc_milliseconds(
        receipt.get("completed_utc"), "completed_utc")
    elapsed = receipt.get("elapsed_milliseconds")
    if (type(elapsed) is not int or elapsed <= 0
            or completed_ms - started_ms != elapsed
            or elapsed > caps["max_elapsed_seconds"] * 1000):
        raise ValueError("v2 receipt elapsed time differs from its hard cap")


def validate_execution_receipt(manifest: object, receipt: object,
                               raw_pages: Mapping[str, bytes]) -> dict:
    """Validate a complete cursor chain against exact supplied response bytes.

    The returned receipt proves internal bytes/query/cursor continuity only. It
    does not authenticate where the bytes came from or admit them into Train.
    """
    manifest = validate_manifest(manifest)
    if not isinstance(receipt, dict) or set(receipt) != _RECEIPT_FIELDS:
        raise ValueError("v2 execution receipt fields differ from contract")
    if not isinstance(raw_pages, Mapping):
        raise ValueError("raw v2 page mapping is required")
    _receipt_scalar_checks(receipt, manifest)
    caps = manifest["hard_caps"]
    pages = receipt["page_receipts"]
    page_offset = 0
    previous_completed_ms = 0
    observed_page_ids = []
    total_bytes = 0
    total_rows = 0
    raw_bindings = []

    for stream in manifest["streams"]:
        cursor = None
        seen_cursors: set[str] = set()
        seen_rows: set[str] = set()
        for page_index in range(caps["max_pages_per_stream"]):
            if page_offset >= len(pages):
                raise ValueError("v2 stream ended without terminal pagination")
            page = pages[page_offset]
            if not isinstance(page, dict) or set(page) != _PAGE_FIELDS:
                raise ValueError("v2 page receipt fields differ from contract")
            page_id = f'{stream["stream_id"]}-page-{page_index:04d}'
            request = _request(stream["condition_id"], cursor)
            if (page.get("page_id") != page_id
                    or type(page.get("request_ordinal")) is not int
                    or page.get("request_ordinal") != page_offset
                    or page.get("stream_id") != stream["stream_id"]
                    or type(page.get("page_index")) is not int
                    or page.get("page_index") != page_index
                    or page.get("request_cursor") != cursor
                    or page.get("method") != request["method"]
                    or page.get("url") != request["url"]
                    or page.get("url_sha256") != request["url_sha256"]
                    or canonical(page.get("query")) != canonical(request["query"])
                    or page.get("headers_sha256") != request["headers_sha256"]
                    or page.get("follow_redirects") is not False
                    or type(page.get("status_code")) is not int
                    or page.get("status_code") != 200
                    or page.get("content_type") != "application/json"):
                raise ValueError("v2 realized request/page identity changed")
            started_ms = page.get("request_started_ms")
            completed_ms = page.get("request_completed_ms")
            if (type(started_ms) is not int or type(completed_ms) is not int
                    or started_ms < previous_completed_ms
                    or completed_ms <= started_ms
                    or completed_ms > receipt["elapsed_milliseconds"]):
                raise ValueError("v2 page timing is invalid or non-monotonic")
            previous_completed_ms = completed_ms
            if page_id not in raw_pages:
                raise ValueError("exact raw v2 page is missing")
            raw = raw_pages[page_id]
            if not isinstance(raw, bytes):
                raise ValueError("raw v2 pages must be exact bytes")
            if (len(raw) > caps["max_page_response_bytes"]
                    or type(page.get("response_bytes")) is not int
                    or page.get("response_bytes") != len(raw)
                    or page.get("response_sha256")
                    != hashlib.sha256(raw).hexdigest()):
                raise ValueError("raw v2 page byte/hash receipt differs")
            payload = _unique_json(raw, page_id)
            data = payload.get("data")
            pagination = payload.get("pagination")
            if (not isinstance(data, list) or not isinstance(pagination, dict)
                    or len(data) > LIMIT
                    or set(pagination) != _PAGINATION_FIELDS
                    or type(pagination.get("limit")) is not int
                    or pagination.get("limit") != LIMIT
                    or type(pagination.get("offset")) is not int
                    or pagination.get("offset") != page_index * LIMIT
                    or type(pagination.get("has_more")) is not bool):
                raise ValueError(
                    "raw v2 page size/pagination differs from frozen API contract")
            for row in data:
                if (not isinstance(row, dict)
                        or row.get("condition_id") != stream["condition_id"]
                        or not isinstance(row.get("token_id"), str)
                        or row["token_id"] not in stream["asset_ids"]):
                    raise ValueError("raw v2 trade escaped fixed condition/assets")
                row_sha = digest(row)
                if row_sha in seen_rows:
                    raise ValueError("duplicate raw v2 trade row within stream")
                seen_rows.add(row_sha)
            has_more = pagination["has_more"]
            next_cursor = pagination["next_cursor"]
            if (type(page.get("rows_received")) is not int
                    or page.get("rows_received") != len(data)
                    or page.get("response_has_more") is not has_more
                    or page.get("response_next_cursor") != next_cursor):
                raise ValueError("v2 page receipt differs from raw pagination")
            total_bytes += len(raw)
            total_rows += len(data)
            observed_page_ids.append(page_id)
            raw_bindings.append({
                "page_id": page_id,
                "response_sha256": hashlib.sha256(raw).hexdigest(),
            })
            page_offset += 1
            if has_more:
                if not data:
                    raise ValueError("continuing v2 page cannot be empty")
                next_cursor = _opaque_cursor(next_cursor)
                if next_cursor in seen_cursors:
                    raise ValueError("repeated or looped v2 cursor")
                seen_cursors.add(next_cursor)
                cursor = next_cursor
                if page_index + 1 >= caps["max_pages_per_stream"]:
                    raise ValueError("v2 stream exceeded per-stream page cap")
                continue
            if next_cursor is not None:
                raise ValueError("terminal v2 page must have null next cursor")
            break
        else:
            raise ValueError("v2 stream did not terminate within page cap")

    if page_offset != len(pages):
        raise ValueError("v2 receipt has pages after all streams terminated")
    if set(raw_pages) != set(observed_page_ids):
        raise ValueError("raw v2 page set has missing or unreceipted bytes")
    if (total_bytes != receipt["response_bytes"]
            or total_rows != receipt["rows_received"]
            or total_bytes > caps["max_total_response_bytes"]):
        raise ValueError("v2 aggregate byte/row receipt differs or exceeds cap")
    return {
        "schema": VALIDATION_SCHEMA,
        "passed": True,
        "request_manifest_sha256": digest(manifest),
        "execution_receipt_sha256": digest(receipt),
        "raw_page_bindings_sha256": digest(raw_bindings),
        "streams_completed": len(manifest["streams"]),
        "requests_completed": len(pages),
        "pages_completed": len(pages),
        "response_bytes": total_bytes,
        "rows_received": total_rows,
        "cursor_chains_terminated": True,
        "network_execution_authorized": False,
        "source_rights_verified": False,
        "provider_origin_authenticated": False,
        "dev_data_read": False,
        "final_data_read": False,
        "formal_data_admitted": False,
        "prediction_improvement_proven": False,
    }
