import copy
import unittest
from quote_source.reconstruct import QuoteReconstructor
from quote_source.test_reconstruct import delta, snap, T
from population_quote_profile import PopulationProfile
from audit_population_quote_profile import describe, verify_population_sums


def fixture():
    p = PopulationProfile(QuoteReconstructor)
    for i, r in enumerate((delta(), delta(t=T+1), delta(ask=".54", t=T+2), snap(asset="other")), 1):
        p.process(r, i, "a"*64)
    return p.summary(include_entities=True)


class AuditTests(unittest.TestCase):
    def test_exact_denominators(self):
        p = fixture(); verify_population_sums(p)
        s = describe(p)
        self.assertEqual(s["equal_mid_fraction_event_weighted"], 0.5)
        self.assertEqual(s["entities_with_valid_pair_denominator"], 1)
        self.assertEqual(s["entities_without_valid_pairs"], 1)
        self.assertEqual(s["top_one_entity_quote_share"], 0.75)

    def test_undefined_ratios_are_not_zero_performance(self):
        s = describe(PopulationProfile(QuoteReconstructor).summary(include_entities=True))
        self.assertIsNone(s["equal_mid_fraction_event_weighted"])
        self.assertIsNone(s["source_depth_mismatch_fraction_of_comparable"])
        self.assertFalse(s["source_admitted"])

    def test_entity_total_tampering_rejected(self):
        p = fixture(); p["entities"][0]["counts"]["quote_observations"] += 1
        with self.assertRaisesRegex(ValueError, "population sums"): verify_population_sums(p)

    def test_gap_and_pair_disagreement_rejected(self):
        p = fixture()
        for item in [p["totals"], *p["entities"]]: item["counts"].pop("pair_gap_1..1000ms", None)
        with self.assertRaisesRegex(ValueError, "gap denominator"): verify_population_sums(p)


if __name__ == "__main__": unittest.main()
