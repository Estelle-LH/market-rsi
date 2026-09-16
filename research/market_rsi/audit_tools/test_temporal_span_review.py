import copy
import unittest
from temporal_span_review import edge_case


class SpanReviewTests(unittest.TestCase):
    def setUp(self):
        self.c = {"clock": "source_ms", "decision_rule": "after_timestamp_group",
            "label_origin": "decision_time", "horizon_ms": 60000,
            "endpoint_rule": "backward_asof", "endpoint_tolerance_ms": 59999,
            "missing_endpoint": "unavailable", "invalid_quote": "invalidate",
            "claim": "recorded_observation_only"}

    def test_one_ms_is_allowed_without_modifying_policy(self):
        original = copy.deepcopy(self.c)
        r = edge_case(self.c)
        self.assertEqual(r["result"]["actual_span_ms"], 1)
        self.assertTrue(r["result"]["available"])
        self.assertEqual(self.c, original)
        self.assertFalse(r["source_admitted"])

    def test_exact_lookup_and_smaller_tolerance(self):
        for tolerance in (0, 1000):
            self.c["endpoint_tolerance_ms"] = tolerance
            r = edge_case(self.c)
            self.assertEqual(r["result"]["actual_span_ms"], 60000 - tolerance)

    def test_per_record_decision(self):
        self.c["decision_rule"] = "after_each_record"
        self.assertEqual(edge_case(self.c)["result"]["actual_span_ms"], 1)

    def test_wrong_direction_or_unsafe_tolerance_rejected(self):
        self.c["endpoint_rule"] = "forward_asof"
        with self.assertRaises(ValueError): edge_case(self.c)
        self.c["endpoint_rule"] = "backward_asof"
        self.c["endpoint_tolerance_ms"] = 60000
        with self.assertRaises(ValueError): edge_case(self.c)


if __name__ == "__main__": unittest.main()
