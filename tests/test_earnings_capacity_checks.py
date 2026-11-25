"""Actual local mechanism probes over the retained matched-trial originals.

Only the HTTP bytes/data are invented by the existing composed fixture. These
tests do not adopt a candidate, sample another model, attest an OS sandbox, or
claim production rollback, provider restart, learning or predictive improvement.
"""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from earnings_capacity_checks import MechanicalProbes
from earnings_capacity_worker import CapacityWorker
from earnings_effect_review import FACTS, SCOPES
from earnings_shadow_measurement import compare
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
from supervisor_harness import continuous_discovery_batch as native_batch
import test_earnings_shadow_trial as trials


class MechanicalCapacityChecksTests(unittest.TestCase):
    def fixture(self, axis="H"):
        owner = trials.MatchedShadowTrialTests()
        self.addCleanup(owner.doCleanups)
        fixture = owner.fixture(axis)
        fixture.original_owner = owner
        fixture.comparison_binding = owner.invoke(fixture)
        fixture.probes = MechanicalProbes(fixture.task)
        return fixture

    def root(self, fixture, name="probe-01"):
        return fixture.role_root / "effects" / name

    def tree(self, root):
        return {str(p): ("link", str(p.readlink())) if p.is_symlink() else ("file", p.read_bytes())
                for p in root.rglob("*") if p.is_symlink() or p.is_file()}

    def capture(self, fixture):
        # Observe only this temporary fixture's ledger; never open a real ledger.
        return {"native": fixture.native.batch.snapshot(),
                "batch": self.tree(fixture.native.batch.root),
                "registry": self.tree(fixture.capacity.registry),
                "sources": {name: (fixture.root / name).read_bytes() for name in fixture.native.files},
                "task_sources": fixture.task.sources(),
                "initial": Path(fixture.initial["path"]).read_bytes(),
                "originals": fixture.original_owner.all_originals(fixture),
                "budget": fixture.rows(), "calls": deepcopy(fixture.calls),
                "raws": deepcopy(fixture.raws), "factory_calls": fixture.factory.call_count}

    def run_probe(self, fixture, name="probe-01", comparison=None):
        root = self.root(fixture, name)
        bound = fixture.probes.run(fixture.capacity,
            fixture.comparison_binding if comparison is None else comparison, root)
        self.assertEqual(bound, engine.pin(root / "observations.json"))
        return root, engine.read(bound)

    def rejected(self, fixture, comparison=None, *, name="rejected", root=None):
        root = self.root(fixture, name) if root is None else root
        before = self.capture(fixture)
        with self.assertRaises((ValueError, KeyError, FileNotFoundError)):
            fixture.probes.run(fixture.capacity,
                fixture.comparison_binding if comparison is None else comparison, root)
        self.assertEqual(self.capture(fixture), before)
        self.assertFalse(root.exists())

    def altered_comparison(self, fixture, value, name):
        # Keep the retained arm files in the original comparison directory.
        # Moving the comparison would test a missing-arm error, not attribution.
        return engine.save(fixture.comparison / (name + ".json"), value)

    def test_actual_eight_groups_are_computed_and_original_state_budget_unchanged(self):
        fixture = self.fixture()
        before = self.capture(fixture)
        root, proof = self.run_probe(fixture)
        self.assertEqual(set(proof), {"schema", "binding", "scopes", "observations", "sources", "native_state_sha256"})
        self.assertEqual(proof["schema"], "earnings_mechanical_checks_v1")
        self.assertEqual(proof["scopes"], SCOPES)
        self.assertEqual(set(proof["observations"]), set(FACTS))
        pending = before["native"]["micro_evolution"]["pending"]
        parent = fixture.capacity._selected(before["native"])["manifest"]
        child = fixture.capacity._version(pending["pair"])["manifest"]
        self.assertEqual(proof["binding"], {"proposal_sha256": pending["record_sha256"],
            "before_identity_sha256": digest(parent), "after_identity_sha256": digest(child),
            "tested_pair_sha256": digest(pending["pair"]),
            "anchor_pair_sha256": digest(before["native"]["micro_evolution"]["anchor_pair"])})
        self.assertEqual(proof["native_state_sha256"], before["native"]["state_sha256"])
        self.assertEqual(proof["sources"], {"producer": engine.source_of(fixture.probes.run), "task": fixture.task.sources()})
        for name, expected in FACTS.items():
            with self.subTest(group=name):
                observation = proof["observations"][name]
                self.assertEqual(set(observation), {"facts", "artifacts"})
                self.assertEqual(set(observation["facts"]), expected)
                self.assertTrue(all(type(v) is bool and v for v in observation["facts"].values()))
                self.assertGreater(len(observation["artifacts"]), 1)
                receipt = engine.read(observation["artifacts"][0])
                self.assertEqual(receipt["facts"], observation["facts"])
                self.assertEqual(receipt["scope"], SCOPES[name])
                self.assertEqual(receipt["binding"], proof["binding"])
                self.assertEqual(receipt["originals"], observation["artifacts"][1:])
                engine.driver._artifacts(observation)
                self.assertEqual(observation["artifacts"][0], engine.pin(root / (name + ".json")))
        self.assertEqual(self.capture(fixture), before)
        self.assertIsNotNone(before["native"]["micro_evolution"]["pending"])
        self.assertEqual(before["native"]["micro_evolution"]["history"], [])

    def test_cold_native_and_initial_state_restore_exact_retained_journal(self):
        fixture = self.fixture()
        root, proof = self.run_probe(fixture)
        before = engine.read(engine.pin(root / "native-before.json"))
        cold = engine.read(engine.pin(root / "native-cold.json"))
        self.assertEqual(cold, before)
        journal = engine.read(engine.pin(root / "journal-comparison.json"))
        self.assertEqual(journal["cold"], journal["original"])
        self.assertGreater(len(journal["original"]), 0)
        scratch = engine.read(engine.pin(root / "native-scratch.json"))
        for name, token in journal["original"].items():
            self.assertEqual(token, engine.pin(fixture.native.batch.root / "journal" / name)["sha256"])
            self.assertEqual(token, engine.pin(Path(scratch["batch_root"]) / "journal" / name)["sha256"])
        restart = engine.read(proof["observations"]["restart"]["artifacts"][0])
        restored_state = fixture.task.load_state(restart["originals"][-1])
        self.assertEqual(restored_state, fixture.task.load_state(fixture.initial))
        self.assertTrue(restart["facts"]["cold_identity_equal"])
        self.assertTrue(restart["facts"]["cold_state_equal"])
        self.assertIn("not provider restart", restart["scope"])

    def test_tool_denial_is_actual_dispatch_and_feedback_is_whitelisted_failure(self):
        fixture = self.fixture()
        actual = CapacityWorker.dispatch
        seen = []
        def dispatch(worker, name, arguments):
            seen.append((worker, name, deepcopy(arguments)))
            return actual(worker, name, arguments)
        with patch.object(CapacityWorker, "dispatch", new=dispatch):
            root, proof = self.run_probe(fixture)
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0][1:], ("read_file", {"path": "__not_a_public_filing__", "offset": 0, "characters": 256}))
        denial = engine.read(engine.pin(root / "tool-denial.json"))
        self.assertEqual(set(denial), {"denied", "error_type", "feedback"})
        self.assertIs(denial["denied"], True)
        self.assertIn(denial["error_type"], {"ValueError", "KeyError"})
        feedback = denial["feedback"]
        self.assertEqual(set(feedback), {"schema", "task_id", "cik", "evidence_scope", "prediction", "execution"})
        self.assertEqual(feedback["prediction"], {"planned_targets": 5, "scored_targets": 0, "score_out_of_5": None})
        self.assertEqual(feedback["execution"], {"status": "FAILED_NO_RETRY", "error_type": denial["error_type"]})
        self.assertEqual((feedback["task_id"], feedback["cik"]), (fixture.task_id, fixture.company["cik"]))
        self.assertEqual(proof["observations"]["failure_feedback"]["facts"], {"tool_denied": True, "feedback_safe": True})

    def test_actual_pure_rollback_is_conditional_without_real_adoption(self):
        fixture = self.fixture()
        native = deepcopy(fixture.native.batch.snapshot())
        actual = engine.activation.micro.rollback_micro_evolution
        with patch.object(engine.activation.micro, "rollback_micro_evolution", wraps=actual) as rollback:
            root, proof = self.run_probe(fixture)
        rollback.assert_called_once()
        retained = engine.read(engine.pin(root / "conditional-rollback.json"))
        self.assertIs(retained["conditional"], True)
        self.assertIs(retained["production_adoption"], False)
        micro = native["micro_evolution"]
        projected, rolled = retained["before"], retained["after"]
        self.assertEqual(projected["active_pair"], micro["pending"]["pair"])
        self.assertEqual(projected["previous_pair"], micro["active_pair"])
        self.assertIsNone(projected["pending"])
        self.assertEqual(rolled["active_pair"], micro["active_pair"])
        self.assertEqual(rolled["history"][:-1], micro["history"])
        self.assertEqual(len(rolled["history"]), len(micro["history"]) + 1)
        self.assertEqual(fixture.native.batch.snapshot(), native)
        self.assertTrue(all(proof["observations"]["rollback"]["facts"].values()))

    def test_anchor_interfaces_and_bounded_originals_do_not_claim_accuracy(self):
        fixture = self.fixture()
        before = self.capture(fixture)
        root, proof = self.run_probe(fixture)
        anchor = engine.read(engine.pin(root / "anchor-interfaces.json"))
        self.assertEqual(anchor["R"], {"axis": "R", "research_instructions": "", "reuse_facts": True})
        self.assertEqual(anchor["H"], {"axis": "H", "read_chunk_limit": 20000, "search_hit_limit": 50})
        self.assertIn("not accuracy", proof["scopes"]["anchor_compatibility"])
        receipt = engine.read(proof["observations"]["bounded_trial"]["artifacts"][0])
        self.assertEqual(len(receipt["originals"]), 4)
        for slot, pair in zip(fixture.slots, (receipt["originals"][:2], receipt["originals"][2:])):
            self.assertEqual(pair, [engine.pin(Path(slot) / "identity.json"), engine.pin(Path(slot) / "budget-summary.json")])
        work = before["native"]["capacity_work"]
        self.assertEqual([r["status"] for r in work], ["completed", "completed"])
        self.assertEqual({r["pair_sha256"] for r in work}, {fixture.active})
        self.assertEqual(self.capture(fixture), before)

    def test_rebound_criterion_cannot_replace_original_predeclared_criterion(self):
        fixture = self.fixture()
        measured = engine.read(fixture.comparison_binding)
        criterion = dict(measured["declaration"], min_delta=2)
        changed = deepcopy(measured)
        changed.update(compare(measured["originals"]["parent"], measured["originals"]["child"], declaration=criterion))
        bound = self.altered_comparison(fixture, changed, "rebound-criterion")
        self.rejected(fixture, bound)
        self.assertEqual(engine.read(fixture.criterion)["min_delta"], 1)

    def test_exact_distinct_work_ids_and_saved_arm_originals_are_required(self):
        fixture = self.fixture()
        measured = engine.read(fixture.comparison_binding)
        original_ids = measured["work_ids"]
        for name, ids in (("duplicate", [original_ids[0], original_ids[0]]),
                          ("unknown", [original_ids[0], "unknown-completed-work"]),
                          ("swapped", list(reversed(original_ids))), ("missing", original_ids[:1])):
            with self.subTest(kind=name):
                changed = dict(measured, work_ids=ids)
                self.rejected(fixture, self.altered_comparison(fixture, changed, "bad-work-" + name), name=name)
        # A consistent-looking measured arm change still cannot replace native
        # completion evidence. Keep the actual parent.json unchanged.
        changed = deepcopy(measured)
        changed["originals"]["parent"]["probe_only_unrecorded_field"] = True
        self.rejected(fixture, self.altered_comparison(fixture, changed, "arm-substitution"), name="arm-substitution")

    def test_trial_identity_source_or_task_drift_fails_before_probe_root(self):
        fixture = self.fixture()
        measured = engine.read(fixture.comparison_binding)
        for name in ("parent-identity", "child-identity", "proposal", "source"):
            with self.subTest(kind=name):
                claim = deepcopy(engine.read(measured["trial_claim"]))
                key = {"parent-identity": "before_identity_sha256", "child-identity": "after_identity_sha256",
                       "proposal": "pending_proposal_sha256"}.get(name)
                if key is not None:
                    claim[key] = "e" * 64
                else:
                    claim["sources"]["coordinator"]["sha256"] = "e" * 64
                claim_binding = engine.save(fixture.comparison / ("wrong-trial-" + name + ".json"), claim)
                changed = dict(measured, trial_claim=claim_binding)
                self.rejected(fixture, self.altered_comparison(fixture, changed, "wrong-comparison-" + name), name=name)
        original_kernel = fixture.task.kernel
        fixture.task.kernel = dict(original_kernel, qa=dict(original_kernel["qa"], sha256="e" * 64))
        try:
            self.rejected(fixture, name="task-kernel")
        finally:
            fixture.task.kernel = original_kernel
        original_id = fixture.task.state_api.task_id
        fixture.task.state_api.task_id = "different-fixture-task"
        try:
            self.rejected(fixture, name="task-namespace")
        finally:
            fixture.task.state_api.task_id = original_id

    def test_raw_resource_or_original_byte_tamper_is_not_repaired(self):
        fixture = self.fixture()
        # Deliberate owned-fixture corruption precedes the captured baseline.
        # The producer must preserve those failed bytes, not silently repair.
        paths = [Path(fixture.slots[0]) / "01-response.json", Path(fixture.slots[1]) / "budget-summary.json",
                 Path(fixture.context_binding["path"]), Path(fixture.study_binding["path"])]
        for index, path in enumerate(paths):
            with self.subTest(artifact=path.name):
                old = path.read_bytes()
                path.write_bytes(old + b"\n ")
                try:
                    self.rejected(fixture, name="tamper-" + str(index))
                    self.assertEqual(path.read_bytes(), old + b"\n ")
                finally:
                    path.write_bytes(old)

    def test_snapshot_guard_rejects_missing_pending_or_active_work_before_any_scratch(self):
        fixture = self.fixture()
        native = fixture.native.batch.snapshot()
        originals = self.capture(fixture)
        # Isolated API guard probes, not claims that the real journal was changed.
        for kind in ("no-pending", "busy"):
            supplied = deepcopy(native)
            if kind == "no-pending": supplied["micro_evolution"]["pending"] = None
            else: supplied["active_attempt_ids"] = ["owned-guard-fixture"]
            root = self.root(fixture, kind)
            with self.subTest(kind=kind), patch.object(fixture.native.batch, "snapshot", return_value=supplied):
                with self.assertRaisesRegex(ValueError, "Exact idle pending"):
                    fixture.probes.run(fixture.capacity, fixture.comparison_binding, root)
            self.assertFalse(root.exists())
            self.assertEqual(self.capture(fixture), originals)

    def test_consumed_or_noncanonical_probe_root_never_overwrites_original_proof(self):
        fixture = self.fixture()
        root, _ = self.run_probe(fixture)
        old = self.tree(root)
        before = self.capture(fixture)
        bad_paths = [root, fixture.root / "outside-effects",
                     str(fixture.role_root / "effects") + "/../effects/alias", Path("relative-probe")]
        for candidate in bad_paths:
            with self.subTest(path=str(candidate)):
                with self.assertRaises(ValueError):
                    fixture.probes.run(fixture.capacity, fixture.comparison_binding, candidate)
                self.assertEqual(self.tree(root), old)
                self.assertEqual(self.capture(fixture), before)
        self.assertFalse((fixture.root / "outside-effects").exists())
        self.assertFalse(self.root(fixture, "alias").exists())

    def test_unchanged_R_trial_can_pass_mechanics_without_benefit_or_adoption(self):
        fixture = self.fixture("R")
        measured = engine.read(fixture.comparison_binding)
        self.assertIs(measured["benefit_observed"], False)
        self.assertEqual(measured["delta"]["input_tokens"], 0)
        before = self.capture(fixture)
        _, proof = self.run_probe(fixture)
        self.assertTrue(all(all(v["facts"].values()) for v in proof["observations"].values()))
        self.assertEqual(self.capture(fixture), before)
        self.assertEqual(before["native"]["micro_evolution"]["history"], [])
        self.assertIsNotNone(before["native"]["micro_evolution"]["pending"])
        self.assertEqual(measured["claims"], {"learning": False, "model_authorship": False, "predictive_gain": False})

    def test_codex_shaped_run_records_use_external_cold_native_without_relaxing_guard(self):
        # Compose a fresh synthetic episode BEFORE either forecast is launched.
        # The original owned fixture clock bytes are retained in the old root
        # and copied exactly; this is not a financial-data admission override
        # or a relabelled completed attempt.
        owner = trials.MatchedShadowTrialTests()
        self.addCleanup(owner.doCleanups)
        fixture = owner.fixture()
        old_clock = Path(fixture.clock_binding["path"]).read_bytes()
        fixture.role_root = fixture.root / ".codex" / "worktrees" / "records" / fixture.task_id
        fixture.role_root.mkdir(parents=True)
        fixture.clock_binding = trials.raw_fixture._save(fixture.role_root / "clock.json", fixture.window)
        self.assertEqual(Path(fixture.clock_binding["path"]).read_bytes(), old_clock)
        trials.raw_fixture._save(fixture.role_root / "clock.binding.json", fixture.clock_binding)
        fixture.slots = [str(fixture.role_root / "roles" / f"forecast-{i:02d}") for i in range(1, 7)]
        fixture.rewrite_context(dict(fixture.context, root=str(fixture.role_root), slots=fixture.slots))
        fixture.envelope = dict(fixture.envelope, root=str(fixture.role_root))
        fixture.comparison = fixture.role_root / "shadow" / "matched-01"
        fixture.service_object = fixture.service()
        fixture.original_owner = owner
        fixture.comparison_binding = owner.invoke(fixture)
        fixture.probes = MechanicalProbes(fixture.task)
        before = self.capture(fixture)
        root, proof = self.run_probe(fixture)
        scratch_binding = engine.pin(root / "native-scratch.json")
        scratch = engine.read(scratch_binding)
        self.assertEqual(set(scratch), {"native_root", "batch_root", "registry_root"})
        self.assertTrue(root.is_relative_to(fixture.role_root / "effects"))
        self.assertFalse(Path(scratch["native_root"]).is_relative_to(fixture.role_root))
        self.assertEqual(Path(scratch["native_root"]).parent, fixture.capacity.registry.parent / "probe-scratch")
        with self.assertRaisesRegex(native_batch.DiscoveryBatchError, "worktree"):
            native_batch._safe_root(root / "cold-batch", allow_temporary=True)
        self.assertEqual(native_batch._safe_root(scratch["batch_root"], allow_temporary=True),
                         Path(scratch["batch_root"]))
        self.assertFalse((root / "cold-batch").exists())
        self.assertFalse((root / "cold-versions").exists())
        self.assertTrue(Path(scratch["batch_root"]).is_dir())
        self.assertTrue(Path(scratch["registry_root"]).is_dir())
        self.assertEqual(proof["observations"]["restart"]["artifacts"][-2], scratch_binding)
        self.assertTrue(all(proof["observations"]["restart"]["facts"].values()))
        self.assertEqual(self.capture(fixture), before)
        self.assertEqual(engine.read(fixture.comparison_binding)["claims"],
                         {"learning": False, "model_authorship": False, "predictive_gain": False})


if __name__ == "__main__":
    unittest.main()
