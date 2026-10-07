"""Focused offline tests for the permanent-ID bridge canary parent."""
from __future__ import annotations

import argparse
import ast
import os
from pathlib import Path
import pwd
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from market_rsi import canonical, digest, file_hash, fresh_json
from supervisor_harness import run_p0_gate1_source_scope_request_plan_canary as runner


class _Completed:
    def __init__(self, returncode=0, stdout=""):
        self.returncode = returncode
        self.stdout = stdout


class RequestPlanCanaryParentTests(unittest.TestCase):
    def test_publication_recomputes_complete_controlled_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary).resolve() / "publication.json"
            hashes = {name: file_hash(runner._SOURCE_ROOT / name)
                      for name in runner._SOURCE_FILES}
            hashes["unrelated-controlled.py"] = "a" * 64
            source_sha = digest(hashes)
            publication = {
                "schema": "market_rsi_protocol_publication_v1",
                "origin": runner.child_entry.PUBLISHED_ORIGIN,
                "tag": runner.RELEASE_TAG,
                "commit": "b" * 40,
                "tag_object": "c" * 40,
                "source_sha256": source_sha,
                "source_hashes": hashes,
                "isolation_proven": False,
                "model_authorship_proven": False,
            }
            path.write_text(canonical(publication) + "\n")
            with patch(
                "supervisor_harness.protocol_source_release.source_hashes",
                return_value=hashes,
            ):
                self.assertEqual(runner._validate_publication(
                    path, expected_source_sha256=source_sha,
                    expected_release_commit="b" * 40,
                    expected_release_tag_object="c" * 40), publication)
            changed = dict(hashes)
            changed["unrelated-controlled.py"] = "d" * 64
            with patch(
                "supervisor_harness.protocol_source_release.source_hashes",
                return_value=changed,
            ):
                with self.assertRaisesRegex(ValueError, "complete controlled source"):
                    runner._validate_publication(
                        path, expected_source_sha256=source_sha,
                        expected_release_commit="b" * 40,
                        expected_release_tag_object="c" * 40)

    def test_exact_clear_rejects_matching_process_and_accepts_empty(self):
        def clear_run(command, **_kwargs):
            if command[0] == "ps":
                return _Completed(stdout="123 /usr/bin/python unrelated.py\n")
            return _Completed(returncode=1)

        self.assertEqual(runner._exact_clear(run=clear_run)["exact_processes"], [])

        def occupied_run(command, **_kwargs):
            if command[0] == "ps":
                return _Completed(stdout=(
                    "321 python child.py --cycle-id " + runner.CANARY_ID + "\n"))
            return _Completed(returncode=1)

        with self.assertRaisesRegex(ValueError, "already present"):
            runner._exact_clear(run=occupied_run)

    def test_permanent_claim_is_exclusive_and_runtime_uses_canonical_digest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = runner._claim_root(Path(temporary).resolve() / "claims")
            claim = root / f"{runner.CANARY_ID}.json"
            fresh_json(claim, {"id": runner.CANARY_ID})
            with self.assertRaises(FileExistsError):
                fresh_json(claim, {"id": runner.CANARY_ID})
        runtime = runner._runtime()
        self.assertRegex(digest(runtime), r"^[0-9a-f]{64}$")
        self.assertFalse(runtime["network_modules_loaded_by_canary"])

    def test_fixed_paths_minimal_environment_and_no_generic_locator_cli(self):
        account_home = Path(pwd.getpwuid(os.geteuid()).pw_dir)
        market_rsi_home = account_home / "Library/Application Support/MarketRSI"
        self.assertEqual(runner._ACCOUNT_HOME, account_home)
        self.assertEqual(runner.RUN_ROOT.parent, market_rsi_home / "runs")
        self.assertNotIn("/tmp", str(runner.RUN_ROOT))
        self.assertNotIn("Documents", str(runner.RUN_ROOT))
        options = {option for action in runner.parser()._actions
                   for option in action.option_strings}
        for forbidden in ("--url", "--method", "--headers", "--query", "--body",
                          "--handler", "--retry", "--budget-root",
                          "--global-state-root", "--catalog", "--train", "--dev",
                          "--final"):
            self.assertNotIn(forbidden, options)
        source = Path(runner.__file__).read_text()
        tree = ast.parse(source)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, ast.Import):
                imported.update(item.name for item in node.names)
        self.assertFalse(any("public_fetch" in name or "watched_fetch" in name
                             for name in imported))
        self.assertIn('env={"PATH": os.defpath, "LANG": "C", "LC_ALL": "C"}',
                      source)

    def test_d0_paths_and_packet_hash_match_registered_preflight(self):
        market_rsi_home = (
            Path(pwd.getpwuid(os.geteuid()).pw_dir)
            / "Library/Application Support/MarketRSI"
        )
        self.assertEqual(
            runner.D0_PATHS["packet"],
            market_rsi_home / "runs"
            / "market-rsi-v0125-gate1-first-current-source-20260928-01"
            / "controller-input.json",
        )
        self.assertEqual(runner.child_entry.D0_FILE_SHA256["packet"],
                         "bb15603ffd32c8b18b17339ce88aec15294862950d8dc8cb3036485716fe1acd")


if __name__ == "__main__":
    unittest.main()
