"""Synthetic callback acceptance of population feedback connection and closure.

The real seven-stage once-only journal and pure population transitions run;
Controller, Author, review and forecast are explicit synthetic callbacks.
Ten completed rounds here do not constitute ten real research experiments.
"""
import copy
import json
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research" / "market_rsi"))
import earnings_population_loop as loop
from market_rsi import digest
from supervisor_harness import feedback_linked_loop as journal
from test_earnings_population import PopulationFixture


class PopulationLoopTests(PopulationFixture):
    def setUp(self):
        super().setUp()
        self.loop_root = self.root / "population"
        self.journal_root = self.loop_root / "loop"
        self.companies = [f"synthetic-cik-{index:02d}" for index in range(10)]
        self.calls = {name: [] for name in ("controller", "author", "review", "forecast")}
        self.trace = ["R"] + ["continue"] * 9
        self.bad_feedback = False
        self.reject_review = False
        self.fail_forecast_at = None
        self.mutate_source_on_first_forecast = False
        self.invalid_first_forecast_score = False
        self.retire_when_full = False
        self.retire_stable = False
        self.reject_review_at = None
        self.identities = {stage: {"synthetic_callback_identity": stage} for stage in journal.STAGES}

    def controller(self, packet, slot):
        self.calls["controller"].append(copy.deepcopy(packet))
        index = packet["round_index"] - 1
        state = packet["population"]
        choice = {
            "schema": "earnings_capacity_decision_v1",
            "axis": self.trace[index],
            "component": "research_policy" if self.trace[index] == "R" else
                         "tool_interface" if self.trace[index] == "H" else "none",
            "parent_pair_sha256": state["stable_id"],
            "feedback_sha256": "0" * 64 if self.bad_feedback else digest(packet["feedback"]),
            "hypothesis": "A declared synthetic hypothesis tests journal ordering only.",
            "expected_effect": "Synthetic callback evidence, no scientific claim.",
        }
        if self.retire_stable:
            choice["retire_branch_id"] = state["stable_id"]
        elif self.retire_when_full and len(state["explorers"]) == 2:
            choice["retire_branch_id"] = state["explorers"][0]
        return self.artifact(choice, "decision")

    def author(self, decision, state, slot):
        self.calls["author"].append(copy.deepcopy(decision))
        # Accepting bindings at this callback boundary is not a model claim;
        # the normal live adapter must verify physical provider receipts.
        if set(decision) == {"path", "sha256"}:
            decision = json.loads(Path(decision["path"]).read_text())
        return self.child(parent=state["versions"][decision["parent_pair_sha256"]],
                          axis=decision["axis"], label=f"synthetic-method-{len(self.calls['author'])}")

    def review(self, child, state, slot):
        self.calls["review"].append(copy.deepcopy(child))
        return {"accepted_for_exploration": not (self.reject_review or
                self.reject_review_at == len(self.calls["review"])), "evidence": self.evidence}

    def forecast(self, version, company_id, slot):
        self.calls["forecast"].append((version["id"], company_id))
        if self.fail_forecast_at == len(self.calls["forecast"]):
            raise RuntimeError("Synthetic forecast interruption, no automatic retry")
        points = 1.0 if version["id"] == self.stable["id"] else 1.5
        if len(self.calls["forecast"]) == 1:
            if self.mutate_source_on_first_forecast:
                Path(self.r["path"]).write_text("synthetic source drift during first callback")
            if self.invalid_first_forecast_score:
                points = 6.0
        return {"version_id": version["id"], "points": points,
                "evidence": [self.artifact({"company_id": company_id,
                    "version_id": version["id"], "points": points, "synthetic": True})]}

    def services(self):
        return {name: getattr(self, name) for name in self.calls}

    def run_loop(self, *, companies=None, rounds=10, admit=None, initial=None):
        return loop.run(self.loop_root, initial or self.initial,
                        self.companies if companies is None else companies,
                        self.services(), admit=admit or (lambda context: True),
                        max_rounds=rounds, identity=lambda: self.identities)

    def test_ten_synthetic_rounds_link_exact_feedback_preserve_stable_and_replay_without_calls(self):
        before = copy.deepcopy(self.initial)
        result = self.run_loop()
        self.assertEqual((result["status"], result["completed_rounds"]), ("completed", 10))
        state = result["result"]["population"]
        self.assertEqual(self.initial, before)
        self.assertEqual(state["stable_id"], self.stable["id"])
        self.assertEqual(state["anchor_id"], self.stable["id"])
        self.assertEqual(len(state["explorers"]), 1)
        self.assertEqual(len(state["observations"]), 10)
        self.assertEqual([item["company_id"] for item in state["observations"]], self.companies)
        self.assertEqual({name: len(calls) for name, calls in self.calls.items()},
                         {"controller": 10, "author": 1, "review": 1, "forecast": 20})
        for index, packet in enumerate(self.calls["controller"], 1):
            self.assertEqual(packet["company_id"], self.companies[index - 1])
            self.assertEqual(len(packet["population"]["observations"]), index - 1)
            if index > 1:
                previous = journal._read_pair(self.journal_root /
                    f"round-{index - 1:04d}-reconcile.done.json")["output"]
                self.assertEqual(packet["feedback"], previous["feedback"])
                self.assertEqual(packet["previous_feedback_sha256"], digest(previous))
        count_before = {name: len(calls) for name, calls in self.calls.items()}
        self.assertEqual(self.run_loop(), result)
        self.assertEqual({name: len(calls) for name, calls in self.calls.items()}, count_before)

    def test_two_distinct_explorers_coexist_and_third_is_not_silently_dropped(self):
        self.trace = ["R", "H", "R"]
        with self.assertRaises(journal.LoopHalted):
            self.run_loop(rounds=3)
        first = journal._read_pair(self.journal_root / "round-0002-reconcile.done.json")["output"]
        self.assertEqual(len(first["population"]["explorers"]), 2)
        self.assertEqual(len(first["population"]["versions"]), 3)
        self.assertEqual(len(self.calls["forecast"]), 5)
        before = {name: len(calls) for name, calls in self.calls.items()}
        with self.assertRaises(journal.LoopHalted):
            self.run_loop(rounds=3)
        self.assertEqual({name: len(calls) for name, calls in self.calls.items()}, before)

    def test_continue_does_not_call_author_or_review_or_mutate_sources(self):
        self.trace = ["continue"] * 2
        result = self.run_loop(rounds=2)
        self.assertEqual(result["result"]["population"]["explorers"], [])
        self.assertEqual(result["result"]["population"]["versions"], self.initial["versions"])
        self.assertEqual(len(self.calls["author"]), 0)
        self.assertEqual(len(self.calls["review"]), 0)
        self.assertEqual(len(self.calls["forecast"]), 2)

    def test_rejected_candidate_is_preserved_in_journal_but_not_executed(self):
        self.reject_review = True
        self.trace = ["R", "continue"]
        result = self.run_loop(rounds=2)
        self.assertEqual(result["result"]["population"]["explorers"], [])
        self.assertEqual({version_id for version_id, _ in self.calls["forecast"]}, {self.stable["id"]})
        implementation = journal._read_pair(self.journal_root / "round-0001-implement.done.json")["output"]
        child_id = self.calls["review"][0]["id"]
        self.assertIn(child_id, json.dumps(implementation))

    def test_failure_preserved_and_no_later_stage_or_retry(self):
        self.fail_forecast_at = 2
        with self.assertRaises(journal.LoopHalted):
            self.run_loop(rounds=2)
        self.assertEqual(len(self.calls["controller"]), 1)
        self.assertEqual(len(self.calls["forecast"]), 2)
        failure = self.journal_root / "round-0001-execute.failed.json"
        self.assertTrue(failure.is_file())
        self.assertFalse(json.loads(failure.read_text())["retry_allowed"])
        before = {name: len(calls) for name, calls in self.calls.items()}
        with self.assertRaises(journal.LoopHalted):
            self.run_loop(rounds=2)
        self.assertEqual({name: len(calls) for name, calls in self.calls.items()}, before)

    def test_stale_controller_feedback_stops_before_author_or_forecast(self):
        self.bad_feedback = True
        with self.assertRaises(journal.LoopHalted):
            self.run_loop(rounds=2)
        self.assertEqual(len(self.calls["controller"]), 1)
        self.assertEqual(len(self.calls["author"]), 0)
        self.assertEqual(len(self.calls["forecast"]), 0)

    def test_admission_stop_makes_no_role_calls_and_does_not_create_manifest(self):
        result = self.run_loop(rounds=2, admit=lambda context: False)
        self.assertEqual((result["status"], result["completed_rounds"]), ("stopped", 0))
        self.assertEqual(sum(map(len, self.calls.values())), 0)
        self.assertFalse((self.journal_root / "manifest.json").exists())

    def test_duplicate_exposed_or_insufficient_company_plan_refuses_before_callbacks(self):
        for companies in (["duplicate", "duplicate"], ["synthetic-exposed", "new"], ["one"]):
            with self.subTest(companies=companies), self.assertRaises(ValueError):
                self.run_loop(companies=companies, rounds=2)
        self.assertEqual(sum(map(len, self.calls.values())), 0)

    def test_restart_with_changed_company_plan_or_source_cannot_reopen(self):
        self.trace = ["continue"] * 2
        self.run_loop(rounds=2)
        before = {name: len(calls) for name, calls in self.calls.items()}
        with self.assertRaises(journal.LoopHalted):
            self.run_loop(companies=["different", "companies"], rounds=2)
        Path(self.r["path"]).write_text("source drift after completion")
        with self.assertRaises((ValueError, journal.LoopHalted)):
            self.run_loop(rounds=2)
        self.assertEqual({name: len(calls) for name, calls in self.calls.items()}, before)

    def test_source_drift_during_first_forecast_stops_before_next_version_executes(self):
        self.mutate_source_on_first_forecast = True
        with self.assertRaises((ValueError, journal.LoopHalted)):
            self.run_loop(rounds=2)
        self.assertEqual(len(self.calls["forecast"]), 1)
        self.assertEqual(len(self.calls["controller"]), 1)

    def test_invalid_first_score_stops_before_spending_on_next_forecast(self):
        self.invalid_first_forecast_score = True
        with self.assertRaises(journal.LoopHalted):
            self.run_loop(rounds=2)
        self.assertEqual(len(self.calls["forecast"]), 1)
        self.assertEqual(len(self.calls["controller"]), 1)

    def test_admission_stop_between_rounds_resumes_only_unclaimed_stages(self):
        def admission(context):
            return not (context["round_index"] == 2 and context["stage"] == "controller")
        first = self.run_loop(rounds=2, admit=admission)
        self.assertEqual(first, {"status": "stopped", "completed_rounds": 1,
                                 "round_index": 2, "stage": "controller"})
        self.assertEqual((len(self.calls["controller"]), len(self.calls["forecast"])), (1, 2))
        again = self.run_loop(rounds=2, admit=admission)
        self.assertEqual(again, first)
        self.assertEqual((len(self.calls["controller"]), len(self.calls["forecast"])), (1, 2))
        completed = self.run_loop(rounds=2)
        self.assertEqual(completed["status"], "completed")
        self.assertEqual((len(self.calls["controller"]), len(self.calls["author"]),
                          len(self.calls["forecast"])), (2, 1, 4))

    def test_wrong_executed_version_stops_before_second_forecast(self):
        original = self.forecast
        def wrong_version(version, company, slot):
            result = original(version, company, slot)
            result["version_id"] = "f" * 64
            return result
        self.forecast = wrong_version
        with self.assertRaises(journal.LoopHalted):
            self.run_loop(rounds=2)
        self.assertEqual(len(self.calls["forecast"]), 1)

    def test_ten_synthetic_mutations_continue_via_explicit_explorer_replacement(self):
        self.trace = ["R", "H"] * 5
        self.retire_when_full = True
        result = self.run_loop()
        self.assertEqual((result["status"], result["completed_rounds"]), ("completed", 10))
        state = result["result"]["population"]
        self.assertEqual(state["stable_id"], self.stable["id"])
        self.assertEqual(len(state["explorers"]), 2)
        self.assertEqual(len(state["versions"]), 11)
        self.assertEqual(len(state["observations"]), 10)
        self.assertEqual(sum(item["kind"] == "retire_exploration" for item in state["history"]), 8)
        self.assertEqual({name: len(calls) for name, calls in self.calls.items()},
                         {"controller": 10, "author": 10, "review": 10, "forecast": 29})
        for index in range(1, 11):
            frozen = json.loads((self.loop_root / f"frozen-pool-{index:02d}.json").read_text())
            self.assertLessEqual(len(frozen["explorers"]), 2)
            self.assertEqual(len(frozen["versions"]), index + 1)
        before = {name: len(calls) for name, calls in self.calls.items()}
        self.assertEqual(self.run_loop(), result)
        self.assertEqual({name: len(calls) for name, calls in self.calls.items()}, before)

    def test_rejected_replacement_keeps_old_explorers_and_never_executes_rejected_code(self):
        self.trace = ["R", "H", "R"]
        self.retire_when_full = True
        self.reject_review_at = 3
        result = self.run_loop(rounds=3)
        state = result["result"]["population"]
        prior = json.loads((self.loop_root / "population-02.json").read_text())
        self.assertEqual(state["explorers"], prior["explorers"])
        self.assertEqual(state["versions"], prior["versions"])
        rejected = self.calls["review"][2]["id"]
        self.assertNotIn(rejected, {version for version, company in self.calls["forecast"]})
        implementation = journal._read_pair(self.journal_root / "round-0003-implement.done.json")["output"]
        self.assertIn(rejected, json.dumps(implementation))
        self.assertEqual(len(self.calls["forecast"]), 8)

    def test_stable_retirement_request_refused_before_author_or_forecast(self):
        self.retire_stable = True
        with self.assertRaises(journal.LoopHalted):
            self.run_loop(rounds=2)
        self.assertEqual(len(self.calls["controller"]), 1)
        self.assertEqual(len(self.calls["author"]), 0)
        self.assertEqual(len(self.calls["forecast"]), 0)


if __name__ == "__main__":
    unittest.main()
