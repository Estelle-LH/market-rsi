import unittest
from capture_raw_prefix import profile


class PrefixTests(unittest.TestCase):
    def test_aggregates_not_identifiers(self):
        r = profile([{'t': 1787270400000, 'src': 'ws', 'm': {'event_type': 'book',
                     'asset_id': 'not-exported', 'market': 'private-fixture', 'bids': [], 'asks': []}}])
        self.assertEqual(r['counts']['event_book'], 1)
        self.assertNotIn('not-exported', str(r))
        self.assertFalse(r['wrapper_clock_semantics_verified'])

    def test_other_date_rejected_before_market_analysis(self):
        with self.assertRaisesRegex(ValueError, 'outside exact'):
            profile([{'t': 1787788800000, 'src': 'ws', 'm': {}}])


if __name__ == '__main__': unittest.main()
