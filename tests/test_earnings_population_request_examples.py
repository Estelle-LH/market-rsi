"""Original receipt/public-file verification, then bounded C/A evidence delivery.

All companies, filings and execution outputs are synthetic. The original guest
receipt verifier and FilingTools dispatch are real; no candidate code, Docker,
API, scorer, original labels or production ledger is executed/read. The final
receiving test uses an explicitly synthetic historical-origin seam only.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import earnings_open_researcher as researcher
import earnings_population_campaign_context as context_api
import earnings_population_failure_context as failure_context
import earnings_population_tasks as tasks
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_population_after03_delivery as delivery
import test_earnings_population_campaign_integration as integration

REAL_PROJECT = failure_context.project
REAL_REQUEST_EXAMPLES = context_api._request_examples


class RequestReturnExamples(unittest.TestCase):
    def setUp(self):
        self.public = delivery.PublicFailureExamples()
        self.public.setUp()
        self.addCleanup(self.public.doCleanups)

    def projection(self, bound=None):
        bound = bound or self.public.probe()
        verified = REAL_PROJECT(bound, source_binding=self.public.source, company=self.public.company)
        return bound, verified, REAL_REQUEST_EXAMPLES(bound, verified, source_binding=self.public.source)

    def receiving(self, bound):
        row = {'stage': 'forecast', 'company_id': integration.CAPITAL,
               'source_sha256': self.public.source['sha256'], 'receipt': bound}
        with patch.object(tasks, 'resident', return_value={'company': self.public.company}):
            return context_api._failure_context({'source': self.public.source}, {'probes': [row]},
                {'company_id': integration.CAPITAL, 'probes': [row]})

    def test_all_eight_requests_include_late_search_read_calculate_and_no_hits(self):
        self.public.requests += [
            {'tool': 'read_file', 'arguments': {'path': 'filings/10-Q_public.md', 'offset': 0, 'characters': 400}},
            {'tool': 'calculate', 'arguments': {'expression': '2+3'}},
            {'tool': 'search_files', 'arguments': {'query': 'no_such_public_text', 'path_prefix': 'filings/', 'max_hits': 1}},
            {'tool': 'search_files', 'arguments': {'query': 'interest expense', 'path_prefix': 'filings/', 'max_hits': 1}}]
        bound, verified, result = self.projection()
        original = engine.read(bound)['execution']['research_observations']
        self.assertEqual(len(verified['examples']), 3)  # Legacy selection remains unchanged.
        self.assertEqual(result['original_request_count'], 8)
        self.assertEqual([r['request_index'] for r in result['examples']], list(range(8)))
        for index, row in enumerate(result['examples']):
            self.assertEqual(row['request'], original[index]['request'])
            self.assertEqual(row['request_sha256'], digest(original[index]['request']))
            self.assertEqual(row['complete_return_sha256'], digest(original[index]['output']))
        self.assertEqual(result['examples'][4]['returned']['offset'], 0)
        self.assertIn('Amounts in thousands', result['examples'][4]['returned']['text'])
        self.assertEqual(result['examples'][5]['returned'], {'value': 5})
        self.assertEqual(result['examples'][6]['returned_hit_count'], 0)
        self.assertIsNone(result['examples'][6]['first_original_hit'])
        self.assertEqual(result['examples'][7]['request']['arguments']['query'], 'interest expense')
        self.assertIn('cannot establish that all hits are irrelevant', result['scope'])

    def test_total_matching_returned_and_sampled_counts_are_distinct(self):
        self.public.requests = [{'tool': 'search_files', 'arguments': {
            'query': '|', 'path_prefix': 'filings/', 'max_hits': 1}}]
        bound, _, result = self.projection()
        output = engine.read(bound)['execution']['research_observations'][0]['output']
        example = result['examples'][0]
        self.assertGreater(output['total_matching_lines'], len(output['hits']))
        self.assertEqual(example['total_matching_lines'], output['total_matching_lines'])
        self.assertEqual(example['returned_hit_count'], 1)
        self.assertEqual(example['sampled_returned_hit_count'], 1)
        self.assertEqual(example['backend_omitted_hit_count'], output['total_matching_lines']-1)
        self.assertEqual(example['omitted_returned_hit_count'], 0)
        self.assertEqual(set(example['first_original_hit']), {'path', 'line', 'text'})
        self.assertEqual(example['complete_first_hit_sha256'], digest(output['hits'][0]))

    def test_prefix_truncation_keeps_original_provenance_and_requests(self):
        bound, _, result = self.projection()
        original = engine.read(bound)['execution']['research_observations'][1]['output']['hits'][0]
        example = result['examples'][1]
        self.assertTrue(example['first_hit_text_truncated'])
        self.assertEqual(example['first_original_hit']['text'], original['text'][:240])
        self.assertEqual(example['first_hit_text_original_characters'], len(original['text']))
        self.assertEqual(example['complete_first_hit_sha256'], digest(original))
        self.assertNotIn('source_sha256', example['first_original_hit'])
        self.assertNotIn('offset', example['first_original_hit'])

    def test_utf8_bound_adapts_prefixes_without_dropping_request_rows(self):
        path = Path(self.public.company['visible_root'])/'filings/10-Q_public.md'
        path.write_text(('浮'*600+'\n')*8)
        for item in self.public.company['allowed_files']:
            if item['path'] == 'filings/10-Q_public.md':
                item.update(sha256=hashlib.sha256(path.read_bytes()).hexdigest(), bytes=path.stat().st_size)
        self.public.requests = [{'tool': 'search_files', 'arguments': {
            'query': '浮', 'path_prefix': 'filings/', 'max_hits': 1}} for _ in range(8)]
        # Exercise clipping independently of the now16KiB production bound.
        with patch.object(context_api, 'REQUEST_EXAMPLES_MAX_BYTES', 8192):
            _, _, result = self.projection()
        self.assertEqual(len(result['examples']), 8)
        self.assertLess(result['bounds']['text_prefix_characters_max'], 240)
        size = len(json.dumps(result, sort_keys=True, ensure_ascii=False, allow_nan=False).encode())
        self.assertLessEqual(size, 8192)
        self.assertTrue(all(row['first_hit_text_truncated'] for row in result['examples']))

    def test_unbounded_exact_request_metadata_fails_closed_not_silently_dropped(self):
        self.public.requests = [{'tool': 'search_files', 'arguments': {
            'query': '浮'*200, 'path_prefix': 'filings/', 'max_hits': 1}} for _ in range(8)]
        bound = self.public.probe()
        verified = REAL_PROJECT(bound, source_binding=self.public.source, company=self.public.company)
        with patch.object(context_api, 'REQUEST_EXAMPLES_MAX_BYTES', 8192):
            with self.assertRaisesRegex(ValueError, 'metadata exceeds bounded extension'):
                REAL_REQUEST_EXAMPLES(bound, verified, source_binding=self.public.source)

    def test_extension_does_not_change_original_packet_raw_probe_or_source(self):
        bound = self.public.probe()
        original_bytes = Path(bound['path']).read_bytes()
        source_bytes = Path(self.public.source['path']).read_bytes()
        baseline = REAL_PROJECT(bound, source_binding=self.public.source, company=self.public.company)
        with patch.object(researcher, 'run', side_effect=AssertionError('saved evidence only')):
            result = self.receiving(bound)
        extension = result.pop('request_return_examples')
        self.assertEqual(result, baseline)
        self.assertLessEqual(len(json.dumps(baseline, sort_keys=True, ensure_ascii=False).encode()), 24576)
        self.assertEqual(extension['probe'], bound)
        self.assertEqual(Path(bound['path']).read_bytes(), original_bytes)
        self.assertEqual(Path(self.public.source['path']).read_bytes(), source_bytes)
        self.assertEqual(extension['bounds']['serialized_extension_utf8_bytes_max'], 16384)

    def test_eight_rows_with_realistic_owned_paths_fail_old8k_but_fit16k(self):
        # Reproduce ordinary metadata overhead, not a fabricated huge query or
        # permission change. Original verifier and public-file dispatch are real.
        company = self.public.company
        root = Path(company['visible_root'])
        logical = 'filings/10-Q_'+'public-evidence-'*3+'.md'
        query = 'public request original literal query for evidence'
        body = '\n'.join(query+' '+('uninterpreted snippet '*15) for _ in range(4))
        (root/logical).write_text(body)
        index = (root/'filing_index.tsv').read_text().replace('filings/10-Q_public.md', logical)
        (root/'filing_index.tsv').write_text(index)
        for item in company['allowed_files']:
            if item['path'] == 'filings/10-Q_public.md':
                item['path'] = logical
            path = root/item['path']
            item.update(sha256=hashlib.sha256(path.read_bytes()).hexdigest(), bytes=path.stat().st_size)
        self.public.requests = [{'tool': 'search_files', 'arguments': {
            'query': query, 'path_prefix': 'filings/', 'max_hits': 1}} for _ in range(8)]
        bound = self.public.probe()
        verified = REAL_PROJECT(bound, source_binding=self.public.source, company=company)
        with patch.object(context_api, 'REQUEST_EXAMPLES_MAX_BYTES', 8192):
            with self.assertRaisesRegex(ValueError, 'metadata exceeds bounded extension'):
                REAL_REQUEST_EXAMPLES(bound, verified, source_binding=self.public.source)
        result = REAL_REQUEST_EXAMPLES(bound, verified, source_binding=self.public.source)
        size = len(json.dumps(result, sort_keys=True, ensure_ascii=False, allow_nan=False).encode())
        self.assertEqual([r['request_index'] for r in result['examples']], list(range(8)))
        self.assertEqual(result['bounds']['text_prefix_characters_max'], 240)
        self.assertGreater(size, 8192)
        self.assertLessEqual(size, 16384)
        self.assertTrue(all(row['request']['arguments']['query'] == query for row in result['examples']))

    def test_original_legacy_probe_without_company_label_remains_valid(self):
        bound = self.public.probe()
        value = engine.read(bound)
        del value['company_id']
        bound = integration.save(Path(bound['path']), value)
        _, verified, result = self.projection(bound)
        self.assertEqual(verified['company_id'], integration.CAPITAL)
        self.assertEqual(result['original_request_count'], 4)

    def test_wrong_verified_source_or_probe_refused_before_read(self):
        bound, verified, _ = self.projection()
        for field in ('schema', 'probe', 'source'):
            wrong = deepcopy(verified)
            wrong[field] = 'wrong' if field == 'schema' else dict(wrong[field], sha256='0'*64)
            with self.subTest(field=field), patch.object(engine, 'read',
                    side_effect=AssertionError('unmatched binding must not be read')):
                with self.assertRaisesRegex(ValueError, 'same verified'):
                    REAL_REQUEST_EXAMPLES(bound, wrong, source_binding=self.public.source)

    def test_changed_verified_metadata_or_observation_digest_refused(self):
        bound, verified, _ = self.projection()
        for field, value in (('company_id', 'CIK0000000002'), ('stage', 'controller'),
                ('first_execution', {'path': '/wrong', 'sha256': '0'*64}),
                ('final_execution', {'path': '/wrong', 'sha256': '0'*64}),
                ('original_request_count', 5), ('original_observations_sha256', '0'*64)):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'same verified'):
                REAL_REQUEST_EXAMPLES(bound, dict(verified, **{field: value}), source_binding=self.public.source)

    def test_changed_actual_observation_rejected_by_original_verifier(self):
        bound = self.public.probe()
        value = engine.read(bound)
        value['execution']['research_observations'][0]['output']['hits'][0]['text'] = 'invented'
        bound = integration.save(Path(bound['path']), value)
        with self.assertRaisesRegex(ValueError, 'observations differ'):
            self.receiving(bound)

    def test_stale_probe_hash_and_rebound_source_diagnostics_are_rejected(self):
        bound = self.public.probe()
        value = engine.read(bound)
        value['diagnostics']['source_sha256'] = '0'*64
        integration.save(Path(bound['path']), value)
        with self.assertRaises(ValueError):
            self.receiving(bound)  # Stale immutable binding.
        with self.assertRaisesRegex(ValueError, 'diagnostics lost'):
            self.receiving(engine.pin(Path(bound['path'])))

    def test_foreign_original_binding_rejected_by_real_verifier_before_read(self):
        with patch.object(failure_context, 'checked', side_effect=AssertionError('foreign bytes must stay sealed')):
            with self.assertRaises(ValueError):
                self.receiving(self.public.data.qa)

    def test_no_source_matching_probe_stays_absent_not_invented(self):
        bound = self.public.probe()
        row = {'stage': 'forecast', 'company_id': integration.CAPITAL,
               'source_sha256': '0'*64, 'receipt': bound}
        with patch.object(engine, 'read', side_effect=AssertionError('no matching probe to read')):
            self.assertIsNone(context_api._failure_context({'source': self.public.source}, {'probes': [row]},
                {'company_id': integration.CAPITAL, 'probes': [row]}))

    def test_typed_error_summary_is_bounded_without_inventing_success(self):
        # Pure rendering seam, not a claim FilingTools accepts error outputs.
        bound, verified, _ = self.projection()
        probe = engine.read(bound)
        rows = probe['execution']['research_observations']
        rows[0]['output'] = {'error': {'type': 'SyntheticError', 'message': 'x'*400}}
        verified = dict(verified, original_observations_sha256=digest(rows))
        with patch.object(engine, 'read', return_value=probe):
            result = REAL_REQUEST_EXAMPLES(bound, verified, source_binding=self.public.source)
        example = result['examples'][0]
        self.assertEqual(example['kind'], 'error')
        self.assertEqual(example['error_type'], 'dict')
        self.assertTrue(example['error_prefix_truncated'])
        self.assertNotIn('returned_hit_count', example)

    def test_real_verified_extension_reaches_controller_and_author_broker(self):
        # Only historical-origin assembly is invented; the probe/projector,
        # exact public FilingTools reconstruction and both broker contexts are real.
        bound = self.public.probe()
        fixture = integration.CampaignIntegrationFixture()
        fixture.setUp(); self.addCleanup(fixture.doCleanups)
        fixture.resident['company'] = deepcopy(self.public.company)
        for key in ('cik', 'cutoff', 'target_accession', 'visible_root'):
            fixture.resident['case'][key] = self.public.company[key]
        fixture.resident['case']['allowed_manifest_sha256'] = digest(self.public.company['allowed_files'])
        fixture.rejected_source = self.public.source
        fixture.reference['source'] = deepcopy(self.public.source)
        fixture.feedback['rejected_candidate'] = deepcopy(fixture.reference)
        fixture.feedback['probes'][0].update(receipt=bound, source_sha256=self.public.source['sha256'])
        fixture.origin.update(research_feedback=fixture.feedback, reference_candidate=fixture.reference)
        fixture.refresh()
        with patch.object(failure_context, 'project', REAL_PROJECT), \
             patch.object(context_api, '_request_examples', REAL_REQUEST_EXAMPLES):
            context = fixture.context()
            full = context['failure_evidence_context']['request_return_examples']
            controller = context_api.controller_view(context['research_context'])
            self.assertEqual(controller['observations']['public_failure_examples']['request_return_examples'], full)
            author = fixture.broker(author=True).research_context(include_source=True)
            self.assertEqual(author['failure_evidence_context']['request_return_examples'], full)
            self.assertEqual(len(full['examples']), 4)
            self.assertEqual(full['examples'][3]['request']['arguments']['query'], 'interest expense')
            self.assertEqual(author['feedback_binding'], fixture.feedback_binding)
            original = engine.read(fixture.feedback_binding)
            self.assertEqual(original, fixture.feedback)
            self.assertNotIn('request_return_examples', json.dumps(original))
            self.assertFalse(fixture.fixture.marker.exists())
            sent, fake_paid = [], integration.role_fixture.OpenRoleTests.fake_paid
            original_service = integration.role_fixture.OpenRoleTests.service
            def service(role, *args, **kwargs):
                result = original_service(role, *args, **kwargs)
                role.factory.return_value.post.return_value = {'input_tokens': 100}
                return result
            def capture(role, client, request, rates, limits, budget, output, turn, *, prepared_count=None):
                value = fake_paid(role, client, request, rates, limits, budget, output, turn,
                                  prepared_count=prepared_count)
                sent.append(deepcopy(request))
                return value
            # Exercise original Services -> C/A effective-input -> completed
            # request construction, with explicitly invented counts/generations.
            with patch.object(integration.role_fixture.OpenRoleTests, 'fake_paid', capture), \
                 patch.object(integration.role_fixture.OpenRoleTests, 'service', service):
                integration.ActualRoleInputContracts.test_actual_controller_and_author_effective_inputs_include_rejection_and_original_R_ABI(fixture)
            self.assertEqual(len(sent), 2)
            controller_body, author_body = [json.loads(request['input'][0]['content']) for request in sent]
            self.assertEqual(controller_body['research_context']['observations']
                ['public_failure_examples']['request_return_examples'], full)
            self.assertEqual(author_body['research_context']['failure_evidence_context']
                ['request_return_examples'], full)

    def test_old_context_without_extension_stays_readable(self):
        _, verified, _ = self.projection()
        old = {'schema': 'earnings_repair_context_v1',
               'observations': {'public_failure_examples': verified}}
        result = context_api.controller_view(old)
        self.assertNotIn('request_return_examples', result['observations']['public_failure_examples'])
        self.assertTrue(result['planning_view']['omitted_nearby_text_characters'])


class Actual18RequestExamples(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('MARKET_RSI_VERIFY_REQUEST_EXAMPLES18') == '1',
                         'Explicit opt-in for retained owned18 public receipt only')
    def test_real_original18_all8_rows_fit16k_without_changing_original_projection(self):
        root = Path('/__LOCAL_RESEARCH_HOME__/.codex/worktrees/3c5e/self-evolving-v18-local/artifacts/edgar-population-20261016')
        bound = {'path': '/private/tmp/market-rsi-edgar-population-20261016-18/review-01-forecast-probe.json',
                 'sha256': 'b91c557212d2965c25e0cd081c69e7cfa7c0f36931fd44bf91a9f7356af26937'}
        source = {'path': str(root/'attempts/edgar-population-20261016-18/roles/author-01/candidate.py'),
                  'sha256': '466cc46f7b6e148df71038852c30213b2521ba391bf63479d2f5e7a5de9011c7'}
        # Full-plan metadata is hash checked. Select only Capital's original
        # public snapshot; do not load any company QA or held-out body/questions.
        plan = json.loads(tasks._read(tasks.FULL_PLAN))
        company = next(row for row in plan['companies'] if row['cik'] == integration.CAPITAL)
        with patch.object(researcher, 'run', side_effect=AssertionError('saved original evidence only')):
            verified = REAL_PROJECT(bound, source_binding=source, company=company)
            result = REAL_REQUEST_EXAMPLES(bound, verified, source_binding=source)
        size = len(json.dumps(result, sort_keys=True, ensure_ascii=False, allow_nan=False).encode())
        self.assertEqual(size, 9421)
        self.assertEqual(len(json.dumps(verified, sort_keys=True, ensure_ascii=False,
                                       allow_nan=False).encode()), 18893)
        self.assertEqual(result['bounds']['serialized_extension_utf8_bytes_max'], 16384)
        self.assertEqual(result['bounds']['existing_failure_projection_utf8_bytes_max'], 24576)
        self.assertEqual(result['bounds']['text_prefix_characters_max'], 240)
        self.assertEqual([row['request_index'] for row in result['examples']], list(range(8)))
        self.assertLessEqual(size, context_api.REQUEST_EXAMPLES_MAX_BYTES)


if __name__ == '__main__':
    unittest.main()
