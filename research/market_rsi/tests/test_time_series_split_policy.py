from __future__ import annotations

import copy
import unittest

from time_series_split_policy import (DAY_MS, POLICY, policy_contract,
                                      train_cv_split, validate_outer_dev)


def row(name: str, game: str, day: int, target: float = 0.5) -> dict:
    decision = day * DAY_MS + 1_000
    return {
        "row_id": name,
        "game_id": game,
        "market_id": game + "-market",
        "decision_ms": decision,
        "feature_available_ms": decision,
        "features": {"mid": 0.5},
        "target": target,
        "label_available_ms": decision + 60_000,
    }


class TimeSeriesSplitPolicyTests(unittest.TestCase):
    def test_contract_freezes_time_order_grouping_and_final_date_minimum(self):
        contract = policy_contract()
        self.assertEqual(contract["order"], "past_to_future_only")
        self.assertFalse(contract["random_shuffle"])
        self.assertFalse(contract["boundary_may_use_targets"])
        self.assertEqual(contract["group_key"], "game_id")
        self.assertEqual(contract["formal_train_cv_holdout_utc_days"], 3)
        self.assertEqual(contract["maximum_label_lateness_seconds"], 5)
        self.assertTrue(contract["outer_dev_selection_receipt_required"])
        self.assertEqual(contract["outer_dev_minimum_utc_days"], 3)
        self.assertEqual(contract["outer_dev_minimum_games"], 8)
        self.assertEqual(contract["final_promotion_minimum_untouched_utc_days"], 20)
        self.assertEqual(len(contract["policy_sha256"]), 64)

    def test_formal_split_requires_four_dates_and_uses_last_three(self):
        with self.assertRaisesRegex(ValueError, "at least 4 UTC dates"):
            train_cv_split([row("d1", "g1", 1), row("d2", "g2", 2),
                            row("d3", "g3", 3)], evidence_class="formal_learning")
        rows = [row(f"d{day}", f"g{day}", day) for day in range(1, 6)]
        fit, cv, audit = train_cv_split(rows, evidence_class="formal_learning")
        self.assertEqual({item["game_id"] for item in fit}, {"g1", "g2"})
        self.assertEqual({item["game_id"] for item in cv}, {"g3", "g4", "g5"})
        self.assertEqual(audit["forecast_origins"], 1)
        self.assertEqual(audit["cv_utc_dates"], [3, 4, 5])

    def test_targets_cannot_change_split_membership(self):
        rows = [row(f"d{day}", f"g{day}", day, target=day / 10)
                for day in range(1, 6)]
        fit, cv, audit = train_cv_split(rows, evidence_class="formal_learning")
        changed = copy.deepcopy(rows)
        for item in changed:
            item["target"] = 1.0 - item["target"]
        fit_changed, cv_changed, audit_changed = train_cv_split(
            changed, evidence_class="formal_learning")
        self.assertEqual([item["row_id"] for item in fit],
                         [item["row_id"] for item in fit_changed])
        self.assertEqual([item["row_id"] for item in cv],
                         [item["row_id"] for item in cv_changed])
        self.assertEqual(audit, audit_changed)
        self.assertFalse(audit["boundary_selected_using_targets"])

    def test_boundary_crossing_game_is_purged_not_split(self):
        rows = [row("early", "early-game", 1),
                row("cross-before", "cross-game", 1),
                row("cross-after", "cross-game", 2),
                row("late", "late-game", 2)]
        rows[1]["decision_ms"] = 2 * DAY_MS - 30_000
        rows[1]["feature_available_ms"] = rows[1]["decision_ms"]
        rows[1]["label_available_ms"] = rows[1]["decision_ms"] + 60_000
        fit, cv, audit = train_cv_split(rows)
        self.assertEqual({item["game_id"] for item in fit}, {"early-game"})
        self.assertEqual({item["game_id"] for item in cv}, {"late-game"})
        self.assertEqual(audit["omitted_boundary_games"], 1)
        self.assertGreater(audit["purged_gap_ms"], 0)

    def test_realistic_capture_lateness_is_allowed_but_bounded(self):
        rows = [row(f"d{day}", f"g{day}", day) for day in range(1, 6)]
        rows[0]["label_available_ms"] += 4_999
        train_cv_split(rows, evidence_class="formal_learning")
        rows[0]["label_available_ms"] += 2
        with self.assertRaisesRegex(ValueError, "exceeds frozen window"):
            train_cv_split(rows, evidence_class="formal_learning")

    def test_formal_split_uses_frozen_longer_objective_window(self):
        rows = [row(f"d{day}", f"g{day}", day) for day in range(1, 6)]
        for item in rows:
            item["label_available_ms"] = item["decision_ms"] + 330_000
        with self.assertRaisesRegex(ValueError, "exceeds frozen window"):
            train_cv_split(rows, evidence_class="formal_learning")
        _, _, audit = train_cv_split(
            rows, evidence_class="formal_learning",
            label_delay_bounds_ms=(330_000, 330_000),
        )
        self.assertEqual(audit["label_delay_bounds_ms"], [330_000, 330_000])
        self.assertEqual(audit["label_delay_source"], "frozen_objective_contract")
        rows[0]["label_available_ms"] += 1
        with self.assertRaisesRegex(ValueError, "exceeds frozen window"):
            train_cv_split(
                rows, evidence_class="formal_learning",
                label_delay_bounds_ms=(330_000, 330_000),
            )

    def test_outer_dev_must_be_later_and_game_disjoint(self):
        train = [row("t1", "train-game", 1)]
        dev = [row(f"d{index}", f"dev-game-{index}", 2 + index % 3)
               for index in range(8)]
        dev.sort(key=lambda item: item["decision_ms"])
        audit = validate_outer_dev(
            train, dev, evidence_class="formal_prospective_learning"
        )
        self.assertEqual(audit["outer_method"], POLICY.outer_dev_method)
        self.assertEqual(audit["dev_openings_allowed"], 1)
        with self.assertRaisesRegex(ValueError, "shares a game"):
            changed = copy.deepcopy(dev)
            changed[0]["game_id"] = "train-game"
            validate_outer_dev(train, changed,
                               evidence_class="formal_prospective_learning")
        with self.assertRaisesRegex(ValueError, "strictly later"):
            changed = copy.deepcopy(dev)
            for item in changed:
                item["decision_ms"] -= 2 * DAY_MS
                item["feature_available_ms"] = item["decision_ms"]
                item["label_available_ms"] = item["decision_ms"] + 60_000
            changed.sort(key=lambda item: item["decision_ms"])
            validate_outer_dev(train, changed,
                               evidence_class="formal_prospective_learning")

    def test_formal_outer_dev_rejects_one_day_or_too_few_games(self):
        train = [row("t1", "train-game", 1)]
        one_day = [row(f"d{index}", f"g{index}", 2) for index in range(8)]
        with self.assertRaisesRegex(ValueError, "too few distinct UTC dates"):
            validate_outer_dev(
                train, one_day, evidence_class="formal_prospective_learning"
            )
        too_few = [row(f"m{index}", f"m-game-{index}", 2 + index)
                   for index in range(3)]
        with self.assertRaisesRegex(ValueError, "too few whole games"):
            validate_outer_dev(
                train, too_few, evidence_class="formal_prospective_learning"
            )


if __name__ == "__main__":
    unittest.main()
