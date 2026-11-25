"""Actual driver/Controller/forecaster/tools/ledger on invented public fixtures."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import earnings_feedback_loop as flow
import earnings_controller_archive as archive
from edgar_forecast_budget import PilotBudget
from edgar_forecast_full_budget import activate, FullBudget
from earnings_night_budget import history_snapshot, NightBudget, DeadlineHTTP, utc_epoch

MODEL = "gpt-6.1-sol"
TARGETS = [f"T{i:03d}" for i in range(1, 6)]


class FeedbackLoopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        visible = self.root / "visible"
        files = {"questions.md": "\n".join(f"### {t} | invented quantity" for t in TARGETS),
            "filing_index.tsv": "date_filed\tform_type\taccession\tpath\n2026-01-01\t10-Q\told\tfilings/10-Q_old.md\n",
            "filings/10-Q_old.md": "invented public quantity 100"}
        self.company = {"visible_root": str(visible), "cutoff": "2026-02-01", "target_accession": "hidden", "allowed_files": []}
        for name, text in files.items():
            path = visible / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
            self.company["allowed_files"].append({"path": name, "bytes": len(text.encode()), "sha256": flow.e.digest(text.encode())})
        ledger = self.root / "invented.sqlite3"
        old = PilotBudget(ledger)
        old.close()
        activate(ledger, "a" * 64, "b" * 40)
        budget = FullBudget(ledger)
        baseline = history_snapshot(budget.db)
        budget.close()
        qa = self.root / "invented-qa.json"
        flow.save(qa, {"fixture_only": True})
        self.config = {"task_id": "synthetic-task", "cik": "synthetic-cik", "source_commit": "a" * 40,
            "ledger": str(ledger), "baseline": baseline, "output": str(self.root / "attempts" / "baseline"),
            "qa": flow.binding(qa), "model": MODEL, "review": {"fixture": True}, "launch_policy_sha256": "c" * 64,
            "deadline_utc": "2099-01-01T01:00:00Z", "new_request_cutoff_utc": "2099-01-01T00:30:00Z",
            "runtime_config": {"request_timeout_seconds": 1200, "company_wall_seconds": 1800,
                "max_input_tokens": 100000, "max_output_tokens": 25000, "final_max_output_tokens": 65536,
                "max_turns_per_company": 2, "models": {MODEL: {"api_model": MODEL, "effort": "xhigh",
                    "input": "2", "cached": ".1", "write": "2.5", "output": "10"}}}}
        self.envelope = {"source_commit": "a" * 40, "baseline_config": self.config,
            "root": str(self.root / "loops" / "earnings-feedback-01"),
            "forecasts": [str(self.root / "attempts" / f"child-{i}") for i in (1, 2)],
            "controllers": [str(self.root / "controllers" / f"child-{i}") for i in (1, 2)],
            "controller_limits": flow.policy.LIMITS, "review": {"fixture": True}, "loop_policy_sha256": "d" * 64}
        self.envelope_binding = flow.save(self.root / "envelope.json", self.envelope)
        observation = {"schema": "earnings_aggregate_feedback_v1", "task_id": "synthetic-task", "cik": "synthetic-cik",
            "prediction": {"planned_targets": 5, "scored_targets": 0, "score_out_of_5": None},
            "execution": {"status": "FAILED_NO_RETRY", "error_type": "ValueError"}}
        self.seed = {"feedback": {"observation": observation, "baseline_score_out_of_5": 1.5}, "prior_recipe": None, "artifacts": []}
        self.controller_payloads, self.forecasters = [], []
        self.bad_controller = False
        self.bad_forecast = False
        self.scorer = Mock(side_effect=self.score)
        patches = [patch.object(flow.e, "ARCHIVE", self.root),
            patch.object(flow.policy, "validate_envelope", return_value=(self.company, TARGETS, self.scorer)),
            patch.object(archive, "validate_envelope", return_value=(self.company, TARGETS, self.scorer)),
            patch.object(flow.e, "preflight", return_value=(self.company, TARGETS, self.scorer)),
            patch.object(flow, "baseline_seed", return_value=self.seed), patch.object(flow.e, "credential")]
        patches.insert(-1, patch.object(flow.clock, "boot_id", return_value="11111111-1111-1111-1111-111111111111"))
        self.keys = patches[-1].start()
        self.addCleanup(patches[-1].stop)
        for p in patches[:-1]:
            p.start()
            self.addCleanup(p.stop)

    def score(self, **kwargs):
        points = kwargs["predictions_payload"]["predictions"][0]["predicted_value"]
        return {"score_out_of_5": points, "target_count": 5, "prediction_count": 5,
                "duplicate_prediction_ids": [], "unknown_prediction_ids": []}

    def provider(self, role):
        outer = self
        class Provider:
            timeout = 1200
            turns = 0
            def post(self, endpoint, payload):
                if endpoint.endswith("input_tokens"):
                    return {"input_tokens": 100}
                self.turns += 1
                if role == "controller":
                    packet = json.loads(payload["input"][0]["content"])
                    outer.controller_payloads.append(packet)
                    n = len(outer.controller_payloads)
                    recipe = {"schema": "earnings_research_recipe_v1", "task_id": packet["task_id"],
                        "parent_feedback_sha256": packet["parent_feedback_sha256"], "research_instructions": f"calculate 100 + {n}"}
                    text = "invalid JSON" if outer.bad_controller else json.dumps(recipe)
                    output = [{"type": "message", "content": [{"type": "output_text", "text": text}]}]
                else:
                    recipe = json.loads(payload["input"][1]["content"].split("\n", 1)[1])
                    self.recipe = recipe
                    n = int(recipe["research_instructions"][-1])
                    if self.turns == 1:
                        output = [{"type": "function_call", "call_id": f"action-{n}", "name": "calculate",
                                   "arguments": json.dumps({"expression": f"100 + {n}"})}]
                    else:
                        text = "invalid JSON" if outer.bad_forecast else json.dumps({"predictions": [
                            {"target_id": t, "predicted_value": n} for t in TARGETS]})
                        output = [{"type": "message", "content": [{"type": "output_text", "text": text}]}]
                return {"status": "completed", "model": MODEL, "service_tier": "default", "output": output,
                    "usage": {"input_tokens": 100, "output_tokens": 10, "total_tokens": 110,
                              "input_tokens_details": {"cached_tokens": 0}}}
        provider = Provider()
        if role == "forecaster":
            self.forecasters.append(provider)
        return provider

    def run_loop(self):
        return flow.run(self.envelope_binding, controller_factory=lambda: self.provider("controller"),
                        forecast_factory=lambda: self.provider("forecaster"))

    def test_actual_two_round_delivery_tools_settlement_and_no_duplicate_replay(self):
        result = self.run_loop()
        self.assertEqual((result["status"], result["completed_rounds"]), ("completed", 2))
        first = flow.driver._read_pair(Path(self.envelope["root"]) / "round-0001-reconcile.done.json")["output"]
        self.assertEqual(self.controller_payloads[1]["parent_feedback_sha256"], flow.driver.c._digest(first))
        self.assertEqual(self.controller_payloads[1]["feedback"]["observation"]["prediction"]["score_out_of_5"], 1)
        self.assertEqual(self.controller_payloads[1]["prior_research_instructions"], "calculate 100 + 1")
        self.assertEqual(result["result"]["delta_from_parent"], 1)
        self.assertTrue(result["result"]["recipe_changed"])
        for n, provider in enumerate(self.forecasters, 1):
            output = Path(self.envelope["forecasts"][n - 1])
            receipt = json.loads((output / "effective-recipe.json").read_text())
            self.assertEqual(receipt["recipe"], provider.recipe)
            action = json.loads(next(output.glob("01-tool-*.json")).read_text())
            self.assertEqual(json.loads(action["output"])["value"], 100 + n)
        budget = FullBudget(self.config["ledger"])
        self.assertEqual(budget.summary()["generation_requests_reserved"], 6)
        self.assertEqual(budget.summary()["unresolved_reserved_usd"], 0)
        budget.close()
        before = len(self.controller_payloads), len(self.forecasters)
        self.assertEqual(self.run_loop(), result)
        self.assertEqual((len(self.controller_payloads), len(self.forecasters)), before)
        self.keys.assert_not_called()

    def test_bad_controller_preserves_charge_and_closes_round_without_forecast(self):
        self.bad_controller = True
        with self.assertRaises(flow.driver.LoopHalted):
            self.run_loop()
        with self.assertRaises(flow.driver.LoopHalted):
            self.run_loop()
        self.assertEqual((len(self.controller_payloads), len(self.forecasters)), (1, 0))
        self.assertTrue((Path(self.envelope["controllers"][0]) / "01-response.json").exists())
        self.assertTrue((Path(self.envelope["root"]) / "round-0001-controller.failed.json").exists())

    def test_bad_forecast_stops_before_second_controller_and_preserves_failure(self):
        self.bad_forecast = True
        with self.assertRaises(flow.driver.LoopHalted):
            self.run_loop()
        self.assertEqual((len(self.controller_payloads), len(self.forecasters)), (1, 1))
        result = json.loads((Path(self.envelope["forecasts"][0]) / "result.json").read_text())
        self.assertEqual(result["status"], "FAILED_NO_RETRY")
        with self.assertRaises(flow.driver.LoopHalted):
            self.run_loop()
        self.assertEqual(len(self.forecasters), 1)

    def test_cross_role_rollback_and_resume_do_not_reopen_original_cutoff(self):
        wall = [utc_epoch(self.config["new_request_cutoff_utc"]) - 1]
        mono = [100.0]
        class ClockBudget(NightBudget):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs, clock=lambda: wall[0], monotonic=lambda: mono[0])
        class ClockHTTP(DeadlineHTTP):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs, clock=lambda: wall[0], monotonic=lambda: mono[0])
        def scored(**kwargs):
            result = self.score(**kwargs)
            wall[0] -= 3600
            mono[0] += 2
            return result
        self.scorer.side_effect = scored
        with patch.object(flow.time, "time", side_effect=lambda: wall[0]), \
                patch.object(flow.time, "monotonic", side_effect=lambda: mono[0]), \
                patch.object(flow.e, "NightBudget", ClockBudget), \
                patch.object(flow.controller, "NightBudget", ClockBudget), \
                patch.object(flow.e, "DeadlineHTTP", ClockHTTP), \
                patch.object(flow.controller, "DeadlineHTTP", ClockHTTP):
            result = self.run_loop()
            self.assertEqual(result, {"status": "stopped", "completed_rounds": 1,
                                     "round_index": 2, "stage": "controller"})
            clock_path = Path(self.envelope["root"]) / "clock.json"
            original = clock_path.read_bytes()
            self.assertEqual(json.loads(original)["cutoff_monotonic"], 101)
            self.assertEqual(self.run_loop(), result)
            self.assertEqual(clock_path.read_bytes(), original)
        self.assertEqual((len(self.controller_payloads), len(self.forecasters)), (1, 1))
        self.assertFalse(Path(self.envelope["controllers"][1]).exists())
        self.assertFalse(Path(self.envelope["forecasts"][1]).exists())
        self.keys.assert_not_called()

    def test_changed_boot_refuses_completed_replay_before_any_new_role(self):
        self.run_loop()
        before = len(self.controller_payloads), len(self.forecasters)
        with patch.object(flow.clock, "boot_id", return_value="different-boot"):
            with self.assertRaises(ValueError):
                self.run_loop()
        self.assertEqual((len(self.controller_payloads), len(self.forecasters)), before)

    def test_archival_first_stage_uses_unchanged_paid_candidate_then_one_new_controller(self):
        # Invented prior call: original accounting runs, only old2000 guard is injected.
        (self.root / "loops" / "earnings-feedback-01").mkdir(parents=True)
        old_source = "c" * 40
        old_clock, old_clock_binding = flow.clock.capture_or_load(
            self.root / "loops" / "earnings-feedback-01", dict(self.config, source_commit=old_source))
        old_packet = {"schema": "earnings_controller_packet_v1", "task_id": self.config["task_id"],
            "parent_feedback_sha256": flow.driver.c._digest(self.seed),
            "questions": flow.e.FilingTools(self.company).files["questions.md"],
            "feedback": self.seed["feedback"], "prior_recipe": None}
        old_packet_binding = flow.save(self.root / "loops" / "earnings-feedback-01" / "packet-01.json", old_packet)
        old = self.root / "controllers" / "old-rejected"
        old.mkdir(parents=True)
        long_text = "calculate 100 + 1; " + "x" * 2007 + "1"
        self.assertEqual(len(long_text), 2027)
        recipe = {"schema": "earnings_research_recipe_v1", "task_id": self.config["task_id"],
            "parent_feedback_sha256": old_packet["parent_feedback_sha256"], "research_instructions": long_text}
        outer = self
        class OldProvider:
            timeout = 1200
            def post(self, endpoint, payload):
                if endpoint.endswith("input_tokens"):
                    return {"input_tokens": 100}
                outer.controller_payloads.append(json.loads(payload["input"][0]["content"]))
                return {"status": "completed", "model": MODEL, "service_tier": "default",
                    "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(recipe)}]}],
                    "usage": {"input_tokens": 100, "output_tokens": 10, "total_tokens": 110,
                              "input_tokens_details": {"cached_tokens": 0}}}
        old_envelope = copy.deepcopy(self.envelope)
        old_envelope["source_commit"] = old_source
        old_envelope["baseline_config"]["source_commit"] = old_source
        flow.save(old / "identity.json", {"source_commit": old_source, "input_packet": old_packet_binding,
            "round_index": 1, "limits": flow.policy.LIMITS, "clock": old_clock_binding})
        with patch.object(flow.controller, "parse_recipe", side_effect=ValueError("Synthetic old2000-character guard")):
            with self.assertRaises(RuntimeError):
                flow.controller._claimed(old_envelope, old_packet, old_packet_binding,
                    flow.controller.safe_input(old_packet), old, flow.time.monotonic() + 60, OldProvider)
        self.config["archived_first_controller"] = {"original_source_commit": old_source,
            **{key: flow.binding(old / filename) for key, filename in (
                ("response", "01-response.json"), ("count", "01-count.json"), ("request", "01-request.json"),
                ("failure_result", "result.json"), ("identity", "identity.json"))}, "input_packet": old_packet_binding}
        # Preserve original clock bytes across the new-source/new-root episode.
        self.config["inherited_clock"] = {"binding": old_clock_binding, "source_commit": old_source}
        self.envelope["root"] = str(self.root / "loops" / "earnings-feedback-recovery-01")
        self.envelope["baseline_config"] = self.config
        new_path = self.root / "recovery-envelope.json"
        self.envelope_binding = flow.save(new_path, self.envelope)
        old_bytes = {p.name: p.read_bytes() for p in old.iterdir() if p.is_file()}
        result = self.run_loop()
        self.assertEqual(result["completed_rounds"], 2)
        self.assertEqual(len(self.controller_payloads), 2)  # One old paid fixture + one new call.
        receipt = json.loads((Path(self.envelope["forecasts"][0]) / "effective-recipe.json").read_text())
        self.assertEqual(receipt["recipe"], recipe)
        self.assertEqual({p.name: p.read_bytes() for p in old.iterdir() if p.is_file()}, old_bytes)
        self.assertEqual(flow.clock.capture_or_load(self.envelope["root"], self.config), (old_clock, old_clock_binding))
        self.assertFalse((Path(self.envelope["root"]) / "clock.json").exists())
        budget = FullBudget(self.config["ledger"])
        self.assertEqual(budget.summary()["generation_requests_reserved"], 6)
        self.assertEqual(budget.summary()["unresolved_reserved_usd"], 0)
        budget.close()
        # Completed replay invokes neither archive nor new model again.
        before = len(self.controller_payloads), len(self.forecasters)
        self.assertEqual(self.run_loop(), result)
        self.assertEqual((len(self.controller_payloads), len(self.forecasters)), before)


if __name__ == "__main__":
    unittest.main()
