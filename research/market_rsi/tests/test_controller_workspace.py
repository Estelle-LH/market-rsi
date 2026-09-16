from __future__ import annotations

import hashlib
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from controller_tools_mcp import Broker, REQUIRED_DECISION_FIELDS
from controller_workspace import LITERATURE_SCHEMA, prepare_workspace, validate_workspace
from harness_evolution import baseline_profile
from controller_harness_contract import ALLOWED_TOOLS
from market_rsi import canonical, digest


VALID_CANDIDATE = (
    "def fit(train_rows, feature_names):\n    return {}\n\n"
    "def predict(model, public_row):\n    return 0.5\n"
)


def candidate_args(name="candidate.py", content=VALID_CANDIDATE, literature_ids=None):
    return {"name": name, "content": content, "algorithm_family": "fixture",
            "hypothesis": "fixture hypothesis", "literature_ids": literature_ids or [],
            "change_summary": "first fixture candidate"}


def row(name, game, day, x, target):
    decision = day * 86_400_000 + int((x + 1) * 1000)
    return {"row_id": name, "game_id": game, "market_id": game + "-market",
            "decision_ms": decision, "feature_available_ms": decision,
            "features": {"mid": x}, "target": target,
            "label_available_ms": decision + 60_000}


class FormalControllerWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.workspace = root / "controller-session-fixture"
        train = {"schema": "market_permitted_rows_v1", "experiment_id": "source-fixture",
                 "task_id": "task-fixture", "split": "train", "feature_names": ["mid"],
                 "rows": [row("t1", "train-game-1", 1, 0.4, 0.41),
                          row("t2", "train-game-2", 2, 0.5, 0.52)]}
        dev = {"schema": "market_permitted_rows_v1", "experiment_id": "source-fixture",
               "task_id": "task-fixture", "split": "dev", "feature_names": ["mid"],
               "rows": [row("d1", "dev-game", 3, 0.6, 0.61)]}
        train_path, dev_path = root / "train.json", root / "dev.json"
        train_path.write_text(canonical(train))
        dev_path.write_text(canonical(dev))
        abstract = "Calibration methods for probabilistic predictions."
        literature = {"schema": LITERATURE_SCHEMA, "papers": [{
            "paper_id": "paper-1", "title": "Probability calibration", "url": "https://example.org/paper",
            "year": 2020, "abstract": abstract,
            "content_sha256": hashlib.sha256(abstract.encode()).hexdigest()}]}
        prepare_workspace(self.workspace, session_id="controller-session-fixture",
            experiment_id="experiment-fixture", task_id="task-fixture", arm="learn",
            train_path=train_path, dev_path=dev_path, own_history={"rounds": []},
            literature_snapshot=literature, opaque_test_commitment="a" * 64)

    def tearDown(self):
        self.tmp.cleanup()

    def test_visible_data_has_train_labels_but_no_dev_labels(self):
        broker = Broker(self.workspace, "formal")
        summary = broker.call("inspect_train_dev", {})
        self.assertEqual(summary["train"]["rows"], 2)
        self.assertFalse(summary["dev"]["labels_visible"])
        population = summary["open_train_population_audit"]
        self.assertEqual(population["rows"], 2)
        self.assertEqual(population["whole_games"], 2)
        self.assertFalse(population["rows_are_independent_samples"])
        selected = broker.call("inspect_train_dev", {"view": "summary", "split": "train"})
        self.assertEqual(selected["selected_split"], "train")
        train = broker.call("inspect_train_dev", {"view": "rows", "split": "train"})
        dev = broker.call("inspect_train_dev", {"view": "rows", "split": "dev"})
        self.assertIn("target", train["rows"][0])
        self.assertNotIn("target", dev["rows"][0])
        search = broker.call("search_public_literature", {"query": "calibration"})
        self.assertEqual(search["results"][0]["paper_id"], "paper-1")
        guide = broker.call("read_research_guide", {})
        self.assertIn("objective contract", guide["steps"][0])
        objective = broker.call("read_objective_contract", {})
        self.assertEqual(objective["objective_id"], "future-midpoint-point-60s-v1")
        self.assertEqual(guide["memory_mode"], "archive_only")
        self.assertFalse(guide["controller_may_rewrite_this_guide"])
        profile = broker.call("read_harness_profile", {})
        self.assertEqual(profile["generation"], 0)
        self.assertTrue(profile["archive_policy"]["complete_history_retrievable"])
        self.assertTrue(profile["authority_boundary"]["may_propose_new_tools"])
        catalog = broker.call("list_algorithms", {})
        self.assertFalse(catalog["catalog_is_exhaustive"])
        self.assertGreaterEqual(len(catalog["algorithms"]), 6)
        inspected = broker.call(
            "inspect_algorithm", {"algorithm_id": "regularized-linear-model"})
        self.assertEqual(inspected["algorithm"]["family"], "linear")

    def test_execution_result_is_bound_and_final_must_select_executed_candidate(self):
        broker = Broker(self.workspace, "formal")
        broker.call("write_candidate", candidate_args())

        def runner():
            request_path = None
            for _ in range(200):
                paths = list((self.workspace / "execution-requests").glob("*.json"))
                if paths:
                    request_path = paths[0]
                    break
                time.sleep(0.01)
            self.assertIsNotNone(request_path)
            request = json.loads(request_path.read_text())
            result = {"schema": "market_controller_execution_result_v1",
                      "execution_id": request["execution_id"], "request_sha256": digest(request),
                      "candidate_sha256": request["candidate_sha256"],
                      "evaluation_role": "train_cv", "execution_verified": True,
                      "future_test_used": False, "automatic_retry": False, "status": "completed",
                      "score": {"baseline_mse": 0.02, "candidate_mse": 0.01,
                                "prediction_sha256": "c" * 64}}
            path = self.workspace / "execution-results" / (request["execution_id"] + ".json")
            path.write_text(canonical(result))

        thread = threading.Thread(target=runner)
        thread.start()
        result = broker.call("run_train_cv_candidate", {"name": "candidate.py"})
        thread.join()
        self.assertTrue(result["execution_verified"])
        decision = {key: "fixture" for key in REQUIRED_DECISION_FIELDS}
        decision["action"] = "select"
        decision["candidate_artifact"] = "candidate.py"
        self.assertTrue(broker.call("submit_decision", {"decision": decision})["submitted"])

    def test_prediction_identical_duplicate_cannot_replace_earlier_candidate(self):
        broker = Broker(self.workspace, "formal")
        for name in ("first.py", "renamed_copy.py"):
            broker.call("write_candidate", candidate_args(name=name))

            def runner():
                request_path = None
                for _ in range(200):
                    paths = sorted((self.workspace / "execution-requests").glob("*.json"))
                    pending = [path for path in paths if not (
                        self.workspace / "execution-results" / path.name).exists()]
                    if pending:
                        request_path = pending[0]
                        break
                    time.sleep(0.01)
                self.assertIsNotNone(request_path)
                request = json.loads(request_path.read_text())
                result = {"schema": "market_controller_execution_result_v1",
                          "execution_id": request["execution_id"],
                          "request_sha256": digest(request),
                          "candidate_sha256": request["candidate_sha256"],
                          "evaluation_role": "train_cv", "execution_verified": True,
                          "future_test_used": False, "automatic_retry": False,
                          "status": "completed", "score": {
                              "prediction_sha256": "d" * 64,
                              "primary": {"valid": True}}}
                path = self.workspace / "execution-results" / request_path.name
                path.write_text(canonical(result))

            thread = threading.Thread(target=runner)
            thread.start()
            result = broker.call("run_train_cv_candidate", {"name": name})
            thread.join()
            if name == "first.py":
                self.assertTrue(result["prediction_novel"])
                self.assertIsNone(result["prediction_equivalent_to"])
            else:
                self.assertFalse(result["prediction_novel"])
                self.assertEqual(result["prediction_equivalent_to"], "first.py")

        decision = {key: "fixture" for key in REQUIRED_DECISION_FIELDS}
        decision["action"] = "select"
        decision["candidate_artifact"] = "renamed_copy.py"
        with self.assertRaisesRegex(ValueError, "prediction-identical"):
            broker.call("submit_decision", {"decision": decision})
        decision["candidate_artifact"] = "first.py"
        self.assertTrue(broker.call("submit_decision", {"decision": decision})["submitted"])

    def test_input_tampering_and_unexecuted_final_candidate_fail_closed(self):
        broker = Broker(self.workspace, "formal")
        broker.call("write_candidate", candidate_args())
        decision = {key: "fixture" for key in REQUIRED_DECISION_FIELDS}
        decision["action"] = "select"
        decision["candidate_artifact"] = "candidate.py"
        with self.assertRaisesRegex(ValueError, "not independently executed"):
            broker.call("submit_decision", {"decision": decision})
        history = self.workspace / "own-history.json"
        history.write_text('{"rounds":["tampered"]}')
        with self.assertRaisesRegex(ValueError, "visible input changed"):
            validate_workspace(self.workspace)

    def test_archive_history_cannot_move_to_a_different_h0_profile(self):
        root = Path(self.tmp.name)
        profile = baseline_profile(ALLOWED_TOOLS)
        wrong = {"schema": "market_controller_history_v2",
                 "lineage_id": "lineage-fixture", "harness_profile_sha256": "0" * 64,
                 "source_manifest_sha256": "1" * 64, "snapshots": []}
        train = root / "train.json"
        dev = root / "dev.json"
        with self.assertRaisesRegex(ValueError, "different H0"):
            prepare_workspace(root / "wrong-h0", session_id="wrong-h0-session",
                experiment_id="experiment-fixture", task_id="task-fixture", arm="learn",
                train_path=train, dev_path=dev, own_history=wrong,
                literature_snapshot={"schema": LITERATURE_SCHEMA, "papers": []},
                opaque_test_commitment="a" * 64, harness_profile=profile)


if __name__ == "__main__":
    unittest.main()
