from __future__ import annotations

import math
from pathlib import Path
import tempfile
import unittest

from experiments import nfl_ingame_prior_play_success_market_uncertainty_audit as audit


def _bootstrap_evidence(*, valid: int = 10_000, lower: float = 0.001) -> dict:
    return {
        "bootstrap_replicates": 10_000,
        "valid_draws": valid,
        "undefined_draws_missing_one_or_both_regimes": 10_000 - valid,
        "interval_95": [lower, 0.04] if valid else None,
    }


def _aggregate(
    *, low_events: int = 12, high_events: int = 12,
    low_log: float = 0.02, high_log: float = -0.01,
    high_brier: float = -0.002,
) -> dict:
    return {
        "low": {
            "events": low_events,
            "mean_log_loss_directional_alignment": low_log,
            "mean_brier_logit_directional_alignment": 0.001,
        },
        "high": {
            "events": high_events,
            "mean_log_loss_directional_alignment": high_log,
            "mean_brier_logit_directional_alignment": high_brier,
        },
        "low_minus_high_log_alignment": low_log - high_log,
    }


def _folds(values: tuple[float | None, ...] = (.03, .02, .01, -.01)) -> list[dict]:
    return [
        {"fold": index, "low_minus_high_log_alignment": value}
        for index, value in enumerate(values, 1)
    ]


class InGamePriorPlaySuccessMarketUncertaintyAuditTests(unittest.TestCase):
    def test_actual_parent_hash_mask_and_zero_fit_preflight(self) -> None:
        if not audit.PARENT_ARTIFACT_ROOT.is_dir():
            self.skipTest("frozen parent artifact is unavailable")
        parent = audit._validate_parent_artifact(audit.PARENT_ARTIFACT_ROOT)
        self.assertEqual(len(parent["records"]), 87)
        self.assertEqual(
            parent["event_identity_sha256"], audit.EXPECTED_EVENT_IDENTITY_SHA256
        )
        self.assertEqual(
            parent["hashes"]["manifest.json"],
            "addececc96838399be8b9713b85048dba6c449e840aff6f69f099f1779750144",
        )
        self.assertEqual(parent["manifest"]["model_fits"], 0)

    def test_parent_hash_guard_fails_closed(self) -> None:
        changed = dict(audit.EXPECTED_PARENT_HASHES)
        changed["event_audit.csv"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "event_audit.csv"):
            audit._validate_parent_artifact(
                audit.PARENT_ARTIFACT_ROOT, expected_hashes=changed
            )
        incomplete = dict(audit.EXPECTED_PARENT_HASHES)
        incomplete.pop("scorecard.json")
        with self.assertRaisesRegex(ValueError, "every frozen parent file"):
            audit._validate_parent_artifact(
                audit.PARENT_ARTIFACT_ROOT, expected_hashes=incomplete
            )

    def test_regime_threshold_is_inclusive_at_both_probability_endpoints(self) -> None:
        self.assertEqual(audit._market_uncertainty_regime(0.25), (0.1875, "high"))
        self.assertEqual(audit._market_uncertainty_regime(0.75), (0.1875, "high"))
        self.assertEqual(audit._market_uncertainty_regime(0.5)[1], "high")
        self.assertEqual(
            audit._market_uncertainty_regime(math.nextafter(0.25, 0.0))[1], "low"
        )
        self.assertEqual(
            audit._market_uncertainty_regime(math.nextafter(0.75, 1.0))[1], "low"
        )
        with self.assertRaisesRegex(ValueError, "inside"):
            audit._market_uncertainty_regime(1.0)

    def test_regime_assignment_preserves_exact_mask_and_rejects_duplicates(self) -> None:
        rows = [
            {"game_id": "a", "raw_market_probability": .1},
            {"game_id": "b", "raw_market_probability": .5},
        ]
        assigned = audit._assign_regimes(rows)
        self.assertEqual([row["game_id"] for row in assigned], ["a", "b"])
        self.assertEqual([row["regime"] for row in assigned], ["low", "high"])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            audit._assign_regimes([rows[0], rows[0]])

    def test_complete_group_bootstrap_counts_undefined_draws_without_imputation(self) -> None:
        records = [
            {
                "game_id": "l1", "game_date": "low-date", "game_week": "1",
                "regime": "low", "log_loss_directional_alignment": 1.0,
                "brier_logit_directional_alignment": .1,
            },
            {
                "game_id": "l2", "game_date": "low-date", "game_week": "1",
                "regime": "low", "log_loss_directional_alignment": 3.0,
                "brier_logit_directional_alignment": .2,
            },
            {
                "game_id": "h1", "game_date": "high-date", "game_week": "2",
                "regime": "high", "log_loss_directional_alignment": 0.0,
                "brier_logit_directional_alignment": -.1,
            },
        ]
        result = audit._group_regime_contrast_bootstrap(
            records, "game_date", seed=7, replicates=1000
        )
        self.assertEqual(result["bootstrap_replicates"], 1000)
        self.assertEqual(
            result["valid_draws"]
            + result["undefined_draws_missing_one_or_both_regimes"],
            1000,
        )
        self.assertGreater(result["undefined_draws_missing_one_or_both_regimes"], 0)
        self.assertGreater(result["valid_draws"], 0)
        self.assertAlmostEqual(result["point_low_minus_high_log_alignment"], 2.0)
        self.assertIn("count", result["resampling_rule"])

    def test_decision_support_is_exact(self) -> None:
        decision, evidence = audit.market_uncertainty_decision(
            _aggregate(), _folds(), _bootstrap_evidence(), _bootstrap_evidence()
        )
        self.assertEqual(
            decision, "PRIOR_PLAY_SUCCESS_MARKET_UNCERTAINTY_SUPPORTED"
        )
        self.assertEqual(evidence["positive_fold_contrasts"], 3)
        self.assertTrue(all(evidence["support_conditions"].values()))

    def test_decision_refute_and_other_inconclusive_are_exact(self) -> None:
        refuted = _aggregate(low_log=-.01, high_log=.01, high_brier=.001)
        decision, evidence = audit.market_uncertainty_decision(
            refuted, _folds((-.02, -.01, .01, -.03)),
            _bootstrap_evidence(lower=-.04), _bootstrap_evidence(lower=-.03),
        )
        self.assertEqual(
            decision, "PRIOR_PLAY_SUCCESS_MARKET_UNCERTAINTY_REFUTED"
        )
        self.assertTrue(evidence["refute_conditions"][
            "low_nonpositive_while_high_nonnegative"
        ])

        decision, evidence = audit.market_uncertainty_decision(
            _aggregate(), _folds((.02, .01, -.01, -.02)),
            _bootstrap_evidence(lower=-.01), _bootstrap_evidence(lower=-.01),
        )
        self.assertEqual(
            decision, "PRIOR_PLAY_SUCCESS_MARKET_UNCERTAINTY_INCONCLUSIVE"
        )
        self.assertEqual(evidence["decision_stage"], "otherwise_inconclusive")

    def test_insufficient_breadth_precedes_refute(self) -> None:
        aggregate = _aggregate(
            low_events=11, low_log=-.02, high_log=.02, high_brier=.001
        )
        decision, evidence = audit.market_uncertainty_decision(
            aggregate, _folds((-.01, -.01, -.01, -.01)),
            _bootstrap_evidence(valid=8999), _bootstrap_evidence(),
        )
        self.assertEqual(
            decision, "PRIOR_PLAY_SUCCESS_MARKET_UNCERTAINTY_INCONCLUSIVE"
        )
        self.assertEqual(evidence["decision_stage"], "insufficient_breadth")
        self.assertEqual(evidence["support_conditions"], {})
        self.assertEqual(evidence["refute_conditions"], {})

    def test_bootstrap_accounting_and_nonfinite_decision_fail_closed(self) -> None:
        malformed = _bootstrap_evidence()
        malformed["undefined_draws_missing_one_or_both_regimes"] = 1
        with self.assertRaisesRegex(ValueError, "accounting"):
            audit.market_uncertainty_decision(
                _aggregate(), _folds(), malformed, _bootstrap_evidence()
            )
        invalid = _aggregate(low_log=float("nan"))
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            audit.market_uncertainty_decision(
                invalid, _folds(), _bootstrap_evidence(), _bootstrap_evidence()
            )
        with self.assertRaisesRegex(ValueError, "fold regime contrast"):
            audit.market_uncertainty_decision(
                _aggregate(), _folds((.03, float("nan"), .01, -.01)),
                _bootstrap_evidence(), _bootstrap_evidence(),
            )

    def test_scheduler_binding_zero_fit_no_pbp_and_persistent_boundary(self) -> None:
        self.assertEqual(
            audit._digest(audit.SCHEDULER_BRANCH_BINDING),
            audit.SCHEDULER_BRANCH_BINDING_SHA256,
        )
        self.assertEqual(audit.SCHEDULER_BRANCH_BINDING["attempt_id"], "attempt-03")
        self.assertEqual(audit.MODEL_FITS, 0)
        source = Path(audit.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "import subprocess", "Rscript", "predict_proba", "LogisticRegression",
            "HistGradientBoosting", "requests", "httpx", "urllib", "socket",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn('"no_pbp_recomputation": True', source)
        self.assertIn('"provider_cost_usd": "0"', source)

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "persistent"):
                audit._validate_paths(
                    audit.PARENT_ARTIFACT_ROOT, Path(directory) / "audit",
                    allow_test_paths=False,
                )
        cloud = audit.PERSISTENT_ARTIFACT_ROOT / "Dropbox" / "audit"
        with self.assertRaisesRegex(ValueError, "cloud"):
            audit._validate_paths(
                audit.PARENT_ARTIFACT_ROOT, cloud, allow_test_paths=False
            )


if __name__ == "__main__":
    unittest.main()
