import base64
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

import bundle_io


def encode_bundle(manifest, payload):
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    raw = json.dumps({"manifest": manifest, "payload": payload}).encode()
    return raw, hashlib.sha256(canonical).hexdigest()


def make_bundle(entries=None):
    if entries is None:
        entries = [("alpha.txt", b"synthetic\n")]
    manifest = [
        {"path": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        for name, data in entries
    ]
    payload = {name: base64.b64encode(data).decode("ascii") for name, data in entries}
    return encode_bundle(manifest, payload)


class BundleIOTests(unittest.TestCase):
    def setUp(self):
        workspace = Path(__file__).resolve().parent
        self.temp = tempfile.TemporaryDirectory(prefix="bundle-test-", dir=workspace)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode), 0o700)
        self.raw, self.pin = make_bundle()
        self.destination = self.root / "installed"

    def test_validate_synthetic_bytes(self):
        entries = [("alpha.txt", b"synthetic\n"), ("nested/beta.bin", b"\x00\xff")]
        raw, pin = make_bundle(entries)
        self.assertEqual(bundle_io.validate(raw, pin), dict(entries))

    def test_reject_payload_digest_tampering(self):
        document = json.loads(self.raw)
        document["payload"]["alpha.txt"] = base64.b64encode(b"tampered!\n").decode()
        with self.assertRaisesRegex(ValueError, "payload size or digest mismatch"):
            bundle_io.validate(json.dumps(document).encode(), self.pin)

    def test_reject_pinned_size_mismatch(self):
        document = json.loads(self.raw)
        document["manifest"][0]["size"] += 1
        raw, pin = encode_bundle(document["manifest"], document["payload"])
        with self.assertRaisesRegex(ValueError, "payload size or digest mismatch"):
            bundle_io.validate(raw, pin)

    def test_external_pin_blocks_replaced_allowlist(self):
        replacement, replacement_pin = make_bundle([("untrusted.txt", b"other")])
        self.assertNotEqual(replacement_pin, self.pin)
        with self.assertRaisesRegex(ValueError, "manifest pin mismatch"):
            bundle_io.validate(replacement, self.pin)

    def test_external_pin_blocks_added_manifest_entry(self):
        replacement, _ = make_bundle([
            ("alpha.txt", b"synthetic\n"), ("extra.txt", b"extra")
        ])
        with self.assertRaisesRegex(ValueError, "manifest pin mismatch"):
            bundle_io.validate(replacement, self.pin)

    def test_reject_missing_or_invalid_pin(self):
        for pin in (None, "", "A" * 64, "0" * 64):
            with self.subTest(pin=pin), self.assertRaises(ValueError):
                bundle_io.validate(self.raw, pin)

    def test_reject_added_payload(self):
        document = json.loads(self.raw)
        document["payload"]["extra.txt"] = "ZXh0cmE="
        with self.assertRaisesRegex(ValueError, "payload does not match allowlist"):
            bundle_io.validate(json.dumps(document).encode(), self.pin)

    def test_reject_missing_payload(self):
        document = json.loads(self.raw)
        del document["payload"]["alpha.txt"]
        with self.assertRaisesRegex(ValueError, "payload encoding or size"):
            bundle_io.validate(json.dumps(document).encode(), self.pin)

    def test_reject_malformed_json(self):
        for raw in (b"{", b"{} []", b"\xff"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                bundle_io.validate(raw, self.pin)

    def test_reject_duplicate_json_at_all_levels(self):
        cases = (
            b'{"manifest":[],"manifest":[],"payload":{}}',
            b'{"manifest":[{"path":"a","path":"b"}],"payload":{}}',
            b'{"manifest":[],"payload":{"a":"YQ==","a":"Yg=="}}',
        )
        for raw in cases:
            with self.subTest(raw=raw):
                with self.assertRaisesRegex(ValueError, "duplicate JSON field"):
                    bundle_io.validate(raw, self.pin)

    def test_reject_invalid_base64(self):
        document = json.loads(self.raw)
        document["payload"]["alpha.txt"] = "not base64!"
        with self.assertRaises(ValueError):
            bundle_io.validate(json.dumps(document).encode(), self.pin)

    def test_reject_noncanonical_payload_paths(self):
        names = (
            "../escape", "a/../escape", "a/./file", "a//file", "/absolute",
            "C:/absolute", "trailing/", "./dot", ".hidden", "BUNDLE_COMPLETE.json",
        )
        for name in names:
            with self.subTest(name=name):
                raw, pin = make_bundle([(name, b"data")])
                with self.assertRaises(ValueError):
                    bundle_io.validate(raw, pin)

    def test_reject_duplicate_manifest_path(self):
        raw, pin = make_bundle([("same", b"a"), ("same", b"a")])
        with self.assertRaisesRegex(ValueError, "duplicate manifest path"):
            bundle_io.validate(raw, pin)

    def test_reject_file_directory_collision_in_either_order(self):
        entries = [("node", b"a"), ("node/child", b"b")]
        for ordered in (entries, list(reversed(entries))):
            with self.subTest(ordered=ordered):
                raw, pin = make_bundle(ordered)
                with self.assertRaisesRegex(ValueError, "file/directory path collision"):
                    bundle_io.validate(raw, pin)

    def test_reject_completion_record_directory_collision(self):
        raw, pin = make_bundle([("BUNDLE_COMPLETE.json/child", b"data")])
        with self.assertRaises(ValueError):
            bundle_io.validate(raw, pin)

    def test_install_canonical_absolute_destination(self):
        entries = [("alpha.txt", b"synthetic\n"), ("nested/beta.bin", b"\x00\xff")]
        raw, pin = make_bundle(entries)
        receipt = bundle_io.install(raw, pin, str(self.destination))
        self.assertEqual(stat.S_IMODE(self.destination.stat().st_mode), 0o700)
        for name, content in entries:
            path = self.destination / name
            self.assertEqual(path.read_bytes(), content)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
        self.assertEqual(receipt, {
            "schema": "ordinary-file-bundle-v1", "manifest_sha256": pin,
            "files": 2, "bytes": sum(len(data) for _, data in entries),
            "payload_executed": False, "workload_admission": False,
        })
        marker = self.destination / "BUNDLE_COMPLETE.json"
        self.assertEqual(json.loads(marker.read_bytes()), receipt)

    def test_invalid_bundle_makes_no_destination(self):
        document = json.loads(self.raw)
        document["payload"]["extra.txt"] = "ZXh0cmE="
        with self.assertRaises(ValueError):
            bundle_io.install(json.dumps(document).encode(), self.pin, self.destination)
        self.assertFalse(self.destination.exists())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_reject_relative_destination(self):
        relative = os.path.relpath(self.destination)
        with self.assertRaises(ValueError):
            bundle_io.install(self.raw, self.pin, relative)
        self.assertFalse(self.destination.exists())

    def test_reject_dot_in_destination_parent_spelling(self):
        destination = str(self.root) + "/./installed"
        with self.assertRaises(ValueError):
            bundle_io.install(self.raw, self.pin, destination)
        self.assertFalse(self.destination.exists())

    def test_reject_dot_at_destination_end(self):
        with self.assertRaises(ValueError):
            bundle_io.install(self.raw, self.pin, str(self.destination) + "/.")
        self.assertFalse(self.destination.exists())

    def test_reject_repeated_destination_separator(self):
        destination = str(self.root) + "//installed"
        with self.assertRaises(ValueError):
            bundle_io.install(self.raw, self.pin, destination)
        self.assertFalse(self.destination.exists())

    def test_reject_dotdot_in_destination_spelling(self):
        anchor = self.root / "anchor"
        anchor.mkdir(mode=0o700)
        destination = str(anchor) + "/../installed"
        with self.assertRaises(ValueError):
            bundle_io.install(self.raw, self.pin, destination)
        self.assertFalse(self.destination.exists())

    def test_existing_destination_is_untouched(self):
        self.destination.mkdir(mode=0o700)
        sentinel = self.destination / "sentinel"
        sentinel.write_bytes(b"keep")
        with self.assertRaises(FileExistsError):
            bundle_io.install(self.raw, self.pin, self.destination)
        self.assertEqual(sentinel.read_bytes(), b"keep")
        self.assertEqual(list(self.destination.iterdir()), [sentinel])

    def test_existing_symlink_destination_is_untouched(self):
        target = self.root / "target"
        target.mkdir(mode=0o700)
        self.destination.symlink_to(target, target_is_directory=True)
        with self.assertRaises(FileExistsError):
            bundle_io.install(self.raw, self.pin, self.destination)
        self.assertTrue(self.destination.is_symlink())
        self.assertEqual(list(target.iterdir()), [])

    def test_reject_symlink_parent(self):
        target = self.root / "parent"
        target.mkdir(mode=0o700)
        link = self.root / "linked-parent"
        link.symlink_to(target, target_is_directory=True)
        with self.assertRaises(ValueError):
            bundle_io.install(self.raw, self.pin, link / "installed")
        self.assertEqual(list(target.iterdir()), [])

    def test_failed_payload_sync_stays_incomplete_and_cannot_resume(self):
        with mock.patch.object(bundle_io.os, "fsync", side_effect=OSError("payload sync failed")):
            with self.assertRaisesRegex(OSError, "payload sync failed"):
                bundle_io.install(self.raw, self.pin, self.destination)
        self.assertTrue(self.destination.is_dir())
        self.assertFalse((self.destination / "BUNDLE_COMPLETE.json").exists())
        with self.assertRaises(FileExistsError):
            bundle_io.install(self.raw, self.pin, self.destination)

    def test_failed_directory_sync_has_no_completion_record(self):
        with mock.patch.object(bundle_io, "_sync_dir", side_effect=OSError("directory sync failed")):
            with self.assertRaisesRegex(OSError, "directory sync failed"):
                bundle_io.install(self.raw, self.pin, self.destination)
        self.assertTrue((self.destination / "alpha.txt").is_file())
        self.assertFalse((self.destination / "BUNDLE_COMPLETE.json").exists())

    def test_partial_receipt_write_has_no_completion_record(self):
        def partial_write(receipt, stream, **kwargs):
            stream.write("{")
            raise OSError("receipt write failed")

        with mock.patch.object(bundle_io.json, "dump", side_effect=partial_write):
            with self.assertRaisesRegex(OSError, "receipt write failed"):
                bundle_io.install(self.raw, self.pin, self.destination)
        self.assertFalse((self.destination / "BUNDLE_COMPLETE.json").exists())

    def test_failed_receipt_sync_has_no_completion_record(self):
        real_fsync = bundle_io.os.fsync
        regular_files = 0

        def fail_receipt_sync(fd):
            nonlocal regular_files
            if stat.S_ISREG(os.fstat(fd).st_mode):
                regular_files += 1
                if regular_files == 2:
                    raise OSError("receipt sync failed")
            return real_fsync(fd)

        with mock.patch.object(bundle_io.os, "fsync", side_effect=fail_receipt_sync):
            with self.assertRaisesRegex(OSError, "receipt sync failed"):
                bundle_io.install(self.raw, self.pin, self.destination)
        self.assertEqual(regular_files, 2)
        self.assertFalse((self.destination / "BUNDLE_COMPLETE.json").exists())

    def test_publication_link_failure_has_no_completion_record(self):
        completion = self.destination / "BUNDLE_COMPLETE.json"

        def fail_link(source, target):
            self.assertEqual(Path(source).parent, self.destination)
            self.assertEqual(Path(target), completion)
            self.assertFalse(completion.exists())
            receipt = json.loads(Path(source).read_bytes())
            self.assertEqual(receipt["manifest_sha256"], self.pin)
            raise OSError("receipt publication link failed")

        with mock.patch.object(bundle_io.os, "link", side_effect=fail_link) as link:
            with self.assertRaisesRegex(OSError, "receipt publication link failed"):
                bundle_io.install(self.raw, self.pin, self.destination)
        link.assert_called_once()
        self.assertEqual((self.destination / "alpha.txt").read_bytes(), b"synthetic\n")
        self.assertFalse(completion.exists())
        with self.assertRaises(FileExistsError):
            bundle_io.install(self.raw, self.pin, self.destination)

    def test_post_publication_parent_sync_failure_removes_completion_record(self):
        completion = self.destination / "BUNDLE_COMPLETE.json"
        real_sync_dir = bundle_io._sync_dir
        published_receipts = []

        def fail_parent_sync(directory):
            if Path(directory) == self.root and completion.exists():
                published_receipts.append(json.loads(completion.read_bytes()))
                raise OSError("post-publication parent sync failed")
            return real_sync_dir(directory)

        with mock.patch.object(bundle_io, "_sync_dir", side_effect=fail_parent_sync):
            with self.assertRaisesRegex(OSError, "post-publication parent sync failed"):
                bundle_io.install(self.raw, self.pin, self.destination)
        self.assertEqual(len(published_receipts), 1)
        self.assertEqual(published_receipts[0]["manifest_sha256"], self.pin)
        self.assertEqual((self.destination / "alpha.txt").read_bytes(), b"synthetic\n")
        self.assertFalse(completion.exists())
        with self.assertRaises(FileExistsError):
            bundle_io.install(self.raw, self.pin, self.destination)


if __name__ == "__main__":
    unittest.main()
