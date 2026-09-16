import unittest

from kalshi_replay import Replay, scaled


def snapshot(seq=1, market="a", t=1000, sid=1):
    return dict(t=t, m=dict(type="orderbook_snapshot", sid=sid, seq=seq,
        msg=dict(market_ticker=market, yes_dollars_fp=[["0.4000", "10.00"]],
                 no_dollars_fp=[["0.5000", "20.00"]])))


def delta(seq=2, market="a", t=1001, side="yes", price="0.4000", quantity="-1.00", sid=1):
    return dict(t=t, m=dict(type="orderbook_delta", sid=sid, seq=seq,
        msg=dict(market_ticker=market, side=side, price_dollars=price, delta_fp=quantity)))


class ReplayTests(unittest.TestCase):
    def test_increment_and_binary_ask_conversion(self):
        r = Replay("no_bids")
        row = r.accept(snapshot(), [0, 0])
        self.assertEqual((row["bid_1e4"], row["ask_1e4"]), (4000, 5000))
        row = r.accept(delta(), [0, 1])
        self.assertEqual(row["bid_size_1e2"], 900)

    def test_cross_file_state_and_global_sequence(self):
        r = Replay("no_bids")
        r.accept(snapshot(), [0, 0])
        r.accept(snapshot(2, "b", 1001), [0, 1])
        self.assertIsNotNone(r.accept(delta(3, t=1002), [1, 0]))
        self.assertIsNotNone(r.accept(delta(4, "b", 1003), [1, 1]))

    def test_gap_invalidates_all_market_books_on_subscription(self):
        r = Replay("no_bids")
        r.accept(snapshot(), [0, 0])
        r.accept(snapshot(2, "b", 1001), [0, 1])
        self.assertIsNone(r.accept(delta(4, t=1002), [0, 2]))
        self.assertIsNone(r.accept(delta(5, "b", 1003), [0, 3]))
        self.assertIsNotNone(r.accept(snapshot(6, "b", 1004), [0, 4]))
        self.assertIsNone(r.accept(delta(7, t=1005), [0, 5]))

    def test_restart_snapshot_recovers_only_that_market(self):
        r = Replay("no_bids")
        r.accept(snapshot(200), [0, 0])
        row = r.accept(snapshot(1, "b", 1001), [1, 0])
        self.assertEqual(row["stream_epoch"], 1)
        self.assertIsNone(r.accept(delta(2, t=1002), [1, 1]))

    def test_negative_quantity_needs_new_anchor(self):
        r = Replay("no_bids")
        r.accept(snapshot(), [0, 0])
        self.assertIsNone(r.accept(delta(quantity="-11.00"), [0, 1]))
        self.assertIsNone(r.accept(delta(3, t=1002, quantity="12.00"), [0, 2]))

    def test_missing_snapshot_never_invented(self):
        r = Replay("no_bids")
        self.assertIsNone(r.accept(delta(), [0, 0]))

    def test_one_sided_interval_breaks_quote_segment_without_losing_book(self):
        r = Replay("yes_asks")
        before = r.accept(snapshot(), [0, 0])
        self.assertIsNone(r.accept(delta(quantity="-10.00"), [0, 1]))
        after = r.accept(delta(3, t=1002, quantity="4.00"), [0, 2])
        self.assertEqual(before["stream_epoch"], after["stream_epoch"])
        self.assertEqual(before["anchor_key"], after["anchor_key"])
        self.assertNotEqual(before["quote_segment"], after["quote_segment"])
        self.assertEqual(after["bid_size_1e2"], 400)

    def test_one_market_losing_side_does_not_invalidate_other_market(self):
        r = Replay("yes_asks")
        r.accept(snapshot(), [0, 0])
        before = r.accept(snapshot(2, market="b", t=1001), [0, 1])
        r.accept(delta(3, t=1002, quantity="-10.00"), [0, 2])
        after = r.accept(delta(4, market="b", t=1003), [0, 3])
        self.assertEqual(before["quote_segment"], after["quote_segment"])

    def test_malformed_message_invalidates_all_streams(self):
        r = Replay("no_bids")
        r.accept(snapshot(), [0, 0])
        r.accept(snapshot(sid=2), [0, 1])
        r.accept({"m": {}}, [0, 2])
        self.assertIsNone(r.accept(delta(), [0, 3]))
        self.assertIsNone(r.accept(delta(sid=2), [0, 4]))

    def test_long_silence_invalidates_until_snapshot(self):
        r = Replay("no_bids", 100)
        r.accept(snapshot(), [0, 0])
        self.assertIsNone(r.accept(delta(t=1200), [0, 1]))

    def test_crossed_book_fails_closed(self):
        r = Replay("no_bids")
        r.accept(snapshot(), [0, 0])
        self.assertIsNone(r.accept(delta(side="no", price="0.7000", quantity="2.00"), [0, 1]))

    def test_fixed_point_exact_and_no_unit_guess(self):
        self.assertEqual(scaled("-0.01", 2), -1)
        for value in ("NaN", "+1.2", "1.001", 0.4):
            with self.assertRaises(ValueError):
                scaled(value, 2)

    def test_clock_reversal_aborts_batch(self):
        r = Replay("no_bids")
        r.accept(snapshot(), [0, 0])
        with self.assertRaises(ValueError):
            r.accept(delta(t=999), [0, 1])

    def test_yes_price_capture_is_not_complemented_twice(self):
        r = Replay("yes_asks")
        record = snapshot()
        record["m"]["msg"]["no_dollars_fp"] = [["0.5500", "20.00"], ["0.9900", "15.00"]]
        row = r.accept(record, [0, 0])
        self.assertEqual(row["ask_1e4"], 5500)
        self.assertEqual(row["ask_size_1e2"], 2000)
        row = r.accept(delta(side="no", price="0.5500", quantity="-1.00"), [0, 1])
        self.assertEqual(row["ask_size_1e2"], 1900)

    def test_price_convention_cannot_be_guessed_from_outcomes(self):
        with self.assertRaises(ValueError):
            Replay("auto")


if __name__ == "__main__":
    unittest.main()
