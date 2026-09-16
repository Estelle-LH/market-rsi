import copy
import unittest

from metadata_inventory import summarize


def row(market="KXMLBGAME-26SEP021800AAABBB-AAA", start="2026-09-02T22:00:00Z"):
    return {"venue": "kalshi", "market": market, "outcome": market.rsplit("-", 1)[-1],
            "league": "MLB", "matchup": "AAABBB", "outcome_label": "AAA", "game_start_utc": start, "market_slug": ""}


def day(day, rows):
    return {"day": day, "path": "fixture-metadata", "sha256": "a"*64, "bytes": 100, "rows": rows}


class MetadataTests(unittest.TestCase):
    def test_related_outcomes_and_midnight_files_count_as_one_candidate_game(self):
        one = row()
        two = row(market="KXMLBGAME-26SEP021800AAABBB-BBB")
        report = summarize([day("2026-09-02", [one, two]), day("2026-09-03", [one, two])])
        stats = report["family_summary"]
        self.assertEqual(stats["candidate_events"], 1)
        self.assertEqual(stats["events_mentioned_on_multiple_capture_days"], 1)
        self.assertEqual(len(stats["event_keys_in_both_provisional_file_partitions"]), 1)
        self.assertEqual(stats["starts_in_provisional_train_date_range"], 1)
        self.assertFalse(report["scoring_ready"])

    def test_other_venue_does_not_increase_kalshi_count(self):
        report = summarize([day("2026-09-02", [row(), dict(row(), venue="polymarket")])])
        self.assertEqual(report["sources"][0]["native_kalshi_rows"], 1)
        self.assertEqual(report["families"]["KXMLBGAME"]["contracts"], 1)

    def test_inconsistent_schedule_is_reported_not_silently_chosen(self):
        report = summarize([day("2026-09-02", [row()]), day("2026-09-03", [row(start="2026-09-03T22:00:00Z")])])
        self.assertEqual(report["family_summary"]["inconsistent_metadata_events"], 1)
        self.assertEqual(report["family_summary"]["candidate_start_dates_utc"], {})

    def test_missing_or_timezone_free_schedule_stays_unknown(self):
        for start in ("", "2026-09-02T22:00:00"):
            report = summarize([day("2026-09-02", [row(start=start)])])
            self.assertEqual(report["family_summary"]["inconsistent_metadata_events"], 1)

    def test_malformed_ticker_is_excluded_with_count(self):
        report = summarize([day("2026-09-02", [row(market="bad-ticker")])])
        self.assertEqual(report["sources"][0]["unrecognized_native_ticker_rows"], 1)
        self.assertEqual(report["family_summary"]["candidate_events"], 0)

    def test_repeated_or_reordered_source_days_rejected(self):
        for values in ([day("2026-09-02", []), day("2026-09-02", [])],
                       [day("2026-09-03", []), day("2026-09-02", [])]):
            with self.assertRaises(ValueError):
                summarize(values)

    def test_future_listings_do_not_count_as_games_in_train_dev_range(self):
        report = summarize([day("2026-09-02", [row(start="2026-09-10T22:00:00Z")])])
        self.assertEqual(report["family_summary"]["starts_in_provisional_train_date_range"], 0)
        self.assertEqual(report["family_summary"]["starts_in_provisional_dev_date_range"], 0)


if __name__ == "__main__":
    unittest.main()
