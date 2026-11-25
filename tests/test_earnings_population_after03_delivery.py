"""Independent offline delivery tests, no model/guest/scorer/real ledger.

Native selected-source resolution, broker reads, role context, receipt writes
and observation packing are real. Generations and token counts are invented;
these checks establish payload delivery, not live model use or token headroom.
"""
from copy import deepcopy
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from edgar_forecast_tools import FilingTools
import earnings_open_researcher as researcher
import earnings_population_campaign_context as campaign_context
import earnings_population_failure_context as failure_context
import earnings_population_tasks as tasks
import earnings_open_roles as roles
from earnings_open_code import encoded
from earnings_open_broker import program_references
import earnings_population as pool
import earnings_population_broker as brokers
import earnings_population_services as services
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_open_roles as role_fixture
from test_earnings_population_campaign_integration import CampaignIntegrationFixture, CAPITAL, save
from test_earnings_open_researcher import ScriptedReceiptRunner
import test_earnings_population_case as native_fixture


class ParentSourceDelivery(CampaignIntegrationFixture):
    def explorer(self, axis='R', *, large=False):
        text = Path(self.version[axis]['path']).read_text()
        text += '\n# selected exploration parent\n'
        if large:
            text += '# ' + 'source-page-headroom-' * 1600 + '\n'
        source = self.fixture.file('explorer-' + axis + '.py', text)
        child = pool.version(source if axis == 'R' else self.version['R'],
            source if axis == 'H' else self.version['H'], parent=self.version['id'],
            axis=axis, method='Synthetic exact-parent delivery', author='inert fixture',
            evidence=[self.public_evidence])
        self.state = pool.retain(self.state, child, reason='Synthetic selected parent',
                                 evidence=[self.public_evidence])
        return child

    def test_services_reads_full_explorer_once_then_public_table_both_reach_next_request(self):
        parent = self.explorer(large=True)
        source = Path(parent['R']['path']).read_text()
        self.assertGreater(len(source), 30000)
        case = self.fixture.prepare(resident=self.resident, version=parent)
        owner = services.Services.__new__(services.Services)
        owner.runtime, owner.native_root, owner.current = self.runtime, self.root, CAPITAL
        owner.runner, owner.literature, owner.traces, owner.authored = Mock(), Mock(), {}, {}
        owner.case = Mock(return_value=case)
        owner.prior_feedback = brokers.public_feedback(self.feedback_binding, self.state['versions'])
        owner.campaign_context = self.context()
        owner.reference_context_binding = save(self.root/'parent-reference.json',
                                               owner.campaign_context['research_context'])
        author = role_fixture.OpenRoleTests()
        author.setUp(); self.addCleanup(author.doCleanups)
        role = author.service(author=True, limits={
            'max_input_tokens': 24000, 'max_output_tokens': 49152, 'wall_seconds': 900})
        # Real pack/ReceiptHTTP path, explicitly synthetic offline count replies.
        author.factory.return_value.post.side_effect = lambda endpoint, payload: {'input_tokens': 100}
        owner.contexts = {'author': (role.binding,
            {'budget': author.budget, 'client_factory': author.factory})}
        chosen = dict(author.choice(), parent_pair_sha256=parent['id'],
                      feedback_sha256=digest(self.feedback_binding))
        next_source = "PROGRAM={'axis':'R'}\ndef run(p): return {'fixture':True}\n"
        file_args = {'path': 'filings/10-Q_public.md', 'offset': 0, 'characters': 2000}
        author.generations = [
            author.tool_response(author.call('full-parent', 'read_current_program', {'axis': 'R'})),
            author.tool_response(author.call('public-table', 'read_prior_file', file_args)),
            author.message({'decision_sha256': digest(chosen),
                'parent_source_sha256': parent['R']['sha256'],
                'edits': [{'kind': 'replace', 'old_text': source, 'new_text': next_source}],
                'test_text': "CASES=[{'input':{},'expected':{'fixture':True}}]"})]
        with patch.object(services, 'resident', return_value=deepcopy(self.resident)), \
             patch.object(roles, 'budgeted_response', side_effect=author.fake_paid):
            child = owner.author(chosen, self.state, str(author.slot))
        actual = engine.read(engine.pin(author.slot/'effective-input.json'))['research_context']
        self.assertEqual(actual['parent_version_id'], parent['id'])
        self.assertEqual(actual['parent_programs'], program_references({
            axis: Path(parent[axis]['path']).read_text() for axis in ('R', 'H')}))
        self.assertNotIn(source, json.dumps(actual))  # on-demand, not huge first packet
        observations = {item['call_id']: json.loads(item['output']) for item in author.requests[-1]['input']
                        if item.get('type') == 'function_call_output'}
        self.assertEqual(observations['full-parent']['value']['source_text'], source)
        self.assertEqual(observations['full-parent']['value']['source_sha256'], parent['R']['sha256'])
        self.assertEqual(observations['public-table']['value']['text'],
                         case['state_api'].tools.files[file_args['path']])
        self.assertEqual(actual['feedback_binding'], self.feedback_binding)
        self.assertEqual(actual['original_R_evidence_abi'], self.abi)
        self.assertNotIn('HIDDEN_', json.dumps(author.requests))
        self.assertEqual(child['parent'], parent['id'])
        calls = [json.loads(p.read_bytes()) for p in sorted(self.root.glob('author-01-actions/*/intent.json'))]
        self.assertEqual([c['name'] for c in calls], ['read_current_program', 'read_prior_file'])
        self.assertFalse(self.fixture.marker.exists())
        self.assertEqual(role.context['limits'],
                         {'max_input_tokens': 24000, 'max_output_tokens': 49152, 'wall_seconds': 900})

    def test_wrong_native_researcher_or_harness_cannot_supply_an_explorer_parent(self):
        for axis in ('R', 'H'):
            child = self.explorer(axis)
            expected = program_references({key: Path(child[key]['path']).read_text() for key in ('R', 'H')})
            # Fixture Native remains the original stable pair, not this child.
            with self.subTest(axis=axis), self.assertRaisesRegex(ValueError, 'Native pair'):
                self.broker(author=True, population_changes={
                    'parent_version_id': child['id'], 'parent_programs': expected})

    def test_whole_source_descriptor_must_be_exact_not_mixed_or_wrong_axis(self):
        expected = program_references({axis: Path(self.version[axis]['path']).read_text()
                                       for axis in ('R', 'H')})
        valid = self.broker(author=True, population_changes={'parent_programs': expected})
        self.assertEqual(valid.research_context()['parent_programs'], expected)
        for axis in ('R', 'H'):
            wrong = deepcopy(expected)
            wrong[axis]['arguments']['axis'] = 'H' if axis == 'R' else 'R'
            with self.subTest(axis=axis), self.assertRaises(ValueError):
                self.broker(author=True, population_changes={'parent_programs': wrong})

    def test_existing_canonical_paged_reference_and_other_versions_remain_available(self):
        broker = self.broker(author=True)
        self.assertEqual(broker.research_context()['parent_programs'],
                         broker.references()[self.version['id']])
        result = broker.dispatch('read_population_program', {'version_id': self.version['id'],
            'axis': 'R', 'offset': 0, 'characters': 40})
        self.assertEqual(result['value']['text'], Path(self.version['R']['path']).read_text()[:40])
        self.assertEqual(result['value']['source_sha256'], self.version['R']['sha256'])

    def test_author_failure_context_must_equal_the_verified_reference_packet(self):
        with self.assertRaisesRegex(ValueError, 'rejected-source reference'):
            self.broker(author=True, population_changes={
                'failure_evidence_context': {'invented_public_excerpt': True}})


class PublicFailureExamples(unittest.TestCase):
    """Real public-file/receipt verifier on explicitly invented executions."""
    def setUp(self):
        self.data = native_fixture.PopulationCaseTests()
        self.data.setUp(); self.addCleanup(self.data.doCleanups)
        self.root = self.data.root
        self.company = self.data.company(CAPITAL)['company']
        path = Path(self.company['visible_root'])/'filings/10-Q_public.md'
        self.body = ('Amounts in thousands\n| Metric | March 31 2025 | March 31 2024 |\n'
            '| EBITDA | 19567 | 18499 |\n' + 'prefix ' * 40 + 'floating rate ' +
            'middle ' * 70 + 'interest expense ' + 'tail ' * 80 + '\n'
            'At March 31 2025 and March 31 2024, unfunded commitments were 20 and 30, respectively.\n')
        path.write_text(self.body)
        for item in self.company['allowed_files']:
            if item['path'] == 'filings/10-Q_public.md':
                item.update(sha256=hashlib.sha256(path.read_bytes()).hexdigest(), bytes=len(path.read_bytes()))
        self.owned, self.native = self.root/'owned', self.root/'native'
        self.ident = 'edgar-population-20261016-99'
        self.attempt = self.owned/'attempts'/self.ident
        source_path = self.attempt/'roles/author-01/candidate.py'
        source_path.parent.mkdir(parents=True)
        source_path.write_text("PROGRAM={'axis':'R'}\ndef run(p): return {}\n")
        self.source = engine.pin(source_path)
        self.requests = [{'tool': 'search_files', 'arguments': {'query': query,
            'path_prefix': 'filings/', 'max_hits': 50}}
            for query in ('EBITDA', 'floating rate', 'unfunded commitments', 'interest expense')]
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(failure_context, 'ROOT', self.owned))
        self.stack.enter_context(patch.object(failure_context, 'NATIVE', self.native))

    def probe(self, *, padding=0, newline=False):
        tools = FilingTools(self.company)
        payload = dict(stage='forecast', questions=tools.files['questions.md'],
                       filing_index=tools.files['filing_index.tsv'], records=[])
        runner = ScriptedReceiptRunner(self.attempt/'code', [
            {'research_requests': self.requests}, {'coverage': {'extracted_cells': 0},
                                                   'unused_padding': 'x'*padding}])
        execution = researcher.run(runner, Path(self.source['path']).read_text(), payload, tools)
        if newline:
            receipt = engine.read(execution['receipt'])
            output = Path(execution['receipt']['path']).parent/'stdout.bin'
            output.write_bytes(output.read_bytes()+b'\n')
            receipt['stdout_sha256'] = hashlib.sha256(output.read_bytes()).hexdigest()
            execution['receipt'] = save(Path(execution['receipt']['path']), receipt)
        value = dict(company_id=CAPITAL, input=payload, execution=execution,
            diagnostics={'source_sha256': self.source['sha256'],
                         'execution_sha256': execution['receipt']['sha256']})
        bound = save(self.native/('market-rsi-'+self.ident)/'review-01-forecast-probe.json', value)
        return bound

    def test_exact_snippets_nearby_header_and_different_same_line_crops_survive(self):
        bound = self.probe()
        result = failure_context.project(bound, source_binding=self.source, company=self.company)
        self.assertEqual(result['original_request_count'], 4)
        self.assertEqual(len(result['examples']), 3)
        self.assertLessEqual(len(json.dumps(result, ensure_ascii=False).encode()), failure_context.MAX_BYTES)
        for row in result['examples']:
            self.assertEqual(set(row['observed_hit']), {'path', 'line', 'text'})
            self.assertEqual(row['observed_hit_sha256'], digest(row['observed_hit']))
            context = row['outer_public_context']
            self.assertEqual(context['provided_by'], 'harness_preparation_not_R_observation')
            self.assertIn(context['read_result']['text'], self.body)
            self.assertEqual(context['text_sha256'], hashlib.sha256(context['read_result']['text'].encode()).hexdigest())
        first = result['examples'][0]
        self.assertNotIn('March 31', first['observed_hit']['text'])
        self.assertIn('March 31', first['outer_public_context']['read_result']['text'])
        pair = result['distinct_query_crops_same_line']
        self.assertEqual(len(pair), 2)
        self.assertEqual(pair[0]['observed_hit']['line'], pair[1]['observed_hit']['line'])
        self.assertNotEqual(pair[0]['observed_hit']['text'], pair[1]['observed_hit']['text'])
        self.assertTrue(all('outer_public_context' not in row for row in pair))

    def test_valid_original_stdout_above_64k_is_not_rejected_by_projection(self):
        bound = self.probe(padding=70000)
        result = failure_context.project(bound, source_binding=self.source, company=self.company)
        self.assertEqual(result['original_request_count'], 4)
        self.assertEqual(len(result['examples']), 3)

    def test_original_maximum_result_plus_print_newline_is_preserved(self):
        value = {'coverage': {'extracted_cells': 0}, 'unused_padding': ''}
        overhead = len(encoded({'ok': True, 'value': value}))
        bound = self.probe(padding=failure_context.MAX_RESULT_BYTES-overhead, newline=True)
        result = failure_context.project(bound, source_binding=self.source, company=self.company)
        self.assertEqual(len(result['examples']), 3)

    def test_saved_stdout_above_original_guest_bound_is_rejected(self):
        bound = self.probe(padding=132000)
        with self.assertRaisesRegex(ValueError, 'execution originals'):
            failure_context.project(bound, source_binding=self.source, company=self.company)

    def test_foreign_probe_or_label_source_is_refused_before_any_read(self):
        bound = self.probe()
        for probe, source in ((self.data.qa, self.source), (bound, self.data.qa)):
            with self.subTest(probe=probe['path']), patch.object(failure_context, 'checked',
                side_effect=AssertionError('foreign/QA binding must not be opened')), self.assertRaises(ValueError):
                failure_context.project(probe, source_binding=source, company=self.company)

    def test_changed_observation_cannot_be_rebound(self):
        bound = self.probe()
        value = engine.read(bound)
        value['execution']['research_observations'][0]['output']['hits'][0]['text'] = 'invented'
        changed = save(Path(bound['path']), value)
        with self.assertRaisesRegex(ValueError, 'observations differ'):
            failure_context.project(changed, source_binding=self.source, company=self.company)

    def test_wrong_company_cutoff_or_changed_source_is_refused(self):
        bound = self.probe()
        for company in (dict(self.company, cik='CIK0000000002'),
                        dict(self.company, cutoff='2024-01-01')):
            with self.subTest(company=company['cik'], cutoff=company['cutoff']), self.assertRaises(ValueError):
                failure_context.project(bound, source_binding=self.source, company=company)
        Path(self.source['path']).write_text("PROGRAM={'axis':'R'}\ndef run(p): return 5\n")
        with self.assertRaises(ValueError):
            failure_context.project(bound, source_binding=engine.pin(Path(self.source['path'])), company=self.company)


class ActualClosed03Context(unittest.TestCase):
    @unittest.skipUnless((tasks.ARTIFACTS/'edgar-population-20261016/attempts/edgar-population-20261016-03/population-run-result.json').is_file(),
                         'Optional retained local03 originals not present')
    def test_real_failed_tables_and_full_parent_reach_original_author_offline(self):
        root = tasks.ARTIFACTS/'edgar-population-20261016'
        attempt = root/'attempts/edgar-population-20261016-03'
        runtime = engine.read(engine.pin(root/'inputs/edgar-population-20261016-03/runtime-reviewed.json'))
        packet = engine.read(engine.pin(attempt/'packet-01.json'))
        packet['feedback'] = engine.pin(attempt/'feedback-01.json')
        packet['parent_feedback_sha256'] = digest(packet['feedback'])
        state = packet['population']
        public = brokers.public_feedback(packet['feedback'], state['versions'])
        with patch.object(researcher, 'run', side_effect=AssertionError('saved observations only')):
            context = campaign_context.prepare(runtime, packet, public)
        evidence = context['failure_evidence_context']
        self.assertEqual(evidence['source']['sha256'],
                         'f90ce6c04aebba3651de480e4156c0819d53ee83c7e832636ab19af63b77e8be')
        self.assertEqual(evidence['original_returned_hit_count'], 206)
        latest_q = evidence['examples'][1]
        self.assertEqual(latest_q['observed_hit']['line'], 4106)
        self.assertNotIn('2025', latest_q['observed_hit']['text'])
        self.assertIn('2025', latest_q['outer_public_context']['read_result']['text'])
        self.assertIn('19567', latest_q['outer_public_context']['read_result']['text'])
        data = native_fixture.PopulationCaseTests()
        data.setUp(); self.addCleanup(data.doCleanups)
        parent = state['versions'][state['explorers'][0]]
        original = tasks.resident(CAPITAL)
        case = data.prepare(resident=original, version=parent)
        owner = services.Services.__new__(services.Services)
        owner.runtime, owner.native_root, owner.current = runtime, data.root, CAPITAL
        owner.runner, owner.literature, owner.traces, owner.authored = Mock(), Mock(), {}, {}
        owner.case = Mock(return_value=case)
        owner.prior_feedback, owner.campaign_context = public, context
        owner.reference_context_binding = save(data.root/'real-public-reference.json', context['research_context'])
        author = role_fixture.OpenRoleTests(); author.setUp(); self.addCleanup(author.doCleanups)
        role = author.service(author=True, limits={
            'max_input_tokens': 24000, 'max_output_tokens': 49152, 'wall_seconds': 900})
        author.factory.return_value.post.side_effect = lambda endpoint, payload: {'input_tokens': 100}
        owner.contexts = {'author': (role.binding, {'budget': author.budget, 'client_factory': author.factory})}
        choice = dict(author.choice(), parent_pair_sha256=parent['id'],
                      feedback_sha256=digest(packet['feedback']))
        author.generations = [author.tool_response(author.call('source', 'read_current_program', {'axis': 'R'})),
            author.message({'decision_sha256': digest(choice),
                'parent_source_sha256': parent['R']['sha256'],
                'edits': [{'kind': 'append', 'old_text': '',
                           'new_text': '\n# Inert delivery fixture; not a scientific candidate.\n'}],
                'test_text': "CASES=[{'input':{},'expected':{}}]"})]
        with patch.object(roles, 'budgeted_response', side_effect=author.fake_paid):
            owner.author(choice, state, str(author.slot))
        initial = json.loads(author.requests[-1]['input'][0]['content'])['research_context']
        self.assertEqual(initial['failure_evidence_context'], evidence)
        self.assertEqual(json.dumps(initial).count('earnings_population_failure_context_v1'), 1)
        observation = next(item for item in author.requests[-1]['input']
                           if item.get('type') == 'function_call_output')
        delivered = json.loads(observation['output'])['value']
        self.assertEqual(delivered['source_text'], Path(parent['R']['path']).read_text())
        self.assertEqual(delivered['source_sha256'], parent['R']['sha256'])
        self.assertEqual(initial['feedback']['score_state'], 'unscored')
        self.assertEqual(initial['original_R_evidence_abi']['request_phases'], 1)
        self.assertFalse(data.marker.exists())


if __name__ == '__main__':
    unittest.main()
