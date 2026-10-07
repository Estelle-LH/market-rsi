from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import math
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import numpy as np

from experiments import nfl_ingame_market_freshness_interaction_offset as candidate


def synthetic_problem():
    dates = [(date(2025, 1, 1) + timedelta(days=index)).isoformat() for index in range(42)]
    rows, states = [], {}
    for index, day in enumerate(dates):
        probability = .15 + .7 * (index % 11) / 10
        cutoff = (10_000 + index * 100) * 1000
        receipt = {"game_id": f"game-{index}", "latest_trade_epoch_ms": cutoff - (index % 19 + 1) * 1000,
            "market_feature_cutoff_epoch_s": cutoff // 1000 - 1,
            "pbp_checkpoint_event_time_utc": datetime.fromtimestamp(cutoff / 1000, timezone.utc).isoformat(),
            "market_staleness_seconds": float(index % 19 + 1)}
        trusted = {"event_id": f"event-{index}", "market_id": f"market-{index}",
            "cutoff_ms": cutoff, "feature_available_ms": cutoff, "outcome_available_ms": cutoff + 1,
            "outcome": int(index % 3 == 0), "market_probability": probability}
        row = candidate.base.InGameRow(f"game-{index}", day, str(index // 6 + 1), trusted,
            (math.log(probability / (1 - probability)),), (0.,) * 9, receipt)
        rows.append(row)
        states[row.game_id] = {"possession_is_home": str(index % 2), "down": str(index % 4 + 1),
            "yards_to_go": str(index % 12), "yards_to_opponent_goal": str(index % 95)}
    folds = candidate.settlement.chronological_date_folds(dates)
    controls = {}
    for fold in folds:
        for row in rows:
            if row.game_date in fold["check_dates"]:
                probability = row.trusted["market_probability"]
                controls[row.key] = {"fold": fold["fold"], "game_id": row.game_id,
                    "game_date": row.game_date, "game_week": row.game_week,
                    "outcome": row.trusted["outcome"], candidate.ARM_RAW: probability,
                    candidate.ARM_ORDINARY: min(.95, probability + .01),
                    candidate.ARM_PARENT: max(.05, probability - .01)}
    return rows, folds, controls, states


class FreshnessInteractionOffsetTests(unittest.TestCase):
    def test_causal_age_arithmetic_and_strict_integer_second_boundary(self):
        receipt = synthetic_problem()[0][0].source_receipt
        self.assertEqual(candidate.causal_age(receipt), 1)
        for change in ({"market_staleness_seconds": math.nan}, {"market_staleness_seconds": 2},
                       {"market_staleness_seconds": 301}, {"latest_trade_epoch_ms": 10_000_000},
                       {"latest_trade_epoch_ms": 9_999_001}, {"market_feature_cutoff_epoch_s": 10000}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                candidate.causal_age({**receipt, **change})
        with self.assertRaisesRegex(ValueError, "incomplete"):
            candidate.causal_age({})

    def test_scaling_uses_only_fit_ages_and_interacts_with_market_logit(self):
        rows, _, _, _ = synthetic_problem()
        fit_x, check_x, report = candidate.freshness_features(rows[:22], rows[22:], states={})
        fit_age = np.asarray([candidate.causal_age(row.source_receipt) for row in rows[:22]])
        np.testing.assert_array_equal(fit_x, (fit_age - fit_age.mean()) / fit_age.std(ddof=0)
            * np.asarray([row.market_features[0] for row in rows[:22]]))
        changed = []
        for row in rows[22:]:
            receipt = {**row.source_receipt, "latest_trade_epoch_ms": row.trusted["cutoff_ms"] - 200_000,
                "market_staleness_seconds": 200.0}
            changed.append(candidate.base.InGameRow(row.game_id, row.game_date, row.game_week,
                {**row.trusted, "outcome": 1 - row.trusted["outcome"]}, row.market_features,
                row.state_features, receipt))
        new_fit, new_check, new_report = candidate.freshness_features(rows[:22], changed, states={})
        np.testing.assert_array_equal(new_fit, fit_x)
        self.assertEqual(new_report, report)
        self.assertFalse(np.array_equal(new_check, check_x))
        with self.assertRaisesRegex(ValueError, "scale"):
            candidate.freshness_features([rows[0], rows[19]], rows[22:], states={})

    def test_single_basis_objective_derivatives_and_zero_column_equivalence(self):
        x, y, offsets, beta = np.array([1., -1., .5, 2.]), np.array([1., 0., 0., 1.]), np.array([.2, -.3, .1, -.1]), .27
        value, gradient, hessian = candidate.objective_gradient_hessian(beta, x, y, offsets)
        eta = offsets + beta * x
        self.assertAlmostEqual(value, float(np.sum(np.logaddexp(0, eta) - y * eta) + .5 * 16 * beta ** 2), places=12)
        h = 1e-5
        hi = candidate.objective_gradient_hessian(beta + h, x, y, offsets)
        lo = candidate.objective_gradient_hessian(beta - h, x, y, offsets)
        self.assertAlmostEqual(gradient, (hi[0] - lo[0]) / (2 * h), places=7)
        self.assertAlmostEqual(hessian, (hi[1] - lo[1]) / (2 * h), places=7)
        old_value, old_gradient, old_hessian = candidate.scaffold.objective_gradient_hessian(
            [beta, 0.], candidate._design(x), y, offsets)
        self.assertEqual(old_value, value)
        self.assertEqual(old_gradient[1], 0.)
        self.assertEqual(old_hessian[1, 1], 16.)
        self.assertEqual(old_hessian[0, 1], 0.)

    def test_zero_coefficient_returns_exact_raw_and_invalid_inputs_fail(self):
        raw = [.15, .251, .81]
        offsets = [math.log(value / (1 - value)) for value in raw]
        self.assertEqual(candidate.candidate_probabilities(0., [1., -.2, 2.], offsets, raw_probabilities=raw), raw)
        with self.assertRaisesRegex(ValueError, "match frozen"):
            candidate.candidate_probabilities(0., [1., -.2, 2.], [0., 0., 0.], raw_probabilities=raw)
        for invalid in ([math.nan], [], [[1.]]):
            with self.assertRaises(ValueError):
                candidate.fit_single_offset(invalid, [1], [0.])

    def test_synthetic_four_fits_frozen_controls_and_deterministic_solver(self):
        rows, folds, controls, states = synthetic_problem()
        original = candidate.fit_single_offset
        with mock.patch.object(candidate, "fit_single_offset", wraps=original) as fit, \
                mock.patch.object(candidate.identity, "fit_identity_anchored", side_effect=AssertionError("no control refit")):
            predictions, reports = candidate._fit_and_predict(rows, folds, controls, states,
                candidate.freshness_features, candidate.ARM_CANDIDATE)
        self.assertEqual(fit.call_count, 4)
        self.assertEqual(len(predictions), 20)
        self.assertEqual({item["row"].key for item in predictions}, set(controls))
        self.assertTrue(all(item["optimizer"]["unused_zero_column_coefficient"] == 0 for item in reports))
        first, report = original([1., -1.] * 10, [1., 0.] * 10, [0.] * 20)
        self.assertEqual((first, report), original([1., -1.] * 10, [1., 0.] * 10, [0.] * 20))
        with mock.patch.object(candidate.scaffold, "MAX_ITERATIONS", 0), self.assertRaisesRegex(RuntimeError, "convergence"):
            original([1., -1.], [1., 0.], [0., 0.])

    def test_missing_control_or_receipt_and_future_label_fail_closed(self):
        rows, folds, controls, states = synthetic_problem()
        missing = dict(controls)
        missing.pop(next(iter(missing)))
        with self.assertRaisesRegex(ValueError, "frozen v0"):
            candidate._fit_and_predict(rows, folds, missing, states, candidate.freshness_features, candidate.ARM_CANDIDATE)
        row = rows[0]
        altered = candidate.base.InGameRow(row.game_id, row.game_date, row.game_week,
            {**row.trusted, "outcome_available_ms": rows[-1].trusted["cutoff_ms"]}, row.market_features, row.state_features, row.source_receipt)
        with self.assertRaisesRegex(ValueError, "strictly available"):
            candidate._fit_and_predict([altered, *rows[1:]], folds, controls, states,
                candidate.freshness_features, candidate.ARM_CANDIDATE)
        with self.assertRaisesRegex(ValueError, "incomplete"):
            candidate.freshness_features([candidate.base.InGameRow(row.game_id, row.game_date, row.game_week,
                row.trusted, row.market_features, row.state_features, {})], rows[22:], states={})

    def test_contract_and_source_drift_rejected_before_fit(self):
        with mock.patch.object(candidate, "_sha256", return_value="0" * 64), \
                mock.patch.object(candidate, "fit_single_offset", side_effect=AssertionError("no fit")):
            with self.assertRaisesRegex(ValueError, "hash-changed"):
                candidate.require_dependencies(candidate.TASK_ID)

    def test_failure_artifact_preserved_and_output_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "attempt"
            with mock.patch.object(candidate.base, "_validate_roots"), \
                    mock.patch.object(candidate, "require_dependencies", side_effect=ValueError("source drift")):
                with self.assertRaisesRegex(ValueError, "source drift"):
                    candidate.run(Path(directory) / "source", output, allow_test_paths=True)
            self.assertEqual(candidate.settlement._strict_json(output / "failure.json")["error"], "source drift")
            with mock.patch.object(candidate.base, "_validate_roots"), self.assertRaises(FileExistsError):
                candidate.run(Path(directory) / "source", output, allow_test_paths=True)

    def test_complete_synthetic_run_has_exact87_predictions_and_hash_bound_artifacts(self):
        from contextlib import ExitStack
        rows, folds, _, states = synthetic_problem()
        # Exact frozen population/fold sizes, but all fields and labels are synthetic.
        per_date = [5] * 20 + [3] * 2 + [6, 5, 5, 5, 5] + [4, 3, 3, 3, 3] + [6, 6, 6, 5, 5] + [4, 4, 3, 3, 3]
        expanded, expanded_states, cohort, controls = [], {}, [], {}
        for template, count in zip(rows, per_date, strict=True):
            for ordinal in range(count):
                game_id = f"{template.game_id}-{ordinal}"
                trusted = {**template.trusted, "event_id": game_id, "market_id": f"market-{game_id}"}
                receipt = {**template.source_receipt, "game_id": game_id}
                row = candidate.base.InGameRow(game_id, template.game_date, template.game_week,
                    trusted, template.market_features, template.state_features, receipt)
                expanded.append(row)
                expanded_states[game_id] = {**states[template.game_id], "game_id": game_id}
                cohort.append({"game_id": game_id, "game_date": row.game_date})
        expanded.sort(key=lambda row: row.key)
        by_game = {row.game_id: row for row in expanded}
        for game_id, reason in candidate.identity.EXPECTED_EXCLUSIONS:
            cohort.append({"game_id": game_id, "game_date": rows[-1].game_date, "exclusion": reason})
            expanded_states[game_id] = {"game_id": game_id}
        for fold in folds:
            for row in expanded:
                if row.game_date in fold["check_dates"]:
                    p = row.trusted["market_probability"]
                    controls[row.key] = {"fold": fold["fold"], "game_id": row.game_id,
                        "game_date": row.game_date, "game_week": row.game_week,
                        "outcome": row.trusted["outcome"], candidate.ARM_RAW: p,
                        candidate.ARM_ORDINARY: p + .01, candidate.ARM_PARENT: p - .01}
        ordered_checks = [row for fold in folds for row in sorted(
            [row for row in expanded if row.game_date in fold["check_dates"]], key=lambda row: row.key)]
        expected_hash = candidate._digest([list(row.key) for row in ordered_checks])
        frozen = {"hashes": {}, "folds": folds, "anchors": list(expanded_states.values()),
            "receipts": {"pbp_receipts": [], "materialized_receipts": [row.source_receipt for row in expanded]}}
        contract = candidate.settlement._strict_json(candidate.CONTRACT)
        recipe = next(item for item in contract["candidates"] if item["candidate_id"] == candidate.TASK_ID)
        def materialize(source, item, state):
            if "exclusion" in item:
                raise candidate.settlement.EventExclusion(item["exclusion"], "synthetic frozen exclusion")
            return by_game[item["game_id"]]
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "source", Path(directory) / "attempt"
            source.mkdir()
            candidate.base._atomic_json(source / "manifest.json", {"synthetic": True})
            candidate.base._atomic_json(source / "cohort.csv", {"synthetic": True})
            with ExitStack() as stack:
                for owner, name, kwargs in (
                    (candidate.base, "_validate_roots", {"return_value": None}),
                    (candidate, "require_dependencies", {"return_value": (contract, recipe)}),
                    (candidate.frozen_v0, "_validate_v0_artifact", {"return_value": frozen}),
                    (candidate.identity, "_frozen_controls", {"return_value": controls}),
                    (candidate.base, "_validate_source", {"return_value": cohort}),
                    (candidate.base, "_validate_pbp_receipts", {"return_value": []}),
                    (candidate.base, "_load_dynamic_market", {"side_effect": materialize}),
                    (candidate.base, "_group_bootstrap", {"return_value": {"interval_95": [-.1, .1]}})):
                    stack.enter_context(mock.patch.object(owner, name, **kwargs))
                stack.enter_context(mock.patch.object(candidate.frozen_v0, "EXPECTED_CHECK_KEY_SHA256", expected_hash))
                manifest = candidate.run(source, output, allow_test_paths=True)
            self.assertTrue(manifest["complete"])
            self.assertEqual((manifest["source_events"], manifest["materialized_events"],
                manifest["excluded_events"], manifest["check_events"], manifest["model_fits"]), (195, 193, 2, 87, 4))
            for name, suffix in (("pre_score_lock", "json"), ("input_receipts", "json"),
                    ("exclusions", "json"), ("predictions", "csv"), ("scorecard", "json")):
                self.assertEqual(manifest[f"{name}_sha256"], candidate._sha256(output / f"{name}.{suffix}"))
            scorecard = candidate.settlement._strict_json(output / "scorecard.json")
            self.assertEqual([item["fit_events"] for item in scorecard["folds"]], [106, 132, 148, 176])
            self.assertEqual([item["check_events"] for item in scorecard["folds"]], [26, 16, 28, 17])
            self.assertFalse((output / "failure.json").exists())

    def test_scores_and_decision_are_frozen_scaffold_parity(self):
        rows, folds, controls, states = synthetic_problem()
        predictions, reports = candidate._fit_and_predict(rows, folds, controls, states,
            candidate.freshness_features, candidate.ARM_CANDIDATE)
        mapped = [{**item, candidate.scaffold.ARM_CANDIDATE: item[candidate.ARM_CANDIDATE]} for item in predictions]
        expected = candidate.scaffold._aggregate(mapped)
        observed = candidate._aggregate(predictions, candidate.ARM_CANDIDATE)
        self.assertEqual(observed[candidate.ARM_CANDIDATE], expected[candidate.scaffold.ARM_CANDIDATE])
        calls = []
        def bootstrap(records, group, value, *, seed, replicates):
            calls.append((group, seed, replicates))
            return {"interval_95": [-.1, .1]}
        with mock.patch.object(candidate.base, "_group_bootstrap", side_effect=bootstrap):
            paired = candidate._paired_evidence(predictions, candidate.ARM_CANDIDATE)
        self.assertEqual(len(calls), 12)
        self.assertTrue(all(item[1:] == (20260929, 10000) for item in calls))
        mapped_folds = [{**item, "arms": {**item["arms"], candidate.scaffold.ARM_CANDIDATE:
            item["arms"][candidate.ARM_CANDIDATE]}} for item in reports]
        self.assertEqual(candidate.decision(observed, reports, paired, candidate.ARM_CANDIDATE),
            candidate.scaffold.decision(expected, mapped_folds, paired))


if __name__ == "__main__":
    unittest.main()
