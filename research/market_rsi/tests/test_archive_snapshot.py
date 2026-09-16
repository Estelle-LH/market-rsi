from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from archive_snapshot import (append_snapshot, assess_carryover, build_snapshot,
                              empty_history, validate_history, validate_snapshot)
from controller_activity_log import read_activity_events
from controller_tools_mcp import Broker, REQUIRED_DECISION_FIELDS
from controller_workspace import LITERATURE_SCHEMA, prepare_workspace
from market_rsi import canonical, digest, fresh_json


def row(name, game, day, value, target):
    decision = day * 86_400_000 + int(value * 1000)
    return {"row_id": name, "game_id": game, "market_id": game + "-market",
            "decision_ms": decision, "feature_available_ms": decision,
            "features": {"mid": value}, "target": target,
            "label_available_ms": decision + 60_000}


class ArchiveSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source_manifest = self.root / "source-manifest.json"
        fresh_json(self.source_manifest, {
            "schema": "market_controller_source_manifest_v1",
            "sources": {"fixture.py": "a" * 64},
        })
        self.literature = {"schema": LITERATURE_SCHEMA, "papers": []}

    def tearDown(self):
        self.tmp.cleanup()

    def make_workspace(self, session_id, task_id, own_history):
        train = {"schema": "market_permitted_rows_v1", "experiment_id": "source-fixture",
                 "task_id": task_id, "split": "train", "feature_names": ["mid"],
                 "rows": [row("t1-" + task_id, "train1-" + task_id, 1, .4, .41),
                          row("t2-" + task_id, "train2-" + task_id, 2, .5, .51)]}
        dev = {"schema": "market_permitted_rows_v1", "experiment_id": "source-fixture",
               "task_id": task_id, "split": "dev", "feature_names": ["mid"],
               "rows": [row("d-" + task_id, "dev-" + task_id, 3, .6, .61)]}
        train_path = self.root / f"{task_id}-train.json"
        dev_path = self.root / f"{task_id}-dev.json"
        train_path.write_text(canonical(train))
        dev_path.write_text(canonical(dev))
        workspace = self.root / (session_id + "-workspace")
        prepare_workspace(workspace, session_id=session_id,
            experiment_id="experiment-fixture", task_id=task_id, arm="archive",
            train_path=train_path, dev_path=dev_path, own_history=own_history,
            literature_snapshot=self.literature, opaque_test_commitment="f" * 64)
        return workspace

    def complete(self, workspace, candidate, archive_parent=None):
        broker = Broker(workspace, "formal")
        broker.call("read_own_research_history", {})
        arguments = {"name": candidate, "content": (
                         "def fit(train_rows, feature_names): return {}\n"
                         "def predict(model, public_row): return 0.5\n"),
                     "algorithm_family": "fixture", "hypothesis": "test inheritance",
                     "literature_ids": [], "change_summary": "one immutable change"}
        if archive_parent is not None:
            arguments["archive_parent"] = archive_parent
        broker.call("write_candidate", arguments)

        def runner():
            request_path = None
            for _ in range(200):
                paths = list((workspace / "execution-requests").glob("*.json"))
                if paths:
                    request_path = paths[0]
                    break
                time.sleep(.01)
            request = json.loads(request_path.read_text())
            result = {"schema": "market_controller_execution_result_v1",
                      "execution_id": request["execution_id"],
                      "request_sha256": digest(request),
                      "candidate_sha256": request["candidate_sha256"],
                      "evaluation_role": "train_cv", "execution_verified": True,
                      "future_test_used": False,
                      "automatic_retry": False, "status": "completed",
                      "score": {"primary": {"valid": True, "mse": .01},
                                "prediction_sha256": "c" * 64}}
            fresh_json(workspace / "execution-results" / request_path.name, result)

        thread = threading.Thread(target=runner)
        thread.start()
        broker.call("run_train_cv_candidate", {"name": candidate})
        thread.join()
        decision = {key: "fixture" for key in REQUIRED_DECISION_FIELDS}
        decision["action"] = "select"
        decision["candidate_artifact"] = candidate
        broker.call("submit_decision", {"decision": decision})

    def make_session(self, name):
        output = self.root / (name + "-output")
        turn = output / "turn-001"
        turn.mkdir(parents=True)
        fresh_json(turn / "request.json", {"turn": 1, "input": "fixture"})
        fresh_json(turn / "response.json", {"text": "fixture controller record",
            "receipt": {"terminal": True, "provider": "tinker",
                        "metered_cost_usd": "0.01", "prompt_tokens": 10,
                        "output_tokens": 5}})
        fresh_json(turn / "assessment.json", {"valid": True, "kind": "function_calls"})
        fresh_json(output / "assessment.json", {"valid": True})
        prompt = self.root / (name + "-prompt.txt")
        prompt.write_text("fixture prompt")
        return output, prompt

    def test_complete_snapshot_carries_to_second_round_and_binds_parent(self):
        first = self.make_workspace("session-a0", "task-a0", {"rounds": []})
        self.complete(first, "first.py")
        session, prompt = self.make_session("session-a0")
        snapshot = build_snapshot(self.root / "a0-snapshot.json", workspace=first,
            session_output=session, prompt_path=prompt,
            source_manifest_path=self.source_manifest, lineage_id="lineage-fixture",
            round_index=0, previous_snapshot_sha256=None)
        history = append_snapshot(empty_history(
            lineage_id="lineage-fixture",
            harness_profile_sha256=snapshot["harness_profile_sha256"],
            source_manifest_sha256=snapshot["source_manifest_sha256"]), snapshot)

        second = self.make_workspace("session-a1", "task-a1", history)
        parent = snapshot["candidates"][0]
        reference = {"session_id": snapshot["session_id"],
                     "candidate": parent["candidate"],
                     "source_sha256": parent["source_sha256"]}
        self.complete(second, "second.py", archive_parent=reference)
        readback = Broker(second, "formal").call("read_own_research_history", {})
        self.assertEqual(readback, history)
        events = read_activity_events(second / "algorithm-activity.jsonl")
        written = next(event for event in events if event["kind"] == "candidate_written")
        self.assertEqual(written["archive_parent"], reference)
        self.assertEqual(written["parent_source_sha256"], parent["source_sha256"])
        carryover = assess_carryover(second)
        self.assertTrue(carryover["valid"])
        self.assertEqual(carryover["archive_parent"], reference)

    def test_snapshot_and_history_tampering_fail_closed(self):
        workspace = self.make_workspace("session-a0", "task-a0", {"rounds": []})
        self.complete(workspace, "first.py")
        session, prompt = self.make_session("session-a0")
        snapshot = build_snapshot(self.root / "snapshot.json", workspace=workspace,
            session_output=session, prompt_path=prompt,
            source_manifest_path=self.source_manifest, lineage_id="lineage-fixture",
            round_index=0, previous_snapshot_sha256=None)
        changed = copy.deepcopy(snapshot)
        changed["candidates"][0]["source"] += "# changed\n"
        with self.assertRaisesRegex(ValueError, "integrity changed"):
            validate_snapshot(changed)
        history = append_snapshot(empty_history(
            lineage_id="lineage-fixture",
            harness_profile_sha256=snapshot["harness_profile_sha256"],
            source_manifest_sha256=snapshot["source_manifest_sha256"]), snapshot)
        history["harness_profile_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "lineage chain changed"):
            validate_history(history)

    def test_later_snapshot_requires_exact_previous_hash(self):
        with self.assertRaisesRegex(ValueError, "previous hash"):
            build_snapshot(self.root / "bad.json", workspace=self.root,
                session_output=self.root, prompt_path=self.root / "missing",
                source_manifest_path=self.source_manifest, lineage_id="lineage-fixture",
                round_index=1, previous_snapshot_sha256=None)


if __name__ == "__main__":
    unittest.main()
