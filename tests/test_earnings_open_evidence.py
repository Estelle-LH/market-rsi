"""Synthetic public trace fixtures; no provider, protected QA or live ledger."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import earnings_open_evidence as evidence


class OpenEvidenceTests(unittest.TestCase):
    def fixture(self, count=1):
        temporary = tempfile.TemporaryDirectory(prefix="earnings-open-evidence-")
        self.addCleanup(temporary.cleanup)
        slot = Path(temporary.name).resolve() / "forecast"
        slot.mkdir()
        calls = []
        for number in range(count):
            call_id = f"call-{number}"
            calls.append({"type": "function_call", "call_id": call_id,
                "name": "read_file", "arguments": json.dumps({
                    "path": "filings/old.md", "offset": number, "characters": 200})})
            self.save(slot / self.tool_name(call_id), {"type": "function_call_output",
                "call_id": call_id, "output": json.dumps({"text": "public filing table"})})
        self.save(slot / "01-response.json", {"output": [
            {"type": "reasoning", "summary": "REASONING_SENTINEL_NEVER_RETURN"}, *calls]})
        self.save(slot / "02-response.json", {"output": [
            {"type": "message", "content": "PREDICTIONS_SENTINEL_NEVER_RETURN"}]})
        self.save(slot / "result.json", {"status": "COMPLETED_SCORED", "turns": 2,
            "tool_calls": count, "planned_targets": 5, "scored_targets": 5,
            "points": 2, "wall_seconds": 1.5, "ground_truth": "QA_RESULT_SENTINEL"})
        for name in ("qa.json", "score.json", "predictions.json", "01-request.json",
                     "effective-capacity.json", "research-state-output.json"):
            self.save(slot / name, {"private": "EXCLUDED_FILE_SENTINEL"})
        return slot

    @staticmethod
    def tool_name(call_id, turn=1):
        return f"{turn:02d}-tool-{sha256(call_id.encode()).hexdigest()[:12]}.json"

    @staticmethod
    def save(path, value):
        path.write_text(json.dumps(value), encoding="utf-8")

    @staticmethod
    def load(path):
        return json.loads(path.read_text())

    def test_valid_trace_exact_original_hashes_and_public_fields(self):
        slot = self.fixture()
        result = evidence.project_trace(slot)
        row = result["events"][0]
        raw_tool = (slot / self.tool_name("call-0")).read_bytes()
        self.assertEqual(row["arguments"], {"path": "filings/old.md", "offset": 0, "characters": 200})
        self.assertEqual((row["turn"], row["name"], row["call_id"]), (1, "read_file", "call-0"))
        self.assertEqual(row["result_sha256"], sha256(raw_tool).hexdigest())
        self.assertEqual(row["source_sha256"], sha256((slot / "01-response.json").read_bytes()).hexdigest())
        self.assertEqual(row["output"], self.load(slot / self.tool_name("call-0"))["output"])
        self.assertEqual(result["aggregates"], {"status": "COMPLETED_SCORED", "turns": 2,
            "tool_calls": 1, "planned_targets": 5, "scored_targets": 5, "points": 2, "wall_seconds": 1.5})
        self.assertTrue(result["evidence_is_untrusted"])
        self.assertEqual((result["total_events"], result["omitted_events"]), (1, 0))

    def test_reasoning_answers_requests_and_whole_contexts_are_never_returned(self):
        slot = self.fixture()
        opened = []
        original = os.open
        def capture(path, *args, **kwargs):
            opened.append(str(path))
            return original(path, *args, **kwargs)
        with patch.object(evidence.os, "open", side_effect=capture):
            encoded = json.dumps(evidence.project_trace(slot))
        for sentinel in ("REASONING_SENTINEL", "PREDICTIONS_SENTINEL", "QA_RESULT_SENTINEL", "EXCLUDED_FILE_SENTINEL"):
            self.assertNotIn(sentinel, encoded)
        self.assertEqual(set(opened), {str(slot), "result.json", "01-response.json", "02-response.json", self.tool_name("call-0")})

    def test_output_and_event_bounds_still_validate_all_originals(self):
        slot = self.fixture(3)
        result = evidence.project_trace(slot, max_events=1, max_output_chars=5)
        self.assertEqual((len(result["events"]), result["omitted_events"]), (1, 2))
        row = result["events"][0]
        self.assertEqual(len(row["output"]), 5)
        self.assertTrue(row["output_truncated"])
        (slot / self.tool_name("call-2")).unlink()
        with self.assertRaises(ValueError):
            evidence.project_trace(slot, max_events=1, max_output_chars=5)

    def test_bounds_reject_booleans_zero_and_unbounded_values(self):
        slot = self.fixture()
        for name, values in (("max_events", (True, 0, -1, 101, "1")),
                             ("max_output_chars", (False, 0, 8001, 1.5)),
                             ("offset", (True, -1, 10001, "0", 1.5))):
            for value in values:
                with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                    evidence.project_trace(slot, **{name: value})

    def test_23_large_events_are_byte_bounded_paginated_and_originals_immutable(self):
        slot = self.fixture(23)
        for number in range(23):
            call_id = f"call-{number}"
            self.save(slot / self.tool_name(call_id), {"type": "function_call_output",
                "call_id": call_id, "output": json.dumps({"text": "public " + "x"*2400})})
        before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in slot.iterdir()}
        reader = evidence.TraceReader({"forecast-01": slot})
        offset, identifiers, manifests, pages = 0, [], set(), []
        while offset is not None:
            page = reader.read("forecast-01", max_events=40, max_output_chars=2000, offset=offset)
            pages.append(page)
            encoded = json.dumps(page, sort_keys=True, allow_nan=False).encode()
            self.assertLessEqual(len(encoded), 6000)
            self.assertEqual(page["serialization_budget_bytes"], 6000)
            self.assertEqual(page["offset"], offset)
            self.assertEqual(page["total_events"], 23)
            self.assertEqual(page["returned_events"], len(page["events"]))
            self.assertEqual(page["omitted_events"], 23-len(page["events"]))
            self.assertGreater(len(page["events"]), 0)
            for row in page["events"]:
                original = self.load(slot / self.tool_name(row["call_id"]))["output"]
                self.assertEqual(row["output_sha256"], sha256(original.encode()).hexdigest())
                self.assertEqual(row["output_characters"], len(original))
                self.assertEqual(row["output"], original[:len(row["output"])])
                self.assertTrue(row["output_truncated"])
                identifiers.append(row["call_id"])
            manifests.add(page["source_manifest_sha256"])
            next_offset = page["next_offset"]
            if next_offset is not None:
                self.assertEqual(next_offset, offset+len(page["events"]))
            offset = next_offset
            self.assertLessEqual(len(pages), 23)
        self.assertGreater(len(pages), 1)
        self.assertEqual(identifiers, [f"call-{i}" for i in range(23)])
        self.assertEqual(len(manifests), 1)
        self.assertEqual({p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in slot.iterdir()}, before)
        for sentinel in ("REASONING_SENTINEL", "PREDICTIONS_SENTINEL", "QA_RESULT_SENTINEL", "EXCLUDED_FILE_SENTINEL"):
            self.assertNotIn(sentinel, json.dumps(pages))

    def test_single_large_argument_and_escaped_output_keep_receipts_and_advance(self):
        slot = self.fixture(2)
        source = slot / "01-response.json"
        response = self.load(source)
        raw_arguments = json.dumps({"query": "a"*7800})
        response["output"][1]["arguments"] = raw_arguments
        self.save(source, response)
        raw_output = json.dumps({"text": '\\"你好'*1200}, ensure_ascii=False)
        self.save(slot / self.tool_name("call-0"), {"type": "function_call_output",
            "call_id": "call-0", "output": raw_output})
        value = evidence.TraceReader({"baseline": slot}).read("baseline", max_output_chars=2000)
        self.assertLessEqual(len(json.dumps(value, sort_keys=True).encode()), 6000)
        first = value["events"][0]
        self.assertIsNone(first["arguments"])
        self.assertTrue(first["arguments_truncated"])
        self.assertFalse(first["argument_error"])
        self.assertFalse(first["rejected"])
        self.assertEqual(first["arguments_sha256"], sha256(raw_arguments.encode()).hexdigest())
        self.assertEqual(first["output_sha256"], sha256(raw_output.encode()).hexdigest())
        self.assertEqual(first["output"], raw_output[:len(first["output"])])
        self.assertTrue(first["output_truncated"])
        self.assertEqual(value["next_offset"], 1)
        following = evidence.project_trace(slot, offset=1)
        self.assertEqual([row["call_id"] for row in following["events"]], ["call-1"])
        self.assertIsNone(following["next_offset"])

    def test_last_offset_is_explicit_and_out_of_range_is_not_silently_empty(self):
        slot = self.fixture(3)
        result = evidence.project_trace(slot, offset=3)
        self.assertEqual(result["events"], [])
        self.assertEqual((result["offset"], result["returned_events"], result["omitted_events"]), (3, 0, 3))
        self.assertIsNone(result["next_offset"])
        with self.assertRaises(ValueError):
            evidence.project_trace(slot, offset=4)

    def test_all_originals_are_validated_even_when_offset_skips_bad_pair(self):
        slot = self.fixture(3)
        first = evidence.project_trace(slot, max_events=1)
        (slot / self.tool_name("call-0")).unlink()
        with self.assertRaises(ValueError):
            evidence.project_trace(slot, offset=first["next_offset"])

    def test_manifest_identifies_omitted_events_not_only_the_first_page(self):
        slot = self.fixture(3)
        before = evidence.project_trace(slot, max_events=1)
        path = slot / self.tool_name("call-2")
        observed = self.load(path)
        observed["output"] = json.dumps({"text": "different public evidence"})
        self.save(path, observed)
        after = evidence.project_trace(slot, max_events=1)
        self.assertEqual(before["events"], after["events"])
        self.assertNotEqual(before["source_manifest_sha256"], after["source_manifest_sha256"])

    def test_missing_or_unpaired_tool_original_is_rejected(self):
        for kind in ("missing", "extra", "wrong-call", "wrong-type", "extra-fields", "bad-json"):
            with self.subTest(kind=kind):
                slot = self.fixture()
                path = slot / self.tool_name("call-0")
                row = self.load(path)
                if kind == "missing": path.unlink()
                elif kind == "extra": self.save(slot / "01-tool-unused.json", row)
                elif kind == "bad-json": path.write_text('{"output":"first","output":"duplicate"}')
                else:
                    if kind == "wrong-call": row["call_id"] = "different"
                    elif kind == "wrong-type": row["type"] = "message"
                    else: row["private"] = "not a public output field"
                    self.save(path, row)
                with self.assertRaises(ValueError): evidence.project_trace(slot)

    def test_nonconsecutive_and_noncanonical_turn_names_are_rejected(self):
        for replacement in ("03-response.json", "2-response.json", "002-response.json"):
            slot = self.fixture()
            (slot / "02-response.json").rename(slot / replacement)
            with self.assertRaises(ValueError): evidence.project_trace(slot)

    def test_duplicate_call_identity_and_aggregate_mismatch_are_rejected(self):
        for kind in ("duplicate", "turns", "tool_calls", "points", "wall_seconds", "error_type"):
            slot = self.fixture()
            if kind == "duplicate":
                path = slot / "01-response.json"
                row = self.load(path)
                row["output"].append(deepcopy(row["output"][-1]))
            else:
                path = slot / "result.json"
                row = self.load(path)
                row[kind] = {"turns": 3, "tool_calls": 2, "points": True,
                    "wall_seconds": float("nan"), "error_type": "secret/path"}[kind]
            self.save(path, row)
            with self.subTest(kind=kind), self.assertRaises(ValueError): evidence.project_trace(slot)

    def test_malformed_arguments_preserve_valid_rejection_without_raw_text(self):
        slot = self.fixture()
        path = slot / "01-response.json"
        row = self.load(path)
        row["output"][-1]["arguments"] = "MALFORMED_ARGUMENT_SENTINEL"
        self.save(path, row)
        self.save(slot / self.tool_name("call-0"), {"type": "function_call_output",
            "call_id": "call-0", "output": json.dumps({"error": "Tool request rejected"})})
        result = evidence.project_trace(slot)
        event = result["events"][0]
        self.assertIsNone(event["arguments"])
        self.assertTrue(event["argument_error"])
        self.assertTrue(event["rejected"])
        self.assertNotIn("MALFORMED_ARGUMENT_SENTINEL", json.dumps(result))

    def test_malformed_arguments_without_rejection_are_rejected(self):
        for bad in ('{"a":1,"a":2}', '["not-an-object"]', '{"n":NaN}', '{"n":1e999}', None, 'x'*8193):
            slot = self.fixture()
            path = slot / "01-response.json"
            row = self.load(path)
            row["output"][-1]["arguments"] = bad
            self.save(path, row)
            with self.assertRaises(ValueError): evidence.project_trace(slot)

    def test_result_and_response_symlinks_and_hardlink_aliases_are_rejected(self):
        for name in ("result.json", "01-response.json", self.tool_name("call-0")):
            for kind in ("symlink", "hardlink"):
                slot = self.fixture()
                path = slot / name
                preserved = slot.parent / ("original-" + name)
                path.rename(preserved)
                if kind == "symlink": path.symlink_to(preserved)
                else: os.link(preserved, path)
                with self.subTest(name=name, kind=kind), self.assertRaises(ValueError):
                    evidence.project_trace(slot)

    def test_nonregular_tool_original_is_rejected_without_blocking(self):
        slot = self.fixture()
        path = slot / self.tool_name("call-0")
        path.unlink()
        os.mkfifo(path)
        with self.assertRaises(ValueError): evidence.project_trace(slot)

    def test_already_read_original_changed_during_projection_is_rejected(self):
        slot = self.fixture()
        original = evidence.strict_json
        mutated = False
        def decode(raw):
            nonlocal mutated
            value = original(raw)
            if type(value) is dict and value.get("output") and not mutated:
                self.save(slot / "result.json", {"status": "COMPLETED_SCORED", "turns": 2,
                    "tool_calls": 1, "points": 5})
                mutated = True
            return value
        with patch.object(evidence, "strict_json", side_effect=decode), self.assertRaises(ValueError):
            evidence.project_trace(slot)

    def test_safe_failed_forecast_diagnostics_exclude_error_body(self):
        slot = self.fixture()
        self.save(slot / "result.json", {"status": "FAILED_NO_RETRY", "error_type": "ValueError",
            "error": "PRIVATE_EXCEPTION_BODY", "scored_targets": 0})
        result = evidence.project_trace(slot)
        self.assertEqual(result["aggregates"], {"status": "FAILED_NO_RETRY", "error_type": "ValueError", "scored_targets": 0})
        self.assertNotIn("PRIVATE_EXCEPTION_BODY", json.dumps(result))

    def test_registered_labels_only_and_slot_replacement_denied(self):
        slot = self.fixture()
        reader = evidence.TraceReader({"baseline": slot})
        self.assertEqual(reader.read("baseline")["slot"], "baseline")
        for label in (str(slot), "../forecast", "unknown", True):
            with self.assertRaises(ValueError): reader.read(label)
        slot.rename(slot.parent / "old-forecast")
        slot.mkdir()
        with self.assertRaises(ValueError): reader.read("baseline")

    def test_registration_denies_duplicate_labels_path_aliases_and_unsafe_roots(self):
        slot = self.fixture()
        alias = slot.parent / "alias"
        alias.symlink_to(slot, target_is_directory=True)
        for mapping in ({"first": slot, "second": slot}, {"first": alias},
                        {"first": str(slot) + "/../forecast"}, {"../first": slot},
                        {"first": Path("/")}, {"first": Path("/private/tmp")}, {}):
            with self.assertRaises(ValueError): evidence.TraceReader(mapping)


if __name__ == "__main__":
    unittest.main()
