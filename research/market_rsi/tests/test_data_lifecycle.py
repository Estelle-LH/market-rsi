from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from data_lifecycle import DataLifecycle, LEDGER_NAME


def dataset(name: str, digit: str) -> dict:
    return {"dataset_id": name, "content_sha256": digit * 64}


def rounds() -> list[dict]:
    return [
        {"round_id": "round-01", "train_datasets": [dataset("train-01", "1")],
         "dev_datasets": [dataset("dev-01", "2")]},
        {"round_id": "round-02", "train_datasets": [dataset("train-02", "3")],
         "dev_datasets": [dataset("dev-02", "4")]},
        {"round_id": "round-03", "train_datasets": [dataset("train-03", "5")],
         "dev_datasets": [dataset("dev-03", "6")]},
    ]


class DataLifecycleTests(unittest.TestCase):
    def create(self, root: Path) -> DataLifecycle:
        return DataLifecycle.create(
            root,
            experiment_id="archive-lineage-fixture",
            rounds=rounds(),
            transfer_datasets=[dataset("transfer-01", "7")],
        )

    def test_controller_sees_all_learning_data_but_not_current_dev_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            lifecycle = self.create(Path(tmp) / "lifecycle")
            first = lifecycle.controller_view("round-01")
            self.assertEqual(
                [item["dataset_id"] for item in first["train_full_access"]], ["train-01"]
            )
            self.assertEqual(
                [item["dataset_id"] for item in first["dev_feature_only"]], ["dev-01"]
            )
            self.assertFalse(first["dev_labels_visible"])
            self.assertFalse(first["transfer_visible"])

    def test_scored_dev_atomically_becomes_next_round_train(self):
        with tempfile.TemporaryDirectory() as tmp:
            lifecycle = self.create(Path(tmp) / "lifecycle")
            lifecycle.claim_dev_score("round-01", candidate_set_sha256="8" * 64)
            with self.assertRaisesRegex(ValueError, "frozen during Dev scoring"):
                lifecycle.controller_view("round-01")
            completed = lifecycle.complete_dev_score(
                "round-01", score_receipt_sha256="9" * 64
            )
            self.assertEqual(completed["transition"], {"from": "dev_sealed", "to": "train"})
            second = lifecycle.controller_view("round-02")
            visible = {item["dataset_id"]: item for item in second["train_full_access"]}
            self.assertEqual(set(visible), {"train-01", "dev-01", "train-02"})
            self.assertEqual(visible["dev-01"]["origin_role"], "dev")
            self.assertEqual(
                [item["dataset_id"] for item in second["dev_feature_only"]], ["dev-02"]
            )

    def test_consumed_dev_cannot_be_scored_again_or_used_out_of_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            lifecycle = self.create(Path(tmp) / "lifecycle")
            with self.assertRaisesRegex(ValueError, "future or consumed"):
                lifecycle.claim_dev_score("round-02", candidate_set_sha256="8" * 64)
            lifecycle.claim_dev_score("round-01", candidate_set_sha256="8" * 64)
            with self.assertRaisesRegex(ValueError, "already claimed"):
                lifecycle.claim_dev_score("round-01", candidate_set_sha256="8" * 64)
            lifecycle.complete_dev_score("round-01", score_receipt_sha256="9" * 64)
            with self.assertRaisesRegex(ValueError, "future or consumed"):
                lifecycle.claim_dev_score("round-01", candidate_set_sha256="a" * 64)

    def test_transfer_is_one_shot_after_every_learning_round(self):
        with tempfile.TemporaryDirectory() as tmp:
            lifecycle = self.create(Path(tmp) / "lifecycle")
            with self.assertRaisesRegex(ValueError, "all learning rounds"):
                lifecycle.freeze_transfer_submissions(submissions_sha256="a" * 64)
            for index in range(1, 4):
                lifecycle.claim_dev_score(
                    f"round-0{index}", candidate_set_sha256=f"{index}" * 64
                )
                lifecycle.complete_dev_score(
                    f"round-0{index}", score_receipt_sha256=f"{index + 3}" * 64
                )
            lifecycle.freeze_transfer_submissions(submissions_sha256="a" * 64)
            lifecycle.complete_transfer_score(score_receipt_sha256="b" * 64)
            with self.assertRaisesRegex(ValueError, "one frozen submission"):
                lifecycle.complete_transfer_score(score_receipt_sha256="c" * 64)
            audit = lifecycle.audit()
            self.assertTrue(audit["transfer_submissions_frozen"])
            self.assertTrue(audit["transfer_scored"])

    def test_ledger_is_append_only_and_tampering_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            lifecycle = self.create(Path(tmp) / "lifecycle")
            lifecycle.claim_dev_score("round-01", candidate_set_sha256="8" * 64)
            ledger = lifecycle.root / LEDGER_NAME
            records = ledger.read_text().splitlines()
            changed = json.loads(records[1])
            changed["payload"]["round_id"] = "round-02"
            records[1] = json.dumps(changed)
            ledger.write_text("\n".join(records) + "\n")
            with self.assertRaisesRegex(ValueError, "integrity failure"):
                lifecycle.audit()

    def test_datasets_cannot_be_reused_across_roles(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = rounds()
            bad[1]["train_datasets"] = [dataset("dev-01", "2")]
            with self.assertRaisesRegex(ValueError, "reused"):
                DataLifecycle.create(
                    Path(tmp) / "lifecycle",
                    experiment_id="archive-lineage-fixture",
                    rounds=bad,
                    transfer_datasets=[dataset("transfer-01", "7")],
                )


if __name__ == "__main__":
    unittest.main()
