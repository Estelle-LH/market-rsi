"""Independent inert campaign admission and actual role-context integration.

Synthetic resident data, historical-origin verifier and role generations are
explicit fixtures. Public-file/hash/Native/broker/role/context checks are real;
there is no candidate execution, model call, Docker, scorer or real ledger.
"""
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from edgar_forecast_tools import FilingTools, TOOLS
import earnings_open_roles as open_roles
import earnings_population as pool
import earnings_population_broker as brokers
import earnings_population_campaign_admission as admission
import earnings_population_campaign_context as context_api
import earnings_population_rejection as rejection
import earnings_population_services as services
import earnings_population_tasks as tasks
import earnings_population_run as run
import earnings_population_runtime as runtime
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_open_roles as role_fixture
import test_earnings_population_case as native_fixture
import test_earnings_population_run as entry_fixture
import test_earnings_population_runtime as runtime_fixture


CAPITAL = 'CIK0000017313'
VALIDATION = 'CIK0000021076'


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True))
    return engine.pin(path)


class CampaignIntegrationFixture(unittest.TestCase):
    def setUp(self):
        self.fixture = native_fixture.PopulationCaseTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.resident = self.fixture.company(CAPITAL)
        self.resident['runtime'] = {'max_input_tokens': 100000, 'max_output_tokens': 25000,
            'company_wall_seconds': 1800, 'models': {'gpt-6.1-sol': {'api_model': 'gpt-6.1-sol', 'effort': 'max'}}}
        self.version = self.fixture.version
        self.state = pool.initialize(self.version, {'K': 'a'*64, 'M': 'b'*64, 'C': 'c'*64},
                                    exposed_companies=[CAPITAL])
        self.owned, self.repo = self.root/'owned', self.root/'repo'
        self.ident = 'edgar-population-20261016-03'
        self.inputs = self.owned/'inputs'/self.ident
        self.ledger = self.root/'pilot/synthetic-budget.sqlite3'
        self.sources = {admission.PLAN: save(self.repo/admission.PLAN, {
            'schema': 'supervisor_bottleneck_plan_v1', 'id': 'earnings-population-campaign-20261016',
            'human_authorization': admission.AUTHORIZATION})}
        self.public_evidence = save(self.root/'synthetic-original.json', {'synthetic_public_receipt': True})
        self.hidden = save(self.root/'synthetic-raw-score.json', {'actual_value': 'HIDDEN_VALUE_SENTINEL',
                                                                'qa': 'HIDDEN_QA_SENTINEL'})
        self.last_public = save(self.root/'last-scored-trial/population-public-feedback.json', {
            'schema': 'earnings_population_public_trial_v1', 'company_id': CAPITAL,
            'version_id': self.version['id'], 'points': 3.5,
            'pool_sources': {axis: self.version[axis]['sha256'] for axis in ('R', 'H')},
            'target_scores': [{'target_id': f'T{i+1:03d}', 'points_awarded': n}
                              for i, n in enumerate([1, 1, 1, .5, 0])]})
        self.last_scored = save(self.root/'last-scored.json', {'schema': 'earnings_population_feedback_v1',
            'company_id': CAPITAL, 'stable_id': self.version['id'], 'round_index': 1,
            'scope': 'Explicit synthetic original award projection, not financial validity.',
            'results': [{'version_id': self.version['id'], 'points': 3.5,
                         'evidence': [self.last_public, self.hidden]}]})
        self.rejected_source = self.fixture.file('rejected.py',
            "PROGRAM={'axis':'R'}\n# REFERENCE_ONLY_PUBLIC_SOURCE\ndef run(payload): return {'incomplete':True}\n")
        self.rejected_tests = self.fixture.file('rejected-cases.py', 'CASES=[]\n')
        self.reference = {'axis': 'R', 'source': self.rejected_source, 'source_delivery': 'paged_reference',
                          'reference_only': True, 'id': 'f'*64, 'parent': self.version['id'], 'tests': self.rejected_tests}
        self.outcome = save(self.root/'review-01-outcome.json', {
            'schema': 'earnings_population_exploration_review_v1', 'candidate_id': self.reference['id'],
            'accepted_for_exploration': False, 'rationale': 'Search transport succeeded but source-bound facts were not extracted.'})
        self.abi = {'schema': 'earnings_original_R_evidence_abi_v1', 'request_phases': 1,
            'max_requests': 8, 'tools': deepcopy(TOOLS), 'search_hit_fields': ['path', 'line', 'text'],
            'search_has_source_sha256': False, 'search_has_character_offset': False,
            'read_result_fields': ['path', 'offset', 'total_characters', 'text', 'next_offset'],
            'read_has_source_sha256': False, 'author_prior_file_hash_is_not_R_observation_hash': True,
            'second_request_phase_allowed': False}
        self.feedback = {'schema': 'earnings_population_rejection_feedback_v1', 'kind': 'review_rejected',
            'score_state': 'unscored', 'company_id': CAPITAL, 'population_sha256': digest(self.state),
            'active_parent_id': self.version['id'], 'last_scored_feedback': self.last_scored,
            'rejected_candidate': deepcopy(self.reference),
            'review': {'binding': self.outcome, 'accepted_for_exploration': False,
                       'rationale': 'Search succeeded; no extracted facts.', 'evidence': [self.outcome]},
            'probes': [{'stage': 'forecast', 'company_id': CAPITAL, 'receipt': self.public_evidence,
                'source_sha256': self.rejected_source['sha256'], 'execution_sha256': 'd'*64,
                'coverage': {'accepted_searches': 8, 'failed_requests': 0, 'extracted_cells': 0},
                'incomplete_targets': 5, 'reason_codes': ['missing_source_hash_or_character_offset']}],
            'original_questions': FilingTools(self.resident['company']).files['questions.md'],
            'tool_abi': self.abi, 'qualifications': ['Reported counts are not independently verified financial correctness.'],
            'scope': 'Synthetic verified-origin seam only; no actual historical acceptance claim.'}
        self.origin = {'population': self.state, 'research_feedback': self.feedback,
                       'last_scored_feedback': self.last_scored, 'reference_candidate': self.reference,
                       'evidence': [self.public_evidence]}
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for target, key, value in ((admission, 'ROOT', self.owned), (admission, 'REPO', self.repo),
                (rejection, 'LEDGER', self.ledger), (rejection, 'PARENT', self.version['id']),
                (tasks, 'FULL_PLAN', self.fixture.data), (tasks, 'SCORER', self.fixture.scorer)):
            self.stack.enter_context(patch.object(target, key, value))
        self.resident_loader = self.stack.enter_context(patch.object(tasks, 'resident',
            side_effect=lambda cik: deepcopy(self.resident) if cik == CAPITAL else
            (_ for _ in ()).throw(ValueError('Synthetic fixture only permits Capital development data'))))
        self.origin_loader = self.stack.enter_context(patch.object(rejection, 'load_closed_review_rejection',
                                                                  side_effect=lambda *a, **k: deepcopy(self.origin)))
        # These legacy integration fixtures deliberately invent historical probe
        # receipts. Separate after03 tests reconstruct real saved public probes.
        self.failure_examples = {'schema': 'earnings_population_failure_context_v1',
            'company_id': CAPITAL, 'examples': [{'synthetic_public_table': True}],
            'scope': 'Explicit inert projection seam; no original execution claimed.'}
        self.failure_projector = self.stack.enter_context(patch(
            'earnings_population_failure_context.project', return_value=deepcopy(self.failure_examples)))
        # Historical probes above are deliberately invented, so this extension
        # is an explicit inert seam too. Real receipt verification and examples
        # are covered independently in test_earnings_population_request_examples.
        self.request_examples = {'schema': 'earnings_population_request_return_examples_v1',
            'examples': [], 'scope': 'Explicit inert request-example seam; no original execution claimed.'}
        self.request_examples_projector = self.stack.enter_context(patch.object(
            context_api, '_request_examples', return_value=deepcopy(self.request_examples)))
        self.value = {'id': self.ident, 'ledger': str(self.ledger), 'companies': [CAPITAL, CAPITAL],
                      'sources': self.sources}
        self.broker_count = 0
        self.refresh()

    def refresh(self, *, manifest_changes=None, origin=None, feedback=None):
        self.feedback_binding = save(self.inputs/'rejection-feedback.json', self.feedback if feedback is None else feedback)
        origin_binding = save(self.inputs/'campaign-origin.json', self.origin if origin is None else origin)
        manifest = {'schema': 'earnings_population_campaign_v1', 'source_plan': self.sources[admission.PLAN],
            'panel': [CAPITAL], 'baseline_version_id': self.version['id'], 'max_decisions': 2,
            'initial_population_sha256': digest(self.state), 'initial_feedback': self.feedback_binding,
            'last_scored_feedback': self.last_scored, 'contract': admission.scientific_contract(self.resident),
            'validation_company_id': VALIDATION}
        manifest.update(manifest_changes or {})
        self.campaign = save(self.inputs/'campaign.json', manifest)
        self.study = {'campaign': self.campaign, 'campaign_origin': origin_binding,
                      'cases': [self.resident['case'], self.resident['case']]}
        self.runtime = {'forecast_study': save(self.inputs/'study.json', self.study)}
        self.packet = {'campaign': self.campaign, 'feedback': self.feedback_binding,
            'parent_feedback_sha256': digest(self.feedback_binding), 'population': deepcopy(self.state),
            'company_id': CAPITAL, 'round_index': 1, 'scope': 'Repeated development panel, not holdout.'}

    def context(self):
        public = brokers.public_feedback(self.feedback_binding, self.state['versions'])
        return context_api.prepare(self.runtime, self.packet, public)

    def broker(self, *, author=False, population_changes=None, context_changes=None):
        self.broker_count += 1
        index = self.broker_count
        context = self.context()
        repair = deepcopy(context['research_context'])
        repair.update(context_changes or {})
        reference_binding = save(self.root/f'reference-context-{index}.json', repair)
        args = {}
        if author:
            references = {axis: {'sha256': self.version[axis]['sha256'], 'read_tool': 'read_population_program',
                'arguments': {'version_id': self.version['id'], 'axis': axis, 'offset': 0, 'characters': 4000}}
                for axis in ('R', 'H')}
            value = {'schema': 'earnings_population_author_context_v1', 'parent_version_id': self.version['id'],
                'parent_programs': references, 'prior_candidate': context['prior_candidate'],
                'feedback': brokers.public_feedback(self.feedback_binding, self.state['versions']),
                'feedback_binding': self.feedback_binding, 'feedback_sha256': digest(self.feedback_binding),
                'original_R_evidence_abi': self.abi, 'campaign': self.campaign,
                'failure_evidence_context': context['failure_evidence_context'],
                'evidence_abi_guidance': context['research_context']['verification']}
            value.update(population_changes or {})
            args['population_context_binding'] = save(self.root/f'population-context-{index}.json', value)
        case = self.fixture.prepare(resident=self.resident, root=self.root/f'case-{index}')
        return brokers.PopulationBroker(self.root/f'broker-{index}', versions=self.state['versions'],
            company=self.resident['company'], capacity=case['capacity'], runner=Mock(), literature=Mock(),
            trace_slots={}, prior_company=self.resident['company'], research_context_binding=reference_binding, **args)


class ScientificAdmissionContracts(CampaignIntegrationFixture):
    def test_exact_original_contract_and_origin_repeated_panel_without_cache_or_mutation(self):
        original = deepcopy((self.value, self.study, self.state, self.origin))
        residents = admission.validate(self.value, self.study, self.state)
        self.assertEqual(len(residents), 2)
        self.assertEqual(residents[0], residents[1])
        self.assertIsNot(residents[0], residents[1])
        manifest = engine.read(self.campaign)
        self.assertEqual(manifest['contract']['cache_policy'], 'disabled')
        self.assertEqual(manifest['contract']['initial_records'], [])
        self.assertEqual(manifest['contract']['baseline_version_id'], self.version['id'])
        self.assertEqual(manifest['contract']['kernel'], self.resident['kernel'])
        self.assertEqual(manifest['contract']['questions_sha256'], hashlib.sha256(self.feedback['original_questions'].encode()).hexdigest())
        self.assertEqual((self.value, self.study, self.state, self.origin), original)
        self.assertFalse(self.fixture.marker.exists())
        self.origin_loader.assert_called_once()

    def test_wrong_panel_data_resources_initial_state_baseline_or_cache_is_rejected(self):
        contract = engine.read(self.campaign)['contract']
        changes = ({'company_id': VALIDATION}, {'data': self.fixture.qa}, {'scorer': self.fixture.qa},
                   {'initial_records': [{'fabricated': True}]}, {'cache_policy': 'use-old-score'},
                   {'limits': dict(contract['limits'], forecast={'max_input_tokens': 1,
                                                               'max_output_tokens': 2, 'wall_seconds': 3})})
        for change in changes:
            self.refresh(manifest_changes={'contract': dict(contract, **change)})
            self.origin_loader.reset_mock()
            with self.subTest(change=change), self.assertRaises(ValueError):
                admission.validate(self.value, self.study, self.state)
            self.origin_loader.assert_not_called()

    def test_rebound_but_wrong_origin_or_feedback_cannot_masquerade_as_closed_rejection(self):
        altered = deepcopy(self.origin)
        altered['research_feedback']['scope'] = 'Wrong independently rebound origin'
        self.refresh(origin=altered)
        with self.assertRaises(ValueError):
            admission.validate(self.value, self.study, self.state)
        self.refresh(feedback=dict(self.feedback, qualifications=['Wrong source-derived diagnosis']))
        with self.assertRaises(ValueError):
            admission.validate(self.value, self.study, self.state)

    def test_foreign_named_input_denied_before_bytes_read_and_mixed_continuation_refused(self):
        foreign = save(self.root/'foreign-campaign.json', engine.read(self.campaign))
        with self.assertRaises(ValueError):
            admission.validate(self.value, dict(self.study, campaign=foreign), self.state)
        with self.assertRaises(ValueError):
            admission.validate(self.value, dict(self.study, continuation=self.public_evidence), self.state)

    def test_origin_loader_failure_or_pending_fee_is_not_bypassed(self):
        self.origin_loader.side_effect = ValueError('Synthetic original owner fee unresolved')
        with self.assertRaisesRegex(ValueError, 'fee unresolved'):
            admission.validate(self.value, self.study, self.state)


class TypedFeedbackAndReferenceContracts(CampaignIntegrationFixture):
    def test_rejection_public_projection_keeps_actual_diagnosis_not_hidden_arbitrary_fields(self):
        value = dict(self.feedback, actual_value='HIDDEN_VALUE_SENTINEL', qa={'secret': 'HIDDEN_QA_SENTINEL'},
                     hidden_score_reasoning='HIDDEN_PROVIDER_SENTINEL')
        # Last-scored awards must be read through the unchanged original
        # public verifier, while this new rejection remains unscored.
        spy = Mock(wraps=brokers._public_scored)
        original_read = engine.read
        def no_hidden_read(binding):
            if binding == self.hidden:
                raise AssertionError('raw hidden score/QA must not be decoded for role input')
            return original_read(binding)
        with patch.object(engine, 'read', side_effect=no_hidden_read):
            public = context_api.project(value, self.state['versions'], spy)
        self.assertEqual(public['probes'][0]['coverage'], {'accepted_searches': 8, 'failed_requests': 0, 'extracted_cells': 0})
        self.assertNotIn('results', public)
        self.assertNotIn('HIDDEN_', json.dumps(public))
        self.assertEqual(public['tool_abi'], self.abi)
        self.assertEqual(public['rejected_candidate'], self.reference)
        self.assertEqual(public['last_scored_observation']['binding'], self.last_scored)
        self.assertEqual(public['last_scored_observation']['results'][0]['points'], 3.5)
        self.assertEqual(len(public['last_scored_observation']['results'][0]['target_scores']), 5)
        self.assertNotIn('research_diagnostics', public['last_scored_observation']['results'][0])
        spy.assert_called_once()

    def test_context_preserves_original_ABI_hashes_as_reference_without_dispatch(self):
        result = self.context()
        self.assertEqual(result['feedback_binding'], self.feedback_binding)
        self.assertEqual(result['original_R_evidence_abi'], self.abi)
        self.assertEqual(result['prior_candidate'], self.reference)
        self.assertEqual(result['research_context']['schema'], 'earnings_repair_context_v1')
        self.assertNotIn('dispatch', result['research_context'])
        self.assertNotIn('source_text', result['research_context']['prior_candidate'])
        self.assertNotIn(Path(self.rejected_source['path']).read_text(), json.dumps(result))
        self.assertFalse(result['original_R_evidence_abi']['read_has_source_sha256'])
        self.assertTrue(result['original_R_evidence_abi']['author_prior_file_hash_is_not_R_observation_hash'])

    def test_abi_mutation_or_wrong_campaign_packet_is_rejected(self):
        original = deepcopy(self.feedback)
        for change in ({'max_requests': 9}, {'request_phases': 2}, {'read_has_source_sha256': True},
                       {'search_has_character_offset': True}, {'tools': []}):
            altered = deepcopy(self.origin)
            altered['research_feedback']['tool_abi'] = dict(original['tool_abi'], **change)
            self.refresh(origin=altered)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.context()
        self.refresh()
        self.packet['campaign'] = self.public_evidence
        with self.assertRaises(ValueError):
            self.context()

    def test_rejected_source_read_pages_are_exact_and_not_in_active_version_choices(self):
        broker = self.broker()
        definitions = {row['name']: row for row in broker.definitions}
        self.assertIn('read_reference_program', definitions)
        self.assertNotIn(self.reference['id'], broker.versions)
        self.assertNotIn(self.reference['id'], definitions['read_population_program']['parameters']['properties']['version_id']['enum'])
        result = broker.dispatch('read_reference_program', {'offset': 0, 'characters': 50})['value']
        self.assertEqual(result['text'], Path(self.rejected_source['path']).read_text()[:50])
        self.assertEqual(result['source_sha256'], self.rejected_source['sha256'])
        self.assertFalse(self.fixture.marker.exists())
        with self.assertRaises(ValueError):
            broker.dispatch('read_population_program', {'version_id': self.reference['id'], 'axis': 'R',
                                                       'offset': 0, 'characters': 50})

    def test_author_population_reference_cannot_substitute_different_rejected_program(self):
        replacement = dict(self.reference, source=self.fixture.r)
        with self.assertRaises(ValueError):
            self.broker(author=True, population_changes={'prior_candidate': replacement})

    def test_author_context_rejects_stale_feedback_hash_binding_or_fabricated_R_ABI(self):
        for change in ({'feedback_binding': self.public_evidence}, {'feedback_sha256': 'f'*64},
                       {'original_R_evidence_abi': dict(self.abi, max_requests=9)},
                       {'evidence_abi_guidance': 'Fabricated requirement to make every advice item a state fact'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.broker(author=True, population_changes=change)

    def test_rejected_source_byte_drift_is_refused_by_existing_page_boundary(self):
        broker = self.broker()
        Path(self.rejected_source['path']).write_text('Synthetic changed rejected bytes')
        with self.assertRaises(ValueError):
            broker.dispatch('read_reference_program', {'offset': 0, 'characters': 50})

    def test_default_no_campaign_keeps_existing_context_route(self):
        study = save(self.root/'default-study.json', {'synthetic_default_study': True})
        self.assertIsNone(context_api.prepare({'forecast_study': study}, {}, {}))


class ActualRoleInputContracts(CampaignIntegrationFixture):
    def test_actual_controller_and_author_effective_inputs_include_rejection_and_original_R_ABI(self):
        case = self.fixture.prepare(resident=self.resident)
        owner = services.Services.__new__(services.Services)
        owner.runtime, owner.native_root = self.runtime, self.root
        owner.runner, owner.literature, owner.traces, owner.authored = Mock(), Mock(), {}, {}
        owner.case = Mock(return_value=case)
        controller = role_fixture.OpenRoleTests()
        controller.setUp(); self.addCleanup(controller.doCleanups)
        controller_role = controller.service(max_turns=1)
        chosen = dict(controller.choice(), parent_pair_sha256=self.version['id'],
                      feedback_sha256=digest(self.feedback_binding), retire_branch_id='none')
        controller.generations = [controller.message(chosen)]
        owner.contexts = {'controller': (controller_role.binding,
            {'budget': controller.budget, 'client_factory': controller.factory})}
        with patch.object(services, 'resident', return_value=deepcopy(self.resident)), \
             patch.object(open_roles, 'budgeted_response', side_effect=controller.fake_paid):
            chosen_binding = owner.controller(self.packet, str(controller.slot))
        effective_controller = engine.read(engine.pin(controller.slot/'effective-input.json'))
        self.assertEqual(effective_controller['feedback_binding'], self.feedback_binding)
        self.assertEqual(effective_controller['feedback']['probes'][0]['coverage']['accepted_searches'], 8)
        self.assertEqual(effective_controller['original_R_evidence_abi'], self.abi)
        self.assertEqual(effective_controller['feedback']['last_scored_observation']['results'][0]['points'], 3.5)
        self.assertNotIn('repair_assignment', effective_controller)
        self.assertNotIn('dispatch', effective_controller['research_context'])
        self.assertNotIn(self.reference['id'], effective_controller['active_versions'])
        author = role_fixture.OpenRoleTests()
        author.setUp(); self.addCleanup(author.doCleanups)
        author_role = author.service(author=True, max_turns=1, limits={
            'max_input_tokens': 24000, 'max_output_tokens': 49152, 'wall_seconds': 900})
        owner.contexts['author'] = (author_role.binding, {'budget': author.budget, 'client_factory': author.factory})
        decision = engine.read(chosen_binding)
        source = "PROGRAM={'axis':'R'}\ndef run(payload): return {'synthetic_new_method':True}\n"
        author.generations = [author.message({'decision_sha256': digest(decision),
            'parent_source_sha256': self.version['R']['sha256'],
            'edits': [{'kind': 'replace', 'old_text': Path(self.version['R']['path']).read_text(),
                       'new_text': source}],
            'test_text': "CASES=[{'input':{},'expected':{'synthetic_new_method':True}}]"})]
        with patch.object(services, 'resident', return_value=deepcopy(self.resident)), \
             patch.object(open_roles, 'budgeted_response', side_effect=author.fake_paid):
            child = owner.author(decision, self.state, str(author.slot))
        context = engine.read(engine.pin(author.slot/'effective-input.json'))['research_context']
        self.assertEqual(context['feedback_binding'], self.feedback_binding)
        self.assertEqual(context['feedback_sha256'], digest(self.feedback_binding))
        self.assertEqual(context['prior_candidate'], self.reference)
        self.assertEqual(context['original_R_evidence_abi'], self.abi)
        self.assertEqual(context['evidence_abi_guidance'],
                         effective_controller['research_context']['verification'])
        self.assertIn('arbitrary JSON advice', context['evidence_abi_guidance'])
        self.assertEqual(context['feedback']['last_scored_observation']['results'][0]['points'], 3.5)
        self.assertNotIn('HIDDEN_', json.dumps(context))
        self.assertEqual(context['parent_version_id'], self.version['id'])
        self.assertEqual(Path(child['R']['path']).read_text(), source)
        self.assertNotIn(self.reference['id'], owner.role_versions)
        self.assertFalse(self.fixture.marker.exists())


class EntryCampaignRoutingContracts(unittest.TestCase):
    def test_campaign_preparation_current_pending_fee_stops_before_origin_or_new_inputs(self):
        fixture = entry_fixture.PreparationContracts()
        fixture.setUp(); self.addCleanup(fixture.doCleanups)
        ident = 'edgar-population-20261016-03'
        fixture.idle.side_effect = RuntimeError('Synthetic current pending fee remains unresolved')
        with patch.object(rejection, 'load_closed_review_rejection',
                          side_effect=AssertionError('must not inherit before current idle check')), \
             self.assertRaisesRegex(RuntimeError, 'pending fee'):
            run.prepare(ident, campaign_rejection=True)
        self.assertFalse((fixture.owned/'inputs'/ident).exists())
        fixture.preflight.assert_not_called()

    def test_opt_in_entry_passes_campaign_binding_only_when_present(self):
        fixture = entry_fixture.ExecutionContracts()
        fixture.setUp(); self.addCleanup(fixture.doCleanups)
        binding = save(fixture.owned/'campaign.json', {'synthetic_campaign': True})
        fixture.study['campaign'] = binding
        fixture.value['forecast_study'] = save(fixture.owned/'study.json', fixture.study)
        seen = []
        def campaign_loop(root, state, companies, roles, *, admit, max_rounds, campaign):
            seen.append(campaign)
            self.assertTrue(admit({'round_index': 1, 'stage': 'controller', 'outputs': {}}))
            return {'synthetic_optin_routing': True, 'not_real_model_or_admission': True}
        fixture.loop.side_effect = campaign_loop
        with patch.object(run, 'preflight', side_effect=engine.read):
            result = engine.read(run.execute(fixture.bound()))
        self.assertEqual(seen, [binding])
        self.assertEqual(result['status'], 'COMPLETED_DISCOVERY_PILOT')
        self.assertFalse(result['improvement_proven'])

    def test_default_entry_still_accepts_original_loop_keyword_signature(self):
        fixture = entry_fixture.ExecutionContracts()
        fixture.setUp(); self.addCleanup(fixture.doCleanups)
        # Its original fixture loop has no campaign keyword parameter. This
        # succeeds only if the legacy entry continues omitting that keyword.
        with patch.object(run, 'preflight', side_effect=engine.read):
            result = engine.read(run.execute(fixture.bound()))
        self.assertEqual(result['status'], 'COMPLETED_DISCOVERY_PILOT')
        self.assertIn('loop', fixture.events)


if __name__ == '__main__':
    unittest.main()
