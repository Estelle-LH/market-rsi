from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import pickle
import sys
import tempfile
import unittest
from unittest import mock


RESEARCH_ROOT = Path(__file__).resolve().parents[1]
if str(RESEARCH_ROOT) not in sys.path:
    sys.path.insert(0, str(RESEARCH_ROOT))

from pmb_simple_lane.artifact_store import (  # noqa: E402
    ArtifactIntegrityError,
    ArtifactStore,
    canonical_json_bytes,
)
from pmb_simple_lane.episode_lease import EpisodeLease  # noqa: E402


class ArtifactStoreTests(unittest.TestCase):
    def make_store(self, directory: str) -> ArtifactStore:
        return ArtifactStore(Path(directory).resolve() / "store", allow_temporary=True)

    def test_temporary_root_requires_explicit_test_allowance(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "temporary"):
                ArtifactStore(Path(directory).resolve() / "store")
            self.make_store(directory)

    def test_exclusive_create_canonical_read_and_mutation_detection(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            receipt = store.write_json_once("artifacts/result.json", {"z": 1, "a": [2]})
            self.assertEqual(store.read_json_verified(receipt), {"a": [2], "z": 1})
            self.assertEqual(
                (store.root / receipt["path"]).read_bytes(),
                canonical_json_bytes({"a": [2], "z": 1}),
            )
            with self.assertRaises(FileExistsError):
                store.write_json_once("artifacts/result.json", {"different": True})
            (store.root / receipt["path"]).write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ArtifactIntegrityError, "length|SHA-256"):
                store.read_json_verified(receipt)

    def test_path_escape_and_symlink_ancestor_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            for path in ("../escape.json", "/absolute.json", "a/../../escape.json"):
                with self.subTest(path=path), self.assertRaisesRegex(ValueError, "inside"):
                    store.write_json_once(path, {})
            outside = Path(directory).resolve() / "outside"
            outside.mkdir()
            os.symlink(outside, store.root / "linked")
            with self.assertRaises(OSError):
                store.write_json_once("linked/escape.json", {})
            self.assertFalse((outside / "escape.json").exists())

    def test_hash_chained_journal_rejects_mutation_and_extra_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            first = store.append_journal("events", {"kind": "one"})
            second = store.append_journal("events", {"kind": "two"})
            replay = store.verify_journal("events", expected_head=second["head_sha256"])
            self.assertEqual(replay["length"], 2)
            self.assertEqual(replay["entries"][1]["previous_sha256"], first["head_sha256"])

            path = store.root / "journals/events/00000000.json"
            record = json.loads(path.read_text(encoding="utf-8"))
            record["event"] = {"kind": "tampered"}
            path.write_bytes(canonical_json_bytes(record))
            with self.assertRaisesRegex(ArtifactIntegrityError, "hash chain"):
                store.verify_journal("events")

        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            store.append_journal("events", {"kind": "one"})
            (store.root / "journals/events/unexpected.txt").write_text("x", encoding="utf-8")
            with self.assertRaisesRegex(ArtifactIntegrityError, "gap|unexpected"):
                store.verify_journal("events")


class EpisodeLeaseTests(unittest.TestCase):
    def make_store(self, directory: str) -> ArtifactStore:
        return ArtifactStore(Path(directory).resolve() / "store", allow_temporary=True)

    def start(self, store: ArtifactStore, lease_id: str = "episode-001") -> EpisodeLease:
        lease = EpisodeLease.create(store, lease_id, registration={"spec_sha256": "a" * 64})
        lease.capture_start_snapshot({"source_sha256": "b" * 64})
        return lease

    def consume_task(self, lease: EpisodeLease, slot: int) -> None:
        lease.record_task(
            slot,
            intent={"hypothesis": f"h{slot}"},
            task={"task_id": f"task-{slot}"},
            observation={"status": "completed"},
        )

    def store_snapshot(self, store: ArtifactStore) -> tuple[tuple[str, str], ...]:
        return tuple(
            sorted(
                (
                    path.relative_to(store.root).as_posix(),
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                )
                for path in store.root.rglob("*")
                if path.is_file()
            )
        )

    def assert_rejected_without_write(self, stores, attempt) -> None:
        before = tuple(self.store_snapshot(store) for store in stores)
        with self.assertRaises((ValueError, ArtifactIntegrityError)):
            attempt()
        after = tuple(self.store_snapshot(store) for store in stores)
        self.assertEqual(after, before)

    def test_full_five_slot_lifecycle_closes_and_cannot_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            lease = self.start(store)
            for slot in range(1, 5):
                self.consume_task(lease, slot)
            self.assertEqual(lease.next_slot, 5)
            lease.synthesize_and_freeze(
                synthesis={"conclusion": "freeze"},
                candidate={"candidate_sha256": "c" * 64},
            )
            self.assertEqual(lease.state, "candidate_frozen")
            lease.begin_terminal_review({"reviewer": "independent"})
            lease.close(
                "passed",
                review={"decision": "PASS"},
                end_snapshot={"cleanup": "complete"},
            )
            inspected = EpisodeLease.inspect(store, "episode-001")
            self.assertEqual(inspected["state"], "closed_passed")
            self.assertEqual(inspected["restart_disposition"], "terminal_read_only")
            with self.assertRaises(FileExistsError):
                EpisodeLease.create(store, "episode-001", registration={"retry": True})
            with self.assertRaisesRegex(ValueError, "terminal|pending"):
                lease.close("passed", review={}, end_snapshot={})

    def test_early_stop_skips_to_forced_slot_five_and_no_task_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            lease = self.start(store)
            self.consume_task(lease, 1)
            lease.stop_early(2, intent={"decision": "enough"}, reason="support absent")
            self.assertEqual(lease.next_slot, 5)
            with self.assertRaisesRegex(ValueError, "out of sequence|consumed"):
                self.consume_task(lease, 3)
            lease.synthesize_and_freeze(synthesis={"result": "stop"}, candidate={"hash": "d" * 64})
            slot_five = next(
                event["event"]
                for event in store.verify_journal("episode-lease.episode-001")["entries"]
                if event["event"]["event"] == "slot_5_synthesis"
            )
            payload = store.read_json_verified(slot_five["artifacts"][0])
            self.assertEqual(payload["slot"], 5)
            self.assertEqual(payload["decision"], "synthesize")
            self.assertIsNone(payload["task"])
            self.assertIsNone(payload["observation"])

    def test_slot_five_and_terminal_transitions_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            lease = self.start(store)
            with self.assertRaisesRegex(ValueError, "slot 5"):
                lease.synthesize_and_freeze(synthesis={}, candidate={})
            with self.assertRaisesRegex(ValueError, "frozen"):
                lease.begin_terminal_review({})
            with self.assertRaisesRegex(ValueError, "pending"):
                lease.close("passed", review={}, end_snapshot={})
            with self.assertRaisesRegex(ValueError, "out of sequence"):
                self.consume_task(lease, 2)

    def test_only_one_active_lease_and_restart_can_only_mark_unresolved(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            self.start(store, "episode-active")
            with self.assertRaisesRegex(ValueError, "another episode"):
                EpisodeLease.create(store, "episode-blocked", registration={})
            inspection = EpisodeLease.inspect(store, "episode-active")
            self.assertEqual(inspection["restart_disposition"], "mark_unresolved_only")
            closed = EpisodeLease.mark_interrupted_unresolved(
                store, "episode-active", reason="owner process disappeared"
            )
            self.assertEqual(closed["state"], "unresolved")
            with self.assertRaisesRegex(ValueError, "exact active|terminal"):
                EpisodeLease.mark_interrupted_unresolved(
                    store, "episode-active", reason="retry"
                )
            fresh = EpisodeLease.create(store, "episode-fresh", registration={})
            self.assertEqual(fresh.state, "registered")

    def test_directly_reconstructed_handle_cannot_advance_any_transition(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            live = EpisodeLease.create(
                store,
                "episode-reconstructed",
                registration={"spec_sha256": "a" * 64},
            )
            reconstructed = EpisodeLease(store, "episode-reconstructed")

            transitions = (
                lambda: reconstructed.capture_start_snapshot(
                    {"source_sha256": "b" * 64}
                ),
                lambda: reconstructed.record_task(
                    1,
                    intent={},
                    task={},
                    observation={},
                ),
                lambda: reconstructed.stop_early(1, intent={}, reason="stop"),
                lambda: reconstructed.synthesize_and_freeze(
                    synthesis={}, candidate={}
                ),
                lambda: reconstructed.begin_terminal_review({}),
                lambda: reconstructed.close(
                    "passed", review={}, end_snapshot={}
                ),
                lambda: reconstructed.mark_unresolved(reason="not an owner"),
            )
            for transition in transitions:
                with self.subTest(transition=transition), self.assertRaisesRegex(
                    ValueError, "reconstructed lease handle cannot advance"
                ):
                    transition()

            self.assertEqual(EpisodeLease.inspect(store, live.lease_id)["state"], "registered")
            self.assertFalse((store.root / "leases/episode-reconstructed").exists())

            closed = EpisodeLease.mark_interrupted_unresolved(
                store,
                live.lease_id,
                reason="discard the reconstructed handle",
            )
            self.assertEqual(closed["state"], "unresolved")
            with self.assertRaisesRegex(ValueError, "exact active"):
                EpisodeLease.mark_interrupted_unresolved(
                    store,
                    live.lease_id,
                    reason="must not close twice",
                )

    def test_live_owner_snapshot_rejects_every_mutable_identity_and_state_field(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            other_store = ArtifactStore(
                Path(directory).resolve() / "other-store", allow_temporary=True
            )
            lease = self.start(store, "episode-owner-snapshot")
            mutations = (
                ("store", other_store),
                ("lease_id", "retargeted-lease"),
                ("journal_name", "episode-lease.retargeted-lease"),
                ("_state", "registered"),
                ("_head", "0" * 64),
                ("_next_slot", 4),
                ("_early_stopped", True),
            )
            for attribute, replacement in mutations:
                original = getattr(lease, attribute)
                setattr(lease, attribute, replacement)
                try:
                    with self.subTest(attribute=attribute):
                        self.assert_rejected_without_write(
                            (store, other_store),
                            lambda: self.consume_task(lease, 1),
                        )
                finally:
                    setattr(lease, attribute, original)

            original_root_identity = store._root_identity
            store._root_identity = (
                original_root_identity[0],
                original_root_identity[1] + 1,
            )
            try:
                self.assert_rejected_without_write(
                    (store, other_store), lambda: self.consume_task(lease, 1)
                )
            finally:
                store._root_identity = original_root_identity

            self.consume_task(lease, 1)
            self.assertEqual(lease.state, "running_round_1")

    def test_revoked_stale_owner_cannot_retarget_same_or_different_store_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            first_store = self.make_store(directory)
            stale = self.start(first_store, "episode-stale-owner")
            EpisodeLease.mark_interrupted_unresolved(
                first_store,
                "episode-stale-owner",
                reason="revoke the original live owner",
            )
            same_store_target = EpisodeLease.create(
                first_store,
                "episode-same-store-target",
                registration={"spec_sha256": "c" * 64},
            )

            stale.store = first_store
            stale.lease_id = same_store_target.lease_id
            stale.journal_name = same_store_target.journal_name
            stale._state = same_store_target._state
            stale._head = same_store_target._head
            stale._next_slot = same_store_target._next_slot
            stale._early_stopped = same_store_target._early_stopped
            self.assert_rejected_without_write(
                (first_store,),
                lambda: stale.capture_start_snapshot({"forged": "same-store"}),
            )

            second_store = ArtifactStore(
                Path(directory).resolve() / "second-store", allow_temporary=True
            )
            different_store_target = EpisodeLease.create(
                second_store,
                "episode-different-store-target",
                registration={"spec_sha256": "d" * 64},
            )
            stale.store = second_store
            stale.lease_id = different_store_target.lease_id
            stale.journal_name = different_store_target.journal_name
            stale._state = different_store_target._state
            stale._head = different_store_target._head
            stale._next_slot = different_store_target._next_slot
            stale._early_stopped = different_store_target._early_stopped
            self.assert_rejected_without_write(
                (first_store, second_store),
                lambda: stale.capture_start_snapshot({"forged": "different-store"}),
            )

    def test_copy_pickle_object_new_and_constructor_handles_never_write(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            live = EpisodeLease.create(
                store,
                "episode-handle-copies",
                registration={"spec_sha256": "e" * 64},
            )
            object_new = object.__new__(EpisodeLease)
            for attribute in (
                "store",
                "lease_id",
                "journal_name",
                "_state",
                "_head",
                "_next_slot",
                "_early_stopped",
            ):
                setattr(object_new, attribute, getattr(live, attribute))
            replicas = (
                copy.copy(live),
                copy.deepcopy(live),
                pickle.loads(pickle.dumps(live)),
                EpisodeLease(store, live.lease_id),
                object_new,
            )
            for replica in replicas:
                with self.subTest(replica=type(replica).__name__):
                    self.assert_rejected_without_write(
                        (store,),
                        lambda replica=replica: replica.capture_start_snapshot(
                            {"forged": True}
                        ),
                    )

            live.capture_start_snapshot({"authentic": True})
            self.assertEqual(live.state, "start_snapshotted")

    def test_registration_claim_drift_fails_before_transition_write(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            lease = EpisodeLease.create(
                store,
                "episode-claim-drift",
                registration={"spec_sha256": "f" * 64},
            )
            claim = store.root / "lease_ids/episode-claim-drift.json"
            claim.write_text("{}\n", encoding="utf-8")
            self.assert_rejected_without_write(
                (store,),
                lambda: lease.capture_start_snapshot({"must_not_write": True}),
            )

    def test_registration_only_crash_window_closes_unresolved_exactly_once(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            append_journal = store.append_journal

            def crash_before_registration(name, event):
                if name == "episode-lease.episode-registration-crash":
                    raise RuntimeError("simulated crash before lease registration")
                return append_journal(name, event)

            with mock.patch.object(
                store, "append_journal", side_effect=crash_before_registration
            ):
                with self.assertRaisesRegex(RuntimeError, "simulated crash"):
                    EpisodeLease.create(
                        store,
                        "episode-registration-crash",
                        registration={"spec_sha256": "a" * 64},
                    )

            self.assertEqual(
                store.verify_journal("episode-lease.episode-registration-crash")["length"],
                0,
            )
            self.assertEqual(
                EpisodeLease._validate_registry(store)["active_lease_id"],
                "episode-registration-crash",
            )

            closed = EpisodeLease.mark_interrupted_unresolved(
                store,
                "episode-registration-crash",
                reason="owner crashed after durable claim",
            )
            self.assertEqual(closed["state"], "unresolved")
            self.assertEqual(closed["restart_disposition"], "terminal_read_only")
            lease_events = store.verify_journal(
                "episode-lease.episode-registration-crash"
            )["entries"]
            self.assertEqual(
                [record["event"]["state"] for record in lease_events],
                ["registered", "unresolved"],
            )
            registry_events = store.verify_journal("episode-lease-registry")["entries"]
            self.assertEqual(
                [record["event"]["event"] for record in registry_events],
                ["claimed", "terminal"],
            )
            with self.assertRaisesRegex(ValueError, "exact active"):
                EpisodeLease.mark_interrupted_unresolved(
                    store,
                    "episode-registration-crash",
                    reason="must not close twice",
                )

    def test_artifact_mutation_and_orphan_file_block_lifecycle(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            lease = self.start(store)
            start = store.root / "leases/episode-001/start_snapshot.json"
            start.write_text("{}\n", encoding="utf-8")
            with self.assertRaises(ArtifactIntegrityError):
                self.consume_task(lease, 1)

        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            lease = self.start(store)
            orphan = store.root / "leases/episode-001/orphan.json"
            orphan.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ArtifactIntegrityError, "orphaned"):
                self.consume_task(lease, 1)
            recovered = EpisodeLease.mark_interrupted_unresolved(
                store, "episode-001", reason="crash after artifact write"
            )
            self.assertEqual(recovered["state"], "unresolved")
            self.assertEqual(recovered["orphan_paths"], [])


if __name__ == "__main__":
    unittest.main()
