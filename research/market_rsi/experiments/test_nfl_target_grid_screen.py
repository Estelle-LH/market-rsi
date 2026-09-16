import csv
from pathlib import Path
import tempfile
import unittest

from experiments.nfl_target_grid_screen import feature_values, load_target_map, shortlist


class TargetGridScreenTests(unittest.TestCase):
    def test_target_map_rejects_inconsistent_common_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "targets.csv"
            with path.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=[
                    "game", "scheduled_utc", "play_id", "a", "b",
                    "eligible_for_common_comparison",
                ])
                writer.writeheader()
                writer.writerow({
                    "game": "g", "scheduled_utc": "2025-01-01T00:00:00+00:00",
                    "play_id": "p", "a": "0.1", "b": "",
                    "eligible_for_common_comparison": "1",
                })
            with self.assertRaisesRegex(ValueError, "common-support"):
                load_target_map(path, ["a", "b"])

    def test_target_map_preserves_missing_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "targets.csv"
            with path.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=[
                    "game", "scheduled_utc", "play_id", "a", "b",
                    "eligible_for_common_comparison",
                ])
                writer.writeheader()
                writer.writerow({
                    "game": "g", "scheduled_utc": "2025-01-01T00:00:00+00:00",
                    "play_id": "p", "a": "0.1", "b": "",
                    "eligible_for_common_comparison": "0",
                })
            target_map, names = load_target_map(path, ["a", "b"])
            self.assertEqual(names, ["a", "b"])
            self.assertEqual(target_map[("g", "p")]["targets"], {"a": 0.1, "b": None})

    def test_shortlist_requires_all_predeclared_conditions(self):
        def target(skill, folds, coverage=0.8, positive=0.7, upper=-0.001):
            report = {
                "relative_mse_improvement": skill,
                "positive_game_fraction": positive,
                "candidate_minus_baseline_date_block_interval": {"upper": upper},
            }
            return {
                "profile": {"full_population_coverage": coverage},
                "methods": {"ridge": report},
                "folds": [{"methods": {"ridge": {"relative_mse_improvement": value}}}
                          for value in folds],
            }
        results = {
            "robust": target(0.08, [0.04, 0.06, 0.05]),
            "one_bad_fold": target(0.10, [0.09, -0.01, 0.12]),
            "weak_interval": target(0.12, [0.1, 0.1, 0.1], upper=0.001),
            "low_coverage": target(0.20, [0.2, 0.2, 0.2], coverage=0.49),
        }
        selected = shortlist(results)
        self.assertEqual([row["target"] for row in selected], ["robust"])
        self.assertEqual(selected[0]["status"], "opened_train_shortlist_only")

    def test_missing_features_allowed_only_when_every_target_is_unavailable(self):
        raw = {name: "1" for name in (
            "home_price_pre", "regulation_seconds_remaining", "period",
            "home_score_diff_pre", "possession_is_home", "down",
            "yards_to_first_down", "yards_to_goal", "official", "is_no_play",
            "is_scoring_play", "home_score_change", "away_score_change", "play_type",
        )}
        raw["home_price_pre"] = ""
        self.assertIsNone(feature_values(raw, {"targets": {"a": None, "b": None}}))
        with self.assertRaisesRegex(ValueError, "observed target"):
            feature_values(raw, {"targets": {"a": 0.1, "b": None}})


if __name__ == "__main__":
    unittest.main()
