import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from build_polymarket_round1 import build
from polymarket_round1_protocol import validate_protocol
from prediction_stream import validate_rows


def ms(day):
    return int(datetime.fromisoformat(day + "T20:00:00+00:00").timestamp() * 1000)


def rows(game, day, count):
    start = ms(day)
    result = []
    for index in range(count):
        decision = start - (count - index + 120) * 60_000
        result.append({"row_id": f"{game}-{index}", "game_id": game,
            "market_id": f"market-{game}", "game_start_ms": start,
            "decision_ms": decision, "feature_available_ms": decision,
            "label_available_ms": decision + 60_000,
            "features": {"bid": .4, "ask": .42, "mid": .41, "spread": .02,
                         "bid_size": 10.0, "ask_size": 20.0, "imbalance": -1 / 3},
            "target": .43})
    return result


class Round1BuilderTests(unittest.TestCase):
    def test_freezes_six_learning_three_transfer_and_runner_rows(self):
        materialized = {"schema": "polymarket_midpoint_labels_v1",
                        "evidence_class": "historical_diagnostic",
                        "scientific_admission": False,
                        "source_bundle_sha256": "a" * 64, "rows": []}
        for index in range(3):
            materialized["rows"] += rows(f"train-{index}", f"2026-08-{29 + index:02d}", 25)
        for index in range(6):
            materialized["rows"] += rows(f"route-{index}", "2026-09-02", 20)
        for index in range(3):
            materialized["rows"] += rows(f"audit-{index}", "2026-09-04", 20)
        materialized["rows"].sort(key=lambda row: (row["decision_ms"], row["row_id"]))
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "round"
            receipt = build(materialized, out, "fixture-polymarket-round1")
            tasks = json.loads((out / "tasks.json").read_text())
            self.assertEqual([task["phase"] for task in tasks], ["learning"] * 6 + ["transfer"] * 3)
            self.assertEqual(receipt["target"], "future_midpoint_at_60_seconds")
            self.assertEqual(receipt["sampling"]["minimum_full_game_persistence_mse"], 0.0000005)
            self.assertTrue(validate_protocol(json.loads((out / "protocol.json").read_text()))["valid"])
            for task in tasks:
                train = json.loads((out / "task-data" / f"{task['task_id']}-train.json").read_text())["rows"]
                dev = json.loads((out / "task-data" / f"{task['task_id']}-dev.json").read_text())["rows"]
                evaluation = [{key: row[key] for key in
                    ("row_id", "game_id", "market_id", "decision_ms", "feature_available_ms", "features")}
                    for row in dev]
                validate_rows(train, evaluation, task["data_catalog"] and
                              ["bid", "ask", "mid", "spread", "bid_size", "ask_size", "imbalance"])


if __name__ == "__main__":
    unittest.main()
