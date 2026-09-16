"""Isolated synthetic-fixture tests; never make an actual hydration request."""

import hashlib
import json
from pathlib import Path
import runpy
import stat
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


HELPER = runpy.run_path(str(Path(__file__).with_name("local_hydration.py")))
prepare = HELPER["prepare"]
request_batch = HELPER["request_batch"]
poll = HELPER["poll"]
foundation_requester = HELPER["foundation_requester"]


class LocalHydrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "source.py"
        self.source.write_bytes(b"unchanged source\n")
        self.prepared = self.root / "prepared"
        self.prepared.mkdir()
        self.snapshots = self.prepared / "source-snapshot"
        self.snapshots.mkdir()
        self.snapshot = self.snapshots / "source.py"
        self.snapshot.write_bytes(self.source.read_bytes())
        self.expected_hash = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.manifest = self.prepared / "preparation.json"
        self.manifest.write_text(json.dumps({"source_hashes": {"source.py": self.expected_hash}}))
        self.out = self.root / "audit-run"
        self.dataless = {self.source, self.snapshot}
        self.requester = Mock(side_effect=lambda paths, **kw: [
            {"path": p, "requestAccepted": True, "outcome": "accepted"} for p in paths])

    def metadata(self, path):
        path = Path(path)
        actual = path.lstat()
        return SimpleNamespace(st_mode=actual.st_mode, st_size=actual.st_size,
            st_mtime_ns=actual.st_mtime_ns, st_dev=actual.st_dev, st_ino=actual.st_ino,
            st_flags=0x40000000 if path in self.dataless else 0)

    def reader(self, row, limit):
        path = Path(row["path"])
        if path in self.dataless:
            raise AssertionError("must not read dataless selected inputs")
        content = path.read_bytes()
        self.assertLessEqual(len(content), limit)
        return {"text": content.decode(), "sha256": hashlib.sha256(content).hexdigest()}

    def plan(self, **kw):
        return prepare(self.root, self.manifest, self.out, lstat=self.metadata,
                       manifest_reader=self.reader, **kw)

    def request(self, plan, **kw):
        return request_batch(plan, self.out, requester=self.requester, lstat=self.metadata,
                             claim_reader=self.reader, **kw)

    def test_plan_counts_sources_snapshots_manifest_and_extra_once(self):
        receipt_dir = self.root / "receipts"
        receipt_dir.mkdir()
        receipt = receipt_dir / "receipt.json"
        receipt.write_text("{}")
        plan = self.plan(files=[receipt, self.source], directories=[receipt_dir])
        self.assertEqual(len(plan["files"]), 4)
        self.assertEqual(plan["total_selected_bytes"], sum(p.stat().st_size for p in
                         [self.source, self.snapshot, self.manifest, receipt]))
        sources = [r for r in plan["files"] if r["role"] in ("source", "snapshot")]
        self.assertEqual({r["expected_sha256"] for r in sources}, {self.expected_hash})
        self.assertTrue(all(r["status"] == "dataless" for r in sources))
        for path in (self.out / "claim.json", self.out / "plan.json"):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
        self.requester.assert_not_called()

    def test_cumulative_cap_includes_both_copies(self):
        cap = self.manifest.stat().st_size + self.source.stat().st_size
        with self.assertRaisesRegex(ValueError, "cumulative"):
            self.plan(max_bytes=cap)
        self.assertFalse(self.out.exists())

    def test_duplicate_run_directory_is_rejected_and_preserved(self):
        self.plan()
        before = (self.out / "plan.json").read_bytes()
        with self.assertRaises(FileExistsError):
            self.plan()
        self.assertEqual(before, (self.out / "plan.json").read_bytes())

    def test_malformed_or_external_paths_are_rejected(self):
        for value in ("../escape", str(self.root.parent / "outside"), "bad\x00path"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.plan(files=[value])
        self.assertFalse(self.out.exists())

    def test_manifest_parent_traversal_or_bad_hash_is_rejected(self):
        for name, expected in (("../source.py", self.expected_hash),
                               (str(self.source), self.expected_hash),
                               ("source.py", "not-a-hash")):
            self.manifest.write_text(json.dumps({"source_hashes": {name: expected}}))
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.plan()

    def test_symlink_file_and_ancestor_are_rejected(self):
        link = self.root / "link.py"
        link.symlink_to(self.source)
        linkdir = self.root / "linkdir"
        linkdir.symlink_to(self.prepared, target_is_directory=True)
        for value in (link, linkdir / "preparation.json"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "symlink"):
                self.plan(files=[value])

    def test_directory_children_are_nonrecursive_and_must_be_regular(self):
        with self.assertRaisesRegex(ValueError, "file type"):
            self.plan(directories=[self.prepared])
        with self.assertRaisesRegex(ValueError, "file type"):
            self.plan(files=[self.prepared])

    def test_dataless_manifest_never_read(self):
        self.dataless.add(self.manifest)
        with self.assertRaisesRegex(ValueError, "manifest must be resident"):
            self.plan()

    def test_unknown_residency_is_rejected(self):
        def missing_flags(path):
            metadata = self.metadata(path)
            del metadata.st_flags
            return metadata
        with self.assertRaisesRegex(ValueError, "residency flags unavailable"):
            prepare(self.root, self.manifest, self.out, lstat=missing_flags,
                    manifest_reader=self.reader)

    def test_selected_receipts_also_count_toward_cap(self):
        receipt = self.root / "receipt.json"
        receipt.write_text("{}")
        cap = sum(p.stat().st_size for p in [self.source, self.snapshot, self.manifest])
        with self.assertRaisesRegex(ValueError, "cumulative"):
            self.plan(max_bytes=cap, files=[receipt])

    def test_manifest_change_during_preparation_is_rejected(self):
        def changing_reader(row, limit):
            loaded = self.reader(row, limit)
            self.manifest.write_text(loaded["text"] + "\n")
            return loaded
        with self.assertRaisesRegex(ValueError, "manifest metadata changed"):
            prepare(self.root, self.manifest, self.out, lstat=self.metadata,
                    manifest_reader=changing_reader)

    def test_accepted_still_dataless_is_not_verified_or_downloaded(self):
        before = {p: p.read_bytes() for p in [self.source, self.snapshot, self.manifest]}
        plan = self.plan()
        report = self.request(plan)
        self.assertTrue(all(r["requestAccepted"] for r in report["requests"]))
        self.assertFalse(report["observation"]["all_resident_at_stat"])
        self.assertFalse(report["acceptance_is_residency_or_integrity"])
        self.assertFalse(report["observation"]["scientific_hashes_verified"])
        self.assertEqual(report["observation"]["content_bytes_read"], 0)
        self.assertEqual(before, {p: p.read_bytes() for p in before})
        paths = self.requester.call_args.args[0]
        self.assertEqual(set(paths), {str(self.source), str(self.snapshot)})
        self.assertEqual(self.requester.call_args.kwargs, {"timeout_seconds": 20})

    def test_becoming_resident_only_changes_metadata_status(self):
        plan = self.plan()
        self.dataless.clear()
        result = poll(plan, lstat=self.metadata)
        self.assertTrue(result["all_resident_at_stat"])
        self.assertFalse(result["scientific_hashes_verified"])
        self.request(plan)
        self.requester.assert_not_called()

    def test_duplicate_request_and_overlapping_batch_cannot_retry(self):
        plan = self.plan()
        self.request(plan, batch_size=1)
        with self.assertRaises(FileExistsError):
            self.request(plan, batch_size=2)
        self.assertEqual(self.requester.call_count, 1)

    def test_changed_plan_or_input_blocks_request(self):
        plan = self.plan()
        mutated = {**plan, "max_bytes": 999}
        with self.assertRaisesRegex(ValueError, "plan changed"):
            self.request(mutated)
        self.source.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "metadata changed"):
            self.request(plan)
        self.requester.assert_not_called()

    def test_symlink_swap_after_plan_blocks_request(self):
        plan = self.plan()
        self.source.unlink()
        self.source.symlink_to(self.snapshot)
        with self.assertRaisesRegex(ValueError, "metadata changed"):
            self.request(plan)
        self.requester.assert_not_called()

    def test_request_timeout_limit_enforced(self):
        plan = self.plan()
        for kwargs in ({"timeout_seconds": 21}, {"timeout_seconds": 0},
                       {"batch_size": 33}, {"batch_index": -1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.request(plan, **kwargs)
        self.requester.assert_not_called()

    def test_foundation_subprocess_is_independently_bounded_and_sanitized(self):
        path = str(self.source)
        runner = Mock(return_value=SimpleNamespace(returncode=0,
                      stdout=json.dumps([{"path": path, "requestAccepted": True}]),
                      stderr="must never be retained"))
        with patch.object(subprocess, "run", runner):
            result = foundation_requester([path])
        args, kwargs = runner.call_args
        self.assertEqual(args[0][:3], ["/usr/bin/osascript", "-l", "JavaScript"])
        self.assertEqual(kwargs["timeout"], 20)
        self.assertNotIn("must never", json.dumps(result))
        runner.side_effect = subprocess.TimeoutExpired("osascript", 20)
        with patch.object(subprocess, "run", runner):
            result = foundation_requester([path])
        self.assertIsNone(result[0]["requestAccepted"])
        self.assertEqual(result[0]["outcome"], "timeout_unknown")


if __name__ == "__main__":
    unittest.main()
