"""Synthetic artifact-only tests: no Train, estimator, model call or fit."""
from __future__ import annotations

import copy
import csv
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from experiments import nfl_ingame_prediction_reference as reference


def _write(path, value):
    path.write_text(json.dumps(value, sort_keys=True, allow_nan=False), encoding="utf-8")


def _binding(path):
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def synthetic_fixture(root, candidate="SyntheticValidNegativeOffset-v1", decision="REVERT"):
    artifacts = root / "artifacts"
    artifacts.mkdir()
    runner = root / "original_source.py"
    runner.write_text("# synthetic frozen source; must never be executed\n", encoding="utf-8")
    days = [(date(2025, 1, 1) + timedelta(days=i)).isoformat() for i in range(42)]
    folds = [{"fold": i + 1, "fit_dates": days[:22 + i * 5],
              "check_dates": days[22 + i * 5:27 + i * 5]} for i in range(4)]
    controls, rows, frozen_rows = {}, [], []
    for fold, count in enumerate((26, 16, 28, 17), start=1):
        for ordinal in range(count):
            number = len(rows)
            key = (f"synthetic-event-{number}", f"synthetic-market-{number}", 1000 + number)
            row = {"fold": str(fold), "game_id": f"synthetic-game-{number}",
                "game_date": folds[fold - 1]["check_dates"][ordinal % 5], "game_week": str(fold),
                "event_id": key[0], "market_id": key[1], "cutoff_ms": str(key[2]),
                "outcome_available_ms": str(key[2] + 9000), "outcome": str(number % 2),
                "raw_market_probability": ".5", "frozen_v0_ordinary_market_only_probability": ".51",
                "frozen_v0_market_plus_state_parent_probability": ".49", "candidate_probability": ".52"}
            controls[key] = {name: int(row[name]) if name in {"fold", "outcome"} else row[name]
                for name in ("fold", "game_id", "game_date", "game_week", "outcome")}
            controls[key].update({arm: float(row[column]) for column, arm in reference.BASELINES.items()})
            rows.append(row)
            frozen_rows.append({**row, "market_model_probability": ".51", "market_plus_state_probability": ".49"})
    exclusions = {"source_events": 195, "materialized_events": 193, "excluded_events": 2,
        "exclusions": [{"game_id": "synthetic-excluded-1", "reason": "unresolved_outcome"},
                       {"game_id": "synthetic-excluded-2", "reason": "market_trade_too_stale"}]}
    frozen = {"manifest": {"task_id": "InGameWinProbabilityTrainDiagnostic-v0", **{k: exclusions[k]
              for k in ("source_events", "materialized_events", "excluded_events")}},
        "hashes": {"synthetic-v0-manifest.json": "1" * 64}, "folds": folds,
        "exclusion_codes": {row["game_id"]: row["reason"] for row in exclusions["exclusions"]},
        "lock": {"folds": folds, "orientation": "home_token_home_win", "max_staleness": 300,
                 "fixed_sampling": "synthetic_preplay_checkpoint"}, "predictions": frozen_rows,
        "receipts": {"pbp_receipts": [{"synthetic": True}], "materialized_receipts": [{"synthetic": True}]}}
    inputs = {"task_id": candidate, "runner_sha256": _binding(runner)["sha256"],
        "v0_artifact_hashes": frozen["hashes"], **frozen["receipts"], **reference.FLAGS}
    lock = {"task_id": candidate, "folds": folds, **reference.FLAGS}
    for name, value in (("input_receipts.json", inputs), ("pre_score_lock.json", lock),
                        ("exclusions.json", exclusions), ("scorecard.json", {"task_id": candidate, "decision": decision})):
        _write(artifacts / name, value)
    with (artifacts / "predictions.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    hashes = {name: _binding(artifacts / name)["sha256"] for name in reference.ARTIFACTS - {"manifest.json"}}
    _write(artifacts / "manifest.json", {"task_id": candidate, "complete": True, "model_fits": 4,
        "check_events": 87, **{name.rsplit(".", 1)[0] + "_sha256": value for name, value in hashes.items()}})
    hashes["manifest.json"] = _binding(artifacts / "manifest.json")["sha256"]
    spec = {"schema": reference.SCHEMA, "candidate_id": candidate, "runner": _binding(runner),
        "source_commit": "a" * 40, "artifact_root": str(artifacts), "artifact_hashes": hashes, "kernel_sha256": "b" * 64}
    # Production-shaped originals; their semantic acceptance is independently
    # projected by a trusted Supervisor, never inferred from passed=True here.
    proofs = {"source": {"schema": "reviewed_candidate_request_v1", "passed": True,
        "files": {"experiments/synthetic.py": spec["runner"]["sha256"]}, "source_commit": spec["source_commit"]},
        "result": {"schema": "market_rsi_independent_candidate_result_review_v1", "passed": True,
            "candidate_id": candidate, "predictions_sha256": hashes["predictions.csv"], "operational_decision": decision},
        "learning": {"schema": "market_rsi_independent_learning_checkpoint_review_v1", "passed": True,
            "normalized_checkpoint": {"validity": {"status": "valid", "leakage_detected": False}, "prediction_decision": decision}}}
    bindings = {}
    for name, value in proofs.items():
        path = root / f"original_{name}_review.json"
        _write(path, value)
        bindings[name] = _binding(path)
    accepted = {"schema": reference.ACCEPTANCE_SCHEMA, "reference_sha256": reference.digest(spec),
        "performance_status": "valid_no_leakage", "prediction_decision": decision,
        "provenance": reference.provenance(spec, frozen), "exclusions": exclusions, "reviews": bindings}
    accepted_path = root / "independently_reviewed_acceptance.json"
    _write(accepted_path, accepted)
    return spec, controls, frozen, _binding(accepted_path), rows, accepted


class PredictionReferenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name).resolve()
        self.spec, self.controls, self.frozen, self.acceptance, self.rows, self.accepted = synthetic_fixture(self.root)

    def tearDown(self):
        self.directory.cleanup()

    def load(self):
        return reference.load_reference(self.spec, self.controls, self.frozen, self.acceptance)

    def accept(self):
        self.accepted["reference_sha256"] = reference.digest(self.spec)
        _write(Path(self.acceptance["path"]), self.accepted)
        self.acceptance = _binding(Path(self.acceptance["path"]))

    def rebind(self, name):
        artifacts = Path(self.spec["artifact_root"])
        self.spec["artifact_hashes"][name] = _binding(artifacts / name)["sha256"]
        if name != "manifest.json":
            path = artifacts / "manifest.json"
            manifest = json.loads(path.read_text())
            manifest[name.rsplit(".", 1)[0] + "_sha256"] = self.spec["artifact_hashes"][name]
            _write(path, manifest)
            self.spec["artifact_hashes"]["manifest.json"] = _binding(path)["sha256"]
        self.accept()

    def write_rows(self):
        path = Path(self.spec["artifact_root"]) / "predictions.csv"
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(self.rows[0]))
            writer.writeheader()
            writer.writerows(self.rows)
        self.rebind("predictions.csv")

    def test_valid_negative_comparison_restart_and_no_fits_or_state_inheritance(self):
        before = {str(path): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        result, receipt = self.load()
        self.assertEqual(len(result), 87)
        self.assertEqual(set(result.values()), {.52})
        self.assertEqual(self.load(), (result, receipt))
        self.assertEqual(receipt["parent_refits"], 0)
        self.assertFalse(receipt["parameter_inheritance"])
        self.assertFalse(receipt["predictor_states_loaded"])
        self.assertTrue(receipt["comparison_only"])
        self.assertEqual(before, {str(path): path.read_bytes() for path in self.root.rglob("*") if path.is_file()})

    def test_archived_nonlinear_parent_and_keep_are_model_agnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            spec, controls, frozen, acceptance, _, _ = synthetic_fixture(Path(directory).resolve(), "InGameMarketStateConfidenceLinkHGB-v2", "KEEP")
            result, receipt = reference.load_reference(spec, controls, frozen, acceptance)
            self.assertEqual(len(result), 87)
            self.assertEqual(receipt["candidate_id"], "InGameMarketStateConfidenceLinkHGB-v2")

    def test_self_asserted_boolean_acceptance_is_not_supported(self):
        with self.assertRaises(ValueError):
            reference.load_reference(self.spec, self.controls, self.frozen, {"accepted": True})

    def test_separate_acceptance_pin_and_original_review_bytes_must_match(self):
        for target in [Path(self.acceptance["path"]), *(Path(p["path"]) for p in self.accepted["reviews"].values())]:
            body = target.read_bytes()
            target.write_bytes(body + b" ")
            with self.assertRaises(ValueError):
                self.load()
            target.write_bytes(body)

    def test_failed_invalid_leaking_acceptance_denied(self):
        for status in ("failed", "invalid", "valid_with_leakage", True):
            self.accepted["performance_status"] = status
            self.accept()
            with self.assertRaises(ValueError):
                self.load()

    def test_source_artifact_and_reference_digest_drift_denied(self):
        Path(self.spec["runner"]["path"]).write_text("# mutated\n")
        with self.assertRaises(ValueError):
            self.load()
        self.spec["candidate_id"] = "different"
        with self.assertRaises(ValueError):
            reference.validate_header(self.spec, self.accepted)

    def test_required_artifact_missing_denied(self):
        del self.spec["artifact_hashes"]["scorecard.json"]
        self.accept()
        with self.assertRaises(ValueError):
            self.load()

    def test_task_completion_fit_and_manifest_binding_drift_denied(self):
        path = Path(self.spec["artifact_root"]) / "manifest.json"
        original = json.loads(path.read_text())
        for field, value in (("task_id", "different"), ("complete", False), ("model_fits", 3), ("check_events", 86), ("predictions_sha256", "c" * 64)):
            _write(path, {**original, field: value})
            self.rebind("manifest.json")
            with self.assertRaises(ValueError):
                self.load()

    def test_protocol_kernel_fold_time_and_orientation_drift_denied(self):
        for change in (lambda f: f["hashes"].update({"synthetic-v0-manifest.json": "c" * 64}),
                       lambda f: f["folds"][0]["fit_dates"].pop(),
                       lambda f: f["lock"].update(orientation="away_token"),
                       lambda f: f["receipts"]["materialized_receipts"].append({"changed": True})):
            original = copy.deepcopy(self.frozen)
            change(self.frozen)
            with self.assertRaises(ValueError):
                self.load()
            self.frozen = original
        self.spec["kernel_sha256"] = "c" * 64
        self.accept()
        with self.assertRaises(ValueError):
            self.load()

    def test_duplicate_missing_reordered_rows_denied(self):
        original = copy.deepcopy(self.rows)
        for rows in (original + [original[0]], original[1:], list(reversed(original))):
            self.rows = rows
            self.write_rows()
            with self.assertRaises(ValueError):
                self.load()

    def test_row_key_fold_labels_game_identity_baselines_and_availability_denied(self):
        original = copy.deepcopy(self.rows)
        for field, value in (("event_id", "unknown"), ("fold", "4"), ("outcome", "1"), ("game_id", "other"),
                             ("game_date", "2025-01-01"), ("game_week", "99"), ("cutoff_ms", "999999"),
                             ("outcome_available_ms", "999999"), ("raw_market_probability", ".6"),
                             ("frozen_v0_ordinary_market_only_probability", ".61"),
                             ("frozen_v0_market_plus_state_parent_probability", ".59")):
            self.rows = copy.deepcopy(original)
            self.rows[0][field] = value
            self.write_rows()
            with self.assertRaises(ValueError):
                self.load()

    def test_nonfinite_and_endpoint_predictions_denied_without_clipping(self):
        for value in ("nan", "inf", "0", "1", "-0.1", "0.0000001"):
            self.rows[0]["candidate_probability"] = value
            self.write_rows()
            with self.assertRaises(ValueError):
                self.load()

    def test_coordinated_control_and_csv_label_or_baseline_change_denied(self):
        original_rows, original_controls = copy.deepcopy(self.rows), copy.deepcopy(self.controls)
        key = next(iter(self.controls))
        for column, field, value in (("outcome", "outcome", 1), ("raw_market_probability", "raw_market", .6)):
            self.rows, self.controls = copy.deepcopy(original_rows), copy.deepcopy(original_controls)
            self.rows[0][column] = str(value)
            self.controls[key][field] = value
            self.write_rows()
            with self.assertRaisesRegex(ValueError, "original frozen rows"):
                self.load()

    def test_exclusion_codes_and_denominator_rebound_artifacts_denied(self):
        path = Path(self.spec["artifact_root"]) / "exclusions.json"
        original = json.loads(path.read_text())
        changed = copy.deepcopy(original)
        changed["exclusions"][0]["reason"] = "hard_to_predict"
        _write(path, changed)
        self.rebind("exclusions.json")
        with self.assertRaises(ValueError):
            self.load()
        changed["source_events"] = 194
        self.accepted["exclusions"] = changed
        _write(path, changed)
        self.rebind("exclusions.json")
        with self.assertRaises(ValueError):
            self.load()

    def test_parent_causal_receipts_and_boundary_flags_drift_denied(self):
        path = Path(self.spec["artifact_root"]) / "input_receipts.json"
        original = json.loads(path.read_text())
        for field, value in (("runner_sha256", "c" * 64), ("route_dev_opened", True), ("external_fetch", True),
                             ("v0_artifact_hashes", {}), ("materialized_receipts", []), ("pbp_receipts", []), ("route_dev_opened", 0)):
            _write(path, {**original, field: value})
            self.rebind("input_receipts.json")
            with self.assertRaises(ValueError):
                self.load()

    def test_rebound_acceptance_cannot_change_frozen_exclusion_codes(self):
        path = Path(self.spec["artifact_root"]) / "exclusions.json"
        changed = json.loads(path.read_text())
        changed["exclusions"][0]["reason"] = "hard_to_predict"
        self.accepted["exclusions"] = changed
        _write(path, changed)
        self.rebind("exclusions.json")
        with self.assertRaisesRegex(ValueError, "frozen exclusion codes"):
            self.load()

    def test_integer_counts_reject_bool_and_float_equality(self):
        path = Path(self.spec["artifact_root"]) / "manifest.json"
        original = json.loads(path.read_text())
        for field, value in (("model_fits", 4.0), ("check_events", 87.0)):
            _write(path, {**original, field: value})
            self.rebind("manifest.json")
            with self.assertRaises(ValueError):
                self.load()

    def test_symlink_and_path_traversal_are_denied(self):
        original_runner_path = self.spec["runner"]["path"]
        alias = self.root / "source_alias.py"
        alias.symlink_to(Path(self.spec["runner"]["path"]))
        self.spec["runner"]["path"] = str(alias)
        self.accept()
        with self.assertRaises(ValueError):
            self.load()
        self.spec["runner"]["path"] = original_runner_path
        self.spec["artifact_hashes"]["../escape"] = "c" * 64
        self.accept()
        with self.assertRaises(ValueError):
            self.load()

    def test_duplicate_json_fields_and_duplicate_csv_headers_denied(self):
        path = Path(self.acceptance["path"])
        path.write_text('{"schema":"one","schema":"two"}', encoding="utf-8")
        self.acceptance = _binding(path)
        with self.assertRaises(ValueError):
            self.load()
        self.accept()
        path = Path(self.spec["artifact_root"]) / "predictions.csv"
        body = path.read_text()
        lines = body.splitlines()
        lines[0] += ",candidate_probability"
        path.write_text("\n".join(lines) + "\n")
        self.rebind("predictions.csv")
        with self.assertRaises(ValueError):
            self.load()

    def test_no_candidate_training_dependencies_or_optional_state_parser(self):
        text = Path(reference.__file__).read_text()
        for forbidden in ("import sklearn", "import numpy", "pickle", ".fit(", "subprocess", "importlib"):
            self.assertNotIn(forbidden, text)
        self.assertNotIn("predictor_states.json", reference.ARTIFACTS)

    def test_preflight_header_is_pure_not_a_read_or_admission(self):
        before = {str(path): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(reference.validate_header(self.spec, self.accepted), self.accepted)
        self.assertEqual(before, {str(path): path.read_bytes() for path in self.root.rglob("*") if path.is_file()})


if __name__ == "__main__":
    unittest.main()
