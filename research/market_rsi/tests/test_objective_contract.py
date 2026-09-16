from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from objective_contract import (build_objective_contract, discovery_policy,
                                freeze_objective_contract, objective_catalog,
                                promote_diagnostic_objective_for_formal,
                                validate_objective_contract)


class ObjectiveContractTests(unittest.TestCase):
    def kwargs(self):
        return {
            "experiment_id": "fresh-objective-study",
            "objective_id": "future-midpoint-window-mean-45-75s-v1",
            "train_diagnostics_sha256": "a" * 64,
            "literature_snapshot_sha256": "b" * 64,
            "literature_ids": ["zhang-zohren-roberts-deeplob-2018"],
            "evidence_class": "formal_learning",
        }

    def test_objective_is_selected_before_dev_and_scale_free_score_is_required(self):
        value = build_objective_contract(**self.kwargs())
        self.assertTrue(value["selection"]["selected_before_dev_schedule"])
        self.assertFalse(value["selection"]["dev_labels_used"])
        self.assertEqual(
            value["objective"]["comparison_metric"],
            "one_minus_candidate_mse_over_persistence_mse",
        )
        self.assertIn("label_stability_under_small_window_or_horizon_changes",
                      discovery_policy()["required_train_only_diagnostics"])

    def test_changing_target_or_hash_invalidates_contract(self):
        value = build_objective_contract(**self.kwargs())
        changed = copy.deepcopy(value)
        changed["objective"]["label"]["future_window_seconds"] = [30, 90]
        with self.assertRaisesRegex(ValueError, "objective definition"):
            validate_objective_contract(changed)
        changed = copy.deepcopy(value)
        changed["selection"]["dev_labels_used"] = True
        with self.assertRaisesRegex(ValueError, "selection boundary"):
            validate_objective_contract(changed)

    def test_freeze_is_exclusive_and_catalog_keeps_multiple_research_targets(self):
        self.assertGreaterEqual(len(objective_catalog()["objectives"]), 4)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "objective.json"
            freeze_objective_contract(path, **self.kwargs())
            with self.assertRaises(FileExistsError):
                freeze_objective_contract(path, **self.kwargs())

    def test_pre_dev_choice_can_be_adopted_without_resampling_or_change(self):
        kwargs = self.kwargs()
        kwargs["objective_id"] = "future-midpoint-window-mean-270-330s-v1"
        kwargs["evidence_class"] = "diagnostic"
        diagnostic = build_objective_contract(**kwargs)
        formal, receipt = promote_diagnostic_objective_for_formal(diagnostic)
        self.assertEqual(formal["objective"], diagnostic["objective"])
        self.assertEqual(formal["selection"]["evidence_class"], "formal_learning")
        self.assertFalse(receipt["controller_resampled"])
        self.assertTrue(receipt["selection_evidence_unchanged"])


if __name__ == "__main__":
    unittest.main()
