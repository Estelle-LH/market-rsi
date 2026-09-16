import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from build_archive_formal_data import build
from formal_round_binding import freeze_binding, validate_binding
from prospective_data_lifecycle import ProspectiveDataLifecycle


def _ms(date, offset):
    return int(datetime.fromisoformat(date + "T12:00:00+00:00").timestamp() * 1000) + offset


def _row(date, game, index, delta=0.001):
    decision = _ms(date, index * 120_000)
    return {"row_id": f"{game}-{index}", "game_id": game, "market_id": game,
            "game_start_ms": _ms(date, 8 * 3_600_000), "decision_ms": decision,
            "feature_available_ms": decision,
            "features": {"bid": 0.49, "ask": 0.51, "mid": 0.5, "spread": 0.02,
                         "bid_size": 1.0, "ask_size": 1.0, "imbalance": 0.0},
            "target": 0.5 + delta, "label_available_ms": decision + 60_000}


def _source():
    rows = []
    for date in ("2026-08-27", "2026-08-28", "2026-08-29", "2026-08-30",
                 "2026-08-31", "2026-09-01", "2026-09-03", "2026-09-05"):
        rows.extend(_row(date, "train-" + date, index) for index in range(30))
    for date in ("2026-09-02", "2026-09-04", "2026-09-06"):
        for game in range(5):
            rows.extend(_row(date, f"dev-{date}-{game}", index, delta=0.01)
                        for index in range(30))
    return {"schema": "polymarket_midpoint_labels_v1",
            "evidence_class": "historical_diagnostic", "scientific_admission": False,
            "test_opened": False, "source_bundle_sha256": "a" * 64, "rows": rows}


class FormalRoundBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        source = _source()
        self.source = self.root / "source.json"
        self.source.write_text(json.dumps(source))
        self.data = self.root / "data"
        receipt = build([(self.source, source)], self.data, "experiment")
        self.lifecycle = ProspectiveDataLifecycle.create(
            self.root / "lifecycle", experiment_id="experiment",
            rounds=json.loads((self.data / "lifecycle-rounds.json").read_text()),
            transfer_policy_sha256=receipt["transfer_policy_sha256"])

    def tearDown(self):
        self.temp.cleanup()

    def test_binding_reconstructs_exact_round_and_advances(self):
        path = self.root / "round-01-binding.json"
        binding = freeze_binding(path, self.data, self.lifecycle.root, "round-01")
        self.assertEqual(validate_binding(path), binding)
        self.assertEqual(binding["train_rows"], 180)
        self.assertEqual(binding["dev_rows"], 150)
        self.assertFalse(binding["dev_labels_visible_to_controller"])
        self.lifecycle.claim_dev_score("round-01", candidate_set_sha256="a" * 64)
        self.lifecycle.complete_dev_score("round-01", score_receipt_sha256="b" * 64)
        second = freeze_binding(self.root / "round-02-binding.json", self.data,
                                self.lifecycle.root, "round-02")
        self.assertEqual(second["train_rows"], 360)
        self.assertEqual([item["dataset_id"] for item in second["train_components"]],
                         ["round-01-new-train", "round-01-dev",
                          "round-02-new-train"])

    def test_changed_source_materialization_fails_closed(self):
        path = self.root / "round-01-binding.json"
        freeze_binding(path, self.data, self.lifecycle.root, "round-01")
        self.source.write_text(self.source.read_text() + "\n")
        with self.assertRaisesRegex(ValueError, "source materialization changed"):
            validate_binding(path)

    def test_binding_cannot_be_reused_after_lifecycle_changes(self):
        path = self.root / "round-01-binding.json"
        freeze_binding(path, self.data, self.lifecycle.root, "round-01")
        self.lifecycle.claim_dev_score("round-01", candidate_set_sha256="a" * 64)
        with self.assertRaises(ValueError):
            validate_binding(path)


if __name__ == "__main__":
    unittest.main()
