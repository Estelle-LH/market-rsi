from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from market_rsi import digest
from objective_contract import freeze_objective_contract
from prospective_time_series_materializer import (build, freeze_schedule,
                                                   validate_output)


def ms(date: str, offset: int = 0) -> int:
    return int(datetime.fromisoformat(date + "T10:00:00+00:00").timestamp() * 1000) + offset


def game_rows(date: str, game_id: str, *, count: int = 20,
              target_delta: float = 0.01) -> list[dict]:
    rows = []
    for index in range(count):
        decision = ms(date, index * 120_000)
        rows.append({
            "row_id": f"{game_id}-{index}",
            "game_id": game_id,
            "market_id": game_id + "-market",
            "game_start_ms": ms(date, 8 * 3_600_000),
            "decision_ms": decision,
            "feature_available_ms": decision,
            "features": {
                "bid": 0.49, "ask": 0.51, "mid": 0.5, "spread": 0.02,
                "bid_size": 2.0, "ask_size": 1.0, "imbalance": 1 / 3,
            },
            "target": 0.5 + target_delta,
            "label_available_ms": decision + 60_000,
        })
    return rows


class ProspectiveTimeSeriesMaterializerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.train_dates = [f"2026-09-{day:02d}" for day in range(1, 8)]
        self.dev_dates = [f"2026-09-{day:02d}" for day in range(8, 11)]
        self.reserved = "reserved-game"
        self.objective_path = self.root / "objective.json"
        freeze_objective_contract(
            self.objective_path,
            experiment_id="fresh-h0",
            objective_id="future-midpoint-point-60s-v1",
            train_diagnostics_sha256="a" * 64,
            literature_snapshot_sha256="b" * 64,
            literature_ids=["zhang-zohren-roberts-deeplob-2018"],
            evidence_class="formal_learning",
        )
        self.schedule_path = self.root / "schedule.json"
        freeze_schedule(
            self.schedule_path,
            experiment_id="fresh-h0",
            objective_contract_path=self.objective_path,
            train_utc_dates=self.train_dates,
            dev_utc_dates=self.dev_dates,
            reserved_game_ids=[self.reserved],
            reservation_commitment_sha256=digest({"reserved": [self.reserved]}),
            evidence_class="formal_learning",
        )

    def tearDown(self):
        self.temp.cleanup()

    def source(self, *, target_delta: float = 0.01) -> dict:
        rows = []
        for index, date in enumerate(self.train_dates):
            rows.extend(game_rows(date, f"train-{index}", target_delta=target_delta))
        # Eight games across the three future dates meets the formal outer gate.
        for index in range(8):
            rows.extend(game_rows(
                self.dev_dates[index % 3], f"dev-{index}", target_delta=target_delta
            ))
        rows.extend(game_rows(self.dev_dates[0], self.reserved,
                              target_delta=target_delta))
        rows.extend(game_rows(self.dev_dates[0], "too-short", count=19,
                              target_delta=target_delta))
        rows.sort(key=lambda row: (row["decision_ms"], row["row_id"]))
        return {
            "schema": "polymarket_midpoint_labels_v1",
            "evidence_class": "historical_diagnostic",
            "scientific_admission": False,
            "test_opened": False,
            "source_bundle_sha256": "a" * 64,
            "rows": rows,
        }

    def write_source(self, value: dict, name: str = "source.json") -> Path:
        path = self.root / name
        path.write_text(json.dumps(value, sort_keys=True))
        return path

    def test_target_values_cannot_change_membership(self):
        first = self.source(target_delta=0.01)
        second = self.source(target_delta=-0.2)
        first_path = self.write_source(first, "first.json")
        second_path = self.write_source(second, "second.json")
        build(self.schedule_path, [(first_path, first)], self.root / "first-out")
        build(self.schedule_path, [(second_path, second)], self.root / "second-out")
        first_receipt = json.loads(
            (self.root / "first-out/selection-receipt.json").read_text())
        second_receipt = json.loads(
            (self.root / "second-out/selection-receipt.json").read_text())
        self.assertEqual(first_receipt["target_blind_source_manifest_sha256"],
                         second_receipt["target_blind_source_manifest_sha256"])
        self.assertEqual(first_receipt["train_membership_sha256"],
                         second_receipt["train_membership_sha256"])
        self.assertEqual(first_receipt["dev_membership_sha256"],
                         second_receipt["dev_membership_sha256"])
        self.assertEqual(first_receipt["target_fields_used"], [])

    def test_build_is_chronological_group_disjoint_and_excludes_reservations(self):
        value = self.source()
        path = self.write_source(value)
        receipt = build(self.schedule_path, [(path, value)], self.root / "out")
        checked = validate_output(self.root / "out")
        self.assertEqual(receipt, checked)
        selection = json.loads((self.root / "out/selection-receipt.json").read_text())
        self.assertNotIn(self.reserved, selection["dev_game_ids"])
        self.assertEqual(selection["omitted"]["reserved_games"], 1)
        self.assertEqual(selection["omitted"]["short_dev_games"], 1)
        self.assertEqual(len(selection["dev_game_ids"]), 8)
        self.assertEqual(selection["train_cv_audit"]["cv_utc_dates"],
                         [int(ms(date) // 86_400_000) for date in self.train_dates[-3:]])
        self.assertFalse(selection["outer_dev_audit"]["boundary_selected_using_targets"])

    def test_source_mutation_invalidates_frozen_output(self):
        value = self.source()
        path = self.write_source(value)
        build(self.schedule_path, [(path, value)], self.root / "out")
        changed = copy.deepcopy(value)
        changed["rows"][0]["target"] = 0.123
        path.write_text(json.dumps(changed, sort_keys=True))
        with self.assertRaisesRegex(ValueError, "source materialization changed"):
            validate_output(self.root / "out")

    def test_schedule_rejects_single_day_dev(self):
        with self.assertRaisesRegex(ValueError, "at least 3"):
            freeze_schedule(
                self.root / "bad.json", experiment_id="fresh-h0",
                objective_contract_path=self.objective_path,
                train_utc_dates=self.train_dates,
                dev_utc_dates=[self.dev_dates[0]], reserved_game_ids=[],
                reservation_commitment_sha256="b" * 64,
                evidence_class="formal_learning",
            )


if __name__ == "__main__":
    unittest.main()
