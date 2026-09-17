"""Offline tests of the frozen, outcome-blind diagnostic sample."""

import unittest

from supervisor_harness.plan_2023_density_audit import sample, stratum


class StratifiedDiagnosticTests(unittest.TestCase):
    def test_week_bands(self) -> None:
        self.assertEqual(stratum("2023_01_DET_KC"), "weeks_01_06")
        self.assertEqual(stratum("2023_21_KC_BAL"), "weeks_19_22")
        with self.assertRaises(ValueError):
            stratum("2023_23_FOO_BAR")

    def test_determinism_and_unmatched_denominator(self) -> None:
        rows = []
        for week in (1, 7, 13, 19):
            for i in range(4):
                rows.append({"game_id": f"2023_{week:02d}_A{chr(65+i)}_B{chr(65+i)}",
                             "condition_id": str(week * 10 + i), "token_ids": ["1", "2"]})
        missing = ["2023_18_X_Y", "2023_22_Y_X"]
        first = sample(rows, missing)
        self.assertEqual(first, sample(list(reversed(rows)), list(reversed(missing))))
        self.assertEqual(first["scheduled_games"], 18)
        self.assertEqual(len(first["selection"]), 12)
        self.assertEqual(sum(s["unmatched_games"] for s in first["stratum_summary"]), 2)
        with self.assertRaises(ValueError):
            sample(rows, [rows[0]["game_id"]])


if __name__ == "__main__":
    unittest.main()
