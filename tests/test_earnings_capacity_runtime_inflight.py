"""Independent CP4c sole-reservation checks on owned activated temp ledgers."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from edgar_forecast_budget import BudgetStop, PilotBudget
from edgar_forecast_full_budget import FullBudget, MODELS, activate
from earnings_night_budget import NightBudget, history_snapshot, utc_epoch


DEADLINE = "2026-10-15T00:00:00Z"
DEFAULT_CAP = 20_000_000_000


class StringSubclass(str):
    pass


class IntegerSubclass(int):
    pass


class EqualKnownModel:
    def __eq__(self, other):
        return other in MODELS


class CapacityRuntimeInflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cp4-inflight-test-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "owned-sole.sqlite3"
        prior = PilotBudget(self.path)
        try:
            prior.reserve("prior", MODELS[0], 4_000_000_000)
            prior.settle("prior", 3_000_000_000)
        finally:
            prior.close()
        activate(self.path, "c" * 64, "d" * 40)
        self.baseline = self.snapshot()
        self.wall = utc_epoch(DEADLINE) - 1000
        self.mono = 100.0

    def snapshot(self):
        budget = FullBudget(self.path)
        try:
            return history_snapshot(budget.db)
        finally:
            budget.close()

    def open_budget(self, cap=1000, **extra):
        kwargs = dict(baseline=self.baseline, deadline_utc=DEADLINE,
                      additional_cap_nano_usd=cap,
                      clock=lambda: self.wall, monotonic=lambda: self.mono)
        kwargs.update(extra)
        budget = NightBudget(self.path, **kwargs)
        self.addCleanup(budget.close)
        return budget

    def state(self, budget):
        # WAL contains durable data; SHM is lock coordination, not ledger data.
        data_paths = (self.path, Path(str(self.path) + "-wal"))
        return {
            "dump": tuple(budget.db.iterdump()),
            "history": history_snapshot(budget.db),
            "data_bytes": {path.name: path.read_bytes() for path in data_paths if path.exists()},
            "total_changes": budget.db.total_changes,
        }

    def assert_check_unchanged(self, budget, request_id="own", model=MODELS[1], amount=100,
                               error=None):
        before = self.state(budget)
        if error is None:
            budget.check_reserved(request_id, model, amount)
        else:
            with self.assertRaises(error):
                budget.check_reserved(request_id, model, amount)
        self.assertFalse(budget.db.in_transaction)
        self.assertEqual(self.state(budget), before)

    def insert_settled(self, budget, request_id, model, charge):
        budget.db.execute("INSERT INTO requests VALUES (?,?,?,?,'settled')",
                          (request_id, model, charge, charge))

    def append_history(self, request_id, model, charge):
        budget = FullBudget(self.path)
        try:
            budget.reserve(request_id, model, charge)
            budget.settle(request_id, charge)
            self.baseline = history_snapshot(budget.db)
        finally:
            budget.close()

    def test_exact_sole_loan_is_read_only_across_handles_and_all_known_models(self):
        first = self.open_budget()
        second = self.open_budget()
        for index, model in enumerate(MODELS):
            request_id = f"own-{index}"
            first.reserve(request_id, model, 100)
            with self.subTest(model=model):
                for handle in (first, second):
                    self.assert_check_unchanged(handle, request_id, model)
                    self.assert_check_unchanged(handle, request_id, model)
            first.settle(request_id, 100)
        self.assertEqual(history_snapshot(first.db, self.baseline["max_rowid"]), self.baseline)

    def test_checker_does_not_unblock_active_or_create_another_reservation(self):
        budget = self.open_budget()
        budget.reserve("own", MODELS[1], 100)
        self.assert_check_unchanged(budget)
        before = self.state(budget)
        with self.assertRaises(BudgetStop):
            budget.active()
        with self.assertRaises(BudgetStop):
            budget.reserve("second", MODELS[2], 1)
        self.assertEqual(self.state(budget), before)
        self.assertEqual(budget.db.execute("SELECT blocked FROM config WHERE id=1").fetchone(), (0,))
        self.assertTrue(budget.summary()["blocked"])
        self.assertEqual(budget.summary()["unresolved_reserved_usd"], 100 / 1e9)

    def test_missing_or_wrong_exact_tuple_rejects_without_new_row(self):
        budget = self.open_budget()
        self.assert_check_unchanged(budget, error=BudgetStop)
        budget.reserve("own", MODELS[1], 100)
        wrong = (("foreign", MODELS[1], 100), ("own", MODELS[2], 100),
                 ("own", MODELS[1], 99), ("own", MODELS[1], 101))
        for request_id, model, amount in wrong:
            with self.subTest(request_id=request_id, model=model, amount=amount):
                self.assert_check_unchanged(budget, request_id, model, amount, BudgetStop)

    def test_malformed_builtin_subclass_and_equality_object_inputs_fail_closed(self):
        budget = self.open_budget()
        budget.reserve("own", MODELS[1], 100)
        invalid_ids = ("", None, 1, True, b"own", [], {}, StringSubclass("own"))
        invalid_models = ("", "unknown-model", None, 1, True, b"known", [], {},
                          StringSubclass(MODELS[1]), EqualKnownModel())
        invalid_amounts = (0, -1, None, True, False, 100.0, "100", [], {},
                           IntegerSubclass(100), float("nan"), float("inf"))
        for request_id in invalid_ids:
            with self.subTest(field="id", value=repr(request_id)):
                self.assert_check_unchanged(budget, request_id=request_id, error=ValueError)
        for model in invalid_models:
            with self.subTest(field="model", value=repr(model)):
                self.assert_check_unchanged(budget, model=model, error=ValueError)
        for amount in invalid_amounts:
            with self.subTest(field="amount", value=repr(amount)):
                self.assert_check_unchanged(budget, amount=amount, error=ValueError)

    def test_another_pending_or_uncertain_row_is_never_bypassed(self):
        budget = self.open_budget()
        budget.reserve("own", MODELS[1], 100)
        budget.db.execute("INSERT INTO requests VALUES ('foreign',?,1,0,'reserved')", (MODELS[2],))
        self.assert_check_unchanged(budget, error=BudgetStop)
        budget.db.execute("UPDATE requests SET status='uncertain' WHERE id='foreign'")
        self.assert_check_unchanged(budget, error=BudgetStop)
        self.assertEqual(budget.db.execute("SELECT COUNT(*) FROM requests").fetchone(), (3,))

    def test_uncertain_own_liability_remains_blocked_and_unreconciled(self):
        budget = self.open_budget()
        budget.reserve("own", MODELS[1], 100)
        budget.uncertain("own")
        self.assert_check_unchanged(budget, error=BudgetStop)
        self.assertEqual(budget.db.execute("SELECT reserved,charged,status FROM requests WHERE id='own'")
                         .fetchone(), (100, 0, "uncertain"))
        self.assertEqual(budget.db.execute("SELECT COUNT(*) FROM reconciliations").fetchone(), (0,))
        self.assertEqual(budget.db.execute("SELECT blocked FROM config WHERE id=1").fetchone(), (1,))

    def test_nonreserved_or_charged_own_row_cannot_be_treated_as_current_loan(self):
        budget = self.open_budget()
        budget.reserve("own", MODELS[1], 100)
        for status, charged in (("settled", 100), ("settled_upper_bound", 100),
                                ("uncertain", 0), ("unknown-status", 0), ("reserved", 1)):
            budget.db.execute("UPDATE requests SET status=?,charged=? WHERE id='own'", (status, charged))
            with self.subTest(status=status, charged=charged):
                self.assert_check_unchanged(budget, error=BudgetStop)

    def test_recorded_overcharge_is_preserved_with_stop_flag(self):
        budget = self.open_budget()
        budget.reserve("own", MODELS[1], 100)
        with self.assertRaises(BudgetStop):
            budget.settle("own", 101)
        self.assert_check_unchanged(budget, error=BudgetStop)
        self.assertEqual(budget.db.execute("SELECT reserved,charged,status FROM requests WHERE id='own'")
                         .fetchone(), (100, 101, "settled"))
        self.assertEqual(budget.db.execute("SELECT blocked FROM config WHERE id=1").fetchone(), (1,))

    def test_config_narrowing_widening_or_blocking_is_rejected_without_repair(self):
        budget = self.open_budget()
        budget.reserve("own", MODELS[1], 100)
        variants = ((200_000_000_001, 100_000_000_000, 0),
                    (199_999_999_999, 100_000_000_000, 0),
                    (200_000_000_000, 100_000_000_001, 0),
                    (200_000_000_000, 99_999_999_999, 0),
                    (200_000_000_000, 100_000_000_000, 1))
        for config in variants:
            budget.db.execute("UPDATE config SET cap=?,model_cap=?,blocked=? WHERE id=1", config)
            with self.subTest(config=config):
                self.assert_check_unchanged(budget, error=BudgetStop)
        budget.db.execute("DELETE FROM config WHERE id=1")
        self.assert_check_unchanged(budget, error=BudgetStop)

    def test_frozen_prior_history_drift_is_rejected_without_refund_or_rewrite(self):
        budget = self.open_budget()
        budget.reserve("own", MODELS[1], 100)
        budget.db.execute("UPDATE requests SET charged=0 WHERE id='prior'")
        self.assert_check_unchanged(budget, error=BudgetStop)
        budget.db.execute("UPDATE requests SET charged=3000000000,model=? WHERE id='prior'", (MODELS[2],))
        self.assert_check_unchanged(budget, error=BudgetStop)

    def test_expired_original_wall_clock_rejects_sole_reserved_loan(self):
        budget = self.open_budget()
        budget.reserve("own", MODELS[1], 100)
        self.wall = utc_epoch(DEADLINE)
        self.assert_check_unchanged(budget, error=BudgetStop)

    def test_captured_monotonic_expiry_still_rejects_after_wall_rollback(self):
        budget = self.open_budget(captured_deadline=101)
        budget.reserve("own", MODELS[1], 100)
        self.wall -= 3600
        self.mono = 101
        self.assert_check_unchanged(budget, error=BudgetStop)

    def test_global_cap_includes_the_current_loan_even_though_its_charge_is_zero(self):
        self.append_history("near-model-cap", MODELS[0], 96_999_999_900)
        self.append_history("near-global-cap", MODELS[1], 100_000_000_000)
        budget = self.open_budget()
        budget.reserve("own", MODELS[2], 100)
        self.assert_check_unchanged(budget, model=MODELS[2])
        self.insert_settled(budget, "late-global-charge", MODELS[0], 1)
        self.assertEqual(history_snapshot(budget.db, self.baseline["max_rowid"]), self.baseline)
        self.assert_check_unchanged(budget, model=MODELS[2], error=BudgetStop)

    def test_model_cap_includes_the_current_loan_even_though_its_charge_is_zero(self):
        self.append_history("near-model-cap", MODELS[1], 99_999_999_900)
        budget = self.open_budget()
        budget.reserve("own", MODELS[1], 100)
        self.assert_check_unchanged(budget)
        self.insert_settled(budget, "late-model-charge", MODELS[1], 1)
        self.assertEqual(history_snapshot(budget.db, self.baseline["max_rowid"]), self.baseline)
        self.assert_check_unchanged(budget, error=BudgetStop)

    def test_lower_additional_cap_counts_settled_new_charges_and_current_loan(self):
        budget = self.open_budget(10)
        budget.reserve("earlier", MODELS[0], 4)
        budget.settle("earlier", 4)
        budget.reserve("own", MODELS[1], 6)
        self.assert_check_unchanged(budget, amount=6)
        self.insert_settled(budget, "late-additional-charge", MODELS[2], 1)
        self.assertEqual(history_snapshot(budget.db, self.baseline["max_rowid"]), self.baseline)
        self.assert_check_unchanged(budget, amount=6, error=BudgetStop)

    def test_smaller_handle_cannot_validate_loan_over_its_explicit_ceiling(self):
        original = self.open_budget(DEFAULT_CAP)
        smaller = self.open_budget(5_000_000_000)
        original.reserve("own", MODELS[1], 6_000_000_000)
        self.assert_check_unchanged(original, amount=6_000_000_000)
        self.assert_check_unchanged(smaller, amount=6_000_000_000, error=BudgetStop)

    def test_one_nano_exact_lower_boundary_accepts_only_the_matching_loan(self):
        budget = self.open_budget(1)
        budget.reserve("own", MODELS[1], 1)
        self.assert_check_unchanged(budget, amount=1)
        self.assert_check_unchanged(budget, amount=2, error=BudgetStop)
        self.assertEqual(budget.summary()["night_cap_usd"], 1 / 1e9)

    def test_default_twenty_dollar_loan_preserves_legacy_summary_without_settlement(self):
        budget = NightBudget(self.path, baseline=self.baseline, deadline_utc=DEADLINE,
                             clock=lambda: self.wall, monotonic=lambda: self.mono)
        self.addCleanup(budget.close)
        budget.reserve("own", MODELS[1], DEFAULT_CAP)
        before = budget.summary()
        self.assert_check_unchanged(budget, amount=DEFAULT_CAP)
        self.assertEqual(budget.summary(), before)
        self.assertIs(type(before["night_cap_usd"]), int)
        self.assertEqual(before["night_cap_usd"], 20)
        self.assertEqual(before["cap_usd"], 200)
        self.assertEqual(before["model_cap_usd"], 100)
        self.assertEqual(before["charged_upper_bound_usd"], 3)
        self.assertEqual(before["night_charged_upper_bound_usd"], 0)
        self.assertEqual(before["unresolved_reserved_usd"], 20)
        self.assertTrue(before["blocked"])


if __name__ == "__main__":
    unittest.main()
