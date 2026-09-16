import copy
import unittest
from vantage_coverage_conclusion import conclude


class ConclusionTests(unittest.TestCase):
    def setUp(self):
        self.plan = {"body": {"plan_id": "fixture", "minimum_complete_sessions": 20}}
        self.calendar = {"status": "complete", "prices_payloads_labels_read": False,
                         "unchanged_identity": {"st_ino": 7}, "observations": {"tables": {
                             k: {"present_dates_union": ["2026-06-03"]}
                             for k in ("pm_events", "cex_trades", "heartbeats")}}}
        self.day = {"status": "complete", "prices_payloads_labels_read": False,
                    "unchanged_identity": {"st_ino": 7}, "observations": {
                        "date_utc": "2026-06-03", "tables": {
                            "pm_events": {"rows": 10000000, "occupied_minutes_union": 1},
                            "heartbeats": {"partitions": [{"source": "process", "occupied_minutes": 1}]}}}}

    def test_millions_of_rows_cannot_be_twenty_sessions(self):
        r = conclude(self.plan, self.calendar, [self.day])
        self.assertFalse(r["necessary_calendar_condition_passed"])
        self.assertFalse(r["source_admitted"])
        self.assertEqual(r["possible_session_count_upper_bound"], 1)

    def test_date_count_does_not_imply_admission(self):
        self.plan["body"]["minimum_complete_sessions"] = 1
        r = conclude(self.plan, self.calendar, [self.day])
        self.assertTrue(r["necessary_calendar_condition_passed"])
        self.assertFalse(r["source_admitted"])

    def test_missing_duplicate_failed_and_mixed_receipts_rejected(self):
        for days in ([], [self.day, self.day]):
            with self.assertRaises(ValueError):
                conclude(self.plan, self.calendar, days)
        for field, value in (("status", "failed"), ("unchanged_identity", {"st_ino": 8}),
                             ("prices_payloads_labels_read", True)):
            bad = copy.deepcopy(self.day)
            bad[field] = value
            with self.assertRaises(ValueError):
                conclude(self.plan, self.calendar, [bad])


if __name__ == "__main__":
    unittest.main()
