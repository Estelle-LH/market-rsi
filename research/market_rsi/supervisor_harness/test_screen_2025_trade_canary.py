"""No-network selection test for the public 2025 trade canary."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from supervisor_harness import screen_2025_trade_canary as canary


class TradeCanaryTests(unittest.TestCase):
    def test_selects_earliest_mapped_game_without_trade_or_score(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            mapping = [{"game_date": "2025-09-08", "event_id": "2", "game_id": "g2",
                        "condition_id": "c2"},
                       {"game_date": "2025-09-04", "event_id": "1", "game_id": "g1",
                        "condition_id": "c1"}]
            raw = json.dumps(mapping).encode()
            (root / "mapping.json").write_bytes(raw)
            (root / "manifest.json").write_text(json.dumps({
                "formal_data_admitted": False, "trade_coverage_verified": False,
                "mapped_unique_games": 2, "schedule_games": 2,
                "mapping_sha256": canary.sha(raw)}))
            event = {"id": "1", "startTime": "2025-09-05T00:20:00Z", "markets": [{
                "conditionId": "c1", "clobTokenIds": '["a","b"]'}]}
            with patch.object(canary, "load_events", return_value=([event], [])):
                selected = canary.select(root, root)
            self.assertEqual(selected["game_id"], "g1")
            self.assertEqual(selected["condition_id"], "c1")
            self.assertNotIn("score", selected)


if __name__ == "__main__":
    unittest.main()
