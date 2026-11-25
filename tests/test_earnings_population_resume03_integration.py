"""Inert current-entry contracts; historical load and generation are fixtures.

Admission, context projections and actual original Broker/role contracts are
exercised by companion tests. No provider, candidate execution or real ledger.
"""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import earnings_population_campaign_admission as admission
import earnings_population_campaign_context as context_api
import earnings_population_campaign_resume as resume
import earnings_population_campaign as campaign
import earnings_population as pool
from earnings_population_services import review_probe_output
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
from test_earnings_population_campaign_integration import CampaignIntegrationFixture, save
import unittest
import earnings_population_runtime as runtime
import earnings_population_budget as budget_amendment
from test_earnings_population_runtime import Fixture as RuntimeFixture
from edgar_forecast_budget import BudgetStop


class ReviewPublicOutput(unittest.TestCase):
    def test_nested_raw_financial_evidence_is_visible_not_opaque_receipt_only(self):
        value = {'coverage': {'extracted_cells': 1}, 'forecasts': {
            'T001': {'status': 'ready', 'period': '2025-03-31', 'unit': 'USD thousands',
                'value': 19567, 'source': {'path': 'filings/10-Q.md', 'line': 4106}}}}
        projected = review_probe_output(value)
        self.assertTrue(projected['complete'])
        self.assertEqual(projected['value'], value)
        self.assertEqual(projected['value_sha256'], digest(value))
        projected['value']['forecasts']['T001']['value'] = -1
        self.assertEqual(value['forecasts']['T001']['value'], 19567)


class AmendedAdmission(RuntimeFixture):
    """Isolate current accounting opt-in; grant verifier tested separately."""
    def test_null_or_malformed_amendment_refused_before_grant_verifier(self):
        for item in (None, {}, 'pretend400', {'path': 'foreign'}):
            value = dict(self.value, budget_amendment=item)
            with patch.object(budget_amendment, 'validate_cap') as verify:
                with self.subTest(item=item), self.assertRaises(ValueError):
                    runtime._ledger_checks(self.db, value, self.synthetic_original)
            verify.assert_not_called()

    def test_exact_amendment_removes_superseded_extra50_not_window_or_model_ceiling(self):
        # No real grant: this explicit verifier seam only tests runtime wiring.
        binding = {'path': str(self.home/'synthetic-grant.json'), 'sha256': 'd'*64}
        self.db.execute('UPDATE config SET cap=400000000000')
        self.db.execute("INSERT INTO requests VALUES('later','gpt-5.5',51000000000,51000000000,'settled')")
        self.db.commit()
        from earnings_night_budget import history_snapshot
        value = dict(self.value, budget_amendment=binding, baseline=history_snapshot(self.db))
        with patch.object(budget_amendment, 'validate_cap', return_value=400000000000) as verify:
            runtime._ledger_checks(self.db, value, self.synthetic_original)
        verify.assert_called_once_with(self.db, amendment=binding)
        self.db.execute("INSERT INTO requests VALUES('pending','gpt-6.1-sol',5000000001,0,'reserved')")
        self.db.commit()
        with patch.object(budget_amendment, 'validate_cap', return_value=400000000000):
            with self.assertRaises(BudgetStop):
                runtime._ledger_checks(self.db, value, self.synthetic_original)

    def test_long_public_output_is_explicitly_truncated_without_fabricated_semantics(self):
        value = {'text': 'x'*13000}
        projected = review_probe_output(value)
        self.assertFalse(projected['complete'])
        self.assertNotIn('value', projected)
        self.assertEqual(len(projected['json_prefix']), 12000)
        self.assertEqual(projected['value_sha256'], digest(value))


class ResumeAdmission(CampaignIntegrationFixture):
    def setUp(self):
        super().setUp()
        self.ident = 'edgar-population-20261016-04'
        self.inputs = self.owned/'inputs'/self.ident
        self.value['id'] = self.ident
        anchor_source = self.fixture.file('older-anchor.py',
            Path(self.version['R']['path']).read_text()+'\n# older anchor\n')
        anchor = pool.version(anchor_source, self.version['H'], method='inert prior anchor')
        state = pool.initialize(anchor, self.state['protected'],
                                exposed_companies=self.state['exposed_companies'])
        self.version = pool.version(self.version['R'], self.version['H'],
            parent=anchor['id'], axis='R', method='inert retained repair parent',
            evidence=[self.public_evidence])
        self.state = pool.retain(state, self.version, reason='Distinct source-bound parent',
                                 evidence=[self.public_evidence])
        self.feedback['population_sha256'] = digest(self.state)
        closed03 = save(self.owned/'attempts'/resume.IDENT/'population-run-result.json',
                        {'synthetic_closed03_origin': True})
        self.origin.update(population=self.state, previous_result=closed03,
            original_research_feedback=deepcopy(self.feedback))
        for key, value in (('OWNED', self.owned), ('LEDGER', self.ledger), ('REPO', self.repo)):
            self.stack.enter_context(patch.object(resume, key, value))
        self.sources[admission.RESUME_PLAN] = save(self.repo/admission.RESUME_PLAN, {
            'schema': 'supervisor_bottleneck_plan_v1',
            'id': 'earnings-population-resume03-20261016',
            'human_authorization': admission.RESUME_AUTHORIZATION})
        self.value['sources'] = self.sources
        contract_sha = digest(admission.scientific_contract(self.resident))
        latest = dict(schema='earnings_population_campaign_feedback_v1', kind='review_rejected',
            score_state='unscored', company_id=self.feedback['company_id'], round_index=1,
            decision=self.public_evidence, chosen_parent_id=self.version['id'],
            baseline_version_id=self.version['id'], candidate={'id': self.reference['id'],
                'axis': 'R', 'R': self.rejected_source, 'parent': self.version['id']},
            exploration_review={'accepted_for_exploration': False, 'evidence': [self.outcome]},
            results=[], previous_feedback=save(self.root/'immutable02-feedback.json', self.feedback),
            campaign_contract_sha256=contract_sha, last_scored_feedback=self.last_scored,
            scope='Fixture latest03; original02 remains the separate ABI seed.')
        self.origin['research_feedback'] = latest
        self.refresh(feedback=latest, manifest_changes={'comparison_policy': campaign.PARENT_COMPARISON,
            'initial_feedback_contract_sha256': contract_sha})
        self.resume_loader = self.stack.enter_context(patch.object(resume, 'load',
            side_effect=lambda *a, **k: deepcopy(self.origin)))
        self.resume_binding = save(self.inputs/'campaign-resume.json', {
            'schema': 'earnings_population_campaign_resume_v1',
            'previous_result': self.origin['previous_result'],
            'plan': self.sources[admission.RESUME_PLAN],
            'repair': {'schema': 'earnings_population_human_repair_v1',
                'parent_version_id': self.version['id'],
                'human_authorization': admission.RESUME_AUTHORIZATION}})
        self.study['campaign_resume'] = self.resume_binding
        self.runtime['forecast_study'] = save(self.inputs/'study.json', self.study)

    def test_current_resume_uses_latest_origin_and_actual_active_parent_not_old02_loader(self):
        rows = admission.validate(self.value, self.study, self.state)
        self.assertEqual(len(rows), 2)
        self.origin_loader.assert_not_called()
        self.resume_loader.assert_called_once_with(self.origin['previous_result'],
            root=self.owned, ledger=self.ledger, repo=self.repo)
        context = self.context()
        self.assertEqual(context['repair_assignment']['parent_version_id'], self.version['id'])
        self.assertEqual(context['feedback_binding'], self.feedback_binding)
        self.assertEqual(context['original_R_evidence_abi'], self.abi)

    def test_following_round_is_feedback_driven_not_permanently_forced_to_first_repair(self):
        self.packet['round_index'] = 2
        context = self.context()
        self.assertNotIn('repair_assignment', context)
        self.assertEqual(context['feedback_binding'], self.feedback_binding)
        self.assertEqual(context['original_R_evidence_abi'], self.abi)

    def test_changed_resume_parent_authority_plan_or_origin_is_denied(self):
        original = engine.read(self.resume_binding)
        mutations = [dict(original, schema='wrong'),
            dict(original, repair=dict(original['repair'], parent_version_id='e'*64)),
            dict(original, repair=dict(original['repair'], human_authorization='fabricated')),
            dict(original, plan=self.public_evidence)]
        for value in mutations:
            self.study['campaign_resume'] = save(self.inputs/'campaign-resume.json', value)
            with self.subTest(value=value), self.assertRaises(ValueError):
                admission.validate(self.value, self.study, self.state)
        self.study['campaign_resume'] = save(self.inputs/'campaign-resume.json', original)
        self.resume_loader.side_effect = ValueError('Original source/fee closure invalid')
        with self.assertRaisesRegex(ValueError, 'closure invalid'):
            admission.validate(self.value, self.study, self.state)

    def test_foreign_resume_path_rejected_before_history_verifier(self):
        self.study['campaign_resume'] = save(self.root/'foreign-resume.json',
                                             engine.read(self.resume_binding))
        with self.assertRaises(ValueError):
            admission.validate(self.value, self.study, self.state)
        self.resume_loader.assert_not_called()

    def test_latest_campaign_feedback_remains_separate_from_abi_seed_and_last_score(self):
        # Current03 rejection is a campaign envelope, while ABI comes from02.
        previous = save(self.root/'immutable02-feedback.json', self.feedback)
        latest = dict(schema='earnings_population_campaign_feedback_v1', kind='review_rejected',
            score_state='unscored', company_id=self.feedback['company_id'], round_index=1,
            decision=self.public_evidence, chosen_parent_id=self.version['id'],
            baseline_version_id=self.version['id'], candidate={'id': self.reference['id'],
                'axis': 'R', 'R': self.rejected_source, 'parent': self.version['id']},
            exploration_review={'accepted_for_exploration': False, 'evidence': [self.outcome]},
            results=[], previous_feedback=previous,
            campaign_contract_sha256=digest(engine.read(self.campaign)['contract']),
            last_scored_feedback=self.last_scored, scope='Fixture latest03, no score.')
        self.origin['research_feedback'] = latest
        self.refresh(feedback=latest, manifest_changes={'comparison_policy': campaign.PARENT_COMPARISON,
            'initial_feedback_contract_sha256': latest['campaign_contract_sha256']})
        self.study['campaign_resume'] = self.resume_binding
        self.runtime['forecast_study'] = save(self.inputs/'study.json', self.study)
        admission.validate(self.value, self.study, self.state)
        context = self.context()
        self.assertEqual(context['feedback_binding'], self.feedback_binding)
        self.assertEqual(context['original_R_evidence_abi'], self.abi)
        self.assertEqual(context['prior_candidate']['source'], self.rejected_source)
        self.assertEqual(context['research_context']['observations']['original_rejection_probes'],
                         self.feedback['probes'])

