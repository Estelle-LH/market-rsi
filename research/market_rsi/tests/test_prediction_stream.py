import copy
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from prediction_stream import (LineChannel, PredictionJournal, fingerprint, linux_candidate_command,
                               predict_stream, validate_rows)


DAY = 86400000


def inputs():
    train = [{"row_id": "train-1", "game_id": "earlier-game", "market_id": "earlier-market",
              "decision_ms": DAY, "feature_available_ms": DAY, "features": {"mid": 0.5},
              "target": 0.1, "label_available_ms": DAY + 60000}]
    evaluation = [{"row_id": f"eval-{i}", "game_id": "later-game", "market_id": "later-market",
                   "decision_ms": 3 * DAY + i, "feature_available_ms": 3 * DAY + i,
                   "features": {"mid": 0.3 + i / 100}} for i in range(3)]
    return train, evaluation


def run(exchange, commit, train=None, evaluation=None, **kw):
    default_train, default_evaluation = inputs()
    options = dict(prediction_min=-1, prediction_max=1, fit_timeout_seconds=1,
                   predict_timeout_seconds=1, wall_seconds=5, max_request_bytes=100000)
    options.update(kw)
    return predict_stream(exchange, commit, default_train if train is None else train,
                          default_evaluation if evaluation is None else evaluation, ["mid"], **options)


class Echo:
    def __init__(self):
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append(copy.deepcopy(request))
        if request["type"] == "fit":
            return {"type": "fitted", "request_id": request["request_id"]}
        return {"type": "prediction", "request_id": request["request_id"],
                "row_id": request["row"]["row_id"], "prediction": 0.0}


class StreamTests(unittest.TestCase):
    def test_only_one_observation_released_after_each_commit(self):
        transport, records = Echo(), []

        def commit(row):
            self.assertEqual(len(transport.requests), len(records) + 2)
            observed = [r["row"]["row_id"] for r in transport.requests if r["type"] == "predict"]
            self.assertEqual(observed, [f"eval-{i}" for i in range(len(records) + 1)])
            records.append(row)

        receipt = run(transport, commit)
        self.assertEqual(receipt["predictions"], 3)
        self.assertFalse(receipt["scored"])
        self.assertEqual(transport.requests[0]["type"], "fit")
        self.assertNotIn("evaluation", transport.requests[0])
        self.assertEqual({r["row_id"] for r in transport.requests[0]["train"]}, {"train-1"})
        for request in transport.requests[1:]:
            self.assertEqual(set(request), {"type", "request_id", "row"})
            self.assertNotIn("target", request["row"])
            self.assertNotIn("runner_endpoints", request["row"])
        chain = "0" * 64
        for record in records:
            self.assertEqual(record["previous"], chain)
            chain = fingerprint({k: v for k, v in record.items() if k != "hash"})
            self.assertEqual(chain, record["hash"])
        self.assertEqual(receipt["last_prediction_hash"], chain)

    def test_commit_failure_prevents_releasing_next_observation(self):
        transport = Echo()
        def fail(record):
            raise OSError("commit failed")
        with self.assertRaises(OSError):
            run(transport, fail)
        self.assertEqual(len(transport.requests), 2)

    def test_eval_labels_future_endpoints_and_unrecognized_fields_rejected(self):
        for key in ("target", "labels", "runner_endpoints", "test_summary", "other_arm"):
            with self.subTest(key=key):
                train, evaluation = inputs()
                evaluation[0][key] = "forbidden"
                transport = Echo()
                with self.assertRaises(ValueError):
                    run(transport, lambda x: None, train, evaluation)
                self.assertEqual(transport.requests, [])

    def test_same_game_rejected_before_candidate_access(self):
        train, evaluation = inputs()
        train[0]["game_id"] = evaluation[0]["game_id"]
        with self.assertRaises(ValueError):
            run(Echo(), lambda x: None, train, evaluation)

    def test_same_market_cannot_be_relabelled_to_escape_game_split(self):
        train, evaluation = inputs()
        train[0]["market_id"] = evaluation[0]["market_id"]
        with self.assertRaises(ValueError):
            run(Echo(), lambda x: None, train, evaluation)

    def test_training_label_cannot_arrive_on_or_after_evaluation_day(self):
        for t in (3 * DAY, 3 * DAY + 1000):
            train, evaluation = inputs()
            train[0]["label_available_ms"] = t
            with self.assertRaises(ValueError):
                validate_rows(train, evaluation, ["mid"])

    def test_duplicate_identity_future_features_and_order_rejected(self):
        for variant in ("duplicate", "future", "reordered"):
            train, evaluation = inputs()
            if variant == "duplicate":
                evaluation[1]["row_id"] = evaluation[0]["row_id"]
            elif variant == "future":
                evaluation[0]["feature_available_ms"] += 1
            else:
                evaluation.reverse()
            with self.subTest(variant=variant), self.assertRaises(ValueError):
                validate_rows(train, evaluation, ["mid"])

    def test_request_bound_does_not_silently_remove_training_rows(self):
        transport = Echo()
        with self.assertRaises(ValueError):
            run(transport, lambda x: None, max_request_bytes=20)
        self.assertEqual(transport.requests, [])

    def test_invalid_predictions_fail_without_committing(self):
        for value in (True, "0.2", float("nan"), float("inf"), 1.01, -1.01):
            records, base = [], Echo()
            def exchange(request, timeout):
                result = base(request, timeout)
                if request["type"] == "predict":
                    result["prediction"] = value
                return result
            with self.subTest(value=value), self.assertRaises(ValueError):
                run(exchange, records.append)
            self.assertEqual(records, [])
            self.assertEqual(len(base.requests), 2)

    def test_wrong_response_identity_cannot_commit(self):
        for key in ("request_id", "row_id", "extra"):
            base, records = Echo(), []
            def exchange(request, timeout):
                result = base(request, timeout)
                if request["type"] == "predict":
                    result[key] = "unexpected"
                return result
            with self.subTest(key=key), self.assertRaises(ValueError):
                run(exchange, records.append)
            self.assertEqual(records, [])

    def test_fit_acknowledgment_is_required(self):
        with self.assertRaises(ValueError):
            run(lambda r, t: {"type": "prediction", "request_id": r["request_id"]}, lambda x: None)

    def test_deadline_is_checked_after_transport_returns(self):
        base = Echo()
        def delayed(request, timeout):
            time.sleep(0.02)
            return base(request, timeout)
        with self.assertRaises(TimeoutError):
            run(delayed, lambda x: None, wall_seconds=0.01)

    def test_resource_limits_and_features_are_frozen(self):
        for kw in ({"wall_seconds": 0}, {"prediction_max": -1},
                   {"max_request_bytes": True}, {"fit_timeout_seconds": float("nan")}):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                run(Echo(), lambda x: None, **kw)
        train, evaluation = inputs()
        evaluation[1]["features"]["future_mid"] = 0.4
        with self.assertRaises(ValueError):
            validate_rows(train, evaluation, ["mid"])

    def test_linux_launcher_refuses_mac_and_nonroot(self):
        with patch("prediction_stream.sys.platform", "darwin"), self.assertRaises(RuntimeError):
            linux_candidate_command("/tmp/server.py", "/tmp/candidate.py")
        with patch("prediction_stream.sys.platform", "linux"), patch("prediction_stream.os.geteuid", return_value=1000):
            with self.assertRaises(RuntimeError):
                linux_candidate_command("/tmp/server.py", "/tmp/candidate.py")


class TransportTests(unittest.TestCase):
    """Only human-authored protocol fixtures, not generated candidate code."""
    def test_real_persistent_fixture_channel_and_exact_cleanup(self):
        fixture = "import sys,json\nfor line in sys.stdin:\n r=json.loads(line); print(json.dumps({'request_id':r['request_id']}),flush=True)\n"
        with tempfile.TemporaryDirectory() as tmp:
            with LineChannel([sys.executable, "-I", "-c", fixture], tmp) as channel:
                for i in range(3):
                    r = channel.exchange({"request_id": str(i), "large": "x" * 100000}, 2)
                    self.assertEqual(r, {"request_id": str(i)})
            self.assertIsNotNone(channel.process.poll())
            self.assertEqual(sum(e["type"] == "request" for e in channel.events), 3)
            self.assertEqual(sum(e["type"] == "response" for e in channel.events), 3)
            channel.close()
            with self.assertRaises(ValueError):
                channel.exchange({}, 1)

    def test_timeout_closes_only_created_process_group(self):
        fixture = "import time; time.sleep(5)"
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(TimeoutError):
                with LineChannel([sys.executable, "-I", "-c", fixture], tmp) as channel:
                    channel.exchange({}, 0.05)
            self.assertIsNotNone(channel.process.poll())

    def test_extra_lines_oversized_output_and_eof_fail(self):
        variants = ["print('{}\\n{}',flush=True)", "print('x'*20000,flush=True)", "pass"]
        for fixture in variants:
            with self.subTest(fixture=fixture), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(ValueError):
                    with LineChannel([sys.executable, "-I", "-c", fixture], tmp) as channel:
                        channel.exchange({}, 1)
                self.assertIsNotNone(channel.process.poll())
                self.assertGreaterEqual(len(channel.events), 2)


class JournalTests(unittest.TestCase):
    def journal(self, path, count=3):
        return PredictionJournal(path, train_sha256="a" * 64, evaluation_sha256="b" * 64,
                                 candidate_sha256="c" * 64, expected_predictions=count)

    def test_stream_commits_readable_log_before_next_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trial-01"
            journal, base = self.journal(path), Echo()
            def exchange(request, timeout):
                if request["type"] == "predict":
                    expected_count = int(request["row"]["row_id"].split("-")[-1])
                    lines = journal.path.read_text().splitlines()
                    self.assertEqual(len(lines), expected_count)
                return base(request, timeout)
            receipt = run(exchange, journal.commit)
            saved = journal.finish()
            self.assertEqual(receipt["last_prediction_hash"], saved["last_prediction_hash"])
            self.assertEqual(path.stat().st_mode & 0o777, 0o700)
            self.assertFalse(saved["scored"])
            with self.assertRaises(FileExistsError):
                self.journal(path)

    def test_incomplete_log_cannot_finish(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = self.journal(Path(tmp) / "trial")
            with self.assertRaises(ValueError):
                journal.finish()
            self.assertFalse((journal.directory / "complete.json").exists())

    def test_prediction_log_mutation_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = self.journal(Path(tmp) / "trial")
            run(Echo(), journal.commit)
            rows = [json.loads(x) for x in journal.path.read_text().splitlines()]
            rows[0]["prediction"] = 0.8
            journal.path.write_text("\n".join(json.dumps(x) for x in rows) + "\n")
            with self.assertRaises(ValueError):
                journal.finish()
            self.assertFalse((journal.directory / "complete.json").exists())

    def test_fsync_failure_blocks_next_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal, base = self.journal(Path(tmp) / "trial"), Echo()
            with patch("prediction_stream.os.fsync", side_effect=OSError("disk write failure")):
                with self.assertRaises(OSError):
                    run(base, journal.commit)
            self.assertEqual(len(base.requests), 2)
            self.assertFalse((journal.directory / "complete.json").exists())


if __name__ == "__main__":
    unittest.main()
