"""Offline checks for the historical role/date boundary auditor."""

import unittest

from supervisor_harness.audit_2025_split_dates import assign_roles


class SplitDateAuditTests(unittest.TestCase):
    def test_same_day_role_boundary_is_reported(self) -> None:
        games = [("2025-09-01", "a"), ("2025-09-02", "b"),
                 ("2025-09-02", "c"), ("2025-09-03", "d")]
        out = assign_roles(games, dev_games=1, final_games=1)
        self.assertEqual(out["role_game_counts"],
                         {"market_train": 2, "route_dev": 1, "sealed_final": 1})
        self.assertEqual(out["cross_role_same_dates"]["market_train__route_dev"],
                         ["2025-09-02"])

    def test_duplicate_game_id_fails(self) -> None:
        with self.assertRaises(ValueError):
            assign_roles([("2025-09-01", "a"), ("2025-09-02", "a"),
                          ("2025-09-03", "b")], 1, 1)


if __name__ == "__main__":
    unittest.main()
