import hashlib
import json
import unittest

from quote_source.reconstruct import QuoteReconstructor
from quote_source.test_reconstruct import snap, delta
from validate_quote_repair import summarize


def records():
    values = [snap(), delta(), delta("SELL", ".50", "0"), delta("SELL", ".51", "0")]
    return [(i, r, hashlib.sha256(json.dumps(r, sort_keys=True).encode()).hexdigest())
            for i, r in enumerate(values, 1)]


class ValidationTests(unittest.TestCase):
    def test_same_record_comparison_and_no_raw_export(self):
        data = records(); cases = {i: h for i, _, h in data[1:]}
        result = summarize(data, QuoteReconstructor("a", "market"), cases)
        self.assertTrue(result["known_cross_record_case_fixed"])
        self.assertEqual(result["counts"]["observations"], 4)
        self.assertEqual(result["counts"]["candidates_with_depth_mismatch"], 2)
        self.assertEqual(result["same_record_depth_to_source_status"]["crossed -> uncrossed"], 1)
        self.assertNotIn('"asset_id"', json.dumps(result))
        self.assertNotIn('"bid":', json.dumps(result))

    def test_changed_case_refused(self):
        with self.assertRaisesRegex(ValueError, "case changed"):
            summarize(records(), QuoteReconstructor("a", "market"), {2: "f"*64, 3: "f"*64, 4: "f"*64})

    def test_missing_case_does_not_pass(self):
        data = records(); cases = {i: h for i, _, h in data[1:]}
        result = summarize(data[:-1], QuoteReconstructor("a", "market"), cases)
        self.assertFalse(result["known_cross_record_case_fixed"])

    def test_real_inner_indices_preserved_with_other_token(self):
        r = delta(); r["m"]["price_changes"].insert(0, {"asset_id": "other"})
        h = hashlib.sha256(json.dumps(r).encode()).hexdigest()
        result = summarize([(1, r, h)], QuoteReconstructor("a", "market"), {1: h})
        self.assertEqual(result["case"][0]["key"], [1, 0, 1])


if __name__ == "__main__": unittest.main()
