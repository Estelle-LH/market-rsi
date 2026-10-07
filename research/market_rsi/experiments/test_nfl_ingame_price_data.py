import csv
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from experiments.nfl_ingame_price_data import (
    FEATURE_NAMES, SOURCE_ROOT, anchor_row, chronological_folds, fit_weights, materialize,
)

GAME = {"game_id": "2025_01_A_B", "game_date": "2025-09-04", "event_slug": "event"}


def fixture(root, trades):
    (root / "catalog").mkdir()
    (root / "trades" / GAME["game_id"]).mkdir(parents=True)
    (root / "audit").mkdir()
    raw = json.dumps({"markets": [{"id": "m", "conditionId": "c", "clobTokenIds": '["b","a"]',
                                  "outcomePrices": '["1","0"]', "bestBid": 1}]}).encode()
    packed = gzip.compress(raw)
    (root / "catalog" / f"{GAME['game_id']}.raw.json.gz").write_bytes(packed)
    digest = lambda value: hashlib.sha256(value).hexdigest()
    catalog = {**GAME, "market_id": "m", "condition_id": "c", "tokens": ["a", "b"],
               "event_start_utc": "2025-09-04T00:00:00+00:00", "stored_sha256": digest(packed),
               "raw_sha256": digest(raw)}
    (root / "catalog" / f"{GAME['game_id']}.json").write_text(json.dumps(catalog))
    trade_file = root / "trades" / GAME["game_id"] / "trade_window.csv"
    header = ["side", "token_id", "condition_id", "size", "price", "timestamp", "event_slug",
              "outcome", "outcome_index", "transaction_hash"]
    with trade_file.open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=header)
        writer.writeheader()
        for trade in trades:
            writer.writerow(trade)
    receipt = {"game_id": GAME["game_id"], "condition_id": "c", "tokens": ["a", "b"],
               "trade_window_sha256": digest(trade_file.read_bytes()), "complete": True,
               "window_start": 0, "window_end": 9999999999, "window_trade_rows": len(trades)}
    (trade_file.parent / "manifest.json").write_text(json.dumps(receipt))
    (root / "audit/per_game.json").write_text("[]")
    (root / "manifest.json").write_text(json.dumps({"complete": True, "dev_final_opened": False,
                                "per_game_sha256": digest((root / "audit/per_game.json").read_bytes())}))
    with (root / "cohort.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(GAME))
        writer.writeheader()
        writer.writerow(GAME)


def trade(timestamp, price=.4, token="b", side="BUY", index="0", identity="x"):
    return {"side": side, "token_id": token, "condition_id": "c", "size": "2", "price": str(price),
            "timestamp": str(timestamp), "event_slug": "event", "outcome": "name",
            "outcome_index": index, "transaction_hash": identity}


class PriceMaterializerTests(unittest.TestCase):
    def test_strict_boundaries_ties_vwap_and_past_information(self):
        tape = [(699, .1, 2, 1), (700, .4, 1, 1), (970, .2, 1, -1),
                (970, .6, 3, 1), (999, .5, 4, 1), (1000, .99, 500, -1),
                (1269, .1, 100, 1), (1270, .8, 2, 1), (1299, .6, 2, -1), (1300, 1, 100, 1)]
        row = anchor_row(GAME, 400, tape, 1000)
        self.assertAlmostEqual(row["p_current"], .5)
        self.assertAlmostEqual(row["label"], .2)
        self.assertEqual(len(row["features"]), len(FEATURE_NAMES))
        self.assertTrue(all(-900 <= item[0] < 0 for item in row["history"]))
        changed = anchor_row(GAME, 400, tape[:5] + [(1000, 0, 9999, 1), (1299, 0, 1, 1)], 1000)
        self.assertEqual(row["features"], changed["features"])
        self.assertEqual(row["history"], changed["history"])

    def test_missing_future_preserves_forecast_not_zero_label(self):
        row = anchor_row(GAME, 400, [(999, .3, 1, 1)], 1000)
        self.assertTrue(row["forecastable"])
        self.assertIsNone(row["label"])
        self.assertEqual(row["reason"], "NO_FUTURE_WINDOW_LABEL")

    def test_missing_current_is_not_forward_filled(self):
        row = anchor_row(GAME, 400, [(969, .3, 1, 1), (1299, .8, 1, 1)], 1000)
        self.assertFalse(row["forecastable"])
        self.assertIsNone(row["p_current"])
        self.assertIsNone(row["label"])
        self.assertEqual(row["reason"], "NO_CURRENT_WINDOW_TRADE")

    def test_price_zero_and_one_remain_eligible(self):
        row = anchor_row(GAME, 400, [(999, 0, 1, 1), (1299, 1, 1, 1)], 1000)
        self.assertEqual(row["label"], 1)

    def test_actual_materialization_orientation_population_and_source_hash(self):
        start = int(datetime(2025, 9, 4, tzinfo=timezone.utc).timestamp())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture(root, [trade(start + 599, .4), trade(start + 899, .7, identity="y"),
                           trade(start + 599, .9, token="a", index="1", identity="z")])
            rows, metadata = materialize(root, allow_test_paths=True)
            self.assertEqual(len(rows), 23)
            self.assertEqual(metadata["population"], 1)
            self.assertEqual(metadata["source_receipts"][GAME["game_id"]]["token0"], "b")
            self.assertAlmostEqual(rows[0]["p_current"], .4)
            self.assertAlmostEqual(rows[0]["label"], .3)
            with self.assertRaises(ValueError):
                materialize(root)
            with (root / "trades" / GAME["game_id"] / "trade_window.csv").open("a") as stream:
                stream.write("corrupt")
            with self.assertRaisesRegex(ValueError, "hash failure"):
                materialize(root, allow_test_paths=True)

    def test_invalid_duplicate_side_and_orientation_fail_not_filter(self):
        for tape in ([trade(1), trade(1)], [trade(1, side="UNKNOWN")], [trade(1, index="1")]):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                fixture(root, tape)
                with self.assertRaises(ValueError):
                    materialize(root, allow_test_paths=True)

    def test_equal_game_fit_weights_normalized_to_mean_one(self):
        rows = [{"game_id": "a"}] * 3 + [{"game_id": "b"}]
        weights = fit_weights(rows)
        self.assertEqual(sum(weights), 4)
        self.assertAlmostEqual(sum(weights[:3]), weights[3])

    def test_date_folds_forecastable_checks_and_label_maturation(self):
        rows = []
        for day in range(42):
            date = (datetime(2025, 9, 4) + timedelta(days=day)).date().isoformat()
            rows.append({"row_id": str(day), "game_id": str(day), "game_date": date,
                         "anchor_s": day * 1000, "forecastable": True, "label": None if day == 23 else 0})
        # Earlier date but a late anchor with unmatured label must not reach first fit.
        rows[21]["anchor_s"] = 21800
        folds = chronological_folds(rows)
        self.assertEqual(len(folds), 4)
        self.assertEqual(len(folds[0][0]), 21)
        self.assertEqual(len(folds[0][1]), 5)
        self.assertIn(rows[23], folds[0][1])
        self.assertNotIn(rows[23], folds[1][0])
        for fit, check in folds:
            self.assertLess(max(r["game_date"] for r in fit), min(r["game_date"] for r in check))
            self.assertTrue(all(r["anchor_s"] + 300 < min(c["anchor_s"] for c in check) for r in fit))

    def test_production_root_constant_and_fixture_escape(self):
        self.assertIn("nfl-2025-train-refresh-20260922-01", str(SOURCE_ROOT))
        with self.assertRaises(ValueError):
            materialize("/Users/estelle/Downloads", allow_test_paths=True)


if __name__ == "__main__":
    unittest.main()
