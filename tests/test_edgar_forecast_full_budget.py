import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from edgar_forecast_budget import PilotBudget, BudgetStop
from edgar_forecast_full_budget import FullBudget, activate, FULL_MODEL_CAP


class FullBudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "sole.sqlite3"
        old = PilotBudget(self.path)
        old.reserve("old", "gpt-5.5-2026-04-23", 4_000_000_000)
        old.settle("old", 3_361_099_000)
        old.close()

    def tearDown(self):
        self.tmp.cleanup()

    def activated(self):
        activate(self.path, "a"*64, "b"*40)
        return FullBudget(self.path)

    def test_prior_history_global_cap_and_allocation_preserved(self):
        budget = self.activated()
        self.addCleanup(budget.close)
        self.assertEqual(budget.summary()["charged_upper_bound_usd"], 3.361099)
        self.assertEqual(budget.summary()["cap_usd"], 200)
        self.assertEqual(budget.summary()["model_cap_usd"], 100)
        with self.assertRaises(BudgetStop):
            budget.reserve("overspend", "gpt-6.1-sol", 200_000_000_000)
        with self.assertRaises(BudgetStop):
            budget.reserve("model-over", "gpt-5.5-2026-04-23", FULL_MODEL_CAP)

    def test_pending_blocks_next_dispatch_and_activation(self):
        old = PilotBudget(self.path)
        old.reserve("pending", "gpt-6.1-sol", 100)
        old.uncertain("pending")
        old.close()
        with self.assertRaises(BudgetStop):
            activate(self.path, "a"*64, "b"*40)

    def test_serial_no_retry_and_unknown_model(self):
        budget = self.activated()
        self.addCleanup(budget.close)
        with self.assertRaises(ValueError):
            budget.reserve("bad", "another-model", 100)
        budget.reserve("new", "gpt-5.4-2026-03-05", 100)
        with self.assertRaises(BudgetStop):
            budget.reserve("concurrent", "gpt-6.1-sol", 100)
        budget.settle("new", 90)
        with self.assertRaises(BudgetStop):
            budget.reserve("new", "gpt-5.4-2026-03-05", 100)

    def test_missing_unactivated_and_repeated_migration_reject(self):
        with self.assertRaises(ValueError):
            FullBudget(self.path.parent / "other.sqlite3")
        with self.assertRaises(ValueError):
            activate(self.path.parent / "other.sqlite3", "a"*64, "b"*40)
        self.assertFalse((self.path.parent / "other.sqlite3").exists())
        with self.assertRaises(BudgetStop):
            FullBudget(self.path)
        budget = self.activated()
        budget.close()
        with self.assertRaises(BudgetStop):
            activate(self.path, "a"*64, "b"*40)

    def test_configuration_drift_stops(self):
        budget = self.activated()
        self.addCleanup(budget.close)
        budget.db.execute("UPDATE config SET cap=cap+1 WHERE id=1")
        with self.assertRaises(BudgetStop):
            budget.reserve("drift", "gpt-6.1-sol", 100)


if __name__ == "__main__":
    unittest.main()
