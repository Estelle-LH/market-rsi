import copy
import tempfile
import unittest
from pathlib import Path

from paid_budget import PaidBudget


class PaidBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "run"
        self.auth = dict(experiment_id="test", cap_usd="200", target_usd="100",
                         buckets_usd=dict(setup="10", learning="120", final="50", repair="20"),
                         authority="test-only fixture")
        self.b = PaidBudget.create(self.root, self.auth)
        self.receipt = dict(terminal=True, tokens=100, source="fixture")

    def tearDown(self):
        self.temp.cleanup()

    def reserve(self, job="one", bucket="learning", upper="100"):
        self.b.reserve(job, bucket, upper, "fixture", "a" * 64)

    def test_reservation_is_not_spend_and_unused_is_released(self):
        self.reserve()
        self.assertEqual(self.b.snapshot()["metered_usd"], "0")
        self.b.dispatch("one")
        self.b.settle_metered("one", "3.25", self.receipt)
        snap = PaidBudget(self.root).snapshot()
        self.assertEqual(snap["reserved_usd"], "0")
        self.assertEqual(snap["available_usd"], "196.75")
        self.assertEqual(snap["metered_usd"], "3.25")
        self.assertFalse(snap["invoice_reconciliation_complete"])

    def test_dispatched_unknown_keeps_entire_hold(self):
        self.reserve()
        self.b.dispatch("one")
        with self.assertRaises(ValueError):
            self.b.cancel_before_dispatch("one")
        self.assertEqual(PaidBudget(self.root).snapshot()["reserved_usd"], "100")
        self.assertFalse(self.b.snapshot()["invoice_reconciliation_complete"])

    def test_reaped_timeout_moves_hold_to_conservative_effective_cost(self):
        self.reserve(upper="10")
        self.b.dispatch("one")
        receipt = {"terminal_local": True, "process_reaped": True,
            "remote_usage_unknown": True, "automatic_retry": False,
            "evidence_sha256": "c" * 64,
            "note": "fixture local timeout; invoice not yet available"}
        self.b.settle_uncertain_at_upper("one", receipt)
        snap = self.b.snapshot()
        self.assertEqual(snap["reserved_usd"], "0")
        self.assertEqual(snap["metered_usd"], "0")
        self.assertEqual(snap["effective_cost_usd"], "10")
        self.assertEqual(snap["available_usd"], "190")
        self.assertFalse(snap["invoice_reconciliation_complete"])
        with self.assertRaises(ValueError):
            self.b.settle_uncertain_at_upper("one", receipt)
        self.b.record_invoice("one", "3", "d" * 64)
        snap = self.b.snapshot()
        self.assertEqual(snap["effective_cost_usd"], "3")
        self.assertEqual(snap["invoiced_usd"], "3")
        self.assertTrue(snap["invoice_reconciliation_complete"])

    def test_uncertain_close_requires_strict_local_terminal_receipt(self):
        self.reserve(upper="10")
        self.b.dispatch("one")
        bad = {"terminal_local": True, "process_reaped": False,
            "remote_usage_unknown": True, "automatic_retry": False,
            "evidence_sha256": "c" * 64, "note": "not reaped"}
        with self.assertRaises(ValueError):
            self.b.settle_uncertain_at_upper("one", bad)
        self.assertEqual(self.b.snapshot()["reserved_usd"], "10")

    def test_invoice_completion_includes_every_pending_job(self):
        self.reserve(upper="10")
        self.assertFalse(self.b.snapshot()["invoice_reconciliation_complete"])
        self.b.dispatch("one")
        self.b.settle_metered("one", "2", self.receipt)
        self.assertFalse(self.b.snapshot()["invoice_reconciliation_complete"])
        self.b.record_invoice("one", "2", "b" * 64)
        self.assertTrue(self.b.snapshot()["invoice_reconciliation_complete"])
        self.reserve("two", upper="10")
        self.assertFalse(self.b.snapshot()["invoice_reconciliation_complete"])
        self.b.cancel_before_dispatch("two")
        self.assertTrue(self.b.snapshot()["invoice_reconciliation_complete"])
        self.reserve("three", upper="10")
        self.b.dispatch("three")
        self.assertFalse(self.b.snapshot()["invoice_reconciliation_complete"])
        self.assertEqual(self.b.snapshot()["reserved_usd"], "10")
        self.assertEqual(self.b.snapshot()["effective_cost_usd"], "2")

    def test_protected_final_cannot_be_spent_on_learning(self):
        self.reserve(upper="120")
        with self.assertRaises(ValueError):
            self.reserve("two", upper="0.01")
        self.reserve("final-job", bucket="final", upper="50")

    def test_duplicate_run_and_job_and_dispatch_rejected(self):
        with self.assertRaises(FileExistsError):
            PaidBudget.create(self.root, self.auth)
        self.reserve()
        with self.assertRaises(ValueError):
            self.reserve()
        self.b.dispatch("one")
        with self.assertRaises(ValueError):
            self.b.dispatch("one")

    def test_cancel_before_send_and_never_reuse(self):
        self.reserve()
        self.b.cancel_before_dispatch("one")
        self.assertEqual(self.b.snapshot()["available_usd"], "200")
        with self.assertRaises(ValueError):
            self.reserve()

    def test_invoice_replaces_not_adds_metering(self):
        self.reserve()
        self.b.dispatch("one")
        self.b.settle_metered("one", "4", self.receipt)
        self.b.record_invoice("one", "3.50", "b" * 64)
        snap = self.b.snapshot()
        self.assertEqual(snap["metered_usd"], "4")
        self.assertEqual(snap["invoiced_usd"], "3.50")
        self.assertEqual(snap["effective_cost_usd"], "3.50")
        self.assertEqual(snap["available_usd"], "196.50")

    def test_invoice_overrun_blocks_new_jobs(self):
        self.reserve()
        self.b.dispatch("one")
        self.b.settle_metered("one", "4", self.receipt)
        self.b.record_invoice("one", "201", "b" * 64)
        with self.assertRaises(ValueError):
            self.reserve("another", bucket="setup", upper="0.01")

    def test_terminal_receipt_is_mandatory_and_single(self):
        self.reserve()
        with self.assertRaises(ValueError):
            self.b.settle_metered("one", "1", self.receipt)
        self.b.dispatch("one")
        with self.assertRaises(ValueError):
            self.b.settle_metered("one", "1", {"terminal": False})
        self.b.settle_metered("one", "1", self.receipt)
        with self.assertRaises(ValueError):
            self.b.settle_metered("one", "1", self.receipt)

    def test_mutated_authority_detected(self):
        p = self.root / "authorization.json"
        p.write_text(p.read_text().replace('"200"', '"2000"'))
        with self.assertRaises(ValueError):
            self.b.snapshot()

    def test_invalid_money(self):
        for value in ("NaN", "Infinity", "-1", True):
            with self.assertRaises(ValueError):
                self.reserve(upper=value)


if __name__ == "__main__":
    unittest.main()
