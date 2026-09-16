import copy
from datetime import datetime, timedelta, timezone
import json
import tempfile
import unittest
from pathlib import Path

from market_rsi import digest, file_hash, fresh_json
from paid_budget import PaidBudget
import scientific_admission as admission
import development_harbor


class ScientificAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.study = self.root / "study"
        self.runner = self.root / "runner"
        self.study.mkdir()
        self.runner.mkdir()
        self.deadline = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        self.manifest = {"schema": "market_study_state_v1", "experiment_id": "live-study-01",
            "deadline_utc": self.deadline, "tasks": [{"task_id": "task-01"}]}
        fresh_json(self.study / "manifest.json", self.manifest)
        self.budget = PaidBudget.create(self.root / "budget", {"experiment_id": "live-study-01",
            "cap_usd": "20", "target_usd": "10", "buckets_usd": {"learning": "15", "final": "5"},
            "authority": "fixture-only admission test"})
        data = self.root / "train.json"
        data.write_text('{"fixture":true}\n')
        self.config = {"schema": "market_study_runner_v1", "experiment_id": "live-study-01",
            "study_path": str(self.study), "budget_path": str(self.budget.root),
            "deadline_utc": self.deadline, "task_data": {"task-01": {"train_path": str(data)}},
            "runtime": {"model": "fixture"}, "coder_limits": {"wall_seconds": 1},
            "coder_identity": {"model": "fixture"}, "source_hashes": {"worker.py": "a" * 64},
            "worst_case_step_seconds": 60, "end_to_end_wall_enforcement_verified": True}
        fresh_json(self.runner / "config.json", self.config)
        fresh_json(self.runner / "config-commitment.json", {"sha256": digest(self.config)})
        self.evidence = []
        for index, kind in enumerate(sorted(admission.EVIDENCE_KINDS)):
            path = self.root / ("evidence-" + str(index) + ".json")
            path.write_text(json.dumps({"kind": kind, "fixture": True}))
            self.evidence.append({"kind": kind, "path": str(path), "sha256": file_hash(path)})
        self.receipt = {"schema": admission.SCHEMA, "experiment_id": "live-study-01",
            "created_at_utc": datetime.now(timezone.utc).isoformat(), "deadline_utc": self.deadline,
            "evidence_class": "reviewed_historical_source", "review_id": "fixture-review-01",
            "reviewer_role": "trusted_runner_reviewer", "checks": {k: True for k in admission.CHECKS},
            "evidence_files": self.evidence, "study_manifest_sha256": digest(self.manifest),
            "runner_config_sha256": digest(self.config), "task_data_sha256": digest(self.config["task_data"]),
            "runtime_sha256": digest(self.config["runtime"]), "coder_limits_sha256": digest(self.config["coder_limits"]),
            "coder_identity_sha256": digest(self.config["coder_identity"]),
            "worker_source_hashes_sha256": digest(self.config["source_hashes"]),
            "budget_cap_usd": "20", "test_set_opened": False, "external_results_seen": False,
            "scientific_admission": True}
        self.reviewed = self.root / "reviewed.json"
        fresh_json(self.reviewed, self.receipt)

    def tearDown(self):
        self.tmp.cleanup()

    def test_install_and_every_dispatch_readback(self):
        installed = admission.install_admission(self.runner, self.reviewed)
        self.assertEqual(installed, self.receipt)
        self.assertEqual(admission.verify_installed_admission(self.runner), self.receipt)
        self.assertEqual(admission.owning_runner(self.runner / "jobs/task-01/sandbox"), self.runner)
        with self.assertRaises(FileExistsError):
            admission.install_admission(self.runner, self.reviewed)

    def test_research_and_coder_nested_audit_claims_are_admitted(self):
        admission.install_admission(self.runner, self.reviewed)
        job = self.runner / "jobs" / "task-01" / "research"
        job.mkdir(parents=True)
        fresh_json(job / "claim.json", {"audit": {"experiment_id": "live-study-01"}})
        self.assertEqual(development_harbor.require_admission(job), self.receipt)
        other = self.runner / "jobs" / "task-02" / "research"
        other.mkdir(parents=True)
        fresh_json(other / "claim.json", {"audit": {"experiment_id": "other-study"}})
        with self.assertRaisesRegex(ValueError, "another admitted experiment"):
            development_harbor.require_admission(other)

    def test_missing_receipt_keeps_gate_closed(self):
        with self.assertRaisesRegex(RuntimeError, "unavailable"):
            admission.verify_installed_admission(self.runner)

    def test_changed_evidence_invalidates_installed_receipt(self):
        admission.install_admission(self.runner, self.reviewed)
        Path(self.evidence[0]["path"]).write_text("changed")
        with self.assertRaisesRegex(ValueError, "evidence changed"):
            admission.verify_installed_admission(self.runner)

    def test_one_false_check_is_not_admission(self):
        value = copy.deepcopy(self.receipt)
        value["checks"]["reconnect_requires_fresh_snapshot"] = False
        with self.assertRaisesRegex(ValueError, "all independent"):
            admission.validate_receipt(value, self.config, self.manifest, self.budget)

    def test_test_or_result_access_is_too_late(self):
        for key in ("test_set_opened", "external_results_seen"):
            value = copy.deepcopy(self.receipt)
            value[key] = True
            with self.assertRaisesRegex(ValueError, "cannot follow"):
                admission.validate_receipt(value, self.config, self.manifest, self.budget)

    def test_unverified_whole_step_deadline_stays_closed(self):
        config = copy.deepcopy(self.config)
        config["end_to_end_wall_enforcement_verified"] = False
        value = copy.deepcopy(self.receipt)
        value["runner_config_sha256"] = digest(config)
        with self.assertRaisesRegex(ValueError, "deadline enforcement"):
            admission.validate_receipt(value, config, self.manifest, self.budget)

    def test_changed_task_or_budget_identity_is_rejected(self):
        value = copy.deepcopy(self.receipt)
        value["task_data_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "task_data"):
            admission.validate_receipt(value, self.config, self.manifest, self.budget)
        value = copy.deepcopy(self.receipt)
        value["budget_cap_usd"] = "200"
        with self.assertRaisesRegex(ValueError, "budget_cap"):
            admission.validate_receipt(value, self.config, self.manifest, self.budget)


if __name__ == "__main__":
    unittest.main()
