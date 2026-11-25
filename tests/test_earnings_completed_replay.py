"""Raw completed replay binds driver + native history without reopening owners.

Human-authored local arithmetic fixtures test record verification, not earnings
prediction, model authorship, paid inference, measured benefit or self-learning.
"""
from contextlib import ExitStack, contextmanager
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

import earnings_capacity_adapter as adapter
import earnings_capacity_runtime as runtime
import earnings_completed_replay as replay
import test_capacity_feedback_engine as engine_fixture
import test_feedback_linked_cold_replay as driver_tests
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
from supervisor_harness.continuous_discovery_batch import ContinuousDiscoveryBatch


class CompletedEarningsReplayTests(unittest.TestCase):
    def _fixture(self, *, mode="accepted", runtime_alias=False):
        owner = engine_fixture.CommonEngineTests()
        owner.setUp(); self.addCleanup(owner.doCleanups)
        owner.setup_task()
        if runtime_alias:
            # Original Native policy permits this exact pinned runtime alias.
            path = owner.root / "python"
            path.rename(owner.root / "retained-runtime-python")
            path.symlink_to(owner.root / "retained-runtime-python")
        owner.initial_snapshot_bytes = (owner.native.root / "batch/batch.json").read_bytes()
        if mode == "rejected": owner.reject = True
        if mode == "continue": owner.axes = ["continue", "continue"]
        if mode == "pending": owner.axes = ["continue", "R"]
        services = owner.services()
        if mode in {"continue", "pending"}:
            services["controller"] = owner.controller_role
        if mode == "pending":
            services["review"] = lambda choice, original, descriptor, slot: self._pending_review(
                owner, choice, original, descriptor, slot)
        owner.outcome = engine.run(owner.bound, owner.native.restore(), owner.task, services=services)
        self.assertEqual((owner.outcome["status"], owner.outcome["completed_rounds"]), ("completed", 2))
        return owner

    def _pending_review(self, owner, chosen, original, descriptor, slot):
        # A human-authored JSON-only static spec, not measured-effect evidence.
        before = descriptor["parent_identity"]
        authored = adapter.author_payload(original)
        args = deepcopy(owner.native.args)
        args["harness"], args["researcher"] = before["components"]["H"], before["components"]["R"]
        name = "researcher_v2.py"
        self.assertEqual((owner.root / name).read_bytes(), authored["source_text"].encode())
        args["researcher"] = {"sources": {name: engine.driver.c.sha(owner.root / name)},
                              "configuration_sha256": before["components"]["R"]["configuration_sha256"]}
        after = adapter.identity.manifest(**args)
        entries = {"R": name, "H": descriptor["parent_entrypoints"]["H"]}
        proposal = {"candidate_id": "retained-pending-child", "proposer_id": "fixture-author",
            "axis": "researcher", "component": chosen["component"], "behavior_change": chosen["expected_effect"],
            "problem_evidence_sha256": chosen["feedback_sha256"],
            "parent_pair_sha256": chosen["parent_pair_sha256"], "pair": adapter.activation.pair(after),
            "fixed_context": descriptor["micro_evolution"]["fixed_context"],
            "write_paths": sorted(set(before["components"]["R"]["sources"]) | {name}),
            "patch_sha256": adapter.activation.patch_digest(before, after)}
        static = owner.native.artifact({"passed": True, "reviewer_id": "independent-auditor",
            "proposer_id": "fixture-author", "identity_sha256": digest(after), "entrypoints": entries})
        body = {"schema": "capacity_review_spec_v1", "after": after, "proposal": proposal,
            "entrypoints": entries, "static_review": static, "review_receipt": None}
        return dict(body, original=owner.record(slot, body), artifacts=[static])

    def _bindings(self, owner):
        snapshot_path = owner.native.root / "batch/batch.json"
        snapshot = json.loads(snapshot_path.read_bytes())
        selected_path = owner.native.root / "versions" / (
            digest(snapshot["micro_evolution"]["active_pair"]) + ".json")
        selected = json.loads(selected_path.read_bytes())
        paths = {str(owner.root / name) for component in selected["manifest"]["components"].values()
                 for name in component["sources"]}
        sources = {path: engine.pin(path) for path in sorted(paths)}
        python = selected["manifest"]["runtime"]["python"]
        sources[python["path"]] = python
        return {"manifest_binding": engine.pin(owner.root / "episode/loop/manifest.json"),
            "native_snapshot_binding": engine.pin(snapshot_path),
            "native_journal_bindings": [engine.pin(path) for path in
                sorted(snapshot_path.parent.joinpath("journal").glob("[0-9]*.json"))],
            "selected_version_binding": engine.pin(selected_path),
            "selected_source_bindings": [sources[path] for path in sorted(sources)],
            "runtime_terminal_binding": None}

    def _seal(self, owner):
        closure = replay.seal_completed_replay(owner.bound, owner.outcome, **self._bindings(owner))
        self.assertEqual(closure["path"], str(owner.root / "episode/completed-replay.json"))
        return closure

    @contextmanager
    def _no_actions(self, owner):
        with ExitStack() as stack:
            targets = [(engine, "run"), (engine, "save"), (engine.driver.c, "save"),
                (replay, "seal_completed_replay"), (owner.task, "preflight"),
                (ContinuousDiscoveryBatch, "__init__"), (ContinuousDiscoveryBatch, "snapshot"),
                (ContinuousDiscoveryBatch, "_load_locked"), (ContinuousDiscoveryBatch, "_recover_pending_journal"),
                (runtime, "open_capacity_runtime"), (runtime, "preflight_runtime"),
                (runtime.NightBudget, "__init__"), (runtime.clock, "capture_or_load"),
                (runtime.clock.time, "time"), (sqlite3, "connect")]
            for target, name in targets:
                stack.enter_context(patch.object(target, name,
                    side_effect=AssertionError("Cold completed replay attempted " + name)))
            yield

    def _replay_unchanged(self, owner, closure):
        before = driver_tests.tree(owner.root)
        calls = (len(owner.packets), len(owner.task.calls), len(owner.reviewed), len(owner.authored))
        with self._no_actions(owner):
            result = replay.replay_completed(owner.bound, closure)
        self.assertEqual(result, owner.outcome)
        self.assertEqual(driver_tests.tree(owner.root), before)
        self.assertEqual((len(owner.packets), len(owner.task.calls), len(owner.reviewed), len(owner.authored)), calls)
        self.assertFalse(result["result"]["claims"]["learning"])
        self.assertFalse(result["result"]["claims"]["live_RH_authorship"])
        return result

    def _refused_replay(self, owner, closure, *, episode=None):
        before = driver_tests.tree(owner.root)
        with self._no_actions(owner), self.assertRaises((ValueError, engine.driver.LoopHalted, OSError)):
            replay.replay_completed(owner.bound if episode is None else episode, closure)
        self.assertEqual(driver_tests.tree(owner.root), before)

    def _refused_seal(self, owner, *, outcome=None):
        before = driver_tests.tree(owner.root)
        with self.assertRaises((ValueError, engine.driver.LoopHalted, OSError)):
            replay.seal_completed_replay(owner.bound, owner.outcome if outcome is None else outcome,
                                         **self._bindings(owner))
        self.assertEqual(driver_tests.tree(owner.root), before)
        self.assertFalse((owner.root / "episode/completed-replay.json").exists())

    def test_completed_two_rounds_exact_outcome_with_no_reopened_owner(self):
        owner = self._fixture(runtime_alias=True)
        self._replay_unchanged(owner, self._seal(owner))

    def test_recorded_pending_parent_remains_valid_without_forced_adoption(self):
        owner = self._fixture(mode="pending")
        snapshot = json.loads((owner.root / "batch/batch.json").read_bytes())
        self.assertEqual(snapshot["micro_evolution"]["pending"]["candidate_id"], "retained-pending-child")
        self.assertEqual(snapshot["micro_evolution"]["active_pair"], adapter.activation.pair(owner.native.before))
        self.assertTrue(all(row["status"] == "completed" for row in snapshot["capacity_work"]))
        self._replay_unchanged(owner, self._seal(owner))

    def test_rejected_inactive_child_loss_is_distinct_from_bound_selected_loss(self):
        owner = self._fixture(mode="rejected")
        closure = self._seal(owner)
        for name in ("researcher_v2.py", "harness_v2.py"):
            (owner.root / name).rename(owner.root / ("retained-inactive-" + name))
        self._replay_unchanged(owner, closure)
        (owner.root / "researcher_v1.py").rename(owner.root / "retained-selected-researcher.py")
        self._refused_replay(owner, closure)

    def test_native_complete_ahead_of_unsealed_driver_never_becomes_complete(self):
        owner = self._fixture()
        snapshot = json.loads((owner.root / "batch/batch.json").read_bytes())
        self.assertTrue(all(row["status"] == "completed" for row in snapshot["capacity_work"]))
        binding = owner.root / "episode/loop/round-0002-execute.done.binding.json"
        binding.rename(owner.root / "retained-unsealed-execute.binding.json")
        self._refused_seal(owner)

    def test_native_snapshot_prefix_temporary_busy_or_extra_journal_is_not_recovered(self):
        for fault in ("snapshot-prefix", "pending-publication", "busy", "journal-after-closure"):
            with self.subTest(fault=fault):
                owner = self._fixture(mode="continue")
                if fault == "journal-after-closure": closure = self._seal(owner)
                if fault == "snapshot-prefix":
                    path = owner.root / "batch/batch.json"
                    path.rename(owner.root / "retained-current-batch.json")
                    path.write_bytes(owner.initial_snapshot_bytes)
                elif fault == "pending-publication":
                    (owner.root / "batch/journal/.pending-fixture.json").write_bytes(b"retained uncertain publication\n")
                else:
                    snapshot = owner.native.batch.snapshot()
                    owner.native.batch.record_capacity_work("claim", work_id="fresh-fixture-unclosed-work",
                        pair_sha256=digest(snapshot["micro_evolution"]["active_pair"]), evidence_sha256="b" * 64,
                        expected_state_sha256=snapshot["state_sha256"])
                if fault == "journal-after-closure":
                    self._refused_replay(owner, closure)
                else:
                    # Raw validation must not silently repair or recover while sealing either.
                    with patch.object(ContinuousDiscoveryBatch, "__init__", side_effect=AssertionError("Native ctor")), \
                         patch.object(ContinuousDiscoveryBatch, "snapshot", side_effect=AssertionError("Native snapshot")), \
                         patch.object(ContinuousDiscoveryBatch, "_load_locked", side_effect=AssertionError("Native load")), \
                         patch.object(ContinuousDiscoveryBatch, "_recover_pending_journal", side_effect=AssertionError("Native recovery")):
                        self._refused_seal(owner)

    def test_episode_closure_result_and_selected_pins_cannot_be_substituted(self):
        owner = self._fixture()
        self._refused_seal(owner, outcome=dict(owner.outcome, completed_rounds=1))
        closure = self._seal(owner)
        self._refused_replay(owner, dict(closure, sha256="c" * 64))
        self._refused_replay(owner, closure, episode=dict(owner.bound, sha256="c" * 64))
        path = owner.root / "versions" / (owner.outcome["result"]["pair_sha256"] + ".json")
        path.rename(owner.root / "retained-selected-version.json")
        path.write_bytes(b"{}\n")
        self._refused_replay(owner, closure)

    def test_initial_seal_binds_all_protected_identity_to_retained_anchor(self):
        for field in ("M", "K", "C", "memory", "runtime"):
            with self.subTest(field=field):
                owner = self._fixture()
                path = owner.root / "versions" / (owner.outcome["result"]["pair_sha256"] + ".json")
                selected = engine.read(engine.pin(path))
                original = selected["manifest"]
                args = {"kernel": deepcopy(original["components"]["K"]),
                    "predictor": deepcopy(original["components"]["C"]),
                    "harness": deepcopy(original["components"]["H"]),
                    "researcher": deepcopy(original["components"]["R"]),
                    "model": deepcopy(original["model"]), "memory": original["memory_sha256"],
                    "runtime": deepcopy(original["runtime"])}
                if field == "M":
                    args["model"]["requested_model"] = "different-owned-fixture-model"
                elif field in {"K", "C"}:
                    name = "substituted-" + field.lower() + ".py"
                    (owner.root / name).write_bytes(b"pass  # Owned negative-fixture substitution\n")
                    args["kernel" if field == "K" else "predictor"]["sources"] = {
                        name: engine.driver.c.sha(owner.root / name)}
                elif field == "memory":
                    args["memory"] = "c" * 64
                else:
                    substitute = owner.root / "substituted-runtime-python"
                    substitute.write_bytes(b"Owned negative fixture; never executed\n")
                    args["runtime"]["python"] = engine.pin(substitute)
                changed = adapter.identity.manifest(**args)
                self.assertEqual(adapter.activation.pair(changed), adapter.activation.pair(original))
                self.assertNotEqual(changed, original)
                selected["manifest"] = changed
                # Keep every supplied artifact internally valid to isolate the
                # retained protected-context mismatch, not a stale hash/type.
                selected["static_review"] = owner.native.artifact({"passed": True,
                    "reviewer_id": "independent-auditor", "proposer_id": "fixture-author",
                    "identity_sha256": digest(changed), "entrypoints": selected["entrypoints"]})
                path.rename(owner.root / ("retained-protected-selected-" + field + ".json"))
                engine.driver.c.save(path, selected)
                with patch.object(ContinuousDiscoveryBatch, "__init__", side_effect=AssertionError("Native ctor")), \
                     patch.object(ContinuousDiscoveryBatch, "snapshot", side_effect=AssertionError("Native snapshot")), \
                     patch.object(ContinuousDiscoveryBatch, "_load_locked", side_effect=AssertionError("Native load")), \
                     patch.object(ContinuousDiscoveryBatch, "_recover_pending_journal", side_effect=AssertionError("Native recovery")):
                    self._refused_seal(owner)


if __name__ == "__main__":
    unittest.main()
