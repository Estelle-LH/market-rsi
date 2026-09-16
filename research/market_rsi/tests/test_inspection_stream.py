import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from coder_worker import prepare_code_request
from inspection_stream import inspect_once, prepare_inspection
from market_harbor import fixture_packet
from prediction_stream import LineChannel, PUBLIC_FIELDS, encoded, fingerprint
from research_context import freeze_common
from researcher_worker import prepare_request
from test_coder_worker import LIMITS as CODER_LIMITS, RUNTIME
from test_researcher_worker import proposal, task


LIMITS = {"timeout_seconds": 1, "max_request_bytes": 65536, "max_response_bytes": 16384,
          "max_json_nodes": 1000, "max_json_depth": 8}


class InspectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.common = self.root / "common.json"
        freeze_common(self.common)
        p = fixture_packet()
        dev = [dict(r, target=r["features"]["x"], label_available_ms=r["decision_ms"] + 60000)
               for r in p["evaluation"]]
        self.artifacts = {kind: {"schema": "market_permitted_rows_v1", "experiment_id": "fixture-research",
            "task_id": "task-0", "split": kind, "feature_names": ["x"], "rows": rows}
            for kind, rows in (("train", p["train"]), ("dev", dev))}

    def tearDown(self):
        self.temp.cleanup()

    def requests(self, arm="learn", action="inspect"):
        t = task()
        blobs = {k: encoded(v) for k, v in self.artifacts.items()}
        for entry in t["data_catalog"]:
            entry["sha256"] = hashlib.sha256(blobs[entry["split"]]).hexdigest()
        r = prepare_request(self.common, arm=arm, task=t, step_index=0, records=[])
        p = proposal()
        p["action"] = action
        c = prepare_code_request(r, json.dumps(p), RUNTIME, CODER_LIMITS)
        return r, c, blobs

    def prepared(self, arm="learn", action="inspect", limits=None):
        r, c, blobs = self.requests(arm, action)
        return prepare_inspection(r, c, train_id="train", train_bytes=blobs["train"],
                                  dev_id="dev", dev_bytes=blobs["dev"], limits=limits or LIMITS)

    def exchange(self, diagnostic):
        return lambda r, t: {"type": "inspection", "request_id": r["request_id"], "diagnostic": diagnostic}

    def test_inspection_dev_view_is_physically_label_free(self):
        p = self.prepared()
        self.assertTrue(all(set(row) == PUBLIC_FIELDS for row in p["payload"]["dev"]))
        self.assertTrue(all("target" not in row and "label_available_ms" not in row
                            for row in p["payload"]["dev"]))
        self.assertNotIn("test", p["payload"])
        self.assertNotIn("opaque_test_commitment", p["payload"])

    def test_same_initial_payload_all_arms_but_owned_audit(self):
        ps = [self.prepared(arm) for arm in ("reset", "archive", "learn")]
        self.assertEqual(len({fingerprint(p["payload"]) for p in ps}), 1)
        self.assertEqual([p["audit"]["arm"] for p in ps], ["reset", "archive", "learn"])

    def test_candidate_claims_remain_untrusted_not_authoritative_score(self):
        diagnostic = {"passed": True, "independent_score": 999, "scientific_admission": True}
        result = inspect_once(self.exchange(diagnostic), self.prepared())
        self.assertEqual(result["diagnostic"], diagnostic)
        self.assertIsNone(result["independent_score"])
        self.assertFalse(result["scientific_admission"])
        self.assertFalse(result["scored"])
        self.assertEqual(result["origin"], "candidate_code_untrusted_diagnostic")

    def test_reject_measurement_is_not_rewritten_as_training(self):
        result = inspect_once(self.exchange({"problem": "input issue"}), self.prepared(action="reject_measurement"))
        self.assertEqual(result["audit"]["action"], "reject_measurement")
        self.assertEqual(result["logical_exchanges"], 1)

    def test_experiment_code_cannot_use_inspection_access(self):
        with self.assertRaises(ValueError):
            self.prepared(action="experiment")

    def test_wrong_bytes_cannot_borrow_a_train_filename(self):
        r, c, blobs = self.requests()
        with self.assertRaises(ValueError):
            prepare_inspection(r, c, train_id="train", train_bytes=blobs["dev"],
                               dev_id="dev", dev_bytes=blobs["dev"], limits=LIMITS)

    def test_uncatalogued_id_and_test_split_rejected(self):
        r, c, blobs = self.requests()
        with self.assertRaises(ValueError):
            prepare_inspection(r, c, train_id="hidden-test", train_bytes=blobs["train"],
                               dev_id="dev", dev_bytes=blobs["dev"], limits=LIMITS)
        self.artifacts["dev"]["split"] = "test"
        with self.assertRaises(ValueError):
            self.prepared()

    def test_hidden_extra_fields_in_artifact_are_rejected_even_with_new_hash(self):
        self.artifacts["dev"]["hidden_test"] = ["secret"]
        with self.assertRaises(ValueError):
            self.prepared()

    def test_runner_endpoint_fields_not_accidentally_copied_into_rows(self):
        self.artifacts["dev"]["rows"][0]["runner_endpoints"] = {"secret": "not a permitted field"}
        with self.assertRaises(ValueError):
            self.prepared()

    def test_other_task_ownership_rejected_even_if_catalog_hash_matches(self):
        self.artifacts["dev"]["task_id"] = "task-1"
        with self.assertRaises(ValueError):
            self.prepared()

    def test_other_arm_coder_request_rejected(self):
        r, _, blobs = self.requests("learn")
        _, c, _ = self.requests("archive")
        with self.assertRaises(ValueError):
            prepare_inspection(r, c, train_id="train", train_bytes=blobs["train"],
                               dev_id="dev", dev_bytes=blobs["dev"], limits=LIMITS)

    def test_missing_values_preserved_for_diagnosis_not_imputed_or_trainable(self):
        self.artifacts["dev"]["rows"][0]["target"] = None
        self.artifacts["train"]["rows"][0]["features"] = {}
        self.artifacts["train"]["rows"][1]["features"]["x"] = "bad numeric source"
        p = self.prepared()
        self.assertNotIn("target", p["payload"]["dev"][0])
        self.assertNotIn("label_available_ms", p["payload"]["dev"][0])
        self.assertEqual(p["payload"]["train"][0]["features"], {})
        self.assertEqual(p["payload"]["train"][1]["features"]["x"], "bad numeric source")

    def test_mutated_packet_rejected_before_exchange(self):
        p = self.prepared()
        p["payload"]["dev"][0]["target"] = .99
        def forbidden(*args):
            self.fail("transport must not be called")
        with self.assertRaises(ValueError):
            inspect_once(forbidden, p)

    def test_wrong_nonce_or_top_level_score_rejected_without_retry(self):
        for change in ({"request_id": "wrong"}, {"score": 1}, {"type": "prediction"}):
            calls = []
            def exchange(r, t):
                calls.append(r)
                return dict(self.exchange({})(r, t), **change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                inspect_once(exchange, self.prepared())
            self.assertEqual(len(calls), 1)

    def test_response_byte_node_depth_and_nonfinite_limits(self):
        for value in ("x" * 20000, list(range(1100)), [[[[[[[[[[0]]]]]]]]]], float("nan")):
            with self.subTest(value_type=type(value)), self.assertRaises(ValueError):
                inspect_once(self.exchange(value), self.prepared())

    def test_transport_failure_is_not_resampled(self):
        calls = []
        def exchange(r, t):
            calls.append(r)
            raise TimeoutError("fixture transport")
        with self.assertRaises(TimeoutError):
            inspect_once(exchange, self.prepared())
        self.assertEqual(len(calls), 1)

    def test_deadline_checked_after_transport_returns(self):
        with patch("inspection_stream.time.monotonic", side_effect=[0, 2]):
            with self.assertRaises(TimeoutError):
                inspect_once(self.exchange({}), self.prepared())

    def test_input_cap_and_hard_safety_limits_rejected(self):
        for changes in ({"max_request_bytes": 10}, {"timeout_seconds": 9999}, {"max_json_depth": True}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.prepared(limits=dict(LIMITS, **changes))

    def test_unprivileged_server_refuses_mac_execution_before_import(self):
        from inspection_candidate_server import main
        with patch("inspection_candidate_server.sys.platform", "darwin"):
            with self.assertRaises(RuntimeError):
                main()

    def test_bounded_line_transport_with_human_written_local_fixture_only(self):
        code = "import sys,json; r=json.loads(sys.stdin.readline()); print(json.dumps({'type':'inspection','request_id':r['request_id'],'diagnostic':{'train_rows':len(r['train']),'dev_rows':len(r['dev'])}}),flush=True)"
        channel = LineChannel([sys.executable, "-u", "-c", code], self.root, max_response_bytes=16384)
        try:
            result = inspect_once(channel.exchange, self.prepared())
            self.assertEqual(result["diagnostic"], {"train_rows": 2, "dev_rows": 3})
            self.assertFalse(result["scored"])
        finally:
            channel.close()
        self.assertIsNotNone(channel.process.returncode)


if __name__ == "__main__":
    unittest.main()
