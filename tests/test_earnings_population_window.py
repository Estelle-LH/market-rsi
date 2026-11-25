"""Outer-window contracts; inert preparation/owner/Native seams, no provider.

The existing fixtures retain their original source/ledger/clock checks where
stated. Fake historical/source/owner callbacks below are not live admission.
"""
from copy import deepcopy
from datetime import datetime, timezone
import unittest
from unittest.mock import patch

import earnings_population_window as window
import earnings_population_run as run
import earnings_population_runtime as runtime
from edgar_forecast_budget import BudgetStop
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_population_run as entry_fixture
import test_earnings_population_completed as completed_fixture
import test_earnings_population_forecast_failure as failed_fixture
from test_earnings_population_runtime import Fixture, save

GRANT = {'path': '/synthetic/existing-budget-grant.json', 'sha256': 'a' * 64}


def policy(minutes=180):
    return dict(window_minutes=minutes, budget_amendment=deepcopy(GRANT), companies=['CIK0000017313'])


class WindowPolicyTests(unittest.TestCase):
    def test_missing_and_explicit90_preserve_original_bounds(self):
        start = datetime(2026, 10, 18, tzinfo=timezone.utc)
        for value in ({}, {'window_minutes': 90}):
            self.assertEqual(window.minutes(value), 90)
            bounded = dict(value, **window.bounds(start, value))
            self.assertEqual(bounded['cutoff_utc'], '2026-10-18T01:30:00Z')
            self.assertEqual(bounded['deadline_utc'], '2026-10-18T01:31:00Z')
            self.assertEqual(window.start_utc(bounded), '2026-10-18T00:00:00Z')

    def test180_is_outer_time_only_and_start_is_not_renewed(self):
        start = datetime(2026, 10, 18, tzinfo=timezone.utc)
        value = policy(); value.update(window.bounds(start, value)); before = deepcopy(value)
        self.assertEqual(value['cutoff_utc'], '2026-10-18T03:00:00Z')
        self.assertEqual(value['deadline_utc'], '2026-10-18T03:01:00Z')
        for elapsed in (0, 200, 10799):
            window.check(value, start.timestamp() + elapsed)
            self.assertEqual(window.start_utc(value), '2026-10-18T00:00:00Z')
        with self.assertRaises(BudgetStop): window.check(value, start.timestamp() + 10800)
        self.assertEqual(value, before)

    def test_strict_numeric_duration_and_present_null_are_refused(self):
        for invalid in (None, True, False, 90.0, 180.0, '180', 0, 89, 91, 181, [], {}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                window.minutes(dict(policy(), window_minutes=invalid))

    def test180_requires_existing_binding_and_one_decision(self):
        for change in ({'budget_amendment': None}, {'budget_amendment': {}},
                       {'budget_amendment': dict(GRANT, sha256='bad')},
                       {'companies': []}, {'companies': ['A', 'B']}, {'companies': ('A',)}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                window.minutes(dict(policy(), **change))
        with self.assertRaises(ValueError): window.minutes({'window_minutes': 180, 'companies': ['A']})

    def test_send_duration_and_terminal_grace_are_not_extended(self):
        start = datetime(2026, 10, 18, tzinfo=timezone.utc)
        for length in (90, 180):
            value = policy(length); value.update(window.bounds(start, value))
            with self.subTest(length=length), self.assertRaises(BudgetStop):
                window.check(value, start.timestamp() - 1)
            value['deadline_utc'] = value['deadline_utc'][:-3] + '01Z'
            with self.assertRaises(BudgetStop): window.check(value, start.timestamp())
        with self.assertRaises(ValueError): window.bounds(datetime(2026, 10, 18), {})


class RuntimeReceivingTests(Fixture):
    def test_window_only90_does_not_trigger_budget400_route(self):
        value = deepcopy(self.value); value['window_minutes'] = 90
        actual = runtime.preflight(self.bound(value))
        self.assertEqual(actual['window_minutes'], 90)
        self.assertNotIn('budget_amendment', actual)
        self.assertEqual(actual['limits'], self.value['limits'])
        self.assertEqual(actual['additional_cap_nano_usd'], 5_000_000_000)

    def test180_real_runtime_shape_requires_amendment_route_and_keeps_resources(self):
        value = dict(deepcopy(self.value), **policy())
        value.update(window.bounds(datetime.fromtimestamp(self.now, timezone.utc), value))
        grant_plan = save(self.repo / runtime.BUDGET_PLAN, {'synthetic_source': True})
        self.expected[runtime.BUDGET_PLAN] = grant_plan['path']
        value['sources'][runtime.BUDGET_PLAN] = grant_plan
        study = dict(self.study, campaign_resume={'synthetic': True})
        value['forecast_study'] = save(self.owned / 'study180.json', study)
        # Only original task and grant-ledger admission are seams here; the
        # real runtime field/source/review/time/slot checks remain exercised.
        with patch.object(runtime, '_study', return_value=self.original), patch.object(runtime, '_ledger') as ledger:
            actual = runtime.preflight(self.bound(value))
            ledger.assert_called_once()
        self.assertEqual(actual['limits'], self.value['limits'])
        self.assertEqual(actual['rates'], self.value['rates'])
        self.assertEqual(actual['additional_cap_nano_usd'], self.value['additional_cap_nano_usd'])

    def test180_without_amendment_or_two_companies_fails_before_ledger(self):
        for value in (dict(self.value, window_minutes=180), dict(dict(self.value, **policy()), companies=self.ciks)):
            with self.subTest(value=value.get('companies')), patch.object(runtime, '_ledger') as ledger:
                with self.assertRaises(ValueError): runtime.preflight(self.bound(value))
                ledger.assert_not_called()


class ProducerAndNativeTests(unittest.TestCase):
    def test_prepare_defaults90_and_rejects180_before_idle_or_inputs(self):
        f = entry_fixture.PreparationContracts(); f.setUp(); self.addCleanup(f.doCleanups)
        for invalid in (180, None, True, 90.0):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                run.prepare(f.id, window_minutes=invalid)
            f.idle.assert_not_called()
            self.assertFalse((f.owned / 'inputs' / f.id).exists())
        actual = engine.read(run.prepare(f.id))
        self.assertEqual(actual['window_minutes'], 90)
        self.assertEqual(window.start_utc(actual), window.start_utc(dict(actual, window_minutes=90)))

    def test_original_execute_passes_same_bound_start_into_services(self):
        f = entry_fixture.ExecutionContracts(); f.setUp(); self.addCleanup(f.doCleanups)
        value = dict(deepcopy(f.value), **policy())
        value.update(window.bounds(datetime.fromtimestamp(f.now, timezone.utc), value))
        bound = f.bound(value)
        # The original clock owner ordering/receiver is real; provider, source
        # authority and loop remain the existing inert fixture boundaries.
        with patch.object(run, 'preflight', return_value=value), patch.object(run, 'loop', return_value={'synthetic': True}):
            result = engine.read(run.execute(bound))
        self.assertEqual(f.instances[0].start_utc, window.start_utc(value))
        self.assertEqual(result['status'], 'COMPLETED_DISCOVERY_PILOT')
        self.assertEqual(engine.read(bound)['cutoff_utc'], value['cutoff_utc'])

    def test_completed_native_replay_uses_same180_start_and_preserves90(self):
        f = completed_fixture.CompletedDraftTests(); f.module = __import__('earnings_population_completed')
        for duration in (90, 180):
            fixture = f.native_fixture(); config = fixture[3]
            if duration == 180: config.update(policy())
            fixture[0].read.return_value['window']['start_utc'] = window.start_utc(config)
            self.assertEqual(len(f.native(fixture)), 2)
            fixture[0].read.return_value['window']['start_utc'] = '2026-10-17T02:59:00Z'
            with self.assertRaises(ValueError): f.native(fixture)

    def test_failed_forecast_native_replay_uses_same180_start(self):
        f = failed_fixture.IdleNativeSchemaTests()
        fixture = f.fixture('controller'); fixture[3].update(policy())
        fixture[0].read.return_value['window']['start_utc'] = window.start_utc(fixture[3])
        self.assertEqual(len(f.run_native(fixture)), 4)
        fixture[0].read.return_value['window']['start_utc'] = '2026-10-17T01:30:00Z'
        with self.assertRaises(ValueError): f.run_native(fixture)
