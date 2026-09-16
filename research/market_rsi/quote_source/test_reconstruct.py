import copy
import hashlib
import json
import unittest

from quote_source.reconstruct import QuoteReconstructor

T = 1787270630696


def snap(t=T-1, *, asset="a", bids=(".49",), asks=(".50", ".51", ".52")):
    return {"t": t, "src": "ws", "m": {"event_type": "book", "timestamp": str(t),
        "asset_id": asset, "market": "market", "bids": [{"price": p, "size": "2"} for p in bids],
        "asks": [{"price": p, "size": "2"} for p in asks]}}


def delta(side="BUY", px=".51", size="2", bid=".51", ask=".52", t=T):
    return {"t": t, "src": "ws", "m": {"event_type": "price_change", "market": "market",
        "timestamp": str(t), "price_changes": [{"asset_id": "a", "side": side,
        "price": px, "size": size, "best_bid": bid, "best_ask": ask}]}}


class ReconstructTests(unittest.TestCase):
    def setUp(self):
        self.engine = QuoteReconstructor("a", "market")
        self.ordinal = 0

    def run_record(self, record):
        self.ordinal += 1
        sha = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()
        return self.engine.process(record, self.ordinal, sha)

    def test_real_case_mechanism_synthetic_values(self):
        self.run_record(snap())
        events = [self.run_record(r)[0] for r in
            (delta(), delta("SELL", ".50", "0"), delta("SELL", ".51", "0"))]
        self.assertEqual([r["depth"]["status"] for r in events], ["crossed", "locked", "uncrossed"])
        self.assertEqual([r["depth"]["bbo_matches_source"] for r in events], [False, False, True])
        self.assertTrue(all(r["source"]["status"] == "uncrossed" and r["price_candidate"] for r in events))
        self.assertTrue(all(r["source"]["bid_size"] is None and r["source"]["ask_size"] is None for r in events))
        self.assertTrue(all(not r["source_admitted"] for r in events))
        final = self.run_record(snap(t=T+1, bids=(".49", ".51"), asks=(".52",)))[0]
        self.assertTrue(final["depth"]["full_map_equals_next_snapshot"])

    def test_equal_timestamp_distinct_quotes_not_collapsed(self):
        first = self.run_record(delta())[0]
        second = self.run_record(delta(ask=".53"))[0]
        self.assertNotEqual(first["source"]["ask"], second["source"]["ask"])
        self.assertNotEqual(first["key"], second["key"])

    def test_future_mutation_does_not_change_past_outputs(self):
        prefix = self.run_record(snap()) + self.run_record(delta())
        before = copy.deepcopy(prefix)
        self.run_record(snap(t=T+1, bids=(".90",), asks=(".91",)))
        self.assertEqual(prefix, before)

    def test_missing_bbo_no_stale_source_or_depth_fallback(self):
        self.run_record(snap())
        record = delta(); del record["m"]["price_changes"][0]["best_ask"]
        row = self.run_record(record)[0]
        self.assertEqual(row["source"]["status"], "one_sided")
        self.assertIsNone(row["source"]["ask"])
        self.assertFalse(row["price_candidate"])

    def test_source_before_anchor_does_not_invent_depth(self):
        row = self.run_record(delta())[0]
        self.assertTrue(row["price_candidate"])
        self.assertEqual(row["depth"]["status"], "unanchored")

    def test_array_order_uses_extrema(self):
        row = self.run_record(snap(bids=(".40", ".49", ".44"), asks=(".55", ".52", ".54")))[0]
        self.assertEqual((row["source"]["bid"], row["source"]["ask"]), ("0.49", "0.52"))

    def test_rest_and_ws_snapshots_reanchor(self):
        for src in ("rest", "ws"):
            r = snap(t=T+self.ordinal); r["src"] = src
            if src == "rest": del r["m"]["event_type"]
            row = self.run_record(r)[0]
            self.assertEqual(row["depth"]["status"], "uncrossed")

    def test_absolute_quantity_then_zero_deletes(self):
        self.run_record(snap())
        self.run_record(delta(px=".49", size="7"))
        r = snap(t=T+1); r["m"]["bids"][0]["size"] = "7"
        self.assertTrue(self.run_record(r)[0]["depth"]["full_map_equals_next_snapshot"])
        row = self.run_record(delta(px=".49", size="0", t=T+2))[0]
        self.assertIsNone(row["depth"]["bid"])

    def test_same_message_internal_order_and_token_separation(self):
        r = delta(); other = copy.deepcopy(r["m"]["price_changes"][0]); other["asset_id"] = "b"
        r["m"]["price_changes"] = [other, r["m"]["price_changes"][0], other]
        rows = self.run_record(r)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["key"], [1, 0, 1])
        self.assertEqual(self.run_record(snap(asset="b")), [])

    def test_identity_conflict_or_missing_rejected(self):
        for market in ("other", None):
            r = snap(); r["m"]["market"] = market
            with self.assertRaisesRegex(ValueError, "token-market"):
                self.run_record(r)

    def test_cross_lock_boundary_and_one_sided_remain_visible(self):
        for bid, ask, expected in ((".7", ".6", "crossed"), (".5", ".5", "locked"),
                                 ("0", "1", "boundary_unknown"), (None, ".5", "one_sided")):
            row = self.run_record(delta(bid=bid, ask=ask))[0]
            self.assertEqual(row["source"]["status"], expected)
            self.assertFalse(row["price_candidate"])

    def test_bad_numbers_fail_closed(self):
        for value in ("NaN", "Infinity", "-0.1", "2", True, {}, "bad"):
            row = self.run_record(delta(ask=value))[0]
            self.assertIn("malformed_source_bbo", row["issues"])
            self.assertFalse(row["price_candidate"])

    def test_malformed_delta_loses_anchor_until_snapshot(self):
        self.run_record(snap())
        row = self.run_record(delta(size="-1"))[0]
        self.assertFalse(row["price_candidate"])
        self.assertEqual(row["depth"]["status"], "unanchored")
        self.assertEqual(self.run_record(delta())[0]["depth"]["status"], "unanchored")
        self.assertEqual(self.run_record(snap(t=T+1))[0]["depth"]["status"], "uncrossed")

    def test_partial_or_duplicate_snapshot_loses_anchor(self):
        for mode in ("missing", "duplicate"):
            r = snap()
            if mode == "missing": del r["m"]["asks"]
            else: r["m"]["asks"].append(r["m"]["asks"][0].copy())
            row = self.run_record(r)[0]
            self.assertIn("malformed_snapshot", row["issues"])
            self.assertEqual(row["depth"]["status"], "unanchored")

    def test_empty_snapshot_is_not_old_quote(self):
        self.run_record(snap())
        row = self.run_record(snap(t=T, bids=(), asks=()))[0]
        self.assertEqual(row["source"]["status"], "missing")
        self.assertFalse(row["price_candidate"])

    def test_regressing_clocks_not_sorted_or_backfilled(self):
        self.run_record(snap(t=T))
        row = self.run_record(delta(t=T-1))[0]
        self.assertIn("source_ms_regression", row["issues"])
        self.assertIn("capture_ms_regression", row["issues"])
        self.assertFalse(row["price_candidate"])
        self.assertEqual(row["depth"]["status"], "unanchored")

    def test_missing_source_clock_and_seconds_units(self):
        for value in (None, 1787270630, True):
            r = delta(); r["m"]["timestamp"] = value
            row = self.run_record(r)[0]
            self.assertIn("source_ms_missing_or_invalid", row["issues"])
            self.assertFalse(row["price_candidate"])

    def test_unknown_event_invalidates_without_guessing(self):
        self.run_record(snap())
        r = snap(t=T); r["m"]["event_type"] = "unrecognized"
        row = self.run_record(r)[0]
        self.assertIn("unsupported_target_event", row["issues"])
        self.assertEqual(row["depth"]["status"], "unanchored")

    def test_trade_and_tick_not_relabelled_as_quote(self):
        for kind in ("last_trade_price", "tick_size_change"):
            r = snap(); r["m"]["event_type"] = kind
            self.assertEqual(self.run_record(r), [])

    def test_bbo_event_no_size_invention(self):
        r = snap(); r["m"] = {"asset_id": "a", "market": "market", "timestamp": str(T),
            "event_type": "best_bid_ask", "best_bid": ".45", "best_ask": ".55"}
        row = self.run_record(r)[0]
        self.assertTrue(row["price_candidate"])
        self.assertIsNone(row["source"]["ask_size"])

    def test_ordinal_and_record_hash_required(self):
        with self.assertRaisesRegex(ValueError, "sha256"):
            self.engine.process(snap(), 1, "bad")
        self.engine.process(snap(), 1, "f"*64)
        with self.assertRaisesRegex(ValueError, "ordinal"):
            self.engine.process(snap(), 1, "f"*64)

    def test_level_resource_limit(self):
        self.engine = QuoteReconstructor("a", "market", max_levels=1)
        row = self.run_record(snap())[0]
        self.assertIn("malformed_snapshot", row["issues"])


if __name__ == "__main__":
    unittest.main()
