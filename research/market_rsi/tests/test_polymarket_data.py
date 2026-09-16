import copy
import unittest

from polymarket_data import (
    NS,
    MaterializationPolicy,
    SplitCounts,
    build_event_catalog,
    information_available_ns,
    materialize_books,
    public_projection,
    scorer_rows,
    whole_game_chronological_split,
)


SOURCE = "a" * 64


def iso(ns):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ns / NS, timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def event(slug, start_ns, event_id=None):
    available = start_ns - 10 * 60 * NS
    return {"observed_at": iso(available + 1_000_000), "request_start_ns": available - 2_000_000,
            "receive_ns": available, "event_id": event_id or slug, "slug": slug,
            "start_time": iso(start_ns), "game_id": f"venue-{slug}", "league": "mlb"}


def book(slug, t, *, bid=.4, ask=.42, market="moneyline", flags=None, event_id=None):
    return {"observed_at": iso(t + 1_000_000), "request_start_ns": t - 2_000_000,
            "receive_ns": t, "event_id": event_id or slug, "event_slug": slug,
            "market_slug": f"{slug}-{market}", "http_status": 200,
            "state": "MARKET_STATE_OPEN", "qa_flags": [] if flags is None else flags,
            "best_bid": bid, "best_ask": ask, "bid_qty_l1": 10, "ask_qty_l1": 20,
            "transact_time": "1999-01-01T00:00:00Z"}


class AvailabilityTests(unittest.TestCase):
    def test_uses_observed_clock_not_receive_or_exchange_clock(self):
        row = book("g", 1_800_000_000_000_000_000)
        self.assertEqual(information_available_ns(row), row["receive_ns"] + 1_000_000)

    def test_observed_before_receive_fails_closed(self):
        row = book("g", 1_800_000_000_000_000_000)
        row["observed_at"] = iso(row["receive_ns"] - 1_000_000)
        with self.assertRaisesRegex(ValueError, "precedes"):
            information_available_ns(row)

    def test_large_clock_disagreement_fails_closed(self):
        row = book("g", 1_800_000_000_000_000_000)
        row["observed_at"] = iso(row["receive_ns"] + 10 * NS)
        with self.assertRaisesRegex(ValueError, "clocks disagree"):
            information_available_ns(row)


class MaterializationTests(unittest.TestCase):
    def setUp(self):
        self.start = 1_800_000_000 * NS
        self.catalog, _ = build_event_catalog([event("g1", self.start)])
        self.policy = MaterializationPolicy(max_pregame_lead_ns=20 * 60 * NS)

    def test_first_future_midpoint_at_60_seconds_is_label(self):
        base = self.start - 5 * 60 * NS
        result = materialize_books([
            book("g1", base, bid=.40, ask=.42),
            book("g1", base + 59 * NS, bid=.44, ask=.46),
            book("g1", base + 61 * NS, bid=.46, ask=.48),
        ], self.catalog, SOURCE, self.policy)
        self.assertEqual(len(result["rows"]), 1)
        self.assertAlmostEqual(result["rows"][0]["target"], .47)
        self.assertAlmostEqual(result["rows"][0]["labels"]["mid_change"], .06)
        self.assertEqual(result["rows"][0]["label_target_ns"], base + 1_000_000 + 60 * NS)
        self.assertFalse(result["exchange_transact_time_used"])
        self.assertEqual(result["imputation_count"], 0)
        self.assertEqual(result["availability_clock"], "observed_at")
        self.assertFalse(result["sequence_or_reconnect_state_required"])
        scored = scorer_rows(result["rows"])
        self.assertAlmostEqual(scored[0]["midpoint"], .41)
        self.assertAlmostEqual(scored[0]["target_midpoint"], .47)
        self.assertEqual(scored[0]["target_ms"], result["rows"][0]["label_target_ns"] // 1_000_000)

    def test_late_endpoint_is_censored_not_filled(self):
        base = self.start - 5 * 60 * NS
        result = materialize_books([
            book("g1", base),
            book("g1", base + 70 * NS, bid=.5, ask=.52),
        ], self.catalog, SOURCE, self.policy)
        self.assertEqual(result["rows"], [])
        self.assertEqual(result["counts"]["label_missing_within_lateness"], 1)
        self.assertEqual(result["imputation_count"], 0)

    def test_flagged_and_missing_bbo_are_excluded(self):
        base = self.start - 5 * 60 * NS
        missing = book("g1", base + NS)
        missing["best_bid"] = None
        result = materialize_books([
            book("g1", base, flags=["stale"]), missing,
        ], self.catalog, SOURCE, self.policy)
        self.assertEqual(result["counts"]["qa_flagged"], 1)
        self.assertEqual(result["counts"]["missing_or_invalid_bbo"], 1)
        self.assertEqual(result["counts"].get("scheduled_decisions", 0), 0)

    def test_market_cannot_change_event_identity(self):
        row = book("g1", self.start - 5 * 60 * NS, event_id="wrong")
        with self.assertRaisesRegex(ValueError, "identity"):
            materialize_books([row], self.catalog, SOURCE, self.policy)

    def test_null_watchlist_rows_are_explicitly_excluded(self):
        row = book("g1", self.start - 5 * 60 * NS)
        row["event_slug"] = None
        result = materialize_books([row], self.catalog, SOURCE, self.policy)
        self.assertEqual(result["counts"]["null_watchlist_identity"], 1)

    def test_event_mapping_mutation_fails(self):
        changed = event("g1", self.start)
        changed["game_id"] = "another"
        with self.assertRaisesRegex(ValueError, "identity changed"):
            build_event_catalog([event("g1", self.start), changed])

    def test_null_event_watchlist_row_is_excluded(self):
        extra = event("extra", self.start + NS)
        extra["event_id"] = None
        catalog, counts = build_event_catalog([event("g1", self.start), extra])
        self.assertEqual(set(catalog), {"g1"})
        self.assertEqual(counts["null_watchlist_identity"], 1)

    def test_bad_event_clock_is_counted_and_excluded(self):
        bad = event("bad", self.start + NS)
        bad["observed_at"] = iso(bad["receive_ns"] + 10 * NS)
        catalog, counts = build_event_catalog([event("g1", self.start), bad])
        self.assertEqual(set(catalog), {"g1"})
        self.assertEqual(counts["invalid_collector_clock"], 1)

    def test_bad_book_clock_is_counted_and_excluded(self):
        row = book("g1", self.start - 5 * 60 * NS)
        row["observed_at"] = iso(row["receive_ns"] + 10 * NS)
        result = materialize_books([row], self.catalog, SOURCE, self.policy)
        self.assertEqual(result["counts"]["invalid_collector_clock"], 1)
        self.assertEqual(result["rows"], [])


class SplitTests(unittest.TestCase):
    def rows(self):
        rows = []
        # Four separated game blocks.  Each has two markets to prove that all
        # contracts belonging to one event stay in one partition.
        for i, split in enumerate(("train", "route", "audit", "test")):
            start = (1_800_000_000 + i * 86_400) * 1000
            for market in ("moneyline", "spread"):
                decision = start - 3_600_000
                rows.append({"row_id": f"{split}-{market}",
                    "game_id": f"polymarket:g{i}", "event_slug": f"g{i}",
                    "market_id": f"g{i}-{market}", "game_start_ms": start,
                    "decision_ms": decision, "feature_available_ms": decision,
                    "label_available_ms": decision + 60_000, "target": .01,
                    "features": {"mid": .5}})
        return rows

    def test_whole_games_and_contracts_are_disjoint(self):
        result = whole_game_chronological_split(
            self.rows(), SplitCounts(train=1, route_dev=1, audit_dev=1, test=1)
        )
        assigned = result["assignments"]
        self.assertEqual(assigned["train"], ["polymarket:g0"])
        self.assertEqual(len(result["rows"]["train"]), 2)
        self.assertEqual(len({g for values in assigned.values() for g in values}), 4)
        self.assertTrue(result["strict_information_chronology"])

    def test_information_time_overlap_is_rejected(self):
        rows = self.rows()
        rows[2]["feature_available_ms"] = rows[0]["label_available_ms"]
        rows[2]["decision_ms"] = rows[2]["feature_available_ms"]
        with self.assertRaisesRegex(ValueError, "embargo"):
            whole_game_chronological_split(
                rows, SplitCounts(train=1, route_dev=1, audit_dev=1, test=1)
            )

    def test_same_start_games_cannot_cross_boundary(self):
        rows = self.rows()
        for row in rows:
            if row["game_id"] == "polymarket:g1":
                row["game_start_ms"] = rows[0]["game_start_ms"]
                row["decision_ms"] = rows[0]["decision_ms"]
                row["feature_available_ms"] = rows[0]["feature_available_ms"]
                row["label_available_ms"] = rows[0]["label_available_ms"]
        with self.assertRaisesRegex(ValueError, "simultaneous"):
            whole_game_chronological_split(
                rows, SplitCounts(train=1, route_dev=1, audit_dev=1, test=1)
            )

    def test_public_projection_does_not_open_test(self):
        split = whole_game_chronological_split(
            self.rows(), SplitCounts(train=1, route_dev=1, audit_dev=1, test=1)
        )
        public = public_projection(split, "secret-nonce-that-is-longer-than-32-characters")
        self.assertNotIn("test", public)
        self.assertNotIn("target", public["route_dev"][0])
        self.assertNotIn("target", public["audit_dev"][0])
        self.assertTrue(public["test_commitment"])
        self.assertFalse(public["test_rows_exposed"])

    def test_market_group_cannot_cross_games(self):
        rows = self.rows()
        rows[2]["market_id"] = rows[0]["market_id"]
        with self.assertRaisesRegex(ValueError, "multiple games"):
            whole_game_chronological_split(
                rows, SplitCounts(train=1, route_dev=1, audit_dev=1, test=1)
            )


if __name__ == "__main__":
    unittest.main()
