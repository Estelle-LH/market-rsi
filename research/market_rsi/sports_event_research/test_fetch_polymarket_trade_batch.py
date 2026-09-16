import json
from pathlib import Path
import tempfile
import unittest

from sports_event_research.fetch_polymarket_trade_batch import run


class TradeBatchTests(unittest.TestCase):
    def test_nontrain_selection_fails_before_network_or_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); selections = root / "selections"; selections.mkdir()
            (selections / "x.selection.json").write_text(json.dumps({
                "nflverse_game_id": "x", "split_role": "route_dev"}))
            master = root / "master.csv"; master.write_text("x\n")
            output = root / "output"
            with self.assertRaisesRegex(ValueError, "non-Train"):
                run(selections, master, output)
            self.assertFalse(output.exists())

    def test_duplicate_game_fails_before_network_or_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); selections = root / "selections"; selections.mkdir()
            value = {"nflverse_game_id": "x", "split_role": "market_train"}
            (selections / "a.selection.json").write_text(json.dumps(value))
            (selections / "b.selection.json").write_text(json.dumps(value))
            master = root / "master.csv"; master.write_text("x\n")
            output = root / "output"
            with self.assertRaisesRegex(ValueError, "duplicate"):
                run(selections, master, output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
