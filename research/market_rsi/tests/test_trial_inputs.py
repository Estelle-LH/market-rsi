import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from coder_worker import dispatch_code_once
from inspection_stream import inspect_once
from market_harbor import fixture_packet
from market_rsi import digest
from paid_budget import PaidBudget
from prediction_stream import PUBLIC_FIELDS, PredictionJournal, encoded, fingerprint, predict_stream
from research_context import freeze_common
from researcher_worker import dispatch_once, prepare_request
from trial_inputs import execution_profile, prepare_development_trial
from worker_receipts import code_request_from_job
from test_coder_worker import FakeCoder, LIMITS, RUNTIME, SOURCE
from test_researcher_worker import FakeTransport, proposal, task
from test_worker_receipts import INSPECT_CODE


PROFILE = {"cpu_seconds": 120, "memory_mb": 512,
           "prediction": {"fit_timeout_seconds": 5, "predict_timeout_seconds": 2,
                          "wall_seconds": 15, "max_request_bytes": 65536},
           "inspection": {"timeout_seconds": 15, "max_request_bytes": 65536,
                          "max_response_bytes": 16384, "max_json_nodes": 1000, "max_json_depth": 8}}


class TrialInputsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.common = self.root / "common.json"
        freeze_common(self.common)
        self.budget = PaidBudget.create(self.root / "budget", {
            "experiment_id": "fixture-research", "cap_usd": "2", "target_usd": "1",
            "buckets_usd": {"learning": "1", "final": "1"}, "authority": "synthetic local integration"})
        p = fixture_packet()
        dev = [dict(r, target=r["features"]["x"], label_available_ms=r["decision_ms"] + 60000)
               for r in p["evaluation"]]
        self.artifacts = {kind: {"schema": "market_permitted_rows_v1", "experiment_id": "fixture-research",
            "task_id": "task-0", "split": kind, "feature_names": ["x"], "rows": rows}
            for kind, rows in (("train", p["train"]), ("dev", dev))}
        self.runtime = dict(copy.deepcopy(RUNTIME), execution_limits=copy.deepcopy(PROFILE))

    def tearDown(self):
        self.tmp.cleanup()

    def jobs(self, action="experiment", arm="learn", prepared_research=None):
        t = task()
        blobs = {kind: encoded(value) for kind, value in self.artifacts.items()}
        for item in t["data_catalog"]:
            item["sha256"] = hashlib.sha256(blobs[item["split"]]).hexdigest()
        prepared = prepared_research or prepare_request(
            self.common, arm=arm, task=t, step_index=0, records=[])
        rdir, cdir = self.root / f"research-{arm}", self.root / f"coder-{arm}"
        p = dict(proposal(), action=action)
        rt = FakeTransport(text=json.dumps(p))
        dispatch_once(prepared, rt, self.budget, rdir)
        _, coding = code_request_from_job(rdir, prepared, self.budget, self.runtime, LIMITS, expected_live=False)
        ct = FakeCoder({"status": "implemented", "code": SOURCE if action == "experiment" else INSPECT_CODE,
                        "notes": "human-authored fixture, not an LLM experiment"})
        dispatch_code_once(coding, ct, cdir)
        return {"research_directory": rdir, "coding_directory": cdir, "prepared_research": prepared,
                "budget": self.budget, "frozen_runtime": self.runtime, "frozen_coder_limits": LIMITS,
                "expected_live": False, "expected_coder_identity": ct.check_ready(),
                "train_id": "train", "train_bytes": blobs["train"], "dev_id": "dev", "dev_bytes": blobs["dev"]}

    def test_exact_source_and_bound_prediction_inputs_from_completed_jobs(self):
        trial = prepare_development_trial(**self.jobs())
        self.assertEqual(trial["candidate_source"], SOURCE)
        self.assertEqual(trial["binding"]["candidate_sha256"], hashlib.sha256(SOURCE.encode()).hexdigest())
        self.assertEqual(trial["binding"]["execution_packet_sha256"], fingerprint(trial["packet"]))
        self.assertTrue(all("target" not in row and "label_available_ms" not in row
                            for row in trial["packet"]["evaluation"]))
        self.assertFalse(trial["binding"]["scientific_admission"])
        self.assertFalse(trial["binding"]["library_availability_verified"])
        self.assertFalse(trial["executed"])

    def test_all_arms_start_with_same_execution_payload(self):
        results = [prepare_development_trial(**self.jobs(arm=arm)) for arm in ("reset", "archive", "learn")]
        self.assertEqual(len({fingerprint(r["packet"]) for r in results}), 1)
        self.assertEqual([r["binding"]["owner"]["arm"] for r in results], ["reset", "archive", "learn"])

    def test_completed_research_coding_to_sequential_protocol_without_any_provider_or_code_execution(self):
        trial = prepare_development_trial(**self.jobs())
        packet = trial["packet"]
        log = PredictionJournal(self.root / "predictions", train_sha256=fingerprint(packet["train"]),
            evaluation_sha256=fingerprint(packet["evaluation"]), candidate_sha256=trial["binding"]["candidate_sha256"],
            expected_predictions=3)
        requests = []
        def human_fixture(request, timeout):
            requests.append(copy.deepcopy(request))
            if request["type"] == "fit":
                return {"type": "fitted", "request_id": request["request_id"]}
            self.assertEqual(log.count, len(requests) - 2)  # Previous result committed first.
            return {"type": "prediction", "request_id": request["request_id"],
                    "row_id": request["row"]["row_id"], "prediction": 0.0}
        result = predict_stream(human_fixture, log.commit, packet["train"], packet["evaluation"],
                                packet["feature_names"], **packet["limits"])
        self.assertEqual(log.finish()["predictions"], 3)
        self.assertFalse(result["scored"])
        self.assertEqual(len(requests), 4)
        self.assertEqual(len(self.budget.snapshot()["jobs"]), 1)  # Only mock research metering.

    def test_completed_inspection_protocol_withholds_dev_labels(self):
        trial = prepare_development_trial(**self.jobs(action="inspect"))
        packet = trial["packet"]
        self.assertTrue(all(set(row) == PUBLIC_FIELDS for row in packet["payload"]["dev"]))
        self.assertTrue(all("target" not in row and "label_available_ms" not in row
                            for row in packet["payload"]["dev"]))
        def human_fixture(request, timeout):
            return {"type": "inspection", "request_id": request["request_id"],
                    "diagnostic": {"rows": len(request["train"]) + len(request["dev"]), "passed": True}}
        result = inspect_once(human_fixture, packet)
        self.assertEqual(result["diagnostic"]["rows"], 5)
        self.assertFalse(result["scientific_admission"])
        self.assertIsNone(result["independent_score"])

    def test_reject_measurement_stays_reject_not_training(self):
        trial = prepare_development_trial(**self.jobs(action="reject_measurement"))
        self.assertEqual(trial["binding"]["mode"], "inspect")
        self.assertEqual(trial["binding"]["action"], "reject_measurement")

    def test_code_from_different_arm_rejected(self):
        one, other = self.jobs(arm="learn"), self.jobs(arm="archive")
        one["coding_directory"] = other["coding_directory"]
        with self.assertRaises(ValueError):
            prepare_development_trial(**one)

    def test_changed_catalog_bytes_rejected(self):
        args = self.jobs()
        args["dev_bytes"] += b" "
        with self.assertRaises(ValueError):
            prepare_development_trial(**args)

    def test_hidden_split_rejected_even_with_matching_public_commitment(self):
        self.artifacts["dev"]["split"] = "test"
        with self.assertRaises(ValueError):
            prepare_development_trial(**self.jobs())

    def test_same_game_train_dev_rejected_for_prediction(self):
        for row in self.artifacts["dev"]["rows"]:
            row["game_id"] = self.artifacts["train"]["rows"][0]["game_id"]
        with self.assertRaises(ValueError):
            prepare_development_trial(**self.jobs())

    def test_missing_values_inspectable_but_not_training(self):
        self.artifacts["train"]["rows"][0]["features"]["x"] = None
        inspected = prepare_development_trial(**self.jobs(action="inspect", arm="archive"))
        self.assertIsNone(inspected["packet"]["payload"]["train"][0]["features"]["x"])
        with self.assertRaises(ValueError):
            prepare_development_trial(**self.jobs())

    def test_bad_dev_label_not_ignored_when_preparing_prediction(self):
        self.artifacts["dev"]["rows"][0]["target"] = None
        with self.assertRaises(ValueError):
            prepare_development_trial(**self.jobs())

    def test_actual_fit_request_byte_bound_not_silently_subsampled(self):
        self.runtime["execution_limits"]["prediction"]["max_request_bytes"] = 16
        with self.assertRaisesRegex(ValueError, "byte cap"):
            prepare_development_trial(**self.jobs())

    def test_runtime_changes_after_coding_are_rejected(self):
        args = self.jobs()
        args["frozen_runtime"] = dict(copy.deepcopy(self.runtime), prediction_max=2)
        with self.assertRaises(ValueError):
            prepare_development_trial(**args)

    def test_unsupported_resource_envelope_rejected_before_loading_jobs(self):
        for changes in ({"cpu_seconds": 121}, {"memory_mb": 256}):
            runtime = dict(copy.deepcopy(self.runtime), execution_limits=dict(PROFILE, **changes))
            with self.assertRaises(ValueError):
                execution_profile(runtime)
        runtime = copy.deepcopy(self.runtime)
        runtime["execution_limits"]["prediction"]["wall_seconds"] = 1000
        with self.assertRaises(ValueError):
            execution_profile(runtime)

    def test_root_inspection_runner_refuses_mac_before_private_import_or_code(self):
        import sandbox_inspection_runner
        with patch.object(sandbox_inspection_runner.sys, "platform", "darwin"):
            with self.assertRaises(RuntimeError):
                sandbox_inspection_runner.main()


if __name__ == "__main__":
    unittest.main()
