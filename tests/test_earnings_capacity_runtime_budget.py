"""Independent CP4a checks against owned, explicitly activated temp ledgers."""
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from edgar_forecast_budget import BudgetStop, PilotBudget
from edgar_forecast_full_budget import FullBudget, MODELS, activate
from earnings_night_budget import NightBudget, history_snapshot, utc_epoch


DEADLINE = "2026-10-15T00:00:00Z"
DEFAULT_CAP = 20_000_000_000
OMITTED = object()


class IntegerSubclass(int):
    pass


class CapacityRuntimeBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cp4-budget-test-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "owned-sole.sqlite3"
        prior = PilotBudget(self.path)
        try:
            prior.reserve("prior", MODELS[0], 4_000_000_000)
            prior.settle("prior", 3_000_000_000)
        finally:
            prior.close()
        activate(self.path, "a" * 64, "b" * 40)
        self.baseline = self.snapshot()
        self.wall = utc_epoch(DEADLINE) - 1000
        self.mono = 100.0

    def snapshot(self):
        budget = FullBudget(self.path)
        try:
            return history_snapshot(budget.db)
        finally:
            budget.close()

    def open_budget(self, cap=OMITTED, **extra):
        kwargs = dict(baseline=self.baseline, deadline_utc=DEADLINE,
                      clock=lambda: self.wall, monotonic=lambda: self.mono)
        if cap is not OMITTED:
            kwargs["additional_cap_nano_usd"] = cap
        kwargs.update(extra)
        budget = NightBudget(self.path, **kwargs)
        self.addCleanup(budget.close)
        return budget

    def rows(self, budget):
        return budget.db.execute(
            "SELECT id,model,reserved,charged,status FROM requests ORDER BY rowid"
        ).fetchall()

    def assert_prior_preserved(self, budget):
        self.assertEqual(history_snapshot(budget.db, self.baseline["max_rowid"]), self.baseline)
        self.assertEqual(budget.db.execute("SELECT cap,model_cap FROM config WHERE id=1").fetchone(),
                         (200_000_000_000, 100_000_000_000))

    def append_history(self, request_id, model, charge):
        budget = FullBudget(self.path)
        try:
            budget.reserve(request_id, model, charge)
            budget.settle(request_id, charge)
            self.baseline = history_snapshot(budget.db)
        finally:
            budget.close()

    def test_omitted_and_explicit_default_preserve_exact_legacy_summary_and_text(self):
        default = self.open_budget()
        explicit = self.open_budget(DEFAULT_CAP)
        expected = {
            "cap_usd": 200,
            "model_cap_usd": 100.0,
            "charged_upper_bound_usd": 3.0,
            "unresolved_reserved_usd": 0.0,
            "generation_requests_reserved": 1,
            "blocked": False,
            "allocation": "explicit_full_openai_batch_prior_charges_included",
            "night_cap_usd": 20,
            "night_charged_upper_bound_usd": 0.0,
            "prior_history_sha256": self.baseline["rows_sha256"],
            "deadline_epoch": utc_epoch(DEADLINE),
        }
        self.assertEqual(default.summary(), expected)
        self.assertEqual(explicit.summary(), expected)
        self.assertIs(type(default.summary()["night_cap_usd"]), int)
        self.assertIs(type(explicit.summary()["night_cap_usd"]), int)
        default.reserve("legacy-20", MODELS[1], DEFAULT_CAP)
        default.settle("legacy-20", DEFAULT_CAP)
        for handle in (default, explicit):
            with self.subTest(handle=handle), self.assertRaises(BudgetStop) as stopped:
                handle.reserve("legacy-over", MODELS[2], 1)
            self.assertEqual(str(stopped.exception), "Additional overnight USD20 ceiling")
            self.assertEqual(handle.summary()["night_charged_upper_bound_usd"], 20.0)
            self.assert_prior_preserved(handle)

    def test_one_nano_lower_boundary_is_usable_and_reported(self):
        budget = self.open_budget(1)
        self.assertEqual(budget.summary()["night_cap_usd"], 1 / 1e9)
        budget.reserve("one-nano", MODELS[2], 1)
        budget.settle("one-nano", 1)
        before = self.rows(budget)
        with self.assertRaises(BudgetStop):
            budget.reserve("second-nano", MODELS[1], 1)
        self.assertEqual(self.rows(budget), before)
        self.assert_prior_preserved(budget)

    def test_fractional_dollar_lower_cap_accumulates_across_models_and_handles(self):
        first = self.open_budget(2_500_000_000)
        second = self.open_budget(2_500_000_000)
        first.reserve("controller", MODELS[0], 1_500_000_000)
        first.settle("controller", 1_000_000_000)
        second.reserve("author", MODELS[1], 1_500_000_000)
        second.settle("author", 1_500_000_000)
        before = self.rows(first)
        for handle in (first, second):
            with self.subTest(handle=handle):
                self.assertEqual(handle.summary()["night_cap_usd"], 2.5)
                self.assertEqual(handle.summary()["night_charged_upper_bound_usd"], 2.5)
                self.assertEqual(handle.summary()["charged_upper_bound_usd"], 5.5)
                with self.assertRaises(BudgetStop):
                    handle.reserve("review-overflow", MODELS[2], 1)
                self.assertEqual(self.rows(handle), before)
                self.assert_prior_preserved(handle)

    def test_rejected_reservation_rolls_back_and_exact_remaining_nano_stays_usable(self):
        first = self.open_budget(7)
        second = self.open_budget(7)
        first.reserve("first", MODELS[0], 7)
        first.settle("first", 6)
        before = self.rows(first)
        with self.assertRaises(BudgetStop):
            second.reserve("overflow", MODELS[1], 2)
        self.assertEqual(self.rows(first), before)
        self.assertEqual(second.db.execute("SELECT blocked FROM config WHERE id=1").fetchone(), (0,))
        second.reserve("overflow", MODELS[2], 1)
        second.settle("overflow", 1)
        self.assertEqual(first.db.execute(
            "SELECT SUM(charged) FROM requests WHERE rowid>?", (self.baseline["max_rowid"],)
        ).fetchone(), (7,))
        with self.assertRaises(BudgetStop):
            first.reserve("overflow", MODELS[2], 1)
        self.assert_prior_preserved(first)

    def test_pending_and_uncertain_liability_block_every_handle_without_reconciliation(self):
        first = self.open_budget(3_000_000_000)
        second = self.open_budget(3_000_000_000)
        first.reserve("unknown", MODELS[1], 2_000_000_000)
        pending = self.rows(first)
        with self.assertRaises(BudgetStop):
            second.reserve("while-pending", MODELS[2], 1)
        self.assertEqual(self.rows(first), pending)
        first.uncertain("unknown")
        uncertain = self.rows(first)
        for handle in (first, second):
            with self.subTest(handle=handle):
                with self.assertRaises(BudgetStop):
                    handle.reserve("after-uncertainty", MODELS[2], 1)
                with self.assertRaises(BudgetStop):
                    handle.reconcile_uncertain_at_ceiling("unknown", "c" * 64)
                self.assertEqual(self.rows(handle), uncertain)
                self.assertEqual(handle.summary()["unresolved_reserved_usd"], 2.0)
                self.assertEqual(handle.summary()["charged_upper_bound_usd"], 3.0)
                self.assertTrue(handle.summary()["blocked"])
                self.assertEqual(handle.db.execute("SELECT COUNT(*) FROM reconciliations").fetchone(), (0,))
        with self.assertRaises(BudgetStop):
            self.open_budget(3_000_000_000)
        self.assert_prior_preserved(first)

    def test_known_overcharge_is_recorded_and_blocks_lower_cap_handles(self):
        first = self.open_budget(500)
        second = self.open_budget(500)
        first.reserve("overcharge", MODELS[1], 100)
        with self.assertRaises(BudgetStop):
            first.settle("overcharge", 101)
        self.assertEqual(first.db.execute(
            "SELECT reserved,charged,status FROM requests WHERE id='overcharge'"
        ).fetchone(), (100, 101, "settled"))
        self.assertEqual(first.db.execute("SELECT blocked FROM config WHERE id=1").fetchone(), (1,))
        before = self.rows(first)
        with self.assertRaises(BudgetStop):
            second.reserve("post-overcharge", MODELS[2], 1)
        self.assertEqual(self.rows(first), before)
        self.assert_prior_preserved(first)

    def test_invalid_caps_reject_before_any_database_open(self):
        invalid = (True, False, None, "1", 1.0, IntegerSubclass(1), 0, -1,
                   DEFAULT_CAP + 1, float("nan"), float("inf"), [], {})
        missing = Path(self.temp.name) / "must-not-create.sqlite3"
        original = self.path.read_bytes()
        for value in invalid:
            for path in (self.path, missing):
                with self.subTest(value=repr(value), path=path.name):
                    with patch("sqlite3.connect", side_effect=AssertionError("DB opened before cap validation")) as connect:
                        with self.assertRaises(ValueError):
                            NightBudget(path, baseline=self.baseline, deadline_utc=DEADLINE,
                                        additional_cap_nano_usd=value,
                                        clock=lambda: self.wall, monotonic=lambda: self.mono)
                        connect.assert_not_called()
                    self.assertFalse(missing.exists())
                    self.assertEqual(self.path.read_bytes(), original)

    def test_prior_model_cap_still_stops_even_with_lower_additional_headroom(self):
        self.append_history("prior-model-full", MODELS[0], 97_000_000_000)
        budget = self.open_budget(5_000_000_000)
        before = self.rows(budget)
        with self.assertRaises(BudgetStop) as stopped:
            budget.reserve("model-overflow", MODELS[0], 1)
        self.assertEqual(str(stopped.exception), "Cumulative full-batch budget ceiling")
        self.assertEqual(self.rows(budget), before)
        budget.reserve("other-model-headroom", MODELS[1], 1)
        budget.settle("other-model-headroom", 1)
        self.assert_prior_preserved(budget)

    def test_prior_global_cap_still_stops_even_with_lower_additional_headroom(self):
        self.append_history("prior-model-full", MODELS[0], 97_000_000_000)
        self.append_history("prior-global-full", MODELS[1], 100_000_000_000)
        budget = self.open_budget(5_000_000_000)
        before = self.rows(budget)
        with self.assertRaises(BudgetStop) as stopped:
            budget.reserve("global-overflow", MODELS[2], 1)
        self.assertEqual(str(stopped.exception), "Cumulative full-batch budget ceiling")
        self.assertEqual(self.rows(budget), before)
        self.assertEqual(budget.summary()["charged_upper_bound_usd"], 200.0)
        self.assertEqual(budget.summary()["night_charged_upper_bound_usd"], 0.0)
        self.assert_prior_preserved(budget)

    def test_changed_frozen_history_rejects_open_and_drift_rejects_insertion(self):
        budget = self.open_budget(100)
        with self.assertRaises(BudgetStop):
            self.open_budget(100, baseline=dict(self.baseline, charged_nano_usd=0))
        self.assert_prior_preserved(budget)
        budget.db.execute("UPDATE requests SET charged=0 WHERE id='prior'")
        before = self.rows(budget)
        with self.assertRaises(BudgetStop):
            budget.reserve("history-refund", MODELS[1], 1)
        self.assertEqual(self.rows(budget), before)

    def test_lower_cap_preserves_wall_expiry_and_monotonic_rollback_guard(self):
        budget = self.open_budget(100)
        before = self.rows(budget)
        self.wall = utc_epoch(DEADLINE)
        with self.assertRaises(BudgetStop):
            budget.reserve("at-wall-deadline", MODELS[1], 1)
        self.wall -= 3600
        self.mono += 1001
        with self.assertRaises(BudgetStop):
            budget.reserve("after-wall-rollback", MODELS[1], 1)
        self.assertEqual(self.rows(budget), before)
        self.assert_prior_preserved(budget)

    def test_lower_cap_cannot_reopen_expired_original_clock_on_new_handle(self):
        budget = self.open_budget(100, captured_deadline=101)
        before = self.rows(budget)
        self.wall -= 3600
        self.mono = 102
        with self.assertRaises(BudgetStop):
            self.open_budget(100, captured_deadline=101)
        with self.assertRaises(BudgetStop):
            budget.reserve("expired-origin", MODELS[1], 1)
        self.assertEqual(self.rows(budget), before)
        self.assert_prior_preserved(budget)


if __name__ == "__main__":
    unittest.main()
