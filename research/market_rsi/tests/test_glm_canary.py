import unittest
from decimal import Decimal

from glm_canary import assess, cost


class CanaryTests(unittest.TestCase):
    def test_exact_pricing_and_cache(self):
        self.assertEqual(cost(100000, 20000), Decimal("0.729"))
        self.assertEqual(cost(100000, 0, 100000), Decimal("0.0972"))

    def test_invalid_tokens(self):
        for counts in ((1, 2, 3), (-1, 2, 0), (True, 3, 0)):
            with self.assertRaises(ValueError):
                cost(*counts)

    def test_response_is_independently_checked(self):
        text = '<think>private reasoning</think>{"case_verdicts":{"random_game_rows":"invalid"},"next_experiment":"Use chronological whole-game splits on earlier Train and Dev dates.","profitability_claim":false,"can_read_hidden_test":false}'
        self.assertTrue(assess(text)["all_checks_pass"])
        self.assertFalse(assess(text.replace('"invalid"', '"valid"'))["all_checks_pass"])
        self.assertFalse(assess("not json")["all_checks_pass"])


if __name__ == "__main__":
    unittest.main()
