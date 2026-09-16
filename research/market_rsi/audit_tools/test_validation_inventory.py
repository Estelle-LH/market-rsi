import unittest
from audit_validation_inventory import summarize


class ValidationInventoryTests(unittest.TestCase):
    def test_known_opened_future_date_is_not_assumed_fresh(self):
        calendar=[{'utc_date':d,'minutes_with_events':3,'possible_minutes':1440}
                  for d in ('2026-04-18','2026-04-19','2026-05-14','2026-05-15')]
        r=summarize(calendar,['2026-04-18','2026-05-14'],['2026-04-18'])
        self.assertEqual(r['potential_later_dates_excluding_known_opened_upper_bound'],2)
        self.assertEqual(r['fresh_holdout_dates_admitted'],[])
        self.assertFalse(r['twenty_future_dates_even_arithmetically_possible'])
        self.assertFalse(r['exposure_audit_complete'])
        self.assertEqual([x['utc_date'] for x in r['later_than_all_known_opened_dates']],['2026-05-15'])

    def test_duplicate_metadata_dates_cannot_inflate_count(self):
        with self.assertRaisesRegex(ValueError,'unique'):
            summarize([{'utc_date':'2026-01-01'}]*2,['2026-01-01'],['2026-01-01'])


if __name__=='__main__':unittest.main()
