"""Explicit operator recovery and slow-call policy on owned synthetic fixtures.

No actual ledger, labels, filing artifacts, credentials or provider network are
used. Financial admission/scoring and the raw provider remain explicit fakes;
the loop, forecast, guards, deadlines and accounting implementations are real.
"""
from contextlib import closing
from copy import deepcopy
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import edgar_forecast_full_budget as full
import edgar_live_feedback as live
from edgar_forecast_budget import BudgetStop, PilotBudget
from earnings_night_budget import DeadlineHTTP, NightBudget, utc_epoch
from test_edgar_live_feedback import COUNT, GENERATE, ScriptedRaw, SyntheticFixture, read_json

MODEL = "gpt-6.1-sol"
OTHER = "gpt-5.4-2026-03-05"
LOST = "invented-uncertain"
CEILING = 487_275_000
EVIDENCE = "a" * 64
DEADLINE = "2026-10-15T00:00:00Z"


class SyntheticLedger:
    def __init__(self, case, *, full_allocation=True):
        temporary = tempfile.TemporaryDirectory(prefix="edgar-recovery-synthetic-")
        case.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name).resolve()
        self.path = self.home / "synthetic.sqlite3"
        budget = PilotBudget(self.path)
        for identity, model, amount in (("invented-prior-target", MODEL, 8_000_000_000),
                                        ("invented-prior-other", OTHER, 2_000_000_000)):
            budget.reserve(identity, model, amount)
            budget.settle(identity, amount)
        budget.close()
        if full_allocation:
            full.activate(self.path, "b" * 64, "c" * 40)
            budget = full.FullBudget(self.path)
            budget.reserve("invented-full-prior", MODEL, 5_000_000_000)
            budget.settle("invented-full-prior", 5_000_000_000)
        else:
            budget = PilotBudget(self.path)
        self.prior_rows = self.snapshot()["requests"]
        budget.reserve(LOST, MODEL, CEILING)
        budget.uncertain(LOST)
        budget.close()

    def snapshot(self):
        with closing(sqlite3.connect(self.path)) as db:
            names = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            return {name: db.execute('SELECT rowid,* FROM "' + name + '" ORDER BY rowid').fetchall()
                    for name in names}

    def mutate(self, statements):
        with closing(sqlite3.connect(self.path)) as db:
            for sql, params in statements:
                db.execute(sql, params)
            db.commit()


class EdgarLiveFeedbackRecoveryTests(unittest.TestCase):
    def assert_operator_refuses_unchanged(self, ledger, *, request_id=LOST, evidence=EVIDENCE):
        before = ledger.snapshot()
        with self.assertRaises((BudgetStop, ValueError)):
            full.reconcile_at_ceiling(ledger.path, request_id, evidence)
        self.assertEqual(ledger.snapshot(), before)

    def test_explicit_full_allocation_reconciliation_books_full_ceiling_once_and_closes(self):
        ledger = SyntheticLedger(self)
        before = ledger.snapshot()
        original = PilotBudget.reconcile_uncertain_at_ceiling
        original_close = PilotBudget.close
        owners = []
        def reconcile(owner, request_id, evidence):
            owners.append(owner)
            return original(owner, request_id, evidence)
        with patch.object(full, "connect_existing", wraps=full.connect_existing) as connect, \
             patch.object(full.FullBudget, "__init__", side_effect=AssertionError("Blocked research constructor forbidden")) as constructor, \
             patch.object(PilotBudget, "reconcile_uncertain_at_ceiling", autospec=True, side_effect=reconcile) as inherited, \
             patch.object(full.FullBudget, "close", autospec=True, side_effect=original_close) as close:
            summary = full.reconcile_at_ceiling(ledger.path, LOST, EVIDENCE)
        connect.assert_called_once_with(ledger.path)
        constructor.assert_not_called()
        self.assertEqual(len(owners), 1)
        self.assertIs(type(owners[0]), full.FullBudget)
        inherited.assert_called_once_with(owners[0], LOST, EVIDENCE)
        close.assert_called_once_with(owners[0])
        with self.assertRaises(sqlite3.ProgrammingError): owners[0].db.execute("SELECT 1")
        after = ledger.snapshot()
        self.assertEqual(after["requests"][:-1], ledger.prior_rows)
        self.assertEqual(after["requests"][:-1], before["requests"][:-1])
        pending = before["requests"][-1]
        self.assertEqual(pending[1:], (LOST, MODEL, CEILING, 0, "uncertain"))
        self.assertEqual(after["requests"][-1], (*pending[:4], CEILING, "settled_upper_bound"))
        self.assertEqual(after["config"], [(1, 1, 200_000_000_000, 100_000_000_000, 0)])
        self.assertEqual(after["full_batch_allocations"], before["full_batch_allocations"])
        audit = after["reconciliations"]
        self.assertEqual(len(audit), 1)
        self.assertEqual(audit[0][1:7], (LOST, EVIDENCE, "uncertain", 0, CEILING,
                                       "operator_full_ceiling_actual_charge_unknown"))
        self.assertTrue(audit[0][7])
        self.assertEqual((summary["cap_usd"], summary["model_cap_usd"], summary["blocked"]), (200, 100, False))
        self.assertAlmostEqual(summary["charged_upper_bound_usd"], 15.487275)
        self.assertEqual(summary["unresolved_reserved_usd"], 0)
        self.assertEqual(summary["generation_requests_reserved"], len(before["requests"]))

    def test_reconciliation_rejects_second_call_wrong_row_and_invalid_evidence(self):
        ledger = SyntheticLedger(self)
        for request_id in ("invented-prior-target", "missing-request"):
            with self.subTest(request_id=request_id):
                self.assert_operator_refuses_unchanged(ledger, request_id=request_id)
        for evidence in (None, "", "a" * 63, "A" * 64, "g" * 64):
            with self.subTest(evidence=evidence):
                self.assert_operator_refuses_unchanged(ledger, evidence=evidence)
        full.reconcile_at_ceiling(ledger.path, LOST, EVIDENCE)
        self.assert_operator_refuses_unchanged(ledger)
        self.assertEqual(len(ledger.snapshot()["reconciliations"]), 1)

    def test_other_pending_overcharge_caps_allocation_and_missing_database_refuse_unchanged(self):
        variants = {
            "other-pending": [("INSERT INTO requests VALUES (?,?,?,?,?)", ("other-pending", OTHER, 1, 0, "reserved"))],
            "known-overcharge": [("INSERT INTO requests VALUES (?,?,?,?,?)", ("known-overcharge", OTHER, 1, 2, "settled"))],
            "total-cap": [
                ("INSERT INTO requests VALUES (?,?,?,?,?)", ("other-to-100", OTHER, 98_000_000_000, 98_000_000_000, "settled")),
                ("INSERT INTO requests VALUES (?,?,?,?,?)", ("third-to-total", "gpt-5.5-2026-04-23", 87_000_000_000, 87_000_000_000, "settled")),
            ],
            "model-cap": [("INSERT INTO requests VALUES (?,?,?,?,?)", ("target-to-100", MODEL, 87_000_000_000, 87_000_000_000, "settled"))],
            "allocation": [("UPDATE config SET model_cap=?", (10_000_000_000,))],
            "global-allocation": [("UPDATE config SET cap=?", (200_000_000_001,))],
            "wrong-stop-cause": [("UPDATE config SET blocked=0", ())],
        }
        for name, statements in variants.items():
            with self.subTest(name=name):
                ledger = SyntheticLedger(self)
                ledger.mutate(statements)
                self.assert_operator_refuses_unchanged(ledger)
        ledger = SyntheticLedger(self)
        missing = ledger.home / "does-not-exist.sqlite3"
        before = ledger.snapshot()
        with patch.object(PilotBudget, "__init__", side_effect=AssertionError("Never initialize another ledger")):
            with self.assertRaises(ValueError): full.reconcile_at_ceiling(missing, LOST, EVIDENCE)
        self.assertFalse(missing.exists())
        self.assertEqual(ledger.snapshot(), before)
        link = ledger.home / "symlink.sqlite3"
        link.symlink_to(ledger.path)
        with self.assertRaises(ValueError): full.reconcile_at_ceiling(link, LOST, EVIDENCE)
        self.assertEqual(ledger.snapshot(), before)

    def test_legacy_pilot_ten_dollar_policy_and_runtime_subclass_refusal_remain(self):
        self.assertEqual(PilotBudget.RECONCILIATION_MODEL_CAP, 10_000_000_000)
        self.assertEqual(full.FullBudget.RECONCILIATION_MODEL_CAP, 100_000_000_000)
        pilot = SyntheticLedger(self, full_allocation=False)
        before = pilot.snapshot()
        with closing(full.connect_existing(pilot.path)) as db:
            budget = PilotBudget.__new__(PilotBudget)
            budget.db = db
            budget.reconcile_uncertain_at_ceiling(LOST, EVIDENCE)
        self.assertEqual(pilot.snapshot()["requests"][:-1], before["requests"][:-1])
        self.assertEqual(pilot.snapshot()["config"][0][3], 10_000_000_000)
        over = SyntheticLedger(self, full_allocation=False)
        over.mutate([("UPDATE requests SET reserved=?,charged=? WHERE id=?",
                      (9_900_000_000, 9_900_000_000, "invented-prior-target"))])
        before = over.snapshot()
        with closing(full.connect_existing(over.path)) as db:
            budget = PilotBudget.__new__(PilotBudget)
            budget.db = db
            with self.assertRaises(BudgetStop): budget.reconcile_uncertain_at_ceiling(LOST, EVIDENCE)
        self.assertEqual(over.snapshot(), before)
        ledger = SyntheticLedger(self)
        before = ledger.snapshot()
        for cls in (PilotBudget, NightBudget):
            with self.subTest(budget_class=cls.__name__), closing(full.connect_existing(ledger.path)) as db:
                budget = cls.__new__(cls)
                budget.db = db
                with self.assertRaises(BudgetStop): budget.reconcile_uncertain_at_ceiling(LOST, EVIDENCE)
        self.assertEqual(ledger.snapshot(), before)

    def test_exact_integer_narrowed_caps_admit_three_dollars_and_refuse_expansion(self):
        fixture = SyntheticFixture(self, "narrowed-cap")
        with fixture.financial_admission():
            before = fixture.protected_snapshot()
            for cap in (1, 3_000_000_000, 5_000_000_000):
                with self.subTest(cap=cap):
                    fixture.config["additional_cap_nano_usd"] = cap
                    self.assertEqual(live.preflight(fixture.config)[0], fixture.company)
            for cap in (True, False, 0, -1, 3_000_000_000.0, "3000000000", None, 5_000_000_001):
                with self.subTest(cap=cap):
                    fixture.config["additional_cap_nano_usd"] = cap
                    with self.assertRaises(ValueError): live.run(fixture.config)
            self.assertEqual(fixture.protected_snapshot(), before)
        fixture.credentials.assert_not_called()
        fixture.factory.assert_not_called()
        self.assertFalse(fixture.root.exists())

    def test_default_constructor_gets_six_hundred_seconds_in_actual_seven_stage_flow(self):
        fixture = SyntheticFixture(self, "default-slow-policy")
        fixture.config["additional_cap_nano_usd"] = 3_000_000_000
        observed_timeouts = []
        class ObservedRaw(ScriptedRaw):
            def post(self, endpoint, payload):
                observed_timeouts.append((self.role, endpoint, self.timeout))
                return super().post(endpoint, payload)
        def make_client(key, *, timeout):
            self.assertEqual(key, "synthetic-credential-not-from-a-file")
            role = ("forecast-01", "controller", "forecast-02")[len(fixture.clients)]
            client = ObservedRaw(fixture, role)
            client.timeout = timeout
            fixture.clients.append(client)
            return client
        with fixture.flow(), \
             patch.object(live.e, "credential", return_value="synthetic-credential-not-from-a-file") as credential, \
             patch.object(live, "RawOpenAIHTTP", side_effect=make_client) as constructor:
            result = live.run(fixture.config)
        self.assertEqual((result["status"], result["completed_rounds"]), ("completed", 2))
        self.assertEqual(live.HTTP_TIMEOUT_SECONDS, 600)
        self.assertEqual(constructor.call_count, 3)
        self.assertEqual(credential.call_count, 3)
        for call in constructor.call_args_list:
            self.assertEqual(call.kwargs, {"timeout": 600})
        self.assertEqual(len(fixture.calls), 10)
        self.assertTrue(all(0 < timeout <= 600 for _, _, timeout in observed_timeouts))
        forecast_timeouts = [timeout for role, _, timeout in observed_timeouts if role.startswith("forecast")]
        self.assertEqual(forecast_timeouts, [600] * 8)
        policy_path = fixture.root / "transport-policy.json"
        self.assertEqual(read_json(policy_path), {
            "schema": "edgar_foreground_slow_call_policy_v1",
            "source_commit": fixture.config["source_commit"],
            "original_runtime_request_timeout_seconds": 180,
            "effective_socket_timeout_seconds": 600,
            "role_and_global_deadlines_unchanged": True, "retry_allowed": False})
        manifest = read_json(fixture.root / "loop/manifest.json")
        for identity in manifest["handler_identity"].values():
            self.assertEqual(identity["transport"], live.pin(policy_path))
        for index in (1, 2):
            for stage in live.driver.STAGES:
                self.assertTrue((fixture.root / "loop" / f"round-{index:04d}-{stage}.done.json").is_file())
        self.assertEqual(read_json(fixture.root / "budget-summary.json")["night_cap_usd"], 3)
        fixture.factory.assert_not_called()

    def test_slow_timeout_is_clipped_to_original_deadline_and_never_retried(self):
        wall, mono = [utc_epoch(DEADLINE) - 100], [1]
        client = Mock(timeout=600)
        client.post.return_value = {"status": "completed"}
        transport = DeadlineHTTP(client, deadline_utc=DEADLINE, rollout_seconds=1800,
            clock=lambda: wall[0], monotonic=lambda: mono[0], captured_deadline=31)
        self.assertEqual(transport.post(COUNT, {}), {"status": "completed"})
        self.assertEqual(client.timeout, 30)
        wall[0] -= 3600
        mono[0] = 32
        with self.assertRaises(BudgetStop): transport.post(GENERATE, {})
        client.post.assert_called_once_with(COUNT, {})
        failing = Mock(timeout=600)
        failing.post.side_effect = TimeoutError("invented slow request")
        transport = DeadlineHTTP(failing, deadline_utc=DEADLINE, rollout_seconds=1800,
            clock=lambda: utc_epoch(DEADLINE) - 800, monotonic=lambda: 1, captured_deadline=901)
        with self.assertRaises(TimeoutError): transport.post(GENERATE, {})
        self.assertEqual(failing.timeout, 600)
        failing.post.assert_called_once_with(GENERATE, {})

    def test_transport_failure_does_not_reconcile_refund_or_automatically_retry(self):
        fixture = SyntheticFixture(self, "no-auto-recovery")
        fixture.config["additional_cap_nano_usd"] = 3_000_000_000
        prior = deepcopy(fixture.rows())
        fixture.failure = ("forecast-01", 1)
        with fixture.flow(), \
             patch.object(full, "reconcile_at_ceiling", side_effect=AssertionError("Operator only")) as operator, \
             patch.object(PilotBudget, "reconcile_uncertain_at_ceiling", side_effect=AssertionError("No automatic recovery")) as reconcile:
            with self.assertRaises(live.driver.LoopHalted):
                live.run(fixture.config, client_factory=fixture.factory)
            before = fixture.protected_snapshot()
            calls = deepcopy(fixture.calls)
            with self.assertRaises(ValueError): live.run(fixture.config, client_factory=fixture.factory)
        operator.assert_not_called()
        reconcile.assert_not_called()
        self.assertEqual(fixture.protected_snapshot(), before)
        self.assertEqual(fixture.calls, calls)
        self.assertEqual([endpoint for _, endpoint, _ in fixture.calls], [COUNT, GENERATE])
        self.assertEqual(fixture.factory.call_count, 1)
        rows = fixture.rows()
        self.assertEqual(rows[:-1], prior)
        self.assertEqual(rows[-1][-2:], (0, "uncertain"))
        self.assertGreater(rows[-1][3], 0)
        with closing(sqlite3.connect(fixture.ledger)) as db:
            self.assertEqual(db.execute("SELECT * FROM reconciliations").fetchall(), [])
            self.assertEqual(db.execute("SELECT cap,model_cap,blocked FROM config").fetchall(),
                             [(200_000_000_000, 100_000_000_000, 1)])
        self.assertEqual(read_json(fixture.root / "result.json")["status"], "FAILED_NO_RETRY")
        self.assertIs(read_json(fixture.root / "loop/round-0001-execute.failed.json")["retry_allowed"], False)
        fixture.credentials.assert_not_called()


if __name__ == "__main__":
    unittest.main()
