"""Actual Native case admission on synthetic public fixtures, no API or runner.

Native source resolution/identity/journal are real, never mocked. Candidate
Python and protected scorer/QA bytes are not imported or executed on the host.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import earnings_population as population
from earnings_population_case import prepare_case
from earnings_open_capacity import ProgramCapacity
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine


class PopulationCaseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.serial = 0
        self.marker = self.root/'must-not-be-created'
        malicious_top_level = f"from pathlib import Path\nPath({str(self.marker)!r}).write_text('executed')\n"
        self.r = self.file('R.py', "PROGRAM={'axis':'R'}\n"+malicious_top_level+"def run(p): return {}\n")
        self.h = self.file('H.py', "PROGRAM={'axis':'H','tools':[]}\ndef run(p): return {}\n")
        self.version = population.version(self.r, self.h)
        self.python = self.file('python-inert', 'synthetic runtime bytes, never executed')
        self.authority = self.file('authority.json', json.dumps({'synthetic': True, 'paid_authority': False}))
        self.data = self.file('data.json', json.dumps({'synthetic_public_fixture': True}))
        # Intentionally invalid Python/JSON proves these protected bytes are
        # hash-verified, not imported, executed or parsed for hidden answers.
        self.scorer = self.file('scorer.py', 'opaque synthetic protected scorer, not executable Python')
        self.qa = self.file('qa.json', 'opaque synthetic protected labels, not valid JSON')
        now = datetime.now(timezone.utc).replace(microsecond=0)
        self.start = (now-timedelta(seconds=1)).strftime('%Y-%m-%dT%H:%M:%SZ')
        self.deadline = (now+timedelta(minutes=90)).strftime('%Y-%m-%dT%H:%M:%SZ')
        self.resident = self.company('CIK0000000001')

    def file(self, name, value):
        path = self.root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)
        return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

    def company(self, cik):
        visible = self.root/'public'/cik
        files = {'questions.md': '\n'.join(f'### T{i:03d} | Synthetic question' for i in range(1, 6)),
            'filing_index.tsv': 'date_filed\tform_type\taccession\tpath\n2025-01-01\t10-Q\tpublic\tfilings/10-Q_public.md\n',
            'filings/10-Q_public.md': 'Synthetic publicly available reported revenue 100.'}
        allowed = []
        for name, text in files.items():
            path = visible/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
            allowed.append({'path': name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'bytes': len(path.read_bytes())})
        company = {'cik': cik, 'cutoff': '2026-02-01', 'target_accession': 'hidden-target',
                   'visible_root': str(visible), 'allowed_files': allowed}
        kernel = {'scorer': deepcopy(self.scorer), 'qa': deepcopy(self.qa)}
        case = {key: company[key] for key in ('cik', 'cutoff', 'target_accession', 'visible_root')}
        case.update(evaluation_kernel=kernel, allowed_manifest_sha256=hashlib.sha256(
            json.dumps(company['allowed_files'], sort_keys=True, separators=(',', ':')).encode()).hexdigest())
        return {'company': company, 'runtime': {'models': {'gpt-6.1-sol': {'api_model': 'gpt-6.1-sol'}}},
                'kernel': kernel, 'data_binding': deepcopy(self.data), 'case': case}

    def prepare(self, *, resident=None, version=None, root=None, **overrides):
        arguments = {'source_commit': 'a'*40, 'authority_binding': self.authority,
                     'python_binding': self.python, 'start_utc': self.start, 'deadline_utc': self.deadline}
        arguments.update(overrides)
        return prepare_case(root or self.root/'case', resident or self.resident,
                            version or self.version, **arguments)

    def test_actual_native_case_prepares_exact_selected_sources_without_host_execution(self):
        result = self.prepare()
        self.assertIsInstance(result['capacity'], ProgramCapacity)
        self.assertEqual(result['company'], self.resident['company'])
        self.assertEqual(result['kernel'], self.resident['kernel'])
        for axis, filename in (('R', 'researcher_v0.py'), ('H', 'harness_v0.py')):
            selected = result['capacity'].resolve(axis, expected_pair_sha256=result['pair_sha256'])
            self.assertEqual(selected['receipt']['source']['sha256'], self.version[axis]['sha256'])
            self.assertEqual((result['source_root']/filename).read_bytes(), Path(self.version[axis]['path']).read_bytes())
            self.assertFalse(selected['receipt']['model_code_executed'])
        packet = result['capacity'].prepare(expected_pair_sha256=result['pair_sha256'], questions='public questions')
        self.assertFalse(packet['live_dispatch'])
        self.assertFalse(self.marker.exists())
        note = engine.read(result['context'])
        self.assertFalse(note['promotion_claimed'])
        self.assertFalse(note['model_code_executed'])
        self.assertEqual(note['provider_calls'], 0)

    def test_original_inputs_untouched_and_copied_opaque_kernel_bytes_preserved(self):
        original_resident, original_version = deepcopy(self.resident), deepcopy(self.version)
        result = self.prepare()
        self.assertEqual(self.resident, original_resident)
        self.assertEqual(self.version, original_version)
        for name, binding in (('evaluation_scorer.py', self.scorer), ('evaluation_qa.json', self.qa)):
            self.assertEqual((result['source_root']/name).read_bytes(), Path(binding['path']).read_bytes())
        self.assertFalse(self.marker.exists())

    def test_wrong_pair_refused_by_real_native_resolution(self):
        result = self.prepare()
        with self.assertRaises(ValueError):
            result['capacity'].resolve('R', expected_pair_sha256='f'*64)

    def test_mutated_researcher_source_fails_real_native_revalidation(self):
        result = self.prepare()
        (result['source_root']/'researcher_v0.py').write_text("PROGRAM={'axis':'R'}\ndef run(p): return 9\n")
        with self.assertRaises(ValueError):
            result['capacity'].resolve('R', expected_pair_sha256=result['pair_sha256'])

    def test_each_protected_source_is_checked_before_native_resolution(self):
        for index, name in enumerate(('evaluation_scorer.py', 'evaluation_qa.json', 'predictor.py')):
            result = self.prepare(root=self.root/f'case-{index}')
            (result['source_root']/name).write_bytes(b'synthetic protected-source drift')
            with self.subTest(source=name), self.assertRaises(ValueError):
                result['capacity'].resolve('H', expected_pair_sha256=result['pair_sha256'])

    def test_runtime_python_source_mutation_is_rejected(self):
        result = self.prepare()
        Path(self.python['path']).write_text('synthetic runtime drift')
        with self.assertRaises(ValueError):
            result['capacity'].resolve('R', expected_pair_sha256=result['pair_sha256'])

    def test_cold_capacity_reopen_keeps_original_pair_and_history_without_adoption(self):
        result = self.prepare()
        existing = result['capacity']
        before = existing.batch.snapshot()
        cold = ProgramCapacity(existing.batch, source_root=existing.source_root,
            registry_root=existing.registry, baseline=result['manifest'], entrypoints=existing.initial_entrypoints)
        cold.prepare(expected_pair_sha256=result['pair_sha256'], questions='synthetic public questions')
        after = cold.batch.snapshot()
        self.assertEqual(after, before)
        self.assertIsNone(after['micro_evolution']['pending'])
        self.assertEqual(after['micro_evolution']['history'], [])

    def test_every_company_and_version_gets_fresh_distinct_empty_factual_state(self):
        first = self.prepare()
        second_resident = self.company('CIK0000000002')
        second = self.prepare(resident=second_resident, root=self.root/'second-case')
        first_state = first['state_api'].load(first['initial_state'])
        second_state = second['state_api'].load(second['initial_state'])
        self.assertEqual(first_state['records'], [])
        self.assertEqual(second_state['records'], [])
        self.assertNotEqual(first['initial_state'], second['initial_state'])
        self.assertNotEqual(first['manifest']['K'], second['manifest']['K'])
        for field in ('C', 'M', 'R', 'H'):
            self.assertEqual(first['manifest'][field], second['manifest'][field])
        with self.assertRaises(ValueError):
            second['state_api'].load(first['initial_state'])

    def test_consumed_root_is_not_reopened_or_rewritten(self):
        result = self.prepare()
        before = Path(result['context']['path']).read_bytes()
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual(Path(result['context']['path']).read_bytes(), before)

    def test_input_source_authority_data_and_kernel_drift_reject_before_writing(self):
        for index, binding in enumerate((self.r, self.authority, self.data, self.scorer, self.qa)):
            path = Path(binding['path'])
            original = path.read_bytes()
            path.write_bytes(b'synthetic drift')
            root = self.root/f'refused-{index}'
            with self.subTest(binding=binding['path']), self.assertRaises(ValueError):
                self.prepare(root=root)
            self.assertFalse(root.exists())
            path.write_bytes(original)

    def test_source_commit_case_model_and_window_drift_refused(self):
        for index, fields in enumerate(({'source_commit': 'not-a-commit'},
                                       {'start_utc': self.deadline},
                                       {'deadline_utc': self.start})):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                self.prepare(root=self.root/f'bad-{index}', **fields)
        for index, key in enumerate(('case', 'runtime')):
            resident = deepcopy(self.resident)
            if key == 'case':
                resident['case']['cutoff'] = '2030-01-01'
            else:
                resident['runtime']['models']['gpt-6.1-sol']['api_model'] = 'other-model'
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.prepare(resident=resident, root=self.root/f'bad-resident-{index}')

    def test_native_worktree_root_policy_not_weakened(self):
        root = self.root/'.codex'/'worktrees'/'forbidden-native-case'
        with self.assertRaisesRegex(ValueError, 'disposable Codex worktree'):
            self.prepare(root=root)
        self.assertFalse(root.exists())


if __name__ == '__main__':
    unittest.main()
