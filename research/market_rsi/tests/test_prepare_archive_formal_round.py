import asyncio
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from build_archive_formal_data import build
from build_archive_continuation_data import build as build_continuation
from controller_tools_mcp import Broker, REQUIRED_DECISION_FIELDS
from controller_execution_service import validate_runner_config
from finalize_archive_formal_round import finalize
from formal_round_binding import validate_binding
from market_rsi import digest, fresh_json
from objective_contract import freeze_objective_contract
from paid_budget import PaidBudget
from prepare_archive_formal_round import prepare
from prospective_data_lifecycle import ProspectiveDataLifecycle
from prospective_sealed_dev_runner import run_once as run_dev_once
from sealed_dev_runner import _validate_config
from research.market_rsi.tests.test_formal_round_binding import _source


class PrepareArchiveFormalRoundTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        source = _source()
        self.source = self.root / "source.json"
        self.source.write_text(json.dumps(source))
        self.data = self.root / "data"
        build([(self.source, source)], self.data, "experiment")
        self.budget_root = self.root / "budget"
        self.budget = PaidBudget.create(self.budget_root, {
            "experiment_id": "experiment", "cap_usd": "20", "target_usd": "10",
            "buckets_usd": {"setup": "2", "learning": "12",
                            "final": "4", "repair": "2"},
            "authority": "test fixture",
        })
        self.env = self.root / ".env"
        self.env.write_text("TINKER_API_KEY=fixture\nE2B_API_KEY=fixture\n")
        self.cache = self.root / "tokenizer-cache"
        self.cache.mkdir()
        self.study = self.root / "study"
        self.objective = self.root / "objective.json"
        freeze_objective_contract(
            self.objective,
            experiment_id="experiment",
            objective_id="future-midpoint-point-60s-v1",
            train_diagnostics_sha256="a" * 64,
            literature_snapshot_sha256="b" * 64,
            literature_ids=[],
            evidence_class="formal_learning",
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_round_one_preparation_is_unpaid_and_fully_bound(self):
        receipt = prepare(self.study, self.data, self.budget_root, self.env,
                          self.cache, Path(sys.executable), "round-01",
                          objective_contract_path=self.objective)
        self.assertEqual(receipt["model_calls"], 0)
        self.assertEqual(receipt["candidate_executions"], 0)
        self.assertEqual(receipt["dev_executions"], 0)
        self.assertFalse(receipt["future_test_used"])
        round_root = self.study / "rounds/round-01"
        binding = validate_binding(round_root / "round-binding.json")
        config = validate_runner_config(round_root / "runner-config.json",
                                        round_root / "workspace")
        self.assertEqual(config["evidence_class"], "formal_learning")
        self.assertEqual(config["train_sha256"], binding["train_sha256"])
        public = json.loads((round_root / "workspace/train-dev-public.json").read_text())
        self.assertTrue(all("target" not in row for row in public["dev"]))
        self.assertEqual(self.budget.snapshot()["jobs"], {})
        self.assertTrue((self.study / "submissions/a0.json").is_file())
        session = round_root / "session"
        session.mkdir()
        fresh_json(session / "assessment.json", {
            "valid": True, "process_reaped": True,
            "submitted_decision_present": True,
            "controller_integrity": {"valid": True}})
        sealed, _ = _validate_config(round_root / "sealed-dev-config.json",
                                     round_root / "workspace",
                                     ProspectiveDataLifecycle)
        self.assertEqual(sealed["round_binding_sha256"],
                         receipt["round_binding_sha256"])

    def test_round_one_cannot_reuse_a_study_id(self):
        prepare(self.study, self.data, self.budget_root, self.env,
                self.cache, Path(sys.executable), "round-01",
                objective_contract_path=self.objective)
        with self.assertRaisesRegex(ValueError, "fresh formal study root"):
            prepare(self.study, self.data, self.budget_root, self.env,
                    self.cache, Path(sys.executable), "round-01",
                    objective_contract_path=self.objective)

    def test_repaired_continuation_starts_with_prior_candidate_as_a0(self):
        continuation = self.root / "continuation-data"
        build_continuation(self.data, continuation, "round-02")
        seed = self.root / "prior-a1.py"
        seed.write_text("def fit(train_rows, feature_names):\n    return None\n\n"
                        "def predict(model, public_row):\n"
                        "    return public_row['features']['mid']\n")
        repaired = self.root / "repaired-study"
        receipt = prepare(repaired, continuation, self.budget_root, self.env,
                          self.cache, Path(sys.executable), "round-02",
                          seed_candidate_path=seed,
                          objective_contract_path=self.objective)
        a0 = json.loads((repaired / "submissions/a0.json").read_text())
        self.assertEqual(receipt["round_index"], 0)
        self.assertEqual(a0["origin"], "validated-prior-study-seed")
        self.assertEqual((repaired / "submissions/a0-persistence.py").read_text(),
                         seed.read_text())

    def test_completed_round_freezes_archive_and_a1(self):
        prepare(self.study, self.data, self.budget_root, self.env,
                self.cache, Path(sys.executable), "round-01",
                objective_contract_path=self.objective)
        round_root = self.study / "rounds/round-01"
        workspace = round_root / "workspace"
        broker = Broker(workspace, "formal")
        source = ("def fit(train_rows, feature_names):\n    return None\n\n"
                  "def predict(model, public_row):\n"
                  "    return public_row['features']['mid']\n")
        broker.call("write_candidate", {"name": "formal_v1.py", "content": source,
            "algorithm_family": "persistence", "hypothesis": "stable reference",
            "literature_ids": [], "change_summary": "formal fixture"})

        def complete_cv():
            for _ in range(300):
                requests = list((workspace / "execution-requests").glob("*.json"))
                if requests:
                    request = json.loads(requests[0].read_text())
                    fresh_json(workspace / "execution-results" / requests[0].name, {
                        "schema": "market_controller_execution_result_v1",
                        "execution_id": request["execution_id"],
                        "request_sha256": digest(request),
                        "candidate_sha256": request["candidate_sha256"],
                        "evaluation_role": "train_cv", "execution_verified": True,
                        "future_test_used": False, "automatic_retry": False,
                        "status": "completed", "failure": None,
                        "job_claim_sha256": "a" * 64,
                        "score": {"primary": {"valid": True},
                                  "prediction_sha256": "c" * 64}})
                    return
                time.sleep(.01)

        thread = threading.Thread(target=complete_cv)
        thread.start()
        broker.call("run_train_cv_candidate", {"name": "formal_v1.py"})
        thread.join()
        decision = {key: "fixture" for key in REQUIRED_DECISION_FIELDS}
        decision["action"] = "select"
        decision["candidate_artifact"] = "formal_v1.py"
        broker.call("submit_decision", {"decision": decision})

        session = round_root / "session"
        turn = session / "turn-001"
        turn.mkdir(parents=True)
        fresh_json(turn / "request.json", {"fixture": True})
        fresh_json(turn / "response.json", {"text": "done", "receipt": {
            "terminal": True, "provider": "tinker", "metered_cost_usd": "0.01"}})
        fresh_json(turn / "assessment.json", {"valid": True})
        source_manifest = json.loads((self.study / "source-manifest.json").read_text())
        fresh_json(session / "assessment.json", {
            "valid": True, "process_reaped": True,
            "submitted_decision_present": True,
            "controller_integrity": broker.log_assessment()["controller_integrity"],
            "source_manifest": source_manifest})
        score = {"evaluation_role": "sealed_dev", "primary": {"valid": True},
                 "coverage": {"coverage_fraction": 1.0}}
        with patch("sealed_dev_runner.run_job", AsyncMock(return_value=score)):
            asyncio.run(run_dev_once(workspace, round_root / "sealed-dev-config.json",
                                     round_root / "sealed-dev"))
        receipt = finalize(self.study, "round-01")
        self.assertEqual(receipt["submission_id"], "a1")
        history = json.loads((round_root / "archive-history.json").read_text())
        self.assertEqual(len(history["snapshots"]), 1)
        self.assertTrue((self.study / "submissions/a1.json").is_file())
        next_receipt = prepare(
            self.study, self.data, self.budget_root, self.env, self.cache,
            Path(sys.executable), "round-02", round_root / "archive-history.json")
        next_root = self.study / "rounds/round-02"
        next_binding = validate_binding(next_root / "round-binding.json")
        self.assertEqual(next_receipt["round_index"], 1)
        self.assertEqual(next_binding["train_rows"], 360)
        self.assertEqual(len(json.loads(
            (next_root / "workspace/own-history.json").read_text())["snapshots"]), 1)


if __name__ == "__main__":
    unittest.main()
