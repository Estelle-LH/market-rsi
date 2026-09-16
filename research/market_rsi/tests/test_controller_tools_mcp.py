from __future__ import annotations

import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from controller_activity_log import read_activity_events
from controller_tools_mcp import Broker, REQUIRED_DECISION_FIELDS, serve
from controller_tools_mcp import TOOLS


VALID_CANDIDATE = (
    "def fit(train_rows, feature_names):\n    return {}\n\n"
    "def predict(model, public_row):\n    return 0.5\n"
)


def candidate_args(name="candidate.py", content=VALID_CANDIDATE, literature_ids=None):
    return {"name": name, "content": content, "algorithm_family": "fixture",
            "hypothesis": "fixture hypothesis", "literature_ids": literature_ids or [],
            "change_summary": "first fixture candidate"}


class ControllerToolBrokerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name)
        (self.workspace / "train-dev-summary.json").write_text(
            json.dumps({"train_rows": 10, "dev_rows": 5}))
        (self.workspace / "own-history.json").write_text(json.dumps({"rounds": []}))
        self.broker = Broker(self.workspace, "canary")

    def tearDown(self):
        self.tmp.cleanup()

    def test_complete_canary_tool_path(self):
        self.assertEqual(self.broker.call("inspect_train_dev", {}),
                         {"train_rows": 10, "dev_rows": 5})
        profile = self.broker.call("read_harness_profile", {})
        self.assertEqual(profile["schema"], "synthetic-harness-profile")
        guide = self.broker.call("read_research_guide", {})
        self.assertEqual(guide["schema"], "synthetic-guide")
        literature = self.broker.call("search_public_literature", {"query": "calibration"})
        self.assertEqual(literature["query"], "calibration")
        catalog = self.broker.call("list_algorithms", {})
        self.assertEqual(catalog["algorithms"][0]["algorithm_id"], "fixture-baseline")
        inspected = self.broker.call(
            "inspect_algorithm", {"algorithm_id": "fixture-baseline"})
        self.assertEqual(inspected["algorithm"]["family"], "baseline")
        self.broker.call("write_candidate", candidate_args(
            literature_ids=["offline-canary-paper"]))
        result = self.broker.call("run_train_cv_candidate", {"name": "candidate.py"})
        self.assertEqual(result["status"], "completed")
        with self.assertRaisesRegex(ValueError, "already executed"):
            self.broker.call("run_train_cv_candidate", {"name": "candidate.py"})
        self.assertEqual(self.broker.call("read_own_research_history", {}), {"rounds": []})
        decision = {key: "fixture" for key in REQUIRED_DECISION_FIELDS}
        decision["action"] = "select"
        decision["candidate_artifact"] = "candidate.py"
        self.assertTrue(self.broker.call("submit_decision", {"decision": decision})["submitted"])
        assessment = self.broker.log_assessment()
        self.assertTrue(assessment["valid"])
        self.assertEqual(assessment["selected_candidate"], "candidate.py")

    def test_archive_controller_can_choose_candidate_without_literature_or_catalog(self):
        self.broker.call("write_candidate", candidate_args())
        self.broker.call("run_train_cv_candidate", {"name": "candidate.py"})
        decision = {key: "fixture" for key in REQUIRED_DECISION_FIELDS}
        decision["action"] = "select"
        decision["candidate_artifact"] = "candidate.py"
        self.broker.call("submit_decision", {"decision": decision})
        assessment = self.broker.log_assessment()
        self.assertTrue(assessment["valid"])
        self.assertEqual(assessment["optional_research_actions"], {
            "literature_searches": 0,
            "algorithm_catalog_lists": 0,
            "algorithm_catalog_inspections": 0,
        })

    def test_submit_schema_tells_controller_every_required_field(self):
        tool = next(item for item in TOOLS if item["name"] == "submit_decision")
        decision = tool["inputSchema"]["properties"]["decision"]
        self.assertEqual(set(decision["required"]), REQUIRED_DECISION_FIELDS)
        self.assertEqual(set(decision["properties"]), REQUIRED_DECISION_FIELDS)
        self.assertEqual(decision["properties"]["action"]["enum"], ["select"])
        self.assertIn("\\.py", decision["properties"]["candidate_artifact"]["pattern"])

    def test_candidate_schema_requires_research_rationale(self):
        tool = next(item for item in TOOLS if item["name"] == "write_candidate")
        required = set(tool["inputSchema"]["required"])
        self.assertEqual(required, {"name", "content", "algorithm_family", "hypothesis",
                                    "literature_ids", "change_summary"})

    def test_paths_and_duplicate_claims_fail(self):
        for name in ("../escape.py", "/tmp/escape.py", ".hidden.py"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.broker.call("write_candidate", candidate_args(name, "x"))
        self.broker.call("write_candidate", candidate_args("claimed.py"))
        with self.assertRaisesRegex(ValueError, "already claimed"):
            self.broker.call("write_candidate", candidate_args("claimed.py", "y"))
    def test_decision_schema_is_exact_and_single_use(self):
        with self.assertRaisesRegex(ValueError, "requires exactly"):
            self.broker.call("submit_decision", {"decision": {"action": "x"}})
        decision = {key: "fixture" for key in REQUIRED_DECISION_FIELDS}
        decision["action"] = "select"
        decision["candidate_artifact"] = "candidate.py"
        self.broker.call("write_candidate", candidate_args())
        self.broker.call("run_train_cv_candidate", {"name": "candidate.py"})
        self.broker.call("submit_decision", {"decision": decision})
        with self.assertRaisesRegex(ValueError, "already submitted"):
            self.broker.call("submit_decision", {"decision": decision})

    def test_decorated_executed_candidate_is_normalized_and_audited(self):
        self.broker.call("write_candidate", candidate_args())
        self.broker.call("run_train_cv_candidate", {"name": "candidate.py"})
        decision = {key: "fixture" for key in REQUIRED_DECISION_FIELDS}
        decision["action"] = "select"
        decision["candidate_artifact"] = "candidate.py (source hash and execution receipt)"
        self.broker.call("submit_decision", {"decision": decision})
        stored = json.loads((self.workspace / "submitted-decision.json").read_text())
        self.assertEqual(stored["candidate_artifact"], "candidate.py")
        selected = [event for event in read_activity_events(
                    self.workspace / "algorithm-activity.jsonl")
                    if event["kind"] == "candidate_selected"][0]
        self.assertTrue(selected["candidate_artifact_normalized"])

    def test_validation_error_is_returned_as_recoverable_tool_evidence(self):
        request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                   "params": {"name": "run_train_cv_candidate",
                              "arguments": {"name": "missing.py"}}}
        output = StringIO()
        with patch("sys.stdin", StringIO(json.dumps(request) + "\n")), \
                patch("sys.stdout", output):
            serve(self.broker)
        reply = json.loads(output.getvalue())
        self.assertNotIn("error", reply)
        self.assertFalse(reply["result"]["isError"])
        evidence = json.loads(reply["result"]["content"][0]["text"])
        self.assertEqual(evidence["accepted"], False)
        self.assertEqual(evidence["recoverable"], True)
        self.assertIn("does not exist", evidence["message"])


if __name__ == "__main__":
    unittest.main()
