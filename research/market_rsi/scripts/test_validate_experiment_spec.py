from __future__ import annotations

import copy
from pathlib import Path
import unittest

from market_rsi import load_json
from scripts.validate_experiment_spec import validate


ROOT = Path(__file__).resolve().parents[1]


class PredictionExperimentSpecTests(unittest.TestCase):
    def setUp(self):
        self.spec = load_json(ROOT / "PREDICTION_EXPERIMENT_DRAFT_2026-09-21.json")

    def test_blocked_draft_is_valid(self):
        self.assertEqual(validate(self.spec), self.spec)

    def test_draft_cannot_authorize_execution(self):
        changed = copy.deepcopy(self.spec)
        changed["frozen_now"]["execution_authorized"] = True
        with self.assertRaises(ValueError):
            validate(changed)

    def test_target_cannot_be_selected_before_data_admission(self):
        changed = copy.deepcopy(self.spec)
        changed["target_selection"]["selected"] = "future_trade_price_change_300s"
        with self.assertRaises(ValueError):
            validate(changed)

    def test_final_cannot_shrink_below_twenty_dates(self):
        changed = copy.deepcopy(self.spec)
        changed["split_plan"]["final"]["minimum_distinct_dates"] = 19
        with self.assertRaises(ValueError):
            validate(changed)

    def test_draft_cannot_add_paid_authority(self):
        changed = copy.deepcopy(self.spec)
        changed["budget"]["new_authorization_usd"] = "10"
        with self.assertRaises(ValueError):
            validate(changed)

    def test_strong_baseline_library_cannot_drop_hgb(self):
        changed = copy.deepcopy(self.spec)
        changed["baseline_plan"]["library"].remove("hgb")
        with self.assertRaises(ValueError):
            validate(changed)

    def test_pnl_cannot_become_the_unvalidated_primary_claim(self):
        changed = copy.deepcopy(self.spec)
        changed["frozen_now"]["pnl_policy"] = "optimize"
        with self.assertRaises(ValueError):
            validate(changed)

    def test_missing_pending_commitment_is_rejected(self):
        changed = copy.deepcopy(self.spec)
        del changed["pending_before_execution"]["target_contract_sha256"]
        with self.assertRaises(ValueError):
            validate(changed)


if __name__ == "__main__":
    unittest.main()
