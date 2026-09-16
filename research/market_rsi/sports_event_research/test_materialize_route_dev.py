import json
from pathlib import Path
import tempfile
import unittest

from sports_event_research.materialize_route_dev import load_frozen_selections


class MaterializeRouteDevTests(unittest.TestCase):
    def test_partial_cohort_is_rejected_before_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selection = {"nflverse_game_id": "g", "split_role": "route_dev"}
            path = root / "g.selection.json"; path.write_text(json.dumps(selection))
            (root / "manifest.json").write_text(json.dumps({
                "schema": "polymarket_nfl_route_dev_selection_manifest_v1",
                "selection_count": 1, "selection_receipts": [],
                "trades_opened": False, "labels_opened": False, "scored": False,
            }))
            with self.assertRaisesRegex(ValueError, "50-game"):
                load_frozen_selections(root)


if __name__ == "__main__":
    unittest.main()
