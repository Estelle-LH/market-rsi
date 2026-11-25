"""Sealed historical identities are metadata, never a new holdout exposure.

Portable tests exercise the real narrow scanner. The explicitly opted-in local
test reconstructs actual closed03 with ordinary source/receipt/accounting
checks, forbidding non-development resident loads and file opens. It does not
execute candidates, call a model, run a scorer or grant a new run.
"""
from contextlib import ExitStack
from copy import deepcopy
import builtins
import io
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

import earnings_population_campaign_resume as resume
import earnings_population_continuation as history
import earnings_population_rejection as rejection
import earnings_population_tasks as tasks
from market_rsi import digest

DEV = frozenset({'CIK0000003545', 'CIK0000004457', 'CIK0000017313'})
STUDY = resume.OWNED/'inputs'/rejection.IDENT/'study.json'


def sealed_metadata():
    """Only saved metadata/source configuration; never load a resident case."""
    qa_path = (tasks.DATASET/'runs/forecast_clean_35_v1/companies'/rejection.VALIDATION
               /'benchmarks/0000021076-26-000010/forecast_benchmark_qa.json')
    case = dict(cik=rejection.VALIDATION, cutoff='2026-02-01',
        target_accession='0000021076-26-000010',
        visible_root=str(tasks.ARTIFACTS/'edgar-model-scoring-20261007/pilot-01'
                         /'full-openai-20261008-01/visible'/rejection.VALIDATION),
        allowed_manifest_sha256='3bc2ce301d721390402d569cf30ddef46b92ca841f757c9496085c24ca7b38e7',
        evaluation_kernel=dict(scorer=deepcopy(tasks.SCORER), qa=dict(path=str(qa_path),
            sha256='c02e960c2c345fe41e1ad6f406c8d07e97a2d7721d79f04d5b1b4bab0248435d')))
    return dict(cases=[case], runtime_config=json.loads(Path(tasks.RUNTIME['path']).read_bytes()))


class SealedMetadataContracts(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        self.reader = rejection._SealedHistoryReader(root, root/'unused.sqlite3', root/'repo', 'synthetic')
        self.study = sealed_metadata()
        self.resident = rejection._sealed_resident(self.reader, self.study)
        self.qa = self.study['cases'][0]['evaluation_kernel']['qa']

    def test_exact_nested_sealed_binding_is_metadata_not_an_opaque_file_read(self):
        with patch.object(history._Reader, 'read', side_effect=AssertionError('Must not open sealed bytes')):
            self.reader.scan({'nested': [self.qa, {'qa': deepcopy(self.qa)}]})
        self.assertEqual(self.resident['case'], self.study['cases'][0])
        self.assertEqual(self.reader.extra, set())

    def test_changed_case_qa_path_hash_or_runtime_is_not_accepted_as_saved_metadata(self):
        variants = []
        for field, value in [('cik', 'CIK0000003545'), ('cutoff', '2026-02-02'),
                             ('allowed_manifest_sha256', '0'*64)]:
            item = deepcopy(self.study); item['cases'][0][field] = value; variants.append(item)
        for field, value in [('path', self.qa['path']+'.foreign'), ('sha256', '0'*64)]:
            item = deepcopy(self.study); item['cases'][0]['evaluation_kernel']['qa'][field] = value
            variants.append(item)
        item = deepcopy(self.study); item['runtime_config']['max_turns_per_company'] += 1; variants.append(item)
        for study in variants:
            with self.subTest(study_digest=digest(study)), self.assertRaises(ValueError):
                rejection._sealed_resident(self.reader, study)

    def test_same_path_different_hash_is_not_a_scan_exception(self):
        with self.assertRaisesRegex(ValueError, 'metadata changed'):
            self.reader.scan(dict(self.qa, sha256='0'*64))

    def test_direct_read_and_rehash_refuse_even_if_path_were_registered(self):
        self.reader.extra.add(Path(self.qa['path']))
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('No sealed file open')):
            with self.assertRaisesRegex(ValueError, 'only remain metadata'):
                self.reader.read(self.qa, binary=True)
            with self.assertRaisesRegex(ValueError, 'not be reopened'):
                self.reader.pin(Path(self.qa['path']))

    def test_scanner_does_not_skip_foreign_bindings_or_fake_bytes(self):
        foreign = dict(path='/private/tmp/foreign-heldout-qa.json', sha256='0'*64)
        with patch.object(history._Reader, 'read', side_effect=ValueError('Ordinary binding validation')) as read:
            with self.assertRaisesRegex(ValueError, 'Ordinary binding'):
                self.reader.scan({'nested': [foreign]})
        read.assert_called_once_with(foreign, binary=True)

    def test_old_default_still_selects_original_reader_and_opt_in_is_explicit(self):
        binding = dict(path=str(resume.OWNED/'attempts'/rejection.IDENT/'population-run-failure.json'),
                       sha256=rejection.FAILURE_SHA)
        args = dict(root=resume.OWNED, ledger=resume.LEDGER, repo=resume.REPO)
        with patch.object(history, '_Reader', side_effect=RuntimeError('Legacy reader selected')):
            with self.assertRaisesRegex(RuntimeError, 'Legacy reader'):
                rejection.load_closed_review_rejection(binding, **args)
        with self.assertRaisesRegex(ValueError, 'Explicit boolean'):
            rejection.load_closed_review_rejection(binding, **args, sealed_history='yes')


@unittest.skipUnless(os.environ.get('MARKET_RSI_VERIFY_SEALED_HISTORY') == '1',
                     'Explicit local read-only historical audit opt-in required')
class ActualClosed03SealedReadAudit(unittest.TestCase):
    def test_actual03_reconstructs_without_any_non_dev_resident_or_file_open(self):
        observed_residents, opened = [], []
        original_resident = tasks.resident

        def resident(cik):
            if cik not in DEV:
                raise AssertionError('Sealed non-development resident: '+str(cik))
            observed_residents.append(cik)
            return original_resident(cik)

        def guard(function):
            def checked(path, *args, **kwargs):
                if not isinstance(path, int):
                    value = os.fsdecode(path)
                    companies = set(re.findall(r'CIK[0-9]{10}', value))
                    if companies-DEV:
                        raise AssertionError('Sealed non-development file open: '+value)
                    opened.append(value)
                return function(path, *args, **kwargs)
            return checked

        result_binding = dict(path=str(resume.OWNED/'attempts'/resume.IDENT/'population-run-result.json'),
                              sha256=resume.RESULT_SHA)
        with ExitStack() as stack:
            stack.enter_context(patch.object(tasks, 'resident', side_effect=resident))
            for module in (builtins, io, os):
                stack.enter_context(patch.object(module, 'open', guard(module.open)))
            result = resume.load(result_binding, root=resume.OWNED, ledger=resume.LEDGER, repo=resume.REPO)
        self.assertTrue(observed_residents)
        self.assertLessEqual(set(observed_residents), DEV)
        self.assertTrue(opened)
        self.assertTrue(all(not (set(re.findall(r'CIK[0-9]{10}', p))-DEV) for p in opened))
        self.assertEqual(digest(result['population']), 'b4b657f387462a49f6a52bc964d8922d73d886b90fd6b6e95ad6f596a7370ce9')
        self.assertEqual(result['research_feedback']['kind'], 'review_rejected')
        self.assertEqual(result['research_feedback']['score_state'], 'unscored')
        self.assertEqual(result['research_feedback']['results'], [])
        self.assertEqual(result['research_feedback']['last_scored_feedback'], result['last_scored_feedback'])
        self.assertTrue(result['reference_candidate']['reference_only'])
        self.assertNotIn(result['reference_candidate']['id'], result['population']['versions'])
        self.assertEqual(result['previous_result'], result_binding)


if __name__ == '__main__':
    unittest.main()
