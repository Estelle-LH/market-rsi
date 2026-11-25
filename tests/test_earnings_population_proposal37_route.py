"""New-ID37-prefix routing, on invented metadata and explicit history seams.

Real prepare/current metadata/trusted training receiver and Services adapters
are exercised. Original36, comparator, financial/Native and incident admission
are synthetic boundaries, not a real37 authentication or paid-ready claim.
No provider, production ledger, candidate/scorer or heldout body is used.
"""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest

import earnings_open_resources as resources
import earnings_population_campaign_admission as admission
import earnings_population_proposal_completed as proposal
import earnings_population_runtime as runtime
import earnings_population_services as services
from edgar_forecast_tools import FilingTools
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_population_frozen_panel_runtime as panel_fixture
import test_earnings_population_training35_reuse as training_fixture
import test_earnings_population_review200k_policy as resource_fixture
import test_earnings_open_researcher as execution_fixture

COMPANY = 'CIK0000003545'


class RouteFixture(panel_fixture.PanelFixture):
    needs_A2 = False

    def setUp(self):
        company_patch = patch.object(training_fixture, 'COMPANY', COMPANY)
        company_patch.start(); self.addCleanup(company_patch.stop)
        original_scope_setup = training_fixture.ScopeFixture.setUp
        def original_25_split(fixture):
            # The original split fixture needs its fourth distinct company to
            # retain25 entries; Alico itself is already one of KNOWN3.
            with patch.object(training_fixture, 'COMPANY', 'CIK0000021076'):
                original_scope_setup(fixture)
        with patch.object(training_fixture.ScopeFixture, 'setUp', original_25_split):
            super().setUp()
        # The inherited adapter fixture intentionally has only a placeholder
        # assembly. Supply an invented but genuine literal-assembly record so
        # the real Review change-index verifier runs, rather than mocking it.
        selected = self.f.bundle['scientific_decision']
        business = services.assemble(self.f.parent_r, selected, engine.read(self.f.raw))
        assembly = dict(schema='earnings_population_delta_assembly_v1', axis=selected['axis'],
            parent_version_id=selected['parent_pair_sha256'], parent_source=self.f.parent_r,
            raw_patch_response=self.f.raw, source=self.f.bundle['source'], tests=self.f.bundle['tests'],
            scientific_decision_sha256=digest(selected), assembled_business_sha256=digest(business))
        Path(self.f.assembly['path']).write_text(json.dumps(assembly))
        self.f.assembly = engine.pin(Path(self.f.assembly['path']))
        self.f.bundle['assembly'] = self.f.assembly
        self.id = 'edgar-population-20261016-38'
        # This branch has no35 attachment; retain the ordinary synthetic entry
        # plan but remove its unrelated same-Clorox35-only optional policy.
        entry_plan = engine.read(self.plan); entry_plan.pop('successful_stage_attachment', None)
        Path(self.plan['path']).write_text(json.dumps(entry_plan))
        self.plan = engine.pin(Path(self.plan['path']))
        self.authority = engine.save(self.root/'TRAIN25-DIRECT-NEW-CANDIDATE-AUTHORITY.json',
            dict(human_answer='让 Author 根据完整25家公司 Round0反馈提出新候选，旧34–36仅归档参考'))
        for name, value in (('PROPOSAL_AUTHORITY', self.authority),
                            ('PROPOSAL_ROUND0', self.comparator), ('PROPOSAL_ORIGIN', self.previous)):
            self.stack.enter_context(patch.object(runtime, name, value))
        self.capacity = resource_fixture.Review200PolicyTests(methodName='runTest')
        self.capacity.setUp(); self.addCleanup(self.capacity.doCleanups)
        (self.root/'attempts/edgar-population-20261016-37').mkdir(parents=True)
        self.failure = engine.save(self.root/'attempts/edgar-population-20261016-37/training-proposal-failure.json',
            {'explicit_synthetic_incident_boundary': True})
        self.stack.enter_context(patch.object(proposal, 'FAILED37', self.failure))
        self.stack.enter_context(patch.object(proposal, 'FAILED37_AUTHORITY', self.capacity.bound))
        self.receipt = dict(schema=proposal.FAILED37_SCHEMA, mode=proposal.FAILED37_MODE,
            policy=proposal.failed37_policy(self.id, company_id=COMPANY),
            consumer_attempt_id=self.id, company_id=COMPANY, failed_attempt=self.failure,
            authority=self.capacity.bound, completed_origin=self.previous, base_origin=deepcopy(self.origin),
            task=runtime._proposal_expected(self.scope, COMPANY), candidate=deepcopy(self.f.child),
            parent=deepcopy(self.parent), original_decision=self.f.bundle['decision'],
            scientific_decision=deepcopy(self.f.bundle['scientific_decision']),
            author_stage_reuse=deepcopy(self.f.bundle), review_assessment='not_completed',
            original_completed_generations=dict(controller=8, author=8, review=4),
            evidence=[self.failure, self.f.assembly])
        self.receipt['author_stage_reuse'].update(failed_attempt=self.failure,
            new_model_Controller_called=False, new_model_Author_called=False)
        self.auth = self.stack.enter_context(patch.object(proposal, 'load_failed37_prefix',
            side_effect=lambda binding, **kwargs: deepcopy(self.receipt)))

    def prepare_route(self, **changes):
        options = dict(frozen_panel=None, new_panel_proposal=True,
            review_input_policy=resources.REVIEW200_POLICY, proposal_prefix_failure=self.failure)
        options.update(changes)
        return self.prepare_panel(**options)

    def prepared(self):
        bound = self.prepare_route(); value = engine.read(bound)
        return bound, value, engine.read(value['forecast_study'])


class ProducerReceiverRouteTests(RouteFixture):
    def test_actual_producer_metadata_and_trusted_receiver_use_one_exact_receipt(self):
        _, value, study = self.prepared()
        saved = value['proposal_prefix_reuse']
        self.assertEqual(saved, study['proposal_prefix_reuse'])
        self.assertEqual(Path(saved['path']), self.root/'inputs'/self.id/'proposal-prefix-reuse.json')
        self.assertEqual(engine.read(saved), self.receipt)
        self.assertEqual(runtime._proposal_prefix_metadata(value, study, company_id=COMPANY), self.receipt)
        self.assertEqual(engine.read(study['campaign_origin']), self.origin)
        self.assertEqual(engine.read(value['initial_population']), self.origin['population'])
        self.assertEqual(value['additional_cap_nano_usd'], 5_000_000_000)
        self.assertEqual(value['limits']['review']['max_input_tokens'], 200000)
        self.assertFalse((self.root/'attempts'/self.id).exists())
        self.auth.reset_mock()
        residents = admission._training_validate(value, study, engine.read(value['initial_population']))
        self.assertEqual([r['case']['cik'] for r in residents], [COMPANY])
        self.auth.assert_called_once()
        self.assertEqual(self.auth.call_args.args[0], self.failure)
        self.assertEqual(self.auth.call_args.kwargs['consumer_attempt_id'], self.id)

    def test_receipt_erasure_null_alias_and_foreign_consumer_never_downgrade(self):
        _, value, study = self.prepared()
        for where in ('runtime', 'study', 'both'):
            for null in (False, True):
                v, s = deepcopy(value), deepcopy(study)
                for obj in ([v, s] if where == 'both' else [v if where == 'runtime' else s]):
                    if null: obj['proposal_prefix_reuse'] = None
                    else: obj.pop('proposal_prefix_reuse')
                with self.subTest(where=where, null=null), self.assertRaises(ValueError):
                    runtime._proposal_prefix_metadata(v, s, company_id=COMPANY)
        v, s = deepcopy(value), deepcopy(study)
        alias = dict(v['proposal_prefix_reuse'])
        alias['path'] = str(self.root/'inputs'/self.id/'..'/self.id/'proposal-prefix-reuse.json')
        v['proposal_prefix_reuse'] = s['proposal_prefix_reuse'] = alias
        with self.assertRaises(ValueError): runtime._proposal_prefix_metadata(v, s, company_id=COMPANY)
        path = Path(value['proposal_prefix_reuse']['path'])
        changed = deepcopy(self.receipt); changed['consumer_attempt_id'] = 'edgar-population-20261016-39'
        path.write_text(json.dumps(changed)); v, s = deepcopy(value), deepcopy(study)
        v['proposal_prefix_reuse'] = s['proposal_prefix_reuse'] = engine.pin(path)
        with self.assertRaises(ValueError): runtime._proposal_prefix_metadata(v, s, company_id=COMPANY)

    def test_trusted_receiver_reauthenticates_instead_of_accepting_saved_shape(self):
        _, value, study = self.prepared(); state = engine.read(value['initial_population'])
        self.auth.side_effect = ValueError('Original37 authentication denied')
        with self.assertRaisesRegex(ValueError, 'Original37 authentication denied'):
            admission._training_validate(value, study, state)

    def test_full_saved_receipt_and_verified_base_mismatch_refuse(self):
        _, value, study = self.prepared(); state = engine.read(value['initial_population'])
        for key, bad in (('review_assessment', 'accepted'),
                         ('completed_origin', dict(path='/invented/foreign.json', sha256='a'*64)),
                         ('base_origin', dict(self.origin, population={})),
                         ('candidate', dict(self.f.child, id='f'*64))):
            changed = deepcopy(self.receipt); changed[key] = bad
            self.auth.side_effect = None; self.auth.return_value = changed
            with self.subTest(key=key), self.assertRaises(ValueError):
                admission._training_validate(value, study, state)

    def test_heldout_membership_precedes_receipt_body_and_old_history(self):
        with self.assertRaises(ValueError): self.prepare_route(training_cik=self.p.heldout[0])
        self.auth.assert_not_called(); self.old_loader.assert_not_called()
        self.assertFalse((self.root/'inputs'/self.id).exists())

    def test_current_heldout_receiver_refuses_before_receipt_or_resident_body(self):
        _, value, study = self.prepared(); value['companies'] = [self.p.heldout[0]]
        self.auth.reset_mock(); original = runtime._local
        def no_receipt(bound):
            if bound == study['proposal_prefix_reuse']:
                raise AssertionError('Receipt body read before heldout refusal')
            return original(bound)
        with patch.object(runtime, '_local', side_effect=no_receipt), self.assertRaises(ValueError):
            admission._training_validate(value, study, self.state)
        self.auth.assert_not_called()

    def test_mixed_old_attachment_panel_wrong_failure_and_missing_policy_refuse_early(self):
        for changes in ({'training_stage_attachment': self.p.input},
                        {'frozen_panel': self.descriptor_binding},
                        {'proposal_prefix_failure': dict(self.failure, sha256='f'*64)},
                        {'review_input_policy': None}):
            with self.subTest(changes=changes), self.assertRaises(ValueError): self.prepare_route(**changes)
            self.assertFalse((self.root/'inputs'/self.id).exists())

    def test_legacy_fresh_absence_is_not_automatic_import(self):
        value = engine.read(self.prepare_panel(frozen_panel=None, new_panel_proposal=True))
        study = engine.read(value['forecast_study'])
        self.assertNotIn('proposal_prefix_reuse', value)
        self.assertIsNone(runtime._proposal_prefix_metadata(value, study, company_id=COMPANY))
        self.auth.assert_not_called()


class ServicesPrefixRouteTests(RouteFixture):
    """Real C/A/fresh Review methods; case/model/receipt runner are inert seams."""

    def prepare_services(self):
        _, self.value, self.study = self.prepared()
        self.owner = self.f.owner
        self.owner.root = Path(self.value['root'])
        self.owner.native_root = self.root/'new-native'; self.owner.native_root.mkdir()
        self.owner.runtime = self.value
        self.owner._training_scope = Mock(return_value=self.scope)
        # The real _proposal_task separately pins production4aa/7a document
        # hashes. These invented producer documents cannot claim those hashes;
        # only that task-certificate seam is supplied for Services. Canonical
        # prefix metadata/_reuse_origin and all three stage methods stay real.
        self.owner._proposal_task = Mock(return_value=deepcopy(self.receipt['task']))
        company = deepcopy(self.resident['company'])
        self.owner.case = Mock(return_value=dict(company=company,
            state_api=SimpleNamespace(tools=FilingTools(company))))
        self.current_feedback = engine.read(self.study['campaign'])['initial_feedback']
        summary = dict(schema='earnings_training25_public_summary_v1',
            split=self.scope['split'], manifest=self.comparator,
            target_order=[f'T{i:03d}' for i in range(1, 6)],
            rows=[dict(company_id=cik, points=3, targets=[dict(target_id=f'T{i:03d}',
                predicted_value=str(index*10+i), points_awarded=1 if i<4 else 0)
                for i in range(1, 6)]) for index, cik in enumerate(self.scope['training'])])
        self.context = deepcopy(self.f.context)
        self.context.update(origin=self.study['campaign_origin'],
            campaign=engine.read(self.study['campaign']), feedback_binding=self.current_feedback,
            training_scope=deepcopy(self.scope), training_comparator=summary, training_state={})
        self.context['research_context']['observations']['training_comparator'] = deepcopy(summary)
        request = {'research_requests': [{'tool': 'search_files', 'arguments': {
            'query': 'revenue', 'path_prefix': 'filings/', 'max_hits': 5}}]}
        advice = dict(coverage={'extracted_cells': 0}, evidence=[], method='Invented public observation',
            targets=[dict(target_id=f'T{i:03d}', status='incomplete', missing=['metric']) for i in range(1, 6)])
        self.owner.runner = execution_fixture.ScriptedReceiptRunner(self.root/'new-runner',
            [deepcopy(v) for _ in range(4) for v in (request, advice)])
        self.review_prompts = []

        def fresh_review(prompt, slot):
            self.review_prompts.append(deepcopy(prompt)); Path(slot).mkdir(parents=True)
            raw = engine.save(Path(slot)/'response.json', {'explicit_synthetic_new_Review': True})
            engine.save(Path(slot)/'review.json', dict(original=raw, review=dict(
                candidate_id=prompt['candidate_id'], accepted_for_exploration=False,
                rationale='New independent synthetic Review rejects; no empirical score.')))
            return raw

        self.new_review = Mock(side_effect=fresh_review)
        def role(name, kind, case, slot):
            if name == 'review':
                return SimpleNamespace(review=self.new_review,
                    broker=SimpleNamespace(references=lambda: deepcopy(self.owner.role_versions)))
            return self.f.role
        self.owner.role = Mock(side_effect=role)

    def drive_services(self):
        self.prepare_services()
        packet = dict(company_id=COMPANY, population=deepcopy(self.state), round_index=1,
            feedback=self.current_feedback, parent_feedback_sha256=digest(self.current_feedback),
            campaign=self.study['campaign'], scope='Invented whole25 proposal receiving test')
        self.owner.root.mkdir(parents=True)
        engine.save(self.owner.root/'packet-01.json', packet)  # Ordinary new input-stage fixture.
        with patch.object(services, 'public_feedback', return_value={'company_id': COMPANY}), \
             patch('earnings_population_campaign_context.prepare', return_value=deepcopy(self.context)), \
             patch.object(services, 'run_cases', return_value=[{'passed': True, 'synthetic': True}]):
            chosen_bound = self.owner.controller(packet, self.value['slots']['controller'][0])
            chosen = engine.read(chosen_bound)
            child = self.owner.author(chosen, self.state, self.value['slots']['author'][0])
            reviewed = self.owner.review(child, self.state, self.value['slots']['review'][0])
        return chosen, child, reviewed

    def test_real_services_reuse_CA_markers_but_call_new_review_and_preserve_old_science(self):
        chosen, child, reviewed = self.drive_services()
        self.f.role.propose.assert_not_called(); self.f.role.author.assert_not_called()
        self.new_review.assert_called_once()
        self.assertFalse(reviewed['accepted_for_exploration'])
        self.assertEqual(child, self.f.child)
        original = engine.read(self.f.bundle['decision'])
        self.assertEqual(chosen['feedback_sha256'], digest(self.current_feedback))
        for key in original:
            if key != 'feedback_sha256': self.assertEqual(chosen[key], original[key])
        self.assertEqual(self.owner.authored[child['id']]['decision'], self.f.bundle['scientific_decision'])
        self.assertEqual(Path(child['R']['path']).read_text(), Path(self.f.child['R']['path']).read_text())
        for role in ('controller', 'author'):
            folder = Path(self.value['slots'][role][0])
            marker = engine.read(engine.pin(folder/(role+'-stage-reuse.json')))
            self.assertIs(marker['new_model_called'], False)
            self.assertFalse(list(folder.glob('http-*')))
            self.assertFalse(list(folder.glob('[0-9][0-9]-request.json')))
            self.assertFalse((folder/'response.json').exists())
            self.assertFalse((folder/'result.json').exists())
        self.assertFalse(self.f.marker.exists())

    def test_fresh_review_receives_honest37_diagnosis_not_old10_financial_story(self):
        _, child, _ = self.drive_services()
        prompt = self.review_prompts[0]
        self.assertEqual(prompt['candidate_id'], child['id'])
        self.assertIn('successful_Author_stage_reuse', prompt)
        failure = prompt['prior_Review_delivery_failure']
        self.assertEqual(failure['failed_attempt'], self.failure)
        self.assertEqual(failure['observed_input_tokens'], [32976, 33290])
        self.assertEqual(failure['prior_input_limit'], 32000)
        self.assertEqual(failure['review_assessment'], 'not_completed')
        self.assertEqual(failure['completed_Review_generations'], 4)
        self.assertNotIn('known_public_tradeoff', prompt)
        self.assertNotIn('human_repair_acceptance', prompt)
        self.assertNotIn('T002 acquisition regression', json.dumps(prompt))
        self.assertNotIn('Prior public cold audit reported improved T005', json.dumps(prompt))
        self.assertIn('not full25', prompt['evaluation_scope'])
        self.assertEqual(len(prompt['proposal_task']['training_companies']), 25)
        self.assertFalse((Path(self.value['slots']['review'][0])/'review-stage-reuse.json').exists())


if __name__ == '__main__':
    unittest.main()
