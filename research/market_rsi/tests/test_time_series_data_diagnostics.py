from __future__ import annotations

from datetime import datetime, timezone
import unittest

from time_series_data_diagnostics import diagnose


def ms(day: int, seconds: int) -> int:
    base = datetime(2026, 9, day, tzinfo=timezone.utc).timestamp() * 1000
    return int(base + seconds * 1000)


class TimeSeriesDataDiagnosticsTests(unittest.TestCase):
    def old_flat_source(self) -> dict:
        rows = []
        for day in (1, 2):
            for second in (0, 60, 120):
                rows.append({
                    "row_id": f"{day}-{second}",
                    "game_id": f"game-{day}",
                    "market_id": f"market-{day}",
                    "decision_ms": ms(day, second),
                    "features": {"mid": 0.5},
                    "target": 0.5,
                })
        return {"schema": "polymarket_midpoint_labels_v1", "rows": rows}

    def test_finds_flat_target_sparse_materialization_and_missing_trades(self):
        result = diagnose(
            self.old_flat_source(),
            opened_train_utc_dates=["2026-09-01", "2026-09-02"],
        )
        self.assertEqual(result["point_target"]["unchanged_fraction"], 1.0)
        self.assertEqual(result["decision_cadence_seconds"]["p50"], 60.0)
        self.assertIn("point_target_is_at_least_90_percent_unchanged",
                      result["findings"])
        self.assertIn("verified_trade_stream_is_absent", result["findings"])
        self.assertIn(
            "materialized_decisions_are_too_sparse_for_45_75s_window_labels",
            result["findings"],
        )
        self.assertFalse(result["dev_labels_used"])

    def test_verified_trade_stream_must_have_explicit_provenance(self):
        source = self.old_flat_source()
        source["trade_stream_provenance"] = {"verified": True}
        result = diagnose(source, opened_train_utc_dates=[
            "2026-09-01", "2026-09-02"
        ])
        self.assertTrue(result["source_inventory"]["verified_trade_stream_present"])
        self.assertNotIn("verified_trade_stream_is_absent", result["findings"])

    def test_rejects_dev_or_unknown_schema_by_construction(self):
        with self.assertRaises(ValueError):
            diagnose({"schema": "unknown", "rows": []},
                     opened_train_utc_dates=["2026-09-01"])


if __name__ == "__main__":
    unittest.main()
