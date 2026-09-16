import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from collector_evidence import freeze_export, validate_export


class CollectorEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / "export"
        self.source.mkdir()
        files = {
            "collector.py": ("collector_source", b"import time\n# writes receive time\n"),
            "collector.service.txt": ("service_unit", b"[Service]\nExecStart=/opt/d10/collector.py\n"),
            "session.log": ("session_record", b"started reconnect snapshot sequence\n"),
            "capture-manifest.json": ("capture_manifest", b'{"files":24}\n'),
        }
        declared = []
        for name, (kind, raw) in files.items():
            (self.source / name).write_bytes(raw)
            declared.append({"name": name, "kind": kind, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
        self.manifest = {"schema": "market_collector_evidence_export_v1", "source_host": "173.255.234.236",
            "exported_at_utc": "2026-09-07T15:00:00Z", "files": declared, "notes": "fixture only"}
        (self.source / "manifest.json").write_text(json.dumps(self.manifest))

    def tearDown(self):
        self.tmp.cleanup()

    def save_manifest(self):
        (self.source / "manifest.json").write_text(json.dumps(self.manifest))

    def test_intake_preserves_bytes_but_does_not_admit_scoring(self):
        manifest, _, files = validate_export(self.source)
        self.assertEqual(manifest, self.manifest)
        self.assertEqual(set(files), {x["name"] for x in self.manifest["files"]})
        output = self.root / "frozen"
        freeze_export(self.source, output)
        receipt = json.loads((output / "intake-receipt.json").read_text())
        self.assertFalse(receipt["scientific_admission"])
        self.assertFalse(receipt["scoring_ready"])
        self.assertEqual((output / "source-manifest.json").read_text(),
                         (self.source / "manifest.json").read_text())

    def test_changed_file_is_rejected(self):
        (self.source / "collector.py").write_text("changed")
        with self.assertRaisesRegex(ValueError, "differ"):
            validate_export(self.source)

    def test_secret_like_filename_is_rejected(self):
        item = self.manifest["files"][0]
        old = self.source / item["name"]
        new = self.source / "api-key.txt"
        old.rename(new)
        item["name"] = new.name
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "secret-like"):
            validate_export(self.source)

    def test_secret_like_contents_are_rejected(self):
        raw = b"API_KEY=abcdefghijklmno\n"
        path = self.source / "session.log"
        path.write_bytes(raw)
        item = next(x for x in self.manifest["files"] if x["name"] == path.name)
        item.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "credential"):
            validate_export(self.source)

    def test_missing_evidence_kind_is_rejected(self):
        self.manifest["files"] = [x for x in self.manifest["files"] if x["kind"] != "session_record"]
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "all required"):
            validate_export(self.source)

    def test_symlink_is_rejected(self):
        path = self.source / "collector.py"
        path.unlink()
        path.symlink_to(self.source / "session.log")
        with self.assertRaisesRegex(ValueError, "non-symlink"):
            validate_export(self.source)

    def test_alternate_host_requires_an_explicit_exact_binding(self):
        self.manifest["source_host"] = "173.255.231.4"
        self.save_manifest()
        manifest, _, _ = validate_export(
            self.source, expected_source_host="173.255.231.4")
        self.assertEqual(manifest["source_host"], "173.255.231.4")
        with self.assertRaisesRegex(ValueError, "explicitly selected"):
            validate_export(self.source)


if __name__ == "__main__":
    unittest.main()
