import gzip
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from sports_event_research.run_state_surprise_discovery import same_event_post_states, state_vector


class StateSurpriseTests(unittest.TestCase):
    def test_home_field_position_uses_possession_direction(self):
        home = state_vector(seconds=120, score_diff=0, period=4, possession_is_home=1,
                            down=1, yards_to_first=10, yards_to_goal=20)
        away = state_vector(seconds=120, score_diff=0, period=4, possession_is_home=0,
                            down=1, yards_to_first=10, yards_to_goal=20)
        self.assertEqual(home[-1], 80)
        self.assertEqual(away[-1], 20)

    def test_time_and_field_are_bounded_without_future_data(self):
        value = state_vector(seconds=9999, score_diff=7, period=9, possession_is_home=1,
                             down=9, yards_to_first=999, yards_to_goal=-4)
        self.assertEqual(value[0], 1.0)
        self.assertEqual(value[3], 5.0)
        self.assertEqual(value[5:], [4.0, 100.0, 0.0, 100.0])

    def test_post_state_comes_from_same_event_not_a_successor_row(self):
        event = {"type": "play", "id": "p", "wall_clock": "2025-01-01T00:00:00Z",
                 "home_points": 7, "away_points": 0,
                 "end_situation": {"clock": "13:50", "down": 1, "yfd": 10,
                     "possession": {"alias": "A"},
                     "location": {"alias": "H", "yardline": 25}}}
        game = {"summary": {"home": {"alias": "H"}, "away": {"alias": "A"}},
                "periods": [{"number": 1, "pbp": [event]}]}
        rows = [{"game": "g", "play_id": "p"}]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); panel = root / "play_trade_alignment.csv"; panel.write_text("x\n")
            pbp = root / "pbp.json.gz"
            with gzip.open(pbp, "wt") as stream: json.dump(game, stream)
            from sports_event_research.run_train_method_screen import sha256
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"pbp_path": str(pbp), "pbp_sha256": sha256(pbp)}))
            receipts = [{"game": "g", "panel_path": str(panel),
                         "alignment_manifest_sha256": sha256(manifest)}]
            states, audit = same_event_post_states(rows, receipts)
        self.assertEqual(states.shape, (1, 9))
        self.assertTrue(np.isfinite(states).all())
        self.assertEqual(audit[0]["eligible_same_event_rows"], 1)


if __name__ == "__main__":
    unittest.main()
