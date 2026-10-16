"""Inert population admission contracts; no production ledger/provider/owner."""
from contextlib import ExitStack, closing
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import earnings_capacity_runtime as shared
import earnings_entry as entry
import earnings_population as pool
import earnings_population_runtime as runtime
import earnings_population_tasks as tasks
from earnings_night_budget import history_snapshot
from edgar_forecast_budget import BudgetStop
from market_rsi import digest


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True))
    return {'path': str(path), 'sha256': entry.digest(path.read_bytes())}


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name).resolve()
        self.owned, self.repo = self.home / 'owned', self.home / 'repo'
        self.pilot = self.home / 'pilot'
        self.pilot.mkdir()
        self.ledger = self.pilot / 'api-budget.sqlite3'
        self.db = sqlite3.connect(self.ledger)
        self.addCleanup(self.db.close)
        self.db.execute('CREATE TABLE config(id INTEGER,cap INTEGER,model_cap INTEGER,blocked INTEGER)')
        self.db.execute('INSERT INTO config VALUES (1,200000000000,100000000000,0)')
        self.db.execute('CREATE TABLE requests(id TEXT,model TEXT,reserved INTEGER,charged INTEGER,status TEXT)')
        self.db.executemany('INSERT INTO requests VALUES (?,?,?,?,?)', [
            ('prior-a', 'gpt-5.4', 80000000000, 80000000000, 'settled'),
            ('prior-b', 'gpt-6.1-sol', 57542765000, 57542765000, 'settled_upper_bound')])
        self.db.commit()
        self.synthetic_original = history_snapshot(self.db)
        self.now, self.commit = 1900000000, 'a' * 40
        self.id = 'edgar-population-20261016-01'
        self.root = self.owned / 'attempts' / self.id
        self.ciks = ['CIK0000004457', 'CIK0000017313']
        self.original = json.loads(tasks._read(tasks.RUNTIME))
        self.residents = {cik: {'runtime': deepcopy(self.original), 'case': {
            'cik': cik, 'cutoff': '2026-02-01', 'target_accession': 'fixture-public-accession',
            'visible_root': str(self.owned / cik), 'allowed_manifest_sha256': 'b' * 64,
            'evaluation_kernel': {'scorer': deepcopy(tasks.SCORER),
                                  'qa': {'path': str(self.owned / cik / 'qa'), 'sha256': 'c' * 64}}}}
            for cik in self.ciks}
        # Fake source bytes and committed-byte reader are fixtures only. They
        # do not prove real source admission, author behavior or live readiness.
        names = [runtime.PLAN, 'tools/earnings_population_services.py',
                 'tools/earnings_population_runtime.py']
        bindings = {name: save(self.repo / name, {'synthetic_source': name}) for name in names}
        self.expected = {name: bound['path'] for name, bound in bindings.items()}
        self.expected.update({key: bindings['tools/earnings_population_runtime.py']['path']
                              for key in ['runtime', 'budget', 'clock', 'controller', 'forecast_entry', 'forecaster']})
        self.expected.update({'factory_' + role: bindings['tools/earnings_population_services.py']['path']
                             for role in runtime.ROLES})
        self.plan = {'schema': 'supervisor_bottleneck_plan_v1',
                     'id': 'earnings-population-restore-20261016',
                     'human_authorization': runtime.AUTHORIZATION}
        save(self.repo / runtime.PLAN, self.plan)
        self.source_bindings = {name: {'path': path, 'sha256': entry.digest(Path(path).read_bytes())}
                                for name, path in self.expected.items()}
        r, h = save(self.owned / 'R.py', {'source': 'R'}), save(self.owned / 'H.py', {'source': 'H'})
        state = pool.initialize(pool.version(r, h),
            {'K': digest({'data': tasks.FULL_PLAN, 'scorer': tasks.SCORER}), 'M': 'd' * 64, 'C': 'e' * 64},
            exposed_companies=['CIK0000003545'])
        initial = save(self.owned / 'initial.json', state)
        prior = save(self.owned / 'prior.json', {'schema': 'original_runtime_snapshot_v1',
                    'source': tasks.RUNTIME, 'config': self.original})
        self.study = {'schema': 'earnings_coevolution_study_v1', 'data': tasks.FULL_PLAN,
            'scorer': tasks.SCORER, 'sole_ledger': str(self.ledger), 'runtime_config': self.original,
            'cases': [self.residents[c]['case'] for c in self.ciks], 'prior_batch': prior,
            'model': {'requested_model': 'gpt-6.1-sol', 'serving_snapshot': 'unknown',
                      'serving_snapshot_verified': False}}
        study = save(self.owned / 'study.json', self.study)
        utc = lambda n: datetime.fromtimestamp(n, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        self.value = {'schema': 'earnings_population_runtime_v1', 'purpose': 'capacity_episode',
            'id': self.id, 'root': str(self.root), 'source_commit': self.commit,
            'ledger': str(self.ledger), 'baseline': self.synthetic_original,
            'cutoff_utc': utc(self.now + 5400), 'deadline_utc': utc(self.now + 5460),
            'additional_cap_nano_usd': 5000000000, 'rates': self.original['models']['gpt-6.1-sol'],
            'role_efforts': deepcopy(runtime.ROLE_EFFORTS), 'limits': dict(runtime.role_limits(),
                forecast={'max_input_tokens': 100000, 'max_output_tokens': 25000, 'wall_seconds': 1800}),
            'slots': {role: [str(self.root / 'roles' / (role + '-01'))] for role in runtime.ROLES},
            'sources': self.source_bindings, 'population_plan': self.source_bindings[runtime.PLAN],
            'initial_population': initial, 'companies': self.ciks, 'forecast_study': study,
            'original_extra_baseline': deepcopy(runtime.EXTRA_BASELINE),
            'original_extra_cap_nano_usd': runtime.EXTRA_CAP, 'review': None}
        stack = ExitStack()
        self.addCleanup(stack.close)
        for target, name, value in [(runtime, 'ROOT', self.owned), (entry, 'REPO', self.repo),
                                    (entry, 'PILOT', self.pilot)]:
            stack.enter_context(patch.object(target, name, value))
        stack.enter_context(patch.object(runtime.time, 'time', return_value=self.now))
        stack.enter_context(patch.object(runtime, 'source_paths', return_value=self.expected))
        stack.enter_context(patch.object(runtime, '_git_source', side_effect=self.git_source))
        stack.enter_context(patch.object(tasks, 'select_companies', return_value=self.ciks))
        stack.enter_context(patch.object(tasks, 'resident', side_effect=lambda cik: deepcopy(self.residents[cik])))
        stack.enter_context(patch.object(runtime, '_ledger', side_effect=self.synthetic_ledger))
        stack.enter_context(patch('socket.socket', side_effect=AssertionError('network forbidden')))

    def git_source(self, commit, name):
        if commit != self.commit:
            raise ValueError('fixture committed source differs')
        return (self.repo / name).read_bytes()

    def synthetic_ledger(self, value):
        if value['ledger'] != str(self.ledger):
            raise ValueError('fixture sole ledger differs')
        with closing(sqlite3.connect(self.ledger.as_uri() + '?mode=ro', uri=True)) as db:
            db.execute('BEGIN')
            runtime._ledger_checks(db, value, self.synthetic_original)

    def bound(self, value=None, *, reviewed=True):
        value = deepcopy(self.value if value is None else value)
        if reviewed:
            value['review'] = save(self.owned / 'review.json', {
                'verdict': 'PASS_POPULATION_RUNTIME_SOURCE_INPUT_ONLY', 'reviewer': '/root/distinct-reviewer',
                'source_commit': value['source_commit'], 'blocking_findings': [],
                'reviewed_configuration_sha256': digest({k: v for k, v in value.items() if k != 'review'})})
        return save(self.owned / 'runtime.json', value)


class RuntimeContracts(Fixture):
    def test_positive_inert_preflight_and_exact_shared_route(self):
        bound = self.bound()
        self.assertEqual(runtime.preflight(bound)['companies'], self.ciks)
        self.assertEqual(shared.preflight_runtime(bound), runtime.preflight(bound))

    def test_review_required_and_explicit_inert_prep_only(self):
        bound = self.bound(reviewed=False)
        with self.assertRaises(ValueError):
            runtime.preflight(bound)
        self.assertEqual(runtime.preflight(bound, require_review=False)['schema'], 'earnings_population_runtime_v1')

    def test_review_root_blocker_wrong_digest_rejected(self):
        for key, change in [('reviewer', 'Root'), ('blocking_findings', ['not reviewed']),
                            ('reviewed_configuration_sha256', '0' * 64), ('source_commit', 'b' * 40)]:
            bound = self.bound()
            value = entry.strict_json(entry.checked(bound))
            review = entry.strict_json(entry.checked(value['review']))
            review[key] = change
            value['review'] = save(self.owned / 'bad-review.json', review)
            with self.subTest(key=key), self.assertRaises(ValueError):
                runtime.preflight(save(self.owned / 'runtime.json', value))

    def test_foreign_root_id_allowance_and_old_authority_rejected(self):
        changes = [('root', str(self.home / 'foreign')), ('id', 'edgar-research-20261016-28'),
                   ('additional_cap_nano_usd', 5000000001), ('original_extra_cap_nano_usd', 51000000000),
                   ('original_extra_baseline', dict(runtime.EXTRA_BASELINE, charged_nano_usd=0))]
        for key, changed in changes:
            value = deepcopy(self.value)
            value[key] = changed
            with self.subTest(key=key), self.assertRaises(ValueError):
                runtime.preflight(self.bound(value))

    def test_window_and_original_resource_limits_rejected(self):
        for key, changed in [('cutoff_utc', '2099-01-01T00:00:00Z'), ('deadline_utc', '2099-01-01T00:00:00Z')]:
            value = deepcopy(self.value)
            value[key] = changed
            with self.subTest(key=key), self.assertRaises(BudgetStop):
                runtime.preflight(self.bound(value))
        value = deepcopy(self.value)
        value['limits']['author']['max_output_tokens'] += 1
        with self.assertRaises(ValueError):
            runtime.preflight(self.bound(value))
        value = deepcopy(self.value)
        value['role_efforts']['author'] = 'max'
        with self.assertRaises(ValueError):
            runtime.preflight(self.bound(value))

    def test_role_slots_foreign_duplicate_and_overflow_rejected(self):
        for slots in [[str(self.home / 'foreign')], self.value['slots']['controller'],
                      [str(self.root / 'roles' / f'author-{i}') for i in range(4)]]:
            value = deepcopy(self.value)
            value['slots']['author'] = slots
            with self.subTest(slots=slots), self.assertRaises(ValueError):
                runtime.preflight(self.bound(value))

    def test_source_substitution_missing_and_actual_drift_rejected(self):
        value = deepcopy(self.value)
        value['sources']['factory_author'] = value['sources']['runtime']
        with self.assertRaises(ValueError):
            runtime.preflight(self.bound(value))
        value = deepcopy(self.value)
        value['sources'].pop('factory_review')
        with self.assertRaises(ValueError):
            runtime.preflight(self.bound(value))
        source = Path(self.value['sources']['runtime']['path'])
        source.write_text('changed')
        with self.assertRaises(ValueError):
            runtime.preflight(self.bound())

    def test_missing_human_authorization_or_company_definition_rejected(self):
        plan = dict(self.plan, human_authorization='old repair approval')
        self.value['population_plan'] = save(self.repo / runtime.PLAN, plan)
        self.value['sources'][runtime.PLAN] = self.value['population_plan']
        with self.assertRaises(ValueError):
            runtime.preflight(self.bound())

    def test_original_study_data_model_kernel_and_global_k_rejected(self):
        for field, changed in [('data', {'path': 'substitute', 'sha256': '0' * 64}),
                               ('model', {'requested_model': 'other'}), ('cases', []),
                               ('new_live_grant', {'path': 'old-grant'})]:
            value = deepcopy(self.value)
            study = deepcopy(self.study)
            study[field] = changed
            value['forecast_study'] = save(self.owned / 'changed-study.json', study)
            with self.subTest(field=field), self.assertRaises(ValueError):
                runtime.preflight(self.bound(value))
        value = deepcopy(self.value)
        state = entry.strict_json(entry.checked(value['initial_population']))
        anchor = state['versions'][state['anchor_id']]
        state = pool.initialize(anchor, dict(state['protected'], K='0' * 64),
                                exposed_companies=['CIK0000003545'])
        value['initial_population'] = save(self.owned / 'changed-population.json', state)
        with self.assertRaisesRegex(ValueError, 'kernel changed'):
            runtime.preflight(self.bound(value))

    def test_company_order_and_first_pilot_count_rejected(self):
        for companies in [list(reversed(self.ciks)), [], self.ciks + ['CIK0000021076']]:
            value = deepcopy(self.value)
            value['companies'] = companies
            with self.subTest(companies=companies), self.assertRaises(ValueError):
                runtime.preflight(self.bound(value))

    def test_original_pending_reserves_and_no_refund_accounting(self):
        self.db.execute("INSERT INTO requests VALUES ('pending','gpt-6.1-sol',1000000,0,'reserved')")
        self.db.commit()
        # Own in-flight loan may pass preflight; shared NightBudget still owns it.
        self.assertEqual(runtime.preflight(self.bound())['baseline'], self.synthetic_original)
        self.db.execute("UPDATE requests SET reserved=5000000001 WHERE id='pending'")
        self.db.commit()
        with self.assertRaises(BudgetStop):
            runtime.preflight(self.bound())

    def test_config_and_prefix_drift_rejected(self):
        self.db.execute('UPDATE config SET blocked=1')
        self.db.commit()
        with self.assertRaises(BudgetStop):
            runtime.preflight(self.bound())
        self.db.execute('UPDATE config SET blocked=0')
        self.db.execute("UPDATE requests SET charged=charged-1 WHERE id='prior-a'")
        self.db.commit()
        with self.assertRaises(BudgetStop):
            runtime.preflight(self.bound())

    def test_extra50_and_model100_ceiling_include_pending(self):
        value = deepcopy(self.value)
        # Advance a valid new opening prefix close to the original extra50 cap;
        # pending fits the <=5 tranche but would exceed the unchanged extra50.
        self.db.execute("INSERT INTO requests VALUES ('later','gpt-5.5',46000000000,46000000000,'settled')")
        self.db.commit()
        value['baseline'] = history_snapshot(self.db)
        self.db.execute("INSERT INTO requests VALUES ('pending','gpt-6.1-sol',5000000000,0,'reserved')")
        self.db.commit()
        with self.assertRaises(BudgetStop):
            runtime._ledger_checks(self.db, value, self.synthetic_original)
        self.db.execute("DELETE FROM requests WHERE id='pending'")
        self.db.execute("UPDATE requests SET model='gpt-5.4',reserved=19999999999,charged=19999999999 WHERE id='later'")
        self.db.commit()
        value['baseline'] = history_snapshot(self.db)
        self.db.execute("INSERT INTO requests VALUES ('pending','gpt-5.4',2,0,'reserved')")
        self.db.commit()
        with self.assertRaises(BudgetStop):
            runtime._ledger_checks(self.db, value, self.synthetic_original)

    def test_global200_ceiling_include_pending(self):
        # Pure synthetic-history probe isolates global200 from extra50 by
        # passing a synthetic original allowance; production never does so.
        self.db.execute("INSERT INTO requests VALUES ('later','gpt-5.5',62457234999,62457234999,'settled')")
        self.db.commit()
        synthetic_original = history_snapshot(self.db)
        value = deepcopy(self.value)
        value['baseline'] = synthetic_original
        self.db.execute("INSERT INTO requests VALUES ('pending','gpt-6.1-sol',2,0,'reserved')")
        self.db.commit()
        with self.assertRaises(BudgetStop):
            runtime._ledger_checks(self.db, value, synthetic_original)

    def test_new_route_is_opt_in_only(self):
        value = deepcopy(self.value)
        value['schema'] = 'earnings_capacity_runtime_v1'
        with self.assertRaises(ValueError):
            shared.preflight_runtime(self.bound(value))


if __name__ == '__main__':
    unittest.main()
