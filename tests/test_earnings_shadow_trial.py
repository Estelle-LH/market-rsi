"""Real matched coordinator/native work with only invented raw HTTP responses.

Actual CapacityForecast, Task.shadow_execution and original scorer run for
both arms under one borrowed fixture budget/window. No acceptance or fabricated
benefit receipt; native ownership remains the active parent throughout.
"""
from contextlib import ExitStack
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from types import MethodType

import earnings_clock as clock
import earnings_entry as entry
import earnings_shadow_trial as trial
from earnings_research_state import ResearchState
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_capacity_forecast as raw_fixture
import test_earnings_shadow_execution as execution_fixture

PRIVATE = "TRIAL_PRIVATE_PROVIDER_FAILURE_MUST_NOT_REACH_TERMINAL"


class MatchedShadowTrialTests(unittest.TestCase):
    def test_explicit_task_factory_used_for_both_actual_arms(self):
        fixture=self.fixture()
        calls=[]
        def make_worker(task, task_id, capacity, pair, state_root, state, **kwargs):
            calls.append((pair,kwargs.get('shadow_proposal_sha256')))
            return trial.CapacityWorker(task.company, task_id, capacity, pair, state_root, state, **kwargs)
        fixture.task.make_worker=MethodType(make_worker,fixture.task)
        bound=self.invoke(fixture)
        self.assertEqual(calls,[(fixture.active,None),(fixture.active,fixture.token)])
        self.assertEqual(engine.read(bound)['claims']['model_authorship'],False)
        for arm in ('parent','child'):
            receipt=engine.read(engine.pin(fixture.comparison/(arm+'-worker.json')))
            self.assertEqual(receipt['factory'],engine.source_of(fixture.task.make_worker))
            self.assertEqual(receipt['source'],engine.pin(trial.worker_source.__file__))

    def fixture(self, axis="H"):
        helper = execution_fixture.ShadowExecutionTests(
            "test_actual_parent_and_child_forecasts_share_prior_bytes_but_distinct_consumption")
        self.addCleanup(helper.doCleanups)
        fixture = helper.fixture(axis)
        fixture.task.company = fixture.company
        fixture.task.state_api = ResearchState(fixture.company, fixture.task_id)
        fixture.envelope = {"id": fixture.task_id, "root": str(fixture.role_root),
            "study": fixture.study_binding, "evaluation_kernel": fixture.kernel,
            "source_commit": raw_fixture.SOURCE_COMMIT, "initial_state": fixture.initial,
            "cik": fixture.company["cik"], "mode": "offline_replay"}
        criterion = {"schema": "earnings_shadow_criterion_v1", "component": "tool_interface" if axis == "H" else "research_policy",
            "metric": "tool_return_characters" if axis == "H" else "input_tokens",
            "direction": "lower", "min_delta": 1}
        fixture.criterion = raw_fixture._save(fixture.root / "criterion.json", criterion)
        fixture.comparison = fixture.role_root / "shadow" / "matched-01"
        fixture.service_object = fixture.service()
        return fixture

    def invoke(self, fixture, *, replies=None, **changes):
        names = {"pending_proposal_sha256": fixture.token,
            "forecast": fixture.service_object.forecast,
            "parent_slot": fixture.slots[0], "child_slot": fixture.slots[1],
            "comparison_root": fixture.comparison, "criterion_binding": fixture.criterion}
        names.update(changes)
        envelope = names.pop("envelope", fixture.envelope)
        state = names.pop("parent_state", fixture.initial)
        replies = [fixture.research(), fixture.final(), fixture.research(), fixture.final()] if replies is None else replies

        def deadline_init(transport_object, client, **options):
            options.update(clock=lambda: fixture.wall, monotonic=lambda: fixture.monotonic)
            raw_fixture.DEADLINE_INIT(transport_object, client, **options)

        with ExitStack() as stack:
            stack.enter_context(patch("earnings_http.http.client.HTTPSConnection", side_effect=fixture.fake_connection(replies)))
            stack.enter_context(patch.object(entry, "credential", side_effect=AssertionError("No credentials")))
            stack.enter_context(patch.object(entry, "NightBudget", side_effect=AssertionError("No budget reopen")))
            stack.enter_context(patch.object(clock, "boot_id", return_value=raw_fixture.BOOT))
            stack.enter_context(patch.object(entry.time, "time", side_effect=lambda: fixture.wall))
            stack.enter_context(patch.object(entry.time, "monotonic", side_effect=lambda: fixture.monotonic))
            stack.enter_context(patch.object(entry.DeadlineHTTP, "__init__", new=deadline_init))
            return trial.run_matched(fixture.task, envelope, fixture.capacity, state, **names)

    def all_originals(self, fixture):
        result = {}
        for root in (fixture.comparison, Path(fixture.slots[0]), Path(fixture.slots[1])):
            if root.exists():
                result.update({str(path): path.read_bytes() for path in root.rglob("*") if path.is_file() and not path.is_symlink()})
        return result

    def assert_native_parent(self, fixture, micro_before):
        after = fixture.native.batch.snapshot()
        self.assertEqual(after["micro_evolution"], micro_before)
        self.assertEqual(digest(after["micro_evolution"]["active_pair"]), fixture.active)
        return after

    def assert_preclaim_rejected(self, fixture, **changes):
        before = fixture.native.batch.snapshot()
        with self.assertRaises(ValueError):
            self.invoke(fixture, **changes)
        self.assertEqual(fixture.native.batch.snapshot(), before)
        self.assertEqual(fixture.calls, [])
        self.assertEqual(fixture.rows(), [])
        self.assertFalse(fixture.comparison.exists())
        fixture.factory.assert_not_called()

    def test_actual_H_trial_measures_originals_with_parent_owned_native_claims(self):
        fixture = self.fixture()
        micro = deepcopy(fixture.native.batch.snapshot()["micro_evolution"])
        initial_bytes = Path(fixture.initial["path"]).read_bytes()
        with patch.object(fixture.budget, "close", wraps=fixture.budget.close) as closed:
            bound = self.invoke(fixture)
            closed.assert_not_called()
        self.assertEqual(bound, raw_fixture._pin(fixture.comparison / "comparison.json"))
        measured = engine.read(bound)
        self.assertIs(measured["benefit_observed"], True)
        self.assertLess(measured["delta"]["tool_return_characters"], -1)
        self.assertEqual(measured["score_delta"], 0)
        self.assertEqual(measured["claims"], {"learning": False, "model_authorship": False, "predictive_gain": False})
        native = self.assert_native_parent(fixture, micro)
        work = native["capacity_work"]
        self.assertEqual(len(work), 2)
        self.assertEqual(native["active_attempt_ids"], [])
        self.assertEqual([row["status"] for row in work], ["completed", "completed"])
        self.assertEqual([row["pair_sha256"] for row in work], [fixture.active, fixture.active])
        self.assertEqual(measured["work_ids"], [row["work_id"] for row in work])
        for arm, tested, row in (("parent", fixture.active, work[0]), ("child", fixture.tested, work[1])):
            verified = engine.read(engine.pin(fixture.comparison / (arm + ".json")))
            self.assertEqual(verified["consumed"], {"active_pair_sha256": fixture.active,
                "tested_pair_sha256": tested, "pending_proposal_sha256": fixture.token,
                "state_sha256": fixture.initial["sha256"]})
            self.assertEqual(row["output_evidence_sha256"], engine.pin(fixture.comparison / (arm + ".json"))["sha256"])
            effective = json.loads((Path(fixture.slots[0 if arm == "parent" else 1]) / "effective-capacity.json").read_bytes())
            self.assertEqual(Path(effective["initial_state"]["path"]).read_bytes(), initial_bytes)
            self.assertEqual(Path(effective["initial_state"]["path"]).parent, fixture.comparison / (arm + "-memory"))
            self.assertEqual(json.loads(entry.checked(verified["score"]))["score_out_of_5"], 5)
        claim = engine.read(measured["trial_claim"])
        self.assertEqual(claim["initial_state"], fixture.initial)
        self.assertEqual(claim["study"], fixture.study_binding)
        self.assertEqual(claim["kernel"], fixture.kernel)
        self.assertEqual(claim["criterion"], fixture.criterion)
        self.assertEqual(claim["pending_proposal_sha256"], fixture.token)
        self.assertEqual(claim["active_pair_sha256"], fixture.active)
        self.assertEqual(claim["tested_pair_sha256"], fixture.tested)
        self.assertEqual(claim["forecast_source"], engine.source_of(fixture.service_object.forecast))
        self.assertEqual(set(claim["sources"]), {"coordinator", "worker", "task", "measurement"})
        terminal = engine.read(engine.pin(fixture.comparison / "terminal.json"))
        self.assertEqual(terminal, {"status": "MEASURED", "comparison": bound, "retry_allowed": False})
        self.assertFalse((fixture.comparison / "failed.json").exists())
        self.assertEqual(Path(fixture.initial["path"]).read_bytes(), initial_bytes)
        self.assertEqual(len(fixture.calls), 8)
        self.assertEqual(len(fixture.rows()), 4)
        self.assertEqual(fixture.factory.call_count, 2)
        self.assertTrue(all(row[2] == "settled" for row in fixture.rows()))

    def test_actual_R_unchanged_observations_are_retained_without_adoption(self):
        fixture = self.fixture("R")
        micro = deepcopy(fixture.native.batch.snapshot()["micro_evolution"])
        bound = self.invoke(fixture)
        measured = engine.read(bound)
        self.assertIs(measured["benefit_observed"], False)
        self.assertEqual(measured["delta"]["input_tokens"], 0)
        self.assertEqual(measured["score_delta"], 0)
        native = self.assert_native_parent(fixture, micro)
        self.assertEqual([row["status"] for row in native["capacity_work"]], ["completed", "completed"])
        self.assertEqual(len(native["micro_evolution"]["history"]), 0)

    def test_bad_criterion_identity_or_task_context_rejected_before_any_claim(self):
        for kind in ("criterion-list", "wrong-component", "invalid-threshold", "token", "id", "mode", "cik", "kernel"):
            with self.subTest(kind=kind):
                fixture = self.fixture()
                changes = {}
                if kind.startswith("criterion") or kind in ("wrong-component", "invalid-threshold"):
                    value = engine.read(fixture.criterion)
                    if kind == "criterion-list": value = []
                    elif kind == "wrong-component": value.update(component="research_policy", metric="input_tokens")
                    else: value["min_delta"] = 0
                    changes["criterion_binding"] = raw_fixture._save(fixture.root / "wrong-criterion.json", value)
                elif kind == "token": changes["pending_proposal_sha256"] = "e" * 64
                else:
                    envelope = deepcopy(fixture.envelope)
                    if kind == "id": envelope["id"] = "../unrelated-task"
                    elif kind == "mode": envelope["mode"] = "live"
                    elif kind == "cik": envelope["cik"] = "CIK0000000002"
                    else: envelope["evaluation_kernel"] = dict(fixture.kernel, qa=dict(fixture.kernel["qa"], sha256="d" * 64))
                    changes["envelope"] = envelope
                self.assert_preclaim_rejected(fixture, **changes)

    def test_false_or_consumed_role_and_comparison_paths_are_preclaim_failures(self):
        for kind in ("same-slot", "outside-slot", "undeclared-flat-slot", "consumed-slot", "outside-comparison", "alias-comparison"):
            with self.subTest(kind=kind):
                fixture = self.fixture()
                if kind == "same-slot": changes = {"child_slot": fixture.slots[0]}
                elif kind == "outside-slot": changes = {"parent_slot": str(fixture.root / "outside-role")}
                elif kind == "undeclared-flat-slot": changes = {"parent_slot": str(fixture.role_root / "roles" / "not-declared")}
                elif kind == "consumed-slot":
                    path = Path(fixture.slots[0]); path.mkdir(parents=True)
                    (path / "old-attempt.txt").write_text("preserve consumed original")
                    changes = {}
                elif kind == "outside-comparison": changes = {"comparison_root": fixture.root / "outside-comparison"}
                else: changes = {"comparison_root": str(fixture.role_root / "shadow") + "/../shadow/matched-01"}
                self.assert_preclaim_rejected(fixture, **changes)
                if kind == "consumed-slot": self.assertEqual((path / "old-attempt.txt").read_text(), "preserve consumed original")

    def test_wrong_initial_state_busy_or_insufficient_quota_rejected_before_forecast(self):
        for kind in ("state", "quota", "busy"):
            with self.subTest(kind=kind):
                fixture = self.fixture()
                changes = {}
                if kind == "state":
                    other = ResearchState(fixture.company, "different-fixture-task")
                    changes["parent_state"] = other.save(fixture.root / "other-memory", other.empty())
                else:
                    # Genuine bounded native bookkeeping setup, not forecast
                    # success, research capacity benefit or new admission.
                    for index in range(2 if kind == "quota" else 1):
                        snap = fixture.native.batch.snapshot()
                        work_id = f"fixture-preconsumed-{index}"
                        fixture.native.batch.record_capacity_work("claim", work_id=work_id,
                            pair_sha256=fixture.active, evidence_sha256=digest({"fixture": kind, "index": index}),
                            expected_state_sha256=snap["state_sha256"])
                        if kind == "quota":
                            snap = fixture.native.batch.snapshot()
                            fixture.native.batch.record_capacity_work("complete", work_id=work_id,
                                pair_sha256=fixture.active, evidence_sha256=digest({"fixture-bookkeeping": index}),
                                expected_state_sha256=snap["state_sha256"])
                self.assert_preclaim_rejected(fixture, **changes)

    def test_child_provider_failure_preserves_parent_and_sticky_active_child_claim(self):
        fixture = self.fixture()
        micro = deepcopy(fixture.native.batch.snapshot()["micro_evolution"])
        with self.assertRaises(RuntimeError):
            self.invoke(fixture, replies=[fixture.research(), fixture.final(), TimeoutError(PRIVATE)])
        native = self.assert_native_parent(fixture, micro)
        self.assertEqual([row["status"] for row in native["capacity_work"]], ["completed", "claimed"])
        self.assertEqual(native["active_attempt_ids"], [native["capacity_work"][1]["work_id"]])
        failed = engine.read(engine.pin(fixture.comparison / "failed.json"))
        self.assertEqual(failed["status"], "FAILED_NO_RETRY")
        self.assertIs(failed["retry_allowed"], False)
        self.assertEqual(set(failed["completed_outputs"]), {"parent"})
        self.assertNotIn(PRIVATE, json.dumps(failed))
        self.assertFalse((fixture.comparison / "comparison.json").exists())
        self.assertTrue((fixture.comparison / "claim.json").is_file())
        self.assertEqual([row[2] for row in fixture.rows()], ["settled", "settled", "uncertain"])
        self.assertEqual(len(fixture.calls), 6)
        # Idle guard rejects before reading any putative acceptance envelope;
        # this is not a fake compatibility or benefit receipt.
        receipt = raw_fixture._save(fixture.root / "unread-acceptance.json", {"review": {"decision": "accept"}})
        with self.assertRaisesRegex(ValueError, "idle"):
            fixture.capacity.review(receipt, expected_state_sha256=native["state_sha256"])
        originals, rows, calls = self.all_originals(fixture), fixture.rows(), deepcopy(fixture.calls)
        with self.assertRaises(ValueError): self.invoke(fixture)
        self.assertEqual(self.all_originals(fixture), originals)
        self.assertEqual(fixture.native.batch.snapshot(), native)
        self.assertEqual(fixture.rows(), rows)
        self.assertEqual(fixture.calls, calls)

    def test_mutated_child_count_cannot_complete_native_work_despite_raw_score(self):
        fixture = self.fixture()
        micro = deepcopy(fixture.native.batch.snapshot()["micro_evolution"])
        before_bytes = {}

        def corrupt(turn):
            if turn == 2:
                path = Path(fixture.slots[1]) / "01-count.json"
                before_bytes["count"] = path.read_bytes()
                (path.parent / "before-corruption-count.json").write_bytes(before_bytes["count"])
                path.write_bytes(raw_fixture._wire({"input_tokens": 0}))

        fixture.after_generation = corrupt
        with self.assertRaises(ValueError): self.invoke(fixture)
        native = self.assert_native_parent(fixture, micro)
        self.assertEqual([row["status"] for row in native["capacity_work"]], ["completed", "claimed"])
        self.assertEqual(len(fixture.calls), 8)
        self.assertTrue(all(row[2] == "settled" for row in fixture.rows()))
        child_result = json.loads((Path(fixture.slots[1]) / "result.json").read_bytes())
        self.assertEqual(child_result["status"], "COMPLETED_SCORED")
        self.assertEqual((Path(fixture.slots[1]) / "before-corruption-count.json").read_bytes(), before_bytes["count"])
        failed = engine.read(engine.pin(fixture.comparison / "failed.json"))
        self.assertEqual(failed["error_type"], "ValueError")
        self.assertEqual(set(failed["completed_outputs"]), {"parent"})
        self.assertFalse((fixture.comparison / "child.json").exists())

    def test_completed_comparison_or_slots_never_reopen_on_identical_request(self):
        fixture = self.fixture()
        self.invoke(fixture)
        originals, native = self.all_originals(fixture), fixture.native.batch.snapshot()
        rows, calls, factories = fixture.rows(), deepcopy(fixture.calls), fixture.factory.call_count
        with self.assertRaises(ValueError): self.invoke(fixture)
        self.assertEqual(self.all_originals(fixture), originals)
        self.assertEqual(fixture.native.batch.snapshot(), native)
        self.assertEqual(fixture.rows(), rows)
        self.assertEqual(fixture.calls, calls)
        self.assertEqual(fixture.factory.call_count, factories)

    def test_criterion_drift_after_parent_prevents_child_claim_or_forecast(self):
        fixture = self.fixture()
        micro = deepcopy(fixture.native.batch.snapshot()["micro_evolution"])

        def drift(turn):
            if turn == 1:
                path = Path(fixture.criterion["path"])
                (path.parent / "before-criterion-drift.json").write_bytes(path.read_bytes())
                path.write_bytes(path.read_bytes() + b" ")

        fixture.after_generation = drift
        with self.assertRaises(ValueError): self.invoke(fixture)
        native = self.assert_native_parent(fixture, micro)
        self.assertEqual([row["status"] for row in native["capacity_work"]], ["completed"])
        self.assertEqual(native["active_attempt_ids"], [])
        self.assertEqual(len(fixture.calls), 4)
        self.assertFalse(Path(fixture.slots[1]).exists())
        self.assertEqual(set(engine.read(engine.pin(fixture.comparison / "failed.json"))["completed_outputs"]), {"parent"})

    def test_terminal_diagnostic_failure_keeps_verified_outputs_comparison_and_claims(self):
        fixture = self.fixture()
        real_save = engine.save

        def fail_terminal(path, value):
            if Path(path).name == "terminal.json": raise OSError("invented terminal diagnostic failure")
            return real_save(path, value)

        with patch.object(engine, "save", side_effect=fail_terminal), self.assertRaises(OSError):
            self.invoke(fixture)
        native = fixture.native.batch.snapshot()
        self.assertEqual([row["status"] for row in native["capacity_work"]], ["completed", "completed"])
        self.assertEqual(native["active_attempt_ids"], [])
        comparison = engine.read(engine.pin(fixture.comparison / "comparison.json"))
        self.assertIs(comparison["benefit_observed"], True)
        failed = engine.read(engine.pin(fixture.comparison / "failed.json"))
        self.assertEqual(failed["error_type"], "OSError")
        self.assertEqual(set(failed["completed_outputs"]), {"parent", "child"})
        self.assertFalse((fixture.comparison / "terminal.json").exists())
        self.assertEqual(len(fixture.calls), 8)
        originals, rows = self.all_originals(fixture), fixture.rows()
        with self.assertRaises(ValueError): self.invoke(fixture)
        self.assertEqual(self.all_originals(fixture), originals)
        self.assertEqual(fixture.rows(), rows)
        self.assertEqual(fixture.native.batch.snapshot(), native)


if __name__ == "__main__":
    unittest.main()
