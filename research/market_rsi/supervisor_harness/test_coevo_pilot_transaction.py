"""Synthetic original proposal transport only; no model/network/data/fits."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from supervisor_harness import coevo_pilot_transaction as p
from supervisor_harness import account_controller_feedback_consumer as c
from supervisor_harness.test_account_controller_feedback_consumer import Fixture, PARENT, OTHER


class Clock(datetime):
    @classmethod
    def now(cls, tz=None): return datetime(2026, 10, 6, 17, 36, tzinfo=timezone.utc)


class PilotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.f = Fixture(self.temp.name); self.root = self.f.root
        for mock in (patch.object(c, "CLI", self.f.cli), patch.object(c, "CLI_SHA", c.sha(self.f.cli)), patch.object(p, "datetime", Clock)):
            mock.start(); self.addCleanup(mock.stop)
        self.authorization = {"schema": "market_rsi_bounded_coevo_pilot_authorization_v1", "batch_id": p.BATCH,
            "granted": True, "limits": p.LIMITS, **p.TIMES,
            "account_transfer": {"approved": True, "destination": p.DESTINATION, "requested_model": c.MODEL,
                "serving_snapshot": "unknown", "raw_train_transfer": False, "tools_enabled": False, "automatic_retry": False},
            "closed": {key: True for key in ("Dev", "Final", "external_data", "external_literature", "paid_provider", "release", "push", "promotion")}}
        self.authorization_binding = self.write("authorization", self.authorization)
        self.packet = {"schema": "controller_coevolution_input_v1",
            "bindings": {"feedback": self.f.bindings["feedback"]}, "feedback": self.f.values["feedback"],
            "memory": self.f.values["memory"], "history": self.f.values["history"],
            "pool": self.f.values["pool"], "authority": self.authorization, "overhead": {},
            "provided_parents": [PARENT, OTHER], "provided_source_sha256": [OTHER]}
        self.ledger = {"schema": "market_rsi_coevo_pilot_ledger_v1", "batch_id": p.BATCH,
                       "controller_decisions": [], "attempts": [], "status": "open"}
        self.write("ledger", self.ledger); self.rebind(); self.calls = 0

    def write(self, name, value):
        path = self.root / (name + ".json"); path.write_text(json.dumps(value))
        return {"path": str(path), "sha256": c.sha(path)}

    def rebind(self):
        self.input_binding = self.write("packet", self.packet)
        self.review = {"passed": True, "authorization_sha256": self.authorization_binding["sha256"],
            "input_sha256": self.input_binding["sha256"], "transaction_source_sha256": c.sha(Path(p.__file__)),
            "consumer_source_sha256": c.sha(Path(c.__file__)), "cli_sha256": c.CLI_SHA, "requested_model": c.MODEL}
        self.review_binding = self.write("operation-review", self.review)

    def response(self, packet):
        change = {name: "synthetic nonexecutable hypothesis" for name in p.CHANGE["required"]}
        return {"schema": "controller_coevolution_proposal_v1", "input_sha256": c._digest(packet),
            "feedback_sha256": packet["bindings"]["feedback"]["sha256"], "requested_model": c.MODEL,
            "serving_snapshot": "unknown", "researcher_change": change, "harness_change": change,
            "candidate": self.f.decision(packet), "attribution": "proposal only, not proof"}

    def transport(self, directory, packet, timeout, *, mutate=None, extra_event=None):
        self.calls += 1; response = self.response(packet)
        self.assertLessEqual(timeout, 120)
        if mutate: mutate(response)
        c.save(directory / "process.json", {"pid": 123, "command": c._command(directory),
            "cli_sha256": c.CLI_SHA, "input_sha256": c._digest(packet), **c._identity()})
        c.save(directory / "response.json", response)
        events = [{"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(response)}},
                  {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}}]
        if extra_event: events.insert(0, extra_event)
        (directory / "events.jsonl").write_text("\n".join(json.dumps(item) for item in events))
        (directory / "stderr").write_bytes(b"")
        c.save(directory / "completion.json", {"exit_code": 0, "timed_out": False, **c._identity(),
            "hashes": {name: c.sha(directory / name) for name in
                ("process.json", "events.jsonl", "stderr", "schema.json", "input.json", "response.json")}})

    def call(self, transport=None):
        return p.call(self.root, self.input_binding, self.authorization_binding,
                      self.review_binding, self.f.repo, transport=transport or self.transport)

    def test_success_original_recovery_schema_and_usage(self):
        first = self.call(); self.assertEqual(self.call(), first); self.assertEqual(self.calls, 1)
        self.assertEqual(first["candidate"]["actual_parent_sha256"], PARENT)
        self.assertEqual(p._file(self.root / "ledger.json")["controller_decisions"][0]["status"], "completed")
        directory = next((self.root / "decisions").iterdir())
        self.assertEqual(p._file(directory / "ack.json")["usage"]["input_tokens"], 10)
        self.assertIn("wall_seconds", p._file(directory / "timing.json"))

    def test_completed_response_recovers_reserved_original_after_accounting_crash(self):
        self.call(); ledger = p._file(self.root / "ledger.json")
        ledger["controller_decisions"][0]["status"] = "reserved"; self.write("ledger", ledger)
        self.call(); self.assertEqual(self.calls, 1)
        self.assertEqual(p._file(self.root / "ledger.json")["controller_decisions"][0]["status"], "completed")

    def test_changed_packet_same_feedback_cannot_resample(self):
        self.call(); self.packet["memory"] = {"changed": True}; self.rebind()
        with self.assertRaisesRegex(ValueError, "claim/input/schema"): self.call()
        self.assertEqual(self.calls, 1)

    def test_cap_and_missing_review_reject_before_claim(self):
        self.ledger["controller_decisions"] = [{"feedback_sha256": str(number) * 64, "status": "completed"} for number in (8, 9)]
        self.write("ledger", self.ledger)
        with self.assertRaisesRegex(RuntimeError, "pilot cap"): self.call()
        self.assertEqual(self.calls, 0); self.assertFalse((self.root / "decisions").exists())

    def test_uncertain_original_never_retries(self):
        def interrupted(*_): self.calls += 1; raise KeyboardInterrupt("unknown completion")
        with self.assertRaises(KeyboardInterrupt): self.call(interrupted)
        with self.assertRaises(FileNotFoundError): self.call()
        self.assertEqual(self.calls, 1)

    def test_strict_r_h_fields_and_unknown_events_fail_without_second_call(self):
        with self.assertRaisesRegex(ValueError, "strict response fields"):
            self.call(lambda *args: self.transport(*args, mutate=lambda response: response["researcher_change"].update(extra=True)))
        with self.assertRaises(ValueError): self.call()
        self.assertEqual(self.calls, 1)

    def test_unprovided_parent_and_tool_events_rejected(self):
        with self.assertRaisesRegex(ValueError, "unprovided"):
            self.call(lambda *args: self.transport(*args, mutate=lambda response: response["candidate"].update(actual_parent_sha256="f" * 64)))
        self.assertEqual(self.calls, 1)

    def test_tool_event_rejected(self):
        with self.assertRaisesRegex(ValueError, "tools or failed"):
            self.call(lambda *args: self.transport(*args, extra_event={"type": "item.completed", "item": {"type": "command_execution"}}))

    def test_compact_cap_review_and_destination_bindings(self):
        self.review["passed"] = False; self.review_binding = self.write("operation-review", self.review)
        with self.assertRaisesRegex(ValueError, "review drift"): self.call()
        self.rebind(); self.packet["memory"] = "x" * 32768; self.rebind()
        with self.assertRaisesRegex(ValueError, "compact reviewed"): self.call()
        self.assertEqual(self.calls, 0)

    def test_explicit_larger_controller_budget_and_original_replay(self):
        self.authorization['account_transfer']['max_input_bytes'] = 262144
        self.authorization_binding = self.write('authorization', self.authorization)
        self.packet['authority'] = self.authorization
        self.packet['memory'] = 'synthetic aggregate memory ' + 'x' * 40000
        self.rebind()
        first = self.call(); second = self.call()
        self.assertEqual(first, second); self.assertEqual(self.calls, 1)
        self.assertEqual(len(p._file(self.root / 'ledger.json')['controller_decisions']), 1)

    def test_input_budget_requires_positive_integer_and_modern_explicit_value(self):
        for value in (None, True, 0, -1, '65536', 65536.):
            grant = {'account_transfer': {'max_input_bytes': value}}
            with self.subTest(value=value), self.assertRaises(ValueError): p.input_limit(grant)
        with self.assertRaises(ValueError): p.input_limit({'account_transfer': {}})
        self.assertEqual(p.input_limit({'account_transfer': {}}, legacy=True), 32768)
        self.assertEqual(p.input_limit({'account_transfer': {'max_input_bytes': 65536}}), 65536)

    def test_wrong_destination_tools_or_original_window_denied(self):
        original = deepcopy(self.authorization)
        for key, value in (("destination", "different account"), ("tools_enabled", True),
                           ("automatic_retry", True), ("raw_train_transfer", True)):
            self.authorization = deepcopy(original); self.authorization["account_transfer"][key] = value
            self.authorization_binding = self.write("authorization", self.authorization)
            self.packet["authority"] = self.authorization; self.rebind()
            with self.assertRaisesRegex(ValueError, "exact user grant"): self.call()
        self.authorization = original; self.authorization_binding = self.write("authorization", original)
        self.packet["authority"] = original; self.rebind()
        class ClosedClock(datetime):
            @classmethod
            def now(cls, tz=None): return datetime(2026, 10, 6, 18, 12, tzinfo=timezone.utc)
        with patch.object(p, "datetime", ClosedClock):
            with self.assertRaisesRegex(ValueError, "selection window"): self.call()
        self.assertEqual(self.calls, 0)


if __name__ == "__main__": unittest.main()
