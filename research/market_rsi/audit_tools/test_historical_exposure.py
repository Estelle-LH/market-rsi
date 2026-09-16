import unittest
from datetime import datetime, timezone
from audit_historical_exposure import possible_utc_dates, summarize


class HistoricalExposureTests(unittest.TestCase):
    def test_utc_clock_not_partition_filename(self):
        start = int(datetime(2026, 4, 18, 23, 59, tzinfo=timezone.utc).timestamp() * 1000)
        self.assertEqual(possible_utc_dates(start, start + 60000), ['2026-04-18', '2026-04-19'])

    def test_invalid_clock_bounds_fail(self):
        for pair in [(2, 1), (True, 2), (-1, 10), (1.5, 10)]:
            with self.assertRaises(ValueError):
                possible_utc_dates(*pair)

    def test_runner_scan_is_not_controller_label_exposure_or_fresh_admission(self):
        result = summarize(['2026-04-18', '2026-04-19', '2026-04-20'], [], [],
                           ['2026-04-18'], [{'possible_utc_dates': ['2026-04-18', '2026-04-19']}])
        self.assertEqual(result['known_open_dates_lower_bound'], ['2026-04-18'])
        self.assertEqual(result['runner_scan_possible_dates_outside_selected_six'], ['2026-04-19'])
        self.assertEqual(result['fresh_holdout_dates_admitted'], [])
        self.assertFalse(result['exposure_audit_complete'])
        self.assertTrue(all(not d['fresh_holdout_admitted'] for d in result['per_date']))

    def test_declared_old_open_dates_remain_open(self):
        result = summarize(['2026-05-14'], ['2026-05-14'], [], [], [])
        self.assertTrue(result['per_date'][0]['known_open_not_fresh'])

    def test_overlapping_fit_and_check_rejected(self):
        with self.assertRaisesRegex(ValueError, 'overlap'):
            summarize(['2026-04-18'], [], ['2026-04-18'], ['2026-04-18'], [])

    def test_duplicate_dates_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            summarize(['2026-04-18'] * 2, [], [], [], [])


if __name__ == '__main__':
    unittest.main()
