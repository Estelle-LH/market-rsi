"""Actual readonly Git/physical source gate on explicitly invented offline data.

Execution requires a separate Root grant for readonly git rev-parse/show.
Package initialization is an executed import dependency, not optional evidence.
This is only policy.validate_capacity_episode, not full financial admission,
owner opening, API authorization, model authorship or OS attestation.
"""
from contextlib import contextmanager, ExitStack
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

import earnings_entry as entry
import earnings_loop_policy as policy
from earnings_capacity_task import EarningsTask
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_capacity_assembly as assembly_fixture

PACKAGE = "research/market_rsi/data_scientist_harness/__init__.py"


class CapacitySourceClosureTests(unittest.TestCase):
    def fixture(self):
        fixture = assembly_fixture.AssemblyFixture(self, rounds=1)
        # Readonly repository identity, not a new/ref-switched Git state. The
        # executor must record the actual HEAD along with each source hash.
        commit = subprocess.run(["git", "rev-parse", "--verify", "HEAD"],
            cwd=entry.REPO, check=True, capture_output=True).stdout.decode().strip()
        self.assertRegex(commit, r"^[0-9a-f]{40}$")
        fixture.policy_pilot = fixture.raw.root / "invented-policy-namespace" / "pilot" / "pilot.json"
        kernel = {"scorer": engine.pin(fixture.paths["source_root"] / "evaluation_scorer.py"),
                  "qa": engine.pin(fixture.paths["source_root"] / "evaluation_qa.json")}
        self.assertEqual(Path(kernel["scorer"]["path"]).read_bytes(), Path(fixture.raw.kernel["scorer"]["path"]).read_bytes())
        self.assertEqual(Path(kernel["qa"]["path"]).read_bytes(), Path(fixture.raw.kernel["qa"]["path"]).read_bytes())
        study = deepcopy(engine.read(fixture.raw.study_binding))
        study["scorer"] = kernel["scorer"]
        study["cases"][0]["evaluation_kernel"] = kernel
        fixture.policy_study = study
        fixture.policy_envelope = deepcopy(fixture.envelope)
        fixture.policy_envelope.update(source_commit=commit, evaluation_kernel=kernel,
            root=str(fixture.policy_pilot.parent.parent / "earnings-coevolution-plan-20261013" / "episodes" / fixture.id),
            study=engine.save(fixture.home / "invented-policy-study.json", study),
            sources={name: engine.pin(entry.REPO / name)["sha256"] for name in policy.capacity_sources()})
        fixture.policy_envelope["slots"] = [{name: str(Path(fixture.policy_envelope["root"]) / "roles" / (name + "-01"))
            for name in ("controller", "author", "review", "forecast")}]
        return fixture

    @contextmanager
    def guards(self, fixture):
        # The unused setup budget was closed by AssemblyFixture. Only this
        # owned ledger file is hashed; no financial/private ledger is opened.
        ledger = fixture.raw.root / "owned-ledger.sqlite3"
        before_ledger = ledger.read_bytes()
        before_native = fixture.raw.native.batch.snapshot()
        namespace = Path(fixture.policy_envelope["root"])
        self.assertFalse(namespace.exists())
        with ExitStack() as stack:
            stack.enter_context(patch.object(entry, "PILOT", fixture.policy_pilot))
            task = stack.enter_context(patch.object(entry, "preflight_capacity_episode", side_effect=AssertionError("No full financial admission")))
            budget = stack.enter_context(patch.object(entry, "NightBudget", side_effect=AssertionError("No owner/ledger opening")))
            credentials = stack.enter_context(patch.object(entry, "credential", side_effect=AssertionError("No credentials")))
            http = stack.enter_context(patch("earnings_http.http.client.HTTPSConnection", side_effect=AssertionError("No API dispatch")))
            try:
                yield
            finally:
                task.assert_not_called(); budget.assert_not_called()
                credentials.assert_not_called(); http.assert_not_called()
                self.assertFalse(namespace.exists())
                self.assertEqual(ledger.read_bytes(), before_ledger)
                self.assertEqual(fixture.raw.native.batch.snapshot(), before_native)
                self.assertEqual(fixture.factory_calls, 0)
                self.assertEqual(fixture.raw.calls, [])

    def test_actual_task_source_bindings_exactly_cover_package_initialization(self):
        names = policy.capacity_sources()
        self.assertEqual(names, sorted(set(names)))
        self.assertIn(PACKAGE, names)
        bindings = EarningsTask().sources()
        self.assertEqual(set(bindings), set(names))
        for name in names:
            self.assertEqual(bindings[name], engine.pin(entry.REPO / name))
            self.assertEqual(set(bindings[name]), {"path", "sha256"})

    def test_actual_current_HEAD_git_bytes_and_physical_gate_accept_owned_invented_study(self):
        fixture = self.fixture()
        before = deepcopy(fixture.policy_envelope)
        self.assertIn(PACKAGE, before["sources"])
        actual_run = policy.subprocess.run
        with self.guards(fixture), patch.object(policy.subprocess, "run", wraps=actual_run) as git_reads:
            admitted = policy.validate_capacity_episode(fixture.policy_envelope)
        self.assertEqual(admitted, fixture.policy_study)
        self.assertEqual(fixture.policy_envelope, before)
        names = policy.capacity_sources()
        self.assertEqual(git_reads.call_count, len(names))
        self.assertEqual([call.args[0] for call in git_reads.call_args_list],
            [["git", "show", before["source_commit"] + ":" + name] for name in names])
        self.assertTrue(all(call.kwargs == {"cwd": entry.REPO, "check": True, "capture_output": True}
                            for call in git_reads.call_args_list))

    def test_missing_extra_package_hash_or_wrong_commit_refuses_without_owner(self):
        fixture = self.fixture()
        self.assertIn(PACKAGE, fixture.policy_envelope["sources"])
        for kind in ("missing", "extra", "bad-package-hash", "bad-hash-format", "wrong-commit"):
            with self.subTest(kind=kind):
                envelope = deepcopy(fixture.policy_envelope)
                if kind == "missing": envelope["sources"].pop(PACKAGE)
                elif kind == "extra": envelope["sources"]["unexecuted-extra.py"] = "e" * 64
                elif kind == "bad-package-hash": envelope["sources"][PACKAGE] = "e" * 64
                elif kind == "bad-hash-format": envelope["sources"][PACKAGE] = "invalid-source-token"
                else: envelope["source_commit"] = "0" * 40
                with self.guards(fixture), self.assertRaises((ValueError, subprocess.CalledProcessError)):
                    policy.validate_capacity_episode(envelope)

    def test_package_physical_read_drift_or_missing_file_is_not_repaired_or_admitted(self):
        fixture = self.fixture()
        original_path = entry.REPO / PACKAGE
        original_bytes = original_path.read_bytes()
        original_sha = sha256(original_bytes).hexdigest()
        actual_read = Path.read_bytes
        for kind in ("drift", "missing"):
            with self.subTest(kind=kind):
                calls = []
                def observed(path):
                    if path == original_path:
                        calls.append(str(path))
                        if kind == "missing": raise FileNotFoundError("Owned fault injection, not an actual source deletion")
                        return actual_read(path) + b"\nINJECTED_SOURCE_DRIFT\n"
                    return actual_read(path)
                with self.guards(fixture), patch.object(Path, "read_bytes", new=observed), \
                        self.assertRaises((ValueError, FileNotFoundError)):
                    policy.validate_capacity_episode(fixture.policy_envelope)
                self.assertEqual(calls, [str(original_path)])
                self.assertEqual(original_path.read_bytes(), original_bytes)
                self.assertEqual(sha256(original_path.read_bytes()).hexdigest(), original_sha)


if __name__ == "__main__":
    unittest.main()
