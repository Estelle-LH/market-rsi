import copy
import math
import unittest

from minimal_prediction_loop.probability_contract import (
    ProbabilityPolicy,
    build_candidate_views,
    validate_probability_rows,
    validate_public_probability_rows,
    validate_train_evaluation_rows,
)
from minimal_prediction_loop.proper_scoring import (
    ProperScoreSpec,
    bounded_log_loss,
    score_probability_forecasts,
)


DAY_MS = 86_400_000


def settlement_row(
    event_id="event-1",
    market_id="market-1",
    cutoff_ms=DAY_MS + 1_000,
    market_probability=0.4,
    outcome=1,
    *,
    feature_available_ms=None,
    outcome_available_ms=10 * DAY_MS,
):
    return {
        "event_id": event_id,
        "market_id": market_id,
        "cutoff_ms": cutoff_ms,
        "feature_available_ms": cutoff_ms if feature_available_ms is None else feature_available_ms,
        "market_probability": market_probability,
        "outcome_available_ms": outcome_available_ms,
        "outcome": outcome,
    }


def prediction(row, value):
    return {
        "event_id": row["event_id"],
        "market_id": row["market_id"],
        "cutoff_ms": row["cutoff_ms"],
        "probability": value,
    }


def raw_signal(row, value):
    return {
        "event_id": row["event_id"],
        "market_id": row["market_id"],
        "cutoff_ms": row["cutoff_ms"],
        "raw_signal": value,
    }


def evaluation_fixture():
    return [
        settlement_row("event-1", "market-1", DAY_MS + 1_000, 0.4, 1),
        settlement_row("event-1", "market-2", DAY_MS + 2_000, 0.6, 1),
        settlement_row("event-2", "market-3", 2 * DAY_MS + 1_000, 0.8, 0),
    ]


class ProbabilityRowContractTests(unittest.TestCase):
    def test_valid_rows_are_canonical_and_do_not_mutate_input(self):
        rows = [
            settlement_row("event-a", "market-2", 2 * DAY_MS, 0.7, 0),
            settlement_row("event-z", "market-1", DAY_MS, 0.4, 1),
        ]
        before = copy.deepcopy(rows)
        parsed = validate_probability_rows(rows)
        self.assertEqual([row.event_id for row in parsed], ["event-z", "event-a"])
        self.assertEqual([row.cutoff_ms for row in parsed], [DAY_MS, 2 * DAY_MS])
        self.assertEqual(rows, before)

    def test_exact_schema_and_conservative_identifiers_are_required(self):
        for change in (
            lambda row: row.update(extra="not frozen"),
            lambda row: row.pop("market_id"),
            lambda row: row.update(event_id="event with spaces"),
            lambda row: row.update(market_id="../market"),
            lambda row: row.update(event_id=""),
        ):
            row = settlement_row()
            change(row)
            with self.subTest(row=row), self.assertRaises(ValueError):
                validate_probability_rows([row])

    def test_future_features_known_outcomes_and_bad_timestamps_fail_closed(self):
        base = settlement_row()
        for field, value in (
            ("feature_available_ms", base["cutoff_ms"] + 1),
            ("outcome_available_ms", base["cutoff_ms"]),
            ("cutoff_ms", True),
            ("feature_available_ms", -1),
            ("outcome_available_ms", 1.5),
        ):
            row = {**base, field: value}
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                validate_probability_rows([row])

    def test_probability_epsilon_policy_rejects_endpoints_and_malformed_values(self):
        policy = ProbabilityPolicy(0.01)
        for value in (0.0, 1.0, 0.009, 0.991, float("nan"), float("inf"), True, "0.5"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_probability_rows(
                    [settlement_row(market_probability=value)], policy=policy
                )
        for value in (0.01, 0.5, 0.99):
            parsed = validate_probability_rows(
                [settlement_row(market_probability=value)], policy=policy
            )
            self.assertEqual(parsed[0].market_probability, value)

    def test_outcome_is_an_integer_bit_not_a_truthy_value(self):
        for value in (True, False, -1, 2, 0.0, "1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_probability_rows([settlement_row(outcome=value)])

    def test_duplicate_relabelled_and_inconsistent_resolution_rows_are_rejected(self):
        row = settlement_row()
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate_probability_rows([row, copy.deepcopy(row)])

        relabelled = settlement_row("event-2", row["market_id"], 2 * DAY_MS, 0.5, 0)
        with self.assertRaisesRegex(ValueError, "relabelled"):
            validate_probability_rows([row, relabelled])

        changed_resolution = settlement_row(
            row["event_id"], row["market_id"], row["cutoff_ms"] + 1, 0.5, 0
        )
        with self.assertRaisesRegex(ValueError, "inconsistent resolution"):
            validate_probability_rows([row, changed_resolution])

    def test_whole_event_split_and_training_label_availability_are_enforced(self):
        train = [settlement_row(
            "train-event", "train-market", DAY_MS, 0.5, 1,
            outcome_available_ms=2 * DAY_MS,
        )]
        evaluation = [settlement_row(
            "eval-event", "eval-market", 3 * DAY_MS, 0.5, 0,
            outcome_available_ms=5 * DAY_MS,
        )]
        validate_train_evaluation_rows(train, evaluation)

        overlapping_event = [{**evaluation[0], "event_id": "train-event"}]
        with self.assertRaisesRegex(ValueError, "same underlying event"):
            validate_train_evaluation_rows(train, overlapping_event)

        late_train = [{**train[0], "outcome_available_ms": evaluation[0]["cutoff_ms"]}]
        with self.assertRaisesRegex(ValueError, "training label"):
            validate_train_evaluation_rows(late_train, evaluation)

    def test_candidate_view_strips_future_outcome_and_public_schema_rejects_it(self):
        train = [settlement_row(
            "train-event", "train-market", DAY_MS, 0.5, 1,
            outcome_available_ms=2 * DAY_MS,
        )]
        evaluation = [settlement_row(
            "eval-event", "eval-market", 3 * DAY_MS, 0.5, 0,
            outcome_available_ms=5 * DAY_MS,
        )]
        views = build_candidate_views(train, evaluation)
        self.assertIn("outcome", views["train"][0])
        self.assertNotIn("outcome", views["evaluation"][0])
        self.assertNotIn("outcome_available_ms", views["evaluation"][0])
        validate_public_probability_rows(views["evaluation"])
        with self.assertRaisesRegex(ValueError, "label-free"):
            validate_public_probability_rows(evaluation)


class ProperScoringTests(unittest.TestCase):
    def setUp(self):
        self.rows = evaluation_fixture()
        self.candidate = [
            prediction(self.rows[0], 0.7),
            prediction(self.rows[1], 0.8),
            prediction(self.rows[2], 0.5),
        ]
        self.spec = ProperScoreSpec(
            probability_epsilon=0.01,
            reliability_bins=2,
            bootstrap_seed=7,
            bootstrap_replicates=100,
            date_block_days=1,
        )

    def score(self, **kwargs):
        return score_probability_forecasts(
            self.rows, self.candidate, spec=self.spec, **kwargs
        )

    def test_hand_calculated_equal_event_and_row_weighted_brier(self):
        score = self.score()
        primary = score["primary"]
        self.assertAlmostEqual(primary["equal_event_candidate_brier"], 0.1575)
        self.assertAlmostEqual(primary["equal_event_market_brier"], 0.45)
        self.assertAlmostEqual(
            primary["equal_event_candidate_minus_market_brier"], -0.2925
        )
        self.assertAlmostEqual(score["row_weighted"]["candidate_brier"], 0.38 / 3)
        self.assertAlmostEqual(score["row_weighted"]["market_brier"], 1.16 / 3)
        self.assertEqual(score["coverage"]["common_complete_fraction"], 1.0)
        self.assertTrue(score["coverage"]["identical_candidate_market_mask"])
        self.assertEqual(len(score["coverage"]["complete_mask_sha256"]), 64)
        self.assertEqual(score["aggregate_metrics"]["candidate_brier"],
                         primary["equal_event_candidate_brier"])
        self.assertEqual(score["aggregate_metrics"]["candidate_minus_market_brier"],
                         primary["equal_event_candidate_minus_market_brier"])

    def test_hand_calculated_equal_event_bounded_log_loss_and_policy(self):
        score = self.score()
        candidate_event_1 = (-math.log(0.7) - math.log(0.8)) / 2
        market_event_1 = (-math.log(0.4) - math.log(0.6)) / 2
        expected_candidate = (candidate_event_1 - math.log(0.5)) / 2
        expected_market = (market_event_1 - math.log(0.2)) / 2
        self.assertAlmostEqual(score["primary"]["equal_event_candidate_log_loss"], expected_candidate)
        self.assertAlmostEqual(score["primary"]["equal_event_market_log_loss"], expected_market)
        self.assertAlmostEqual(
            score["primary"]["equal_event_candidate_minus_market_log_loss"],
            expected_candidate - expected_market,
        )
        self.assertFalse(score["probability_policy"]["log_loss_clipping"])
        self.assertAlmostEqual(
            score["probability_policy"]["maximum_per_row_log_loss"], -math.log(0.01)
        )
        self.assertAlmostEqual(bounded_log_loss(0.01, 1, policy=ProbabilityPolicy(0.01)), -math.log(0.01))

    def test_calibration_reliability_breadth_concentration_and_paired_evidence(self):
        first = self.score()
        second = self.score()
        self.assertEqual(first, second)
        self.assertAlmostEqual(first["calibration"]["candidate"]["slope"], 25 / 7)
        self.assertAlmostEqual(first["calibration"]["candidate"]["intercept"], -12 / 7)
        self.assertEqual(first["reliability"]["candidate"]["bins"][0]["rows"], 0)
        self.assertEqual(first["reliability"]["candidate"]["bins"][1]["rows"], 3)
        self.assertEqual(first["breadth"]["events"], 2)
        self.assertEqual(first["breadth"]["utc_dates"], 2)
        self.assertEqual(first["breadth"]["markets"], 3)
        self.assertAlmostEqual(first["concentration"]["event_rows"]["top_1_row_share"], 2 / 3)
        self.assertEqual(first["paired_evidence"]["event_brier"]["units"], 2)
        self.assertEqual(first["paired_evidence"]["date_block_brier"]["units"], 2)
        self.assertEqual(len(first["paired_evidence"]["date_blocks"]), 2)
        self.assertFalse(first["inference_boundary"]["promotion_authorized"])

    def test_raw_signal_and_candidate_adjustment_incremental_diagnostics(self):
        signals = [
            raw_signal(self.rows[0], 1.0),
            raw_signal(self.rows[1], 2.0),
            raw_signal(self.rows[2], -1.0),
        ]
        diagnostics = self.score(raw_signal_records=signals)["incremental_diagnostics"]
        self.assertTrue(diagnostics["raw_signal_vs_market"]["available"])
        self.assertEqual(diagnostics["raw_signal_vs_market"]["rows"], 3)
        self.assertIn(
            "partial_pearson_with_outcome_controlling_market_probability",
            diagnostics["raw_signal_vs_market"],
        )
        self.assertTrue(diagnostics["candidate_adjustment_vs_market"]["available"])
        self.assertFalse(self.score()["incremental_diagnostics"]["raw_signal_vs_market"]["available"])

    def test_incomplete_extra_duplicate_and_mismatched_candidate_masks_fail(self):
        bad_candidates = [
            self.candidate[:-1],
            self.candidate + [prediction(settlement_row("event-x", "market-x"), 0.5)],
            self.candidate + [copy.deepcopy(self.candidate[0])],
            [{**self.candidate[0], "market_id": "another-market"}, *self.candidate[1:]],
        ]
        for candidate in bad_candidates:
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                score_probability_forecasts(self.rows, candidate, spec=self.spec)

    def test_bad_candidate_probabilities_fail_instead_of_being_clipped(self):
        for value in (0, 1, 0.009, 0.991, float("nan"), float("inf"), True, "0.5"):
            candidate = copy.deepcopy(self.candidate)
            candidate[0]["probability"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                score_probability_forecasts(self.rows, candidate, spec=self.spec)

    def test_raw_signal_requires_the_same_complete_mask_and_finite_values(self):
        complete = [raw_signal(row, index) for index, row in enumerate(self.rows)]
        for signals in (
            complete[:-1],
            complete + [copy.deepcopy(complete[0])],
            [{**complete[0], "raw_signal": float("nan")}, *complete[1:]],
        ):
            with self.subTest(signals=signals), self.assertRaises(ValueError):
                self.score(raw_signal_records=signals)

    def test_input_order_does_not_change_deterministic_score(self):
        forward = self.score(raw_signal_records=[raw_signal(row, i) for i, row in enumerate(self.rows)])
        reverse = score_probability_forecasts(
            list(reversed(self.rows)),
            list(reversed(self.candidate)),
            raw_signal_records=list(reversed([raw_signal(row, i) for i, row in enumerate(self.rows)])),
            spec=self.spec,
        )
        self.assertEqual(forward, reverse)

    def test_score_binds_trusted_rows_candidate_records_and_scorer_spec(self):
        original = self.score()
        changed_rows = copy.deepcopy(self.rows)
        for row in changed_rows[:2]:
            row["outcome"] = 0
            row["market_probability"] = 0.3
        changed = score_probability_forecasts(changed_rows, self.candidate, spec=self.spec)
        self.assertEqual(
            original["input_commitments"]["complete_mask_sha256"],
            changed["input_commitments"]["complete_mask_sha256"],
        )
        self.assertNotEqual(
            original["input_commitments"]["trusted_rows_sha256"],
            changed["input_commitments"]["trusted_rows_sha256"],
        )
        self.assertNotEqual(original["score_receipt_sha256"], changed["score_receipt_sha256"])

        changed_candidate = copy.deepcopy(self.candidate)
        changed_candidate[0]["probability"] = 0.45
        candidate_score = score_probability_forecasts(
            self.rows, changed_candidate, spec=self.spec
        )
        self.assertNotEqual(
            original["input_commitments"]["candidate_records_sha256"],
            candidate_score["input_commitments"]["candidate_records_sha256"],
        )

        changed_spec = score_probability_forecasts(
            self.rows,
            self.candidate,
            spec=ProperScoreSpec(
                probability_epsilon=0.01,
                reliability_bins=5,
                bootstrap_seed=17,
                bootstrap_replicates=100,
                date_block_days=2,
            ),
        )
        self.assertNotEqual(
            original["input_commitments"]["scorer_spec_sha256"],
            changed_spec["input_commitments"]["scorer_spec_sha256"],
        )

    def test_dense_event_does_not_dominate_equal_event_primary(self):
        dense_rows = [
            settlement_row("dense", "dense-market", DAY_MS + i, 0.5, 1)
            for i in range(1, 10)
        ]
        # Same market at multiple cutoffs must carry one consistent resolution.
        sparse = settlement_row("sparse", "sparse-market", 2 * DAY_MS, 0.9, 0)
        rows = dense_rows + [sparse]
        candidate = [prediction(row, 0.6 if row["event_id"] == "dense" else 0.1)
                     for row in rows]
        score = score_probability_forecasts(rows, candidate, spec=self.spec)
        dense_delta = (0.6 - 1) ** 2 - (0.5 - 1) ** 2
        sparse_delta = (0.1 - 0) ** 2 - (0.9 - 0) ** 2
        self.assertAlmostEqual(
            score["primary"]["equal_event_candidate_minus_market_brier"],
            (dense_delta + sparse_delta) / 2,
        )
        self.assertNotAlmostEqual(
            score["primary"]["equal_event_candidate_minus_market_brier"],
            score["row_weighted"]["candidate_minus_market_brier"],
        )


if __name__ == "__main__":
    unittest.main()
