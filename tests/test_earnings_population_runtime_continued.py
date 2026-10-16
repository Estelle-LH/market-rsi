"""Actual continuation admission under inert source/ledger/CT-loader fixtures."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

import earnings_entry as entry
import earnings_population as pool
import earnings_population_continuation as ct
import earnings_population_runtime as runtime
from edgar_forecast_budget import BudgetStop
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_population_runtime as base
from test_earnings_population_prepare_continued import inherited_fixture


class ContinuedRuntime(base.Fixture):
    def setUp(self):
        super().setUp()
        self.id = 'edgar-population-20261016-02'
        self.root = self.owned / 'attempts' / self.id
        self.value.update(id=self.id, root=str(self.root))
        self.value['slots'] = {role: [str(self.root / 'roles' / (role + '-01'))]
                               for role in runtime.ROLES}
        self.latest_plan = base.save(self.repo / runtime.CONTINUATION_PLAN, {
            'schema': 'supervisor_bottleneck_plan_v1', 'id': 'earnings-population-continuation-20261016',
            'human_authorization': runtime.CONTINUATION_AUTHORIZATION})
        self.expected[runtime.CONTINUATION_PLAN] = self.latest_plan['path']
        self.value['sources'][runtime.CONTINUATION_PLAN] = self.latest_plan
        old = engine.read(self.value['initial_population'])
        self.inherited, self.previous = inherited_fixture(self.owned,
            old['versions'][old['stable_id']], old['protected'])
        self.value['initial_population'] = base.save(self.owned / 'initial.json', self.inherited['population'])
        self.ciks = ['CIK0000021076']
        runtime.tasks.select_companies.return_value = self.ciks
        self.residents[self.ciks[0]] = deepcopy(next(iter(self.residents.values())))
        self.residents[self.ciks[0]]['case']['cik'] = self.ciks[0]
        self.value['companies'] = self.ciks
        self.study['cases'] = [self.residents[c]['case'] for c in self.ciks]
        self.manifest = {'schema': 'earnings_population_continuation_v1', 'previous_result': self.previous,
            'population_sha256': digest(self.inherited['population']), 'feedback': self.inherited['feedback'],
            'evidence': self.inherited['evidence'], 'plan': self.latest_plan,
            'repair': {'schema': 'earnings_population_human_repair_v1',
                'parent_version_id': self.inherited['population']['explorers'][0],
                'human_authorization': runtime.CONTINUATION_AUTHORIZATION}}
        self.write_manifest(self.manifest)
        self.loader_patch = patch.object(ct, 'load', side_effect=self.prior)
        self.loader = self.loader_patch.start()
        self.addCleanup(self.loader_patch.stop)
        # Base fixture's source map / Git reader and synthetic original ledger
        # prefix remain inert; preflight itself is actual production code.

    def prior(self, binding, **kwargs):
        self.assertEqual(kwargs, {'root': self.owned, 'ledger': self.ledger, 'repo': self.repo})
        if binding != self.previous:
            raise ValueError('CT fixture rejects foreign/unverified result')
        return deepcopy(self.inherited)

    def write_manifest(self, manifest):
        self.study['continuation'] = base.save(self.owned / 'continuation.json', manifest)
        self.value['forecast_study'] = base.save(self.owned / 'study.json', self.study)

    def test_actual_preflight_accepts_exact_continuation_without_budget_reset(self):
        value = runtime.preflight(self.bound())
        self.assertEqual(value['initial_population'], self.value['initial_population'])
        self.assertEqual(value['baseline'], self.synthetic_original)
        self.assertEqual(value['original_extra_baseline'], runtime.EXTRA_BASELINE)
        self.assertEqual(value['original_extra_cap_nano_usd'], 50000000000)
        self.assertEqual(value['additional_cap_nano_usd'], 5000000000)
        self.loader.assert_called_once_with(self.previous, root=self.owned, ledger=self.ledger, repo=self.repo)
        self.assertEqual(engine.read(value['initial_population']), self.inherited['population'])

    def test_stale_feedback_wrong_digest_and_changed_evidence_rejected(self):
        stale = self.inherited['population']['observations'][0]['feedback']
        for key, changed in [('feedback', stale), ('population_sha256', '0' * 64), ('evidence', [])]:
            self.write_manifest(dict(self.manifest, **{key: changed}))
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'continuation required'):
                runtime.preflight(self.bound())

    def test_prior_foreign_binding_delegates_to_verified_loader_and_fails(self):
        self.write_manifest(dict(self.manifest, previous_result={'path': str(self.home / 'foreign.json'), 'sha256': '0' * 64}))
        with self.assertRaisesRegex(ValueError, 'CT fixture rejects'):
            runtime.preflight(self.bound())

    def test_history_without_continuation_and_reset_pool_rejected(self):
        self.study.pop('continuation')
        self.value['forecast_study'] = base.save(self.owned / 'study.json', self.study)
        with self.assertRaisesRegex(ValueError, 'silently reset'):
            runtime.preflight(self.bound())
        self.write_manifest(self.manifest)
        old = self.inherited['population']
        reset = pool.initialize(old['versions'][old['anchor_id']], old['protected'],
                                exposed_companies=['CIK0000003545'])
        self.value['initial_population'] = base.save(self.owned / 'initial.json', reset)
        with self.assertRaisesRegex(ValueError, 'continuation required'):
            runtime.preflight(self.bound())

    def test_latest_authorization_plan_identity_and_registered_source_required(self):
        changed = {'schema': 'supervisor_bottleneck_plan_v1',
            'id': 'earnings-population-continuation-20261016', 'human_authorization': 'old approval'}
        plan = base.save(self.repo / runtime.CONTINUATION_PLAN, changed)
        self.value['sources'][runtime.CONTINUATION_PLAN] = plan
        self.write_manifest(dict(self.manifest, plan=plan))
        with self.assertRaisesRegex(ValueError, 'human continuation plan'):
            runtime.preflight(self.bound())

    def test_repair_parent_must_be_active_explorer_and_exact_human_task(self):
        for parent in [self.inherited['population']['stable_id'], 'f' * 64]:
            repair = dict(self.manifest['repair'], parent_version_id=parent)
            self.write_manifest(dict(self.manifest, repair=repair))
            with self.subTest(parent=parent), self.assertRaisesRegex(ValueError, 'actual inherited explorer'):
                runtime.preflight(self.bound())
        repair = dict(self.manifest['repair'], human_authorization='unrelated old task')
        self.write_manifest(dict(self.manifest, repair=repair))
        with self.assertRaises(ValueError):
            runtime.preflight(self.bound())

    def test_null_repair_valid_but_independent_review_still_required(self):
        self.write_manifest(dict(self.manifest, repair=None))
        self.assertEqual(runtime.preflight(self.bound())['companies'], self.ciks)
        with self.assertRaises(ValueError):
            runtime.preflight(self.bound(reviewed=False))

    def test_no_original_prefix_global_or_extra_allowance_reset(self):
        value = deepcopy(self.value)
        value['original_extra_baseline']['charged_nano_usd'] -= 1
        with self.assertRaises(ValueError):
            runtime.preflight(self.bound(value))
        value = deepcopy(self.value)
        value['original_extra_cap_nano_usd'] += 1
        with self.assertRaises(ValueError):
            runtime.preflight(self.bound(value))
        self.db.execute('UPDATE config SET cap=201000000000')
        self.db.commit()
        with self.assertRaises(BudgetStop):
            runtime.preflight(self.bound())


if __name__ == '__main__':
    unittest.main()
