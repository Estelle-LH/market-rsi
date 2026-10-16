"""Original-public-evidence delivery to the same selected executable R.

Default tests retain explicitly synthetic runner originals, while real
FilingTools, Native source selection, worker and forecast request construction
execute normally. No candidate source is executed on host. The opt-in Docker
test executes an invented algorithm on invented public filing text only.
Neither mode establishes actual-model authorship or predictive improvement.
"""

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "research" / "market_rsi"))

import edgar_forecast_openai as forecast
from edgar_forecast_tools import FilingTools
import earnings_open_researcher as researcher
from earnings_open_code import DockerRunner, encoded
from earnings_open_program import candidate
from earnings_open_source_review import ProgramSourceReview
from earnings_open_worker import ProgramWorker
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_open_capacity as native_fixture
import test_earnings_research_state as state_fixture


REQUESTS = [
    {"tool": "read_file", "arguments": {
        "path": "filings/old.md", "offset": 0, "characters": 20000}},
    {"tool": "search_files", "arguments": {
        "query": "revenue", "path_prefix": "filings/", "max_hits": 5}},
    {"tool": "calculate", "arguments": {"expression": "100 - 5"}},
]
REQUEST_PHASE = {"research_requests": REQUESTS}
ADVICE = {"method": "signed_historical_sum", "value": 95.0,
          "matching_lines": 1, "arithmetic_check": 95}
SOURCE = (
    "PROGRAM = {'axis': 'R'}\n"
    "import re\n"
    "REQUESTS = " + repr(REQUESTS) + "\n"
    "def run(payload):\n"
    "    if 'research_observations' not in payload:\n"
    "        return {'research_requests': REQUESTS}\n"
    "    observations = payload['research_observations']\n"
    "    text = observations[0]['output']['text']\n"
    "    values = [float(x) for x in re.findall(r'[+-]?\\d+(?:\\.\\d+)?', text)]\n"
    "    return {'method': 'signed_historical_sum', 'value': sum(values),\n"
    "            'matching_lines': observations[1]['output']['total_matching_lines'],\n"
    "            'arithmetic_check': observations[2]['output']['value']}\n"
)


class ScriptedReceiptRunner:
    """Preserve real-format synthetic originals; never eval/import the source."""

    blocked = False

    def __init__(self, root, values):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=False)
        self.values = deepcopy(values)
        self.calls = 0
        self.invocations = []

    def run(self, source, payload):
        if self.calls >= len(self.values):
            raise AssertionError("Unexpected extra execution or automatic retry")
        value = deepcopy(self.values[self.calls])
        self.calls += 1
        path = self.root / ("call-" + f"{self.calls:032x}")
        path.mkdir()
        request = encoded({"source": source, "payload": payload})
        stdout = encoded({"ok": True, "value": value})
        for name, raw in (
            ("input.json", request), ("stdout.bin", stdout), ("stderr.bin", b""),
            ("intent.json", encoded({"synthetic": True, "no_candidate_execution": True})),
            ("create.stdout", b"SYNTHETIC: no container launched"), ("create.stderr", b""),
        ):
            (path / name).write_bytes(raw)
        receipt = engine.save(path / "result.json", {
            "synthetic": True, "status": "COMPLETED", "cleanup_verified": True,
            "host_candidate_execution": False, "exit_code": 0,
            "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "input_sha256": hashlib.sha256(request).hexdigest(),
            "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
            "stderr_sha256": hashlib.sha256(b"").hexdigest(),
        })
        self.invocations.append({"source": source, "payload": deepcopy(payload),
                                 "receipt": deepcopy(receipt)})
        return {"value": value, "receipt": receipt}


class ResearcherEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.data = state_fixture.ResearchStateTests(
            "test_append_preserves_parent_and_old_history")
        self.data.setUp()
        self.addCleanup(self.data.doCleanups)
        self.root = self.data.root
        self.tools = FilingTools(self.data.company)
        self.payload = {"stage": "forecast", "questions": self.data.files["questions.md"],
                        "filing_index": self.data.files["filing_index.tsv"], "records": []}
        self.runners = []

    def runner(self, values):
        runner = ScriptedReceiptRunner(self.root / f"runner-{len(self.runners)}", values)
        self.runners.append(runner)
        return runner

    def completed(self):
        runner = self.runner([REQUEST_PHASE, ADVICE])
        result = researcher.run(runner, SOURCE, self.payload, self.tools)
        return result, runner

    def test_exact_original_evidence_then_same_source_runs_again(self):
        initial = deepcopy(self.payload)
        execution, runner = self.completed()
        expected_tools = FilingTools(self.data.company)
        expected = [{"request": deepcopy(row),
                     "output": expected_tools.dispatch(row["tool"], row["arguments"])}
                    for row in REQUESTS]
        self.assertEqual(runner.calls, 2)
        self.assertEqual([row["source"] for row in runner.invocations], [SOURCE, SOURCE])
        self.assertEqual(runner.invocations[0]["payload"], initial)
        self.assertEqual(runner.invocations[1]["payload"],
                         dict(initial, research_observations=expected))
        self.assertEqual(execution["research_observations"], expected)
        self.assertEqual(expected[0]["output"]["text"], self.data.files["filings/old.md"])
        self.assertEqual(self.tools.calls, 3)
        self.assertEqual(researcher.verify(execution, SOURCE, initial, self.data.company), ADVICE)
        self.assertEqual(self.payload, initial)
        self.assertNotIn("files", self.payload)

    def test_originals_include_both_container_calls_and_reverification_does_not_recharge(self):
        execution, runner = self.completed()
        original_calls = self.tools.calls, self.tools.returned
        original_runs = researcher.originals(execution)
        self.assertEqual(original_runs, [execution["request_execution"], execution])
        self.assertNotEqual(original_runs[0]["receipt"], original_runs[1]["receipt"])
        for original in original_runs:
            path = Path(original["receipt"]["path"]).parent
            for name in ("input.json", "stdout.bin", "stderr.bin", "intent.json", "result.json"):
                self.assertTrue((path / name).is_file())
        self.assertEqual(researcher.verify(execution, SOURCE, self.payload, self.data.company), ADVICE)
        self.assertEqual(researcher.verify(execution, SOURCE, self.payload, self.data.company), ADVICE)
        self.assertEqual((self.tools.calls, self.tools.returned), original_calls)
        self.assertEqual(runner.calls, 2)

    def test_R0_and_legacy_JSON_advice_keep_one_execution_and_no_evidence_calls(self):
        for value in ({}, {"advice": "Compare units"}, [], "legacy advice", 0, False, None):
            with self.subTest(value=value):
                runner = self.runner([value])
                source = "PROGRAM={'axis':'R'}\ndef run(payload): return {}\n"
                execution = researcher.run(runner, source, self.payload, self.tools)
                self.assertEqual(researcher.verify(execution, source, self.payload, self.data.company), value)
                self.assertEqual(researcher.originals(execution), [execution])
                self.assertNotIn("request_execution", execution)
                self.assertNotIn("research_observations", execution)
                self.assertEqual(runner.calls, 1)
        self.assertEqual(self.tools.calls, 0)

    def test_request_protocol_is_exact_bounded_and_not_mixed_with_advice(self):
        invalid = [
            {"research_requests": []}, {"research_requests": REQUESTS * 3},
            {"research_requests": None}, {"research_requests": "read_file"},
            {"research_requests": REQUESTS, "advice": "mixed"},
            {"research_requests": [None]},
            {"research_requests": [{"tool": "read_file"}]},
            {"research_requests": [{"tool": "read_file", "arguments": {}, "extra": True}]},
            {"research_requests": [{"tool": "read_file", "arguments": "not object"}]},
            {"research_requests": [{"tool": 1, "arguments": {}}]},
        ]
        for value in invalid:
            with self.subTest(value=value):
                runner = self.runner([value])
                with self.assertRaises(ValueError):
                    researcher.run(runner, SOURCE, self.payload, self.tools)
                self.assertEqual(runner.calls, 1)
                self.assertTrue(Path(runner.invocations[0]["receipt"]["path"]).is_file())
        self.assertEqual(self.tools.calls, 0)

    def test_eight_requests_allowed_but_second_evidence_phase_not_allowed(self):
        request = {"tool": "calculate", "arguments": {"expression": "1"}}
        runner = self.runner([{"research_requests": [request] * 8}, {"completed": True}])
        execution = researcher.run(runner, SOURCE, self.payload, self.tools)
        self.assertEqual(len(execution["research_observations"]), 8)
        self.assertEqual(self.tools.calls, 8)
        self.assertEqual(runner.calls, 2)
        again = self.runner([REQUEST_PHASE, REQUEST_PHASE])
        with self.assertRaisesRegex(ValueError, "another evidence phase"):
            researcher.run(again, SOURCE, self.payload, FilingTools(self.data.company))
        self.assertEqual(again.calls, 2)
        self.assertTrue(all(Path(row["receipt"]["path"]).is_file() for row in again.invocations))

    def test_reserved_or_external_tools_are_forbidden_before_dispatch(self):
        for tool in ("save_research_record", "run_python", "search_literature", "read_literature",
                     "inspect_trace", "extract_numbers", "shell", "http_get"):
            with self.subTest(tool=tool):
                runner = self.runner([{"research_requests": [{"tool": tool, "arguments": {}}]}])
                with self.assertRaises(ValueError):
                    researcher.run(runner, SOURCE, self.payload, self.tools)
                self.assertEqual(runner.calls, 1)
        self.assertEqual(self.tools.calls, 0)

    def test_unknown_absolute_traversal_and_hidden_paths_are_not_read(self):
        for path in ("../qa.json", "/tmp/private", "labels/qa.json", "filings/hidden.md", "missing.md"):
            with self.subTest(path=path):
                tools = FilingTools(self.data.company)
                runner = self.runner([{"research_requests": [{"tool": "read_file", "arguments": {
                    "path": path, "offset": 0, "characters": 100}}]}])
                with self.assertRaises(ValueError):
                    researcher.run(runner, SOURCE, self.payload, tools)
                self.assertEqual(runner.calls, 1)
                self.assertEqual(tools.calls, 1)

    def test_original_read_search_and_numeric_argument_bounds_apply(self):
        invalid = [
            {"tool": "read_file", "arguments": {"path": "filings/old.md", "offset": -1, "characters": 1}},
            {"tool": "read_file", "arguments": {"path": "filings/old.md", "offset": False, "characters": 1}},
            {"tool": "read_file", "arguments": {"path": "filings/old.md", "offset": 0, "characters": 20001}},
            {"tool": "read_file", "arguments": {"path": "filings/old.md", "offset": 0, "characters": 0}},
            {"tool": "search_files", "arguments": {"query": "revenue", "path_prefix": "filings/", "max_hits": 51}},
            {"tool": "search_files", "arguments": {"query": "", "path_prefix": "filings/", "max_hits": 1}},
            {"tool": "search_files", "arguments": {"query": "revenue", "path_prefix": "../", "max_hits": 1}},
            {"tool": "calculate", "arguments": {"expression": "__import__('os')"}},
        ]
        for request in invalid:
            with self.subTest(request=request):
                runner = self.runner([{"research_requests": [request]}])
                with self.assertRaises(ValueError):
                    researcher.run(runner, SOURCE, self.payload, FilingTools(self.data.company))
                self.assertEqual(runner.calls, 1)

    def test_shared_existing_call_and_return_budgets_stop_before_second_container(self):
        for calls, returned in ((79, 0), (80, 0), (0, 2_000_000)):
            with self.subTest(calls=calls, returned=returned):
                tools = FilingTools(self.data.company)
                tools.calls, tools.returned = calls, returned
                runner = self.runner([REQUEST_PHASE, ADVICE])
                with self.assertRaises(ValueError):
                    researcher.run(runner, SOURCE, self.payload, tools)
                self.assertEqual(runner.calls, 1)
                self.assertTrue(Path(runner.invocations[0]["receipt"]["path"]).is_file())

    def test_unfulfilled_request_or_incomplete_observation_envelope_refuses(self):
        runner = self.runner([REQUEST_PHASE])
        first = runner.run(SOURCE, self.payload)
        with self.assertRaisesRegex(ValueError, "Unfulfilled"):
            researcher.verify(first, SOURCE, self.payload, self.data.company)
        execution, _ = self.completed()
        for key in ("request_execution", "research_observations"):
            changed = deepcopy(execution)
            del changed[key]
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "Incomplete"):
                researcher.verify(changed, SOURCE, self.payload, self.data.company)

    def test_forged_observations_source_or_base_input_refuse(self):
        execution, _ = self.completed()
        changed = deepcopy(execution)
        changed["research_observations"][0]["output"]["text"] = "Forged value 999"
        with self.assertRaisesRegex(ValueError, "original allowed public data"):
            researcher.verify(changed, SOURCE, self.payload, self.data.company)
        changed = deepcopy(execution)
        changed["research_observations"][0]["request"]["arguments"]["offset"] = 1
        with self.assertRaises(ValueError):
            researcher.verify(changed, SOURCE, self.payload, self.data.company)
        with self.assertRaises(ValueError):
            researcher.verify(execution, SOURCE + "\n", self.payload, self.data.company)
        with self.assertRaises(ValueError):
            researcher.verify(execution, SOURCE, dict(self.payload, stage="controller"), self.data.company)

    def test_first_and_second_original_input_stdout_and_receipt_tampering_refuse(self):
        for phase in ("request_execution", "final"):
            for name in ("input.json", "stdout.bin", "result.json"):
                with self.subTest(phase=phase, name=name):
                    execution, _ = self.completed()
                    original = execution if phase == "final" else execution[phase]
                    path = Path(original["receipt"]["path"]).parent / name
                    path.write_bytes(path.read_bytes() + b" ")
                    with self.assertRaises(ValueError):
                        researcher.verify(execution, SOURCE, self.payload, self.data.company)

    def test_changed_public_source_snapshot_refuses_reverification(self):
        execution, _ = self.completed()
        path = Path(self.data.company["visible_root"]) / "filings/old.md"
        path.write_text("Changed public source value 999")
        with self.assertRaises(ValueError):
            researcher.verify(execution, SOURCE, self.payload, self.data.company)

    def test_evidence_cost_rows_rejoin_both_originals_and_return_a_detached_copy(self):
        execution, runner = self.completed()
        rows = researcher.evidence_rows(execution)
        self.assertEqual(rows, execution["research_observations"])
        rows[0]["output"]["text"] = "Changed returned copy"
        self.assertNotEqual(rows, execution["research_observations"])
        self.assertEqual(len(researcher.evidence_rows(execution)), 3)
        self.assertEqual(runner.calls, 2)
        changed = deepcopy(execution)
        changed["research_observations"] = changed["research_observations"][:-1]
        with self.assertRaises(ValueError):
            researcher.evidence_rows(changed)
        changed = deepcopy(execution)
        changed["research_observations"][0]["output"]["text"] = "Forged evidence cost"
        with self.assertRaises(ValueError):
            researcher.evidence_rows(changed)
        legacy = self.runner([{}]).run("PROGRAM={'axis':'R'}\ndef run(p): return {}\n", self.payload)
        self.assertEqual(researcher.evidence_rows(legacy), [])
        legacy["research_observations"] = execution["research_observations"]
        with self.assertRaises(ValueError):
            researcher.evidence_rows(legacy)


class ProgramWorkerResearcherEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.native = native_fixture.ProgramCapacityTests(
            "test_kernel_and_other_axis_preserved_in_program_proposal")
        self.native.setUp()
        self.addCleanup(self.native.doCleanups)
        self.data = state_fixture.ResearchStateTests(
            "test_append_preserves_parent_and_old_history")
        self.data.setUp()
        self.addCleanup(self.data.doCleanups)
        self.root = self.native.root
        self.workers = 0

    def pending_R(self, case_runner=None):
        payload = {"stage": "forecast", "questions": self.data.files["questions.md"],
                   "filing_index": self.data.files["filing_index.tsv"], "records": []}
        tools = FilingTools(self.data.company)
        observations = [{"request": deepcopy(row), "output": tools.dispatch(row["tool"], row["arguments"])}
                        for row in REQUESTS]
        chosen = {"schema": "earnings_capacity_decision_v1", "axis": "R", "component": "research_policy",
                  "parent_pair_sha256": digest(self.native.micro["pair"]),
                  "feedback_sha256": digest("synthetic evidence-interface feedback"),
                  "hypothesis": "Synthetic same-R evidence/computation wiring, not actual autonomous research",
                  "expected_effect": "Synthetic protocol verification only"}
        authored = {"decision_sha256": digest(chosen), "source_text": SOURCE,
                    "test_text": "CASES = " + repr([
                        {"input": payload, "expected": REQUEST_PHASE},
                        {"input": dict(payload, research_observations=observations), "expected": ADVICE},
                    ])}
        decoded = candidate(authored, {"axis": "R"}, chosen)
        descriptor = {"parent_identity": self.native.before, "parent_entrypoints": self.native.entries,
                      "parent_pair_sha256": chosen["parent_pair_sha256"], "decision_sha256": digest(chosen),
                      "candidate": engine.save(self.root / "candidate-R.json", decoded),
                      "author_original": engine.save(self.root / "author-R.json", authored),
                      "micro_evolution": self.native.batch.snapshot()["micro_evolution"]}
        case_runner = case_runner or ScriptedReceiptRunner(
            self.root / "synthetic-case-runner", [REQUEST_PHASE, ADVICE])
        slot = str(self.root / "review-R")
        review = ProgramSourceReview(self.native.source,
            slots={slot: {"candidate_id": "synthetic-evidence-R", "R": "R1.py", "H": "H1.py"}},
            proposer_id="synthetic-author", reviewer_id="host-reviewer", runner=case_runner)
        spec = review.review(chosen, authored, descriptor, slot)
        self.native.capacity.propose(spec["after"], spec["proposal"], spec["entrypoints"],
            static_review=spec["static_review"],
            expected_state_sha256=self.native.batch.snapshot()["state_sha256"])
        return self.native.batch.snapshot()["micro_evolution"]["pending"]["record_sha256"]

    def worker(self, runner, shadow=None):
        self.workers += 1
        return ProgramWorker(self.data.company, "fixture-task", self.native.restore(),
            digest(self.native.batch.snapshot()["micro_evolution"]["active_pair"]),
            self.root / f"memory-{self.workers}", runner=runner, shadow_proposal_sha256=shadow)

    def test_selected_R_reads_original_filing_and_next_cold_forecast_request_uses_computation(self):
        shadow = self.pending_R()
        runner = ScriptedReceiptRunner(self.root / "ordinary-R-runner",
                                      [REQUEST_PHASE, ADVICE, REQUEST_PHASE, ADVICE])
        first = self.worker(runner, shadow)
        worker = self.worker(runner, shadow)
        self.assertEqual(runner.calls, 4)
        self.assertNotEqual(first.r_execution["receipt"], worker.r_execution["receipt"])
        self.assertEqual(first.context, worker.context)
        self.assertEqual(worker.calls, 3)
        self.assertEqual(worker.executions, [])
        self.assertEqual(worker._source("H"), (self.native.source / "H0.py").read_text())
        selected = worker.capacity.resolve("R", expected_pair_sha256=worker.pair,
                                         shadow_proposal_sha256=shadow)
        self.assertEqual(selected["receipt"]["source"]["sha256"], hashlib.sha256(SOURCE.encode()).hexdigest())
        execution = worker.r_execution
        initial = engine.read(engine.pin(Path(execution["request_execution"]["receipt"]["path"]).parent / "input.json"))
        following = engine.read(engine.pin(Path(execution["receipt"]["path"]).parent / "input.json"))
        self.assertEqual(initial["source"], SOURCE)
        self.assertEqual(following["source"], initial["source"])
        self.assertEqual(initial["payload"], worker.r_payload)
        self.assertEqual(following["payload"], dict(worker.r_payload,
                         research_observations=execution["research_observations"]))
        self.assertEqual(following["payload"]["research_observations"][0]["output"]["text"],
                         self.data.files["filings/old.md"])
        self.assertEqual(worker.context["program_execution"]["research_observations_sha256"],
                         digest(execution["research_observations"]))
        requests = []
        def response(client, request, *unused, completion_request=None):
            requests.append(deepcopy(request))
            result = {"output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps({
                "predictions": [{"target_id": "T001", "predicted_value": 100}]})}]}]}
            return (result, False) if completion_request is not None else result
        output = self.root / "forecast-output"
        output.mkdir()
        with patch.object(forecast, "budgeted_response", side_effect=response):
            forecast.forecast(None, {"api_model": "gpt-6.1-sol", "effort": "xhigh"},
                {"max_turns_per_company": 3, "company_wall_seconds": 30},
                self.data.company, None, output, capacity_worker=worker)
        self.assertEqual(len(requests), 1)
        self.assertEqual(json.loads(requests[0]["input"][-1]["content"].split("\n", 1)[1]), ADVICE)
        summary = engine.read(engine.pin(output / "program-executions.json"))
        self.assertEqual(summary["R"], execution)
        self.assertEqual(summary["H"], [])
        self.assertEqual(runner.calls, 4)
        worker._check()
        self.assertEqual(worker.calls, 3)

    def test_selected_R_observation_tamper_rejects_before_any_new_model_request(self):
        shadow = self.pending_R()
        runner = ScriptedReceiptRunner(self.root / "tamper-runner", [REQUEST_PHASE, ADVICE])
        worker = self.worker(runner, shadow)
        worker.r_execution["research_observations"][0]["output"]["text"] = "Fabricated 999"
        with self.assertRaises(ValueError):
            worker._check()
        self.assertEqual(runner.calls, 2)
        self.assertEqual(worker.executions, [])

    def test_original_R0_worker_is_compatible_without_a_new_H_or_evidence_phase(self):
        runner = ScriptedReceiptRunner(self.root / "legacy-runner", [{}])
        worker = self.worker(runner)
        self.assertEqual(runner.calls, 1)
        self.assertEqual(worker.calls, 0)
        self.assertEqual(worker.executions, [])
        self.assertNotIn("research_observations", worker.r_execution)
        self.assertNotIn("research_observations_sha256", worker.context["program_execution"])
        self.assertEqual(json.loads(worker.context["messages"][-1]["content"].split("\n", 1)[1]), {})
        worker._check()

    @unittest.skipUnless(os.environ.get("EARNINGS_OPEN_DOCKER_TESTS") == "1",
                         "explicit Docker integration only")
    def test_actual_container_same_R_algorithm_computes_from_original_allowed_filing(self):
        runner = DockerRunner(self.root / "actual-R-docker", max_calls=8)
        shadow = self.pending_R(case_runner=runner)
        first = self.worker(runner, shadow)
        worker = self.worker(runner, shadow)
        self.assertEqual(runner.calls, 6)
        self.assertNotEqual(first.r_execution["receipt"], worker.r_execution["receipt"])
        self.assertEqual(researcher.verify(worker.r_execution, SOURCE, worker.r_payload,
                                           self.data.company), ADVICE)
        self.assertEqual(worker.calls, 3)
        self.assertEqual(worker.executions, [])
        for execution in researcher.originals(worker.r_execution):
            receipt = engine.read(execution["receipt"])
            self.assertFalse(receipt["host_candidate_execution"])
            self.assertTrue(receipt["cleanup_verified"])
            self.assertNotIn("synthetic", receipt)
            self.assertEqual(receipt["source_sha256"], hashlib.sha256(SOURCE.encode()).hexdigest())
        self.assertEqual(first.context, worker.context)


class ResearcherAssemblyAccountingTests(unittest.TestCase):
    def test_real_Task_execution_and_trace_measurement_count_R_evidence_without_erasing_cost(self):
        import test_earnings_open_assembly as open_fixture
        import earnings_shadow_measurement as measurement
        import earnings_open_evidence as public_trace

        helper = open_fixture.OpenAssemblyTests(
            "test_complete_open_continue_delivers_actual_final_feedback_to_next_controller")
        self.addCleanup(helper.doCleanups)
        fixture = helper.fixture()
        # A human-declared invented R baseline, not a claimed model mutation.
        declared = fixture.raw.root / "invented-evidence-R.py"
        declared.write_text(SOURCE)
        fixture.copy("researcher_v1.py", declared)
        researcher_component = {
            "sources": {"researcher_v1.py": fixture.copies["researcher_v1.py"]},
            "configuration_sha256": fixture.native["baseline"]["components"]["R"]["configuration_sha256"],
        }
        fixture.rebuild_baseline(researcher=researcher_component)
        fixture.native["micro_config"]["pair"] = engine.activation.pair(fixture.native["baseline"])
        fixture.assembly["native"] = fixture.save("evidence-native", fixture.native)
        review = engine.read(fixture.assembly["independent_review"])
        review["reviewed_configuration_sha256"] = digest({
            key: value for key, value in fixture.assembly.items() if key != "independent_review"})
        fixture.assembly["independent_review"] = fixture.save("invented-evidence-review", review)
        fixture.assembly_binding = fixture.save("evidence-assembly", fixture.assembly)
        runners = []
        def runner_factory(root, **unused):
            runner = ScriptedReceiptRunner(root, [REQUEST_PHASE, ADVICE] * 5)
            runners.append(runner)
            return runner
        sequence = [fixture.raw.research(), fixture.raw.final(),
                    helper.choose(fixture, "continue"), fixture.raw.research(), fixture.raw.final(),
                    helper.choose(fixture, "continue")]
        with helper.scope(fixture), fixture.exchange(sequence), patch.object(
                open_fixture.assembly, "DockerRunner", side_effect=runner_factory):
            result = engine.read(open_fixture.assembly.run(fixture.episode_binding, fixture.assembly_binding))
        # Completing the real assembly has already exercised OpenTask.execution
        # and earnings_execution_receipt.verify on both original scored forecasts.
        self.assertEqual(result["outcome"]["completed_rounds"], 2)
        self.assertEqual(len(runners), 1)
        self.assertEqual(runners[0].calls, 10)
        for index, slots in enumerate(fixture.slots, 1):
            with self.subTest(round=index):
                output = engine.read(engine.pin(
                    fixture.root / "loop" / f"round-{index:04d}-execute.done.json"))["output"]
                observed = measurement.observe(output)
                root = Path(slots["forecast"])
                summary = engine.read(engine.pin(root / "program-executions.json"))
                evidence = researcher.evidence_rows(summary["R"])
                provider_calls = sum(len([row for row in engine.read(engine.pin(path))["output"]
                                          if row.get("type") == "function_call"])
                                     for path in root.glob("[0-9][0-9]-response.json"))
                self.assertEqual(len(evidence), 3)
                self.assertEqual(provider_calls, 2)
                self.assertEqual(observed["tool_calls"], 5)
                self.assertEqual(engine.read(output["result"])["tool_calls"], 5)
                provider_characters = sum(len(engine.read(engine.pin(path))["output"])
                                          for path in root.glob("[0-9][0-9]-tool-*.json"))
                self.assertEqual(observed["tool_return_characters"], provider_characters
                                 + sum(len(json.dumps(row["output"])) for row in evidence))
                self.assertEqual(observed["score_out_of_5"], engine.read(output["score"])["score_out_of_5"])
                self.assertEqual(summary["H"], [])
                paths = {binding["path"] for binding in output["artifacts"]}
                for execution in researcher.originals(summary["R"]):
                    self.assertIn(execution["receipt"]["path"], paths)
                    self.assertIn(str(Path(execution["receipt"]["path"]).parent / "input.json"), paths)
                publication_path = root / "researcher-public-tools.json"
                publication_binding = engine.pin(publication_path)
                publication = engine.read(publication_binding)
                self.assertIn(publication_binding, output["artifacts"])
                self.assertEqual(publication, {
                    "schema": "earnings_public_researcher_tools_v1", "observations": evidence,
                    "request_execution_sha256": summary["R"]["request_execution"]["receipt"]["sha256"],
                    "execution_sha256": summary["R"]["receipt"]["sha256"],
                })
                reader = public_trace.TraceReader({"forecast": root})
                events, manifests = [], set()
                for offset in range(5):
                    page = reader.read("forecast", max_events=1, max_output_chars=300, offset=offset)
                    self.assertEqual((page["total_events"], page["returned_events"]), (5, 1))
                    self.assertEqual(page["aggregates"]["tool_calls"], 5)
                    self.assertEqual(page["next_offset"], offset + 1 if offset < 4 else None)
                    self.assertLessEqual(len(encoded(page)), 6000)
                    manifests.add(page["source_manifest_sha256"])
                    events.extend(page["events"])
                self.assertEqual(len(manifests), 1)
                self.assertEqual(sum(row.get("actor") == "researcher_program" for row in events), 3)
                self.assertEqual(sum(row.get("actor") != "researcher_program" for row in events), 2)
                self.assertEqual([(row["turn"], row["name"]) for row in events[:3]],
                                 [(0, request["tool"]) for request in REQUESTS])
                for event, item in zip(events[:3], evidence):
                    self.assertEqual(event["arguments"], item["request"]["arguments"])
                    self.assertEqual(event["source_sha256"], publication_binding["sha256"])
                    text = json.dumps(item["output"], sort_keys=True, allow_nan=False)
                    self.assertEqual(event["output_sha256"], hashlib.sha256(text.encode()).hexdigest())
                    self.assertEqual(event["output"], text[:len(event["output"])])
                # Even a last-provider-event page validates the complete R
                # publication schema; no reasoning/context field can be added.
                original_publication = publication_path.read_bytes()
                try:
                    publication_path.write_bytes(encoded(dict(publication, reasoning="MUST_NOT_PROJECT")))
                    with self.assertRaises(ValueError):
                        reader.read("forecast", max_events=1, max_output_chars=300, offset=4)
                finally:
                    publication_path.write_bytes(original_publication)
        self.assertEqual(result["outcome"]["result"]["feedback"]["public_trace"]["total_events"], 5)


if __name__ == "__main__":
    unittest.main()
