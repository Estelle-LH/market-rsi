import json
import tempfile
import unittest
from pathlib import Path

from market_rsi import digest
from minimal_prediction_loop.lineage import PredictionLineage


H = {
    "parent": "1" * 64,
    "candidate_good": "2" * 64,
    "candidate_bad": "3" * 64,
    "journal": "4" * 64,
    "mask": "5" * 64,
    "trusted_rows": "6" * 64,
    "dev_dataset": "6" * 64,
    "candidate_records": "7" * 64,
    "scorer_spec": "8" * 64,
    "full_score": "9" * 64,
    "public_rows": "a" * 64,
    "prediction_receipt": "b" * 64,
}


def rule():
    return {
        "metric": "candidate_minus_market_brier",
        "operator": "<",
        "threshold": 0.0,
        "minimum_rows": 4,
        "minimum_events": 2,
        "minimum_dates": 2,
    }


def score(
    dev_id,
    *,
    candidate=0.15,
    market=0.25,
    rows=4,
    events=2,
    dates=2,
    coverage=1.0,
    journal=None,
):
    candidate_log = 0.4 if candidate < market else 0.8
    market_log = 0.6
    return {
        "schema": "minimal_prediction_score_receipt_v1",
        "dev_id": dev_id,
        "dev_dataset_sha256": H["dev_dataset"],
        "complete_mask_sha256": H["mask"],
        "trusted_rows_sha256": H["trusted_rows"],
        "public_rows_sha256": H["public_rows"],
        "candidate_records_sha256": H["candidate_records"],
        "prediction_journal_sha256": journal or H["journal"],
        "prediction_receipt_sha256": H["prediction_receipt"],
        "scorer_spec_sha256": H["scorer_spec"],
        "full_score_sha256": H["full_score"],
        "candidate_brier": candidate,
        "market_brier": market,
        "candidate_minus_market_brier": candidate - market,
        "candidate_log_loss": candidate_log,
        "market_log_loss": market_log,
        "candidate_minus_market_log_loss": candidate_log - market_log,
        "coverage": coverage,
        "rows": rows,
        "events": events,
        "dates": dates,
    }


class PredictionLineageTests(unittest.TestCase):
    def create(self, root):
        return PredictionLineage.create(
            root,
            experiment_id="synthetic-loop",
            initial_parent_sha256=H["parent"],
            keep_rule=rule(),
        )

    def start(self, lineage, *, round_id="round-1", dev_id="dev-1", candidate=None, role="dev"):
        return lineage.start_round(
            round_id=round_id,
            changed_stage="prediction",
            candidate_sha256=candidate or H["candidate_good"],
            prediction_journal_sha256=H["journal"],
            prediction_receipt_sha256=H["prediction_receipt"],
            public_rows_sha256=H["public_rows"],
            dev_id=dev_id,
            evaluation_role=role,
        )

    def test_keep_then_revert_and_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "lineage"
            lineage = self.create(root)
            self.start(lineage)
            kept_score = score("dev-1")
            lineage.bind_dev_score(round_id="round-1", score_receipt=kept_score)
            state = lineage.decide(round_id="round-1")
            self.assertEqual(state["parent_sha256"], H["candidate_good"])
            self.assertEqual(state["decisions"][-1]["decision"], "KEEP")
            with self.assertRaisesRegex(ValueError, "no matching active"):
                lineage.decide(round_id="round-1")

            restarted = PredictionLineage(root)
            self.start(
                restarted, round_id="round-2", dev_id="dev-2", candidate=H["candidate_bad"]
            )
            bad_score = score("dev-2", candidate=0.30, market=0.25)
            restarted.bind_dev_score(round_id="round-2", score_receipt=bad_score)
            state = restarted.decide(round_id="round-2")
            self.assertEqual(state["parent_sha256"], H["candidate_good"])
            self.assertEqual([item["decision"] for item in state["decisions"]], ["KEEP", "REVERT"])
            self.assertEqual(state["used_dev_ids"], ["dev-1", "dev-2"])
            self.assertFalse(state["final_feedback_allowed"])

    def test_insufficient_breadth_reverts_even_with_better_score(self):
        with tempfile.TemporaryDirectory() as directory:
            lineage = self.create(Path(directory) / "lineage")
            self.start(lineage)
            receipt = score("dev-1", rows=3)
            lineage.bind_dev_score(round_id="round-1", score_receipt=receipt)
            state = lineage.decide(round_id="round-1")
            self.assertEqual(state["decisions"][-1]["decision"], "REVERT")
            self.assertEqual(state["parent_sha256"], H["parent"])

    def test_final_feedback_and_caller_controlled_memory_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            lineage = self.create(Path(directory) / "lineage")
            with self.assertRaisesRegex(ValueError, "Final is sealed"):
                self.start(lineage, role="final")
            self.start(lineage)
            receipt = score("dev-1")
            lineage.bind_dev_score(round_id="round-1", score_receipt=receipt)
            with self.assertRaises(TypeError):
                lineage.decide(
                    round_id="round-1",
                    memory={
                        "summary_code": "labels_1010",
                        "aggregate_metrics": {"candidate_brier": 0.101},
                        "failure_codes": ["event_a_label_1"],
                    },
                )
            state = lineage.decide(round_id="round-1")
            self.assertEqual(state["memory"][0]["summary_code"], "kept")
            self.assertEqual(
                state["memory"][0]["aggregate_metrics"]["candidate_brier"],
                receipt["candidate_brier"],
            )
            self.assertEqual(state["memory"][0]["failure_codes"], [])

    def test_duplicate_score_round_and_dev_replay_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "lineage"
            lineage = self.create(root)
            self.start(lineage)
            receipt = score("dev-1")
            lineage.bind_dev_score(round_id="round-1", score_receipt=receipt)
            with self.assertRaisesRegex(ValueError, "one-shot"):
                lineage.bind_dev_score(round_id="round-1", score_receipt=receipt)
            lineage.decide(round_id="round-1")
            with self.assertRaisesRegex(ValueError, "already consumed"):
                self.start(lineage, round_id="round-2", dev_id="dev-1")
            with self.assertRaisesRegex(ValueError, "already consumed"):
                self.start(lineage, round_id="round-1", dev_id="dev-2")

    def test_crash_restart_preserves_active_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "lineage"
            lineage = self.create(root)
            self.start(lineage)
            restarted = PredictionLineage(root)
            state = restarted.audit()
            self.assertEqual(state["active_round"]["round_id"], "round-1")
            with self.assertRaisesRegex(ValueError, "already active"):
                self.start(restarted, round_id="round-2", dev_id="dev-2")
            receipt = score("dev-1")
            restarted.bind_dev_score(round_id="round-1", score_receipt=receipt)
            state = PredictionLineage(root).decide(round_id="round-1")
            self.assertEqual(state["parent_sha256"], H["candidate_good"])

    def test_score_receipt_is_exact_and_self_consistent(self):
        with tempfile.TemporaryDirectory() as directory:
            lineage = self.create(Path(directory) / "lineage")
            self.start(lineage)
            bad = score("dev-1")
            bad["candidate_minus_market_brier"] = 0.5
            with self.assertRaisesRegex(ValueError, "Brier delta"):
                lineage.bind_dev_score(round_id="round-1", score_receipt=bad)
            overshared = score("dev-1")
            overshared["row_labels"] = [0, 1]
            with self.assertRaisesRegex(ValueError, "aggregate fields only"):
                lineage.bind_dev_score(round_id="round-1", score_receipt=overshared)

    def test_score_must_bind_the_active_prediction_journal(self):
        with tempfile.TemporaryDirectory() as directory:
            lineage = self.create(Path(directory) / "lineage")
            self.start(lineage)
            with self.assertRaisesRegex(ValueError, "active prediction journal"):
                lineage.bind_dev_score(
                    round_id="round-1",
                    score_receipt=score("dev-1", journal="a" * 64),
                )

    def test_score_must_bind_trusted_rows_to_frozen_dev_dataset(self):
        with tempfile.TemporaryDirectory() as directory:
            lineage = self.create(Path(directory) / "lineage")
            self.start(lineage)
            bad = score("dev-1")
            bad["dev_dataset_sha256"] = "c" * 64
            with self.assertRaisesRegex(ValueError, "frozen Dev dataset"):
                lineage.bind_dev_score(round_id="round-1", score_receipt=bad)

    def test_ledger_suffix_truncation_is_detected_by_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "lineage"
            lineage = self.create(root)
            self.start(lineage)
            receipt = score("dev-1")
            lineage.bind_dev_score(round_id="round-1", score_receipt=receipt)
            lineage.decide(round_id="round-1")
            ledger = root / "ledger.jsonl"
            lines = ledger.read_text().splitlines()
            ledger.write_text("\n".join(lines[:-1]) + "\n")
            with self.assertRaisesRegex(ValueError, "durable checkpoint"):
                PredictionLineage(root).audit()

    def test_ledger_mutation_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "lineage"
            lineage = self.create(root)
            self.start(lineage)
            path = root / "ledger.jsonl"
            records = [json.loads(line) for line in path.read_text().splitlines()]
            records[1]["payload"]["candidate_sha256"] = "9" * 64
            path.write_text("\n".join(json.dumps(item) for item in records) + "\n")
            with self.assertRaisesRegex(ValueError, "integrity failure"):
                PredictionLineage(root).audit()


if __name__ == "__main__":
    unittest.main()
