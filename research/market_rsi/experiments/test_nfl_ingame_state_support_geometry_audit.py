from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import numpy as np

from experiments import nfl_ingame_state_support_geometry_audit as audit


def _decision_records(mode: str) -> list[dict]:
    records = []
    counts = audit.EXPECTED_CHECK_COUNTS
    for fold, count in enumerate(counts, 1):
        for index in range(count):
            unsupported = False
            delta = 0.01
            if mode == "support" and index < 3:
                unsupported, delta = True, 0.10
            elif mode == "inconclusive" and fold <= 2 and index < 3:
                unsupported, delta = True, 0.12
            records.append({
                "fold": fold,
                "game_id": f"f{fold}-{index}",
                "game_date": f"2025-0{fold}-01",
                "game_week": str(fold),
                "delta": delta,
                "unsupported": unsupported,
            })
    return records


class InGameStateSupportGeometryAuditTests(unittest.TestCase):
    def test_support_refute_and_inconclusive_rules_are_exact(self) -> None:
        supported, evidence = audit.support_decision(_decision_records("support"))
        self.assertEqual(supported, "SAMPLE_SUPPORT_EXPLANATION_SUPPORTED")
        self.assertEqual(evidence["positive_fold_contrasts"], 4)
        self.assertTrue(all(evidence["support_conditions"].values()))

        refuted, evidence = audit.support_decision(_decision_records("refute"))
        self.assertEqual(refuted, "SAMPLE_SUPPORT_EXPLANATION_REFUTED")
        self.assertTrue(evidence["refute_conditions"]["unsupported_share_below_5_percent"])

        inconclusive, evidence = audit.support_decision(
            _decision_records("inconclusive")
        )
        self.assertEqual(inconclusive, "SAMPLE_SUPPORT_EXPLANATION_INCONCLUSIVE")
        self.assertEqual(evidence["positive_fold_contrasts"], 2)
        self.assertFalse(all(evidence["support_conditions"].values()))
        self.assertFalse(any(evidence["refute_conditions"].values()))

    def test_scaler_and_threshold_are_fit_only_and_binary_columns_stay_raw(self) -> None:
        fit = np.asarray([
            [index, 1200 + 5 * index, index % 2, 1, 0, 0, 0, 5 + index, -0.5 + index / 10]
            for index in range(8)
        ], dtype=float)
        check_a = np.asarray([
            [2, 1210, 1, 0, 1, 0, 0, 7, -0.2],
            [6, 1230, 0, 0, 0, 1, 0, 11, 0.1],
        ], dtype=float)
        check_b = check_a.copy()
        check_b[:, audit.CONTINUOUS_INDICES] += 1_000_000
        first = audit._fold_geometry(fit, check_a)
        second = audit._fold_geometry(fit, check_b)
        self.assertEqual(first["threshold"], second["threshold"])
        self.assertEqual(first["scaler"], second["scaler"])
        scaled_fit, scaled_check, _ = audit._scale_state_fit_only(fit, check_a)
        np.testing.assert_array_equal(
            scaled_fit[:, audit.BINARY_INDICES], fit[:, audit.BINARY_INDICES]
        )
        np.testing.assert_array_equal(
            scaled_check[:, audit.BINARY_INDICES], check_a[:, audit.BINARY_INDICES]
        )
        np.testing.assert_array_equal(
            first["unsupported"],
            first["check_mean_distances"] > first["threshold"],
        )

    def test_fit_distance_is_leave_one_out_five_neighbor_mean(self) -> None:
        values = np.arange(6, dtype=float).reshape(-1, 1)
        observed = audit._mean_k_distances(values, values, leave_self_out=True)
        self.assertEqual(observed[0], 3.0)
        self.assertEqual(observed[-1], 3.0)
        with self.assertRaisesRegex(ValueError, "same query/reference"):
            audit._mean_k_distances(values + 1, values, leave_self_out=True)

    def test_group_arithmetic_uses_signed_sums_and_equal_event_means(self) -> None:
        records = [
            {"delta": 0.1, "unsupported": False},
            {"delta": -0.05, "unsupported": False},
            {"delta": 0.4, "unsupported": True},
            {"delta": -0.1, "unsupported": True},
        ]
        summary = audit._stratum_summary(records)
        self.assertAlmostEqual(summary["all_signed_sum"], 0.35)
        self.assertAlmostEqual(summary["unsupported_signed_sum"], 0.3)
        self.assertAlmostEqual(summary["unsupported_signed_contribution"], 0.3 / 0.35)
        self.assertAlmostEqual(summary["supported_mean_delta"], 0.025)
        self.assertAlmostEqual(summary["unsupported_mean_delta"], 0.15)
        self.assertAlmostEqual(
            summary["unsupported_minus_supported_mean_delta"], 0.125
        )
        # A chronological fold may have negative total harm even though the
        # frozen 87-game aggregate is positive; fold contrasts remain valid.
        negative_fold = audit._stratum_summary([
            {"delta": -0.2, "unsupported": False},
            {"delta": 0.1, "unsupported": True},
        ])
        self.assertAlmostEqual(negative_fold["all_signed_sum"], -0.1)

    def test_feature_range_violations_are_fit_relative_and_do_not_drop_rows(self) -> None:
        fit = np.zeros((6, len(audit.STATE_FEATURE_NAMES)))
        fit[:, 0] = np.arange(6)
        check = np.zeros((2, len(audit.STATE_FEATURE_NAMES)))
        check[0, 0] = 6
        violations = audit._feature_range_violations(fit, check)
        self.assertEqual(violations[0], ["home_score_diff_pre"])
        self.assertEqual(violations[1], [])
        self.assertEqual(len(violations), len(check))

    def test_hash_guard_fails_closed_on_any_mutated_v0_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = {}
            for index, name in enumerate(audit.EXPECTED_V0_HASHES):
                path = root / name
                path.write_text(f"file-{index}\n", encoding="utf-8")
                expected[name] = audit._sha256(path)
            self.assertEqual(audit._validate_hashes(root, expected), expected)
            (root / "predictions.csv").write_text("mutated\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "predictions.csv"):
                audit._validate_hashes(root, expected)

    def test_chronology_and_output_boundary_fail_closed(self) -> None:
        valid = [
            {"fold": 1, "fit_dates": ["2025-01-01"],
             "check_dates": ["2025-01-02", "2025-01-03", "2025-01-04", "2025-01-05", "2025-01-06"]},
            {"fold": 2,
             "fit_dates": ["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04", "2025-01-05", "2025-01-06"],
             "check_dates": ["2025-01-07", "2025-01-08", "2025-01-09", "2025-01-10", "2025-01-11"]},
            {"fold": 3,
             "fit_dates": [f"2025-01-{day:02d}" for day in range(1, 12)],
             "check_dates": [f"2025-01-{day:02d}" for day in range(12, 17)]},
            {"fold": 4,
             "fit_dates": [f"2025-01-{day:02d}" for day in range(1, 17)],
             "check_dates": [f"2025-01-{day:02d}" for day in range(17, 22)]},
        ]
        self.assertEqual(len(audit._validate_folds(valid)), 4)
        invalid = [dict(row) for row in valid]
        invalid[0] = {**invalid[0], "check_dates": [
            "2024-12-31", "2025-01-03", "2025-01-04", "2025-01-05", "2025-01-06"
        ]}
        with self.assertRaisesRegex(ValueError, "chronological"):
            audit._validate_folds(invalid)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "persistent"):
                audit._validate_paths(
                    audit.V0_ARTIFACT_ROOT, Path(directory) / "audit",
                    allow_test_paths=False,
                )

    def test_exact_v0_hash_mask_and_lineage_preflight(self) -> None:
        if not audit.V0_ARTIFACT_ROOT.is_dir():
            self.skipTest("reviewed v0 artifact is not present")
        inputs = audit._load_frozen_inputs(
            audit.V0_ARTIFACT_ROOT,
            expected_hashes=audit.EXPECTED_V0_HASHES,
            require_exact_counts=True,
        )
        self.assertEqual(len(inputs["materialized"]), 193)
        self.assertEqual(len(inputs["checks"]), 87)
        self.assertEqual(
            [
                sum(row["game_date"] in fold["fit_dates"] for row in inputs["materialized"])
                for fold in inputs["folds"]
            ],
            list(audit.EXPECTED_FIT_COUNTS),
        )
        self.assertEqual(
            inputs["check_key_sha256"],
            "2e35779fdbb4b83e129758008338b0c778d7f6281682118ad8d26d21293cc9f9",
        )

    def test_runner_has_exactly_zero_prediction_model_fits(self) -> None:
        source = Path(audit.__file__).read_text(encoding="utf-8")
        self.assertEqual(audit.MODEL_FITS, 0)
        self.assertNotIn("LogisticRegression", source)
        self.assertNotIn("HistGradientBoosting", source)
        self.assertNotIn("predict_proba", source)


if __name__ == "__main__":
    unittest.main()
