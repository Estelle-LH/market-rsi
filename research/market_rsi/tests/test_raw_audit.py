import unittest

from raw_audit import RawAudit


def row(seq, market="a", kind="orderbook_delta", sid=1, t=1000):
    return dict(t=t, m=dict(type=kind, sid=sid, seq=seq, msg=dict(market_ticker=market, ts_ms=t - 20)))


class RawTests(unittest.TestCase):
    def test_subscription_sequence_not_per_market(self):
        a = RawAudit()
        for i, r in enumerate([row(1, kind="orderbook_snapshot"), row(2, market="b", kind="orderbook_snapshot"),
                               row(3), row(4, market="b")]):
            a.accept(r, i)
        self.assertTrue(a.summary()["standalone_replay_pass"])
        self.assertFalse(a.summary()["collector_receive_semantics_verified"])

    def test_gap_invalidates_all_markets(self):
        a = RawAudit()
        for i, r in enumerate([row(1, kind="orderbook_snapshot"), row(2, market="b", kind="orderbook_snapshot"),
                               row(4), row(5, market="b")]):
            a.accept(r, i)
        self.assertEqual(a.counts["sequence_discontinuity"], 1)
        self.assertEqual(a.counts["delta_without_snapshot"], 2)

    def test_missing_initial_snapshot_is_not_silently_valid(self):
        a = RawAudit()
        a.accept(row(100), 0)
        self.assertFalse(a.summary()["standalone_replay_pass"])

    def test_new_snapshot_recovers_that_market_only(self):
        a = RawAudit()
        for i, r in enumerate([row(1, kind="orderbook_snapshot"), row(5), row(6, kind="orderbook_snapshot"), row(7)]):
            a.accept(r, i)
        self.assertEqual(a.counts["deltas_with_initialized_snapshot"], 1)

    def test_timestamp_reversal_fails(self):
        a = RawAudit()
        a.accept(row(1, kind="orderbook_snapshot", t=1000), 0)
        a.accept(row(2, t=999), 1)
        self.assertFalse(a.summary()["parsing_pass"])


if __name__ == "__main__":
    unittest.main()
