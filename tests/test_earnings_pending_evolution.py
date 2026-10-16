"""Actual measured pending->Root review->ordinary worker->next feedback.

Controller/Author/source-review outputs and external admission are explicit
invented fixtures. Forecast HTTP is mocked; scorer, probes, review, native
adoption, worker selection and common driver run unchanged. No live authorship.
"""
from contextlib import ExitStack
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import earnings_capacity_adapter as adapter
import earnings_clock as clock
import earnings_entry as entry
from earnings_capacity_checks import MechanicalProbes
from earnings_capacity_task import EarningsTask
from earnings_effect_review import review, SCOPES
from earnings_pending_evolution import PendingEvolution
from earnings_research_state import ResearchState
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
from supervisor_harness.continuous_discovery_batch import ContinuousDiscoveryBatch
import test_earnings_capacity_forecast as raw_fixture


class _PendingFixture:
    def __init__(self, owner, *, axes=("H", "R"), quota=6):
        initialize = ContinuousDiscoveryBatch.initialize

        def prospective(batch, *args, **kwargs):
            # Set the first immutable initialization prospectively; never
            # rewrite existing journals, consumed quota or original API cap.
            kwargs["max_attempts"] = quota
            return initialize(batch, *args, **kwargs)

        with patch.object(ContinuousDiscoveryBatch, "initialize", new=prospective):
            self.raw = raw_fixture._ForecastFixture(owner)
        self.axes, self.packets, self.choices, self.authored, self.review_specs = list(axes), [], [], [], []
        self.raw.task_id = "fixture-task"
        self.state_api = ResearchState(self.raw.company, self.raw.task_id)
        initial = self.state_api.save(self.raw.root / "initial-memory", self.state_api.empty())
        self.envelope = {"id": self.raw.task_id, "root": str(self.raw.role_root), "mode": "offline_replay",
            "cik": self.raw.company["cik"], "max_rounds": len(axes), "source_commit": raw_fixture.SOURCE_COMMIT,
            "study": self.raw.study_binding, "evaluation_kernel": self.raw.kernel, "initial_state": initial,
            "slots": [{**{role: str(self.raw.role_root / "roles" / f"{role}-{n+1:02d}")
                         for role in ("controller", "author", "review")},
                       "forecast": self.raw.slots[n*3+2]} for n in range(len(axes))]}
        self.bound = raw_fixture._save(self.raw.root / "episode.json", self.envelope)
        self.plan = {"schema": "earnings_matched_plan_v1", "episode": self.bound,
            "rounds": [{"parent": self.raw.slots[n*3], "candidate": self.raw.slots[n*3+1],
                        "downstream": self.raw.slots[n*3+2]} for n in range(len(axes))]}
        self.plan_binding = raw_fixture._save(self.raw.root / "matched-plan.json", self.plan)
        self.task = EarningsTask()
        self.task.company, self.task.state_api, self.task.kernel = self.raw.company, self.state_api, self.raw.kernel
        self.forecaster = self.raw.service()
        probes = MechanicalProbes(self.task)
        registration = {"schema": "earnings_effect_review_registration_v1", "reviewer_id": "independent-auditor",
            "proposer_id": "fixture-author", "review_source": engine.source_of(review),
            "probe_source": engine.source_of(probes.run), "scopes": SCOPES}
        self.registration_binding = raw_fixture._save(self.raw.root / "effect-registration.json", registration)
        self.pending = PendingEvolution(self.bound, self.raw.native.adapter, self.task, self.forecaster.forecast,
            plan_binding=self.plan_binding, registration_binding=self.registration_binding)
        self.effects = {"H": "earnings-shadow-v1|tool_interface|tool_return_characters|lower|1|score_nonregression|matched_trial_only",
                       "R": "earnings-shadow-v1|research_policy|input_tokens|lower|1|score_nonregression|matched_trial_only"}
        self.author_drift = False

    def record(self, slot, value):
        Path(slot).mkdir(parents=True, exist_ok=False)
        return raw_fixture._save(Path(slot) / "response.json", value)

    def controller(self, packet, slot):
        self.packets.append(deepcopy(packet))
        axis = self.axes[len(self.packets)-1]
        chosen = {"schema": "earnings_capacity_decision_v1", "axis": axis,
            "component": "tool_interface" if axis == "H" else "research_policy",
            "parent_pair_sha256": packet["parent_pair_sha256"], "feedback_sha256": packet["feedback_sha256"],
            "hypothesis": "Invented fixture tests a narrow policy effect", "expected_effect": self.effects[axis]}
        self.choices.append(deepcopy(chosen))
        return self.record(slot, {"status": "completed", "output": [{"type": "message",
            "content": [{"type": "output_text", "text": json.dumps(chosen)}]}]})

    def author(self, chosen, before, slot):
        self.authored.append(deepcopy(chosen))
        name = "harness_v2.py" if chosen["axis"] == "H" else "researcher_v2.py"
        source = self.raw.native.files[name]
        value = adapter.profile(source.encode(), chosen["axis"])
        field = "read_chunk_limit" if chosen["axis"] == "H" else "research_instructions"
        body = {"decision_sha256": digest(chosen), "source_text": source,
                "test_text": "CASES = " + repr([{"field": field, "expected": value[field]}])}
        bound = self.record(slot, {"status": "completed", "output": [{"type": "message",
            "content": [{"type": "output_text", "text": json.dumps(body)}]}]})
        if self.author_drift:
            path = self.raw.root / name
            (self.raw.root / ("before-drift-" + name)).write_bytes(path.read_bytes())
            path.write_text("PROFILE = {}\n")
        return bound

    def source_review(self, chosen, original, descriptor, slot):
        before = descriptor["parent_identity"]
        authored = adapter.author_payload(original)
        args = deepcopy(self.raw.native.args)
        args["harness"], args["researcher"] = before["components"]["H"], before["components"]["R"]
        kind = "harness" if chosen["axis"] == "H" else "researcher"
        name = kind + "_v2.py"
        args[kind] = {"sources": {name: entry.digest(authored["source_text"].encode())},
                      "configuration_sha256": self.raw.native.args[kind]["configuration_sha256"]}
        after = adapter.identity.manifest(**args)
        entries = {axis: next(iter(after["components"][axis]["sources"])) for axis in ("R", "H")}
        proposal = {"candidate_id": f"fixture-{chosen['axis']}-child", "proposer_id": "fixture-author",
            "axis": kind, "component": chosen["component"], "behavior_change": chosen["expected_effect"],
            "problem_evidence_sha256": chosen["feedback_sha256"], "parent_pair_sha256": chosen["parent_pair_sha256"],
            "pair": adapter.activation.pair(after), "fixed_context": descriptor["micro_evolution"]["fixed_context"],
            "write_paths": list(before["components"][chosen["axis"]]["sources"]) + [name],
            "patch_sha256": adapter.activation.patch_digest(before, after)}
        scope = raw_fixture._save(self.raw.root / f"scope-{len(self.review_specs)+1}.json",
            {"passed": True, "reviewer_id": "independent-auditor", "proposer_id": "fixture-author",
             "identity_sha256": digest(after), "entrypoints": entries})
        body = {"schema": "capacity_review_spec_v1", "after": after, "proposal": proposal,
                "entrypoints": entries, "static_review": scope, "review_receipt": None}
        self.review_specs.append(deepcopy(body))
        return dict(body, original=self.record(slot, body), artifacts=[scope])

    def run(self, *, pending_handler=None, replies=None):
        replies = ([item for _ in range(len(self.axes)*3) for item in (self.raw.research(), self.raw.final())]
                   if replies is None else replies)

        def deadline_init(transport_object, client, **options):
            options.update(clock=lambda: self.raw.wall, monotonic=lambda: self.raw.monotonic)
            raw_fixture.DEADLINE_INIT(transport_object, client, **options)

        with ExitStack() as stack:
            # Explicit synthetic admission fixture, not live/source/data access.
            stack.enter_context(patch.object(entry, "preflight_capacity_episode", return_value=(self.raw.company, self.state_api)))
            stack.enter_context(patch("earnings_http.http.client.HTTPSConnection", side_effect=self.raw.fake_connection(replies)))
            stack.enter_context(patch.object(entry, "credential", side_effect=AssertionError("No credentials")))
            stack.enter_context(patch.object(entry, "NightBudget", side_effect=AssertionError("No ledger reopen")))
            stack.enter_context(patch.object(clock, "boot_id", return_value=raw_fixture.BOOT))
            stack.enter_context(patch.object(entry.time, "time", side_effect=lambda: self.raw.wall))
            stack.enter_context(patch.object(entry.time, "monotonic", side_effect=lambda: self.raw.monotonic))
            stack.enter_context(patch.object(entry.DeadlineHTTP, "__init__", new=deadline_init))
            return engine.run(self.bound, self.raw.native.adapter, self.task,
                services={"controller": self.controller, "author": self.author,
                          "review": self.source_review, "execute": self.forecaster.forecast},
                pending_handler=self.pending.handle if pending_handler is None else pending_handler)


class PendingEvolutionIntegrationTests(unittest.TestCase):
    def fixture(self, **options): return _PendingFixture(self, **options)

    def effective(self, fixture, index):
        return json.loads((Path(fixture.raw.slots[index]) / "effective-capacity.json").read_bytes())

    def test_two_round_measured_H_adoption_then_R_rejection_reaches_real_next_feedback(self):
        fixture = self.fixture()
        anchor = fixture.raw.native.batch.snapshot()["micro_evolution"]["active_pair"]
        result = fixture.run()
        self.assertEqual(result["status"], "completed")
        native = fixture.raw.native.batch.snapshot()
        self.assertEqual(native["max_attempts"], 6)
        self.assertEqual(len(native["capacity_work"]), 6)
        self.assertTrue(all(row["status"] == "completed" for row in native["capacity_work"]))
        self.assertEqual(native["active_attempt_ids"], [])
        micro = native["micro_evolution"]
        self.assertIsNone(micro["pending"])
        self.assertEqual([row["review"]["decision"] for row in micro["history"]], ["accept", "reject"])
        for index, row in enumerate(micro["history"]):
            self.assertEqual(row["proposal"]["parent_pair_sha256"], fixture.choices[index]["parent_pair_sha256"])
            self.assertEqual(row["proposal"]["problem_evidence_sha256"], fixture.choices[index]["feedback_sha256"])
            self.assertEqual(row["proposal"]["behavior_change"], fixture.choices[index]["expected_effect"])
            self.assertEqual(row["proposal"]["component"], fixture.choices[index]["component"])
        self.assertEqual(micro["active_pair"], micro["history"][0]["proposal"]["pair"])
        self.assertNotEqual(micro["active_pair"], anchor)
        self.assertTrue(all(spec["review_receipt"] is None for spec in fixture.review_specs))
        self.assertEqual(len(fixture.packets), 2)
        self.assertEqual(fixture.packets[1]["parent_pair_sha256"], digest(micro["active_pair"]))
        self.assertEqual(fixture.packets[1]["feedback"]["observation"]["prediction"]["score_out_of_5"], 5)
        first_review = json.loads((fixture.raw.role_root / "loop/round-0001-result_review.done.json").read_bytes())["output"]
        self.assertEqual(fixture.packets[1]["feedback"], first_review["feedback"])
        self.assertEqual(fixture.packets[1]["feedback_sha256"], digest(first_review))
        first_terminal = json.loads((Path(fixture.raw.slots[2]) / "research-state-output.json").read_bytes())
        self.assertEqual(self.effective(fixture, 3)["initial_state"]["sha256"], first_terminal["state"]["sha256"])
        self.assertEqual(self.effective(fixture, 5)["initial_state"]["sha256"], first_terminal["state"]["sha256"])
        for index in (2, 5):
            actual = self.effective(fixture, index)
            self.assertNotIn("shadow", actual)
            self.assertTrue(all(not row["shadow"] and row["selected_pair_sha256"] == digest(micro["active_pair"])
                                for row in actual["context"]["receipts"]))
            self.assertEqual(actual["context"]["tool_bounds"]["read_chunk_limit"], 1000)
        for index in (1, 4): self.assertIn("shadow", self.effective(fixture, index))
        self.assertEqual(len(fixture.raw.calls), 24)
        self.assertEqual(len(fixture.raw.rows()), 12)
        self.assertFalse(result["result"]["claims"]["learning"])

    def test_unchanged_R_is_rejected_and_ordinary_parent_still_moves_forward(self):
        fixture = self.fixture(axes=("R",))
        before = fixture.raw.native.batch.snapshot()["micro_evolution"]["active_pair"]
        result = fixture.run()
        self.assertEqual(result["status"], "completed")
        micro = fixture.raw.native.batch.snapshot()["micro_evolution"]
        self.assertEqual(micro["active_pair"], before)
        self.assertEqual(micro["history"][-1]["review"]["decision"], "reject")
        self.assertEqual(micro["history"][-1]["review"]["reason"], "NO_MATCHED_BENEFIT")
        self.assertNotIn("shadow", self.effective(fixture, 2))
        self.assertEqual(len(fixture.raw.calls), 12)

    def test_broad_unknown_effect_rejects_without_trial_but_runs_working_parent(self):
        fixture = self.fixture(axes=("H",))
        fixture.effects["H"] = "Become a better researcher overall"
        result = fixture.run()
        self.assertEqual(result["status"], "completed")
        native = fixture.raw.native.batch.snapshot()
        self.assertEqual(len(native["capacity_work"]), 1)
        self.assertEqual(native["micro_evolution"]["history"][-1]["review"]["reason"], "UNKNOWN_EFFECT_SEMANTICS")
        self.assertFalse(Path(fixture.raw.slots[0]).exists())
        self.assertFalse(Path(fixture.raw.slots[1]).exists())
        self.assertEqual(len(fixture.raw.calls), 4)
        self.assertEqual(self.effective(fixture, 2)["context"]["tool_bounds"]["read_chunk_limit"], 20000)

    def test_H_score_regression_rejects_measured_child_and_preserves_parent_downstream(self):
        fixture = self.fixture(axes=("H",))
        worse = fixture.raw.final({"predictions": [{"target_id": f"T{i:03d}", "predicted_value": 200} for i in range(1, 6)]})
        result = fixture.run(replies=[fixture.raw.research(), fixture.raw.final(), fixture.raw.research(), worse,
                                     fixture.raw.research(), fixture.raw.final()])
        self.assertEqual(result["status"], "completed")
        native = fixture.raw.native.batch.snapshot()
        self.assertEqual(native["micro_evolution"]["history"][-1]["review"]["decision"], "reject")
        comparison = engine.read(engine.pin(fixture.raw.role_root / "shadow/round-01/comparison.json"))
        self.assertLess(comparison["delta"]["tool_return_characters"], 0)
        self.assertEqual(comparison["score_delta"], -5)
        self.assertFalse(comparison["benefit_observed"])
        self.assertEqual(self.effective(fixture, 2)["context"]["tool_bounds"]["read_chunk_limit"], 20000)

    def test_malformed_effect_callback_stops_before_review_or_ordinary_worker(self):
        fixture = self.fixture(axes=("H",))

        def callback(chosen, state, *, round_index):
            value = fixture.pending.handle(chosen, state, round_index=round_index)
            return dict(value, invented_flag=True)

        with self.assertRaises(engine.driver.LoopHalted): fixture.run(pending_handler=callback)
        native = fixture.raw.native.batch.snapshot()
        self.assertIsNotNone(native["micro_evolution"]["pending"])
        self.assertEqual(len(native["micro_evolution"]["history"]), 0)
        self.assertEqual(len(native["capacity_work"]), 2)
        self.assertFalse(Path(fixture.raw.slots[2]).exists())

    def test_callback_native_adoption_is_detected_and_not_relabelled_as_Root_use(self):
        fixture = self.fixture(axes=("H",))

        def callback(chosen, state, *, round_index):
            value = fixture.pending.handle(chosen, state, round_index=round_index)
            snap = fixture.raw.native.batch.snapshot()
            fixture.raw.native.adapter.review(value["review_receipt"], expected_state_sha256=snap["state_sha256"])
            return value

        with self.assertRaises(engine.driver.LoopHalted): fixture.run(pending_handler=callback)
        native = fixture.raw.native.batch.snapshot()
        # Trusted Python callback already performed this real side effect. The
        # engine detects it, does not hide/undo it, and never claims containment.
        self.assertEqual(len(native["micro_evolution"]["history"]), 1)
        self.assertEqual(native["micro_evolution"]["history"][0]["review"]["decision"], "accept")
        self.assertEqual(len(native["capacity_work"]), 2)
        self.assertFalse(Path(fixture.raw.slots[2]).exists())

    def test_wrong_pending_review_identity_cannot_close_other_candidate(self):
        fixture = self.fixture(axes=("H",))

        def callback(chosen, state, *, round_index):
            value = fixture.pending.handle(chosen, state, round_index=round_index)
            body = engine.read(value["review_receipt"])
            body["review"]["proposal_sha256"] = "a" * 64
            bad = engine.save(fixture.raw.role_root / "effects/round-01/wrong-review.json", body)
            return dict(value, review_receipt=bad, artifacts=[*value["artifacts"], bad])

        with self.assertRaises(engine.driver.LoopHalted): fixture.run(pending_handler=callback)
        native = fixture.raw.native.batch.snapshot()
        self.assertIsNotNone(native["micro_evolution"]["pending"])
        self.assertEqual(len(native["micro_evolution"]["history"]), 0)
        self.assertFalse(Path(fixture.raw.slots[2]).exists())

    def test_insufficient_prospective_quota_or_consumed_downstream_stops_before_trial(self):
        for kind in ("quota", "downstream"):
            with self.subTest(kind=kind):
                fixture = self.fixture(axes=("H",), quota=2 if kind == "quota" else 6)
                if kind == "downstream":
                    slot = Path(fixture.raw.slots[2]); slot.mkdir(parents=True)
                    (slot / "old-attempt.txt").write_text("preserve original closed slot")
                with self.assertRaises(engine.driver.LoopHalted): fixture.run()
                native = fixture.raw.native.batch.snapshot()
                self.assertEqual(native.get("capacity_work", []), [])
                self.assertEqual(len(native["micro_evolution"]["history"]), 0)
                self.assertEqual(fixture.raw.calls, [])
                self.assertIsNotNone(native["micro_evolution"]["pending"])

    def test_child_uncertainty_stays_claimed_without_adoption_or_second_Controller(self):
        fixture = self.fixture()
        replies = [fixture.raw.research(), fixture.raw.final(), TimeoutError("invented private child failure")]
        with self.assertRaises(engine.driver.LoopHalted): fixture.run(replies=replies)
        native = fixture.raw.native.batch.snapshot()
        self.assertEqual([row["status"] for row in native["capacity_work"]], ["completed", "claimed"])
        self.assertEqual(len(native["micro_evolution"]["history"]), 0)
        self.assertIsNotNone(native["micro_evolution"]["pending"])
        self.assertEqual(len(fixture.packets), 1)
        self.assertFalse(Path(fixture.raw.slots[2]).exists())
        self.assertEqual(len(fixture.raw.calls), 6)
        rows, calls = fixture.raw.rows(), deepcopy(fixture.raw.calls)
        with self.assertRaises(engine.driver.LoopHalted): fixture.run(replies=replies)
        self.assertEqual(fixture.raw.native.batch.snapshot(), native)
        self.assertEqual(fixture.raw.rows(), rows)
        self.assertEqual(fixture.raw.calls, calls)
        self.assertEqual(len(fixture.packets), 1)

    def test_original_authored_source_drift_fails_before_native_proposal_or_trial(self):
        fixture = self.fixture(axes=("H",))
        fixture.author_drift = True
        with self.assertRaises(engine.driver.LoopHalted): fixture.run()
        native = fixture.raw.native.batch.snapshot()
        self.assertIsNone(native["micro_evolution"]["pending"])
        self.assertEqual(len(native["micro_evolution"]["history"]), 0)
        self.assertEqual(fixture.raw.calls, [])
        self.assertTrue((fixture.raw.root / "before-drift-harness_v2.py").is_file())

    def test_changed_plan_or_registration_cannot_trigger_downstream_use(self):
        for kind in ("plan", "registration"):
            with self.subTest(kind=kind):
                fixture = self.fixture(axes=("H",))
                path = Path(fixture.plan_binding["path"] if kind == "plan" else fixture.registration_binding["path"])
                (path.parent / ("before-drift-" + path.name)).write_bytes(path.read_bytes())
                path.write_bytes(path.read_bytes() + b" ")
                with self.assertRaises((ValueError, engine.driver.LoopHalted)): fixture.run()
                native = fixture.raw.native.batch.snapshot()
                self.assertEqual(len(native["micro_evolution"]["history"]), 0)
                self.assertFalse(Path(fixture.raw.slots[2]).exists())
                self.assertEqual(fixture.raw.calls, [])


if __name__ == "__main__":
    unittest.main()
