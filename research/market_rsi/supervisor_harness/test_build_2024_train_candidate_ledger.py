import csv
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from supervisor_harness import build_2024_train_candidate_ledger as ledger_builder
from supervisor_harness.build_2024_train_candidate_ledger import (
    MAPPED_FIELDS, _assemble_verified, build, canonical_digest,
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FullDenominatorLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.paths = {name: root / name for name in (
            "capture_manifest", "schedule_source", "catalog_manifest",
            "catalog_payload", "mapping_manifest", "mapped_rows",
            "mapping_failures",
        )}
        schedule = "game_id\n" + "".join(f"2024_{index:03d}\n" for index in range(285))
        self.paths["schedule_source"].write_bytes(
            gzip.compress(schedule.encode(), mtime=0)
        )
        events = [
            {"id": str(1000 + index), "slug": f"nfl-a-b-{index:03d}"}
            for index in range(284)
        ] + [{"id": "17330", "slug": "nfl-kc-phi-2025-02-09"}]
        self.paths["catalog_payload"].write_text(json.dumps(events) + "\n")
        with self.paths["mapped_rows"].open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=MAPPED_FIELDS)
            writer.writeheader()
            for index in range(284):
                writer.writerow({
                    "polymarket_event_id": str(1000 + index),
                    "event_slug": f"nfl-a-b-{index:03d}",
                    "event_start_utc": "2024-09-01T00:00:00Z",
                    "nflverse_game_id": f"2024_{index:03d}",
                    "nflverse_game_date": "2024-09-01",
                    "away_team": "A", "home_team": "B",
                    "slug_order": "away_home", "date_resolution": "exact",
                    "moneyline_market_id": str(2000 + index),
                    "condition_id": f"condition-{index}",
                    "outcomes_json": '["A","B"]',
                    "tokens_json": '["1","2"]',
                })
        failures = [{"event_id": "17330", "reason": "moneyline_missing_or_ambiguous",
                     "slug": "nfl-kc-phi-2025-02-09"}]
        self.paths["mapping_failures"].write_text(json.dumps(failures) + "\n")
        base_hashes = {name: digest(path) for name, path in self.paths.items()
                       if path.exists()}
        catalog = {
            "schema": "polymarket_2024_nfl_train_catalog_manifest_v1",
            "events": 285, "two_outcome_moneyline_markets_on_candidates": 284,
            "catalog_sha256": base_hashes["catalog_payload"], "train_admitted": False,
        }
        self.paths["catalog_manifest"].write_text(json.dumps(catalog) + "\n")
        base_hashes["catalog_manifest"] = digest(self.paths["catalog_manifest"])
        mapping = {
            "schema": "polymarket_2024_nfl_train_candidate_mapping_manifest_v1",
            "catalog_events": 285, "nflverse_2024_games": 285,
            "mapped_unique_games": 284, "unmapped_events": 1,
            "failure_reasons": {"moneyline_missing_or_ambiguous": 1},
            "catalog_sha256": base_hashes["catalog_payload"],
            "nflverse_sha256": base_hashes["schedule_source"],
            "mapping_sha256": base_hashes["mapped_rows"],
            "failures_sha256": base_hashes["mapping_failures"],
            "train_admitted": False,
        }
        self.paths["mapping_manifest"].write_text(json.dumps(mapping) + "\n")
        base_hashes["mapping_manifest"] = digest(self.paths["mapping_manifest"])
        capture = {
            "schema": "nfl_2024_fresh_source_version_v1",
            "gamma_catalog_events": 285, "mapped_games": 284,
            "train_admitted": False, "dev_final_opened": False,
            "pbp_gzip_sha256": base_hashes["schedule_source"],
            "gamma_catalog_manifest_sha256": base_hashes["catalog_manifest"],
            "mapping_manifest_sha256": base_hashes["mapping_manifest"],
            "mapping_sha256": base_hashes["mapped_rows"],
        }
        self.paths["capture_manifest"].write_text(json.dumps(capture) + "\n")
        self.expected = {name: digest(path) for name, path in self.paths.items()}

    def tearDown(self):
        self.temporary.cleanup()

    def _refresh_all_hash_links(self):
        current = {name: digest(path) for name, path in self.paths.items()}
        catalog = json.loads(self.paths["catalog_manifest"].read_text())
        catalog["catalog_sha256"] = current["catalog_payload"]
        self.paths["catalog_manifest"].write_text(json.dumps(catalog) + "\n")
        current["catalog_manifest"] = digest(self.paths["catalog_manifest"])
        mapping = json.loads(self.paths["mapping_manifest"].read_text())
        mapping.update({
            "catalog_sha256": current["catalog_payload"],
            "nflverse_sha256": current["schedule_source"],
            "mapping_sha256": current["mapped_rows"],
            "failures_sha256": current["mapping_failures"],
        })
        self.paths["mapping_manifest"].write_text(json.dumps(mapping) + "\n")
        current["mapping_manifest"] = digest(self.paths["mapping_manifest"])
        capture = json.loads(self.paths["capture_manifest"].read_text())
        capture.update({
            "pbp_gzip_sha256": current["schedule_source"],
            "gamma_catalog_manifest_sha256": current["catalog_manifest"],
            "mapping_manifest_sha256": current["mapping_manifest"],
            "mapping_sha256": current["mapped_rows"],
        })
        self.paths["capture_manifest"].write_text(json.dumps(capture) + "\n")
        current["capture_manifest"] = digest(self.paths["capture_manifest"])
        return current

    def _canonical_fixture_tree(self):
        root = Path(self.temporary.name) / "canonical"
        root.mkdir()
        for name, relative in ledger_builder.SOURCE_FILES.items():
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.paths[name], target)
        return root, {
            name: digest(root / relative)
            for name, relative in ledger_builder.SOURCE_FILES.items()
        }

    def test_preserves_285_as_284_plus_one_explicit_missing_row(self):
        ledger = _assemble_verified(self.paths, self.expected)
        self.assertEqual(ledger["denominator"], {
            "candidate_rows": 285, "mapped_rows": 284, "missing_rows": 1,
        })
        missing = [row for row in ledger["rows"] if row["mapping_status"] == "missing"]
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]["schedule_game_id"], "2024_284")
        self.assertIsNone(missing[0]["source_event_id"])
        self.assertEqual(missing[0]["missing_reason"], "moneyline_missing_or_ambiguous")
        self.assertEqual(missing[0]["unmapped_catalog_event_evidence"], {
            "source_event_id": "17330",
            "source_event_slug": "nfl-kc-phi-2025-02-09",
            "claimed_as_mapping": False,
        })
        self.assertFalse(ledger["admission_claim"])

    def _rewrite_mapping_identity(self, replacement):
        original = self.paths["mapped_rows"].read_text()
        lines = original.splitlines()
        cells = lines[2].split(",")
        cells[3] = replacement(lines)
        lines[2] = ",".join(cells)
        self.paths["mapped_rows"].write_text("\n".join(lines) + "\n")
        changed = dict(self.expected, mapped_rows=digest(self.paths["mapped_rows"]))
        mapping = json.loads(self.paths["mapping_manifest"].read_text())
        mapping["mapping_sha256"] = changed["mapped_rows"]
        self.paths["mapping_manifest"].write_text(json.dumps(mapping) + "\n")
        changed["mapping_manifest"] = digest(self.paths["mapping_manifest"])
        capture = json.loads(self.paths["capture_manifest"].read_text())
        capture["mapping_sha256"] = changed["mapped_rows"]
        capture["mapping_manifest_sha256"] = changed["mapping_manifest"]
        self.paths["capture_manifest"].write_text(json.dumps(capture) + "\n")
        changed["capture_manifest"] = digest(self.paths["capture_manifest"])
        return changed

    def test_duplicate_mapped_id_is_rejected(self):
        changed = self._rewrite_mapping_identity(lambda lines: lines[1].split(",")[3])
        with self.assertRaisesRegex(ValueError, "duplicate mapped identity"):
            _assemble_verified(self.paths, changed)

    def test_missing_mapped_id_is_rejected(self):
        changed = self._rewrite_mapping_identity(lambda _lines: "")
        with self.assertRaisesRegex(ValueError, "blank mapped identity"):
            _assemble_verified(self.paths, changed)

    def test_denominator_drift_is_rejected(self):
        mapping = json.loads(self.paths["mapping_manifest"].read_text())
        mapping["nflverse_2024_games"] = 284
        self.paths["mapping_manifest"].write_text(json.dumps(mapping) + "\n")
        changed = dict(self.expected, mapping_manifest=digest(self.paths["mapping_manifest"]))
        capture = json.loads(self.paths["capture_manifest"].read_text())
        capture["mapping_manifest_sha256"] = changed["mapping_manifest"]
        self.paths["capture_manifest"].write_text(json.dumps(capture) + "\n")
        changed["capture_manifest"] = digest(self.paths["capture_manifest"])
        with self.assertRaisesRegex(ValueError, "mapping denominator"):
            _assemble_verified(self.paths, changed)

    def test_source_hash_mismatch_is_rejected(self):
        self.paths["catalog_payload"].write_bytes(b"mutated")
        with self.assertRaisesRegex(ValueError, "source hash mismatch"):
            _assemble_verified(self.paths, self.expected)

    def test_ledger_has_no_dev_or_final_fields(self):
        ledger = _assemble_verified(self.paths, self.expected)
        def keys(value):
            if isinstance(value, dict):
                return set(value).union(*(keys(item) for item in value.values()))
            if isinstance(value, list):
                return set().union(*(keys(item) for item in value))
            return set()
        lowered = {key.lower() for key in keys(ledger)}
        self.assertFalse(any("dev" in key or "final" in key for key in lowered))
        self.assertFalse(ledger["admission_claim"])

    def test_public_build_rejects_fully_rehashed_substitute_tree(self):
        root, _expected = self._canonical_fixture_tree()
        with self.assertRaisesRegex(ValueError, "exact canonical repository"):
            build(root)

    def test_public_build_rejects_symlink_even_with_matching_hash(self):
        root, expected = self._canonical_fixture_tree()
        target = root / ledger_builder.SOURCE_FILES["mapping_failures"]
        external = Path(self.temporary.name) / "external-failure.json"
        shutil.copyfile(target, external)
        target.unlink()
        target.symlink_to(external)
        with (mock.patch.object(ledger_builder, "CANONICAL_REPO", root),
              mock.patch.object(ledger_builder, "PINNED_SHA256", expected)):
            with self.assertRaisesRegex(ValueError, "symlink source path"):
                build(root)

    def test_fabricated_missing_event_is_rejected_after_rehash(self):
        self.paths["mapping_failures"].write_text(json.dumps([{
            "event_id": "999999", "reason": "moneyline_missing_or_ambiguous",
            "slug": "fabricated-event",
        }]) + "\n")
        changed = self._refresh_all_hash_links()
        with self.assertRaisesRegex(ValueError, "unexpected missing event evidence"):
            _assemble_verified(self.paths, changed)

    def test_extra_dev_field_is_rejected_after_rehash(self):
        with self.paths["mapped_rows"].open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        fields = MAPPED_FIELDS + ("dev_score",)
        with self.paths["mapped_rows"].open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({**row, "dev_score": "1"})
        changed = self._refresh_all_hash_links()
        with self.assertRaisesRegex(ValueError, "unexpected mapping fields"):
            _assemble_verified(self.paths, changed)

    def test_every_row_has_recomputable_source_commitment(self):
        ledger = _assemble_verified(self.paths, self.expected)
        for row in ledger["rows"]:
            commitment = row["row_commitment_sha256"]
            without_commitment = dict(row)
            del without_commitment["row_commitment_sha256"]
            self.assertEqual(commitment, canonical_digest(without_commitment))
            binding = row["source_binding"]
            self.assertEqual(
                binding["source_artifact_sha256"]["schedule_source"],
                self.expected["schedule_source"],
            )
            self.assertEqual(
                binding["source_artifact_sha256"]["catalog_payload"],
                self.expected["catalog_payload"],
            )


if __name__ == "__main__":
    unittest.main()
