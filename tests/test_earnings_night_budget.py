import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from edgar_forecast_budget import PilotBudget, BudgetStop
from edgar_forecast_full_budget import activate, FullBudget
from earnings_night_budget import NightBudget, DeadlineHTTP, history_snapshot, utc_epoch

DEADLINE = "2026-10-13T15:03:10Z"
MODEL = "gpt-6.1-sol"


class NightBudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "sole.sqlite3"
        old = PilotBudget(self.path)
        old.reserve("prior", MODEL, 4_000_000_000)
        old.settle("prior", 3_000_000_000)
        old.close()
        activate(self.path, "a" * 64, "b" * 40)
        current = FullBudget(self.path)
        self.baseline = history_snapshot(current.db)
        current.close()
        self.now = utc_epoch(DEADLINE) - 1000
        self.budget = self.open()
        self.addCleanup(self.budget.close)

    def open(self):
        return NightBudget(self.path, baseline=self.baseline, deadline_utc=DEADLINE, clock=lambda: self.now)

    def test_prior_charges_and_global_model_limits_remain(self):
        self.assertEqual(self.budget.summary()["charged_upper_bound_usd"], 3)
        self.assertEqual(self.budget.summary()["night_charged_upper_bound_usd"], 0)
        self.assertEqual(self.budget.summary()["cap_usd"], 200)
        self.assertEqual(self.budget.summary()["model_cap_usd"], 100)
        for amount in (200_000_000_000, 100_000_000_000):
            with self.assertRaises(BudgetStop):
                self.budget.reserve("overflow", MODEL, amount)

    def test_night_cap_is_atomic_and_survives_another_handle(self):
        other = self.open()
        self.addCleanup(other.close)
        self.budget.reserve("one", MODEL, 20_000_000_000)
        with self.assertRaises(BudgetStop):
            other.reserve("concurrent", MODEL, 1)
        self.budget.settle("one", 19_999_999_999)
        with self.assertRaises(BudgetStop):
            other.reserve("over", MODEL, 2)
        other.reserve("last", MODEL, 1)
        other.settle("last", 1)
        self.assertEqual(other.summary()["night_charged_upper_bound_usd"], 20)
        with self.assertRaises(BudgetStop):
            other.reserve("last", MODEL, 1)

    def test_uncertainty_and_overcharge_are_not_cleared(self):
        self.budget.reserve("unknown", MODEL, 100)
        self.budget.uncertain("unknown")
        with self.assertRaises(BudgetStop):
            self.budget.reserve("retry", MODEL, 1)
        with self.assertRaises(BudgetStop):
            self.budget.reconcile_uncertain_at_ceiling("unknown", "a" * 64)
        self.assertEqual(self.budget.summary()["unresolved_reserved_usd"], 100 / 1e9)

    def test_deadline_and_history_drift_stop_before_insertion(self):
        self.now = utc_epoch(DEADLINE)
        with self.assertRaises(BudgetStop):
            self.budget.reserve("late", MODEL, 1)
        self.now -= 1
        self.budget.db.execute("UPDATE requests SET charged=0 WHERE id='prior'")
        with self.assertRaises(BudgetStop):
            self.budget.reserve("refund", MODEL, 1)
        self.assertEqual(self.budget.db.execute("SELECT COUNT(*) FROM requests").fetchone()[0], 1)

    def test_unknown_model_and_changed_baseline_reject(self):
        with self.assertRaises(ValueError):
            self.budget.reserve("new", "other-model", 1)
        changed = dict(self.baseline, charged_nano_usd=0)
        with self.assertRaises(BudgetStop):
            NightBudget(self.path, baseline=changed, deadline_utc=DEADLINE, clock=lambda: self.now)

    def test_wall_rollback_does_not_reopen_reservation_window(self):
        mono = [1]
        budget = NightBudget(self.path, baseline=self.baseline, deadline_utc=DEADLINE,
                             clock=lambda: self.now, monotonic=lambda: mono[0])
        self.addCleanup(budget.close)
        self.now -= 3600
        mono[0] += 1001
        with self.assertRaises(BudgetStop):
            budget.reserve("late-after-rollback", MODEL, 1)
        self.assertEqual(budget.db.execute("SELECT COUNT(*) FROM requests").fetchone()[0], 1)

    def test_shared_origin_expiry_survives_a_new_role_budget_and_wall_rollback(self):
        with self.assertRaises(BudgetStop):
            NightBudget(self.path, baseline=self.baseline, deadline_utc=DEADLINE,
                clock=lambda: self.now - 3600, monotonic=lambda: 102, captured_deadline=101)
        for value in (True, float("inf"), -1):
            with self.assertRaises(ValueError):
                NightBudget(self.path, baseline=self.baseline, deadline_utc=DEADLINE, captured_deadline=value)


class DeadlineHTTPTests(unittest.TestCase):
    def test_transport_reuses_before_credential_deadline(self):
        client = Mock(timeout=1200)
        transport = DeadlineHTTP(client, deadline_utc=DEADLINE, rollout_seconds=1800,
                                 clock=lambda: utc_epoch(DEADLINE) - 3600, monotonic=lambda: 52,
                                 captured_deadline=51)
        with self.assertRaises(BudgetStop):
            transport.post("/v1/responses/input_tokens", {})
        client.post.assert_not_called()

    def test_wall_rollback_never_extends_actual_send_window(self):
        client = Mock(timeout=1200)
        wall, mono = [utc_epoch(DEADLINE) - 50], [1]
        transport = DeadlineHTTP(client, deadline_utc=DEADLINE, rollout_seconds=1800,
                                 clock=lambda: wall[0], monotonic=lambda: mono[0])
        wall[0] -= 3600
        mono[0] += 51
        with self.assertRaises(BudgetStop):
            transport.post("/v1/responses", {})
        client.post.assert_not_called()

    def test_actual_timeout_is_clipped_without_retry(self):
        client = Mock(timeout=1200)
        client.post.return_value = {"status": "completed"}
        now = [utc_epoch(DEADLINE) - 50]
        clock = lambda: now[0]
        transport = DeadlineHTTP(client, deadline_utc=DEADLINE, rollout_seconds=1800,
                                 clock=clock, monotonic=lambda: 1)
        self.assertEqual(transport.post("/v1/responses", {"input": "x"}), {"status": "completed"})
        self.assertEqual(client.timeout, 50)
        now[0] += 50
        with self.assertRaises(BudgetStop):
            transport.post("/v1/responses", {})
        self.assertEqual(client.post.call_count, 1)

    def test_transport_failure_is_not_retried(self):
        client = Mock(timeout=1200)
        client.post.side_effect = TimeoutError("synthetic")
        transport = DeadlineHTTP(client, deadline_utc=DEADLINE, rollout_seconds=1800,
                                 clock=lambda: utc_epoch(DEADLINE) - 50, monotonic=lambda: 1)
        with self.assertRaises(TimeoutError):
            transport.post("/v1/responses", {})
        client.post.assert_called_once()


if __name__ == "__main__":
    unittest.main()
