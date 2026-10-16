"""Inert human-repair/Author/reviewer handoffs; no API, Docker or real ledger.

Role transport and company-loader boundaries are explicit fixtures. Native,
source hashes, prior FilingTools, original execution verifier and diagnostics
projection remain real on invented public data/synthetic execution originals.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import earnings_open_roles as open_roles
from earnings_population_broker import PopulationBroker
from earnings_population_diagnostics import project
from earnings_population_roles import PopulationController
import earnings_population_services as services
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_open_roles as role_fixture
import test_earnings_open_researcher as receipt_fixture
import test_earnings_population_case as native_fixture
import test_earnings_population_services as service_fixture


class RepairControllerTests(unittest.TestCase):
    def setUp(self):
        self.fixture = role_fixture.OpenRoleTests()
        self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        base = self.fixture.service(max_turns=1)
        self.role = PopulationController(base.binding, budget=self.fixture.budget,
            client_factory=self.fixture.factory, broker=self.fixture.broker, max_turns=1)
        self.prompt = {'active_versions': ['a'*64, 'c'*64], 'explorers': ['c'*64],
            'feedback_sha256': 'b'*64, 'feedback': {'synthetic_diagnostics': True},
            'repair_assignment': {'schema': 'earnings_population_human_repair_v1', 'parent_version_id': 'c'*64}}

    def chosen(self, **changes):
        result = self.fixture.choice(); result.update(parent_pair_sha256='c'*64, retire_branch_id='none')
        result.update(changes)
        return result

    def invoke(self, chosen):
        self.fixture.generations = [self.fixture.message(chosen)]
        with patch.object(open_roles, 'budgeted_response', side_effect=self.fixture.fake_paid):
            return self.role.propose(self.prompt, str(self.fixture.slot))

    def test_first_slot_repair_forces_declared_parent_R_scope_without_rewriting_reply(self):
        chosen = self.chosen()
        before = deepcopy(chosen)
        original = self.invoke(chosen)
        projection = engine.read(engine.pin(self.fixture.slot/'decision.json'))
        self.assertEqual(projection['decision'], {key: value for key, value in chosen.items() if key != 'retire_branch_id'})
        self.assertEqual(chosen, before)
        self.assertEqual(Path(original['path']).read_bytes(), (self.fixture.slot/'01-response.json').read_bytes())
        fields = self.fixture.requests[0]['text']['format']['schema']['properties']
        self.assertEqual(fields['axis']['enum'], ['R'])
        self.assertEqual(fields['component']['enum'], ['research_policy'])
        self.assertEqual(fields['parent_pair_sha256']['enum'], ['c'*64])
        self.assertEqual(fields['feedback_sha256']['enum'], ['b'*64])

    def test_assigned_continue_or_wrong_parent_is_rejected_not_rewritten(self):
        for changes in ({'axis': 'continue', 'component': 'none'}, {'parent_pair_sha256': 'a'*64},
                        {'axis': 'H', 'component': 'tool_interface'}):
            captured = []
            def decode(prompt, slot, instructions, fmt, decoder, artifact, status):
                captured.append(fmt)
                return decoder(self.fixture.message(self.chosen(**changes)))
            self.role._run_open = decode
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.role.propose(self.prompt, str(self.fixture.slot))

    def test_repair_assignment_only_first_declared_slot_and_active_explorer(self):
        second = self.fixture.root/'roles'/'controller-02'
        for prompt, slot in ((self.prompt, second),
            (dict(self.prompt, repair_assignment={'schema': 'earnings_population_human_repair_v1',
                                                 'parent_version_id': 'a'*64}), self.fixture.slot)):
            with self.subTest(slot=str(slot)), self.assertRaises(ValueError):
                self.role.propose(prompt, str(slot))
        self.assertEqual(self.fixture.requests, [])

    def test_default_without_assignment_still_allows_continue(self):
        self.prompt.pop('repair_assignment')
        self.invoke(self.chosen(axis='continue', component='none'))
        fields = self.fixture.requests[0]['text']['format']['schema']['properties']
        self.assertEqual(fields['axis']['enum'], ['R', 'H', 'continue'])


class PopulationAuthorContextTests(unittest.TestCase):
    def setUp(self):
        self.fixture = native_fixture.PopulationCaseTests()
        self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        self.case = self.fixture.prepare()
        self.prior = self.fixture.company('CIK0000000002')['company']
        path = Path(self.prior['visible_root'])/'filings/10-Q_public.md'
        path.write_text('PRIOR_PUBLIC_TABLE revenue 100; different from current company.')
        for row in self.prior['allowed_files']:
            if row['path'] == 'filings/10-Q_public.md':
                row.update(bytes=len(path.read_bytes()), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        self.counter = 0

    def broker(self, *, context=None, prior=True):
        self.counter += 1
        return PopulationBroker(self.fixture.root/f'broker-{self.counter}',
            versions={self.fixture.version['id']: self.fixture.version},
            population_context_binding=context, prior_company=self.prior if prior else None,
            company=self.case['company'], capacity=self.case['capacity'], runner=Mock(), literature=Mock(), trace_slots={})

    def context(self):
        plain = self.broker(prior=False)
        diagnostic = project({'coverage': {'extracted_cells': 0}, 'evidence': [], 'targets': [
            {'target_id': f'T{i:03d}', 'status': 'incomplete', 'missing': ['metric']}
            for i in range(1, 6)]}, source_sha256=self.fixture.r['sha256'],
            execution_sha256='b'*64, target_ids=[f'T{i:03d}' for i in range(1, 6)])
        return {'schema': 'earnings_population_author_context_v1',
            'parent_version_id': self.fixture.version['id'],
            'parent_programs': plain.references()[self.fixture.version['id']],
            'feedback_sha256': 'b'*64, 'feedback': {'company_id': self.prior['cik'],
                'results': [{'version_id': self.fixture.version['id'], 'research_diagnostics': diagnostic}]},
            'task': 'Synthetic repair assignment; diagnostics are not correctness.'}

    def test_actual_author_effective_input_contains_pinned_diagnostics_not_full_parent_code(self):
        context = self.context()
        binding = engine.save(self.fixture.root/'author-context.json', context)
        broker = self.broker(context=binding)
        transport = role_fixture.OpenRoleTests()
        transport.setUp(); self.addCleanup(transport.doCleanups)
        original_role = transport.service(author=True, max_turns=1)
        role = open_roles.OpenAuthor(original_role.binding, budget=transport.budget,
            client_factory=transport.factory, broker=broker, max_turns=1)
        chosen = transport.choice(); chosen['parent_pair_sha256'] = self.fixture.version['id']
        source = "PROGRAM={'axis':'R'}\ndef run(payload): return {'repair': 'synthetic new algorithm'}\n"
        reply = {'decision_sha256': digest(chosen), 'source_text': source,
                 'test_text': "CASES=[{'input': {}, 'expected': {'repair': 'synthetic new algorithm'}}]"}
        transport.generations = [transport.message(reply)]
        with patch.object(open_roles, 'budgeted_response', side_effect=transport.fake_paid):
            original = role.author(chosen, {'axis': 'R'}, str(transport.slot))
        effective = engine.read(engine.pin(transport.slot/'effective-input.json'))
        self.assertEqual(effective['research_context'], context)
        self.assertEqual(effective['research_context']['feedback']['results'][0]['research_diagnostics']
                         ['program_reported_coverage']['extracted_cells'], 0)
        self.assertNotIn(Path(self.fixture.r['path']).read_text(), json.dumps(effective))
        self.assertEqual(Path(original['path']).read_bytes(), (transport.slot/'01-response.json').read_bytes())
        self.assertEqual(engine.read(original)['output'][0]['content'][0]['text'], json.dumps(reply))
        self.assertFalse(self.fixture.marker.exists())

    def test_context_parent_source_reference_and_binding_drift_rejected(self):
        for index, change in enumerate(('parent', 'source')):
            context = self.context()
            if change == 'parent': context['parent_version_id'] = 'f'*64
            else: context['parent_programs']['R']['sha256'] = 'f'*64
            broker = self.broker(context=engine.save(self.fixture.root/f'bad-context-{index}.json', context))
            with self.subTest(change=change), self.assertRaises(ValueError):
                broker.research_context(include_source=True)
        context = self.context()
        bound = engine.save(self.fixture.root/'drift-context.json', context)
        broker = self.broker(context=bound)
        Path(bound['path']).write_text('{}')
        with self.assertRaises(ValueError):
            broker.research_context()

    def test_actual_services_author_delivers_cached_feedback_and_preserves_generated_code(self):
        transport = role_fixture.OpenRoleTests()
        transport.setUp(); self.addCleanup(transport.doCleanups)
        original_role = transport.service(author=True, max_turns=1, limits={
            'max_input_tokens': 24000, 'max_output_tokens': 49152, 'wall_seconds': 900})
        owner = services.Services.__new__(services.Services)
        owner.case = Mock(return_value=self.case)
        owner.native_root, owner.runner, owner.literature = self.fixture.root, Mock(), Mock()
        owner.traces, owner.authored = {}, {}
        owner.prior_feedback = self.context()['feedback']
        owner.contexts = {'author': (original_role.binding,
            {'budget': transport.budget, 'client_factory': transport.factory})}
        chosen = transport.choice(); chosen['parent_pair_sha256'] = self.fixture.version['id']
        source = "PROGRAM={'axis':'R'}\ndef run(payload): return {'repair': 'model fixture implementation'}\n"
        reply = {'decision_sha256': digest(chosen), 'source_text': source,
                 'test_text': "CASES=[{'input': {}, 'expected': {'repair': 'model fixture implementation'}}]"}
        transport.generations = [transport.message(reply)]
        state = {'stable_id': self.fixture.version['id'], 'explorers': [],
                 'versions': {self.fixture.version['id']: self.fixture.version}}
        with patch.object(services, 'resident', return_value={'company': self.prior}), \
             patch.object(open_roles, 'budgeted_response', side_effect=transport.fake_paid):
            child = owner.author(chosen, state, str(transport.slot))
        effective = engine.read(engine.pin(transport.slot/'effective-input.json'))
        context = effective['research_context']
        self.assertEqual(context['feedback'], owner.prior_feedback)
        self.assertEqual(context['feedback_sha256'], chosen['feedback_sha256'])
        self.assertEqual(context['parent_version_id'], self.fixture.version['id'])
        self.assertEqual(context, engine.read(owner.author_context))
        self.assertEqual(Path(child['R']['path']).read_text(), source)
        self.assertEqual(child['H'], self.fixture.h)
        self.assertEqual((transport.slot/'response.json').read_bytes(), (transport.slot/'01-response.json').read_bytes())
        self.assertFalse(self.fixture.marker.exists())

    def test_prior_file_reads_original_prior_snapshot_and_reports_exact_identity(self):
        broker = self.broker()
        value = broker.dispatch('read_prior_file', {'path': 'filings/10-Q_public.md', 'offset': 0, 'characters': 20000})['value']
        original = (Path(self.prior['visible_root'])/'filings/10-Q_public.md').read_bytes()
        self.assertEqual(value['prior_company_id'], self.prior['cik'])
        self.assertEqual(value['source_sha256'], hashlib.sha256(original).hexdigest())
        self.assertEqual(value['text'], original.decode())
        self.assertNotEqual(value['text'], self.case['state_api'].tools.files['filings/10-Q_public.md'])
        self.assertFalse(self.fixture.marker.exists())

    def test_prior_file_unknown_hidden_absolute_and_out_of_bounds_refused(self):
        broker = self.broker()
        for path in ('../qa.json', '/private/tmp/qa.json', 'evaluation_qa.json', 'filings/hidden-target.md'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                broker.dispatch('read_prior_file', {'path': path, 'offset': 0, 'characters': 100})
        for change in ({'offset': -1}, {'characters': 0}, {'characters': 20001}, {'offset': False}):
            arguments = dict(path='filings/10-Q_public.md', offset=0, characters=100); arguments.update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                broker.dispatch('read_prior_file', arguments)
        self.assertFalse(self.fixture.marker.exists())

    def test_without_prior_company_read_tool_is_not_registered(self):
        broker = self.broker(prior=False)
        self.assertNotIn('read_prior_file', {row['name'] for row in broker.definitions})
        with self.assertRaises(ValueError):
            broker.dispatch('read_prior_file', dict(path='questions.md', offset=0, characters=100))
        self.assertEqual(broker.calls, 0)


class ReviewerDiagnosticDeliveryTests(unittest.TestCase):
    def test_review_receives_verified_current_and_prior_company_probe_diagnostics(self):
        fixture = service_fixture.PopulationAuthorAndFailureTests()
        fixture.setUp(); self.addCleanup(fixture.doCleanups)
        case, child, source = fixture.cold_probe_setup()
        prior = fixture.fixture.company('CIK0000000002')['company']
        fixture.owner.prior_feedback = {'company_id': prior['cik'], 'results': [{'research_diagnostics': 'synthetic prior'}]}
        seen, prompts = [], []
        def run(runner, actual_source, payload, tools):
            seen.append(deepcopy(payload))
            value = {'coverage': {'extracted_cells': 0}, 'evidence': [], 'targets': [
                {'target_id': f'T{i:03d}', 'status': 'incomplete', 'missing': ['metric']}
                for i in range(1, 6)]}
            return receipt_fixture.ScriptedReceiptRunner(fixture.fixture.root/f'probe-{len(seen)}', [value]).run(actual_source, payload)
        def review(prompt, slot):
            prompts.append(deepcopy(prompt)); Path(slot).mkdir(parents=True)
            original = engine.save(Path(slot)/'response.json', {'synthetic': True})
            engine.save(Path(slot)/'review.json', {'original': original, 'review': {
                'accepted_for_exploration': False, 'rationale': 'Synthetic no extraction despite completed interfaces'}})
            return original
        fixture.owner.role = Mock(return_value=SimpleNamespace(review=review,
            broker=SimpleNamespace(references=lambda: {'synthetic': 'source references'})))
        with patch.object(services, 'resident', return_value={'company': prior}), \
             patch.object(services, 'run_cases', return_value=[{'passed': True, 'synthetic': True}]), \
             patch.object(services.researcher, 'run', side_effect=run):
            result = fixture.owner.review(child, fixture.state, str(fixture.fixture.root/'roles'/'review-04'))
        self.assertFalse(result['accepted_for_exploration'])
        self.assertEqual(len(seen), 3)
        self.assertTrue(all(payload['records'] == [] for payload in seen))
        for row in prompts[0]['original_public_empty_state_probes']:
            self.assertEqual(row['diagnostics']['program_reported_coverage']['extracted_cells'], 0)
            self.assertTrue(all(t['status'] == 'incomplete' for t in row['diagnostics']['reported_target_completion']))
        prior_probe = prompts[0]['prior_company_repair_probe']
        self.assertEqual(prior_probe['company_id'], prior['cik'])
        self.assertEqual(prior_probe['diagnostics']['source_sha256'], child['R']['sha256'])
        self.assertEqual(prior_probe['diagnostics']['program_reported_coverage']['extracted_cells'], 0)
        self.assertIn(prior_probe['receipt'], result['evidence'])
        self.assertFalse(fixture.fixture.marker.exists())


class ServiceRepairInjectionTests(unittest.TestCase):
    def test_continuation_repair_only_round_one_and_feedback_cached_before_role_creation(self):
        fixture = service_fixture.PopulationServiceProjectionTests()
        fixture.setUp(); self.addCleanup(fixture.doCleanups)
        feedback, _ = fixture.feedback()
        repair = {'schema': 'earnings_population_human_repair_v1', 'parent_version_id': 'c'*64}
        manifest = engine.save(fixture.root/'continuation.json', {'repair': repair})
        study = engine.save(fixture.root/'study.json', {'continuation': manifest})
        fixture.owner.runtime = {'forecast_study': study}
        seen = []
        def role(name, kind, case, slot):
            seen.append(deepcopy(fixture.owner.prior_feedback))
            return fixture.role
        fixture.owner.role = role
        for index in (1, 2):
            fixture.owner.controller({'company_id': 'synthetic-next', 'round_index': index,
                'population': fixture.initial, 'feedback': feedback,
                'parent_feedback_sha256': digest(feedback)}, str(fixture.root/f'controller-{index:02d}'))
        self.assertEqual(fixture.prompts[0]['repair_assignment'], repair)
        self.assertNotIn('repair_assignment', fixture.prompts[1])
        self.assertEqual(seen, [prompt['feedback'] for prompt in fixture.prompts])


class TransferRepairRoutingTests(unittest.TestCase):
    def setUp(self):
        self.fixture = native_fixture.PopulationCaseTests()
        self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        self.new = self.fixture.resident
        self.prior = self.fixture.company('CIK0000000002')
        for resident, tag in ((self.new, 'NEW_VALIDATION_QUESTION_MARKER'), (self.prior, 'PRIOR_REPAIR_QUESTION_MARKER')):
            path = Path(resident['company']['visible_root'])/'questions.md'
            path.write_text(path.read_text().replace('Synthetic question', tag))
            for row in resident['company']['allowed_files']:
                if row['path'] == 'questions.md':
                    row.update(bytes=len(path.read_bytes()), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            resident['case']['allowed_manifest_sha256'] = hashlib.sha256(json.dumps(
                resident['company']['allowed_files'], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        self.owner = services.Services.__new__(services.Services)
        self.owner.native_root = self.fixture.root/'transfer-native'
        self.owner.binding, self.owner.python = self.fixture.authority, self.fixture.python
        self.owner.runtime = {'source_commit': 'a'*40, 'deadline_utc': self.fixture.deadline}
        self.owner.start_utc = self.fixture.start
        self.owner.current = self.new['company']['cik']
        self.owner.repair_company = self.prior['company']['cik']

    def resident(self, cik):
        return {self.new['company']['cik']: self.new, self.prior['company']['cik']: self.prior}[cik]

    def test_actual_native_cases_route_repair_roles_to_prior_and_frozen_forecasts_to_new(self):
        with patch.object(services, 'resident', side_effect=self.resident) as loader:
            cases = [self.owner.case(self.fixture.version, self.fixture.root/'roles'/role)
                     for role in ('controller-01', 'author-01', 'review-01', 'forecast-01-00')]
            self.owner.repair_company = None
            normal = self.owner.case(self.fixture.version, self.fixture.root/'roles'/'controller-02')
        self.assertEqual([item.args[0] for item in loader.call_args_list],
                         [self.prior['company']['cik']]*3 + [self.new['company']['cik']]*2)
        for case in cases[:3]:
            self.assertEqual(case['company']['cik'], self.prior['company']['cik'])
            self.assertNotIn('NEW_VALIDATION_QUESTION_MARKER', json.dumps(case['state_api'].tools.files))
            self.assertEqual(case['state_api'].load(case['initial_state'])['records'], [])
        self.assertEqual(cases[3]['company']['cik'], self.new['company']['cik'])
        self.assertEqual(normal['company']['cik'], self.new['company']['cik'])
        self.assertNotEqual(cases[0]['manifest']['K'], cases[3]['manifest']['K'])
        self.assertEqual(cases[0]['pair_sha256'], cases[3]['pair_sha256'])
        self.assertFalse(self.fixture.marker.exists())

    def test_actual_controller_caches_feedback_before_case_and_never_exposes_new_questions(self):
        prior_id, new_id = self.prior['company']['cik'], self.new['company']['cik']
        brief = engine.save(self.fixture.root/'transfer-continuation.json', {'repair': {
            'schema': 'earnings_population_human_repair_v1', 'parent_version_id': self.fixture.version['id']}})
        self.owner.runtime['forecast_study'] = engine.save(self.fixture.root/'transfer-study.json', {'continuation': brief})
        self.owner.runner, self.owner.literature, self.owner.traces = Mock(), Mock(), {}
        seen, prompts = [], []
        actual_case = self.owner.case
        def case(version, slot):
            seen.append((deepcopy(self.owner.prior_feedback), self.owner.repair_company))
            return actual_case(version, slot)
        self.owner.case = case
        def propose(prompt, slot):
            prompts.append(deepcopy(prompt)); Path(slot).mkdir(parents=True)
            original = engine.save(Path(slot)/'response.json', {'synthetic': True})
            engine.save(Path(slot)/'decision.json', {'original': original, 'decision': {'axis': 'continue'}})
            return original
        brokers = []
        def role(name, kind, case, slot):
            broker = self.owner.broker(case, slot); brokers.append(broker)
            return SimpleNamespace(broker=broker, propose=propose)
        self.owner.role = role
        projected = {'schema': 'synthetic-prior-feedback', 'company_id': prior_id, 'results': []}
        packet = {'company_id': new_id, 'round_index': 1,
            'population': {'stable_id': self.fixture.version['id'], 'explorers': [],
                           'versions': {self.fixture.version['id']: self.fixture.version}},
            'feedback': {'synthetic': True}, 'parent_feedback_sha256': 'b'*64}
        with patch.object(services, 'resident', side_effect=self.resident), \
             patch.object(services, 'public_feedback', return_value=projected):
            self.owner.controller(packet, str(self.fixture.root/'roles'/'controller-01'))
        self.assertEqual(seen, [(projected, prior_id)])
        self.assertEqual(prompts[0]['company_id'], prior_id)
        self.assertEqual(prompts[0]['validation_company_id'], new_id)
        self.assertIn('PRIOR_REPAIR_QUESTION_MARKER', prompts[0]['questions'])
        self.assertNotIn('NEW_VALIDATION_QUESTION_MARKER', json.dumps(prompts[0]))
        self.assertNotIn('NEW_VALIDATION_QUESTION_MARKER', json.dumps(brokers[0].files.files))
        self.assertEqual(self.owner.current, new_id)


if __name__ == '__main__':
    unittest.main()
