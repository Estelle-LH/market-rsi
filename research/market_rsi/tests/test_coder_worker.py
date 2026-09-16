import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from coder_worker import (CodexCLITransport, assess_code, coding_command, dispatch_code_once,
                          load_pin, minimal_environment, prepare_code_request, run_bounded)
from market_rsi import digest, file_hash, fresh_json
from research_context import freeze_common
from researcher_worker import prepare_request
from test_researcher_worker import task, record, proposal


LIMITS = {"wall_seconds": 5, "max_prompt_bytes": 65536, "max_stream_bytes": 131072,
          "max_code_bytes": 65536}
RUNTIME = {"feature_names": ["x"], "prediction_min": -1, "prediction_max": 1,
           "libraries": {"python": "fixture-standard-library"},
           "execution_limits": {"cpu_seconds": 2, "memory_mb": 64}}
SOURCE = "def fit(train, feature_names):\n    return 0.0\ndef predict(model, row):\n    return model\n"


def events(body):
    return "\n".join(json.dumps(e) for e in [
        {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(body)}},
        {"type": "turn.completed", "usage": {"input_tokens": 50, "output_tokens": 30}}]) + "\n"


class FakeCoder:
    live = False

    def __init__(self, body=None, error=None):
        self.count, self.ready_count, self.error = 0, 0, error
        self.body = body or {"status": "implemented", "code": SOURCE, "notes": "fixture"}

    def check_ready(self):
        self.ready_count += 1
        return {"authentication": "fixture", "model": "fixture"}

    def run(self, prompt, output, limits):
        self.count += 1
        if self.error:
            raise self.error
        return {"body": self.body, "events": events(self.body), "exit_code": 0,
                "transport_failure": None}


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.common = self.root / "common.json"
        freeze_common(self.common)

    def tearDown(self):
        self.tmp.cleanup()

    def prepared(self, arm="learn", *, history=None, experiment="fixture-research", action="experiment"):
        history = history or []
        r = prepare_request(self.common, arm=arm, task=task(1 if history else 0, experiment=experiment),
                            step_index=0, records=history)
        p = proposal()
        p["action"] = action
        return prepare_code_request(r, json.dumps(p), RUNTIME, LIMITS)


class RequestTests(Fixture):
    def test_initial_coding_inputs_equal_across_arms(self):
        ps = [self.prepared(arm) for arm in ["reset", "archive", "learn"]]
        self.assertEqual(len({p["prompt"] for p in ps}), 1)
        self.assertEqual(len({p["audit"]["common_manifest_sha256"] for p in ps}), 1)
        self.assertNotIn(str(self.root), ps[0]["prompt"])

    def test_complete_history_is_committed_but_prompt_uses_bounded_projection(self):
        r = record()
        p = self.prepared(history=[r])
        context = json.loads(p["prompt"])["research_context"]
        payload = json.loads(context[1]["content"])["records"][0]["payload"]
        self.assertNotIn("candidate_code", payload)
        self.assertIn("candidate_code_sha256", payload)
        self.assertEqual(payload["proposal"], r["payload"]["proposal"])
        self.assertEqual(p["audit"]["record_sha256"], [digest(r)])

    def test_research_packet_mutation_rejected(self):
        r = prepare_request(self.common, arm="learn", task=task(), step_index=0, records=[])
        r["messages"][0]["content"] += "human hint"
        with self.assertRaises(ValueError):
            prepare_code_request(r, json.dumps(proposal()), RUNTIME, LIMITS)

    def test_invalid_proposal_cannot_be_rewritten_by_coder(self):
        r = prepare_request(self.common, arm="learn", task=task(), step_index=0, records=[])
        with self.assertRaises(ValueError):
            prepare_code_request(r, "invalid researcher output", RUNTIME, LIMITS)

    def test_inspect_and_reject_measurement_keep_their_interface(self):
        for action in ["inspect", "reject_measurement"]:
            p = self.prepared(action=action)
            self.assertEqual(p["audit"]["entrypoint"], "inspect")
            self.assertEqual(json.loads(p["prompt"])["proposal"]["action"], action)

    def test_runtime_extra_fields_and_context_overflow_rejected(self):
        r = prepare_request(self.common, arm="learn", task=task(), step_index=0, records=[])
        for runtime, limits in [(dict(RUNTIME, hidden_test=[1]), LIMITS),
                                 (RUNTIME, dict(LIMITS, max_prompt_bytes=5))]:
            with self.assertRaises(ValueError):
                prepare_code_request(r, json.dumps(proposal()), runtime, limits)


class DispatchTests(Fixture):
    def test_one_dispatch_and_subscription_usage_not_dollar_estimate(self):
        p, t, output = self.prepared(), FakeCoder(), self.root / "job"
        report = dispatch_code_once(p, t, output)
        self.assertTrue(report["valid"])
        self.assertFalse(report["executed"])
        usage = json.loads((output / "subscription-usage.json").read_text())
        self.assertEqual(usage["usage"]["output_tokens"], 30)
        self.assertIsNone(usage["allocated_cost_usd"])
        with self.assertRaises(FileExistsError):
            dispatch_code_once(p, t, output)
        self.assertEqual(t.count, 1)

    def test_live_blocked_before_readiness_and_claim(self):
        t = FakeCoder()
        t.live = True
        with self.assertRaises(RuntimeError):
            dispatch_code_once(self.prepared(), t, self.root / "job")
        self.assertEqual(t.ready_count, 0)
        self.assertEqual(t.count, 0)
        self.assertFalse((self.root / "job").exists())

    def test_mock_cannot_claim_real_experiment(self):
        with self.assertRaises(ValueError):
            dispatch_code_once(self.prepared(experiment="real-experiment"), FakeCoder(), self.root / "job")

    def test_packet_tamper_fails_before_dispatch(self):
        p, t = self.prepared(), FakeCoder()
        p["prompt"] += "extra data"
        with self.assertRaises(ValueError):
            dispatch_code_once(p, t, self.root / "job")
        self.assertEqual(t.count, 0)

    def test_failure_preserves_claim_and_never_retries(self):
        t, out = FakeCoder(error=TimeoutError()), self.root / "job"
        with self.assertRaises(TimeoutError):
            dispatch_code_once(self.prepared(), t, out)
        self.assertTrue((out / "dispatch.json").exists())
        self.assertEqual(json.loads((out / "failure.json").read_text())["error_type"], "TimeoutError")
        self.assertEqual(t.count, 1)

    def test_invalid_or_unsupported_code_still_records_usage(self):
        for i, body in enumerate([{"status": "implemented", "code": "bad syntax?!", "notes": "fixture"},
                                  {"status": "unsupported", "code": "", "notes": "cannot implement"}]):
            out, t = self.root / f"job-{i}", FakeCoder(body)
            self.assertFalse(dispatch_code_once(self.prepared(), t, out)["valid"])
            self.assertTrue((out / "subscription-usage.json").exists())
            self.assertEqual(t.count, 1)

    def test_answer_file_must_match_one_saved_terminal_message(self):
        class Mismatch(FakeCoder):
            def run(self, prompt, output, limits):
                r = super().run(prompt, output, limits)
                r["events"] = events(dict(self.body, code=SOURCE + "# different\n"))
                return r
        out = self.root / "job"
        result = dispatch_code_once(self.prepared(), Mismatch(), out)
        self.assertFalse(result["valid"])
        self.assertFalse(result["response_matches_saved_event"])
        self.assertTrue((out / "subscription-usage.json").exists())


class BoundaryTests(Fixture):
    def test_no_provider_key_proxy_or_config_environment(self):
        env = minimal_environment({"HOME": "/fixture", "PATH": "/bin", "TINKER_API_KEY": "sentinel",
                                   "OPENAI_API_KEY": "sentinel", "E2B_API_KEY": "sentinel",
                                   "HTTP_PROXY": "sentinel", "CODEX_HOME": "sentinel"})
        self.assertEqual(env, {"HOME": "/fixture", "PATH": "/bin"})

    def test_explicit_model_chatgpt_and_no_tools(self):
        args = coding_command("/tmp/coder", "schema", "answer",
                               {"cli_path": "/codex", "model": "gpt-6-astra"}, "/catalog.json")
        self.assertEqual(args[args.index("--model") + 1], "gpt-6-astra")
        for x in ["--ignore-user-config", "--ignore-rules", "--ephemeral", "--strict-config",
                  'forced_login_method="chatgpt"', 'web_search="disabled"',
                  'model_catalog_json="/catalog.json"', "shell_tool", "multi_agent", "apps"]:
            self.assertIn(x, args)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", args)

    def test_ast_inspection_never_executes_returned_source(self):
        marker = self.root / "must-not-exist"
        source = f"from pathlib import Path\nPath({str(marker)!r}).touch()\n" + SOURCE
        self.assertTrue(assess_code({"status": "implemented", "code": source, "notes": "fixture"},
                                   "fit_predict", 65536)["valid"])
        self.assertFalse(marker.exists())

    def test_wrong_interface_and_oversized_source_fail(self):
        for source in ["def fit(): pass\ndef predict(): pass", "async def inspect(a,b,c): pass"]:
            self.assertFalse(assess_code({"status": "implemented", "code": source, "notes": "fixture"},
                                        "fit_predict", 65536)["valid"])
        self.assertFalse(assess_code({"status": "implemented", "code": SOURCE, "notes": "fixture"},
                                    "fit_predict", 2)["valid"])

    def test_pin_hash_and_model_verified(self):
        binary, catalog, pin = self.root / "binary", self.root / "catalog.json", self.root / "pin.json"
        # Human-authored fixture files, not executable returned model code.
        binary.write_bytes(b"fixture binary")
        fresh_json(catalog, {"models": [{"slug": "fixture", "visibility": "list",
                                       "supported_reasoning_levels": [{"effort": "medium"}]}]})
        fresh_json(pin, {"schema": "subscribed_coder_pin_v1", "authentication": "chatgpt",
                        "reasoning_effort": "medium", "model": "fixture", "cli_path": str(binary),
                        "cli_sha256": file_hash(binary), "catalog_file": catalog.name,
                        "catalog_sha256": file_hash(catalog)})
        self.assertEqual(load_pin(pin)[0]["model"], "fixture")
        binary.write_bytes(b"changed fixture")
        with self.assertRaises(ValueError):
            load_pin(pin)


class SubprocessTests(Fixture):
    def run_fixture(self, script, limits=None):
        return run_bounded([sys.executable, "-I", "-c", script], "fixture only",
                           minimal_environment(os.environ), self.root, limits or LIMITS)

    def test_real_pipe_streaming_preserves_events_and_reaps(self):
        result = self.run_fixture("import sys,json; sys.stdin.read(); print(json.dumps({'type':'turn.completed',"
                                  "'usage':{'input_tokens':1,'output_tokens':2}}))")
        self.assertEqual(result["exit_code"], 0)
        self.assertIsNone(result["failure_type"])
        self.assertTrue(result["process_reaped"])
        self.assertEqual(json.loads((self.root / "events.jsonl").read_text())["type"], "turn.completed")

    def test_tool_event_stops_exact_owned_process(self):
        result = self.run_fixture("import json,time; print(json.dumps({'type':'item.started',"
                                  "'item':{'type':'command_execution'}}),flush=True); time.sleep(5)")
        self.assertEqual(result["failure_type"], "ValueError")
        self.assertTrue(result["process_reaped"])
        self.assertLess(result["elapsed_seconds"], 2)

    def test_timeout_is_bounded_and_reaped(self):
        result = self.run_fixture("import time; time.sleep(5)", dict(LIMITS, wall_seconds=1))
        self.assertEqual(result["failure_type"], "TimeoutError")
        self.assertTrue(result["process_reaped"])
        self.assertLess(result["elapsed_seconds"], 2.5)

    def test_oversized_stderr_preserved_only_to_cap(self):
        result = self.run_fixture("import sys; sys.stderr.write('x'*10000)",
                                  dict(LIMITS, max_stream_bytes=200, max_code_bytes=100))
        self.assertEqual(result["failure_type"], "ValueError")
        self.assertEqual((self.root / "stderr.log").stat().st_size, 200)

    def test_partial_json_event_fails(self):
        result = self.run_fixture("import sys; sys.stdout.write('{')")
        self.assertEqual(result["failure_type"], "ValueError")


if __name__ == "__main__":
    unittest.main()
