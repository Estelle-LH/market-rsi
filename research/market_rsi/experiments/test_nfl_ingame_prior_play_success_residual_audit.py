from __future__ import annotations

import csv
from pathlib import Path
import subprocess
import tempfile
import unittest

from experiments import nfl_ingame_prior_play_success_residual_audit as audit


class InGamePriorPlaySuccessResidualAuditTests(unittest.TestCase):
    def test_frozen_support_refute_and_inconclusive_rules(self) -> None:
        aggregate = {
            "pearson_signal_vs_market_residual": 0.2,
            "spearman_signal_vs_market_residual": 0.1,
            "mean_log_loss_directional_alignment": 0.02,
            "mean_brier_logit_directional_alignment": 0.003,
        }
        folds = [
            {"mean_log_loss_directional_alignment": value}
            for value in (0.02, 0.01, 0.03, -0.01)
        ]
        positive = {"interval_95": [0.001, 0.04]}
        decision, evidence = audit.audit_decision(
            aggregate, folds, positive, positive
        )
        self.assertEqual(decision, "PRIOR_PLAY_SUCCESS_RESIDUAL_SUPPORTED")
        self.assertTrue(all(evidence["support_conditions"].values()))

        refuted = dict(
            aggregate,
            pearson_signal_vs_market_residual=0.0,
            spearman_signal_vs_market_residual=-0.1,
        )
        self.assertEqual(
            audit.audit_decision(refuted, folds, positive, positive)[0],
            "PRIOR_PLAY_SUCCESS_RESIDUAL_REFUTED",
        )

        inconclusive_folds = [
            {"mean_log_loss_directional_alignment": value}
            for value in (0.02, 0.01, -0.03, -0.01)
        ]
        inconclusive = dict(
            aggregate, spearman_signal_vs_market_residual=-0.01
        )
        crossing = {"interval_95": [-0.01, 0.04]}
        decision, evidence = audit.audit_decision(
            inconclusive, inconclusive_folds, crossing, crossing
        )
        self.assertEqual(decision, "PRIOR_PLAY_SUCCESS_RESIDUAL_INCONCLUSIVE")
        self.assertEqual(evidence["positive_log_alignment_folds"], 2)
        self.assertFalse(any(evidence["refute_conditions"].values()))

    def test_event_alignment_formulas_use_raw_market_residual(self) -> None:
        frozen = {"predictions": [{
            "fold": "1", "game_id": "g", "game_date": "2025-01-01",
            "game_week": "01", "outcome": "1", "raw_market_probability": "0.8",
        }]}
        indicator = {
            "g": {
                "signal": 0.5, "home_eligible_plays": 2, "home_successes": 1,
                "away_eligible_plays": 2, "away_successes": 0,
                "home_success_rate": 0.5, "away_success_rate": 0.0,
            }
        }
        with self.assertRaisesRegex(ValueError, "exact 87"):
            audit._event_records(frozen, indicator)
        # Check the production formula directly without weakening the exact
        # 87-row guard for a one-row unit fixture.
        residual, log_alignment, brier_alignment = audit._directional_terms(
            1, 0.8, 0.5
        )
        self.assertAlmostEqual(residual, 0.2)
        self.assertAlmostEqual(log_alignment, 0.1)
        self.assertAlmostEqual(brier_alignment, 0.016)

    def test_average_ranks_and_associations_handle_ties(self) -> None:
        self.assertEqual(
            audit._average_ranks([1.0, 1.0, 3.0]).tolist(), [1.5, 1.5, 3.0]
        )
        self.assertAlmostEqual(audit._pearson([1, 2, 3], [2, 4, 6]), 1.0)
        with self.assertRaisesRegex(ValueError, "constant"):
            audit._pearson([1, 1, 1], [1, 2, 3])

    def test_complete_group_bootstrap_recomputes_pooled_equal_event_mean(self) -> None:
        records = [
            {"game_date": "a", "value": 1.0},
            {"game_date": "a", "value": 3.0},
            {"game_date": "b", "value": 9.0},
        ]
        result = audit._group_bootstrap(
            records, "game_date", "value", seed=7, replicates=100
        )
        self.assertEqual(result["groups"], 2)
        self.assertEqual(result["events"], 3)
        self.assertAlmostEqual(result["point_equal_event_mean"], 13 / 3)
        self.assertIn("pooled equal-event", result["resampling_rule"])

    def test_missing_side_is_integrity_failure_not_row_drop(self) -> None:
        exclusions = list(audit.EXPECTED_EXCLUSIONS)
        materialized = [f"g-{index:03d}" for index in range(193)]
        game_ids = exclusions + materialized
        anchors = [{
            "game_id": game_id, "play_id": str(index + 1),
            "order_sequence": str(index + 1), "status": "eligible",
        } for index, game_id in enumerate(game_ids)]
        frozen = {
            "anchors": anchors,
            "excluded_game_ids": set(exclusions),
        }
        fields = (
            "game_id", "status", "detail", "anchor_play_id",
            "anchor_order_sequence", "home_eligible_plays", "home_successes",
            "away_eligible_plays", "away_successes", "home_success_rate",
            "away_success_rate", "home_minus_away_success_rate",
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "indicator.csv"
            with path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                for index, game_id in enumerate(game_ids):
                    status = "missing_side_eligible_plays" if game_id == "g-007" else "eligible"
                    writer.writerow({
                        "game_id": game_id, "status": status, "detail": "",
                        "anchor_play_id": str(index + 1),
                        "anchor_order_sequence": str(index + 1),
                        "home_eligible_plays": 2, "home_successes": 1,
                        "away_eligible_plays": 2, "away_successes": 1,
                        "home_success_rate": 0.5, "away_success_rate": 0.5,
                        "home_minus_away_success_rate": 0.0,
                    })
            with self.assertRaisesRegex(ValueError, "lacks both-side"):
                audit._load_indicators(path, frozen)

    def test_r_extractor_self_test_and_static_leakage_boundary(self) -> None:
        completed = subprocess.run(
            ["Rscript", str(audit.EXTRACTOR), "--self-test"],
            check=True, capture_output=True, text=True, timeout=30,
        )
        self.assertIn("self-test PASS", completed.stdout)
        source = audit.EXTRACTOR.read_text(encoding="utf-8")
        self.assertIn(
            "prior_positions <- which(order_value < as.numeric(anchor_order))",
            source,
        )
        self.assertNotIn("which(order_value <=", source)
        self.assertIn("prior_plays <- plays[prior_positions", source)
        for forbidden in (
            "scoringSummaries", "homeScore", "visitorScore", "finalScore",
            "winner", "outcomePrices",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("playDeleted", source)
        self.assertIn('play_type != "UNSPECIFIED"', source)
        self.assertIn("0.45 * yards_to_go", source)
        self.assertIn("0.60 * yards_to_go", source)

    def test_actual_v0_hash_mask_and_source_receipt_preflight(self) -> None:
        if not audit.V0_ARTIFACT_ROOT.is_dir() or not audit.SOURCE_ROOT.is_dir():
            self.skipTest("opened Train or reviewed v0 artifact is unavailable")
        frozen = audit._validate_v0_artifact(audit.V0_ARTIFACT_ROOT)
        self.assertEqual(len(frozen["anchors"]), 195)
        self.assertEqual(len(frozen["predictions"]), 87)
        self.assertEqual(frozen["check_key_sha256"], audit.EXPECTED_CHECK_KEY_SHA256)
        receipt = audit._validate_source_and_receipts(audit.SOURCE_ROOT, frozen)
        self.assertEqual(receipt["pbp_games"], 195)

    def test_scheduler_branch_digest_and_zero_prediction_fit_are_frozen(self) -> None:
        self.assertEqual(
            audit._digest(audit.SCHEDULER_BRANCH_BINDING),
            audit.SCHEDULER_BRANCH_BINDING_SHA256,
        )
        self.assertEqual(audit.SCHEDULER_BRANCH_BINDING["attempt_id"], "attempt-01")
        self.assertEqual(audit.SCHEDULER_BRANCH_BINDING["allocation"], "exploration")
        self.assertIs(
            audit.SCHEDULER_BRANCH_BINDING["resource_hint"]["authority_granted"],
            False,
        )
        source = Path(audit.__file__).read_text(encoding="utf-8")
        self.assertEqual(audit.MODEL_FITS, 0)
        self.assertNotIn("LogisticRegression", source)
        self.assertNotIn("HistGradientBoosting", source)
        self.assertNotIn("predict_proba", source)

    def test_persistent_output_guard_rejects_temporary_and_cloud_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "persistent"):
                audit._validate_paths(
                    audit.SOURCE_ROOT, audit.V0_ARTIFACT_ROOT,
                    Path(directory) / "audit", allow_test_paths=False,
                )
        cloud = audit.PERSISTENT_ARTIFACT_ROOT / "Google Drive" / "audit"
        with self.assertRaisesRegex(ValueError, "cloud"):
            audit._validate_paths(
                audit.SOURCE_ROOT, audit.V0_ARTIFACT_ROOT, cloud,
                allow_test_paths=False,
            )


if __name__ == "__main__":
    unittest.main()
