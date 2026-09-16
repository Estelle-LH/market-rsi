"""Release gate tests against temporary local Git repos, never GitHub or providers."""
from pathlib import Path
import json
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from data_scientist_harness import VERSION, fixtures, release
from data_scientist_harness.broker import Broker
from data_scientist_harness.store import Store
from market_rsi import digest, file_hash, load_json


class GitReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name).resolve()
        self.repo = self.base / "repo"; self.repo.mkdir()
        self.remote = self.base / "remote.git"
        self.run_git("init", "--bare", str(self.remote))
        self.run_git("init", "-b", "main")
        self.run_git("config", "user.email", "fixture@example.invalid")
        self.run_git("config", "user.name", "Synthetic test")
        self.run_git("config", "commit.gpgsign", "false")
        self.run_git("remote", "add", "origin", str(self.remote))
        self.root = self.repo / "research/market_rsi"; self.root.mkdir(parents=True)
        self.file = self.root / "method.py"; self.file.write_text("# synthetic code\n")
        for path in release.source_files(self.root):
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists(): path.write_text("# synthetic dependency\n")
        self.run_git("add", "research")
        self.run_git("commit", "-m", "synthetic baseline")
        self.commit = self.run_git("rev-parse", "HEAD").strip()
        self.run_git("tag", "-a", release.TAG, "-m", "synthetic release")
        self.sources = release.source_hashes(self.root)

    def tearDown(self): self.tmp.cleanup()

    def run_git(self, *args):
        result = subprocess.run(["git", "-C", str(self.repo), *args], check=True,
            capture_output=True, text=True, timeout=20)
        return result.stdout

    def publish(self): self.run_git("push", "origin", "main", "refs/tags/" + release.TAG)

    def check(self, sources=None, commit=None):
        with patch.object(release, "ORIGIN", str(self.remote)):
            return release.verify_git_publication(sources or self.sources, root=self.root,
                                                  commit=commit or self.commit)

    def test_exact_committed_pushed_tag_passes(self):
        self.publish()
        result = self.check()
        self.assertEqual(result["commit"], self.commit)
        self.assertEqual(result["tag"], release.TAG)

    def test_sports_execution_code_is_in_release_snapshot(self):
        sports = self.root / "sports_event_research"; sports.mkdir()
        method = sports / "method.py"; method.write_text("# executable sports method\n")
        test = sports / "test_method.py"; test.write_text("# test only\n")
        files = release.source_files(self.root)
        self.assertIn(method, files)
        self.assertNotIn(test, files)

    def test_unpushed_tag_rejected(self):
        self.run_git("push", "origin", "main")
        with self.assertRaises(ValueError): self.check()

    def test_uncommitted_change_even_matching_new_canary_rejected(self):
        self.publish(); self.file.write_text("# changed but unpublished\n")
        with self.assertRaisesRegex(ValueError, "uncommitted"):
            self.check(release.source_hashes(self.root))

    def test_staged_change_rejected(self):
        self.publish(); self.file.write_text("# staged change\n"); self.run_git("add", "research")
        with self.assertRaisesRegex(ValueError, "uncommitted"):
            self.check(release.source_hashes(self.root))

    def test_untracked_executable_rejected(self):
        self.publish(); (self.root / "new_method.py").write_text("# untracked\n")
        with self.assertRaisesRegex(ValueError, "source set differs"):
            self.check()

    def test_different_commit_cannot_reuse_version_tag(self):
        self.publish(); self.file.write_text("# new method\n")
        self.run_git("add", "research"); self.run_git("commit", "-m", "new method")
        newer = self.run_git("rev-parse", "HEAD").strip()
        with self.assertRaisesRegex(ValueError, "tag belongs to another commit"):
            self.check(release.source_hashes(self.root), newer)

    def test_local_retag_same_commit_does_not_match_remote_object(self):
        self.publish()
        # Deliberately corrupt only this test's temporary tag, never a project tag.
        self.run_git("tag", "-f", "-a", release.TAG, "-m", "different annotation")
        with self.assertRaisesRegex(ValueError, "not published"):
            self.check()

    def test_unrelated_dirty_notes_do_not_force_a_new_harness(self):
        self.publish(); (self.repo / "unrelated-note.md").write_text("unrelated draft\n")
        self.assertEqual(self.check()["commit"], self.commit)

    def test_wrong_origin_rejected(self):
        self.publish()
        with self.assertRaisesRegex(ValueError, "authorized private repository"):
            release.verify_git_publication(self.sources, root=self.root, commit=self.commit)

    def test_lightweight_tag_is_not_a_release(self):
        self.run_git("tag", "-f", release.TAG, self.commit); self.publish()
        with self.assertRaisesRegex(ValueError, "annotated"):
            self.check()

    def many_sources(self, *, export_ignore=False):
        for n in range(40): (self.root / f"part_{n:02}.py").write_text(f"# fixture {n}\n")
        if export_ignore:
            (self.root / ".gitattributes").write_text("part_39.py export-ignore\n")
        self.run_git("add", "research"); self.run_git("commit", "-m", "many fixture sources")
        self.commit = self.run_git("rev-parse", "HEAD").strip()
        # Only this test's unpublished temporary tag is replaced.
        self.run_git("tag", "-f", "-a", release.TAG, "-m", "many fixture sources")
        self.sources = release.source_hashes(self.root); self.publish()

    def test_archive_checks_every_source_in_bounded_batches(self):
        self.many_sources()
        with patch.object(release, "git", wraps=release.git) as calls:
            self.assertEqual(self.check()["commit"], self.commit)
        batches = [list(c.args[c.args.index("--") + 1:]) for c in calls.call_args_list
                   if "archive" in c.args]
        self.assertGreater(len(batches), 1)
        self.assertTrue(all(0 < len(batch) <= 16 for batch in batches))
        self.assertEqual([p for batch in batches for p in batch],
            ["research/market_rsi/" + p for p in self.sources])

    def test_export_ignored_source_in_later_batch_rejected(self):
        self.many_sources(export_ignore=True)
        with self.assertRaisesRegex(ValueError, "exact canary/runtime source set"):
            self.check()


class WorkspaceReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name).resolve() / "run"
        self.sha = fixtures.workspace(self.root)

    def tearDown(self): self.tmp.cleanup()

    def rewrite(self, config):
        (self.root / "workspace.json").write_text(json.dumps(config))
        self.sha = file_hash(self.root / "workspace.json")

    def test_canary_explicitly_unpublished(self):
        store = Store(self.root, self.sha)
        self.assertEqual(release.identity(store.config), {"version": VERSION, "published": False,
            "change_origin": release.CHANGE_ORIGIN, "is_agent_self_evolution": False,
            "commit": None, "tag": None, "release_sha256": None})

    def test_development_workspace_cannot_reach_real_cpu_training(self):
        config = load_json(self.root / "workspace.json"); config["purpose"] = "opened_train_research"
        self.rewrite(config)
        broker = Broker(self.root, self.sha)
        broker.call("inspect_harness", {})
        with patch("data_scientist_harness.broker.subprocess.Popen") as spawn:
            with self.assertRaisesRegex(ValueError, "published harness release required"):
                broker.call("train_candidate", {"trial_id": "no-start", "parent_trial_id": "", "plan": {},
                    "feature_review": "0001", "trainer_research": "0001", "experiment":{}})
            spawn.assert_not_called()
        self.assertFalse((self.root / "trials").exists())

    def test_resealed_different_version_is_rejected(self):
        config = load_json(self.root / "workspace.json"); config["harness_version"] = "different-version"
        self.rewrite(config)
        with self.assertRaisesRegex(ValueError, "harness version differs"):
            Store(self.root, self.sha)

    def test_string_label_is_not_release_proof(self):
        config = load_json(self.root / "workspace.json"); config["release"] = VERSION
        self.rewrite(config)
        with self.assertRaisesRegex(ValueError, "published harness release"):
            Store(self.root, self.sha)

    def test_tool_record_carries_explicit_version(self):
        broker = Broker(self.root, self.sha); broker.call("inspect_harness", {})
        record = broker.store.records()[0]
        self.assertEqual(record["harness_release"]["version"], VERSION)
        self.assertFalse(record["harness_release"]["published"])

    def test_changed_harness_cannot_be_called_model_only_progress(self):
        before = release.attribution(load_json(self.root / "workspace.json"), fixtures.plan())
        after = dict(before, harness=dict(before["harness"], commit="a" * 40))
        result = release.compare_attribution(before, after)
        self.assertEqual(result["changed_components"], ["harness"])
        self.assertTrue(result["model_only_claim_blocked"])

    def test_one_trainer_change_still_does_not_prove_improvement(self):
        config = load_json(self.root / "workspace.json")
        result = release.compare_attribution(release.attribution(config, fixtures.plan()),
            release.attribution(config, fixtures.plan("random_forest")))
        self.assertEqual(result["changed_components"], ["trainer_sha256"])
        self.assertFalse(result["model_only_claim_blocked"])
        self.assertFalse(result["performance_improvement_proven"])

    def test_changed_context_and_codex_are_not_hidden_by_same_commit(self):
        before = release.attribution(load_json(self.root / "workspace.json"), fixtures.plan())
        for component in ("research_context_sha256", "codex_sha256"):
            with self.subTest(component=component):
                after = dict(before, **{component: "b" * 64})
                result = release.compare_attribution(before, after)
                self.assertEqual(result["changed_components"], [component])
                self.assertTrue(result["model_only_claim_blocked"])


if __name__ == "__main__": unittest.main()
