"""Synthetic native consumer integration using actual broker observations."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import tomllib
import unittest
from unittest.mock import patch

from supervisor_harness import account_controller_feedback_consumer as c
from supervisor_harness import controller_evidence_session as e
from supervisor_harness import controller_research_evidence_tools as broker
from supervisor_harness import test_account_controller_feedback_consumer as legacy


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.f = legacy.Fixture(self.temp.name)
        self.root = self.f.root / "calls"
        self.directory = self.root / self.f.bindings["feedback"]["sha256"]
        self.source = self.f.root / "approved-evidence.txt"
        self.source.write_text("Synthetic prior finding: conditional residual failed, not the whole family.")
        self.policy = {"schema": broker.SCHEMA, "evidence": [{"id": "finding", "path": str(self.source),
            "sha256": c.sha(self.source), "kind": "evidence", "controller_payload_approved": True}],
            "limits": {"file_bytes": 4096, "page_bytes": 2048, "output_bytes": 8192, "tool_calls": 4},
            "audit_path": str(self.directory / "evidence-audit.jsonl")}
        self.proof = {"schema": "controller_evidence_runtime_attestation_v1", "profile_sha256": e.profile_sha256(),
            "cli_sha256": e.CLI_SHA, "reader_sha256": e.READER_SHA, "python_sha256": e.PYTHON_SHA,
            "requested_model": "catalog-fixture", "protected_channel_check": "passed", "scope": "synthetic",
            "effective_tools": sorted(e.RESOURCE_HELPERS | {"mcp__controller_evidence__" + n for n in e.TOOLS})}
        self.session = {"schema": e.SCHEMA, "policy": self.bind("policy", self.policy),
                        "runtime_attestation": self.bind("proof", self.proof)}
        for mock in [patch.object(c.subprocess, "check_output", return_value=b"synthetic source"),
                     patch.object(c, "CLI", self.f.cli), patch.object(c, "CLI_SHA", c.sha(self.f.cli))]:
            mock.start(); self.addCleanup(mock.stop)
        self.packet = self.prepare(); self.calls = 0

    def bind(self, name, value):
        path = self.f.root / (name + ".json"); path.write_bytes(broker.encode(value))
        return {"path": str(path), "sha256": c.sha(path)}

    def prepare(self):
        return c.prepare_input(self.f.bindings, self.f.batch, self.f.repo, legacy.NOW, evidence_session=self.session)

    def transport(self, directory, packet, timeout, *, tool="read_evidence", arguments=None, mutate_event=None):
        self.calls += 1
        arguments = arguments if arguments is not None else ({"evidence_id": "finding"} if tool == "read_evidence" else {})
        reader = broker.EvidenceBroker(self.session["policy"]["path"], self.session["policy"]["sha256"])
        try: value = reader.call(tool, arguments)
        finally: reader.close()
        response = self.f.decision(packet)
        response["evidence_used"] = [{"sha256": c.sha(self.source), "finding": value.get("text", "not read"),
                                      "choice_consequence": "choose a different conditional question"}]
        item = {"id": "read-1", "type": "mcp_tool_call", "server": e.SERVER, "tool": tool,
                "arguments": arguments, "status": "completed", "error": None,
                "result": {"content": [{"type": "text", "text": broker.encode(value).decode()}], "structured_content": None}}
        event = {"type": "item.completed", "item": item}
        if mutate_event: mutate_event(event)
        events = [event, {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(response)}},
                  {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}}]
        c.save(directory / "process.json", {"pid": 123, "command": c._command(directory, self.session),
            "cli_sha256": c.CLI_SHA, "input_sha256": c._digest(packet),
            **c._identity(self.session, packet["schema"] == "controller_failure_feedback_input_v1")})
        c.save(directory / "response.json", response)
        (directory / "events.jsonl").write_text("\n".join(json.dumps(v) for v in events))
        (directory / "stderr").write_bytes(b"")
        self.seal(directory)

    def seal(self, directory):
        names = ["process.json", "events.jsonl", "stderr", "schema.json", "input.json", "response.json", "evidence-audit.jsonl"]
        failure_input = c._json((directory / "input.json").read_bytes())["schema"] == "controller_failure_feedback_input_v1"
        (directory / "completion.json").write_bytes(broker.encode({"exit_code": 0, "timed_out": False, **c._identity(self.session, failure_input),
            "hashes": {name: c.sha(directory / name) for name in names}}))

    def consume(self, transport=None):
        return c.consume(self.packet, self.root, batch=self.f.batch, repo=self.f.repo, now=legacy.NOW,
                         transport=transport or self.transport, evidence_session=self.session)

    def test_real_broker_result_and_citation_reach_native_recovery_once(self):
        result = self.consume()
        self.assertIn("conditional residual failed", result["evidence_used"][0]["finding"])
        self.assertEqual(self.consume(), result); self.assertEqual(self.calls, 1)
        ack = c._json((self.directory / "ack.json").read_bytes())
        self.assertEqual(ack["provider_calls"], 0)
        self.assertEqual(ack["completion_sha256"], c.sha(self.directory / "completion.json"))

    def test_recovery_uses_original_input_after_closed_budget_without_new_read(self):
        result = self.consume(); self.f.write("authority", {"closed": True})
        recovered = c.consume(self.packet, self.root, batch=self.f.batch, repo=self.f.repo, now=c.DEADLINE,
            evidence_session=self.session, transport=lambda *args: self.fail("never resample"))
        self.assertEqual(recovered, result); self.assertEqual(self.calls, 1)

    def test_catalog_only_and_denied_reads_are_not_source_citations(self):
        for tool, arguments in [("list_evidence", {}), ("read_evidence", {"evidence_id": "unapproved"})]:
            with self.subTest(tool=tool), TemporaryDirectory() as temp:
                old = self.root; self.root = Path(temp).resolve() / "calls"
                self.directory = self.root / self.f.bindings["feedback"]["sha256"]
                self.policy["audit_path"] = str(self.directory / "evidence-audit.jsonl")
                self.session["policy"] = self.bind("policy", self.policy); self.packet = self.prepare()
                with self.assertRaisesRegex(ValueError, "unprovided evidence/parent"):
                    self.consume(lambda *a: self.transport(*a, tool=tool, arguments=arguments))
                self.root = old

    def test_unapproved_server_or_tool_and_incomplete_call_rejected(self):
        for change in [{"server": "filesystem"}, {"tool": "shell"}, {"id": ""}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.consume(lambda *a: self.transport(*a, mutate_event=lambda v: v["item"].update(change)))
            # Each subcase uses a fresh original feedback call root, not a retry.
            self.root = self.f.root / ("calls-" + str(self.calls))
            self.directory = self.root / self.f.bindings["feedback"]["sha256"]
            self.policy["audit_path"] = str(self.directory / "evidence-audit.jsonl")
            self.session["policy"] = self.bind("policy", self.policy); self.packet = self.prepare()
        self.directory.mkdir(parents=True)
        (self.directory / "evidence-audit.jsonl").write_bytes(b"")
        with self.assertRaisesRegex(ValueError, "incomplete"):
            e.verify_events(self.session, self.directory, [{"type": "item.started", "item": {
                "id": "unfinished", "type": "mcp_tool_call", "server": e.SERVER, "tool": "read_evidence"}}])

    def test_completed_result_and_audit_drift_rejected_even_with_resealed_completion(self):
        def changed(directory, packet, timeout):
            self.transport(directory, packet, timeout)
            audit = broker.strict_json((directory / "evidence-audit.jsonl").read_bytes())
            audit["payload_sha256"] = "f" * 64
            (directory / "evidence-audit.jsonl").write_bytes(broker.encode(audit) + b"\n"); self.seal(directory)
        with self.assertRaisesRegex(ValueError, "audit drift"): self.consume(changed)
        self.assertEqual(self.calls, 1)

    def test_payload_mutation_and_duplicate_completion_fail(self):
        def wrong(event): event["item"]["result"]["content"][0]["text"] = '{"ok":false,"error":"fake"}'
        with self.assertRaisesRegex(ValueError, "audit drift"):
            self.consume(lambda *a: self.transport(*a, mutate_event=wrong))
        raw = (self.directory / "events.jsonl").read_text().splitlines()
        events = [broker.strict_json(v) for v in raw]
        with self.assertRaisesRegex(ValueError, "duplicate"):
            e.verify_events(self.session, self.directory, [events[0], events[0]])

    def test_explicit_mode_binding_and_account_activation_fail_before_claim(self):
        for session in [None, dict(self.session, schema="other")]:
            with self.assertRaises(ValueError):
                c.consume(self.packet, self.root, batch=self.f.batch, repo=self.f.repo, now=legacy.NOW,
                          transport=lambda *a: self.fail("must not run"), evidence_session=session)
        with patch.object(c.subprocess, "Popen", side_effect=AssertionError("no account launch")), self.assertRaisesRegex(ValueError, "activation"):
            c.consume(self.packet, self.root, batch=self.f.batch, repo=self.f.repo, now=legacy.NOW, evidence_session=self.session)
        self.assertFalse(self.root.exists())
        self.proof["scope"] = "account"; self.session["runtime_attestation"] = self.bind("proof", self.proof)
        with self.assertRaises(ValueError): e.validate(self.session)
        with self.assertRaisesRegex(ValueError, "activation"): e.validate(self.session, account=True)

    def test_strict_profile_compiles_exact_scoped_mcp_and_disabled_channels(self):
        args = e.config_overrides(self.session, self.directory)
        self.assertEqual(args[0], "--strict-config")
        config = {}
        for index in range(1, len(args), 2):
            self.assertEqual(args[index], "-c"); config.update(tomllib.loads(args[index + 1]))
        self.assertEqual(config["features"]["code_mode"], {"enabled": False})
        self.assertNotIn("code_mode", config)
        self.assertEqual(config["web_search"], "disabled")
        self.assertEqual(set(config["mcp_servers"]), {e.SERVER})
        server = config["mcp_servers"][e.SERVER]
        self.assertTrue(server["required"]); self.assertEqual(server["env_vars"], [])
        self.assertEqual(set(server["enabled_tools"]), e.TOOLS)
        self.assertEqual(server["default_tools_approval_mode"], "prompt")
        self.assertTrue(all(v == {"approval_mode": "approve"} for v in server["tools"].values()))

    def test_catalog_limits_policy_and_runtime_drift_denied(self):
        original = deepcopy(self.proof)
        for key, value in [("effective_tools", original["effective_tools"] + ["shell"]), ("profile_sha256", "f" * 64),
                           ("protected_channel_check", "unknown"), ("requested_model", c.MODEL)]:
            proof = dict(original, **{key: value}); self.session["runtime_attestation"] = self.bind("proof", proof)
            with self.assertRaises(ValueError): self.prepare()
        self.session["runtime_attestation"] = self.bind("proof", original)
        self.policy["limits"]["tool_calls"] = True; self.session["policy"] = self.bind("policy", self.policy)
        with self.assertRaises(ValueError): self.prepare()
        self.assertEqual(self.calls, 0)

    def test_source_changed_denied_read_is_not_retrieved_evidence(self):
        self.source.write_text("drift")
        with self.assertRaisesRegex(ValueError, "unprovided evidence/parent"): self.consume()

    def test_helper_source_drift_blocks_original_claim_without_resampling(self):
        self.consume(); original = c.sha
        with patch.object(c, "sha", side_effect=lambda p: "f" * 64 if Path(p).resolve() == Path(e.__file__).resolve() else original(p)):
            with self.assertRaisesRegex(ValueError, "same feedback changed"): self.consume()
        self.assertEqual(self.calls, 1)

    def test_factual_native_failure_with_audited_evidence_recovery(self):
        from supervisor_harness import test_controller_failure_feedback as failed
        with TemporaryDirectory() as temp:
            self.f = failed.Fixture(temp)
            self.root = self.f.root / "calls"; self.directory = self.root / self.f.bindings["feedback"]["sha256"]
            self.policy["audit_path"] = str(self.directory / "evidence-audit.jsonl")
            self.session["policy"] = self.bind("policy", self.policy)
            self.session["runtime_attestation"] = self.bind("proof", self.proof)
            with patch.object(c, "CLI", self.f.cli), patch.object(c, "CLI_SHA", c.sha(self.f.cli)):
                self.packet = self.prepare()
                self.assertIsNone(self.packet["numerical"])
                self.assertEqual(self.consume()["actual_parent_sha256"], self.f.good)
                self.assertEqual(self.calls, 1)
                self.assertFalse(any(self.f.root.glob("*.csv")))


if __name__ == "__main__": unittest.main()
