import copy
import json
import tempfile
import unittest
from pathlib import Path

from learner import fit_predict
from market_rsi import Budget, Journal, Market, Round, audit_rows, file_hash, fresh_json, metrics
from smoke import fixture_rows, specs


class FrameworkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.rows = fixture_rows()
        self.data = self.root / "data.json"
        fresh_json(self.data, self.rows)
        self.protocol, self.plans = specs(dict(steps=10, learning_rate=.1, l2=.01))

    def make_round(self):
        return Round.create(self.root / "r1", self.protocol, self.plans, self.data)

    def commit(self, r):
        return r.commit_forecasts(self.data, {a: {p["id"]: .6 for p in self.plans}
                                             for a in self.protocol["actors"]}, [], "forecaster_a")

    def test_chronological_game_audit(self):
        result = audit_rows(self.rows, self.protocol["features"], 250)
        self.assertEqual(result["train"]["games"], 4)

    def test_future_feature_rejected(self):
        self.rows[0]["feature_available_ms"] += 1
        with self.assertRaises(ValueError):
            audit_rows(self.rows, self.protocol["features"], 250)

    def test_game_overlap_rejected(self):
        self.rows[-1]["game_id"] = self.rows[0]["game_id"]
        with self.assertRaises(ValueError):
            audit_rows(self.rows, self.protocol["features"], 250)

    def test_duplicate_rows_rejected(self):
        with self.assertRaises(ValueError):
            audit_rows(self.rows + [self.rows[0]], self.protocol["features"], 250)

    def test_wrong_date_rejected(self):
        self.rows[0]["date"] = "2026-01-02"
        with self.assertRaises(ValueError):
            audit_rows(self.rows, self.protocol["features"], 250)

    def test_label_boundary_overlap_rejected(self):
        self.rows[0]["label_end_ms"] = self.rows[-1]["decision_ms"]
        with self.assertRaises(ValueError):
            audit_rows(self.rows, self.protocol["features"], 250)

    def test_metric_exact_rows_required(self):
        with self.assertRaises(ValueError):
            metrics(self.rows, {})

    def test_metric_ties_and_fixed_alert_budget(self):
        s = metrics(self.rows, {r["row_id"]: .5 for r in self.rows})
        self.assertEqual(s["auc"], .5)
        self.assertEqual(s["alerts"], 42)

    def test_metric_nan_rejected(self):
        with self.assertRaises(ValueError):
            metrics(self.rows, {r["row_id"]: float("nan") for r in self.rows})

    def test_no_forecast_no_evaluation(self):
        r = self.make_round()
        with self.assertRaises(FileNotFoundError):
            r.evaluate(self.data, fit_predict)

    def test_duplicate_round_rejected(self):
        self.make_round()
        with self.assertRaises(FileExistsError):
            self.make_round()

    def test_duplicate_forecast_rejected(self):
        r = self.make_round()
        self.commit(r)
        with self.assertRaises(FileExistsError):
            self.commit(r)

    def test_input_mutation_rejected(self):
        r = self.make_round()
        self.data.write_text("[]")
        with self.assertRaises(ValueError):
            self.commit(r)

    def test_forecast_mutation_rejected(self):
        r = self.make_round()
        self.commit(r)
        f = r.root / "forecasts.json"
        data = json.loads(f.read_text())
        data["forecasts"]["forecaster_a"]["more_steps"] = .9
        f.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            r.evaluate(self.data, fit_predict)

    def test_multi_stage_change_rejected(self):
        self.plans[0]["candidate_components"]["objective"] = "changed"
        with self.assertRaises(ValueError):
            self.make_round()

    def test_successful_end_to_end_and_no_rerun(self):
        r = self.make_round()
        self.commit(r)
        result = r.evaluate(self.data, fit_predict)
        self.assertEqual(len(result["candidates"]), 4)
        self.assertFalse(result["pnl_claim"])
        self.assertEqual(result["choices"]["market"], "parent")
        self.assertEqual(r.journal.read()[-1]["event"], "evaluation_completed")
        self.assertEqual(file_hash(r.root / "source/learner.py"), self.protocol["evaluator_sha256"])
        self.assertEqual(len(result["candidates"]["parent"]["by_date"]), 1)
        with self.assertRaises(ValueError):
            r.evaluate(self.data, fit_predict)

    def test_wrong_adapter_source_rejected(self):
        self.protocol["evaluator_sha256"] = "a" * 64
        with self.assertRaises(ValueError):
            self.make_round()

    def test_failed_candidate_stays_unknown(self):
        self.plans[0]["config"]["steps"] = -1
        r = self.make_round()
        self.commit(r)
        result = r.evaluate(self.data, fit_predict)
        self.assertIsNone(result["outcomes"]["more_steps"])
        self.assertIsNone(result["forecast_brier"]["forecaster_a"]["more_steps"])
        self.assertTrue(all(x is None for x in result["selection_regret_brier"].values()))
        self.assertEqual(result["candidates"]["smaller_update"]["status"], "completed")

    def test_journal_tampering_detected(self):
        r = self.make_round()
        data = json.loads(r.journal.path.read_text())
        data["event"] = "edited"
        r.journal.path.write_text(json.dumps(data) + "\n")
        with self.assertRaises(ValueError):
            r.journal.read()

    def test_market_stake_and_identity_bounds(self):
        m = Market(["candidate"], ["a", "b"])
        with self.assertRaises(ValueError):
            m.buy("invented", "candidate", "yes", 1)
        with self.assertRaises(ValueError):
            m.buy("a", "candidate", "yes", 1000)
        m.buy("a", "candidate", "yes", 1)
        self.assertGreater(m.price("candidate"), .5)
        self.assertLess(m.cash["a"], 10)

    def test_unresolved_market_not_a_loss(self):
        m = Market(["candidate"], ["a", "b"])
        m.buy("a", "candidate", "yes", 1)
        result = m.settle({"candidate": None})
        self.assertEqual(result["realized_virtual_pnl"]["a"], 0)
        self.assertEqual(len(result["unresolved_trades"]), 1)

    def test_reservation_is_not_spend(self):
        b = Budget(200)
        b.reserve("job", 150)
        self.assertEqual(b.snapshot()["actual"], "0")
        b.reconcile("job", actual=15, estimate=14)
        self.assertEqual(b.snapshot()["available"], "185")
        self.assertEqual(b.snapshot()["reserved"], "0")

    def test_unknown_cost_remains_reserved(self):
        b = Budget(200)
        b.reserve("job", 150)
        b.reconcile("job", estimate=15)
        self.assertEqual(b.snapshot()["available"], "50")
        with self.assertRaises(ValueError):
            b.reserve("other", 51)

    def test_hard_cap_no_double_charge(self):
        b = Budget(0)
        with self.assertRaises(ValueError):
            b.reserve("paid", .01)
        b.reserve("local", 0)
        b.reconcile("local", actual=0)
        with self.assertRaises(ValueError):
            b.reconcile("local", actual=0)

    def test_inherited_checkpoint_has_actual_steps(self):
        train = [r for r in self.rows if r["split"] == "train"]
        evaluation = [r for r in self.rows if r["split"] == "dev"]
        _, first = fit_predict(dict(steps=10), train, evaluation)
        _, second = fit_predict(dict(steps=3, initial_checkpoint=first["checkpoint"]), train, evaluation)
        self.assertEqual(second["checkpoint"]["cumulative_optimizer_steps"], 13)
        _, frozen = fit_predict(dict(initial_checkpoint=first["checkpoint"], frozen_parent=True), train, evaluation)
        self.assertEqual(frozen["optimizer_steps"], 0)
        self.assertEqual(frozen["checkpoint"], first["checkpoint"])


if __name__ == "__main__":
    unittest.main()
