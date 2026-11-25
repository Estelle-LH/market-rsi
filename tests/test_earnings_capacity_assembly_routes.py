"""Additional actual CLI routes: continued work after no mutation/rejection.

Compose existing AssemblyFixture/ActualRoleReplies/CLI helpers without TestCase
inheritance. Only invented admission/clocks/raw HTTPS replies are substituted;
roles, dispatcher, scorer, review, Native selection and closure remain actual.
"""
from pathlib import Path
import json
import unittest
from unittest.mock import patch

import earnings_controller as controller
import earnings_entry as entry
import earnings_capacity_runtime as runtime
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_capacity_assembly_cli as cli


class CapacityAssemblyRoutesTests(unittest.TestCase):
    def fixture(self, axes):
        helper = cli.CapacityAssemblyCLITests()
        self.addCleanup(helper.doCleanups)
        fixture = helper.fixture()
        return helper, fixture, cli.ActualRoleReplies(fixture, axes=axes)

    def run_actual(self, helper, fixture, sequence):
        created, closed = [], []
        actual_init, actual_close = runtime.NightBudget.__init__, runtime.NightBudget.close
        def initialize(budget, *args, **kwargs):
            created.append(budget)
            return actual_init(budget, *args, **kwargs)
        def close(budget):
            closed.append(budget)
            return actual_close(budget)
        with helper.actual_run(fixture, sequence), \
                patch.object(runtime.NightBudget, "__init__", new=initialize), \
                patch.object(runtime.NightBudget, "close", new=close), \
                patch.object(entry, "NightBudget", side_effect=AssertionError("No forecast owner reopen")), \
                patch.object(controller, "NightBudget", side_effect=AssertionError("No role owner reopen")):
            result = helper.main_result(helper.arguments(fixture), client_factory=fixture.client_factory)
        self.assertEqual(len(created), 1)
        self.assertEqual(closed, created)
        self.assertEqual((result["status"], result["completed_rounds"]), ("completed", 2))
        self.assertEqual(result["result"]["claims"], {"mode": "offline_replay", "learning": False, "live_RH_authorship": False})
        self.assertTrue(all(row[4] == "settled" for row in fixture.ledger_rows()))
        self.assertEqual(helper.terminal(fixture)["status"], "COMPLETED_COMPONENT_CONTEXT")
        self.assertIs(helper.terminal(fixture)["retry_allowed"], False)
        return result

    def connected_second(self, helper, fixture, replies):
        first = helper.done(fixture, 1, "reconcile")
        second = replies.controller_inputs[1]
        self.assertEqual(second["feedback"], first["feedback"])
        self.assertEqual(second["feedback_sha256"], digest(first))
        self.assertEqual(second["parent_pair_sha256"], first["pair_sha256"])
        count = engine.read(engine.pin(Path(fixture.slots[1]["controller"]) / "01-request.json"))
        self.assertEqual(json.loads(count["payload"]["input"][0]["content"]), second)
        effective = engine.read(engine.pin(Path(fixture.plan_rows[1]["downstream"]) / "effective-capacity.json"))
        self.assertEqual(effective["initial_state"]["sha256"], first["state"]["sha256"])
        self.assertEqual(Path(effective["initial_state"]["path"]).read_bytes(), Path(first["state"]["path"]).read_bytes())
        self.assertNotIn("shadow", effective)
        return first, effective

    def test_two_actual_free_continue_rounds_skip_Author_shadow_and_keep_feedback_state_cold_closure(self):
        helper, fixture, replies = self.fixture(("continue", "continue"))
        result = self.run_actual(helper, fixture, replies.sequence())
        snapshot = helper.snapshot(fixture)
        micro = snapshot["micro_evolution"]
        self.assertEqual(micro["active_pair"], micro["anchor_pair"])
        self.assertEqual(micro["history"], [])
        self.assertIsNone(micro["pending"])
        self.assertEqual(len(snapshot["capacity_work"]), 2)
        self.assertTrue(all(row["status"] == "completed" for row in snapshot["capacity_work"]))
        self.assertEqual(replies.author_inputs, [])
        self.assertEqual(fixture.factory_calls, 4)  # 2 actual Controllers + 2 ordinary forecasts.
        self.assertEqual(len(fixture.raw.calls), 12)
        for index, row in enumerate(fixture.plan_rows):
            self.assertFalse(Path(row["parent"]).exists())
            self.assertFalse(Path(row["candidate"]).exists())
            self.assertFalse(Path(fixture.slots[index]["author"]).exists())
            self.assertFalse(Path(fixture.slots[index]["review"]).exists())
        first, effective = self.connected_second(helper, fixture, replies)
        self.assertEqual(first["feedback"]["research_diagnostics"]["review"]["reason"], "NOT_MEASURED")
        self.assertEqual(first["feedback"]["research_diagnostics"]["review"]["verdict"], "continue")
        self.assertEqual(effective["context"]["tool_bounds"]["read_chunk_limit"], 20000)
        self.assertEqual(result["result"]["feedback"]["observation"]["prediction"]["score_out_of_5"], 5)
        helper.assert_cold_without_callbacks_or_writes(fixture, result)

    def test_actual_R_no_effect_rejection_then_H_acceptance_uses_reject_diagnostics_and_new_worker(self):
        helper, fixture, replies = self.fixture(("R", "H"))
        result = self.run_actual(helper, fixture, replies.sequence())
        snapshot = helper.snapshot(fixture)
        micro = snapshot["micro_evolution"]
        self.assertEqual([row["review"]["decision"] for row in micro["history"]], ["reject", "accept"])
        self.assertEqual([row["review"]["reason"] for row in micro["history"]], ["NO_MATCHED_BENEFIT", "MATCHED_OPERATIONAL_BENEFIT"])
        self.assertEqual(len(snapshot["capacity_work"]), 6)
        self.assertTrue(all(row["status"] == "completed" for row in snapshot["capacity_work"]))
        self.assertEqual(micro["active_pair"], micro["history"][1]["proposal"]["pair"])
        self.assertIsNone(micro["pending"])
        first, effective = self.connected_second(helper, fixture, replies)
        review = first["feedback"]["research_diagnostics"]["review"]
        self.assertEqual((review["verdict"], review["reason"], review["metric"]), ("reject", "NO_MATCHED_BENEFIT", "input_tokens"))
        self.assertEqual((review["observed_delta"], review["score_delta"], review["benefit_observed"]), (0, 0, False))
        self.assertEqual(effective["context"]["tool_bounds"]["read_chunk_limit"], 1000)
        self.assertTrue(all(row["selected_pair_sha256"] == digest(micro["active_pair"]) and not row["shadow"]
                            for row in effective["context"]["receipts"]))
        first_worker = engine.read(engine.pin(Path(fixture.plan_rows[0]["downstream"]) / "effective-capacity.json"))
        self.assertEqual(first_worker["context"]["tool_bounds"]["read_chunk_limit"], 20000)
        self.assertEqual(len(replies.controller_inputs), 2)
        self.assertEqual(len(replies.author_inputs), 2)
        self.assertEqual(fixture.factory_calls, 10)
        self.assertEqual(len(fixture.raw.calls), 32)
        helper.assert_cold_without_callbacks_or_writes(fixture, result)

    def test_actual_valid_literal_unknown_effect_rejects_without_shadow_then_continue_and_cold_closure(self):
        helper, fixture, replies = self.fixture(("R", "continue"))
        def choose_wire(payload):
            response = replies.choose(payload)
            if len(replies.decisions) == 1:
                # Only the invented provider business object changes. The actual
                # Controller parser/Author/SourceReview/Pending path is not mocked.
                decision = dict(replies.decisions[-1], expected_effect="Become better at financial research overall")
                replies.decisions[-1] = decision
                return replies.message(decision)
            return response
        sequence = [choose_wire, replies.author, fixture.raw.research(), fixture.raw.final(),
                    choose_wire, fixture.raw.research(), fixture.raw.final()]
        result = self.run_actual(helper, fixture, sequence)
        snapshot = helper.snapshot(fixture)
        micro = snapshot["micro_evolution"]
        self.assertEqual(len(micro["history"]), 1)
        self.assertEqual((micro["history"][0]["review"]["decision"], micro["history"][0]["review"]["reason"]),
                         ("reject", "UNKNOWN_EFFECT_SEMANTICS"))
        self.assertIs(micro["history"][0]["review"]["benefit_observed"], False)
        self.assertIsNone(micro["history"][0]["review"]["benefit_evidence_sha256"])
        self.assertEqual(micro["active_pair"], micro["anchor_pair"])
        self.assertIsNone(micro["pending"])
        self.assertEqual(len(snapshot["capacity_work"]), 2)
        self.assertTrue(all(row["status"] == "completed" for row in snapshot["capacity_work"]))
        for row in fixture.plan_rows:
            self.assertFalse(Path(row["parent"]).exists())
            self.assertFalse(Path(row["candidate"]).exists())
        self.assertFalse((fixture.root / "shadow").exists())
        self.assertFalse((fixture.root / "effects/round-01/benefit.json").exists())
        self.assertEqual(len(replies.author_inputs), 1)
        declared = fixture.review["slots"][fixture.slots[0]["review"]]["R"]
        self.assertEqual((fixture.paths["source_root"] / declared).read_bytes(), replies.authored[0]["source_text"].encode())
        self.assertEqual(micro["history"][0]["proposal"]["behavior_change"], replies.decisions[0]["expected_effect"])
        self.assertFalse(Path(fixture.slots[1]["author"]).exists())
        self.assertFalse(Path(fixture.slots[1]["review"]).exists())
        first, _ = self.connected_second(helper, fixture, replies)
        review = first["feedback"]["research_diagnostics"]["review"]
        self.assertEqual((review["verdict"], review["reason"], review["benefit_observed"]),
                         ("reject", "UNKNOWN_EFFECT_SEMANTICS", False))
        for field in ("metric", "direction", "min_delta", "observed_delta", "score_delta"):
            self.assertIsNone(review[field])
        self.assertEqual(fixture.factory_calls, 5)
        self.assertEqual(len(fixture.raw.calls), 14)
        helper.assert_cold_without_callbacks_or_writes(fixture, result)


if __name__ == "__main__":
    unittest.main()
