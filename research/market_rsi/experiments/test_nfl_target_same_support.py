import unittest

from experiments.nfl_target_same_support import TARGETS, common_indices, ranking


class SameSupportTests(unittest.TestCase):
    def test_common_indices_require_every_target(self):
        complete = {name: 0.1 for name in TARGETS}
        missing = dict(complete)
        missing[TARGETS[2]] = None
        rows = [
            {"game": "a", "targets": complete},
            {"game": "a", "targets": missing},
            {"game": "b", "targets": complete},
        ]
        self.assertEqual(common_indices(rows, ["a"]).tolist(), [0])

    def test_ranking_uses_minimum_fold_first(self):
        def candidate(aggregate, folds):
            return {
                "methods": {"ridge": {"relative_mse_improvement": aggregate}},
                "folds": [{"methods": {"ridge": {"relative_mse_improvement": value}}}
                          for value in folds],
            }
        results = {
            "stable": candidate(0.05, [0.04, 0.04, 0.04]),
            "higher_average": candidate(0.10, [0.01, 0.12, 0.13]),
        }
        self.assertEqual([row["target"] for row in ranking(results, "ridge")],
                         ["stable", "higher_average"])


if __name__ == "__main__":
    unittest.main()
