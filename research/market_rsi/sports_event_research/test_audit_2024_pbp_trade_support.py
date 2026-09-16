import unittest

from sports_event_research.audit_2024_pbp_trade_support import support, timestamp


class TimingSupportTests(unittest.TestCase):
    def test_requires_fresh_pre_print_and_new_future_print(self):
        self.assertEqual(support([699, 1010], 1000), {30: False, 60: False, 300: False})
        self.assertEqual(support([700, 1030], 1000), {30: True, 60: True, 300: True})
        self.assertEqual(support([701, 1031], 1000), {30: False, 60: True, 300: True})
        self.assertEqual(support([999, 1301], 1000), {30: False, 60: False, 300: False})

    def test_carried_forward_pre_play_price_is_not_a_label(self):
        self.assertEqual(support([999], 1000), {30: False, 60: False, 300: False})
        self.assertEqual(support([1000, 1030], 1000), {30: True, 60: True, 300: True})

    def test_timestamp_requires_timezone(self):
        self.assertEqual(timestamp("2024-09-06T00:44:42.100Z"), 1725583482)
        with self.assertRaisesRegex(ValueError, "timezone"):
            timestamp("2024-09-06T00:44:42")


if __name__ == "__main__":
    unittest.main()
