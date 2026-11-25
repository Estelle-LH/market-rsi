"""Synthetic acceptance for one finite ten-round offline earnings segment.

Only financial-data admission and raw HTTPS are explicit fixtures.  Assembly,
Controller, Author, SourceReview, Forecast, Native capacity, scorer, task,
budget owner, driver, and completed replay remain the actual source-bound
implementations.  These tests grant no live authority and make no model,
prediction, or research-improvement claim.
"""
from copy import deepcopy
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "research" / "market_rsi"))

import earnings_capacity_assembly as assembly
import earnings_capacity_runtime as runtime
import earnings_completed_replay as completed_replay
import earnings_round_plan as round_plan
import earnings_feedback_loop as flow
import earnings_entry as entry
from earnings_research_state import ResearchState
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
from supervisor_harness.continuous_discovery_batch import ContinuousDiscoveryBatch
from test_earnings_capacity_assembly import AssemblyFixture


ROUNDS = 10
CONTINUE_TRACE = ("continue",) * ROUNDS
MIXED_TRACE = (
    "continue", "accept_H", "continue", "reject_R", "continue",
    "continue", "continue", "continue", "continue", "continue",
)
H_EFFECT = (
    "earnings-shadow-v1|tool_interface|tool_return_characters|lower|1|"
    "score_nonregression|matched_trial_only"
)


class TenRoundAssemblyFixture(AssemblyFixture):
    """Prospective v2/v3 fixture without changing the inherited fixture."""

    def __init__(self, owner, *, rounds=ROUNDS):
        if rounds != ROUNDS:
            raise ValueError("This fixture is the exact ten-round contract")
        super().__init__(owner, rounds=rounds)

    def seal(self):
        """Bind episode, then plan, then runtime; no binding cycle is possible."""
        self.envelope["schema"] = "earnings_capacity_episode_v2"
        self.episode_binding = self.save("episode-v2", self.envelope)

        self.plan = {
            "schema": "earnings_matched_plan_v1",
            "episode": self.episode_binding,
            "rounds": self.plan_rows,
        }
        self.plan_binding = self.save("matched-plan-v2", self.plan)

        self.runtime["schema"] = "earnings_capacity_runtime_v3"
        self.runtime["episode"] = self.episode_binding
        self.runtime["matched_plan"] = self.plan_binding
        self.runtime["sources"]["round_plan"] = engine.pin(round_plan.__file__)
        self.runtime_binding = self.save("runtime-v3", self.runtime)

        self.native["micro_config"]["fixed_context"] = {
            "model_sha256": self.native["baseline"]["M"],
            "evaluation_sha256": self.native["baseline"]["K"],
            "data_scope_sha256": digest({
                "study": self.envelope["study"],
                "cik": self.envelope["cik"],
                "kernel": self.envelope["evaluation_kernel"],
            }),
            "authority_sha256": digest({
                key: self.envelope[key] for key in ("mode", "grant", "window")
            }),
            "resource_policy_sha256": digest(self.runtime_binding),
        }
        self.assembly = {
            "schema": "earnings_capacity_assembly_v1",
            "mode": "offline_replay",
            "episode": self.episode_binding,
            "runtime": self.runtime_binding,
            "native": self.save("native-v2", self.native),
            "matched_plan": self.plan_binding,
            "effect_registration": self.save("effect-registration-v2", self.registration),
            "source_review": self.save("source-review-v2", self.review),
            "constructors": assembly.constructor_sources(),
            "transport": engine.source_of(self.client_factory),
            "claims": {"model_authorship": False, "predictive_gain": False},
        }
        self.assembly_binding = self.save("assembly-v2", self.assembly)

    @staticmethod
    def response(fixture, value):
        return fixture.raw.response([
            {
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": json.dumps(value)}],
            }
        ])

    @classmethod
    def continue_response(cls, fixture, request):
        prompt = json.loads(request["input"][0]["content"])
        return cls.response(fixture, {
            "schema": "earnings_capacity_decision_v1",
            "axis": "continue",
            "component": "none",
            "parent_pair_sha256": prompt["parent_pair_sha256"],
            "feedback_sha256": prompt["feedback_sha256"],
            "hypothesis": "Retain the selected pair when no bounded change is justified.",
            "expected_effect": "No R/H mutation; execute the exact selected pair.",
        })

    @classmethod
    def mutation_response(cls, fixture, request, *, axis, expected_effect):
        prompt = json.loads(request["input"][0]["content"])
        return cls.response(fixture, {
            "schema": "earnings_capacity_decision_v1",
            "axis": axis,
            "component": "research_policy" if axis == "R" else "tool_interface",
            "parent_pair_sha256": prompt["parent_pair_sha256"],
            "feedback_sha256": prompt["feedback_sha256"],
            "hypothesis": "Exercise one bounded literal profile change on matched inputs.",
            "expected_effect": expected_effect,
        })

    @classmethod
    def author_response(cls, fixture, request):
        prompt = json.loads(request["input"][0]["content"])
        choice, after = prompt["decision"], dict(prompt["before_profile"])
        if choice["axis"] == "R":
            field = "research_instructions"
            after[field] = "Reconcile exact units and filing dates before forecasting."
        else:
            field = "read_chunk_limit"
            after[field] = 1000
        return cls.response(fixture, {
            "decision_sha256": prompt["decision_sha256"],
            "source_text": "PROFILE = " + repr(after) + "\n",
            "test_text": "CASES = " + repr([
                {"field": field, "expected": after[field]}
            ]) + "\n",
        })

    def scripted_replies(self, trace):
        if tuple(trace) not in {CONTINUE_TRACE, MIXED_TRACE}:
            raise ValueError("Exact declared ten-round trace required")
        replies = []
        for round_index, action in enumerate(trace, 1):
            if action == "continue":
                replies.append(lambda request, f=self: self.continue_response(f, request))
                if round_index == 1:
                    replies.append(self.raw.research())
                replies.append(self.raw.final())
            elif action == "accept_H":
                replies.append(lambda request, f=self: self.mutation_response(
                    f, request, axis="H", expected_effect=H_EFFECT
                ))
                replies.append(lambda request, f=self: self.author_response(f, request))
                replies.extend([
                    self.raw.research(), self.raw.final(),
                    self.raw.research(), self.raw.final(),
                    self.raw.final(),
                ])
            elif action == "reject_R":
                replies.append(lambda request, f=self: self.mutation_response(
                    f, request, axis="R",
                    expected_effect="Unknown fixture-only effect semantics",
                ))
                replies.append(lambda request, f=self: self.author_response(f, request))
                replies.append(self.raw.final())
        return replies


class TenRoundSegmentTests(unittest.TestCase):
    def fixture(self):
        return TenRoundAssemblyFixture(self)

    def run_trace(self, trace):
        fixture = self.fixture()
        replies = fixture.scripted_replies(trace)
        with fixture.exchange(replies):
            outcome = flow.run(
                fixture.episode_binding,
                assembly_binding=fixture.assembly_binding,
                client_factory=fixture.client_factory,
                task=fixture.task,
            )
        self.assertEqual(len(fixture.raw.calls), 2 * len(replies))
        return fixture, outcome

    def assert_all_feedback_edges(self, fixture):
        loop = fixture.root / "loop"
        for index in range(2, ROUNDS + 1):
            with self.subTest(edge=f"{index - 1}->{index}"):
                previous = engine.driver._read_pair(
                    loop / f"round-{index - 1:04d}-reconcile.done.json"
                )["output"]
                packet = engine.read(engine.pin(fixture.root / f"packet-{index:02d}.json"))
                input_stage = engine.driver._read_pair(
                    loop / f"round-{index:04d}-input.done.json"
                )["output"]
                execute = engine.driver._read_pair(
                    loop / f"round-{index:04d}-execute.done.json"
                )["output"]
                self.assertEqual(packet["feedback"], previous["feedback"])
                self.assertEqual(packet["parent_feedback_sha256"], digest(previous))
                self.assertEqual(packet["parent_pair_sha256"], previous["pair_sha256"])
                self.assertEqual(input_stage["parent_state"], previous["state"])
                self.assertEqual(execute["parent_state"], previous["state"])
                self.assertEqual(execute["consumed"]["state_sha256"], previous["state"]["sha256"])
                self.assertEqual(execute["consumed"]["pair_sha256"], execute["pair_sha256"])

    def test_legacy_v1_readiness_and_runtime_ceilings_remain_unchanged(self):
        for rounds in (1, 2):
            with self.subTest(rounds=rounds):
                fixture = AssemblyFixture(self, rounds=rounds)
                self.assertEqual(fixture.readiness(), fixture.paths)
                self.assertEqual(runtime.preflight_runtime(fixture.runtime_binding), fixture.runtime)

        fixture = AssemblyFixture(self, rounds=3)
        with self.assertRaises(ValueError):
            fixture.readiness()
        with self.assertRaises(ValueError):
            runtime.preflight_runtime(fixture.runtime_binding)

    def test_legacy_pending_component_retains_minimal_bound_envelope_protocol(self):
        from test_earnings_pending_evolution import _PendingFixture
        fixture = _PendingFixture(self)
        self.assertNotIn('schema', fixture.envelope)
        self.assertNotIn('grant', fixture.envelope)
        self.assertNotIn('window', fixture.envelope)
        self.assertEqual(fixture.pending.plan, fixture.plan)
        self.assertEqual(fixture.raw.calls, [])

    def test_ten_continue_rounds_bind_all_nine_edges_and_cold_replay(self):
        fixture, outcome = self.run_trace(CONTINUE_TRACE)
        self.assertEqual((outcome["status"], outcome["completed_rounds"]), ("completed", ROUNDS))
        self.assert_all_feedback_edges(fixture)

        snapshot = engine.read(engine.pin(fixture.paths["batch_root"] / "batch.json"))
        self.assertEqual(snapshot["micro_evolution"]["history"], [])
        self.assertEqual(snapshot["micro_evolution"]["active_pair"],
                         engine.activation.pair(fixture.baseline))
        self.assertEqual(len(snapshot["capacity_work"]), ROUNDS)

        retained = fixture.retained_tree()
        calls = len(fixture.raw.calls)
        factories = fixture.factory_calls
        closure = engine.pin(fixture.root / "completed-replay.json")
        with patch.object(engine, "run", side_effect=AssertionError("No engine run")), \
             patch.object(engine, "save", side_effect=AssertionError("No artifact write")), \
             patch.object(engine.driver.c, "save", side_effect=AssertionError("No driver write")), \
             patch.object(fixture.task, "preflight", side_effect=AssertionError("No task admission")), \
             patch.object(ContinuousDiscoveryBatch, "__init__",
                          side_effect=AssertionError("No Native constructor")), \
             patch.object(assembly, "open_capacity_runtime",
                          side_effect=AssertionError("No runtime owner")), \
             patch.object(sqlite3, "connect", side_effect=AssertionError("No ledger open")):
            replayed = completed_replay.replay_completed(fixture.episode_binding, closure)
        self.assertEqual(replayed, outcome)
        self.assertEqual(fixture.retained_tree(), retained)
        self.assertEqual(len(fixture.raw.calls), calls)
        self.assertEqual(fixture.factory_calls, factories)

    def test_mixed_accept_reject_continue_trace_binds_all_nine_edges(self):
        fixture, outcome = self.run_trace(MIXED_TRACE)
        self.assertEqual((outcome["status"], outcome["completed_rounds"]), ("completed", ROUNDS))
        self.assert_all_feedback_edges(fixture)

        decisions = [
            engine.read(engine.pin(fixture.root / f"decision-{index:02d}.json"))["axis"]
            for index in range(1, ROUNDS + 1)
        ]
        self.assertEqual(decisions, [
            "continue", "H", "continue", "R", "continue",
            "continue", "continue", "continue", "continue", "continue",
        ])
        snapshot = engine.read(engine.pin(fixture.paths["batch_root"] / "batch.json"))
        history = snapshot["micro_evolution"]["history"]
        self.assertEqual([row["review"]["decision"] for row in history], ["accept", "reject"])
        self.assertEqual([row["proposal"]["axis"] for row in history], ["harness", "researcher"])
        self.assertEqual(len(history), 2)
        self.assertEqual(snapshot["micro_evolution"]["active_pair"]["researcher_sha256"],
                         engine.activation.pair(fixture.baseline)["researcher_sha256"])
        self.assertNotEqual(snapshot["micro_evolution"]["active_pair"]["harness_sha256"],
                            engine.activation.pair(fixture.baseline)["harness_sha256"])
        self.assertEqual(len(snapshot["capacity_work"]), 12)
        self.assertTrue(all(row["status"] == "completed" for row in snapshot["capacity_work"]))

        retained, calls = fixture.retained_tree(), len(fixture.raw.calls)
        self.assertEqual(completed_replay.replay_completed(fixture.episode_binding,
            engine.pin(fixture.root / 'completed-replay.json')), outcome)
        self.assertEqual(fixture.retained_tree(), retained)
        self.assertEqual(len(fixture.raw.calls), calls)

    def test_same_n_equivalent_plan_at_another_binding_is_not_the_runtime_plan(self):
        fixture = self.fixture()
        equivalent = fixture.save('equivalent-plan', fixture.plan)
        changed = fixture.save('wrong-plan-assembly', dict(fixture.assembly, matched_plan=equivalent))
        before = fixture.retained_tree()
        with self.assertRaisesRegex(ValueError, 'actual assembly episode and matched plan'):
            assembly.validate_assembly(fixture.episode_binding, changed,
                client_factory=fixture.client_factory, task=fixture.task)
        self.assertEqual(fixture.retained_tree(), before)
        self.assertEqual(fixture.factory_calls, 0)
        self.assertEqual(fixture.task.preflight_calls, [])

    def test_new_episode_cannot_use_valid_legacy_runtime_even_at_one_round(self):
        fixture = AssemblyFixture(self, rounds=1)
        fixture.envelope['schema'] = 'earnings_capacity_episode_v2'
        fixture.seal()
        self.assertEqual(runtime.preflight_runtime(fixture.runtime_binding)['schema'],
                         'earnings_capacity_runtime_v2')
        before = fixture.retained_tree()
        with self.assertRaisesRegex(ValueError, 'runtime/factory bindings differ'):
            assembly.validate_assembly(fixture.episode_binding, fixture.assembly_binding,
                client_factory=fixture.client_factory, task=fixture.task)
        self.assertEqual(fixture.retained_tree(), before)
        self.assertEqual(fixture.task.preflight_calls, [])

    def test_v2_programmatic_cli_preflight_routes_without_opening_resources(self):
        fixture = self.fixture()
        # Only original financial-data admission is substituted, explicitly.
        admission = (fixture.raw.company, ResearchState(fixture.raw.company, fixture.id))
        output = StringIO()
        before = fixture.retained_tree()
        with fixture.scope(), redirect_stdout(output), \
             patch.object(entry, 'preflight_capacity_episode', return_value=admission) as preflight, \
             patch.object(assembly, 'open_capacity_runtime', side_effect=AssertionError('No owner')) as owner:
            flow.main(['--envelope', fixture.episode_binding['path'], '--assembly',
                       fixture.assembly_binding['path'], '--preflight-only'],
                      client_factory=fixture.client_factory)
        self.assertEqual(json.loads(output.getvalue())['status'], 'OFFLINE_CAPACITY_ASSEMBLY_PREFLIGHT_PASS')
        preflight.assert_called_once_with(fixture.envelope)
        owner.assert_not_called()
        self.assertEqual(fixture.factory_calls, 0)
        self.assertEqual(fixture.retained_tree(), before)

    def test_slot_or_binding_mismatch_refuses_before_native_or_runtime_owner(self):
        changes = []
        fixture = self.fixture()
        short = deepcopy(fixture.runtime)
        short["slots"]["controller"] = short["slots"]["controller"][:-1]
        changes.append((fixture, short))

        fixture = self.fixture()
        duplicate = deepcopy(fixture.runtime)
        duplicate["slots"]["forecast"][-1] = duplicate["slots"]["forecast"][0]
        changes.append((fixture, duplicate))

        fixture = self.fixture()
        wrong_episode = deepcopy(fixture.runtime)
        wrong_episode["episode"] = dict(wrong_episode["episode"], sha256="f" * 64)
        changes.append((fixture, wrong_episode))

        fixture = self.fixture()
        wrong_plan = deepcopy(fixture.runtime)
        wrong_plan["matched_plan"] = dict(wrong_plan["matched_plan"], sha256="e" * 64)
        changes.append((fixture, wrong_plan))

        for fixture, changed_runtime in changes:
            with self.subTest(change=changed_runtime):
                runtime_binding = fixture.save("changed-runtime", changed_runtime)
                changed_assembly = dict(fixture.assembly, runtime=runtime_binding)
                assembly_binding = fixture.save("changed-assembly", changed_assembly)
                before = fixture.retained_tree()
                with patch.object(assembly, "_native",
                                  side_effect=AssertionError("No Native constructor")) as native, \
                     patch.object(assembly, "open_capacity_runtime",
                                  side_effect=AssertionError("No runtime owner")) as owner:
                    with self.assertRaises((ValueError, KeyError, TypeError, OSError)):
                        assembly.validate_assembly(
                            fixture.episode_binding,
                            assembly_binding,
                            client_factory=fixture.client_factory,
                            task=fixture.task,
                        )
                native.assert_not_called()
                owner.assert_not_called()
                self.assertEqual(fixture.retained_tree(), before)
                self.assertEqual(fixture.factory_calls, 0)
                self.assertEqual(fixture.task.preflight_calls, [])


if __name__ == "__main__":
    unittest.main()
