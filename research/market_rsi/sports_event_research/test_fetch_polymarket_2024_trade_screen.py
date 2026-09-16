import csv
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sports_event_research.fetch_polymarket_2024_trade_screen import choose_sample, run


FIELDS = ("polymarket_event_id", "event_slug", "event_start_utc", "nflverse_game_id",
          "condition_id", "tokens_json", "slug_order")


def mapping(path: Path, count=25) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for index in range(count):
            writer.writerow({"polymarket_event_id": str(index),
                             "event_slug": f"nfl-a-b-2024-09-{index + 1:02d}",
                             "event_start_utc": f"2024-09-{index + 1:02d}T00:00:00Z",
                             "nflverse_game_id": f"game-{index}",
                             "condition_id": f"condition-{index}",
                             "tokens_json": '["a","b"]', "slug_order": "away_home"})


class TradeScreen2024Tests(unittest.TestCase):
    def test_sample_is_spread_and_excludes_opened_earliest(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mapping.csv"
            mapping(path)
            selected = choose_sample(path)
            self.assertEqual(len(selected), 12)
            self.assertNotIn("game-0", {row["nflverse_game_id"] for row in selected})
            self.assertEqual(len({row["nflverse_game_id"] for row in selected}), 12)

    def test_failure_preserves_selection_and_stops_without_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "mapping.csv"
            mapping(path)
            with patch("sports_event_research.fetch_polymarket_2024_trade_screen.fetch_selected",
                       side_effect=OSError("source unavailable")) as mocked:
                with self.assertRaisesRegex(OSError, "source unavailable"):
                    run(path, root / "output", request_pause_seconds=0)
            self.assertEqual(mocked.call_count, 1)
            self.assertTrue((root / "output" / "selection_manifest.json").exists())
            self.assertTrue((root / "output" / "failure.json").exists())
            self.assertFalse((root / "output" / "manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
