import copy
import tempfile
import unittest
from pathlib import Path

from label_materializer import LabelBuilder, LabelPolicy
from market_scoring import (NumericScoreSpec, correlation, numeric_metrics, ranks,
                            read_predictions, score_pair)
from market_harbor import fixture_packet
from prediction_stream import PredictionJournal, fingerprint


def rows(day=1, movement=1000, market="m", game="g"):
    t = day * 86400000 + 1000
    builder = LabelBuilder(LabelPolicy(100, 10, 20, 20, 1000, 10000), {market: game}, ["a" * 64])
    def quote(when, line, delta=0):
        return dict(source_key=[0, line], receive_ms=when, sid=1, seq=line + 1, stream_epoch=0,
                    market_id=market, anchor_key=[0, 0], anchor_ms=t, quote_segment=0,
                    bid_1e4=4000 + delta, ask_1e4=5000 + delta, bid_size_1e2=1000, ask_size_1e2=2000)
    builder.accept(quote(t, 0))
    builder.accept(quote(t + 10, 1))
    return builder.accept(quote(t + 110, 2, movement))


def spec(**overrides):
    values = dict(target="mid_change", prediction_min=-1, prediction_max=1,
                  sessions=("1970-01-02",), evidence_class="synthetic",
                  bootstrap_seed=23, bootstrap_replicates=100, block_sessions=1)
    values.update(overrides)
    return NumericScoreSpec(**values)


class NumericScoringTests(unittest.TestCase):
    def test_exact_paired_scores_and_direction(self):
        data = rows()
        rid = data[0]["row_id"]
        result = score_pair(data, {rid: 0}, {rid: 0.1}, spec())
        self.assertAlmostEqual(result["row_weighted"]["baseline"]["mse"], .01)
        self.assertAlmostEqual(result["row_weighted"]["candidate"]["mse"], 0)
        self.assertAlmostEqual(result["equal_session_delta_mse"], -.01)
        self.assertIsNone(result["net_pnl"])
        self.assertFalse(result["scientific_admission"])
        self.assertFalse(result["promotion"])

    def test_unchanged_candidate_gets_zero_delta_not_progress(self):
        data = rows()
        predictions = {data[0]["row_id"]: 0}
        result = score_pair(data, predictions, predictions, spec())
        self.assertEqual(result["equal_session_delta_mse"], 0)
        self.assertEqual(result["fraction_sessions_lower_mse"], 0)

    def test_missing_or_extra_prediction_is_failure_not_smaller_intersection(self):
        data = rows()
        predictions = {data[0]["row_id"]: 0}
        for bad in ({}, dict(predictions, extra=0)):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                score_pair(data, predictions, bad, spec())

    def test_prediction_nonfinite_boolean_and_out_of_bounds_rejected(self):
        data = rows()
        rid = data[0]["row_id"]
        for p in (float("nan"), float("inf"), True, "0.1", 1.1, -1.1):
            with self.subTest(p=p), self.assertRaises(ValueError):
                score_pair(data, {rid: 0}, {rid: p}, spec())

    def test_recomputed_endpoint_label_rejects_tampering(self):
        data = rows()
        rid = data[0]["row_id"]
        data[0]["labels"]["mid_change"] = .9
        with self.assertRaises(ValueError):
            score_pair(data, {rid: 0}, {rid: .9}, spec())

    def test_gross_contra_side_target_is_not_mid_target_or_net_profit(self):
        data = rows()
        rid = data[0]["row_id"]
        yes = score_pair(data, {rid: 0}, {rid: 0}, spec(target="buy_yes_gross_price_change"))
        no = score_pair(data, {rid: 0}, {rid: 0}, spec(target="buy_no_gross_price_change"))
        self.assertAlmostEqual(yes["row_weighted"]["baseline"]["mean_target"], 0)
        self.assertAlmostEqual(no["row_weighted"]["baseline"]["mean_target"], -.2)
        self.assertIsNone(yes["net_pnl"])

    def test_missing_frozen_session_rejected(self):
        data = rows()
        predictions = {data[0]["row_id"]: 0}
        with self.assertRaises(ValueError):
            score_pair(data, predictions, predictions, spec(sessions=("1970-01-02", "1970-01-03")))

    def test_future_features_and_reversed_label_times_rejected(self):
        original = rows()
        rid = original[0]["row_id"]
        for key, value in (("feature_available_ms", original[0]["entry_ms"]),
                           ("label_end_ms", original[0]["entry_ms"]), ("label_available_ms", 1)):
            data = copy.deepcopy(original)
            data[0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                score_pair(data, {rid: 0}, {rid: 0}, spec())

    def test_duplicate_row_and_zero_depth_rejected(self):
        data = rows()
        predictions = {data[0]["row_id"]: 0}
        with self.assertRaises(ValueError):
            score_pair(data + data, predictions, predictions, spec())
        data[0]["runner_endpoints"]["exit_bid_size_1e2"] = 0
        with self.assertRaises(ValueError):
            score_pair(data, predictions, predictions, spec())

    def test_constancy_is_undefined_not_fake_zero_ic(self):
        m = numeric_metrics([0, 0, 0], [-.1, 0, .1])
        self.assertIsNone(m["pearson_ic"])
        self.assertIsNone(m["rank_ic"])
        self.assertIsNone(m["calibration_slope"])
        self.assertIsNone(m["calibration_intercept"])

    def test_rank_ties_and_calibration(self):
        self.assertEqual(ranks([5, 1, 5, 2]), [3.5, 1.0, 3.5, 2.0])
        m = numeric_metrics([-.2, 0, .2], [-.3, .1, .5])
        self.assertAlmostEqual(m["calibration_slope"], 2)
        self.assertAlmostEqual(m["calibration_intercept"], .1)
        self.assertAlmostEqual(m["pearson_ic"], 1)
        self.assertAlmostEqual(m["rank_ic"], 1)

    def test_scale_inflation_can_keep_ic_and_worsen_mse(self):
        y = [-.1, 0, .1]
        base, inflated = numeric_metrics(y, y), numeric_metrics([-.9, 0, .9], y)
        self.assertEqual(base["pearson_ic"], inflated["pearson_ic"])
        self.assertGreater(inflated["mse"], base["mse"])

    def test_equal_session_and_game_metrics_not_dominated_by_dense_day(self):
        data = rows(1, 1000, "a", "ga") + rows(1, 1000, "b", "gb") + rows(2, 2000, "c", "gc")
        baseline = {r["row_id"]: 0 for r in data}
        candidate = {r["row_id"]: .1 if r["game_id"] != "gc" else .5 for r in data}
        result = score_pair(data, baseline, candidate, spec(sessions=("1970-01-02", "1970-01-03")))
        self.assertAlmostEqual(result["equal_session_delta_mse"], .02)
        self.assertAlmostEqual(result["equal_game_delta_mse"], .01)
        self.assertEqual(result["fraction_sessions_lower_mse"], .5)
        self.assertAlmostEqual(result["fraction_games_lower_mse"], 2 / 3)

    def test_fewer_than_twenty_untouched_sessions_have_no_inference(self):
        data = rows()
        p = {data[0]["row_id"]: 0}
        result = score_pair(data, p, p, spec(evidence_class="untouched"))
        self.assertIsNone(result["interval"]["equal_session_delta_mse_95pct_circular_block"])

    def test_twenty_sessions_resample_dates_not_rows_and_no_automatic_promotion(self):
        data = sum([rows(d, 1000, f"m{d}", f"g{d}") for d in range(1, 21)], [])
        baseline = {r["row_id"]: 0 for r in data}
        candidate = {r["row_id"]: .1 for r in data}
        s = spec(sessions=tuple(f"1970-01-{d:02d}" for d in range(2, 22)), evidence_class="untouched", block_sessions=3)
        a = score_pair(data, baseline, candidate, s)
        b = score_pair(data, baseline, candidate, s)
        self.assertEqual(a, b)
        ci = a["interval"]["equal_session_delta_mse_95pct_circular_block"]
        self.assertAlmostEqual(ci[0], -.01)
        self.assertAlmostEqual(ci[1], -.01)
        self.assertFalse(a["promotion"])

    def test_previously_inspected_dates_never_become_promotion_evidence_by_count(self):
        data = sum([rows(d, 1000, f"m{d}", f"g{d}") for d in range(1, 21)], [])
        p = {r["row_id"]: 0 for r in data}
        s = spec(sessions=tuple(f"1970-01-{d:02d}" for d in range(2, 22)), evidence_class="diagnostic")
        result = score_pair(data, p, p, s)
        self.assertIsNone(result["interval"]["equal_session_delta_mse_95pct_circular_block"])

    def test_spec_rejects_unfrozen_sessions_and_unknown_target(self):
        for changes in ({"target": "settlement"}, {"sessions": ("1970-01-02", "1970-01-02")},
                        {"bootstrap_seed": True}, {"prediction_max": 5}, {"block_sessions": 2}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                spec(**changes)


class JournalReadbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "predictions"
        self.packet = fixture_packet()
        self.kw = dict(train=self.packet["train"], evaluation=self.packet["evaluation"], feature_names=["x"],
                       candidate_sha256="c" * 64, prediction_min=-1, prediction_max=1)
        self.j = PredictionJournal(self.root, train_sha256=fingerprint(self.packet["train"]),
            evaluation_sha256=fingerprint(self.packet["evaluation"]), candidate_sha256="c" * 64, expected_predictions=3)
        chain = "0" * 64
        for i, r in enumerate(self.packet["evaluation"]):
            body = dict(sequence=i, row_id=r["row_id"], prediction=r["features"]["x"],
                        feature_row_sha256=fingerprint(r), previous=chain)
            body["hash"] = fingerprint(body)
            self.j.commit(body)
            chain = body["hash"]
        self.j.finish()

    def tearDown(self):
        self.temp.cleanup()

    def test_valid_complete_readback(self):
        self.assertEqual(read_predictions(self.root, **self.kw), {"eval-0": -.25, "eval-1": 0, "eval-2": .25})

    def test_other_code_or_input_binding_rejected(self):
        for changed in ({"candidate_sha256": "d" * 64}, {"evaluation": self.packet["evaluation"][:-1]}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                read_predictions(self.root, **dict(self.kw, **changed))

    def test_truncated_journal_is_not_scored_on_survivors(self):
        path = self.root / "predictions.jsonl"
        original = path.read_bytes()
        path.write_bytes(original.splitlines(keepends=True)[0])
        with self.assertRaises(ValueError):
            read_predictions(self.root, **self.kw)

    def test_output_limits_reject_oversize_and_numeric_bounds(self):
        for changed in ({"max_bytes": 10}, {"prediction_max": .1}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                read_predictions(self.root, **dict(self.kw, **changed))


if __name__ == "__main__":
    unittest.main()
