import unittest

from sports_event_research.diagnose_2024_60s_missingness import classify


class MissingnessTests(unittest.TestCase):
    def test_mutually_exclusive_missingness_reasons(self):
        self.assertEqual(classify(1000, []), "no_prior_trade")
        self.assertEqual(classify(1000, [1001]), "no_prior_trade")
        self.assertEqual(classify(1000, [699, 1010]), "stale_prior_trade")
        self.assertEqual(classify(1000, [700, 1061]), "recent_prior_no_post_trade")
        self.assertEqual(classify(1000, [700, 1060]), "covered")
        self.assertEqual(classify(1000, [1000, 1060]), "covered")

    def test_post_trade_must_be_strictly_later_than_play(self):
        self.assertEqual(classify(1000, [1000]), "recent_prior_no_post_trade")

    def test_unsorted_trades_rejected(self):
        with self.assertRaisesRegex(ValueError, "sorted"):
            classify(1000, [1010, 990])


if __name__ == "__main__":
    unittest.main()
