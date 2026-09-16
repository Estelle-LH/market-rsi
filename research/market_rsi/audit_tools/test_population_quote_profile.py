import copy
import hashlib
import json
import unittest

from quote_source.reconstruct import QuoteReconstructor
from quote_source.test_reconstruct import snap, delta, T
from population_quote_profile import PopulationProfile


class PopulationTests(unittest.TestCase):
    def setUp(self):
        self.profile = PopulationProfile(QuoteReconstructor)
        self.ordinal = 0

    def send(self, record):
        self.ordinal += 1
        self.profile.process(record, self.ordinal, hashlib.sha256(json.dumps(record).encode()).hexdigest())

    def summary(self):
        return self.profile.summary(include_entities=True)

    def test_multiple_tokens_same_record_preserve_indices(self):
        r = delta(); other = copy.deepcopy(r["m"]["price_changes"][0]); other["asset_id"] = "b"
        r["m"]["price_changes"].insert(0, other)
        sha = hashlib.sha256(json.dumps(r).encode()).hexdigest()
        self.profile.process(r, 1, sha, cases={(1, 0, 1): sha})
        result = self.summary()
        self.assertEqual(result["breadth"]["entities"], 2)
        self.assertEqual(result["case"][0]["key"], [1, 0, 1])
        self.assertEqual(result["input_counts"]["quote_observations"], 2)
        self.assertEqual(result["breadth"]["observed_market_ids"], 1)
        self.assertNotIn('"asset_id"', json.dumps(result))
        self.assertNotIn('"bid":', json.dumps(result))

    def test_three_record_case_profile(self):
        for r in (snap(), delta(), delta("SELL", ".50", "0"), delta("SELL", ".51", "0")):
            self.send(r)
        total = self.summary()["totals"]
        self.assertEqual(total["counts"]["bbo_mismatch"], 2)
        self.assertEqual(total["depth_status"]["crossed"], 1)
        self.assertEqual(total["source_status"], {"uncrossed": 4})

    def test_no_price_change_is_retained(self):
        self.send(delta()); self.send(delta(t=T+100000))
        s = self.summary(); c = s["totals"]["counts"]
        self.assertEqual(c["equal_mid_pairs"], 1)
        self.assertEqual(c["pair_gap_>60000ms"], 1)
        self.assertFalse(s["continuous_flat_price_proven"])
        self.assertFalse(s["outage_classified"])
        self.assertEqual(s["entities"][0]["max_equal_mid_observed_span_ms"], 100000)

    def test_invalid_quote_breaks_flat_pair(self):
        self.send(delta()); self.send(delta(ask=None)); self.send(delta(t=T+1000))
        self.assertEqual(self.summary()["totals"]["counts"].get("adjacent_valid_mid_pairs", 0), 0)

    def test_mid_movement_count(self):
        self.send(delta()); self.send(delta(ask=".54", t=T+1))
        self.assertEqual(self.summary()["totals"]["counts"]["changed_mid_pairs"], 1)

    def test_minute_breadth_not_quote_count(self):
        for _ in range(4): self.send(delta())
        self.assertEqual(self.summary()["entities"][0]["candidate_quote_minutes"], 1)
        self.assertEqual(self.summary()["totals"]["counts"]["quote_observations"], 4)

    def test_trade_only_entity_remains_in_breadth(self):
        r = snap(); r["m"]["event_type"] = "last_trade_price"
        self.send(r)
        b = self.summary()["breadth"]
        self.assertEqual(b["entities"], 1)
        self.assertEqual(b["entities_with_quotes"], 0)

    def test_unanchored_delta_not_missing_quote(self):
        self.send(delta())
        c = self.summary()["totals"]["counts"]
        self.assertEqual(c["unanchored_delta_observations"], 1)
        self.assertEqual(c["price_candidates"], 1)

    def test_source_crossing_preserved(self):
        self.send(delta(bid=".55", ask=".52"))
        self.assertEqual(self.summary()["breadth"]["entities_with_source_crossings"], 1)
        self.assertEqual(self.summary()["totals"]["counts"]["price_candidates"], 0)

    def test_checkpoint_does_not_mutate_history(self):
        self.send(snap()); before = self.summary(); saved = copy.deepcopy(before)
        self.send(delta())
        self.assertEqual(before, saved)

    def test_identity_conflict_stops(self):
        self.send(snap()); r = delta(); r["m"]["market"] = "other"
        with self.assertRaisesRegex(ValueError, "market changed"): self.send(r)

    def test_entity_cap_fails_instead_of_dropping(self):
        self.profile = PopulationProfile(QuoteReconstructor, max_entities=1)
        self.send(snap())
        with self.assertRaisesRegex(ValueError, "resource"): self.send(snap(asset="b"))

    def test_unknown_message_count_not_quote_or_inferred_venue(self):
        self.send({"t": T, "m": {"event_type": "unknown"}})
        s = self.summary()
        self.assertEqual(s["input_counts"]["messages_without_routable_asset"], 1)
        self.assertEqual(s["input_counts"].get("quote_observations", 0), 0)

    def test_multiple_same_asset_changes_one_raw_record(self):
        self.send(snap()); r = delta(); r["m"]["price_changes"].append(copy.deepcopy(r["m"]["price_changes"][0]))
        self.send(r)
        s = self.summary()
        self.assertEqual(s["totals"]["counts"]["raw_records_with_entity"], 2)
        self.assertEqual(s["totals"]["counts"]["quote_observations"], 3)
        self.assertEqual(s["entities"][0]["event_kinds"]["price_change"], 1)


if __name__ == "__main__": unittest.main()
