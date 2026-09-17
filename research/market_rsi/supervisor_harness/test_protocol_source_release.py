"""Local Git-only publication tests; never pushes the user's repository."""
from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from market_rsi import digest
from supervisor_harness import protocol_source_release as release


def git(root, *args):
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                            text=True, timeout=10, check=False)
    if result.returncode:
        raise AssertionError(f"fixture Git failed: {args}: {result.stderr}")
    return result.stdout.strip()


class ProtocolPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name).resolve()
        self.repo = self.parent / "work"
        self.remote = self.parent / "user-fork.git"
        self.repo.mkdir()
        self.remote.mkdir()
        git(self.repo, "init", "-q")
        git(self.remote, "init", "-q", "--bare")
        git(self.repo, "config", "user.name", "Fixture")
        git(self.repo, "config", "user.email", "fixture@example.invalid")
        git(self.repo, "remote", "add", "origin", str(self.remote))
        self.file = self.repo / release.PREFIX / "one.py"
        self.file.parent.mkdir(parents=True)
        self.file.write_text("value = 1\n")
        git(self.repo, "add", "--", str(self.file.relative_to(self.repo)))
        git(self.repo, "commit", "-qm", "freeze fixture")
        self.tag = "market-rsi-protocol-v0.1.0"
        git(self.repo, "tag", "-a", self.tag, "-m", "fixture release")
        self.patches = [patch.object(release, "REPO", self.repo),
                        patch.object(release, "ORIGIN", str(self.remote)),
                        patch.object(release, "FILES", ("one.py",))]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def manifest(self):
        return digest(release.source_hashes())

    def test_requires_exact_annotated_tag_on_origin(self):
        expected = self.manifest()
        with self.assertRaisesRegex(ValueError, "Git publication check failed"):
            release.verify_published(tag=self.tag, expected_source_sha256=expected)
        git(self.repo, "push", "-q", "origin", self.tag)
        value = release.verify_published(tag=self.tag, expected_source_sha256=expected)
        self.assertEqual(value["source_sha256"], expected)
        self.assertFalse(value["isolation_proven"])

    def test_changed_runtime_source_is_not_released(self):
        git(self.repo, "push", "-q", "origin", self.tag)
        expected = self.manifest()
        self.file.write_text("value = 2\n")
        with self.assertRaisesRegex(ValueError, "current protocol source"):
            release.verify_published(tag=self.tag, expected_source_sha256=expected)

    def test_lightweight_tag_is_rejected(self):
        git(self.repo, "tag", "market-rsi-protocol-v0.1.1")
        git(self.repo, "push", "-q", "origin", "market-rsi-protocol-v0.1.1")
        with self.assertRaisesRegex(ValueError, "annotated release tag"):
            release.verify_published(tag="market-rsi-protocol-v0.1.1",
                                     expected_source_sha256=self.manifest())


if __name__ == "__main__":
    unittest.main()
