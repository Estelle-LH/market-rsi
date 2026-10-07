"""Synthetic-only boundary tests: no research data, model sessions or fits."""
import concurrent.futures
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from . import controller_research_evidence_tools as tools


class EvidenceToolsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.content = "Synthetic café evidence. 世界\nSecond line.\n"
        self.source = self.root / "source.txt"
        self.source.write_text(self.content, encoding="utf-8")
        self.policy_path = self.root / "policy.json"
        self.policy = {
            "schema": tools.SCHEMA,
            "evidence": [{"id": "fixture-1", "path": str(self.source),
                          "sha256": tools.digest(self.source.read_bytes()), "kind": "evidence",
                          "controller_payload_approved": True}],
            "limits": {"file_bytes": 1024, "page_bytes": 32,
                       "output_bytes": 8192, "tool_calls": 30},
            "audit_path": str(self.root / "audit.jsonl"),
        }

    def save(self):
        self.policy_path.write_bytes(tools.encode(self.policy))
        return tools.digest(self.policy_path.read_bytes())

    def broker(self):
        broker = tools.EvidenceBroker(str(self.policy_path), self.save())
        self.addCleanup(broker.close)
        return broker

    def receipts(self):
        return [json.loads(line) for line in (self.root / "audit.jsonl").read_text().splitlines()]

    def test_list_hides_filesystem_paths(self):
        broker = self.broker()
        result = broker.call("list_evidence", {})
        self.assertTrue(result["ok"])
        self.assertEqual(result["evidence"][0]["id"], "fixture-1")
        self.assertNotIn(str(self.root), json.dumps(result))
        self.assertEqual(self.receipts()[0]["payload_sha256"], tools.digest(tools.encode(result)))

    def test_unicode_pagination_exact_reconstruction(self):
        broker = self.broker()
        pieces, offset = [], 0
        for _ in range(30):
            page = broker.call("read_evidence", {"evidence_id": "fixture-1", "offset": offset, "max_bytes": 4})
            self.assertTrue(page["ok"])
            self.assertLessEqual(len(page["text"].encode("utf-8")), 4)
            pieces.append(page["text"])
            if page["eof"]:
                break
            self.assertGreater(page["next_offset"], offset)
            offset = page["next_offset"]
        self.assertEqual("".join(pieces), self.content)

    def test_unknown_id_does_not_open_source(self):
        broker = self.broker()
        with mock.patch.object(tools, "read_file", wraps=tools.read_file) as reader:
            result = broker.call("read_evidence", {"evidence_id": "../protected"})
        self.assertFalse(result["ok"])
        self.assertEqual([c.args[0] for c in reader.call_args_list], [str(self.policy_path)])
        self.assertEqual(self.receipts()[0]["status"], "denied")

    def test_model_supplied_path_denied_before_source_read(self):
        broker = self.broker()
        with mock.patch.object(tools, "read_file", wraps=tools.read_file) as reader:
            result = broker.call("read_evidence", {"evidence_id": "fixture-1", "path": "/protected.txt"})
        self.assertFalse(result["ok"])
        self.assertEqual(len(reader.call_args_list), 1)

    def test_policy_hash_mismatch_does_not_create_audit(self):
        self.save()
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            tools.EvidenceBroker(str(self.policy_path), "0" * 64)
        self.assertFalse((self.root / "audit.jsonl").exists())

    def test_policy_drift_denied_before_evidence_read(self):
        broker = self.broker()
        self.policy["limits"]["tool_calls"] = 100
        self.save()
        with mock.patch.object(tools, "read_file", wraps=tools.read_file) as reader:
            result = broker.call("read_evidence", {"evidence_id": "fixture-1"})
        self.assertEqual(result["error"], "policy drift")
        self.assertEqual(len(reader.call_args_list), 1)
        self.assertEqual(broker.limits["tool_calls"], 30)

    def test_source_drift_returns_no_source_text(self):
        broker = self.broker()
        self.source.write_text("changed sensitive fixture")
        result = broker.call("read_evidence", {"evidence_id": "fixture-1"})
        self.assertEqual(result, {"ok": False, "error": "source drift"})

    def test_source_leaf_symlink_denied(self):
        broker = self.broker()
        self.source.unlink()
        self.source.symlink_to(self.policy_path)
        result = broker.call("read_evidence", {"evidence_id": "fixture-1"})
        self.assertFalse(result["ok"])
        self.assertNotIn("schema", json.dumps(result))

    def test_parent_symlink_denied(self):
        nested = self.root / "real"
        nested.mkdir()
        child = nested / "source.txt"
        child.write_text("fixture")
        link = self.root / "link"
        link.symlink_to(nested, target_is_directory=True)
        self.policy["evidence"][0]["path"] = str(link / "source.txt")
        with self.assertRaises(OSError):
            self.broker()

    def test_parent_replaced_by_symlink_after_admission_denied(self):
        nested = self.root / "nested"
        nested.mkdir()
        child = nested / "source.txt"
        child.write_text(self.content)
        self.policy["evidence"][0]["path"] = str(child)
        broker = self.broker()
        nested.rename(self.root / "moved")
        nested.symlink_to(self.root / "moved", target_is_directory=True)
        self.assertFalse(broker.call("read_evidence", {"evidence_id": "fixture-1"})["ok"])

    def test_traversal_policy_denied_before_leaf_open(self):
        self.policy["evidence"][0]["path"] = str(self.root) + "/../protected.txt"
        with self.assertRaisesRegex(ValueError, "noncanonical"):
            self.broker()

    def test_unapproved_records_and_kinds_denied(self):
        for field, value in [("kind", "raw_train"), ("controller_payload_approved", False),
                             ("controller_payload_approved", 1), ("sha256", "bad")]:
            with self.subTest(field=field, value=value):
                original = self.policy["evidence"][0][field]
                self.policy["evidence"][0][field] = value
                with self.assertRaises(ValueError):
                    self.broker()
                self.policy["evidence"][0][field] = original

    def test_duplicate_ids_denied(self):
        self.policy["evidence"].append(dict(self.policy["evidence"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.broker()

    def test_policy_invalid_limits_and_unknown_fields_denied(self):
        for key, value in [("tool_calls", True), ("output_bytes", 0),
                           ("file_bytes", 16777217), ("page_bytes", 3)]:
            with self.subTest(key=key, value=value):
                old = self.policy["limits"][key]
                self.policy["limits"][key] = value
                with self.assertRaises(ValueError):
                    self.broker()
                self.policy["limits"][key] = old
        self.policy["extra"] = "not admitted"
        with self.assertRaises(ValueError):
            self.broker()

    def test_nonregular_file_denied_without_blocking(self):
        broker = self.broker()
        self.source.unlink()
        os.mkfifo(self.source)
        self.assertFalse(broker.call("read_evidence", {"evidence_id": "fixture-1"})["ok"])

    def test_file_size_cap_denied(self):
        self.policy["limits"]["file_bytes"] = 8
        broker = self.broker()
        self.assertFalse(broker.call("read_evidence", {"evidence_id": "fixture-1"})["ok"])

    def test_invalid_page_parameters_do_not_open_evidence(self):
        broker = self.broker()
        for args in [{"offset": -1}, {"offset": True}, {"max_bytes": 0},
                     {"max_bytes": 33}, {"max_bytes": True}]:
            with self.subTest(args=args), mock.patch.object(tools, "read_file", wraps=tools.read_file) as reader:
                result = broker.call("read_evidence", {"evidence_id": "fixture-1", **args})
                self.assertFalse(result["ok"])
                self.assertEqual(len(reader.call_args_list), 1)

    def test_offset_beyond_end_denied(self):
        broker = self.broker()
        self.assertFalse(broker.call("read_evidence", {"evidence_id": "fixture-1", "offset": 10000})["ok"])

    def test_invalid_utf8_not_disclosed(self):
        self.source.write_bytes(b"\xfffixture")
        self.policy["evidence"][0]["sha256"] = tools.digest(self.source.read_bytes())
        broker = self.broker()
        self.assertFalse(broker.call("read_evidence", {"evidence_id": "fixture-1"})["ok"])

    def test_invalid_calls_consume_nonresettable_budget(self):
        self.policy["limits"]["tool_calls"] = 2
        broker = self.broker()
        self.assertFalse(broker.call("not-a-tool", {})["ok"])
        self.assertFalse(broker.call("read_evidence", ["fixture-1"])["ok"])
        with mock.patch.object(tools, "read_file", wraps=tools.read_file) as reader:
            with self.assertRaises(tools.BudgetStop):
                broker.call("list_evidence", {})
            self.assertEqual(reader.call_count, 0)
        with self.assertRaises(tools.BudgetStop):
            broker.call("read_evidence", {"evidence_id": "fixture-1"})
        self.assertEqual(len(self.receipts()), 3)

    def test_output_limit_covers_success_and_denial_payloads(self):
        self.policy["limits"]["output_bytes"] = 80
        broker = self.broker()
        denial = broker.call("no", {})
        self.assertEqual(broker.bytes, len(tools.encode(denial)))
        with self.assertRaises(tools.BudgetStop):
            broker.call("list_evidence", {})
        receipt = self.receipts()[-1]
        self.assertEqual(receipt["payload_bytes"], 0)
        self.assertEqual(receipt["status"], "denied")
        self.assertLessEqual(broker.bytes, 80)

    def test_concurrent_calls_share_one_process_budget(self):
        self.policy["limits"]["tool_calls"] = 3
        broker = self.broker()
        def call(_):
            try:
                return broker.call("read_evidence", {"evidence_id": "fixture-1"})["ok"]
            except tools.BudgetStop:
                return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(call, range(12)))
        self.assertEqual(sum(results), 3)
        self.assertEqual([r["sequence"] for r in self.receipts()], [1, 2, 3, 4])

    def test_exactly_exhausted_output_denied_before_read(self):
        listed = {"ok": True, "evidence": [{k: self.policy["evidence"][0][k] for k in ("id", "kind", "sha256")}]}
        self.policy["limits"]["output_bytes"] = len(tools.encode(listed))
        broker = self.broker()
        broker.call("list_evidence", {})
        with mock.patch.object(tools, "read_file", wraps=tools.read_file) as reader:
            with self.assertRaises(tools.BudgetStop):
                broker.call("read_evidence", {"evidence_id": "fixture-1"})
            self.assertEqual(reader.call_count, 0)

    def test_same_policy_cannot_restart_and_reset_budget(self):
        broker = self.broker()
        broker.call("list_evidence", {})
        with self.assertRaises(FileExistsError):
            tools.EvidenceBroker(str(self.policy_path), tools.digest(self.policy_path.read_bytes()))

    def test_audit_failure_emits_no_result_and_poison_session(self):
        broker = self.broker()
        with mock.patch.object(tools.os, "fsync", side_effect=OSError("synthetic persistence failure")):
            with self.assertRaisesRegex(tools.BudgetStop, "audit persistence"):
                broker.call("read_evidence", {"evidence_id": "fixture-1"})
        with mock.patch.object(tools, "read_file", wraps=tools.read_file) as reader:
            with self.assertRaises(tools.BudgetStop):
                broker.call("list_evidence", {})
            self.assertEqual(reader.call_count, 0)
        self.assertEqual(broker.bytes, 0)

    def test_replaced_audit_path_fails_closed(self):
        broker = self.broker()
        audit = self.root / "audit.jsonl"
        audit.rename(self.root / "old-audit")
        audit.write_text("replacement")
        with self.assertRaisesRegex(tools.BudgetStop, "audit persistence"):
            broker.call("list_evidence", {})

    def test_audit_leaf_symlink_denied_without_target_overwrite(self):
        (self.root / "audit.jsonl").symlink_to(self.source)
        with self.assertRaises(OSError):
            self.broker()
        self.assertEqual(self.source.read_text(), self.content)

    def test_audit_zero_write_returns_no_response(self):
        broker = self.broker()
        with mock.patch.object(tools.os, "write", return_value=0):
            with self.assertRaises(tools.BudgetStop):
                broker.call("list_evidence", {})
        self.assertEqual(broker.bytes, 0)
        self.assertTrue(broker.stopped)

    def test_audit_never_duplicates_evidence_text(self):
        broker = self.broker()
        broker.call("read_evidence", {"evidence_id": "fixture-1"})
        audit = (self.root / "audit.jsonl").read_text()
        self.assertNotIn("Synthetic café", audit)
        self.assertNotIn(str(self.root), audit)

    def test_rpc_malformed_requests_and_notification(self):
        broker = self.broker()
        source = io.StringIO('[]\nnot-json\n{"jsonrpc":"2.0","method":"notifications/initialized"}\n'
                             '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":null}\n'
                             '{"jsonrpc":"2.0","id":4,"method":"ping"}\n')
        sink = io.StringIO()
        tools.serve(broker, source, sink)
        responses = [json.loads(line) for line in sink.getvalue().splitlines()]
        self.assertEqual(len(responses), 4)
        self.assertIn("error", responses[0])
        self.assertTrue(responses[2]["result"]["isError"])
        self.assertEqual(responses[-1]["result"], {})
        self.assertEqual(broker.calls, 1)

    def test_oversized_rpc_terminates_without_tail_execution(self):
        broker = self.broker()
        source = io.StringIO(" " * 100001 + '{"jsonrpc":"2.0","id":1,"method":"tools/call",'
                             '"params":{"name":"list_evidence"}}\n')
        sink = io.StringIO()
        tools.serve(broker, source, sink)
        self.assertEqual(len(sink.getvalue().splitlines()), 1)
        self.assertEqual(broker.calls, 0)

    def test_rpc_invalid_ids_nonfinite_and_duplicates_never_dispatch(self):
        broker = self.broker()
        lines = [
            '{"jsonrpc":"2.0","id":NaN,"method":"tools/call","params":{"name":"list_evidence"}}',
            '{"jsonrpc":"2.0","id":1e9999,"method":"tools/call","params":{"name":"list_evidence"}}',
            '{"jsonrpc":"2.0","id":[],"method":"tools/call","params":{"name":"list_evidence"}}',
            '{"jsonrpc":"2.0","id":true,"method":"tools/call","params":{"name":"list_evidence"}}',
            '{"jsonrpc":"2.0","id":1,"method":"ping","method":"tools/call","params":{"name":"list_evidence"}}',
            '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"read_evidence","arguments":{"evidence_id":"fixture-1","offset":Infinity}}}',
        ]
        sink = io.StringIO()
        tools.serve(broker, io.StringIO("\n".join(lines) + "\n"), sink)
        self.assertEqual(broker.calls, 0)
        self.assertEqual(len(sink.getvalue().splitlines()), len(lines))
        self.assertTrue(all("error" in json.loads(line) for line in sink.getvalue().splitlines()))
        self.assertTrue(all(json.loads(line)["id"] is None for line in sink.getvalue().splitlines()))

    def test_stdio_subprocess_roundtrip(self):
        policy_sha = self.save()
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
                "name": "read_evidence", "arguments": {"evidence_id": "fixture-1"}}},
            {"jsonrpc": "2.0", "id": 4, "method": "ping"},
        ]
        command = [sys.executable, tools.__file__, "--policy", str(self.policy_path), "--policy-sha256", policy_sha]
        result = subprocess.run(command, input="".join(json.dumps(r) + "\n" for r in requests),
                                text=True, capture_output=True, timeout=10, check=True)
        responses = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual([r["id"] for r in responses], [1, 2, 3, 4])
        self.assertEqual(responses[0]["result"]["serverInfo"]["name"], "controller-research-evidence")
        self.assertEqual(len(responses[1]["result"]["tools"]), 2)
        payload = json.loads(responses[2]["result"]["content"][0]["text"])
        self.assertTrue(payload["ok"])
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
