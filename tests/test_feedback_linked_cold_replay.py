"""Completed-only driver verification; fresh owned records, zero callbacks."""
from contextlib import ExitStack, contextmanager
from copy import deepcopy
import fcntl
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from supervisor_harness import feedback_linked_loop as driver
from supervisor_harness import test_feedback_linked_loop as fixture


def tree(root):
    """Include bytes and identity metadata, so a same-byte rewrite is visible."""
    records = {}
    for path in [root, *sorted(root.rglob("*"))]:
        info = path.lstat()
        item = {"inode": info.st_ino, "mode": info.st_mode, "mtime_ns": info.st_mtime_ns}
        if path.is_symlink():
            item["symlink"] = str(path.readlink())
        elif path.is_file():
            item["bytes"] = path.read_bytes()
        records[str(path.relative_to(root))] = item
    return records


@contextmanager
def no_driver_actions():
    with ExitStack() as stack:
        for owner, name in ((driver, "run"), (driver, "_save_pair"), (driver.c, "save")):
            stack.enter_context(patch.object(owner, name,
                side_effect=AssertionError("Cold replay attempted " + name)))
        yield


class ColdDriverReplayTests(unittest.TestCase):
    def _fixture(self):
        owner = fixture.LoopTests()
        owner.setUp(); self.addCleanup(owner.doCleanups)
        source = owner.directory / "trusted-handler-source.txt"
        source.write_bytes(b"Human-authored synthetic handler provenance\n")
        source_binding = {"path": str(source), "sha256": driver.c.sha(source)}
        owner.identities = {stage: {"trusted_handler": stage, "version": 1,
            "source": source_binding} for stage in driver.STAGES}
        owner.outcome = owner.run_loop()
        owner.manifest = {"path": str(owner.root / "manifest.json"),
                          "sha256": driver.c.sha(owner.root / "manifest.json")}
        owner.source = source
        return owner

    def _refused(self, owner, *, root=None, binding=None):
        before = tree(owner.directory)
        calls = deepcopy(owner.calls)
        with no_driver_actions(), self.assertRaises((ValueError, driver.LoopHalted, OSError)):
            driver.replay_completed(owner.root if root is None else root,
                manifest_binding=owner.manifest if binding is None else binding)
        self.assertEqual(owner.calls, calls)
        self.assertEqual(tree(owner.directory), before)

    @staticmethod
    def _retain(owner, path):
        # Fault setup preserves the original outside the loop namespace.
        path.rename(owner.directory / ("retained-" + path.name))

    def test_two_rounds_exact_return_without_callbacks_or_writable_lock(self):
        owner = self._fixture()
        before, calls = tree(owner.directory), deepcopy(owner.calls)
        opened, locked = [], []
        original_open, original_flock = os.open, fcntl.flock
        def observe_open(path, flags, *args, **kwargs):
            if Path(path) == owner.root / ".loop.lock":
                opened.append(flags)
                self.assertEqual(flags & os.O_ACCMODE, os.O_RDONLY)
                self.assertFalse(flags & os.O_CREAT)
            return original_open(path, flags, *args, **kwargs)
        def observe_lock(fd, flags):
            locked.append(flags)
            return original_flock(fd, flags)
        with no_driver_actions(), patch.object(driver.os, "open", side_effect=observe_open), \
                patch.object(driver.fcntl, "flock", side_effect=observe_lock):
            outcome = driver.replay_completed(owner.root, manifest_binding=owner.manifest)
        self.assertEqual(outcome, owner.outcome)
        self.assertEqual(owner.calls, calls)
        self.assertEqual(tree(owner.directory), before)
        self.assertTrue(opened)
        self.assertIn(fcntl.LOCK_SH | fcntl.LOCK_NB, locked)

    def test_missing_failed_and_orphan_records_stop_without_action(self):
        for fault in ("manifest", "done", "done-binding", "failed", "claim", "extra-round", "lock"):
            with self.subTest(fault=fault):
                owner = self._fixture()
                prefix = owner.root / "round-0002-reconcile"
                if fault == "manifest": self._retain(owner, owner.root / "manifest.json")
                elif fault == "done": self._retain(owner, prefix.with_suffix(".done.json"))
                elif fault == "done-binding": self._retain(owner, prefix.with_suffix(".done.binding.json"))
                elif fault == "failed": driver.c.save(prefix.with_suffix(".failed.json"), {"retry_allowed": False})
                elif fault == "claim": self._retain(owner, prefix.with_suffix(".claim.json"))
                elif fault == "extra-round": driver.c.save(owner.root / "round-0003-input.claim.json", {"orphan": True})
                elif fault == "lock": self._retain(owner, owner.root / ".loop.lock")
                self._refused(owner)

    def test_nonexistent_root_is_not_created(self):
        owner = self._fixture()
        missing = owner.directory / "never-created"
        self._refused(owner, root=missing,
            binding={"path": str(missing / "manifest.json"), "sha256": "a" * 64})
        self.assertFalse(missing.exists())

    def test_lineage_and_local_done_reseal_cannot_substitute_feedback(self):
        for fault in ("feedback", "claim"):
            with self.subTest(fault=fault):
                owner = self._fixture()
                if fault == "feedback":
                    path = owner.root / "round-0002-input.done.json"
                    done = driver._read_pair(path)
                    done["output"]["feedback"]["forecast"] = 0.99
                    done["output_sha256"] = driver.c._digest(done["output"])
                    self._retain(owner, path)
                    self._retain(owner, path.with_suffix(".binding.json"))
                    driver._save_pair(path, done)  # A locally resealed, inconsistent synthetic record.
                else:
                    path = owner.root / "round-0002-controller.claim.json"
                    claim = driver.c._json(path.read_bytes())
                    claim["previous_feedback_sha256"] = "c" * 64
                    self._retain(owner, path); driver.c.save(path, claim)
                self._refused(owner)

    def test_manifest_external_source_and_artifact_pins_are_rechecked(self):
        owner = self._fixture()
        wrong = dict(owner.manifest, sha256="a" * 64)
        self._refused(owner, binding=wrong)
        owner.source.write_bytes(b"Changed owned synthetic handler source\n")
        self._refused(owner)
        owner = self._fixture()
        physical_source = Path(driver.__file__).resolve()
        original_sha = driver.c.sha
        with patch.object(driver.c, "sha", side_effect=lambda path:
                "a" * 64 if Path(path) == physical_source else original_sha(path)):
            self._refused(owner)

    def test_existing_lock_alias_and_exclusive_owner_are_refused(self):
        owner = self._fixture()
        fd = os.open(owner.root / ".loop.lock", os.O_RDONLY | os.O_NOFOLLOW)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._refused(owner)
        finally:
            os.close(fd)
        owner = self._fixture()
        target = owner.directory / "foreign.lock"; target.write_bytes(b"preserved foreign lock\n")
        self._retain(owner, owner.root / ".loop.lock")
        (owner.root / ".loop.lock").symlink_to(target)
        self._refused(owner)

    def test_closed_factual_negative_result_is_not_an_uncertain_stage(self):
        owner = fixture.LoopTests(); owner.setUp(); self.addCleanup(owner.doCleanups)
        owner.handlers["execute"] = lambda context: {"status": "failed", "error": "Recorded fit failure"}
        owner.handlers["reconcile"] = lambda context: context["outputs"]["execute"]
        outcome = owner.run_loop()
        binding = {"path": str(owner.root / "manifest.json"), "sha256": driver.c.sha(owner.root / "manifest.json")}
        before = tree(owner.directory)
        with no_driver_actions():
            self.assertEqual(driver.replay_completed(owner.root, manifest_binding=binding), outcome)
        self.assertEqual(outcome["result"]["status"], "failed")
        self.assertEqual(tree(owner.directory), before)


if __name__ == "__main__":
    unittest.main()
