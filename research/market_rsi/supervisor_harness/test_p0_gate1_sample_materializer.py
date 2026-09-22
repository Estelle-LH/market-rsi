"""Offline tests for the deterministic Gate 1 Train sample materializer."""
from __future__ import annotations

import hashlib
import json
import unittest

from market_rsi import canonical, digest
from supervisor_harness.p0_gate1_sample_materializer import (
    CATALOG_SCHEMA, DATA_SCOPE, MATERIALIZATION_SCHEMA, RULE_ID, SOURCE_ID,
    canonical_output, materialize,
)


def row(number: int, game_date: str, game_id: str | None = None) -> dict:
    return {
        "game_date": game_date,
        "game_id": game_id or f"game-{number}",
        "split_role": "market_train",
        "condition_id": f"0x{number:064x}",
        "asset_ids": [str(1000 + number), str(2000 + number)],
        "start_timestamp": 1_700_000_000 + number * 1000,
        "end_timestamp": 1_700_000_600 + number * 1000,
    }


def catalog(rows: list[dict], **changes: object) -> dict:
    value = {
        "schema": CATALOG_SCHEMA,
        "catalog_id": "train-catalog-001",
        "source_id": SOURCE_ID,
        "data_scope": DATA_SCOPE,
        "rows": rows,
    }
    value.update(changes)
    return value


def frozen(value: dict) -> tuple[bytes, str]:
    raw = canonical(value).encode("utf-8")
    return raw, hashlib.sha256(raw).hexdigest()


class Gate1SampleMaterializerTests(unittest.TestCase):
    def test_stable_first_middle_last_and_exact_runner_inputs(self) -> None:
        rows = [row(5, "2025-09-14", "game-e"),
                row(1, "2025-09-04", "game-b"),
                row(3, "2025-09-07", "game-c"),
                row(2, "2025-09-04", "game-a"),
                row(4, "2025-09-11", "game-d")]
        raw, frozen_sha = frozen(catalog(rows))
        result = materialize(raw, frozen_sha, RULE_ID)
        self.assertEqual(result["schema"], MATERIALIZATION_SCHEMA)
        self.assertEqual(result["sample_ids"], ["game-a", "game-c", "game-e"])
        self.assertEqual(result["middle_index"], 2)
        self.assertEqual(result["sort_keys"], ["game_date", "game_id"])
        self.assertFalse(result["dev_or_final_exposed"])
        expected_rows = [rows[3], rows[2], rows[0]]
        self.assertEqual(result["selected_rows_sha256"], digest(expected_rows))
        for selected, request, commitment in zip(
                expected_rows, result["request_plan_inputs"],
                result["sample_commitments"], strict=True):
            self.assertEqual(set(request), {"sample_id", "condition_id", "asset_ids",
                                            "start_timestamp", "end_timestamp",
                                            "input_sha256"})
            self.assertEqual(request["sample_id"], selected["game_id"])
            self.assertEqual(request["input_sha256"], digest(selected))
            self.assertEqual(commitment, {"sample_id": selected["game_id"],
                                          "input_sha256": digest(selected)})

    def test_row_order_does_not_change_selection_or_request_inputs(self) -> None:
        rows = [row(number, f"2025-09-{number:02d}") for number in range(1, 7)]
        raw_a, sha_a = frozen(catalog(rows))
        raw_b, sha_b = frozen(catalog(list(reversed(rows))))
        first = materialize(raw_a, sha_a)
        second = materialize(raw_b, sha_b)
        self.assertEqual(first["sample_ids"], ["game-1", "game-4", "game-6"])
        self.assertEqual(first["request_plan_inputs"], second["request_plan_inputs"])
        self.assertNotEqual(first["catalog_file_sha256"], second["catalog_file_sha256"])

    def test_canonical_output_and_hash_are_exact_and_tamper_evident(self) -> None:
        value = catalog([row(number, f"2025-09-{number:02d}")
                         for number in range(1, 4)])
        raw, frozen_sha = frozen(value)
        result = materialize(raw, frozen_sha)
        body = {key: item for key, item in result.items()
                if key != "materialization_sha256"}
        self.assertEqual(result["materialization_sha256"], digest(body))
        output, output_sha = canonical_output(result)
        self.assertEqual(output, (canonical(result) + "\n").encode("utf-8"))
        self.assertEqual(output_sha, hashlib.sha256(output).hexdigest())
        self.assertEqual(json.loads(output), result)
        result["sample_ids"][0] = "tampered"
        with self.assertRaisesRegex(ValueError, "commitment changed"):
            canonical_output(result)

    def test_rejects_empty_and_out_of_range_samples(self) -> None:
        for rows, message in (([], "cannot be empty"),
                              ([row(1, "2025-09-01"),
                                row(2, "2025-09-02")], "out of range or duplicate")):
            raw, frozen_sha = frozen(catalog(rows))
            with self.subTest(rows=len(rows)), self.assertRaisesRegex(ValueError, message):
                materialize(raw, frozen_sha)

    def test_rejects_duplicate_samples_conditions_and_assets(self) -> None:
        duplicate_id = [row(1, "2025-09-01", "same"),
                        row(2, "2025-09-02", "same"), row(3, "2025-09-03")]
        duplicate_condition = [row(1, "2025-09-01"), row(2, "2025-09-02"),
                               row(3, "2025-09-03")]
        duplicate_condition[1]["condition_id"] = duplicate_condition[0]["condition_id"]
        duplicate_asset = [row(1, "2025-09-01"), row(2, "2025-09-02"),
                           row(3, "2025-09-03")]
        duplicate_asset[1]["asset_ids"] = ["42", "42"]
        for rows, message in ((duplicate_id, "duplicate exact sample ID"),
                              (duplicate_condition, "duplicate condition_id"),
                              (duplicate_asset, "distinct decimal token IDs")):
            raw, frozen_sha = frozen(catalog(rows))
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                materialize(raw, frozen_sha)

    def test_rejects_dev_final_or_non_train_scope(self) -> None:
        for role in ("route_dev", "sealed_final", "dev", "final"):
            rows = [row(1, "2025-09-01"), row(2, "2025-09-02"),
                    row(3, "2025-09-03")]
            rows[1]["split_role"] = role
            raw, frozen_sha = frozen(catalog(rows))
            with self.subTest(role=role), self.assertRaisesRegex(ValueError,
                                                                 "Dev/Final exposure"):
                materialize(raw, frozen_sha)
        raw, frozen_sha = frozen(catalog(
            [row(1, "2025-09-01"), row(2, "2025-09-02"), row(3, "2025-09-03")],
            data_scope="public_dev"))
        with self.assertRaisesRegex(ValueError, "Dev/Final exposure"):
            materialize(raw, frozen_sha)

    def test_rejects_ambiguous_rules_and_changed_catalog_bytes(self) -> None:
        value = catalog([row(1, "2025-09-01"), row(2, "2025-09-02"),
                         row(3, "2025-09-03")])
        raw, frozen_sha = frozen(value)
        for rule in ("first middle last", "first_and_last", "", None,
                     {"sort": ["game_date", "game_id"]}):
            with self.subTest(rule=rule), self.assertRaisesRegex(ValueError,
                                                                 "ambiguous or unsupported"):
                materialize(raw, frozen_sha, rule)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "hash changed"):
            materialize(raw + b"\n", frozen_sha)

    def test_rejects_wrong_schema_source_and_top_level_fields(self) -> None:
        rows = [row(1, "2025-09-01"), row(2, "2025-09-02"),
                row(3, "2025-09-03")]
        for changes, message in (({"schema": "future_schema"}, "wrong.*schema"),
                                 ({"source_id": "another_source"}, "not the admitted")):
            raw, frozen_sha = frozen(catalog(rows, **changes))
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, message):
                materialize(raw, frozen_sha)
        value = catalog(rows)
        value["url"] = "https://example.invalid/forbidden"
        raw, frozen_sha = frozen(value)
        with self.assertRaisesRegex(ValueError, "fields differ"):
            materialize(raw, frozen_sha)

    def test_rejects_invalid_or_ambiguous_catalog_rows(self) -> None:
        base = [row(1, "2025-09-01"), row(2, "2025-09-02"),
                row(3, "2025-09-03")]
        mutations = []
        for field, invalid, message in (
                ("game_date", "09/01/2025", "valid ISO date"),
                ("game_id", "bad id", "safe exact sample ID"),
                ("condition_id", "ABC", "lowercase 0x-prefixed"),
                ("asset_ids", ["0"], "decimal token IDs"),
                ("start_timestamp", 0, "out of range"),
                ("end_timestamp", 0, "out of range")):
            rows = [dict(item) for item in base]
            rows[0][field] = invalid
            mutations.append((rows, message))
        reversed_window = [dict(item) for item in base]
        reversed_window[0]["end_timestamp"] = reversed_window[0]["start_timestamp"]
        mutations.append((reversed_window, "empty or reversed"))
        extra_field = [dict(item) for item in base]
        extra_field[0]["outcome"] = "FORBIDDEN"
        mutations.append((extra_field, "fields differ"))
        for rows, message in mutations:
            raw, frozen_sha = frozen(catalog(rows))
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                materialize(raw, frozen_sha)

    def test_rejects_duplicate_json_fields_and_nonfinite_values(self) -> None:
        raw = (b'{"schema":"market_p0_gate1_train_catalog_v1",'
               b'"catalog_id":"x","catalog_id":"y",'
               b'"source_id":"polymarket_public_trades_v1",'
               b'"data_scope":"public_train_only","rows":[]}')
        with self.assertRaisesRegex(ValueError, "duplicate JSON field"):
            materialize(raw, hashlib.sha256(raw).hexdigest())
        raw = (b'{"schema":"market_p0_gate1_train_catalog_v1",'
               b'"catalog_id":"x","source_id":"polymarket_public_trades_v1",'
               b'"data_scope":"public_train_only","rows":NaN}')
        with self.assertRaisesRegex(ValueError, "non-finite"):
            materialize(raw, hashlib.sha256(raw).hexdigest())


if __name__ == "__main__":
    unittest.main()
