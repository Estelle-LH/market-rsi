"""Synthetic role transport fixtures; no account/model calls or real training."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from supervisor_harness import price_account_roles as p

SCHEMA = p.c._object({"schema": {"type": "string", "const": "synthetic_role_v1"}, "answer": p.c.TEXT})
RESPONSE = {"schema": "synthetic_role_v1", "answer": "synthetic fixture; not a model decision"}

# Real subprocess/stdio exercise, but this inert child is not Codex and performs
# no network/account call. The production Popen is replaced only inside tests.
RPC_FIXTURE = r'''
import json, sys
settings = json.loads(sys.argv[1])
def emit(message):
    print(json.dumps(message), flush=True)
for line in sys.stdin:
    request = json.loads(line)
    method = request.get("method")
    if method == "initialize":
        emit({"id": 0, "result": {"synthetic": True}})
    elif method == "thread/start":
        emit({"id": 1, "result": {"model": settings["model"], "instructionSources": [],
            "thread": {"id": "synthetic-native-thread", "environments": settings["environments"]}}})
        emit({"method": "thread/started", "params": {"thread": {"id": "synthetic-native-thread"}}})
    elif method == "turn/start":
        emit({"id": 2, "result": {"turn": {"id": "synthetic-turn"}}})
        emit({"method": "turn/started", "params": {"turn": {"id": "synthetic-turn"}}})
        emit({"method": "item/completed", "params": {"item": {"type": "agentMessage", "phase": "final",
            "text": json.dumps(settings["response"])}}})
        emit({"method": "thread/tokenUsage/updated", "params": {"tokenUsage": {"last": {"input_tokens": 7, "output_tokens": 3}}}})
        emit({"method": "turn/completed", "params": {"turn": {"status": settings["status"]}}})
'''


class RoleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve() / "synthetic-batch"
        self.root.mkdir(); self.calls = 0
        now = datetime.now(timezone.utc)
        fmt = lambda dt: dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        self.grant = {"schema": "market_rsi_bounded_coevo_pilot_authorization_v1", "granted": True,
            "batch_id": self.root.name, "start_utc": fmt(now - timedelta(seconds=5)),
            "selection_cutoff_utc": fmt(now + timedelta(minutes=25)), "deadline_utc": fmt(now + timedelta(minutes=30)),
            "account_transfer": {"requested_model": p.c.MODEL, "serving_snapshot": "unknown"},
            "account_roles": {"approved": True, "destination": p.DESTINATION, "requested_model": p.c.MODEL,
                "serving_snapshot": "unknown", "max_input_bytes": 32768, "max_call_seconds": 120,
                "caps": {key: 2 for key in p.ROLES}, "raw_train_transfer": False, "tools_enabled": False, "automatic_retry": False},
            "closed": {key: True for key in ("Dev", "Final", "external_data", "external_literature", "paid_provider", "release", "push", "promotion")}}
        self.bind_grant()

    def tearDown(self): self.temp.cleanup()

    def bind_grant(self):
        path = self.root / "authorization.json"
        if path.exists(): path.unlink()  # Only disposable synthetic fixture, never a live grant.
        p.c.save(path, self.grant)
        self.binding = {"path": str(path), "sha256": p.c.sha(path)}

    def transport(self, directory, packet, timeout):
        self.calls += 1
        p.c.save(directory / "process.json", {"pid": 1234, "command": p._command(directory), "cli_sha256": p.c.CLI_SHA,
            "source_sha256": p.c.sha(Path(p.__file__).resolve()), "input_sha256": p.c._digest(packet), "transport_contract": p.transport_contract()})
        events = [{"type": "thread.started", "thread_id": "synthetic"}, {"type": "turn.started"},
            {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(RESPONSE)}},
            {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}}]
        (directory / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events))
        (directory / "stderr").write_text(""); p.c.save(directory / "response.json", RESPONSE)
        ack = {"model": p.c.MODEL, "instructionSources": [], "thread": {"id": "synthetic", "environments": []}}
        wire = [{"direction": "request", "message": {"id": 1, "method": "thread/start", "params": p._thread_params(directory)}},
            {"direction": "response", "message": {"id": 1, "result": ack}},
            {"direction": "request", "message": {"id": 2, "method": "turn/start", "params": {"threadId": "synthetic", "environments": [],
                "input": [{"type": "text", "text": p._prompt(packet)}], "model": p.c.MODEL, "outputSchema": SCHEMA}}},
            {"direction": "response", "message": {"method": "thread/started", "params": {"thread": {"id": "synthetic"}}}},
            {"direction": "response", "message": {"method": "turn/started", "params": {"turn": {"id": "synthetic-turn"}}}},
            {"direction": "response", "message": {"method": "item/completed", "params": {"item": {"type": "agentMessage", "text": json.dumps(RESPONSE)}}}},
            {"direction": "response", "message": {"method": "thread/tokenUsage/updated", "params": {"tokenUsage": {"last": {"input_tokens": 1, "output_tokens": 1}}}}},
            {"direction": "response", "message": {"method": "turn/completed", "params": {"turn": {"status": "completed"}}}}]
        (directory / "native-events.jsonl").write_text("\n".join(json.dumps(item) for item in wire))
        p.c.save(directory / "runtime-policy.json", {"contract": p.transport_contract(), "thread_start_result": ack, "environment_acknowledged": True})
        names = ["input.json", "schema.json", "process.json", "events.jsonl", "stderr", "response.json", "native-events.jsonl", "runtime-policy.json"]
        p.c.save(directory / "completion.json", {"exit_code": 0, "timed_out": False,
            "source_sha256": p.c.sha(Path(p.__file__).resolve()), "transport_contract": p.transport_contract(), "hashes": {name: p.c.sha(directory / name) for name in names}})

    def call(self, role="author", role_id="original-1", packet=None, transport=None, policy=None):
        return p.role_call(role, packet or {"synthetic": True}, SCHEMA, root=self.root,
            grant_binding=self.binding, role_id=role_id, _test_transport=transport or self.transport,
            _test_policy=policy or (lambda: {"synthetic": True, "operational_ready": True}))

    def test_complete_replay_no_resample(self):
        a = self.call(); b = self.call()
        self.assertEqual(a, b); self.assertEqual(self.calls, 1)
        self.assertEqual(a["serving_snapshot"], "unknown")
        self.assertEqual(p.c._read(a["response_binding"]), RESPONSE)

    def test_role_caps_and_independent_roles(self):
        self.call(role_id="original-1"); self.call(role_id="original-2")
        with self.assertRaisesRegex(RuntimeError, "cap"): self.call(role_id="original-3")
        self.call(role="source_review", role_id="original-review-1")
        self.assertEqual(self.calls, 3)

    def test_uncertain_original_blocks_all_new_calls(self):
        def fail(*_): raise RuntimeError("synthetic process uncertain")
        with self.assertRaisesRegex(RuntimeError, "uncertain"): self.call(transport=fail)
        with self.assertRaisesRegex(RuntimeError, "uncertain"): self.call(role="source_review", role_id="new-2")
        self.assertTrue((self.root / "role_calls" / "author" / "original-1" / "failure.json").exists())

    def test_input_drift_cannot_reuse_id(self):
        self.call()
        with self.assertRaisesRegex(ValueError, "claim drift"): self.call(packet={"synthetic": "changed"})
        self.assertEqual(self.calls, 1)

    def test_limits_precede_claim(self):
        with self.assertRaisesRegex(ValueError, "32KiB"): self.call(packet={"synthetic": "x" * 32768})
        self.assertFalse((self.root / "role_calls").exists()); self.assertEqual(self.calls, 0)

    def test_missing_role_authority_precedes_claim(self):
        self.grant["account_roles"]["approved"] = False; self.bind_grant()
        with self.assertRaisesRegex(ValueError, "whole-role"): self.call()
        self.assertFalse((self.root / "role_calls").exists())

    def test_expired_fresh_window_no_reservation(self):
        old = datetime.now(timezone.utc) - timedelta(days=1)
        self.grant.update(start_utc=old.strftime("%Y-%m-%dT%H:%M:%SZ"),
            selection_cutoff_utc=(old + timedelta(minutes=25)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            deadline_utc=(old + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ"))
        self.bind_grant()
        with self.assertRaisesRegex(ValueError, "window closed"): self.call()
        self.assertFalse(list((self.root / "role_calls").glob("*/*/claim.json")))

    def test_policy_failure_precedes_reservation(self):
        def fail(): raise ValueError("actual policy missing")
        with self.assertRaisesRegex(ValueError, "policy missing"): self.call(policy=fail)
        self.assertFalse(list((self.root / "role_calls").glob("*/*/claim.json")))

    def test_tampered_artifact_rejected_on_replay(self):
        result = self.call()
        Path(result["response_binding"]["path"]).write_text(json.dumps({"wrong": True}))
        with self.assertRaisesRegex(ValueError, "drift"): self.call()
        self.assertEqual(self.calls, 1)

    def test_unknown_tool_event_rejected(self):
        def bad(directory, packet, timeout):
            self.transport(directory, packet, timeout)
            events = directory / "events.jsonl"
            events.write_text(events.read_text() + '\n{"type":"item.completed","item":{"type":"command_execution"}}')
            completion = p.c._json((directory / "completion.json").read_bytes())
            completion["hashes"]["events.jsonl"] = p.c.sha(events)
            (directory / "completion.json").unlink(); p.c.save(directory / "completion.json", completion)
        with self.assertRaisesRegex(ValueError, "normalized|tool/failed/unknown"): self.call(transport=bad)

    def test_failed_process_retained_no_same_id_retry(self):
        def failed(directory, packet, timeout):
            self.transport(directory, packet, timeout)
            completion = p.c._json((directory / "completion.json").read_bytes()); completion["exit_code"] = 1
            (directory / "completion.json").unlink(); p.c.save(directory / "completion.json", completion)
        with self.assertRaisesRegex(RuntimeError, "failed original"): self.call(transport=failed)
        with self.assertRaisesRegex(RuntimeError, "failed original"): self.call()
        self.assertEqual(self.calls, 1)

    def test_unverified_runtime_is_blocked_before_claim(self):
        with self.assertRaisesRegex(RuntimeError, "enforcement unverified"):
            self.call(policy=lambda: {"operational_ready": False})
        self.assertFalse(list((self.root / "role_calls").glob("*/*/claim.json")))

    def test_core_and_wrapper_share_claim(self):
        first = self.call()
        second = p.AccountRoles(self.root, self.binding).call("author", {"synthetic": True}, SCHEMA, operation_id="original-1")
        self.assertEqual(first, second); self.assertEqual(self.calls, 1)

    def test_native_contract_has_no_trust_or_rule_bypass(self):
        contract = p.transport_contract()
        self.assertEqual(contract["thread_environments"], [])
        self.assertEqual(contract["turn_environments"], [])
        self.assertEqual(contract["dynamic_tools"], [])
        self.assertEqual(contract["hosted_search"], "disabled")
        self.assertNotIn("--ignore-rules", contract["command"])
        self.assertNotIn("--dangerously-bypass-hook-trust", contract["command"])
        self.assertIn("features.hooks=false", contract["command"])

    def test_native_request_tool_failure_paths(self):
        for event in [
            {"id": 3, "method": "item/tool/call", "params": {}},
            {"method": "item/completed", "params": {"item": {"type": "fileChange"}}},
            {"method": "item/started", "params": {"item": {"type": "mcpToolCall"}}},
            {"method": "error", "params": {"willRetry": True}},
            {"method": "turn/completed", "params": {"turn": {"status": "failed"}}},
        ]:
            with self.assertRaises((ValueError, RuntimeError)): p._normalize_native(event)

    def test_native_projection_is_traceable_text_only(self):
        native = {"method": "item/completed", "params": {"item": {"type": "agentMessage", "phase": "final", "text": json.dumps(RESPONSE)}}}
        result = p._normalize_native(native)
        self.assertEqual(result["item"]["type"], "agent_message")
        self.assertEqual(result["item"]["text"], native["params"]["item"]["text"])
        self.assertEqual(native["params"]["item"]["type"], "agentMessage")

    def test_strict_numeric_schema(self):
        for value in [True, -1, 3, "1"]:
            with self.assertRaises(ValueError): p._validate(value, {"type": "integer", "minimum": 0, "maximum": 2})
        p._validate(2, {"type": "integer", "minimum": 0, "maximum": 2})

    def native_fixture(self, *, environments=None, status="completed", model=None):
        original_popen = subprocess.Popen
        settings = {"model": model or p.c.MODEL, "environments": [] if environments is None else environments,
            "status": status, "response": RESPONSE}
        def launch(command, **kwargs):
            self.assertEqual(command, p.native_command(None))
            return original_popen([sys.executable, "-u", "-c", RPC_FIXTURE, json.dumps(settings)], **kwargs)
        return patch.object(p.subprocess, "Popen", side_effect=launch)

    def test_native_full_stdio_original_then_replay(self):
        with self.native_fixture():
            first = self.call(transport=p._transport)
        second = self.call()
        self.assertEqual(first, second)
        self.assertEqual(first["usage"], {"input_tokens": 7, "output_tokens": 3})
        self.assertEqual(self.calls, 0)
        directory = Path(first["completion_binding"]["path"]).parent
        process = p.c._json((directory / "process.json").read_bytes())
        completion = p.c._json((directory / "completion.json").read_bytes())
        self.assertGreater(process["pid"], 0)
        self.assertEqual(completion["exit_code"], 0)
        self.assertIsInstance(completion["process_exit_code"], int)

    def test_native_ack_failure_never_sends_model_turn(self):
        for settings in [{"environments": [{"id": "forbidden"}]}, {"model": "wrong-model"}]:
            with self.subTest(settings=settings), self.native_fixture(**settings):
                directory = self.root / ("synthetic-ack-" + str(len(list(self.root.glob("synthetic-ack-*")))))
                directory.mkdir()
                with self.assertRaisesRegex(ValueError, "not acknowledged"):
                    p.native_transport(directory, {"synthetic": True}, 5, preflight_only=True)
            records = [p.c._json(line) for line in (directory / "native-events.jsonl").read_text().splitlines()]
            self.assertFalse(any(record["message"].get("method") == "turn/start" for record in records))
            self.assertFalse((directory / "runtime-policy.json").exists())

    def test_metadata_preflight_actual_stdio_and_replay_no_turn(self):
        with self.native_fixture():
            first = p.native_preflight(self.root, self.binding)
        with patch.object(p, "native_transport", side_effect=AssertionError("replay must not spawn")):
            second = p.native_preflight(self.root, self.binding)
        self.assertEqual(first, second); self.assertTrue(first["operational_ready"])
        self.assertEqual(first["model_calls"], 0); self.assertFalse(first["private_payload_transfer"])
        wire = self.root / "account-runtime-preflight" / "native-events.jsonl"
        self.assertNotIn('"turn/start"', wire.read_text())

    def test_native_failed_turn_preserved_without_retry(self):
        with self.native_fixture(status="failed"):
            with self.assertRaisesRegex(RuntimeError, "failed/interrupted"):
                self.call(transport=p._transport)
        directory = self.root / "role_calls" / "author" / "original-1"
        self.assertTrue((directory / "failure.json").exists())
        self.assertTrue((directory / "native-events.jsonl").exists())
        self.assertFalse((directory / "completion.json").exists())
        with self.assertRaisesRegex(RuntimeError, "uncertain"):
            self.call(role_id="new-original")

    def test_recorded_preflight_drift_rejected(self):
        with self.native_fixture(): p.native_preflight(self.root, self.binding)
        wire = self.root / "account-runtime-preflight" / "native-events.jsonl"
        wire.write_text(wire.read_text() + "\n{}")
        with self.assertRaisesRegex(ValueError, "drift"): p.native_preflight(self.root, self.binding)

    def test_completed_preflight_replays_after_deadline_without_new_thread(self):
        with self.native_fixture(): first = p.native_preflight(self.root, self.binding)
        with patch.object(p, "datetime") as clock, patch.object(p, "native_transport", side_effect=AssertionError("no new metadata")):
            clock.now.return_value = datetime.now(timezone.utc) + timedelta(days=1)
            self.assertEqual(first, p.native_preflight(self.root, self.binding))


if __name__ == "__main__": unittest.main()
