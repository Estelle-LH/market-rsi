import csv
import gzip
import json
from pathlib import Path
import tempfile
import unittest

from sports_event_research.build_game_master import build


class GameMasterTests(unittest.TestCase):
    def test_whole_game_split_and_provider_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pbp = root / "play_by_play_2025.csv.gz"
            fields = ["game_id", "home_team", "away_team", "season_type", "week", "game_date"]
            games = [
                ("2025_01_A_B", "B", "A", "REG", "1", "2025-09-04"),
                ("2025_02_C_D", "D", "C", "REG", "2", "2025-09-11"),
                ("2025_03_E_F", "F", "E", "REG", "3", "2025-09-18"),
            ]
            with gzip.open(pbp, "wt", newline="") as stream:
                writer = csv.writer(stream); writer.writerow(fields)
                for game in games:
                    writer.writerow(game); writer.writerow(game)
            schedule = root / "sr" / "REG" / "schedule.json.gz"
            schedule.parent.mkdir(parents=True)
            payload = {"weeks": [{"sequence": index + 1, "games": [{
                "id": f"sr-{index}", "sr_id": f"sr:match:{index}", "status": "closed",
                "scheduled": game[-1] + "T20:00:00+00:00",
                "home": {"alias": game[1]}, "away": {"alias": game[2]},
            }]} for index, game in enumerate(games)]}
            with gzip.open(schedule, "wt") as stream:
                json.dump(payload, stream)
            result = build([pbp], root / "sr", root / "out", dev_games=1, final_games=1)
            self.assertEqual(result["split_counts"], {"market_train": 1, "route_dev": 1, "sealed_final": 1})
            self.assertEqual(result["sportradar_binding"]["matched_games"], 3)
            with (root / "out/game_master.csv").open() as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual([row["split_role"] for row in rows], ["market_train", "route_dev", "sealed_final"])
            self.assertEqual({row["nflverse_play_rows"] for row in rows}, {"2"})
            self.assertNotIn("score", rows[0])


if __name__ == "__main__":
    unittest.main()
