"""Inert continued preparation probes; CT loader is independently mocked here."""
from contextlib import redirect_stderr
from copy import deepcopy
import io
from pathlib import Path
import runpy
import sys
import unittest
from unittest.mock import patch

import earnings_entry as entry
import earnings_population as pool
import earnings_population_continuation as ct
import earnings_population_run as run
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_population_run as original_entry


def inherited_fixture(root, stable, protected):
    old = root / 'attempts/edgar-population-20261016-01'
    old.mkdir(parents=True, exist_ok=True)
    previous = engine.save(old / 'population-run-result.json', {'synthetic_closed_result': True})
    child_path = old / 'model-researcher.py'
    child_path.write_bytes(b'PROGRAM={"axis":"R"}\ndef run(payload): return {"synthetic":True}\n')
    state = pool.initialize(stable, protected, exposed_companies=['CIK0000003545'])
    child = pool.version(engine.pin(child_path), stable['H'], parent=stable['id'], axis='R',
                         method='synthetic retained algorithm', author='fixture:model', evidence=[previous])
    state = pool.retain(state, child, reason='test inherited capability', evidence=[previous])
    for index, cik in enumerate(['CIK0000004457', 'CIK0000017313'], 1):
        results = [{'version_id': ident, 'points': 1, 'evidence': [previous]}
                   for ident in [state['stable_id'], *state['explorers']]]
        fb = engine.save(old / f'feedback-{index:02d}.json', {'schema': 'earnings_population_feedback_v1',
            'company_id': cik, 'results': results, 'stable_id': state['stable_id'], 'round_index': index})
        state = pool.observe(state, cik, results, feedback=fb)
    return {'population': state, 'feedback': fb, 'evidence': [previous]}, previous


class ContinuedPreparation(original_entry.PreparationContracts):
    def setUp(self):
        super().setUp()
        self.id = 'edgar-population-20261016-02'
        self.plan_continue = engine.save(self.repo / run.CONTINUATION_PLAN, {
            'schema': 'supervisor_bottleneck_plan_v1', 'id': 'earnings-population-continuation-20261016',
            'human_authorization': run.CONTINUATION_AUTHORIZATION})
        run.source_paths.return_value[run.CONTINUATION_PLAN] = self.plan_continue['path']
        seed = self.owned / 'seed'
        seed.mkdir(parents=True)
        r, h = engine.save(seed / 'R.py', {'old': 'R'}), engine.save(seed / 'H.py', {'old': 'H'})
        self.inherited, self.previous = inherited_fixture(self.owned, pool.version(r, h),
            {'K': digest({'data': run.FULL_PLAN, 'scorer': run.SCORER}), 'M': 'd' * 64, 'C': 'e' * 64})
        self.loader_patch = patch.object(ct, 'load', side_effect=self.load_prior)
        self.loader = self.loader_patch.start()
        self.addCleanup(self.loader_patch.stop)
        self.select_patch = patch.object(run, 'select_companies', side_effect=lambda excluded, count:
            [c for c in ['CIK0000003545', 'CIK0000004457', 'CIK0000017313', 'CIK0000021076', 'CIK0000030625']
             if c not in excluded][:count])
        self.select = self.select_patch.start()
        self.addCleanup(self.select_patch.stop)

    def load_prior(self, binding, **kwargs):
        if binding != self.previous:
            raise ValueError('fixture rejects foreign or unverified previous result')
        self.assertEqual(kwargs, {'root': self.owned, 'ledger': entry.PILOT / 'api-budget.sqlite3', 'repo': self.repo})
        return deepcopy(self.inherited)

    def test_continued_pool_feedback_and_versions_preserved_without_copy_or_reset(self):
        before = deepcopy(self.inherited)
        with (patch.object(run, 'save_bytes', wraps=run.save_bytes) as copying,
              patch.object(run, 'initialize', wraps=run.initialize) as resetting):
            bound = run.prepare(self.id, continue_from=self.previous['path'], company_count=1,
                                repair_parent=self.inherited['population']['explorers'][0])
        value = engine.read(bound)
        state = engine.read(value['initial_population'])
        study = engine.read(value['forecast_study'])
        manifest = engine.read(study['continuation'])
        self.assertEqual(state, before['population'])
        self.assertEqual(manifest['feedback'], before['feedback'])
        self.assertEqual(manifest['evidence'], before['evidence'])
        self.assertEqual(manifest['population_sha256'], digest(state))
        self.assertEqual(manifest['previous_result'], self.previous)
        self.assertEqual(manifest['plan'], value['sources'][run.CONTINUATION_PLAN])
        self.assertEqual(manifest['repair'], {'schema': 'earnings_population_human_repair_v1',
            'parent_version_id': state['explorers'][0], 'human_authorization': run.CONTINUATION_AUTHORIZATION})
        self.assertEqual(value['companies'], ['CIK0000021076'])
        self.select.assert_called_once_with(state['exposed_companies'], 1)
        self.assertEqual(value['baseline'], self.baseline)
        self.assertEqual(value['original_extra_baseline'], run.EXTRA_BASELINE)
        self.assertEqual(value['original_extra_cap_nano_usd'], 50000000000)
        self.assertEqual(value['additional_cap_nano_usd'], 5000000000)
        self.assertIsNone(value['review'])
        copying.assert_not_called()
        resetting.assert_not_called()
        self.assertFalse((self.owned / 'inputs' / self.id / 'R.py').exists())
        self.assertFalse((self.owned / 'inputs' / self.id / 'H.py').exists())

    def test_continue_without_human_repair_retains_exact_state(self):
        bound = run.prepare(self.id, continue_from=self.previous['path'], company_count=1)
        value = engine.read(bound)
        manifest = engine.read(engine.read(value['forecast_study'])['continuation'])
        self.assertIsNone(manifest['repair'])
        self.assertEqual(engine.read(value['initial_population']), self.inherited['population'])

    def test_repair_nonactive_or_no_prior_rejected_before_inputs(self):
        for parent in [self.inherited['population']['stable_id'], 'f' * 64]:
            with self.subTest(parent=parent), self.assertRaises(ValueError):
                run.prepare(self.id, continue_from=self.previous['path'], company_count=1, repair_parent=parent)
            self.assertFalse((self.owned / 'inputs' / self.id).exists())
        with self.assertRaises(ValueError):
            run.prepare(self.id, repair_parent=self.inherited['population']['explorers'][0])

    def test_foreign_prior_is_rejected_before_any_file_bytes_are_read(self):
        foreign = self.home / 'foreign.json'
        foreign.write_bytes(b'owned negative fixture, not another Supervisor')
        original = Path.read_bytes
        def guarded(path):
            if path == foreign:
                raise AssertionError('foreign previous-result bytes read before ownership check')
            return original(path)
        with patch.object(Path, 'read_bytes', guarded), self.assertRaises(ValueError):
            run.prepare(self.id, continue_from=str(foreign), company_count=1)
        self.assertFalse((self.owned / 'inputs' / self.id).exists())

    def test_invalid_company_counts_fail_without_loader_or_idle(self):
        for count in [0, 3, True]:
            with self.subTest(count=count), self.assertRaises(ValueError):
                run.prepare(self.id, continue_from=self.previous['path'], company_count=count)
        self.loader.assert_not_called()
        self.idle.assert_not_called()

    def test_cli_continuation_flags_are_prepare_only(self):
        for flags in [['--continue-from', 'not-read.json'], ['--companies', '1'], ['--repair-parent', 'a' * 64]]:
            with (self.subTest(flags=flags), patch.object(sys, 'argv', ['entry', '--runtime', 'not-read.json', *flags]),
                  redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught):
                runpy.run_module('earnings_population_run', run_name='__main__')
            self.assertEqual(caught.exception.code, 2)


class ContinuedRepairExecutionGate(original_entry.ExecutionContracts):
    """Guard-only owner/loop fixtures; not source/admission/live proof."""
    def repair_study(self):
        self.study['continuation'] = original_entry.save(self.owned / 'repair.json', {
            'repair': {'schema': 'earnings_population_human_repair_v1',
                       'parent_version_id': 'c' * 64,
                       'human_authorization': run.CONTINUATION_AUTHORIZATION}})
        self.value['forecast_study'] = original_entry.save(self.owned / 'study.json', self.study)

    def test_rejected_assigned_repair_stops_before_redundant_forecasts(self):
        self.repair_study()
        dispatched = []
        def guarded_loop(root, state, companies, roles, *, admit, max_rounds):
            self.assertTrue(admit({'round_index': 1, 'stage': 'controller', 'outputs': {}}))
            admit({'round_index': 1, 'stage': 'execute', 'outputs': {
                'source_review': {'accepted_for_exploration': False}}})
            dispatched.append('must not dispatch predictions')
        self.loop.side_effect = guarded_loop
        with patch.object(run, 'preflight', side_effect=engine.read), self.assertRaisesRegex(ValueError, 'redundant'):
            run.execute(self.bound())
        self.assertEqual(dispatched, [])
        self.assertTrue(self.closed)
        self.assertFalse((self.root / 'population-run-result.json').exists())
        self.assertEqual(engine.read(engine.pin(self.root / 'population-run-failure.json'))['status'], 'FAILED_NO_RETRY')

    def test_review_acceptance_allows_only_bounded_original_loop_path(self):
        self.repair_study()
        dispatched = []
        def guarded_loop(root, state, companies, roles, *, admit, max_rounds):
            self.assertTrue(admit({'round_index': 1, 'stage': 'execute', 'outputs': {
                'source_review': {'accepted_for_exploration': True}}}))
            dispatched.append((companies, max_rounds))
            return {'synthetic_gate_path': True, 'not_real_forecasts': True}
        self.loop.side_effect = guarded_loop
        with patch.object(run, 'preflight', side_effect=engine.read):
            result = engine.read(run.execute(self.bound()))
        self.assertEqual(dispatched, [(self.ciks, len(self.ciks))])
        self.assertEqual(result['status'], 'COMPLETED_DISCOVERY_PILOT')
        self.assertFalse(result['improvement_proven'])


if __name__ == '__main__':
    unittest.main()
