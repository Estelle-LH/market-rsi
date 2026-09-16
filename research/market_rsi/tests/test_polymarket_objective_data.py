from __future__ import annotations

from datetime import datetime, timezone
import unittest

from objective_train_audit import audit
from polymarket_data import NS, build_event_catalog
from polymarket_objective_data import (
    DISCOVERY_TARGET_SPECS,
    ObjectiveMaterializationPolicy,
    materialize_objective_books,
)


SOURCE = "d" * 64


def iso(ns: int) -> str:
    return datetime.fromtimestamp(ns / NS, timezone.utc).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")


def event(slug: str, start_ns: int) -> dict:
    available = start_ns - 10 * 60 * NS
    return {
        "observed_at": iso(available + 1_000_000),
        "request_start_ns": available - 2_000_000,
        "receive_ns": available,
        "event_id": slug,
        "slug": slug,
        "start_time": iso(start_ns),
        "game_id": f"venue-{slug}",
        "league": "mlb",
    }


def book(slug: str, time_ns: int, midpoint: float) -> dict:
    return {
        "observed_at": iso(time_ns + 1_000_000),
        "request_start_ns": time_ns - 2_000_000,
        "receive_ns": time_ns,
        "event_id": slug,
        "event_slug": slug,
        "market_slug": f"{slug}-moneyline",
        "http_status": 200,
        "state": "MARKET_STATE_OPEN",
        "qa_flags": [],
        "best_bid": midpoint - 0.01,
        "best_ask": midpoint + 0.01,
        "bid_qty_l1": 10,
        "ask_qty_l1": 20,
    }


class ObjectiveMaterializationTests(unittest.TestCase):
    def build_day(self, day: int) -> dict:
        base = int(datetime(2026, 9, day, 12, tzinfo=timezone.utc).timestamp()) * NS
        start = base + 30 * 60 * NS
        slug = f"g{day}"
        catalog, _ = build_event_catalog([event(slug, start)])
        records = [
            book(slug, base + second * NS, 0.40 + second / 10_000)
            for second in range(0, 86, 5)
        ]
        return materialize_objective_books(
            records,
            catalog,
            SOURCE,
            ObjectiveMaterializationPolicy(max_pregame_lead_ns=60 * 60 * NS),
        )

    def test_sparse_decision_uses_dense_future_quotes_for_all_window_targets(self):
        result = self.build_day(1)
        self.assertEqual(result["schema"], "polymarket_objective_labels_v1")
        self.assertEqual(result["feature_source"], "decision_quote_only")
        self.assertEqual(result["label_source"], "dense_future_quotes_only")
        row = result["rows"][0]
        self.assertEqual(row["target_metadata"]["future_observation_count"], 7)
        self.assertAlmostEqual(row["features"]["mid"], 0.40)
        self.assertAlmostEqual(
            row["target_candidates"]["future-midpoint-point-60s-v1"],
            0.406,
        )
        self.assertAlmostEqual(
            row["target_candidates"]["future-midpoint-window-mean-45-75s-v1"],
            0.406,
        )
        self.assertGreater(
            row["target_metadata"]["forward_ewma_effective_horizon_ms"],
            60_000,
        )
        self.assertGreaterEqual(
            row["label_available_ms"], row["label_window_end_ns"] // 1_000_000
        )

    def test_insufficient_dense_quotes_are_null_not_imputed(self):
        base = int(datetime(2026, 9, 1, 12, tzinfo=timezone.utc).timestamp()) * NS
        start = base + 30 * 60 * NS
        catalog, _ = build_event_catalog([event("g", start)])
        result = materialize_objective_books(
            [book("g", base, 0.4), book("g", base + 60 * NS, 0.5),
             book("g", base + 80 * NS, 0.6)],
            catalog,
            SOURCE,
            ObjectiveMaterializationPolicy(max_pregame_lead_ns=60 * 60 * NS),
        )
        row = result["rows"][0]
        self.assertEqual(
            row["target_candidates"]["future-midpoint-point-60s-v1"], 0.5
        )
        self.assertIsNone(
            row["target_candidates"]["future-midpoint-window-mean-45-75s-v1"]
        )
        self.assertEqual(result["imputation_count"], 0)

    def test_dense_materialization_feeds_train_only_objective_audit(self):
        rows = []
        for day in range(1, 5):
            rows.extend(self.build_day(day)["rows"])
        source = {"schema": "polymarket_objective_labels_v1", "rows": rows}
        result = audit(source, train_utc_dates=[
            "2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04"
        ])
        self.assertFalse(result["dev_labels_used"])
        self.assertEqual(
            result["candidate_diagnostics"]
            ["future-midpoint-window-mean-45-75s-v1"]["coverage_fraction"],
            1.0,
        )

    def test_discovery_grid_materializes_and_audits_longer_horizons(self):
        rows = []
        for day in range(1, 5):
            base = int(datetime(2026, 9, day, 12, tzinfo=timezone.utc).timestamp()) * NS
            start = base + 60 * 60 * NS
            slug = f"long-g{day}"
            catalog, _ = build_event_catalog([event(slug, start)])
            records = [
                book(slug, base + second * NS, 0.40 + second / 100_000)
                for second in range(0, 990, 5)
            ]
            materialized = materialize_objective_books(
                records, catalog, SOURCE,
                ObjectiveMaterializationPolicy(max_pregame_lead_ns=2 * 60 * 60 * NS),
                target_specs=DISCOVERY_TARGET_SPECS,
            )
            rows.extend(materialized["rows"])
        result = audit(
            {"schema": "polymarket_objective_labels_v1", "rows": rows},
            train_utc_dates=[
                "2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04"
            ],
        )
        self.assertEqual(len(result["candidate_diagnostics"]), 12)
        self.assertIn(
            "future-midpoint-window-mean-840-960s-v1",
            result["candidate_diagnostics"],
        )


if __name__ == "__main__":
    unittest.main()
