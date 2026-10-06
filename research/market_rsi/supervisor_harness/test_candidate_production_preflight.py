"""Production-shaped native clock and source admission; synthetic files only."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from supervisor_harness import candidate_production_preflight as p
from supervisor_harness import opened_train_discovery_worker as w
from supervisor_harness import account_controller_feedback_consumer as c
from supervisor_harness import continuous_discovery_batch as r

PINNED = Path("/Users/estelle/Library/Application Support/MarketRSI/runtimes/"
              "ds-py312-20260912-01/bin/python")
PARENT = "f5a80888069140a78ab637cf0e03a7bf3df3da2458151323a43e696bf88b8085"


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve(); self.repo = self.root / "repo"
        self.repo.mkdir(); self.git("init", "-q")
        self.runner = "research/market_rsi/experiments/nfl_ingame_preflight_fixture.py"
        path = self.repo / self.runner; path.parent.mkdir(parents=True)
        path.write_text("raise AssertionError('candidate must not be imported')\n")
        self.adapter = p.MODES["legacy_c1_c7"]
        (self.repo / self.adapter).write_text("# synthetic reviewed C1/C7 adapter\n")
        self.metadata_path = "research/market_rsi/preflight-parent.json"
        self.contract = {"candidate_id": "candidate", "actual_parent_sha256": PARENT,
            "comparison_incumbent_sha256": "b" * 64,
            "resources": {"fits": 4, "seconds": 900, "threads": 1,
                          "rss_bytes": 1073741824, "provider_calls": 0}}
        self.contract_binding = self.write("contract", self.contract)
        self.metadata = {"schema": "candidate_parent_support_v1", "candidate_id": "candidate",
            "module": "experiments.nfl_ingame_preflight_fixture",
            "contract_sha256": self.contract_binding["sha256"],
            "research_parent_sha256": PARENT, "comparison_incumbent_sha256": "b" * 64,
            "mode": "legacy_c1_c7", "adapter_sources": {self.adapter: w.sha(self.repo / self.adapter)},
            "accepted_reference": None}
        (self.repo / self.metadata_path).write_text(json.dumps(self.metadata))
        self.git("add", "."); self.git("-c", "user.name=Synthetic", "-c", "user.email=test@invalid", "commit", "-qm", "fixture")
        self.alias = self.root / "venv/bin/python"; self.alias.parent.mkdir(parents=True)
        self.alias.symlink_to(Path(sys.executable).resolve())
        memory = self.write("memory", {"synthetic": True})
        self.request = {"attempt_id": "attempt", "candidate_id": "candidate",
            "module": self.metadata["module"], "source_commit": self.git("rev-parse", "HEAD").strip(),
            "files": {name: w.sha(self.repo / name) for name in (self.runner, self.adapter, self.metadata_path)},
            "python": str(self.alias), "python_sha256": w.sha(self.alias),
            "memory": memory["path"], "memory_sha256": memory["sha256"],
            "runtime_pair_sha256": "c" * 64, "spec_sha256": self.contract_binding["sha256"],
            "max_fits": 4, "max_wall_seconds": 900}
        now = datetime.now(timezone.utc)
        self.batch = r.ContinuousDiscoveryBatch(self.root / "batch", allow_temporary=True)
        self.batch.initialize(batch_id="production-shaped", start_utc=now - timedelta(minutes=1),
            deadline_utc=now + timedelta(minutes=5), max_attempts=3,
            initial_incumbent={"candidate_id": "market", "candidate_sha256": "b" * 64,
                "scorecard_sha256": "d" * 64, "review_sha256": "e" * 64})
        self.rebind()

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.repo, text=True)

    def write(self, name, value):
        path = self.root / (name + ".json"); path.write_text(json.dumps(value))
        return {"path": str(path), "sha256": w.sha(path)}

    def rebind(self):
        self.request_binding = self.write("request", self.request)
        self.review = {"schema": "reviewed_candidate_request_v1", "passed": True,
            "batch_id": "production-shaped", "request_sha256": self.request_binding["sha256"],
            "contract_sha256": self.contract_binding["sha256"],
            "source_commit": self.request["source_commit"], "files": self.request["files"],
            "semantic_source_matches_decision": True, "research_parent_sha256": self.contract["actual_parent_sha256"],
            "comparison_incumbent_sha256": "b" * 64}
        self.review_binding = self.write("review", self.review)

    def invoke(self):
        return p.preflight(self.batch, self.request_binding, self.review_binding,
                           self.contract_binding, self.repo, parent_check=self.metadata_path)

    def probe(self):
        return {"versions": p.EXPECTED_VERSIONS, "executable": str(self.alias),
                "prefix": str(self.alias.parent.parent)}

    def denied(self, regex):
        before = self.batch.snapshot()
        with patch.object(p, "_probe", return_value=self.probe()) as imports:
            with self.assertRaisesRegex((ValueError, RuntimeError), regex): self.invoke()
        self.assertEqual(self.batch.snapshot(), before)
        self.assertEqual(before["branches"], [])
        return imports

    def test_real_native_clock_alias_and_committed_source_no_admission(self):
        before = self.batch.snapshot()
        with patch.object(p, "_probe", return_value=self.probe()) as imports:
            result = self.invoke()
        imports.assert_called_once_with(str(self.alias), self.repo)
        self.assertIs(result["passed"], True); self.assertFalse(result["candidate_execution_performed"])
        self.assertEqual(result["python_alias"], str(self.alias))
        self.assertEqual(self.batch.snapshot(), before)
        with self.assertRaisesRegex(ValueError, "caller-supplied time"):
            self.batch._trusted_now(datetime.now(timezone.utc), "historical bad handoff")

    def test_injected_production_clock_denied_before_import_or_slot(self):
        self.batch._clock = lambda: datetime.now(timezone.utc)
        self.denied("production recorder").assert_not_called()

    def test_native_temporary_test_clock_explicitly_supported(self):
        self.batch = r.ContinuousDiscoveryBatch(self.batch.root, allow_temporary=True,
            test_clock=lambda: datetime.now(timezone.utc), allow_test_clock=True)
        with patch.object(p, "_probe", return_value=self.probe()): self.invoke()

    def test_request_review_and_runtime_hash_drift_denied(self):
        self.review["semantic_source_matches_decision"] = False
        self.review_binding = self.write("review", self.review)
        self.denied("reviewed request").assert_not_called()
        self.rebind(); self.request["python_sha256"] = "f" * 64; self.rebind()
        self.denied("runtime or memory identity").assert_not_called()

    def test_uncommitted_source_even_resealed_hash_denied(self):
        (self.repo / self.runner).write_text("# drift, independently resealed but not committed\n")
        self.request["files"][self.runner] = w.sha(self.repo / self.runner); self.rebind()
        self.denied("committed capability source").assert_not_called()

    def test_parent_metadata_cannot_self_attest_outside_reviewed_files(self):
        del self.request["files"][self.metadata_path]; self.rebind()
        self.denied("reviewed source files").assert_not_called()

    def test_unknown_parent_mode_denied(self):
        self.metadata["mode"] = "trust_me"
        self.recommit_metadata()
        self.denied("parent capability").assert_not_called()

    def recommit_metadata(self):
        (self.repo / self.metadata_path).write_text(json.dumps(self.metadata))
        self.git("add", "."); self.git("-c", "user.name=Synthetic", "-c", "user.email=test@invalid", "commit", "-qm", "next fixture")
        self.request["source_commit"] = self.git("rev-parse", "HEAD").strip()
        self.request["files"][self.metadata_path] = w.sha(self.repo / self.metadata_path); self.rebind()

    def test_parent_contract_or_adapter_hash_drift_denied(self):
        self.metadata["research_parent_sha256"] = "f" * 64; self.recommit_metadata()
        self.denied("parent capability").assert_not_called()
        self.metadata["research_parent_sha256"] = PARENT
        self.metadata["adapter_sources"][self.adapter] = "f" * 64; self.recommit_metadata()
        self.denied("adapter source").assert_not_called()

    def test_resealed_review_cannot_expand_legacy_parent_support(self):
        self.contract["actual_parent_sha256"] = "f" * 64
        self.contract_binding = self.write("contract", self.contract)
        self.request["spec_sha256"] = self.contract_binding["sha256"]
        self.metadata["contract_sha256"] = self.contract_binding["sha256"]
        self.metadata["research_parent_sha256"] = "f" * 64; self.recommit_metadata()
        self.denied("only frozen C1/C7").assert_not_called()

    def test_reviewed_generic_accepted_negative_parent_original_bytes_without_state_interpretation(self):
        from experiments import nfl_ingame_prediction_reference as reference
        relative = p.MODES["accepted_prediction_reference"]
        (self.repo / relative).write_bytes(Path(reference.__file__).read_bytes())
        self.request["files"][relative] = w.sha(self.repo / relative)
        source = self.root / "original-source.py"; source.write_text("# original synthetic parent\n")
        original_parent = w.sha(source)
        self.contract["actual_parent_sha256"] = original_parent
        self.contract_binding = self.write("contract", self.contract)
        self.request["spec_sha256"] = self.contract_binding["sha256"]
        self.metadata.update(contract_sha256=self.contract_binding["sha256"], research_parent_sha256=original_parent)
        artifacts = self.root / "original-artifacts"; artifacts.mkdir()
        for name in reference.ARTIFACTS:
            (artifacts / name).write_text("synthetic bytes, not parsed or fitted\n")
        binding = {"schema": reference.SCHEMA, "candidate_id": "archived-negative",
            "runner": {"path": str(source), "sha256": original_parent},
            "source_commit": "1" * 40, "artifact_root": str(artifacts),
            "artifact_hashes": {name: w.sha(artifacts / name) for name in reference.ARTIFACTS},
            "kernel_sha256": "c" * 64}
        acceptance = {"schema": reference.ACCEPTANCE_SCHEMA,
            "reference_sha256": reference.digest(binding), "performance_status": "valid_no_leakage",
            "prediction_decision": "REVERT", "provenance": {
                "task_id": "InGameWinProbabilityTrainDiagnostic-v0", "kernel_sha256": "c" * 64,
                "v0_artifact_hashes": {}, "folds_sha256": "d" * 64, "data_time_sha256": "d" * 64,
                "check_key_sha256": "d" * 64, "check_rows_sha256": "d" * 64,
                "exclusion_codes_sha256": "d" * 64}, "exclusions": {},
            "reviews": {name: self.write("original-review-" + name, {"synthetic_review": name})
                        for name in ("source", "result", "learning")}}
        self.metadata.update(mode="accepted_prediction_reference",
            adapter_sources={relative: self.request["files"][relative]},
            accepted_reference={"reference": binding, "acceptance_binding": self.write("accepted", acceptance)})
        self.recommit_metadata()
        with patch.object(p, "_probe", return_value=self.probe()): result = self.invoke()
        self.assertEqual(result["parent"]["mode"], "accepted_prediction_reference")
        (artifacts / "predictions.csv").write_text("changed original bytes\n")
        self.denied("file hash/path drift").assert_not_called()
        acceptance["performance_status"] = "invalid"
        self.metadata["accepted_reference"]["acceptance_binding"] = self.write("accepted", acceptance)
        self.recommit_metadata(); self.denied("acceptance/validity").assert_not_called()

    def test_output_and_broken_symlink_conflicts_denied(self):
        runs = self.batch.root / "runs"; runs.symlink_to(self.root / "absent")
        self.denied("output isolation").assert_not_called(); runs.unlink()
        runs.mkdir(); (runs / "attempt").mkdir()
        self.denied("already occupied").assert_not_called()

    def test_fixed_limits_and_closed_deadline_before_import(self):
        self.request["max_fits"] = 5; self.rebind()
        self.denied("reviewed request").assert_not_called()
        self.request["max_fits"] = 4; self.rebind()
        self.batch = r.ContinuousDiscoveryBatch(self.batch.root, allow_temporary=True,
            test_clock=lambda: datetime.now(timezone.utc) + timedelta(days=1), allow_test_clock=True)
        self.denied("deadline_reached").assert_not_called()

    def test_deadline_crossed_during_import_uses_native_completion_clock(self):
        before = self.batch.snapshot()
        future = datetime.now(timezone.utc) + timedelta(days=1)
        def complete_probe(*_):
            self.batch._clock = lambda: future
            return self.probe()
        self.batch = r.ContinuousDiscoveryBatch(self.batch.root, allow_temporary=True,
            test_clock=lambda: datetime.now(timezone.utc), allow_test_clock=True)
        with patch.object(p, "_probe", side_effect=complete_probe):
            with self.assertRaisesRegex(ValueError, "deadline_reached"): self.invoke()
        self.assertEqual(self.batch.snapshot(), before)

    def test_durable_fit_reservations_not_refunded_before_new_slot(self):
        worker = self.batch.root / "worker"; worker.mkdir()
        for number in range(3):
            (worker / f"old-{number}.request.json").write_text(json.dumps(self.request))
        self.denied("twelve-fit").assert_not_called()
        self.assertEqual(len(list(worker.glob("*.request.json"))), 3)

    def test_missing_alias_target_and_unknown_import_fail_without_slots(self):
        self.alias.unlink()
        before = self.batch.snapshot()
        with self.assertRaises(FileNotFoundError): self.invoke()
        self.assertEqual(self.batch.snapshot(), before)
        self.alias.symlink_to(Path(sys.executable).resolve())
        with patch.object(p, "_probe", side_effect=ValueError("unknown imports")):
            with self.assertRaisesRegex(ValueError, "unknown imports"): self.invoke()
        self.assertEqual(self.batch.snapshot(), before)

    @unittest.skipUnless(PINNED.exists(), "frozen local scientific interpreter unavailable")
    def test_actual_import_only_probe_preserves_pinned_alias(self):
        result = p._probe(str(PINNED), Path(__file__).resolve().parents[3])
        self.assertEqual(result["versions"], p.EXPECTED_VERSIONS)
        self.assertEqual(result["executable"], str(PINNED))

    def test_import_probe_fixed_command_environment_and_timeout_cleanup(self):
        child = Mock(pid=4321, poll=Mock(return_value=None))
        child.wait.side_effect = [subprocess.TimeoutExpired("fixed-import-probe", p.PROBE_SECONDS), -9]
        with patch.object(p.subprocess, "Popen", return_value=child) as launched, \
                patch.object(p.os, "killpg") as killed:
            with self.assertRaisesRegex(ValueError, "import probe timed out"):
                p._probe(str(self.alias), self.repo)
        command = launched.call_args.args[0]
        self.assertEqual(command, [str(self.alias), "-B", "-c", p.PROBE])
        self.assertNotIn(self.request["module"], command[-1])
        self.assertEqual(launched.call_args.kwargs["cwd"], self.repo / "research/market_rsi")
        self.assertEqual(launched.call_args.kwargs["env"], {
            "PATH": "/usr/bin:/bin", "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1", **w.THREADS})
        killed.assert_called_once_with(4321, p.signal.SIGKILL)
        self.assertEqual(child.wait.call_args_list[0].kwargs, {"timeout": 20})

    def test_interrupted_import_probe_kills_original_child_without_retry(self):
        child = Mock(pid=4321, poll=Mock(return_value=None))
        child.wait.side_effect = [KeyboardInterrupt("interrupted import"), -9]
        with patch.object(p.subprocess, "Popen", return_value=child) as launched, \
                patch.object(p.os, "killpg") as killed:
            with self.assertRaises(KeyboardInterrupt): p._probe(str(self.alias), self.repo)
        launched.assert_called_once(); killed.assert_called_once_with(4321, p.signal.SIGKILL)
        self.assertEqual(child.wait.call_count, 2)

    def test_import_probe_version_or_prefix_drift_rejected(self):
        for field, value in (("versions", {**p.EXPECTED_VERSIONS, "sklearn": "wrong"}),
                             ("prefix", "/wrong/prefix"), ("executable", str(self.alias.resolve()))):
            payload = {**self.probe(), field: value}
            def launched(*_, **kwargs):
                kwargs["stdout"].write(json.dumps(payload).encode())
                return Mock(wait=Mock(return_value=0))
            with patch.object(p.subprocess, "Popen", side_effect=launched):
                with self.assertRaisesRegex(ValueError, "alias drift"):
                    p._probe(str(self.alias), self.repo)


if __name__ == "__main__": unittest.main()
