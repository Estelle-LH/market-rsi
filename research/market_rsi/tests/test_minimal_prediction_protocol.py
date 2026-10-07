import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from minimal_prediction_loop.prediction_protocol import (
    COMPLETE_RECEIPT_SCHEMA,
    PREDICTION_SCHEMA,
    PUBLIC_AS_OF_FIELDS,
    PUBLIC_RELEASE_FIELDS,
    PUBLIC_ROW_SCHEMA,
    LabelFreePredictionProtocol,
    PredictionJournalIntegrityError,
    PredictionProtocolError,
    deterministic_run_id,
    fingerprint,
    prediction_submission,
    run_label_free_protocol,
    validate_public_rows,
)


def rows():
    return [
        {
            "event_id": "event-a",
            "market_id": "market-a",
            "cutoff_ms": 1_000,
            "feature_available_ms": 999,
            "market_probability": 0.25,
        },
        {
            "event_id": "event-b",
            "market_id": "market-b",
            "cutoff_ms": 2_000,
            "feature_available_ms": 2_000,
            "market_probability": 0.75,
        },
        {
            "event_id": "event-c",
            "market_id": "market-c",
            "cutoff_ms": 3_000,
            "feature_available_ms": 2_900,
            "market_probability": 0.40,
        },
    ]


def candidate_hash():
    return hashlib.sha256(b"trusted synthetic candidate fixture").hexdigest()


class PublicSchemaTests(unittest.TestCase):
    def test_schema_is_explicit_flat_and_label_free(self):
        self.assertEqual(
            PUBLIC_AS_OF_FIELDS,
            {
                "event_id",
                "market_id",
                "cutoff_ms",
                "feature_available_ms",
                "market_probability",
            },
        )
        self.assertEqual(
            PUBLIC_RELEASE_FIELDS,
            PUBLIC_AS_OF_FIELDS | {"schema", "run_id", "sequence", "row_id"},
        )
        self.assertTrue(
            {"outcome", "label", "outcome_available_ms", "evaluator_path"}.isdisjoint(
                PUBLIC_RELEASE_FIELDS
            )
        )

    def test_rejects_labels_outcomes_paths_and_internal_fields_before_run(self):
        forbidden = (
            "outcome",
            "label",
            "target",
            "outcome_available_ms",
            "future_rows",
            "evaluator_path",
            "scorer_source",
            "_internal",
        )
        for field in forbidden:
            bad = rows()
            bad[0][field] = 1
            with self.subTest(field=field), self.assertRaises(PredictionProtocolError):
                validate_public_rows(bad)

    def test_rejects_future_duplicate_reordered_and_malformed_rows(self):
        variants = []
        future = rows()
        future[0]["feature_available_ms"] = future[0]["cutoff_ms"] + 1
        variants.append(future)
        duplicate = rows()
        duplicate[1] = copy.deepcopy(duplicate[0])
        variants.append(duplicate)
        reordered = rows()
        reordered.reverse()
        variants.append(reordered)
        bad_probability = rows()
        bad_probability[0]["market_probability"] = float("nan")
        variants.append(bad_probability)
        bool_timestamp = rows()
        bool_timestamp[0]["cutoff_ms"] = True
        variants.append(bool_timestamp)
        for bad in variants:
            with self.subTest(bad=bad), self.assertRaises(PredictionProtocolError):
                validate_public_rows(bad)

    def test_ids_are_deterministic_and_bind_candidate_and_row_content(self):
        run_id = deterministic_run_id(
            run_key="synthetic-round-1",
            candidate_sha256=candidate_hash(),
            public_rows=rows(),
        )
        self.assertEqual(
            run_id,
            deterministic_run_id(
                run_key="synthetic-round-1",
                candidate_sha256=candidate_hash(),
                public_rows=copy.deepcopy(rows()),
            ),
        )
        changed = rows()
        changed[0]["market_probability"] = 0.26
        self.assertNotEqual(
            run_id,
            deterministic_run_id(
                run_key="synthetic-round-1",
                candidate_sha256=candidate_hash(),
                public_rows=changed,
            ),
        )


class SequentialProtocolTests(unittest.TestCase):
    def create(self, root, run_key="round-1"):
        return LabelFreePredictionProtocol.create(
            root,
            run_key=run_key,
            candidate_sha256=candidate_hash(),
            public_rows=rows(),
        )

    def test_one_row_at_a_time_and_commit_is_durable_before_next_release(self):
        with tempfile.TemporaryDirectory() as temporary:
            protocol = self.create(Path(temporary) / "state")
            try:
                first = protocol.release_next()
                self.assertEqual(set(first), PUBLIC_RELEASE_FIELDS)
                self.assertEqual(first["schema"], PUBLIC_ROW_SCHEMA)
                self.assertEqual(first["sequence"], 0)
                with self.assertRaises(PredictionProtocolError):
                    protocol.release_next()

                receipt = protocol.commit_prediction(prediction_submission(first, 0.30))
                self.assertFalse(receipt["real_isolation_admitted"])
                self.assertFalse(receipt["scored"])
                durable = [
                    json.loads(line)
                    for line in protocol.journal_path.read_text().splitlines()
                ]
                self.assertEqual(
                    [record["event"] for record in durable],
                    ["row_released", "prediction_committed"],
                )
                self.assertEqual(durable[-1]["probability"], 0.30)
                second = protocol.release_next()
                self.assertEqual(second["sequence"], 1)
                self.assertNotEqual(first["row_id"], second["row_id"])
            finally:
                protocol.close()

    def test_hash_chain_and_completion_receipt_are_exact_and_non_scoring(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary) / "state"
            protocol = self.create(state)
            try:
                for probability in (0.2, 0.8, 0.5):
                    release = protocol.release_next()
                    protocol.commit_prediction(prediction_submission(release, probability))
                self.assertIsNone(protocol.release_next())
                receipt = protocol.finish()
                self.assertEqual(receipt["schema"], COMPLETE_RECEIPT_SCHEMA)
                self.assertFalse(receipt["real_isolation_admitted"])
                self.assertFalse(receipt["scored"])
                self.assertTrue(receipt["label_free"])

                previous = "0" * 64
                for sequence, line in enumerate(protocol.journal_path.read_text().splitlines()):
                    record = json.loads(line)
                    self.assertEqual(record["journal_sequence"], sequence)
                    self.assertEqual(record["previous_hash"], previous)
                    body = {key: value for key, value in record.items() if key != "hash"}
                    self.assertEqual(record["hash"], fingerprint(body))
                    previous = record["hash"]
                self.assertEqual(receipt["journal_head_sha256"], previous)
                self.assertEqual(
                    receipt["journal_sha256"],
                    hashlib.sha256(protocol.journal_path.read_bytes()).hexdigest(),
                )
                self.assertEqual(
                    protocol.prediction_records(),
                    [
                        {
                            "event_id": row["event_id"],
                            "market_id": row["market_id"],
                            "cutoff_ms": row["cutoff_ms"],
                            "probability": probability,
                        }
                        for row, probability in zip(rows(), (0.2, 0.8, 0.5), strict=True)
                    ],
                )
            finally:
                protocol.close()

    def test_rejects_skip_duplicate_rewrite_and_extra_output_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            protocol = self.create(Path(temporary) / "state")
            try:
                release = protocol.release_next()
                valid = prediction_submission(release, 0.4)
                attacks = []
                skipped = dict(valid, sequence=1)
                attacks.append(skipped)
                wrong_row = dict(valid, row_id="row-" + "0" * 64)
                attacks.append(wrong_row)
                wrong_run = dict(valid, run_id="run-" + "0" * 64)
                attacks.append(wrong_run)
                extra = dict(valid, evaluator_path="/trusted/scorer")
                attacks.append(extra)
                label = dict(valid, outcome=1)
                attacks.append(label)
                for attack in attacks:
                    with self.subTest(attack=attack), self.assertRaises(
                        PredictionProtocolError
                    ):
                        protocol.commit_prediction(attack)
                protocol.commit_prediction(valid)
                with self.assertRaises(PredictionProtocolError):
                    protocol.commit_prediction(valid)
            finally:
                protocol.close()

    def test_invalid_candidate_probabilities_never_commit(self):
        invalid = (
            True,
            "0.4",
            None,
            -0.01,
            0.0,
            1.0,
            1.01,
            float("nan"),
            float("inf"),
        )
        with tempfile.TemporaryDirectory() as temporary:
            protocol = self.create(Path(temporary) / "state")
            try:
                release = protocol.release_next()
                for value in invalid:
                    submission = {
                        "schema": PREDICTION_SCHEMA,
                        "run_id": release["run_id"],
                        "sequence": release["sequence"],
                        "row_id": release["row_id"],
                        "probability": value,
                    }
                    with self.subTest(value=value), self.assertRaises(
                        PredictionProtocolError
                    ):
                        protocol.commit_prediction(submission)
                journal = [
                    json.loads(line)
                    for line in protocol.journal_path.read_text().splitlines()
                ]
                self.assertEqual([entry["event"] for entry in journal], ["row_released"])
            finally:
                protocol.close()

    def test_fsync_failure_poisoning_prevents_next_row_release(self):
        with tempfile.TemporaryDirectory() as temporary:
            protocol = self.create(Path(temporary) / "state")
            try:
                release = protocol.release_next()
                with patch(
                    "minimal_prediction_loop.prediction_protocol.os.fsync",
                    side_effect=OSError("synthetic durability failure"),
                ):
                    with self.assertRaises(OSError):
                        protocol.commit_prediction(prediction_submission(release, 0.4))
                with self.assertRaises(PredictionProtocolError):
                    protocol.release_next()
            finally:
                protocol.close()

    def test_fixture_callback_never_receives_full_sequence_or_private_fields(self):
        observed = []

        def predict(public_row):
            self.assertEqual(set(public_row), PUBLIC_RELEASE_FIELDS)
            self.assertEqual(public_row["sequence"], len(observed))
            self.assertFalse(any(key.startswith("_") for key in public_row))
            self.assertNotIn("outcome", public_row)
            self.assertNotIn("future_rows", public_row)
            observed.append(copy.deepcopy(public_row))
            return prediction_submission(public_row, public_row["market_probability"])

        with tempfile.TemporaryDirectory() as temporary:
            receipt = run_label_free_protocol(
                Path(temporary) / "state",
                run_key="fixture-run",
                candidate_sha256=candidate_hash(),
                public_rows=rows(),
                predict=predict,
            )
        self.assertEqual(len(observed), len(rows()))
        self.assertEqual(receipt["predictions"], len(rows()))
        self.assertFalse(receipt["real_isolation_admitted"])

    def test_same_commitments_produce_identical_journal_and_receipt(self):
        def predict(public_row):
            return prediction_submission(public_row, public_row["market_probability"])

        with tempfile.TemporaryDirectory() as temporary:
            artifacts = []
            for name in ("first", "second"):
                root = Path(temporary) / name
                receipt = run_label_free_protocol(
                    root,
                    run_key="deterministic-fixture",
                    candidate_sha256=candidate_hash(),
                    public_rows=rows(),
                    predict=predict,
                )
                artifacts.append(
                    (receipt, (root / receipt["run_id"] / "journal.jsonl").read_bytes())
                )
        self.assertEqual(artifacts[0], artifacts[1])


class RestartAndIntegrityTests(unittest.TestCase):
    def create(self, root, run_key="restart-round"):
        return LabelFreePredictionProtocol.create(
            root,
            run_key=run_key,
            candidate_sha256=candidate_hash(),
            public_rows=rows(),
        )

    def resume(self, root, run_id):
        return LabelFreePredictionProtocol.resume(
            root,
            run_id=run_id,
            candidate_sha256=candidate_hash(),
            public_rows=rows(),
        )

    def test_clean_restart_continues_only_at_next_uncommitted_row(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "state"
            first_owner = self.create(root)
            first_release = first_owner.release_next()
            old_submission = prediction_submission(first_release, 0.4)
            first_owner.commit_prediction(old_submission)
            run_id = first_owner.run_id
            first_owner.close()

            second_owner = self.resume(root, run_id)
            try:
                with self.assertRaises(PredictionProtocolError):
                    second_owner.commit_prediction(old_submission)
                next_release = second_owner.release_next()
                self.assertEqual(next_release["sequence"], 1)
                with self.assertRaises(PredictionProtocolError):
                    second_owner.commit_prediction(old_submission)
                second_owner.commit_prediction(prediction_submission(next_release, 0.6))
            finally:
                second_owner.close()

    def test_restart_with_uncommitted_release_fails_closed_without_replay(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "state"
            first_owner = self.create(root)
            release = first_owner.release_next()
            stale_submission = prediction_submission(release, 0.4)
            run_id = first_owner.run_id
            first_owner.close()

            second_owner = self.resume(root, run_id)
            try:
                with self.assertRaises(PredictionProtocolError):
                    second_owner.release_next()
                with self.assertRaises(PredictionProtocolError):
                    second_owner.commit_prediction(stale_submission)
            finally:
                second_owner.close()

    def test_deterministic_run_recreation_and_concurrent_owner_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "state"
            owner = self.create(root)
            try:
                with self.assertRaises(PredictionProtocolError):
                    self.create(root)
                with self.assertRaises(PredictionProtocolError):
                    self.resume(root, owner.run_id)
            finally:
                owner.close()

    def test_completed_run_can_be_verified_but_never_replayed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "state"
            owner = self.create(root)
            for value in (0.2, 0.8, 0.5):
                release = owner.release_next()
                owner.commit_prediction(prediction_submission(release, value))
            original = owner.finish()
            run_id = owner.run_id
            owner.close()

            restarted = self.resume(root, run_id)
            try:
                self.assertEqual(restarted.completion_receipt(), original)
                with self.assertRaises(PredictionProtocolError):
                    restarted.release_next()
                with self.assertRaises(PredictionProtocolError):
                    restarted.finish()
            finally:
                restarted.close()

    def test_claim_candidate_and_rows_cannot_be_substituted_on_resume(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "state"
            owner = self.create(root)
            run_id = owner.run_id
            owner.close()
            with self.assertRaises(PredictionProtocolError):
                LabelFreePredictionProtocol.resume(
                    root,
                    run_id=run_id,
                    candidate_sha256="f" * 64,
                    public_rows=rows(),
                )
            changed = rows()
            changed[0]["market_probability"] = 0.26
            with self.assertRaises(PredictionProtocolError):
                LabelFreePredictionProtocol.resume(
                    root,
                    run_id=run_id,
                    candidate_sha256=candidate_hash(),
                    public_rows=changed,
                )

    def test_journal_rewrite_and_completion_rewrite_are_detected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "journal-state"
            owner = self.create(root, run_key="journal-tamper")
            release = owner.release_next()
            owner.commit_prediction(prediction_submission(release, 0.4))
            run_id = owner.run_id
            owner.close()
            journal_path = root / run_id / "journal.jsonl"
            entries = [json.loads(line) for line in journal_path.read_text().splitlines()]
            entries[-1]["probability"] = 0.9
            journal_path.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n")
            with self.assertRaises(PredictionJournalIntegrityError):
                self.resume(root, run_id)

            complete_root = Path(temporary) / "complete-state"
            owner = self.create(complete_root, run_key="complete-tamper")
            for value in (0.2, 0.8, 0.5):
                release = owner.release_next()
                owner.commit_prediction(prediction_submission(release, value))
            owner.finish()
            run_id = owner.run_id
            owner.close()
            complete_path = complete_root / run_id / "complete.json"
            receipt = json.loads(complete_path.read_text())
            receipt["real_isolation_admitted"] = True
            complete_path.write_text(json.dumps(receipt) + "\n")
            with self.assertRaises(PredictionJournalIntegrityError):
                self.resume(complete_root, run_id)

    def test_torn_or_extended_journal_is_detected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "state"
            owner = self.create(root)
            release = owner.release_next()
            owner.commit_prediction(prediction_submission(release, 0.4))
            run_id = owner.run_id
            owner.close()
            with (root / run_id / "journal.jsonl").open("ab") as output:
                output.write(b'{"event":"prediction_committed"')
            with self.assertRaises(PredictionJournalIntegrityError):
                self.resume(root, run_id)

            truncated_root = Path(temporary) / "truncated-state"
            owner = self.create(truncated_root, run_key="truncated-round")
            release = owner.release_next()
            owner.commit_prediction(prediction_submission(release, 0.4))
            run_id = owner.run_id
            owner.close()
            journal_path = truncated_root / run_id / "journal.jsonl"
            complete_lines = journal_path.read_bytes().splitlines(keepends=True)
            journal_path.write_bytes(b"".join(complete_lines[:-1]))
            with self.assertRaises(PredictionJournalIntegrityError):
                self.resume(truncated_root, run_id)


if __name__ == "__main__":
    unittest.main()
