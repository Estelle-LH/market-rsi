"""Content/order semantics through real broker and native consumer fixtures."""
import json
import unittest
from unittest.mock import patch

from supervisor_harness import account_controller_feedback_consumer as c
from supervisor_harness import controller_evidence_session as e
from supervisor_harness import controller_research_evidence_tools as broker
from supervisor_harness import test_controller_evidence_session as fixtures


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.SessionTests(methodName="runTest")
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()
        guard = patch.object(c.subprocess, "Popen", side_effect=AssertionError("no account/process"))
        guard.start(); self.addCleanup(guard.stop)

    def rewrite(self, directory, transform, response=None):
        events = [json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()]
        if response is not None:
            (directory / "response.json").write_text(json.dumps(response))
            events[1]["item"]["text"] = json.dumps(response)
        (directory / "events.jsonl").write_text("\n".join(json.dumps(event) for event in transform(events)))
        self.f.seal(directory)

    def eof_transport(self, directory, packet, timeout, *, cite_source):
        self.f.transport(directory, packet, timeout, arguments={"evidence_id": "finding", "offset": len(self.f.source.read_bytes())})
        response = json.loads((directory / "response.json").read_text()) if cite_source else self.f.f.decision(packet)
        if cite_source:
            response["evidence_used"][0]["finding"] = "A claimed finding despite receiving no content"
        self.rewrite(directory, lambda events: events, response)

    def test_informative_read_before_final_accepts_and_recovers_once(self):
        result = self.f.consume()
        self.assertEqual(self.f.consume(), result)
        self.assertEqual(self.f.calls, 1)

    def test_empty_eof_cannot_qualify_new_source_citation(self):
        with self.assertRaisesRegex(ValueError, "unprovided evidence/parent"):
            self.f.consume(lambda *args: self.eof_transport(*args, cite_source=True))
        self.assertEqual(self.f.calls, 1)
        self.assertFalse((self.f.directory / "ack.json").exists())

    def test_empty_eof_with_original_memory_citation_remains_allowed(self):
        result = self.f.consume(lambda *args: self.eof_transport(*args, cite_source=False))
        self.assertNotEqual(result["evidence_used"][0]["sha256"], c.sha(self.f.source))

    def assert_late_rejected(self, order):
        def transport(directory, packet, timeout):
            self.f.transport(directory, packet, timeout)
            self.rewrite(directory, lambda events: [events[i] for i in order])
        with self.assertRaisesRegex(ValueError, "after final decision or terminal"):
            self.f.consume(transport)
        self.assertFalse((self.f.directory / "ack.json").exists())

    def test_read_after_final_decision_rejected(self):
        self.assert_late_rejected([1, 0, 2])

    def test_read_after_terminal_turn_rejected(self):
        self.assert_late_rejected([1, 2, 0])

    def test_started_tool_after_final_rejected_even_if_other_read_was_valid(self):
        def transport(directory, packet, timeout):
            self.f.transport(directory, packet, timeout)
            def changed(events):
                started = {"type": "item.started", "item": {"id": "late", "type": "mcp_tool_call",
                    "server": e.SERVER, "tool": "read_evidence"}}
                return [events[0], events[1], started, events[2]]
            self.rewrite(directory, changed)
        with self.assertRaisesRegex(ValueError, "after final decision or terminal"):
            self.f.consume(transport)

    def test_intermediate_json_message_does_not_block_later_read(self):
        def transport(directory, packet, timeout):
            self.f.transport(directory, packet, timeout)
            note = {"type": "item.completed", "item": {"type": "agent_message", "text": '{"note":"Read first"}'}}
            self.rewrite(directory, lambda events: [note] + events)
        self.assertEqual(self.f.consume(transport)["evidence_used"][0]["finding"], self.f.source.read_text())

    def test_informative_read_followed_by_eof_preserves_source_citation(self):
        def transport(directory, packet, timeout):
            self.f.calls += 1
            reader = broker.EvidenceBroker(self.f.session["policy"]["path"], self.f.session["policy"]["sha256"])
            arguments = [{"evidence_id": "finding"}, {"evidence_id": "finding", "offset": len(self.f.source.read_bytes())}]
            try: values = [reader.call("read_evidence", args) for args in arguments]
            finally: reader.close()
            response = self.f.f.decision(packet)
            response["evidence_used"] = [{"sha256": c.sha(self.f.source), "finding": values[0]["text"],
                                          "choice_consequence": "Use actual earlier content"}]
            events = [{"type": "item.completed", "item": {"id": str(i), "type": "mcp_tool_call", "server": e.SERVER,
                "tool": "read_evidence", "arguments": args, "status": "completed", "error": None,
                "result": {"content": [{"type": "text", "text": broker.encode(value).decode()}], "structured_content": None}}}
                      for i, (args, value) in enumerate(zip(arguments, values))]
            events += [{"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(response)}},
                       {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}}]
            c.save(directory / "process.json", {"pid": 123, "command": c._command(directory, self.f.session),
                "cli_sha256": c.CLI_SHA, "input_sha256": c._digest(packet), **c._identity(self.f.session)})
            c.save(directory / "response.json", response)
            (directory / "events.jsonl").write_text("\n".join(json.dumps(event) for event in events))
            (directory / "stderr").write_bytes(b"")
            self.f.seal(directory)
        self.assertEqual(self.f.consume(transport)["evidence_used"][0]["finding"], self.f.source.read_text())
        self.assertEqual(self.f.calls, 1)


if __name__ == "__main__": unittest.main()
