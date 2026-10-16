"""Completed-only inheritance probes; synthetic journal writes, no paid work."""
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import earnings_population as pool
import earnings_population_continuation as continuation
import earnings_population_tasks as tasks
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
from supervisor_harness import feedback_linked_loop as driver


class ContinuationContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()
        self.root, self.repo, self.ledger = self.home / 'owned', self.home / 'repo', self.home / 'pilot/api-budget.sqlite3'
        self.commit = 'a' * 40
        self.bytes = {}
        for name in [continuation.DRIVER, 'tools/earnings_population_loop.py',
                     'tools/earnings_population_run.py', 'tools/earnings_population_services.py',
                     'tools/edgar_forecast_openai.py']:
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            raw = Path(driver.__file__).read_bytes() if name == continuation.DRIVER else ('# old fixture ' + name).encode()
            path.write_bytes(raw)
            self.bytes[name] = raw
        self.sources = {name: engine.pin(self.repo / name) for name in self.bytes}
        self.sources['forecaster'] = self.sources['tools/edgar_forecast_openai.py']
        original = self.home / 'original'
        original.mkdir()
        self.full = engine.save(original / 'full.json', {'synthetic_full50': True})
        self.scorer = engine.save(original / 'scorer.json', {'synthetic_opaque_scorer': True})
        self.runtime_config = {'models': {'gpt-6.1-sol': {'api_model': 'gpt-6.1-sol', 'effort': 'max'}}}
        self.runtime_source = self.write(self.repo / 'benchmarks/runtime.json', self.runtime_config)
        self.bytes['benchmarks/runtime.json'] = Path(self.runtime_source['path']).read_bytes()
        self.model = {'requested_model': 'gpt-6.1-sol', 'serving_snapshot': 'unknown', 'serving_snapshot_verified': False}
        self.residents = {}
        for cik in ['CIK0000004457', 'CIK0000017313', 'CIK0000021076']:
            qa = engine.save(original / (cik + '.json'), {'opaque_fixture': True})
            self.residents[cik] = {'runtime': self.runtime_config, 'kernel': {'qa': qa, 'scorer': self.scorer},
                'case': {'cik': cik, 'cutoff': '2026-02-01', 'evaluation_kernel': {'qa': qa, 'scorer': self.scorer}}}
        stack = ExitStack()
        self.addCleanup(stack.close)
        for target, key, value in [(continuation, 'OWNED', self.root), (continuation, 'LEDGER', self.ledger),
                (continuation, 'REPO', self.repo), (tasks, 'FULL_PLAN', self.full),
                (tasks, 'SCORER', self.scorer), (tasks, 'RUNTIME', self.runtime_source)]:
            stack.enter_context(patch.object(target, key, value))
        stack.enter_context(patch.object(continuation, '_git', side_effect=self.git))
        stack.enter_context(patch.object(tasks, 'resident', side_effect=lambda cik: deepcopy(self.residents[cik])))
        stack.enter_context(patch('socket.socket', side_effect=AssertionError('network forbidden')))
        self.first = self.build('edgar-population-20261016-01', ['CIK0000004457'])

    def git(self, repo, commit, name):
        if repo != self.repo or commit != self.commit:
            raise ValueError('fixture Git source commit differs')
        return self.bytes[name]

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        return engine.save(path, value)

    def build(self, ident, companies, inherited=None, previous=None, *, kernel_evidence=False, extra_evidence=()):
        inputs, attempt = self.root / 'inputs' / ident, self.root / 'attempts' / ident
        inputs.mkdir(parents=True)
        attempt.mkdir(parents=True)
        if inherited is None:
            r, h = self.write(inputs / 'R.py', {'source': 'R'}), self.write(inputs / 'H.py', {'source': 'H'})
            state = pool.initialize(pool.version(r, h), {'K': digest({'data': self.full, 'scorer': self.scorer}),
                'M': digest(self.model), 'C': self.sources['forecaster']['sha256']}, exposed_companies=['CIK0000003545'])
            feedback = {'schema': 'earnings_population_seed_v1', 'scope': 'synthetic only'}
        else:
            state, feedback = inherited['population'], inherited['feedback']
        initial = self.write(inputs / 'initial.json', state)
        study = {'schema': 'earnings_coevolution_study_v1', 'data': self.full, 'scorer': self.scorer,
            'sole_ledger': str(self.ledger), 'runtime_config': self.runtime_config, 'model': self.model,
            'cases': [self.residents[c]['case'] for c in companies]}
        if inherited is not None:
            study['continuation'] = self.write(inputs / 'continuation.json', {
                'schema': 'earnings_population_continuation_v1', 'previous_result': previous,
                'population_sha256': digest(state), 'feedback': feedback, 'evidence': inherited['evidence']})
        study_bound = self.write(inputs / 'study.json', study)
        runtime = {'schema': 'earnings_population_runtime_v1', 'id': ident, 'root': str(attempt),
            'ledger': str(self.ledger), 'source_commit': self.commit, 'sources': self.sources,
            'forecast_study': study_bound, 'initial_population': initial, 'companies': companies,
            'rates': self.runtime_config['models']['gpt-6.1-sol'],
            'original_extra_baseline': continuation.EXTRA_BASELINE, 'original_extra_cap_nano_usd': continuation.EXTRA_CAP,
            'additional_cap_nano_usd': 5000000000, 'baseline': {'rows_sha256': 'b' * 64},
            'cutoff_utc': '2030-01-01T00:00:00Z', 'deadline_utc': '2030-01-01T00:01:00Z', 'review': None}
        runtime['review'] = self.write(inputs / 'review.json', {'verdict': 'PASS_POPULATION_RUNTIME_SOURCE_INPUT_ONLY',
            'reviewer': '/root/fixture-reviewer', 'blocking_findings': [], 'source_commit': self.commit,
            'reviewed_configuration_sha256': digest({k: v for k, v in runtime.items() if k != 'review'})})
        runtime_bound = self.write(inputs / 'runtime.json', runtime)
        common = {'adapter': self.sources['tools/earnings_population_loop.py'],
            'services': {role: {'function': 'Services.' + role, 'module': self.sources['tools/earnings_population_services.py']}
                         for role in ('controller', 'author', 'review', 'forecast')},
            'admission': {'function': 'execute.<locals>.admit', 'module': self.sources['tools/earnings_population_run.py']}}
        def identity():
            return {stage: dict(common, stage=stage) for stage in driver.STAGES}
        def simple(ctx):
            return {'synthetic_stage': True}
        def result_review(ctx):
            previous_state = ctx['previous_result']['population']
            index = ctx['round_index']
            receipt = self.write(attempt / f'trial-{index}.json', {'synthetic': True})
            evidence = [receipt]
            if kernel_evidence:
                # Real execution receipts carry opaque kernel bindings through
                # results -> observations/history -> the next window's seed.
                # Use this company's original fixture bindings, not QA values.
                kernel = self.residents[companies[index - 1]]['kernel']
                evidence += [deepcopy(kernel['scorer']), deepcopy(kernel['qa'])]
            measured = [{'version_id': previous_state['stable_id'], 'points': 1,
                         'evidence': evidence + deepcopy(list(extra_evidence))}]
            fb = self.write(attempt / f'feedback-{index:02d}.json', {'schema': 'earnings_population_feedback_v1',
                'company_id': companies[index - 1], 'results': measured,
                'stable_id': previous_state['stable_id'], 'round_index': index, 'synthetic': True})
            return {'population': pool.observe(previous_state, companies[index - 1], measured, feedback=fb),
                    'feedback': fb}
        def reconcile(ctx):
            value = ctx['outputs']['result_review']
            pop = self.write(attempt / f'population-{ctx["round_index"]:02d}.json', value['population'])
            return dict(value, company_id=companies[ctx['round_index'] - 1], artifacts=[pop, value['feedback']])
        handlers = {stage: simple for stage in driver.STAGES}
        handlers.update(result_review=result_review, reconcile=reconcile)
        journal = driver.run(attempt / 'loop', handlers, seed={'population': state, 'feedback': feedback, 'companies': companies},
                             admit=lambda ctx: True, max_rounds=len(companies), handler_identity=identity)
        budget = {'blocked': False, 'unresolved_reserved_usd': 0, 'cap_usd': 200, 'model_cap_usd': 100,
            'night_cap_usd': 5, 'charged_upper_bound_usd': 140, 'night_charged_upper_bound_usd': 1,
            'prior_history_sha256': 'b' * 64}
        clock = self.write(attempt / 'clock.json', {'source_commit': self.commit,
            'cutoff_utc': runtime['cutoff_utc'], 'deadline_utc': runtime['deadline_utc']})
        self.write(attempt / 'clock.binding.json', clock)
        result = self.write(attempt / 'population-run-result.json', {'status': 'COMPLETED_DISCOVERY_PILOT',
            'retry_allowed': False, 'improvement_proven': False, 'budget': budget, 'result': journal})
        token = hashlib.sha256(ident.encode()).hexdigest()
        registry = self.ledger.parent / '.capacity-runtime-claims'
        self.write(registry / (token + '.json'), {'id': ident, 'runtime': runtime_bound,
            'source_commit': self.commit, 'retry_allowed': False})
        self.write(registry / (token + '.result.json'), {'status': 'COMPLETED_COMPONENT_CONTEXT',
            'error_type': None, 'retry_allowed': False, 'runtime': runtime_bound, 'budget_summary': budget, 'clock': clock})
        return result

    def load(self, bound=None):
        return continuation.load(self.first if bound is None else bound, root=self.root, ledger=self.ledger, repo=self.repo)

    def rebind_continuation(self, ident, manifest):
        inputs = self.root / 'inputs' / ident
        (inputs / 'continuation.json').write_text(json.dumps(manifest))
        study = engine.read(engine.pin(inputs / 'study.json'))
        study['continuation'] = engine.pin(inputs / 'continuation.json')
        (inputs / 'study.json').write_text(json.dumps(study))
        runtime = engine.read(engine.pin(inputs / 'runtime.json'))
        runtime['forecast_study'] = engine.pin(inputs / 'study.json')
        review = engine.read(runtime['review'])
        review['reviewed_configuration_sha256'] = digest({k: v for k, v in runtime.items() if k != 'review'})
        (inputs / 'review.json').write_text(json.dumps(review))
        runtime['review'] = engine.pin(inputs / 'review.json')
        (inputs / 'runtime.json').write_text(json.dumps(runtime))
        token = hashlib.sha256(ident.encode()).hexdigest()
        for suffix in ['.json', '.result.json']:
            path = self.ledger.parent / '.capacity-runtime-claims' / (token + suffix)
            value = engine.read(engine.pin(path))
            value['runtime'] = engine.pin(inputs / 'runtime.json')
            path.write_text(json.dumps(value))

    def test_completed_read_only_load_and_historical_source_changes(self):
        before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in self.home.rglob('*') if p.is_file()}
        result = self.load()
        self.assertEqual(result['population']['exposed_companies'], ['CIK0000003545', 'CIK0000004457'])
        self.assertEqual(len(result['evidence']), 8)
        self.assertEqual(before, {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in self.home.rglob('*') if p.is_file()})
        (self.repo / 'tools/earnings_population_loop.py').write_bytes(b'# new current code')
        with self.assertRaises(Exception):
            driver.replay_completed(Path(self.first['path']).parent / 'loop',
                manifest_binding=engine.pin(Path(self.first['path']).parent / 'loop/manifest.json'))
        self.assertEqual(self.load()['population'], result['population'])

    def test_two_windows_inherit_exact_pool_last_feedback_and_exposures(self):
        first = self.load()
        second = self.build('edgar-population-20261016-02', ['CIK0000017313'], first, self.first)
        result = self.load(second)
        self.assertEqual(result['population']['exposed_companies'],
                         ['CIK0000003545', 'CIK0000004457', 'CIK0000017313'])
        self.assertEqual(result['population']['anchor_id'], first['population']['anchor_id'])
        self.assertGreater(len(result['evidence']), len(first['evidence']))

    def test_second_window_inherits_original_qa_bindings_nested_in_history_without_decoding(self):
        first_binding = self.build('edgar-population-20261016-03', ['CIK0000004457'], kernel_evidence=True)
        first = self.load(first_binding)
        qa = self.residents['CIK0000004457']['kernel']['qa']
        self.assertIn(qa, first['population']['observations'][0]['results'][0]['evidence'])
        self.assertIn(qa, first['population']['history'][-1]['body']['results'][0]['evidence'])
        second = self.build('edgar-population-20261016-04', ['CIK0000017313'], first, first_binding,
                            kernel_evidence=True)
        strict_json = continuation.e.strict_json
        opaque_qa_bytes = Path(qa['path']).read_bytes()
        def no_qa_decode(raw):
            self.assertNotEqual(raw, opaque_qa_bytes, 'QA must be hashed as opaque bytes, never decoded')
            return strict_json(raw)
        with patch.object(continuation.e, 'strict_json', side_effect=no_qa_decode):
            result = self.load(second)
        self.assertEqual(result['population']['observations'][:-1], first['population']['observations'])
        self.assertIn(qa, result['population']['observations'][0]['results'][0]['evidence'])
        self.assertEqual(result['population']['exposed_companies'],
                         ['CIK0000003545', 'CIK0000004457', 'CIK0000017313'])

    def test_mutated_ancestor_qa_is_rehashed_and_rejected(self):
        first_binding = self.build('edgar-population-20261016-03', ['CIK0000004457'], kernel_evidence=True)
        first = self.load(first_binding)
        second = self.build('edgar-population-20261016-04', ['CIK0000017313'], first, first_binding,
                            kernel_evidence=True)
        qa = Path(self.residents['CIK0000004457']['kernel']['qa']['path'])
        qa.write_bytes(qa.read_bytes() + b'\nopaque fixture mutation')
        with self.assertRaisesRegex(ValueError, 'hash differs'):
            self.load(second)

    def test_unrelated_company_qa_is_not_allowed_by_shared_original_directory(self):
        first_binding = self.build('edgar-population-20261016-03', ['CIK0000004457'], kernel_evidence=True)
        first = self.load(first_binding)
        unrelated = self.residents['CIK0000021076']['kernel']['qa']
        second = self.build('edgar-population-20261016-04', ['CIK0000017313'], first, first_binding,
                            kernel_evidence=True, extra_evidence=[unrelated])
        with self.assertRaisesRegex(ValueError, 'outside exact owned roots'):
            self.load(second)

    def test_unrelated_file_is_not_allowed_as_ancestor_kernel_evidence(self):
        first_binding = self.build('edgar-population-20261016-03', ['CIK0000004457'], kernel_evidence=True)
        first = self.load(first_binding)
        unrelated = self.write(self.home / 'original/unrelated.json', {'opaque_unrelated_fixture': True})
        second = self.build('edgar-population-20261016-04', ['CIK0000017313'], first, first_binding,
                            kernel_evidence=True, extra_evidence=[unrelated])
        with self.assertRaisesRegex(ValueError, 'outside exact owned roots'):
            self.load(second)

    def test_missing_done_and_orphaned_failure_rejected(self):
        path = Path(self.first['path']).parent / 'loop/round-0001-input.failed.json'
        self.write(path, {'synthetic_failed': True})
        with self.assertRaises(ValueError):
            self.load()
        path.unlink()
        done = path.with_name('round-0001-input.done.json')
        done.unlink()
        with self.assertRaises((ValueError, FileNotFoundError)):
            self.load()

    def test_changed_claim_and_final_population_rejected(self):
        path = Path(self.first['path']).parent / 'loop/round-0001-input.claim.json'
        original = path.read_bytes()
        path.write_bytes(b'{}')
        with self.assertRaises(ValueError):
            self.load()
        path.write_bytes(original)
        population = Path(self.first['path']).parent / 'population-01.json'
        population.write_bytes(b'{}')
        with self.assertRaises(ValueError):
            self.load()

    def test_owner_failure_or_pending_at_close_rejected(self):
        token = hashlib.sha256('edgar-population-20261016-01'.encode()).hexdigest()
        owner = self.ledger.parent / '.capacity-runtime-claims' / (token + '.result.json')
        original = engine.read(engine.pin(owner))
        for change in [{'status': 'FAILED_NO_RETRY'}, {'budget_summary': dict(original['budget_summary'], unresolved_reserved_usd=1)}]:
            owner.write_text(json.dumps(dict(original, **change)))
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.load()

    def test_prior_failed_marker_stays_closed_even_with_completed_result(self):
        self.write(Path(self.first['path']).parent / 'population-run-failure.json', {'status': 'FAILED_NO_RETRY'})
        with self.assertRaisesRegex(ValueError, 'remains closed'):
            self.load()

    def test_wrong_historical_git_bytes_rejected_not_current_file_substitution(self):
        with patch.object(continuation, '_git', return_value=b'not the committed old source'):
            with self.assertRaisesRegex(ValueError, 'hash differs'):
                self.load()

    def test_clock_tamper_rejected_without_recreating_or_renewing_it(self):
        clock = Path(self.first['path']).parent / 'clock.json'
        clock.write_text('{"source_commit":"wrong"}')
        with self.assertRaisesRegex(ValueError, 'hash differs'):
            self.load()

    def test_foreign_roots_paths_and_symlink_rejected_before_read(self):
        with self.assertRaises(ValueError):
            continuation.load(self.first, root=self.home, ledger=self.ledger, repo=self.repo)
        foreign = dict(self.first, path=str(self.home / 'foreign/population-run-result.json'))
        with self.assertRaises(ValueError):
            self.load(foreign)
        result_path = Path(self.first['path'])
        moved = result_path.with_name('saved-result.json')
        result_path.rename(moved)
        result_path.symlink_to(moved)
        with self.assertRaises(ValueError):
            self.load()

    def test_cross_window_wrong_feedback_population_digest_and_cycle_rejected(self):
        first = self.load()
        second = self.build('edgar-population-20261016-02', ['CIK0000017313'], first, self.first)
        manifest_path = self.root / 'inputs/edgar-population-20261016-02/continuation.json'
        manifest = engine.read(engine.pin(manifest_path))
        for key, changed in [('population_sha256', '0' * 64), ('feedback', {'path': str(self.home / 'foreign'), 'sha256': '0' * 64})]:
            self.rebind_continuation('edgar-population-20261016-02', dict(manifest, **{key: changed}))
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'Cross-window'):
                self.load(second)
        self.rebind_continuation('edgar-population-20261016-02', dict(manifest, previous_result=second))
        with self.assertRaisesRegex(ValueError, 'noncyclic'):
            self.load(second)
        with self.assertRaises(ValueError):
            continuation._load(self.first, self.root, self.ledger, self.repo, {'edgar-population-20261016-01'})


class HistoricalCodeCache(unittest.TestCase):
    def test_only_immutable_git_commit_bytes_are_cached(self):
        continuation._git.cache_clear()
        self.addCleanup(continuation._git.cache_clear)
        with patch.object(continuation.subprocess, 'run', return_value=SimpleNamespace(stdout=b'old source')) as run:
            self.assertEqual(continuation._git(continuation.REPO, 'a' * 40, 'tools/a.py'), b'old source')
            self.assertEqual(continuation._git(continuation.REPO, 'a' * 40, 'tools/a.py'), b'old source')
            self.assertEqual(run.call_count, 1)
            continuation._git(continuation.REPO, 'b' * 40, 'tools/a.py')
            self.assertEqual(run.call_count, 2)


if __name__ == '__main__':
    unittest.main()
