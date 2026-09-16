import copy
import unittest

from canary_activity_observations import MINUTE_MS, summarize


class ActivityTests(unittest.TestCase):
    def report(self, events=(), heartbeats=(), gaps=(), **kwargs):
        return summarize(events, heartbeats, gaps, start_ms=0,
                         end_ms=3 * MINUTE_MS, recorder_scope="synthetic-one-recorder", **kwargs)

    def test_no_observations_is_unknown_not_complete(self):
        r = self.report()
        self.assertEqual(r["minutes_with_neither_message_nor_heartbeat"], 3)
        self.assertFalse(r["clean_session_admitted"])
        self.assertFalse(r["fresh_validation_admitted"])

    def test_heartbeat_without_message_is_not_deleted_or_called_quiet(self):
        h = [{"emitted_at_ms": t, "source": "pm", "subscription_id": "s"}
             for t in [0, MINUTE_MS, 2 * MINUTE_MS]]
        r = self.report(heartbeats=h)
        self.assertEqual(r["minutes_with_heartbeat_but_no_pm_message"], 3)
        self.assertEqual((r["rows_deleted"], r["rows_imputed"]), (0, 0))
        self.assertFalse(r["clean_session_admitted"])

    def test_window_is_half_open_and_outside_rows_accounted(self):
        e = [{"received_at_ms": t, "event_type": "book"}
             for t in [-1, 0, MINUTE_MS - 1, 3 * MINUTE_MS]]
        r = self.report(e)
        self.assertEqual(r["observed_rows"]["pm_seen"], 4)
        self.assertEqual(r["observed_rows"]["pm_outside_window"], 2)
        self.assertEqual(r["minutes_with_pm_messages"], 1)

    def test_overlapping_gaps_not_double_counted_or_filled(self):
        r = self.report(gaps=[{"gap_start_ms": 0, "gap_end_ms": MINUTE_MS},
                              {"gap_start_ms": 1, "gap_end_ms": 2 * MINUTE_MS}])
        self.assertEqual(r["minutes_overlapping_any_recorded_gap"], 2)
        self.assertEqual(r["rows_imputed"], 0)

    def test_separate_heartbeat_sources_and_subscriptions(self):
        h = [{"emitted_at_ms": 0, "source": s, "subscription_id": sub}
             for s, sub in [("cex", None), ("pm", "a"), ("pm", "b")]]
        r = self.report(heartbeats=h)
        self.assertEqual(len(r["heartbeat_groups"]), 3)
        self.assertEqual(r["minutes_with_any_recorder_heartbeat"], 1)

    def test_inputs_preserved_and_resolution_only_counted(self):
        e = [{"received_at_ms": 0, "event_type": "market_resolved", "payload_json": "not read"}]
        before = copy.deepcopy(e)
        r = self.report(e)
        self.assertEqual(e, before)
        self.assertEqual(r["event_type_counts"], {"market_resolved": 1})
        self.assertNotIn("features", r)

    def test_reject_coerced_timestamps(self):
        for t in [None, 0.0, "0", True]:
            with self.subTest(t=t), self.assertRaises(ValueError):
                self.report([{"received_at_ms": t, "event_type": "book"}])

    def test_reject_reversed_gap(self):
        with self.assertRaises(ValueError):
            self.report(gaps=[{"gap_start_ms": 3, "gap_end_ms": 2}])

    def test_zero_gap_is_not_coverage(self):
        r = self.report(gaps=[{"gap_start_ms": 1, "gap_end_ms": 1}])
        self.assertEqual(r["observed_rows"]["zero_duration_gaps"], 1)
        self.assertEqual(r["minutes_overlapping_any_recorded_gap"], 0)

    def test_minute_alignment_and_scope_required(self):
        for start, end, scope in [(1, 60000, "a"), (0, 0, "a"), (0, 60000, "")]:
            with self.subTest(start=start, end=end, scope=scope), self.assertRaises(ValueError):
                summarize([], [], [], start_ms=start, end_ms=end, recorder_scope=scope)


if __name__ == "__main__":
    unittest.main()
