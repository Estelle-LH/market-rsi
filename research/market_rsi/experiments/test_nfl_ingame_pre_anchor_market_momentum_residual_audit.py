from __future__ import annotations

import csv
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from experiments import nfl_ingame_pre_anchor_market_momentum_residual_audit as audit


def _trade(timestamp: int, probability: float, size: float = 1.0) -> dict:
    return {"timestamp": timestamp, "home_probability": probability, "size": size}


class InGamePreAnchorMarketMomentumResidualAuditTests(unittest.TestCase):
    def test_strict_current_and_reference_cutoffs_and_weighting(self) -> None:
        trades = [
            _trade(700, 0.2), _trade(780, 0.99),
            _trade(899, 0.6, 1.0), _trade(899, 0.8, 3.0),
            _trade(900, 0.01),
        ]
        result = audit.market_momentum_signal(trades, 900)
        self.assertEqual(result["reference_cutoff_epoch_s"], 780)
        self.assertEqual(result["reference_latest_trade_epoch_s"], 700)
        self.assertEqual(result["reference_age_seconds"], 80)
        self.assertAlmostEqual(result["p_ref"], 0.2)
        self.assertAlmostEqual(result["p_now"], 0.75)
        expected = math.log(0.75 / 0.25) - math.log(0.2 / 0.8)
        self.assertAlmostEqual(result["signal"], expected)

    def test_reference_coverage_and_staleness_fail_closed(self) -> None:
        self.assertEqual(
            audit.market_momentum_signal(
                [_trade(580, 0.4), _trade(999, 0.6)], 1000
            )["reference_age_seconds"],
            300,
        )
        with self.assertRaisesRegex(ValueError, "age gate"):
            audit.market_momentum_signal(
                [_trade(579, 0.4), _trade(999, 0.6)], 1000
            )
        with self.assertRaisesRegex(ValueError, "strictly before"):
            audit.market_momentum_signal([_trade(999, 0.6)], 1000)

    def test_logit_clips_only_for_transform_and_signal_uses_no_label(self) -> None:
        result = audit.market_momentum_signal(
            [_trade(700, 0.0), _trade(899, 1.0)], 900
        )
        expected = audit._clipped_logit(1.0) - audit._clipped_logit(0.0)
        self.assertEqual(result["p_ref"], 0.0)
        self.assertEqual(result["p_now"], 1.0)
        self.assertAlmostEqual(result["signal"], expected)
        self.assertNotIn("outcome", audit.market_momentum_signal.__code__.co_varnames)

    def test_event_formulas_and_label_change_do_not_change_signal(self) -> None:
        base = {
            "fold": 1, "game_id": "g", "game_date": "2025-01-01",
            "game_week": "01", "event_id": "e", "market_id": "m",
            "cutoff_ms": 1, "decision_floor_epoch_s": 1,
            "current_latest_trade_epoch_s": 0, "reference_cutoff_epoch_s": -119,
            "reference_latest_trade_epoch_s": -120, "reference_age_seconds": 1,
            "p_now": 0.8, "p_ref": 0.5, "signal": 0.4,
        }
        one = audit._event_records([{**base, "outcome": 1}])[0]
        zero = audit._event_records([{**base, "outcome": 0}])[0]
        self.assertEqual(one["signal"], zero["signal"])
        self.assertAlmostEqual(one["market_residual"], 0.2)
        self.assertAlmostEqual(one["log_loss_directional_alignment"], 0.08)
        self.assertAlmostEqual(one["brier_logit_directional_alignment"], 0.0128)
        self.assertAlmostEqual(zero["market_residual"], -0.8)

    def test_complete_group_bootstrap_reports_draw_counts(self) -> None:
        records = [
            {"game_date": "a", "value": 1.0},
            {"game_date": "a", "value": 3.0},
            {"game_date": "b", "value": 9.0},
        ]
        result = audit._group_bootstrap(
            records, "game_date", "value", seed=7, replicates=100
        )
        self.assertEqual(result["valid_draws"], 100)
        self.assertEqual(result["undefined_draws"], 0)
        self.assertAlmostEqual(result["point_equal_event_mean"], 13 / 3)
        self.assertIn("pooled equal-event", result["resampling_rule"])

    def test_frozen_support_refute_and_inconclusive_rules(self) -> None:
        aggregate = {
            "pearson_signal_vs_market_residual": 0.2,
            "spearman_signal_vs_market_residual": 0.1,
            "mean_log_loss_directional_alignment": 0.02,
            "mean_brier_logit_directional_alignment": 0.003,
        }
        folds = [{"mean_log_loss_directional_alignment": value}
                 for value in (0.02, 0.01, 0.03, -0.01)]
        positive = {"interval_95": [0.001, 0.04]}
        decision, conditions = audit.audit_decision(
            aggregate, folds, positive, positive
        )
        self.assertEqual(decision, "PRE_ANCHOR_MARKET_MOMENTUM_RESIDUAL_SUPPORTED")
        self.assertTrue(all(conditions["support_conditions"].values()))
        refuted = dict(aggregate, pearson_signal_vs_market_residual=0.0,
                       spearman_signal_vs_market_residual=-0.1)
        self.assertEqual(
            audit.audit_decision(refuted, folds, positive, positive)[0],
            "PRE_ANCHOR_MARKET_MOMENTUM_RESIDUAL_REFUTED",
        )
        crossing = {"interval_95": [-0.01, 0.04]}
        mixed = dict(aggregate, mean_brier_logit_directional_alignment=-0.001)
        decision, _ = audit.audit_decision(mixed, folds, crossing, crossing)
        self.assertEqual(decision, "PRE_ANCHOR_MARKET_MOMENTUM_RESIDUAL_INCONCLUSIVE")

    def test_actual_v0_hash_lineage_and_mask_preflight_only(self) -> None:
        if not audit.V0_ARTIFACT_ROOT.is_dir() or not audit.SOURCE_ROOT.is_dir():
            self.skipTest("opened Train or reviewed v0 artifact is unavailable")
        frozen = audit.prior._validate_v0_artifact(audit.V0_ARTIFACT_ROOT)
        source = audit.prior._validate_source_and_receipts(audit.SOURCE_ROOT, frozen)
        self.assertEqual(len(frozen["anchors"]), 195)
        self.assertEqual(len(frozen["predictions"]), 87)
        self.assertEqual(frozen["check_key_sha256"], audit.prior.EXPECTED_CHECK_KEY_SHA256)
        self.assertEqual(source["pbp_games"], 195)

    def test_scheduler_zero_fit_and_no_network_or_model_path(self) -> None:
        self.assertEqual(
            audit._digest(audit.SCHEDULER_BRANCH_BINDING),
            audit.SCHEDULER_BRANCH_BINDING_SHA256,
        )
        self.assertEqual(audit.SCHEDULER_BRANCH_BINDING["attempt_id"], "attempt-04")
        self.assertEqual(audit.MODEL_FITS, 0)
        source = Path(audit.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "requests", "urllib", "httpx", "aiohttp", "socket",
            "LogisticRegression", "HistGradientBoosting", "predict_proba",
        ):
            self.assertNotIn(forbidden, source)

    def test_persistent_output_guard(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "persistent"):
                audit._validate_paths(
                    audit.SOURCE_ROOT, audit.V0_ARTIFACT_ROOT,
                    Path(directory) / "audit", allow_test_paths=False,
                )
        cloud = audit.PERSISTENT_ARTIFACT_ROOT / "Dropbox" / "audit"
        with self.assertRaisesRegex(ValueError, "cloud"):
            audit._validate_paths(
                audit.SOURCE_ROOT, audit.V0_ARTIFACT_ROOT, cloud,
                allow_test_paths=False,
            )

    def test_synthetic_end_to_end_writes_zero_fit_artifact(self) -> None:
        rows = []
        for fold in range(1, 5):
            for offset in range(2):
                number = (fold - 1) * 2 + offset
                p = 0.35 + 0.04 * number
                outcome = number % 2
                rows.append({
                    "fold": fold, "game_id": f"g{number}",
                    "game_date": f"2025-01-{number + 1:02d}",
                    "game_week": f"{fold:02d}", "event_id": f"e{number}",
                    "market_id": f"m{number}", "cutoff_ms": 1000 + number,
                    "outcome": outcome, "p_now": p, "p_ref": 0.5,
                    "signal": (number - 3.5) / 10,
                    "decision_floor_epoch_s": 1000 + number,
                    "current_latest_trade_epoch_s": 999 + number,
                    "reference_cutoff_epoch_s": 880 + number,
                    "reference_latest_trade_epoch_s": 879 + number,
                    "reference_age_seconds": 1,
                })
        frozen = {
            "hashes": {}, "receipts": {}, "anchors": [],
            "predictions": [dict(row) for row in rows],
            "check_key_sha256": "a" * 64,
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, v0_root, output = root / "source", root / "v0", root / "output"
            source.mkdir(); v0_root.mkdir()
            with (source / "cohort.csv").open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=("game_id", "game_date", "event_slug"))
                writer.writeheader()
            with mock.patch.object(audit.prior, "_validate_v0_artifact", return_value=frozen), \
                    mock.patch.object(audit, "_extract_market_signals", return_value=(rows, [])), \
                    mock.patch.object(audit, "BOOTSTRAP_REPLICATES", 100):
                manifest = audit.run(
                    source, v0_root, output, allow_test_paths=True,
                    expected_v0_hashes={}, generated_utc="2026-09-29T00:00:00Z",
                )
            self.assertTrue(manifest["complete"])
            self.assertEqual(manifest["model_fits"], 0)
            self.assertEqual(manifest["check_events"], 8)
            self.assertFalse(manifest["incumbent_or_keep_revert_changed"])
            scorecard = json.loads((output / "scorecard.json").read_text())
            self.assertEqual(scorecard["model_fits"], 0)
            self.assertTrue(scorecard["no_rows_dropped_from_v0_common_mask"])
            self.assertFalse(scorecard["no_prediction_candidate_emitted"] is False)

    def test_coverage_failure_writes_terminal_failure_and_no_manifest(self) -> None:
        frozen = {"hashes": {}, "receipts": {}, "anchors": [], "predictions": [],
                  "check_key_sha256": "a" * 64}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, v0_root, output = root / "source", root / "v0", root / "output"
            source.mkdir(); v0_root.mkdir()
            with (source / "cohort.csv").open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=("game_id", "game_date", "event_slug"))
                writer.writeheader()
            with mock.patch.object(audit.prior, "_validate_v0_artifact", return_value=frozen), \
                    mock.patch.object(audit, "_extract_market_signals", side_effect=ValueError("reference coverage failed")):
                with self.assertRaisesRegex(ValueError, "coverage"):
                    audit.run(source, v0_root, output, allow_test_paths=True,
                              expected_v0_hashes={})
            failure = json.loads((output / "failure.json").read_text())
            self.assertEqual(failure["model_fits"], 0)
            self.assertFalse((output / "manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
