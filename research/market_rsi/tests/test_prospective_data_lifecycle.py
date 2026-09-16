import tempfile
import unittest
from pathlib import Path

from prospective_data_lifecycle import ProspectiveDataLifecycle


def dataset(name, fill):
    return {"dataset_id": name, "content_sha256": fill * 64}


class ProspectiveDataLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "lifecycle"
        self.rounds = [
            {"round_id": "round-01", "train_datasets": [dataset("train-01", "a")],
             "dev_datasets": [dataset("dev-01", "b")]},
            {"round_id": "round-02", "train_datasets": [dataset("train-02", "c")],
             "dev_datasets": [dataset("dev-02", "d")]},
        ]
        self.lifecycle = ProspectiveDataLifecycle.create(self.root,
            experiment_id="experiment", rounds=self.rounds,
            transfer_policy_sha256="e" * 64)

    def tearDown(self):
        self.temp.cleanup()

    def complete_round(self, round_id):
        self.lifecycle.claim_dev_score(round_id, candidate_set_sha256="1" * 64)
        self.lifecycle.complete_dev_score(round_id, score_receipt_sha256="2" * 64)

    def test_transfer_policy_is_bound_but_never_in_controller_view(self):
        view = self.lifecycle.controller_view("round-01")
        self.assertFalse(view["transfer_visible"])
        self.assertNotIn("transfer_policy_sha256", view)
        audit = self.lifecycle.audit()
        self.assertEqual(audit["transfer_policy_sha256"], "e" * 64)
        self.assertFalse(audit["transfer_materialized"])

    def test_materialization_can_arrive_later_but_scoring_waits_for_all_rounds(self):
        self.complete_round("round-01")
        materialized = self.lifecycle.materialize_transfer(
            transfer_datasets=[dataset("transfer-01", "f")],
            materialization_receipt_sha256="3" * 64)
        self.assertEqual(materialized["transfer_policy_sha256"], "e" * 64)
        self.assertFalse(self.lifecycle.controller_view("round-02")["transfer_visible"])
        with self.assertRaises(ValueError):
            self.lifecycle.freeze_transfer_submissions(submissions_sha256="4" * 64)
        self.complete_round("round-02")
        frozen = self.lifecycle.freeze_transfer_submissions(submissions_sha256="4" * 64)
        self.assertEqual(frozen["transfer_dataset_ids"], ["transfer-01"])
        self.lifecycle.complete_transfer_score(score_receipt_sha256="5" * 64)
        self.assertTrue(self.lifecycle.audit()["transfer_scored"])

    def test_transfer_cannot_be_materialized_twice_or_reuse_learning_id(self):
        with self.assertRaises(ValueError):
            self.lifecycle.materialize_transfer(
                transfer_datasets=[dataset("train-01", "f")],
                materialization_receipt_sha256="3" * 64)
        self.lifecycle.materialize_transfer(
            transfer_datasets=[dataset("transfer-01", "f")],
            materialization_receipt_sha256="3" * 64)
        with self.assertRaises(ValueError):
            self.lifecycle.materialize_transfer(
                transfer_datasets=[dataset("transfer-02", "6")],
                materialization_receipt_sha256="7" * 64)


if __name__ == "__main__":
    unittest.main()
