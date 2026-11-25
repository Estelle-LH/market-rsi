"""Inert recovery delivery, not historical admission, paid review or code execution."""
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import Mock, patch

import earnings_open_roles as roles
import earnings_population_broker as brokers
import earnings_population_services as services
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_open_roles as role_fixture
from test_earnings_population_campaign_integration import CampaignIntegrationFixture, CAPITAL, save


class RecoveryAuthorDelivery(CampaignIntegrationFixture):
    def setUp(self):
        super().setUp()
        # Historical verification/probe projection is an explicit fixture seam.
        # Native, broker, source identity, Author transport and saved requests are real.
        self.recovery = {
            'schema': 'earnings_population_delivery_failure_v1',
            'failed_attempt': deepcopy(self.public_evidence),
            'audit': deepcopy(self.public_evidence), 'candidate_id': self.reference['id'],
            'stage': 'source_review', 'error_type': 'BudgetStop',
            'observed_input_tokens': 14616, 'prior_input_limit': 10000,
            'review_assessment': 'not_generated', 'score_state': 'unscored',
            'probes': deepcopy(self.feedback['probes']),
            'independent_offline_observations': {
                'receipt': deepcopy(self.public_evidence),
                'summary': {'actual_period_bound_cells': 0, 'actual_fully_complete_cells': 0,
                            'scientific_review': 'Not performed; capacity failure.'},
                'fallback_static_finding': 'A forecast_policy string does not invoke the parent algorithm.',
                'qualification': 'Static/public cold-output audit, not model review or forecast score.'},
            'scope': 'Synthetic delivery failure reference; no quality rejection, adoption or score.'}
        self.origin['recovery_context'] = deepcopy(self.recovery)
        self.refresh()

    def test_services_author_first_physical_request_gets_exact_offline_diagnosis(self):
        case = self.fixture.prepare(resident=self.resident)
        owner = services.Services.__new__(services.Services)
        owner.runtime, owner.native_root, owner.current = self.runtime, self.root, CAPITAL
        owner.runner, owner.literature, owner.traces, owner.authored = Mock(), Mock(), {}, {}
        owner.case = Mock(return_value=case)
        owner.prior_feedback = brokers.public_feedback(self.feedback_binding, self.state['versions'])
        owner.campaign_context = self.context()
        before = deepcopy(owner.campaign_context)
        owner.reference_context_binding = save(self.root/'recovery-reference.json',
                                               owner.campaign_context['research_context'])
        author = role_fixture.OpenRoleTests()
        author.setUp(); self.addCleanup(author.doCleanups)
        role = author.service(author=True, max_turns=1, limits={
            'max_input_tokens': 24000, 'max_output_tokens': 49152, 'wall_seconds': 900})
        author.factory.return_value.post.return_value = {'input_tokens': 100, 'synthetic_count': True}
        owner.contexts = {'author': (role.binding,
            {'budget': author.budget, 'client_factory': author.factory})}
        chosen = dict(author.choice(), parent_pair_sha256=self.version['id'],
                      feedback_sha256=digest(self.feedback_binding))
        source = "PROGRAM={'axis':'R'}\ndef run(p): return {'synthetic_delivery':True}\n"
        author.generations = [author.message({'decision_sha256': digest(chosen),
            'parent_source_sha256': self.version['R']['sha256'],
            'edits': [{'kind': 'replace', 'old_text': Path(self.version['R']['path']).read_text(),
                       'new_text': source}],
            'test_text': "CASES=[{'input':{},'expected':{'synthetic_delivery':True}}]"})]
        with patch.object(services, 'resident', return_value=deepcopy(self.resident)), \
             patch.object(roles, 'budgeted_response', side_effect=author.fake_paid):
            child = owner.author(chosen, self.state, str(author.slot))
        delivered = engine.read(engine.pin(author.slot/'effective-input.json'))['research_context']
        self.assertEqual(delivered['prior_delivery_failure'], self.recovery)
        self.assertEqual(delivered['prior_candidate'], self.reference)
        self.assertEqual(delivered['failure_evidence_context'], before['failure_evidence_context'])
        self.assertEqual(delivered['feedback_binding'], self.feedback_binding)
        self.assertEqual(delivered['feedback_sha256'], digest(self.feedback_binding))
        self.assertEqual(delivered['parent_version_id'], self.version['id'])
        self.assertEqual(delivered['original_R_evidence_abi'], self.abi)
        self.assertEqual(json.loads(author.requests[0]['input'][0]['content'])['research_context'], delivered)
        self.assertEqual(owner.campaign_context, before)
        self.assertEqual(child['parent'], self.version['id'])
        self.assertNotIn(self.reference['id'], owner.role_versions)
        self.assertNotIn('repair_assignment', delivered)
        self.assertNotIn('HIDDEN_', json.dumps(author.requests))
        self.assertFalse(self.fixture.marker.exists())

    def test_broker_exact_copy_is_public_reference_not_parent_or_score(self):
        broker = self.broker(author=True, population_changes={'prior_delivery_failure': deepcopy(self.recovery)})
        actual = broker.research_context(include_source=True)
        self.assertEqual(actual['prior_delivery_failure'], self.recovery)
        self.assertEqual(actual['prior_delivery_failure']['review_assessment'], 'not_generated')
        self.assertEqual(actual['prior_delivery_failure']['score_state'], 'unscored')
        self.assertNotIn('results', actual['prior_delivery_failure'])
        self.assertNotIn(self.reference['id'], broker.versions)
        self.assertEqual(actual['parent_version_id'], self.version['id'])

    def test_missing_failure_packet_cannot_silently_pass_to_author(self):
        with self.assertRaisesRegex(ValueError, 'rejected-source reference'):
            self.broker(author=True)

    def test_rebound_quality_claim_or_offline_observation_tamper_is_refused(self):
        changes = [dict(self.recovery, review_assessment='scientifically_rejected'),
                   dict(self.recovery, score_state='scored')]
        altered = deepcopy(self.recovery)
        altered['independent_offline_observations']['summary']['actual_period_bound_cells'] = 42
        changes.append(altered)
        altered = deepcopy(self.recovery)
        altered['independent_offline_observations']['receipt']['sha256'] = 'e'*64
        changes.append(altered)
        for value in changes:
            with self.subTest(change=value), self.assertRaisesRegex(ValueError, 'rejected-source reference'):
                self.broker(author=True, population_changes={'prior_delivery_failure': value})

    def test_legacy_no_recovery_context_remains_unchanged_and_invention_is_rejected(self):
        del self.origin['recovery_context']; self.refresh()
        broker = self.broker(author=True)
        self.assertNotIn('prior_delivery_failure', broker.research_context(include_source=True))
        with self.assertRaisesRegex(ValueError, 'rejected-source reference'):
            self.broker(author=True, population_changes={'prior_delivery_failure': self.recovery})

    def test_next_round_does_not_relabel_old_delivery_failure_as_latest_feedback(self):
        self.packet['round_index'] = 2
        context = self.context()
        self.assertNotIn('prior_delivery_failure', context['research_context']['observations'])
        self.assertEqual(context['feedback_binding'], self.feedback_binding)
        self.assertEqual(self.state, self.origin['population'])
