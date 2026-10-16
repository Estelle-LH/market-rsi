"""Offline original-public dry loads and inert negative adapter contracts."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import earnings_population_tasks as tasks
from edgar_forecast_audit import git_blob


class BindingHelpers(unittest.TestCase):
    def test_exact_file_and_source_drift(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root).resolve() / 'source.json'
            path.write_bytes(b'{"public":true}')
            bound = {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
            self.assertEqual(tasks._read(bound), b'{"public":true}')
            path.write_bytes(b'{"public":false}')
            with self.assertRaisesRegex(ValueError, 'hash differs'):
                tasks._read(bound)

    def test_rejects_bad_binding_and_symlink(self):
        with tempfile.TemporaryDirectory() as root:
            original = Path(root).resolve() / 'source'
            original.write_bytes(b'public')
            link = original.with_name('alias')
            link.symlink_to(original)
            sha = hashlib.sha256(b'public').hexdigest()
            for bound in [{'path': str(link), 'sha256': sha}, {'path': 'relative', 'sha256': sha},
                          {'path': str(original), 'sha256': 'x'},
                          {'path': str(original), 'sha256': sha, 'extra': True}]:
                with self.subTest(binding=bound), self.assertRaises(ValueError):
                    tasks._read(bound)

    def test_original_metadata_blob_size_and_duplicate_fail_closed(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root).resolve()
            (root / 'public').write_bytes(b'historical public data')
            metadata = {'siblings': [{'rfilename': 'public', 'size': 22,
                                      'blobId': git_blob(b'historical public data')}]}
            with patch.object(tasks, 'DATASET', root):
                self.assertEqual(tasks._upstream('public', metadata), b'historical public data')
                wrong_size = deepcopy(metadata)
                wrong_size['siblings'][0]['size'] += 1
                wrong_blob = deepcopy(metadata)
                wrong_blob['siblings'][0]['blobId'] = '0' * 40
                duplicate = deepcopy(metadata)
                duplicate['siblings'] *= 2
                for value in [wrong_size, wrong_blob, duplicate, {'siblings': []}]:
                    with self.subTest(metadata=value), self.assertRaises(ValueError):
                        tasks._upstream('public', value)
                with self.assertRaises(ValueError):
                    tasks._upstream('../public', metadata)

    def test_original_metadata_lfs(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root).resolve()
            data = b'public large-file pointer content'
            (root / 'filing').write_bytes(data)
            row = {'rfilename': 'filing', 'size': len(data),
                   'lfs': {'sha256': hashlib.sha256(data).hexdigest()}}
            with patch.object(tasks, 'DATASET', root):
                self.assertEqual(tasks._upstream('filing', {'siblings': [row]}), data)
                row['lfs']['sha256'] = '0' * 64
                with self.assertRaises(ValueError):
                    tasks._upstream('filing', {'siblings': [row]})

    def test_selection_order_exclusions_bounds_and_exhaustion(self):
        ordered = ['CIK0000003545', 'CIK0000004457', 'CIK0000017313']
        self.assertEqual(tasks._choose(ordered, {'CIK0000003545'}, 2), ordered[1:])
        self.assertEqual(tasks._choose(ordered, ['CIK0000004457'], 2), [ordered[0], ordered[2]])
        for excluded, count in [('CIK0000003545', 1), (['CIK0000003545'] * 2, 1),
                                ({'CIK9999999999'}, 1), (set(), True), (set(), 0),
                                (set(), 4), (set(ordered), 1)]:
            with self.subTest(excluded=excluded, count=count), self.assertRaises(ValueError):
                tasks._choose(ordered, excluded, count)

    def test_cutoff_uses_original_target_and_fixed_ceiling(self):
        self.assertEqual(tasks._cutoff('20260204'), '2026-02-01')
        self.assertEqual(tasks._cutoff('2026-02-02'), '2026-02-01')
        self.assertEqual(tasks._cutoff('20260120'), '2026-01-19')
        with self.assertRaises(ValueError):
            tasks._cutoff('20260230')


@unittest.skipUnless(os.environ.get('MARKET_RSI_RESIDENT_DATA_TESTS') == '1',
    'Opt-in local resident snapshots; data is deliberately not published')
class RealResidentPublicData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # No provider/network/socket, candidate code, Docker or ledger is needed.
        with patch('socket.socket', side_effect=AssertionError('network forbidden')):
            cls.plan, cls.manifest, cls.metadata = tasks._universe()
            cls.residents = {cik: tasks.resident(cik)
                for cik in ('CIK0000004457', 'CIK0000017313')}

    def test_real_full_plan_order_frozen_and_no_score_selection(self):
        self.assertEqual(tasks.select_companies({'CIK0000003545'}, 2),
                         ['CIK0000004457', 'CIK0000017313'])
        self.assertEqual(self.plan['selection'], 'all_original_CIKs_sorted')
        self.assertEqual(len(self.plan['companies']), 50)
        self.assertEqual(self.plan['target_count'], 250)

    def test_two_real_original_public_snapshots_and_kernel_identities(self):
        expected = {
            'CIK0000004457': (165, '0001193125-26-037685',
                'eaea65732f460bd5048cf6159d23db9df1d011d1ec5cb7f11cb9d04ced20db1a',
                '1f5a54b95d028abd0507985a842a4472acd68761322823b0f9f8b656552f0d8a'),
            'CIK0000017313': (304, '0000017313-26-000011',
                'b07409f4c8c52f40909096c7b1be5c2c017e3381b9632ed4e2c0fb06c130cae0',
                '4d6e5212c77ef36b9e41d21548613265da60e24edb79a2ec36ec7319da31532c')}
        for cik, value in self.residents.items():
            with self.subTest(cik=cik):
                company, case = value['company'], value['case']
                self.assertEqual(set(value), {'company', 'runtime', 'kernel', 'data_binding', 'case'})
                self.assertEqual(company, next(c for c in self.plan['companies'] if c['cik'] == cik))
                count, accession, allowed_sha, qa_sha = expected[cik]
                self.assertEqual(company['filing_count'], count)
                self.assertEqual(len(company['allowed_files']), count + 2)
                self.assertEqual(case['cutoff'], '2026-02-01')
                self.assertEqual(case['target_accession'], accession)
                self.assertEqual(case['allowed_manifest_sha256'], allowed_sha)
                self.assertEqual(case['evaluation_kernel'], value['kernel'])
                self.assertEqual(value['kernel']['qa']['sha256'], qa_sha)
                self.assertEqual(value['kernel']['scorer'], tasks.SCORER)
                self.assertEqual(value['data_binding'], tasks.FULL_PLAN)
                self.assertEqual(value['runtime']['max_input_tokens'], 100000)
                self.assertEqual(value['runtime']['max_output_tokens'], 25000)
                self.assertEqual(value['runtime']['models']['gpt-6.1-sol']['effort'], 'max')
                # Kernel carries opaque path/hash only, never protected QA content.
                self.assertEqual(set(value['kernel']['qa']), {'path', 'sha256'})
                self.assertNotIn('records', value)

    def test_protected_qa_is_not_json_decoded(self):
        original = json.loads
        protected = set(tasks._upstream(c['staged_bundle_path'] + '/forecast_benchmark_qa.json',
            self.metadata) for c in self.manifest['instances']
            if c['cik'] in self.residents)
        def no_qa_loads(data, *args, **kwargs):
            raw = data.encode() if type(data) is str else data
            if raw in protected:
                raise AssertionError('protected QA was decoded')
            return original(data, *args, **kwargs)
        with patch.object(tasks.json, 'loads', side_effect=no_qa_loads):
            for cik in self.residents:
                self.assertEqual(tasks.resident(cik)['kernel']['qa'], self.residents[cik]['kernel']['qa'])

    def test_wrong_cik_accession_cutoff_and_duplicate_company_rejected(self):
        for cik in [None, 'CIK9999999999', '../CIK0000004457']:
            with self.subTest(cik=cik), self.assertRaises(ValueError):
                tasks._company(cik, self.plan, self.manifest, self.metadata)
        for kind in ['cutoff', 'target_accession', 'duplicate']:
            plan = deepcopy(self.plan)
            company = next(c for c in plan['companies'] if c['cik'] == 'CIK0000004457')
            if kind == 'duplicate':
                plan['companies'].append(deepcopy(company))
            else:
                company[kind] = '2026-01-31' if kind == 'cutoff' else '0000000000-00-000001'
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                tasks._company('CIK0000004457', plan, self.manifest, self.metadata)

    def test_original_staged_filing_drift_rejected(self):
        plan = deepcopy(self.plan)
        company = next(c for c in plan['companies'] if c['cik'] == 'CIK0000004457')
        receipt = next(r for r in company['allowed_files'] if r['path'].startswith('filings/'))
        receipt['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'snapshot differs'):
            tasks._company(company['cik'], plan, self.manifest, self.metadata)


if __name__ == '__main__':
    unittest.main()
