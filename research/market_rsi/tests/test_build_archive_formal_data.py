import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from build_archive_formal_data import build, ROUND_SPECS
from data_lifecycle import DataLifecycle


def ms(date, offset):
    return int(datetime.fromisoformat(date + "T12:00:00+00:00").timestamp() * 1000) + offset


class ArchiveFormalDataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def source(self):
        rows = []
        train_dates = ["2026-08-27", "2026-08-28", "2026-08-29", "2026-08-30",
                       "2026-08-31", "2026-09-01", "2026-09-03", "2026-09-05"]
        for date in train_dates:
            for index in range(30):
                rows.append(self.row(date, "train-" + date, index))
        for date in ("2026-09-02", "2026-09-04", "2026-09-06"):
            for game in range(5):
                for index in range(30):
                    rows.append(self.row(date, f"dev-{date}-{game}", index, delta=0.01))
        return {"schema": "polymarket_midpoint_labels_v1",
                "evidence_class": "historical_diagnostic", "scientific_admission": False,
                "test_opened": False, "source_bundle_sha256": "a" * 64, "rows": rows}

    @staticmethod
    def row(date, game, index, delta=0.001):
        decision = ms(date, index * 120_000)
        return {"row_id": f"{game}-{index}", "game_id": game, "market_id": game,
                "game_start_ms": ms(date, 8 * 3_600_000), "decision_ms": decision,
                "feature_available_ms": decision,
                "features": {"bid": 0.49, "ask": 0.51, "mid": 0.5, "spread": 0.02,
                             "bid_size": 1.0, "ask_size": 1.0, "imbalance": 0.0},
                "target": 0.5 + delta, "label_available_ms": decision + 60_000}

    def test_builds_three_cumulative_rounds_and_keeps_transfer_prospective(self):
        source_path = self.root / "source.json"
        source_path.write_text(json.dumps(self.source()))
        result = build([(source_path, self.source())], self.root / "out", "experiment")
        self.assertEqual(len(result["rounds"]), len(ROUND_SPECS))
        self.assertFalse(result["transfer_materialized"])
        self.assertFalse(result["formal_lineage_ready"])
        inputs = json.loads((self.root / "out/round-inputs.json").read_text())
        self.assertEqual([item["train"]["rows"] for item in inputs], [180, 360, 540])
        self.assertEqual([item["dev"]["games"] for item in inputs], [5, 5, 5])
        self.assertEqual(inputs[1]["train_dataset_ids"],
                         ["round-01-new-train", "round-01-dev", "round-02-new-train"])
        self.assertEqual(inputs[2]["train_dataset_ids"],
                         ["round-01-new-train", "round-01-dev", "round-02-new-train",
                          "round-02-dev", "round-03-new-train"])
        lifecycle = DataLifecycle.create(self.root / "lifecycle", experiment_id="experiment",
            rounds=json.loads((self.root / "out/lifecycle-rounds.json").read_text()),
            transfer_datasets=[{"dataset_id": "fixture-transfer",
                                "content_sha256": "f" * 64}])
        for item in inputs:
            view = lifecycle.controller_view(item["round_id"])
            self.assertEqual([entry["dataset_id"] for entry in view["train_full_access"]],
                             item["train_dataset_ids"])
            self.assertEqual([entry["dataset_id"] for entry in view["dev_feature_only"]],
                             item["dev_dataset_ids"])
            lifecycle.claim_dev_score(item["round_id"], candidate_set_sha256="c" * 64)
            lifecycle.complete_dev_score(item["round_id"], score_receipt_sha256="d" * 64)

    def test_easy_dev_stays_in_the_target_blind_population(self):
        value = self.source()
        for row in value["rows"]:
            if row["game_id"].startswith("dev-2026-09-04"):
                row["target"] = row["features"]["mid"]
        path = self.root / "source.json"
        path.write_text(json.dumps(value))
        receipt = build([(path, value)], self.root / "out", "experiment")
        self.assertTrue(receipt["sampling"]["dev_membership_target_blind"])
        self.assertTrue(receipt["sampling"]["persistence_mse_computed_after_membership"])
        second = receipt["rounds"][1]
        self.assertEqual(len(second["dev_games"]), 5)
        self.assertTrue(all(item["persistence_mse"] == 0
                            for item in second["dev_games"]))

    def test_dev_membership_uses_actual_decision_date_not_game_start_date(self):
        value = self.source()
        # This game is nominally scheduled for Sep 2 but all of its prediction
        # rows occur on Sep 1.  It must not enter the Sep 2 Dev block.
        for index in range(30):
            row = self.row("2026-09-02", "cross-boundary", index, delta=0.01)
            row["decision_ms"] -= 24 * 3_600_000
            row["feature_available_ms"] = row["decision_ms"]
            row["label_available_ms"] = row["decision_ms"] + 60_000
            value["rows"].append(row)
        path = self.root / "source.json"
        path.write_text(json.dumps(value))
        build([(path, value)], self.root / "out", "experiment")
        dev = json.loads(
            (self.root / "out/blocks/round-01-sealed-dev.json").read_text()
        )["rows"]
        self.assertNotIn("cross-boundary", {row["game_id"] for row in dev})

    def test_binds_one_objective_across_every_source(self):
        first = self.source()
        first["objective_id"] = "future-midpoint-point-60s-v1"
        first["objective_contract_sha256"] = "b" * 64
        path = self.root / "source.json"
        path.write_text(json.dumps(first))
        receipt = build([(path, first)], self.root / "out", "experiment")
        self.assertEqual(receipt["objective_id"], first["objective_id"])
        self.assertEqual(receipt["objective_contract_sha256"], "b" * 64)


if __name__ == "__main__":
    unittest.main()
