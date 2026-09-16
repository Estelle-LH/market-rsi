from __future__ import annotations

from datetime import datetime, timezone
import unittest

from objective_train_audit import audit


def ms(day: int, seconds: int) -> int:
    base = datetime(2026, 9, day, tzinfo=timezone.utc).timestamp() * 1000
    return int(base + seconds * 1000)


class ObjectiveTrainAuditTests(unittest.TestCase):
    def source(self):
        rows = []
        for day in range(1, 5):
            for second in range(0, 181, 15):
                mid = 0.5 + (0.01 if second >= 60 else 0.0)
                rows.append({
                    "row_id": f"{day}-{second}",
                    "game_id": f"game-{day}",
                    "market_id": f"market-{day}",
                    "decision_ms": ms(day, second),
                    "features": {"mid": mid},
                    "target": 0.5 + (0.01 if second + 60 >= 60 else 0.0),
                })
        return {"schema": "polymarket_midpoint_labels_v1", "rows": rows}

    def test_audit_compares_point_and_window_without_selecting(self):
        result = audit(self.source(), train_utc_dates=[
            "2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04"
        ])
        self.assertFalse(result["dev_labels_used"])
        self.assertIsNone(result["selection"]["objective_selected"])
        window = result["candidate_diagnostics"][
            "future-midpoint-window-mean-45-75s-v1"
        ]
        self.assertGreater(window["coverage_fraction"], 0)
        self.assertIn("window_half_stability", window)
        ewma = result["candidate_diagnostics"][
            "future-midpoint-window-forward-ewma-45-75s-v1"
        ]
        self.assertGreater(ewma["effective_horizon_seconds"], 60)
        self.assertIn("future-midpoint-window-median-45-75s-v1",
                      result["candidate_diagnostics"])

    def test_requires_four_train_dates(self):
        with self.assertRaisesRegex(ValueError, "at least four"):
            audit(self.source(), train_utc_dates=["2026-09-01"])


if __name__ == "__main__":
    unittest.main()
