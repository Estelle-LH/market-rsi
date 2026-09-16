import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import split_manifest as splits


def fixture_index():
    source = "a" * 64
    rows = []
    for i in range(6):
        t = (i + 1) * splits.DAY_MS + 10000
        rows.append({"row_id": f"r{i}", "game_id": f"g{i}", "market_id": f"m{i}",
            "decision_ms": t, "feature_available_ms": t - 10,
            "label_end_ms": t + 1005, "label_available_ms": t + 1015,
            "input_source": {"sha256": source, "ordinal": i * 2},
            "label_source": {"sha256": source, "ordinal": i * 2 + 1}})
    return {"schema": "market_split_index_v1", "evidence_class": "fixture",
        "source_sha256": [source], "market_games": {f"m{i}": f"g{i}" for i in range(6)},
        "horizon_ms": 1000, "latency_ms": 5, "max_label_lateness_ms": 100,
        "rows": rows, "tasks": [
            {"task_id": "learning-01", "phase": "learning",
             "splits": {"train": ["g0"], "dev": ["g1"], "test": ["g2"]}},
            {"task_id": "transfer-01", "phase": "transfer",
             "splits": {"train": ["g3"], "dev": ["g4"], "test": ["g5"]}}]}


class SplitManifestTests(unittest.TestCase):
    def setUp(self):
        self.index = fixture_index()

    def reject(self, match):
        with self.assertRaisesRegex(ValueError, match):
            splits.validate_index(self.index)

    def test_valid_whole_game_chronology(self):
        before = copy.deepcopy(self.index)
        result = splits.validate_index(self.index)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["summaries"]["dev"]["games"], 1)
        self.assertEqual(self.index, before)

    def test_same_game_cannot_appear_in_two_splits(self):
        self.index["tasks"][0]["splits"]["dev"].append("g0")
        self.reject("game reused")

    def test_test_game_cannot_become_later_training(self):
        self.index["tasks"][1]["splits"]["train"].append("g2")
        self.reject("game reused")

    def test_market_cannot_be_relabelled_to_hide_overlap(self):
        self.index["rows"][0]["game_id"] = "g1"
        self.reject("market relabeled")

    def test_duplicate_row_ids(self):
        self.index["rows"][1]["row_id"] = "r0"
        self.reject("duplicate row ID")

    def test_duplicate_observation_under_another_row_id(self):
        self.index["rows"].append({**self.index["rows"][0], "row_id": "another-id"})
        self.reject("duplicate indexed observation")

    def test_features_cannot_arrive_later(self):
        self.index["rows"][0]["feature_available_ms"] += 11
        self.reject("feature arrives")

    def test_exact_horizon_and_lateness_enforced(self):
        original = fixture_index()
        for delta in (-1, 101):
            self.index = copy.deepcopy(original)
            self.index["rows"][0]["label_end_ms"] += delta
            self.reject("horizon/lateness")

    def test_label_cannot_be_known_before_observation(self):
        self.index["rows"][0]["label_available_ms"] -= 11
        self.reject("label unavailable")

    def test_label_receipt_crossing_boundary_is_rejected(self):
        self.index["rows"][0]["label_available_ms"] = self.index["rows"][1]["decision_ms"]
        self.reject("availability crosses")

    def test_same_date_split_is_rejected_even_without_timestamp_overlap(self):
        row = self.index["rows"][1]
        for key in ("decision_ms", "feature_available_ms", "label_end_ms", "label_available_ms"):
            row[key] -= splits.DAY_MS - 5000
        self.reject("earlier UTC dates")

    def test_cross_midnight_game_is_kept_whole(self):
        row = copy.deepcopy(self.index["rows"][0])
        row.update(row_id="r0-late", decision_ms=2 * splits.DAY_MS + 15000,
                   feature_available_ms=2 * splits.DAY_MS + 14999,
                   label_end_ms=2 * splits.DAY_MS + 16005,
                   label_available_ms=2 * splits.DAY_MS + 16015)
        row["input_source"]["ordinal"] = 50
        row["label_source"]["ordinal"] = 51
        self.index["rows"].append(row)
        self.reject("availability crosses")

    def test_unknown_source_rejected(self):
        self.index["rows"][0]["input_source"]["sha256"] = "b" * 64
        self.reject("source not in frozen")

    def test_future_label_cannot_reuse_input_observation(self):
        self.index["rows"][0]["label_source"] = self.index["rows"][0]["input_source"].copy()
        self.reject("same observation")

    def test_booleans_are_not_timestamps(self):
        self.index["rows"][0]["decision_ms"] = True
        self.reject("integer milliseconds")

    def test_extra_label_or_free_text_fields_cannot_enter_index(self):
        for extra in ("label", "features", "test_results", "human_hint"):
            self.index = fixture_index()
            self.index["rows"][0][extra] = "must not be copied to model"
            self.reject("metadata fields")

    def test_unassigned_games_cannot_be_silently_dropped(self):
        self.index["tasks"] = self.index["tasks"][:1]
        self.reject("unassigned games")

    def test_reversed_research_task_order_rejected(self):
        self.index["tasks"].reverse()
        self.reject("learning task follows transfer")

    def test_live_scoring_claim_is_not_supported_by_structural_check(self):
        self.index["evidence_class"] = "verified"
        self.reject("live-source gate is not implemented")

    def test_future_task_cannot_share_previous_test_day(self):
        for row in self.index["rows"][3:]:
            for key in ("decision_ms", "feature_available_ms", "label_end_ms", "label_available_ms"):
                row[key] -= splits.DAY_MS - 5000
        self.reject("research tasks share a UTC date")

    def test_public_projection_hides_all_test_rows_and_nonces(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "index.json"
            source.write_text(json.dumps(self.index))
            output = root / "split-check"
            receipt = splits.freeze_diagnostic_index(source, output)
            public = json.loads((output / "public-train-dev.json").read_text())
            private = json.loads((output / "runner-only.json").read_text())
            self.assertFalse(receipt["scoring_ready"])
            self.assertFalse(receipt["research_result"])
            self.assertTrue(receipt["structural_checks_pass"])
            serialized = json.dumps(public)
            for hidden in ('"g2"', '"g5"', '"r2"', '"r5"', '"m2"', '"m5"'):
                self.assertNotIn(hidden, serialized)
            for nonce in private["test_commitment_nonces"].values():
                self.assertNotIn(nonce, serialized)
            for task in public["tasks"]:
                self.assertEqual(set(task), {"task_id", "phase", "train_rows", "dev_rows",
                                           "train_summary", "dev_summary", "test_commitment"})
            self.assertEqual(receipt["public_sha256"], splits.file_hash(output / "public-train-dev.json"))
            before = (output / "claim.json").read_bytes()
            with self.assertRaises(FileExistsError):
                splits.freeze_diagnostic_index(source, output)
            self.assertEqual((output / "claim.json").read_bytes(), before)

    def test_changed_input_cannot_finish_freeze(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "index.json"
            source.write_text(json.dumps(self.index))
            output = root / "split-check"
            real_hash = splits.file_hash
            calls = 0

            def changed(path):
                nonlocal calls
                if Path(path) == source:
                    calls += 1
                    if calls > 2:
                        return "b" * 64
                return real_hash(path)

            with patch.object(splits, "file_hash", side_effect=changed):
                with self.assertRaisesRegex(ValueError, "changed while freezing"):
                    splits.freeze_diagnostic_index(source, output)
            self.assertTrue((output / "claim.json").exists())
            self.assertFalse((output / "complete.json").exists())


if __name__ == "__main__":
    unittest.main()
