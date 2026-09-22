import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import unittest
from urllib.parse import parse_qs, urlencode, urlsplit

from market_rsi import digest
from supervisor_harness import p0_gate1_trade_query as legacy_v1
from supervisor_harness.p0_gate1_executable_plan_canary_fixtures import (
    trade_builder_input,
)
from supervisor_harness.p0_polymarket_v2_cursor_acquisition import (
    API_VERSION,
    EXECUTION_RECEIPT_SCHEMA,
    MANIFEST_SCHEMA,
    RECEIPT_CONTRACT_SCHEMA,
    SOURCE_ID,
    VALIDATION_SCHEMA,
    build_manifest,
    build_receipt_contract,
    realize_next_request,
    validate_execution_receipt,
    validate_manifest,
)


def stream(number: int) -> dict:
    return {
        "stream_id": f"train-game-{number:03d}",
        "condition_id": "0x" + f"{number:x}"[-1] * 64,
        "asset_ids": [str(10_000 + number * 2), str(10_001 + number * 2)],
    }


def caps(**changes) -> dict:
    value = {
        "max_requests": 8,
        "max_pages": 8,
        "max_pages_per_stream": 4,
        "max_page_response_bytes": 4096,
        "max_total_response_bytes": 16_384,
        "max_elapsed_seconds": 60,
    }
    value.update(changes)
    return value


def row(item: dict, identity: str, *, condition_id=None, token_id=None) -> dict:
    return {
        "condition_id": condition_id or item["condition_id"],
        "token_id": token_id or item["asset_ids"][0],
        "timestamp": 1_720_000_000,
        "transaction_hash": identity,
        "price": 0.5,
        "size": 1.0,
    }


def raw_page(rows, page_index: int, *, has_more: bool,
             next_cursor, extra_envelope=None, extra_pagination=None,
             limit=1000, offset=None) -> bytes:
    payload = {
        "data": rows,
        "pagination": {
            "limit": limit,
            "offset": page_index * 1000 if offset is None else offset,
            "has_more": has_more,
            "next_cursor": next_cursor,
        },
    }
    if extra_envelope:
        payload.update(extra_envelope)
    if extra_pagination:
        payload["pagination"].update(extra_pagination)
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def execution_fixture(manifest: dict, pages_by_stream: dict[str, list[bytes]]):
    page_receipts = []
    raw_pages = {}
    total_rows = 0
    total_bytes = 0
    ordinal = 0
    for item in manifest["streams"]:
        cursor = None
        for page_index, raw in enumerate(pages_by_stream[item["stream_id"]]):
            request = realize_next_request(
                manifest, item["stream_id"], cursor)
            payload = json.loads(raw)
            page_id = f'{item["stream_id"]}-page-{page_index:04d}'
            data = payload.get("data") if isinstance(payload, dict) else []
            pagination = payload.get("pagination", {}) if isinstance(
                payload, dict) else {}
            page_receipts.append({
                "page_id": page_id,
                "request_ordinal": ordinal,
                "stream_id": item["stream_id"],
                "page_index": page_index,
                "request_cursor": cursor,
                "method": request["method"],
                "url": request["url"],
                "url_sha256": request["url_sha256"],
                "query": request["query"],
                "headers_sha256": request["headers_sha256"],
                "follow_redirects": False,
                "status_code": 200,
                "content_type": "application/json",
                "request_started_ms": ordinal * 10,
                "request_completed_ms": ordinal * 10 + 9,
                "response_bytes": len(raw),
                "response_sha256": hashlib.sha256(raw).hexdigest(),
                "rows_received": len(data) if isinstance(data, list) else 0,
                "response_has_more": pagination.get("has_more"),
                "response_next_cursor": pagination.get("next_cursor"),
            })
            raw_pages[page_id] = raw
            total_rows += len(data) if isinstance(data, list) else 0
            total_bytes += len(raw)
            cursor = pagination.get("next_cursor")
            ordinal += 1
    elapsed = max(10, ordinal * 10)
    started = datetime(2026, 9, 22, 20, 0, 0, tzinfo=timezone.utc)
    completed = started + timedelta(milliseconds=elapsed)
    receipt = {
        "schema": EXECUTION_RECEIPT_SCHEMA,
        "request_manifest_sha256": digest(manifest),
        "terminal_status": "succeeded",
        "failure_code": None,
        "started_utc": started.isoformat(timespec="milliseconds").replace(
            "+00:00", "Z"),
        "completed_utc": completed.isoformat(timespec="milliseconds").replace(
            "+00:00", "Z"),
        "elapsed_milliseconds": elapsed,
        "requests_attempted": ordinal,
        "requests_completed": ordinal,
        "pages_completed": ordinal,
        "response_bytes": total_bytes,
        "rows_received": total_rows,
        "page_receipts": page_receipts,
        "redirects_followed": 0,
        "authentication_used": False,
        "paid_access_used": False,
        "write_operation_used": False,
        "retries_used": 0,
        "provider_cost_usd": "0",
        "dev_data_read": False,
        "final_data_read": False,
        "formal_data_admitted": False,
    }
    return receipt, raw_pages


class PolymarketV2CursorAcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.streams = [stream(1), stream(2)]
        self.manifest = build_manifest(self.streams, caps())
        first, second = self.manifest["streams"]
        self.pages = {
            first["stream_id"]: [
                raw_page([row(first, "tx-1")], 0,
                         has_more=True, next_cursor="opaque+/=_c1"),
                raw_page([row(first, "tx-2")], 1,
                         has_more=False, next_cursor=None),
            ],
            second["stream_id"]: [
                raw_page([], 0, has_more=False, next_cursor=None),
            ],
        }

    def valid(self, manifest=None, pages=None):
        manifest = self.manifest if manifest is None else manifest
        pages = self.pages if pages is None else pages
        receipt, raw_pages = execution_fixture(manifest, pages)
        return manifest, receipt, raw_pages

    def test_builds_version_correct_v2_manifest_and_contract(self):
        manifest = self.manifest
        self.assertEqual(manifest["schema"], MANIFEST_SCHEMA)
        self.assertEqual(manifest["source_id"], SOURCE_ID)
        self.assertEqual(manifest["api_version"], API_VERSION)
        self.assertEqual(manifest["endpoint"], {
            "scheme": "https", "host": "data-api.polymarket.com",
            "path": "/v2/trades", "method": "GET",
        })
        self.assertEqual(manifest["invariant_query"], {
            "limit": 1000, "taker_only": "true", "filter_amount": "0.01",
        })
        self.assertFalse(manifest["execution_policy"][
            "network_execution_authorized"])
        contract = build_receipt_contract(manifest)
        self.assertEqual(contract["schema"], RECEIPT_CONTRACT_SCHEMA)
        self.assertEqual(contract["request_manifest_sha256"], digest(manifest))
        self.assertFalse(contract["claim_boundaries"][
            "receipt_validation_authorizes_network"])
        self.assertFalse(contract["claim_boundaries"]["formal_data_admitted"])

    def test_initial_and_cursor_requests_change_only_cursor(self):
        item = self.manifest["streams"][0]
        initial = item["initial_request"]
        continued = realize_next_request(
            self.manifest, item["stream_id"], "opaque+/=_c1")
        self.assertEqual(urlsplit(initial["url"]).path, "/v2/trades")
        self.assertNotIn("cursor", initial["query"])
        self.assertEqual(continued["query"]["cursor"], "opaque+/=_c1")
        self.assertEqual(parse_qs(urlsplit(continued["url"]).query)["cursor"],
                         ["opaque+/=_c1"])
        for name in ("condition", "limit", "taker_only", "filter_amount"):
            self.assertEqual(initial["query"][name], continued["query"][name])
        self.assertEqual(initial["headers"], continued["headers"])
        self.assertFalse(continued["follow_redirects"])

    def test_complete_frozen_cursor_chains_validate(self):
        manifest, receipt, raw_pages = self.valid()
        result = validate_execution_receipt(manifest, receipt, raw_pages)
        self.assertEqual(result["schema"], VALIDATION_SCHEMA)
        self.assertTrue(result["passed"])
        self.assertEqual(result["streams_completed"], 2)
        self.assertEqual(result["pages_completed"], 3)
        self.assertTrue(result["cursor_chains_terminated"])
        self.assertFalse(result["network_execution_authorized"])
        self.assertFalse(result["source_rights_verified"])
        self.assertFalse(result["provider_origin_authenticated"])
        self.assertFalse(result["formal_data_admitted"])

    def test_manifest_tampering_and_extra_authority_fail_closed(self):
        for field, value in (
            ("api_version", "polymarket_data_api_v1"),
            ("source_id", "caller-source"),
            ("endpoint", {**self.manifest["endpoint"], "path": "/trades"}),
            ("invariant_query", {**self.manifest["invariant_query"],
                                 "limit": 999}),
            ("execution_policy", {**self.manifest["execution_policy"],
                                  "network_execution_authorized": True}),
            ("claim_boundaries", {**self.manifest["claim_boundaries"],
                                  "formal_data_admitted": True}),
        ):
            changed = copy.deepcopy(self.manifest)
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_manifest(changed)
        changed = copy.deepcopy(self.manifest)
        changed["authorization"] = "model-granted"
        with self.assertRaises(ValueError):
            validate_manifest(changed)

    def test_stream_inputs_and_caps_are_strict(self):
        cases = (
            ([{**stream(1), "url": "https://example.test"}], caps()),
            ([{**stream(1), "condition_id": "condition"}], caps()),
            ([{**stream(1), "asset_ids": ["10002"]}], caps()),
            ([{**stream(1), "asset_ids": ["01", "2"]}], caps()),
            ([stream(1), stream(1)], caps()),
            ([stream(1)], caps(max_pages_per_stream=True)),
            ([stream(1)], caps(max_requests=3001)),
            ([stream(1)], caps(max_page_response_bytes=5000,
                               max_total_response_bytes=4000)),
        )
        for streams, limits in cases:
            with self.subTest(streams=streams, limits=limits), self.assertRaises(
                    ValueError):
                build_manifest(streams, limits)

    def test_request_query_url_and_identity_tamper_rejected(self):
        manifest, receipt, raw_pages = self.valid()
        changed = copy.deepcopy(receipt)
        page = changed["page_receipts"][1]
        page["query"]["limit"] = 999
        page["url"] = "https://data-api.polymarket.com/v2/trades?" + urlencode(
            page["query"])
        page["url_sha256"] = hashlib.sha256(page["url"].encode()).hexdigest()
        with self.assertRaisesRegex(ValueError, "identity changed"):
            validate_execution_receipt(manifest, changed, raw_pages)

    def test_empty_and_whitespace_cursors_rejected(self):
        item = self.manifest["streams"][0]
        for value in ("", "   ", "cursor\nvalue"):
            with self.subTest(value=repr(value)), self.assertRaisesRegex(
                    ValueError, "opaque token"):
                realize_next_request(self.manifest, item["stream_id"], value)
        single = build_manifest([stream(1)], caps())
        item = single["streams"][0]
        pages = {item["stream_id"]: [raw_page(
            [row(item, "tx")], 0, has_more=True, next_cursor="")]}
        manifest, receipt, raw_pages = self.valid(single, pages)
        with self.assertRaisesRegex(ValueError, "opaque token"):
            validate_execution_receipt(manifest, receipt, raw_pages)

    def test_repeated_and_looped_cursors_rejected(self):
        single = build_manifest([stream(1)], caps())
        item = single["streams"][0]
        cases = (
            [
                raw_page([row(item, "a")], 0, has_more=True, next_cursor="c1"),
                raw_page([row(item, "b")], 1, has_more=True, next_cursor="c1"),
            ],
            [
                raw_page([row(item, "a")], 0, has_more=True, next_cursor="c1"),
                raw_page([row(item, "b")], 1, has_more=True, next_cursor="c2"),
                raw_page([row(item, "c")], 2, has_more=True, next_cursor="c1"),
            ],
        )
        for pages_list in cases:
            pages = {item["stream_id"]: pages_list}
            _, receipt, raw_pages = self.valid(single, pages)
            with self.subTest(count=len(pages_list)), self.assertRaisesRegex(
                    ValueError, "repeated or looped"):
                validate_execution_receipt(single, receipt, raw_pages)

    def test_incomplete_chain_and_extra_page_after_termination_rejected(self):
        single = build_manifest([stream(1)], caps())
        item = single["streams"][0]
        unfinished = {item["stream_id"]: [raw_page(
            [row(item, "a")], 0, has_more=True, next_cursor="c1")]}
        _, receipt, raw_pages = self.valid(single, unfinished)
        with self.assertRaisesRegex(ValueError, "without terminal"):
            validate_execution_receipt(single, receipt, raw_pages)
        extra = {item["stream_id"]: [
            raw_page([row(item, "a")], 0, has_more=False, next_cursor=None),
            raw_page([row(item, "b")], 1, has_more=False, next_cursor=None),
        ]}
        _, receipt, raw_pages = self.valid(single, extra)
        with self.assertRaisesRegex(ValueError, "after all streams"):
            validate_execution_receipt(single, receipt, raw_pages)

    def test_continuing_empty_page_rejected_but_terminal_empty_allowed(self):
        single = build_manifest([stream(1)], caps())
        item = single["streams"][0]
        continuing = {item["stream_id"]: [
            raw_page([], 0, has_more=True, next_cursor="c1"),
            raw_page([], 1, has_more=False, next_cursor=None),
        ]}
        _, receipt, raw_pages = self.valid(single, continuing)
        with self.assertRaisesRegex(ValueError, "cannot be empty"):
            validate_execution_receipt(single, receipt, raw_pages)
        terminal = {item["stream_id"]: [
            raw_page([], 0, has_more=False, next_cursor=None)]}
        _, receipt, raw_pages = self.valid(single, terminal)
        self.assertTrue(validate_execution_receipt(
            single, receipt, raw_pages)["passed"])

    def test_has_more_cursor_and_pagination_fields_are_exact(self):
        single = build_manifest([stream(1)], caps())
        item = single["streams"][0]
        cases = (
            raw_page([row(item, "a")], 0, has_more=False, next_cursor="c1"),
            raw_page([row(item, "a")], 0, has_more=True, next_cursor=None),
            raw_page([row(item, "a")], 0, has_more=False, next_cursor=None,
                     limit=999),
            raw_page([row(item, "a")], 0, has_more=False, next_cursor=None,
                     offset=1000),
            raw_page([row(item, "a")], 0, has_more=False, next_cursor=None,
                     extra_pagination={"caller": True}),
            raw_page([row(item, "a")], 0, has_more=False, next_cursor=None,
                     extra_envelope={"extra": []}),
        )
        for raw in cases:
            pages = {item["stream_id"]: [raw]}
            _, receipt, raw_pages = self.valid(single, pages)
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                validate_execution_receipt(single, receipt, raw_pages)

    def test_response_cannot_exceed_declared_page_limit(self):
        single = build_manifest([stream(1)], caps(
            max_page_response_bytes=2_000_000,
            max_total_response_bytes=2_000_000))
        item = single["streams"][0]
        repeated_shape = [row(item, f"tx-{index}") for index in range(1001)]
        pages = {item["stream_id"]: [raw_page(
            repeated_shape, 0, has_more=False, next_cursor=None)]}
        _, receipt, raw_pages = self.valid(single, pages)
        with self.assertRaisesRegex(ValueError, "page size/pagination"):
            validate_execution_receipt(single, receipt, raw_pages)

    def test_pagination_limit_and_offset_require_exact_integers(self):
        single = build_manifest([stream(1)], caps())
        item = single["streams"][0]
        for limit, offset in ((1000.0, 0), (1000, 0.0), (1000, False)):
            pages = {item["stream_id"]: [raw_page(
                [], 0, has_more=False, next_cursor=None,
                limit=limit, offset=offset)]}
            _, receipt, raw_pages = self.valid(single, pages)
            with self.subTest(limit=limit, offset=offset), self.assertRaisesRegex(
                    ValueError, "page size/pagination"):
                validate_execution_receipt(single, receipt, raw_pages)

    def test_page_receipt_integer_fields_reject_bool_and_float(self):
        single = build_manifest([stream(1)], caps())
        item = single["streams"][0]
        pages = {item["stream_id"]: [raw_page(
            [], 0, has_more=False, next_cursor=None)]}
        _, receipt, raw_pages = self.valid(single, pages)
        for field, value in (
            ("request_ordinal", False),
            ("page_index", False),
            ("rows_received", False),
            ("response_bytes", float(
                receipt["page_receipts"][0]["response_bytes"])),
            ("status_code", 200.0),
        ):
            changed = copy.deepcopy(receipt)
            changed["page_receipts"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_execution_receipt(single, changed, raw_pages)
        for field in ("redirects_followed", "retries_used"):
            changed = copy.deepcopy(receipt)
            changed[field] = False
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_execution_receipt(single, changed, raw_pages)

    def test_receipt_query_numeric_float_does_not_equal_integer(self):
        manifest, receipt, raw_pages = self.valid()
        changed = copy.deepcopy(receipt)
        changed["page_receipts"][0]["query"]["limit"] = 1000.0
        # The URL remains the correctly realized integer URL; structural Python
        # equality alone must not accept the float-valued receipt object.
        with self.assertRaisesRegex(ValueError, "identity changed"):
            validate_execution_receipt(manifest, changed, raw_pages)

    def test_request_page_and_per_stream_caps_reject_overrun(self):
        single = build_manifest([stream(1)], caps(
            max_requests=2, max_pages=2, max_pages_per_stream=2))
        item = single["streams"][0]
        pages = {item["stream_id"]: [
            raw_page([row(item, "a")], 0, has_more=True, next_cursor="c1"),
            raw_page([row(item, "b")], 1, has_more=True, next_cursor="c2"),
            raw_page([row(item, "c")], 2, has_more=False, next_cursor=None),
        ]}
        _, receipt, raw_pages = self.valid(single, pages)
        with self.assertRaises(ValueError):
            validate_execution_receipt(single, receipt, raw_pages)

    def test_page_and_total_byte_caps_reject_overrun(self):
        single = build_manifest([stream(1)], caps(
            max_page_response_bytes=150, max_total_response_bytes=4096))
        item = single["streams"][0]
        pages = {item["stream_id"]: [raw_page(
            [row(item, "x" * 200)], 0, has_more=False, next_cursor=None)]}
        _, receipt, raw_pages = self.valid(single, pages)
        with self.assertRaisesRegex(ValueError, "byte/hash"):
            validate_execution_receipt(single, receipt, raw_pages)

        single = build_manifest([stream(1)], caps(
            max_page_response_bytes=450, max_total_response_bytes=450))
        item = single["streams"][0]
        pages = {item["stream_id"]: [
            raw_page([row(item, "a" * 100)], 0,
                     has_more=True, next_cursor="c1"),
            raw_page([row(item, "b" * 100)], 1,
                     has_more=False, next_cursor=None),
        ]}
        _, receipt, raw_pages = self.valid(single, pages)
        with self.assertRaises(ValueError):
            validate_execution_receipt(single, receipt, raw_pages)

    def test_elapsed_and_page_timing_caps_are_enforced(self):
        single = build_manifest([stream(1)], caps(max_elapsed_seconds=1))
        item = single["streams"][0]
        pages = {item["stream_id"]: [raw_page(
            [], 0, has_more=False, next_cursor=None)]}
        _, receipt, raw_pages = self.valid(single, pages)
        changed = copy.deepcopy(receipt)
        changed["completed_utc"] = "2026-09-22T20:00:02.000Z"
        changed["elapsed_milliseconds"] = 2000
        with self.assertRaisesRegex(ValueError, "elapsed"):
            validate_execution_receipt(single, changed, raw_pages)
        changed = copy.deepcopy(receipt)
        changed["page_receipts"][0]["request_started_ms"] = 10
        changed["page_receipts"][0]["request_completed_ms"] = 9
        with self.assertRaisesRegex(ValueError, "timing"):
            validate_execution_receipt(single, changed, raw_pages)

    def test_raw_bytes_hash_and_unreceipted_pages_are_rejected(self):
        manifest, receipt, raw_pages = self.valid()
        changed_raw = dict(raw_pages)
        first = receipt["page_receipts"][0]["page_id"]
        changed_raw[first] += b" "
        with self.assertRaisesRegex(ValueError, "byte/hash"):
            validate_execution_receipt(manifest, receipt, changed_raw)
        changed_raw = dict(raw_pages)
        changed_raw["unreceipted-page"] = b"{}"
        with self.assertRaisesRegex(ValueError, "unreceipted"):
            validate_execution_receipt(manifest, receipt, changed_raw)

    def test_duplicate_json_members_and_nonfinite_values_rejected(self):
        single = build_manifest([stream(1)], caps())
        item = single["streams"][0]
        raw_values = (
            b'{"data":[],"data":[],"pagination":{"limit":1000,"offset":0,"has_more":false,"next_cursor":null}}',
            b'{"data":[{"condition_id":"' + item["condition_id"].encode()
            + b'","token_id":"' + item["asset_ids"][0].encode()
            + b'","price":NaN}],"pagination":{"limit":1000,"offset":0,"has_more":false,"next_cursor":null}}',
        )
        for raw in raw_values:
            pages = {item["stream_id"]: [raw]}
            _, receipt, raw_pages = self.valid(single, pages)
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                validate_execution_receipt(single, receipt, raw_pages)

    def test_wrong_condition_token_and_duplicate_rows_rejected(self):
        single = build_manifest([stream(1)], caps())
        item = single["streams"][0]
        invalid_rows = (
            row(item, "a", condition_id="0x" + "f" * 64),
            row(item, "a", token_id="999999"),
        )
        for invalid in invalid_rows:
            pages = {item["stream_id"]: [raw_page(
                [invalid], 0, has_more=False, next_cursor=None)]}
            _, receipt, raw_pages = self.valid(single, pages)
            with self.subTest(row=invalid), self.assertRaisesRegex(
                    ValueError, "condition/assets"):
                validate_execution_receipt(single, receipt, raw_pages)
        repeated = row(item, "same")
        pages = {item["stream_id"]: [
            raw_page([repeated], 0, has_more=True, next_cursor="c1"),
            raw_page([repeated], 1, has_more=False, next_cursor=None),
        ]}
        _, receipt, raw_pages = self.valid(single, pages)
        with self.assertRaisesRegex(ValueError, "duplicate raw"):
            validate_execution_receipt(single, receipt, raw_pages)

    def test_receipt_counts_and_terminal_boundaries_are_exact(self):
        manifest, receipt, raw_pages = self.valid()
        for field, value in (
            ("terminal_status", "failed"),
            ("failure_code", "timeout"),
            ("requests_attempted", 2),
            ("pages_completed", 2),
            ("redirects_followed", 1),
            ("authentication_used", True),
            ("paid_access_used", True),
            ("write_operation_used", True),
            ("retries_used", 1),
            ("provider_cost_usd", "0.01"),
            ("dev_data_read", True),
            ("final_data_read", True),
            ("formal_data_admitted", True),
        ):
            changed = copy.deepcopy(receipt)
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_execution_receipt(manifest, changed, raw_pages)

    def test_receipt_page_order_and_stream_order_are_fixed(self):
        manifest, receipt, raw_pages = self.valid()
        changed = copy.deepcopy(receipt)
        changed["page_receipts"][0], changed["page_receipts"][1] = (
            changed["page_receipts"][1], changed["page_receipts"][0])
        with self.assertRaisesRegex(ValueError, "identity changed"):
            validate_execution_receipt(manifest, changed, raw_pages)
        changed = copy.deepcopy(receipt)
        changed["page_receipts"][0]["request_ordinal"] = 1
        with self.assertRaisesRegex(ValueError, "identity changed"):
            validate_execution_receipt(manifest, changed, raw_pages)

    def test_manifest_builder_is_deterministic_and_sorts_streams(self):
        first = build_manifest([stream(2), stream(1)], caps())
        second = build_manifest([stream(1), stream(2)], copy.deepcopy(caps()))
        self.assertEqual(first, second)
        self.assertEqual([item["stream_id"] for item in first["streams"]],
                         ["train-game-001", "train-game-002"])
        self.assertEqual(validate_manifest(first), first)

    def test_legacy_v1_offset_path_remains_separate_and_unchanged(self):
        legacy = legacy_v1.build_request_manifest(trade_builder_input())
        self.assertEqual(legacy_v1.SOURCE_ID, "polymarket_public_trades_v1")
        self.assertEqual(legacy["endpoint"]["path"], "/trades")
        self.assertEqual(legacy["request_count"], 6)
        self.assertEqual([item["query"]["offset"] for item in legacy["requests"]],
                         [0, 100, 0, 100, 0, 100])
        self.assertTrue(all("cursor" not in item["query"]
                            for item in legacy["requests"]))


if __name__ == "__main__":
    unittest.main()
