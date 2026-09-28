"""Local Git-only publication tests; never pushes the user's repository."""
from __future__ import annotations

import os
import subprocess
import shlex
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


class ProtocolReleaseConfigurationTests(unittest.TestCase):
    def test_production_origin_is_standalone_repository(self):
        self.assertEqual(
            release.ORIGIN,
            "https://github.com/Estelle-LH/market-rsi.git")

    def test_new_controller_to_b_admission_modules_are_released(self):
        required = {
            "supervisor_harness/frozen_glm_first_response.py",
            "supervisor_harness/offline_a_to_b_driver.py",
            "supervisor_harness/local_b_containment_canary.py",
            "supervisor_harness/local_b_containment_guest.py",
            "supervisor_harness/bottleneck_gate.py",
            "supervisor_harness/bounded_live_adapter_v2.py",
            "supervisor_harness/bounded_live_entry_v1.py",
            "supervisor_harness/live_runtime_requirements_v1.txt",
            "supervisor_harness/bounded_live_outer_runner_v3.py",
            "supervisor_harness/bounded_live_supervisor_parent_v1.py",
            "supervisor_harness/run_bounded_live_supervisor_parent_canary.py",
            "supervisor_harness/run_bounded_live_supervisor_parent_success_canary.py",
            "supervisor_harness/build_p0_gate1_controller_packet.py",
            "supervisor_harness/p0_gate1_research_contract.py",
            "supervisor_harness/p0_gate1_controller_adapter.py",
            "supervisor_harness/prospective_source_scope_decision.py",
            "supervisor_harness/test_prospective_source_scope_decision.py",
            "supervisor_harness/gate1_canary_receipt.py",
            "supervisor_harness/test_gate1_canary_receipt.py",
            "supervisor_harness/p0_gate1_controller_outer.py",
            "supervisor_harness/p0_gate1_controller_live_entry.py",
            "supervisor_harness/p0_gate1_controller_supervisor_parent.py",
            "supervisor_harness/run_p0_gate1_packet_preflight_canary.py",
            "supervisor_harness/p0_gate1_controller_cli_canary_child.py",
            "supervisor_harness/run_p0_gate1_controller_production_cli_canary.py",
            "supervisor_harness/run_p0_gate1_controller_adapter_canary.py",
            "supervisor_harness/run_p0_gate1_controller_outer_canary.py",
            "supervisor_harness/p0_gate1_public_fetch.py",
            "supervisor_harness/p0_gate1_watched_fetch.py",
            "supervisor_harness/p0_gate1_sample_materializer.py",
            "supervisor_harness/p0_gate1_trade_query.py",
            "supervisor_harness/p0_gate1_plan_compiler.py",
            "supervisor_harness/p0_gate1_executable_plan_canary_fixtures.py",
            "supervisor_harness/run_p0_gate1_executable_plan_canary.py",
        }
        self.assertTrue(required.issubset(release.PROTOCOL_FILES))

    def test_local_git_subprocess_has_fixed_trust_controls(self):
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=b"", stderr=b"")
        with patch.object(release.subprocess, "run", return_value=completed) as run:
            release._git("rev-parse", "HEAD")
        command = run.call_args.args[0]
        environment = run.call_args.kwargs["env"]
        self.assertEqual(command[:3], ["git", "-c", "core.fsmonitor=false"])
        self.assertEqual(environment["GIT_NO_REPLACE_OBJECTS"], "1")
        self.assertEqual(environment["GIT_OPTIONAL_LOCKS"], "0")
        self.assertEqual(environment["GIT_TERMINAL_PROMPT"], "0")

    def test_remote_git_uses_literal_origin_outside_repo_with_minimal_config(self):
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=b"", stderr=b"")
        injected = {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "protocol.ext.allow",
            "GIT_CONFIG_VALUE_0": "always",
            "GIT_CONFIG_PARAMETERS": "'protocol.ext.allow=always'",
            "GIT_CONFIG_GLOBAL": "/attacker/global-config",
            "GIT_CONFIG_SYSTEM": "/attacker/system-config",
            "GIT_DIR": "/attacker/repository",
            "GIT_EXEC_PATH": "/attacker/helpers",
        }
        with patch.dict(release.os.environ, injected, clear=False):
            with patch.object(
                    release.subprocess, "run", return_value=completed) as run:
                release._git_remote("refs/tags/fixture")
        command = run.call_args.args[0]
        environment = run.call_args.kwargs["env"]
        self.assertTrue(Path(command[0]).is_absolute())
        self.assertNotIn("-C", command)
        self.assertEqual(
            command[-3:],
            ["--", release.ORIGIN, "refs/tags/fixture"])
        self.assertEqual(run.call_args.kwargs["cwd"],
                         Path(os.devnull).resolve().parent)
        self.assertIn("protocol.allow=never", command)
        self.assertIn("protocol.https.allow=always", command)
        self.assertIn("credential.helper=", command)
        self.assertIn("http.followRedirects=false", command)
        self.assertEqual(environment["GIT_CONFIG_NOSYSTEM"], "1")
        self.assertEqual(environment["GIT_CONFIG_GLOBAL"], os.devnull)
        self.assertEqual(environment["GIT_CONFIG_SYSTEM"], os.devnull)
        self.assertEqual(environment["GIT_TERMINAL_PROMPT"], "0")
        self.assertEqual(environment["GCM_INTERACTIVE"], "never")
        for name in (
                "GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0",
                "GIT_CONFIG_PARAMETERS", "GIT_DIR", "GIT_EXEC_PATH"):
            self.assertNotIn(name, environment)

    def test_remote_git_rejects_ext_literal_transport(self):
        with patch.object(release, "ORIGIN", "ext::attacker-helper"):
            with self.assertRaisesRegex(
                    ValueError, "unsupported publication origin transport"):
                release._git_remote("refs/tags/fixture")


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
                        patch.object(release, "FILES", ("one.py",)),
                        patch.object(release, "ORIGIN", str(self.remote))]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def manifest(self):
        return digest(release.source_hashes())

    def attacker_remote_with_tag(self, name="attacker.git"):
        attacker = self.parent / name
        attacker.mkdir()
        git(attacker, "init", "-q", "--bare")
        git(self.repo, "push", "-q", str(attacker), self.tag)
        return attacker

    def test_requires_exact_annotated_tag_on_origin(self):
        expected = self.manifest()
        with self.assertRaisesRegex(ValueError, "Git publication check failed"):
            release.verify_published(tag=self.tag, expected_source_sha256=expected)
        git(self.repo, "push", "-q", "origin", self.tag)
        value = release.verify_published(tag=self.tag, expected_source_sha256=expected)
        self.assertEqual(value["source_sha256"], expected)
        self.assertEqual(value["origin"], release.ORIGIN)
        self.assertFalse(value["isolation_proven"])

    def test_old_fork_origin_is_rejected_without_remote_access(self):
        git(self.repo, "remote", "set-url", "origin",
            "https://github.com/Estelle-LH/RSIBench-Data.git")
        with self.assertRaisesRegex(
                ValueError, "authorized standalone repository"):
            release.verify_published(
                tag=self.tag, expected_source_sha256=self.manifest())

    def test_instead_of_cannot_hide_malicious_raw_origin(self):
        malicious = "https://attacker.invalid/market-rsi.git"
        git(self.repo, "remote", "set-url", "origin", malicious)
        git(self.repo, "config", f"url.{self.remote}.insteadOf", malicious)
        self.assertEqual(git(self.repo, "remote", "get-url", "origin"),
                         str(self.remote))
        with self.assertRaisesRegex(
                ValueError, "authorized standalone repository"):
            release.verify_published(
                tag=self.tag, expected_source_sha256=self.manifest())

    def test_authorized_origin_cannot_be_rewritten_to_attacker_file_remote(self):
        attacker = self.attacker_remote_with_tag()
        git(self.repo, "config", f"url.{attacker}.insteadOf", str(self.remote))
        ref = "refs/tags/" + self.tag
        self.assertIn(ref, git(
            self.repo, "ls-remote", "--exit-code", "origin", ref, ref + "^{}"))
        with self.assertRaisesRegex(ValueError, "Git publication check failed"):
            release.verify_published(
                tag=self.tag, expected_source_sha256=self.manifest())

    def test_local_ext_rewrite_helper_cannot_execute(self):
        marker = self.parent / "ext-helper-executed"
        helper = self.parent / "ext-helper.sh"
        helper.write_text(
            "#!/bin/sh\n"
            f"printf 'ran\\n' >> {shlex.quote(str(marker))}\n"
            "exit 1\n")
        helper.chmod(0o755)
        git(self.repo, "config", f"url.ext::{helper}.insteadOf", str(self.remote))
        git(self.repo, "config", "protocol.ext.allow", "always")
        ref = "refs/tags/" + self.tag
        reproduced = subprocess.run(
            ["git", "-C", str(self.repo), "ls-remote", "origin", ref],
            capture_output=True, text=True, timeout=10, check=False)
        self.assertNotEqual(reproduced.returncode, 0)
        self.assertTrue(marker.is_file())
        marker.unlink()

        with self.assertRaisesRegex(ValueError, "Git publication check failed"):
            release.verify_published(
                tag=self.tag, expected_source_sha256=self.manifest())
        self.assertFalse(marker.exists())

    def test_git_config_count_url_rewrite_is_not_inherited(self):
        attacker = self.attacker_remote_with_tag()
        ref = "refs/tags/" + self.tag
        injection = {
            "GIT_CONFIG_COUNT": "2",
            "GIT_CONFIG_KEY_0": f"url.{attacker}.insteadOf",
            "GIT_CONFIG_VALUE_0": str(self.remote),
            "GIT_CONFIG_KEY_1": "protocol.file.allow",
            "GIT_CONFIG_VALUE_1": "always",
        }
        attack_env = {**os.environ, **injection}
        reproduced = subprocess.run(
            ["git", "-C", str(self.repo), "ls-remote", "--exit-code",
             "origin", ref, ref + "^{}"],
            capture_output=True, text=True, timeout=10, env=attack_env,
            check=False)
        self.assertEqual(reproduced.returncode, 0, reproduced.stderr)

        with patch.dict(release.os.environ, injection, clear=False):
            with self.assertRaisesRegex(
                    ValueError, "Git publication check failed"):
                release.verify_published(
                    tag=self.tag, expected_source_sha256=self.manifest())

    def test_global_and_system_config_url_rewrites_are_not_inherited(self):
        attacker = self.attacker_remote_with_tag()
        ref = "refs/tags/" + self.tag
        for scope in ("GLOBAL", "SYSTEM"):
            with self.subTest(scope=scope):
                config = self.parent / f"{scope.lower()}.gitconfig"
                git(self.repo, "config", "--file", str(config),
                    f"url.{attacker}.insteadOf", str(self.remote))
                injection = {f"GIT_CONFIG_{scope}": str(config)}
                attack_env = {**os.environ, **injection}
                if scope == "SYSTEM":
                    attack_env.pop("GIT_CONFIG_NOSYSTEM", None)
                reproduced = subprocess.run(
                    ["git", "-C", str(self.repo), "ls-remote", "--exit-code",
                     "origin", ref, ref + "^{}"],
                    capture_output=True, text=True, timeout=10, env=attack_env,
                    check=False)
                self.assertEqual(reproduced.returncode, 0, reproduced.stderr)
                with patch.dict(release.os.environ, injection, clear=False):
                    with self.assertRaisesRegex(
                            ValueError, "Git publication check failed"):
                        release.verify_published(
                            tag=self.tag,
                            expected_source_sha256=self.manifest())

    def test_git_config_parameters_ext_helper_is_not_inherited(self):
        marker = self.parent / "environment-ext-helper-executed"
        helper = self.parent / "environment-ext-helper.sh"
        helper.write_text(
            "#!/bin/sh\n"
            f"printf 'ran\\n' >> {shlex.quote(str(marker))}\n"
            "exit 1\n")
        helper.chmod(0o755)
        parameter = (
            f"'url.ext::{helper}.insteadOf={self.remote}' "
            "'protocol.ext.allow=always'")
        ref = "refs/tags/" + self.tag
        injection = {"GIT_CONFIG_PARAMETERS": parameter}
        reproduced = subprocess.run(
            ["git", "-C", str(self.repo), "ls-remote", "origin", ref],
            capture_output=True, text=True, timeout=10,
            env={**os.environ, **injection}, check=False)
        self.assertNotEqual(reproduced.returncode, 0)
        self.assertTrue(marker.is_file())
        marker.unlink()

        with patch.dict(release.os.environ, injection, clear=False):
            with self.assertRaisesRegex(
                    ValueError, "Git publication check failed"):
                release.verify_published(
                    tag=self.tag, expected_source_sha256=self.manifest())
        self.assertFalse(marker.exists())

    def test_multiple_raw_origin_values_are_rejected(self):
        git(self.repo, "config", "--add", "remote.origin.url",
            "https://attacker.invalid/second.git")
        self.assertEqual(
            git(self.repo, "config", "--local", "--no-includes", "--get-all",
                "remote.origin.url").splitlines(),
            [str(self.remote), "https://attacker.invalid/second.git"])
        with self.assertRaisesRegex(
                ValueError, "authorized standalone repository"):
            release.verify_published(
                tag=self.tag, expected_source_sha256=self.manifest())

    def test_changed_runtime_source_is_not_released(self):
        git(self.repo, "push", "-q", "origin", self.tag)
        expected = self.manifest()
        self.file.write_text("value = 2\n")
        with self.assertRaisesRegex(ValueError, "current protocol source"):
            release.verify_published(tag=self.tag, expected_source_sha256=expected)

    def test_documentation_only_head_commit_does_not_invalidate_release(self):
        expected = self.manifest()
        release_commit = git(self.repo, "rev-parse", f"{self.tag}^{{commit}}")
        git(self.repo, "push", "-q", "origin", self.tag)
        notes = self.repo / "notes.md"
        notes.write_text("documentation after protocol release\n")
        git(self.repo, "add", "--", "notes.md")
        git(self.repo, "commit", "-qm", "document published protocol")
        self.assertNotEqual(git(self.repo, "rev-parse", "HEAD"), release_commit)
        value = release.verify_published(
            tag=self.tag, expected_source_sha256=expected)
        self.assertEqual(value["commit"], release_commit)

    def test_committed_protocol_change_after_tag_is_rejected(self):
        git(self.repo, "push", "-q", "origin", self.tag)
        self.file.write_text("value = 2\n")
        git(self.repo, "add", "--", str(self.file.relative_to(self.repo)))
        git(self.repo, "commit", "-qm", "change controlled protocol")
        with self.assertRaisesRegex(
                ValueError, "release tag differs from current protocol source"):
            release.verify_published(
                tag=self.tag, expected_source_sha256=self.manifest())

    def test_replace_ref_cannot_substitute_archived_tag_bytes(self):
        release_commit = git(self.repo, "rev-parse", f"{self.tag}^{{commit}}")
        git(self.repo, "push", "-q", "origin", self.tag)
        self.file.write_text("value = 2\n")
        git(self.repo, "add", "--", str(self.file.relative_to(self.repo)))
        git(self.repo, "commit", "-qm", "replacement fixture")
        replacement_commit = git(self.repo, "rev-parse", "HEAD")
        git(self.repo, "replace", release_commit, replacement_commit)
        self.assertEqual(
            git(self.repo, "show", f"{release_commit}:"
                f"{self.file.relative_to(self.repo)}"),
            "value = 2")
        with self.assertRaisesRegex(
                ValueError, "release tag differs from current protocol source"):
            release.verify_published(
                tag=self.tag, expected_source_sha256=self.manifest())

    def test_fsmonitor_cannot_execute_during_verification(self):
        git(self.repo, "push", "-q", "origin", self.tag)
        marker = self.parent / "fsmonitor-executed"
        hook = self.parent / "fsmonitor-hook.sh"
        hook.write_text(
            "#!/bin/sh\n"
            f"printf 'ran\\n' >> {shlex.quote(str(marker))}\n"
            "exit 1\n")
        hook.chmod(0o755)
        git(self.repo, "config", "core.fsmonitor", str(hook))
        git(self.repo, "status", "--porcelain")
        self.assertTrue(marker.is_file())
        marker.unlink()

        value = release.verify_published(
            tag=self.tag, expected_source_sha256=self.manifest())
        self.assertEqual(value["tag"], self.tag)
        self.assertFalse(marker.exists())

    def test_lightweight_tag_is_rejected(self):
        git(self.repo, "tag", "market-rsi-protocol-v0.1.1")
        git(self.repo, "push", "-q", "origin", "market-rsi-protocol-v0.1.1")
        with self.assertRaisesRegex(ValueError, "annotated release tag"):
            release.verify_published(tag="market-rsi-protocol-v0.1.1",
                                     expected_source_sha256=self.manifest())


if __name__ == "__main__":
    unittest.main()
