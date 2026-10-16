"""Independent inert role/service contracts; no API, Docker or real ledger.

Role generations/accounting and forecast execution are explicitly mocked.
Raw artifacts, projection logic, ordinary Native journal/source checks and
population loop ordering are actual implementations. No live proof is claimed.
"""
from copy import deepcopy
import inspect
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import earnings_open_roles as open_roles
import earnings_population_execution as execution
import earnings_population_roles as roles
import earnings_population_services as services
from earnings_population_broker import PopulationBroker, public_feedback
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_open_roles as role_fixture
import test_earnings_open_researcher as receipt_fixture
import test_earnings_population as pool_fixture
import test_earnings_population_case as native_fixture
import test_earnings_population_loop as loop_fixture


class PopulationRoleContractTests(unittest.TestCase):
    def setUp(self):
        self.fixture = role_fixture.OpenRoleTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.prompt = {'active_versions': ['a'*64, 'c'*64], 'explorers': ['c'*64],
                       'feedback_sha256': 'b'*64, 'company_id': 'synthetic-company'}

    def role(self, review=False):
        original = self.fixture.service(max_turns=1)
        if not review:
            return roles.PopulationController(original.binding, budget=self.fixture.budget,
                client_factory=self.fixture.factory, broker=self.fixture.broker, max_turns=1)
        context = deepcopy(original.context)
        self.fixture.slot = self.fixture.root/'roles'/'review-01'
        context.update(schema='earnings_capacity_review_transport_v1', slots=[str(self.fixture.slot)])
        binding = engine.save(self.fixture.root/'review-context.json', context)
        return roles.PopulationReviewer(binding, budget=self.fixture.budget,
            client_factory=self.fixture.factory, broker=self.fixture.broker, max_turns=1)

    def choice(self, **changes):
        return dict(self.fixture.choice(), retire_branch_id='none', **changes)

    def invoke(self, value, *, review=False):
        role = self.role(review)
        self.fixture.generations = [self.fixture.message(value)]
        with patch.object(open_roles, 'budgeted_response', side_effect=self.fixture.fake_paid):
            if review:
                return role.review({'candidate_id': 'c'*64}, str(self.fixture.slot))
            return role.propose(self.prompt, str(self.fixture.slot))

    def test_controller_retirement_projection_preserves_original_and_exact_identities(self):
        chosen = self.choice()
        chosen['retire_branch_id'] = 'c'*64
        before = deepcopy(chosen)
        bound = self.invoke(chosen)
        raw = Path(bound['path']).read_bytes()
        self.assertEqual(raw, (self.fixture.slot/'01-response.json').read_bytes())
        projected = engine.read(engine.pin(self.fixture.slot/'decision.json'))
        self.assertEqual(projected['original'], bound)
        self.assertEqual(projected['decision'], chosen)
        scientific = roles.scientific(chosen)
        self.assertEqual(chosen, before)
        self.assertNotIn('retire_branch_id', scientific)
        for field in ('parent_pair_sha256', 'feedback_sha256', 'hypothesis', 'expected_effect'):
            self.assertEqual(scientific[field], chosen[field])
        self.assertIn('retire_branch_id', self.fixture.requests[0]['instructions'])
        self.assertEqual(self.fixture.requests[0]['tool_choice'], 'none')

    def test_none_retirement_normalizes_only_optional_operational_field(self):
        chosen = self.choice()
        self.invoke(chosen)
        projection = engine.read(engine.pin(self.fixture.slot/'decision.json'))['decision']
        self.assertEqual(projection, {key: value for key, value in chosen.items() if key != 'retire_branch_id'})

    def test_extra_business_field_fails_once_preserving_actual_response(self):
        chosen = self.choice()
        chosen['unrequested_field'] = 'not allowed'
        with self.assertRaises(RuntimeError):
            self.invoke(chosen)
        before = (self.fixture.slot/'response.json').read_bytes()
        self.assertEqual(json.loads(before)['output'][0]['content'][0]['text'], json.dumps(chosen))
        result = engine.read(engine.pin(self.fixture.slot/'result.json'))
        self.assertEqual(result['status'], 'FAILED_NO_RETRY')
        self.assertFalse(result['retry_allowed'])
        self.assertFalse((self.fixture.slot/'decision.json').exists())
        with patch.object(open_roles, 'budgeted_response', side_effect=self.fixture.fake_paid):
            with self.assertRaises(FileExistsError):
                roles.PopulationController(engine.pin(self.fixture.context_path), budget=self.fixture.budget,
                    client_factory=self.fixture.factory, broker=self.fixture.broker).propose(self.prompt, str(self.fixture.slot))
        self.assertEqual((self.fixture.slot/'response.json').read_bytes(), before)
        self.assertEqual(len(self.fixture.requests), 1)

    def test_raw_refusal_tool_incomplete_and_multiple_messages_are_rejected(self):
        valid = self.fixture.message(self.choice())
        responses = []
        wrong = deepcopy(valid); wrong['status'] = 'incomplete'; responses.append(wrong)
        wrong = deepcopy(valid); wrong['output'][0]['content'] = [{'type': 'refusal', 'refusal': 'no'}]; responses.append(wrong)
        wrong = deepcopy(valid); wrong['output'].append(deepcopy(wrong['output'][0])); responses.append(wrong)
        wrong = deepcopy(valid); wrong['output'].append({'type': 'function_call'}); responses.append(wrong)
        wrong = deepcopy(valid); wrong['output'][0]['role'] = 'user'; responses.append(wrong)
        for index, value in enumerate(responses):
            with self.subTest(case=index), self.assertRaises(ValueError):
                roles.message(value)

    def test_scientific_projection_rejects_undeclared_field_not_silent_rewrite(self):
        chosen = self.choice()
        chosen['budget_override'] = 1000000
        with self.assertRaises(ValueError):
            roles.scientific(chosen)

    def test_controller_wrong_parent_feedback_or_stable_retirement_refused(self):
        for index, changes in enumerate(({'parent_pair_sha256': 'f'*64}, {'feedback_sha256': 'f'*64},
                                         {'retire_branch_id': 'a'*64})):
            role = roles.PopulationController.__new__(roles.PopulationController)
            def run(prompt, slot, instructions, response_format, decode, artifact, status):
                return decode(self.fixture.message(dict(self.choice(), **changes)))
            role._run_open = run
            with self.subTest(case=index), self.assertRaises(ValueError):
                role.propose(self.prompt, 'synthetic-never-dispatched')

    def test_full_explorer_pool_requires_explicit_replacement_for_mutation(self):
        self.prompt['explorers'].append('d'*64)
        self.prompt['active_versions'].append('d'*64)
        role = roles.PopulationController.__new__(roles.PopulationController)
        role._run_open = lambda prompt, slot, instructions, fmt, decode, artifact, status: decode(
            self.fixture.message(self.choice()))
        with self.assertRaises(ValueError):
            role.propose(self.prompt, 'synthetic-never-dispatched')

    def test_reviewer_uses_its_own_final_schema_hint_and_preserves_original(self):
        chosen = {'candidate_id': 'c'*64, 'accepted_for_exploration': True,
                  'rationale': 'Synthetic contract acceptance, no financial-correctness claim.'}
        original = self.invoke(chosen, review=True)
        projection = engine.read(engine.pin(self.fixture.slot/'review.json'))
        self.assertEqual(projection, {'original': original, 'review': chosen})
        self.assertEqual(Path(original['path']).read_bytes(), (self.fixture.slot/'01-response.json').read_bytes())
        final = self.fixture.requests[0]['instructions']
        self.assertIn('candidate_id, accepted_for_exploration and rationale', final)
        self.assertNotIn(open_roles.FINAL_CONTROLLER, final)
        self.assertEqual(self.fixture.requests[0]['tool_choice'], 'none')

    def test_default_final_hook_remains_equivalent_for_original_roles(self):
        for kind, expected in ((open_roles.OpenController, open_roles.FINAL_CONTROLLER),
                               (open_roles.OpenAuthor, open_roles.FINAL_AUTHOR)):
            self.assertEqual(kind.__new__(kind)._final_instruction(), expected)


class PopulationServiceProjectionTests(pool_fixture.PopulationFixture):
    def setUp(self):
        super().setUp()
        self.owner = services.Services.__new__(services.Services)
        self.owner.contexts = {}
        self.owner.traces = {}
        self.owner.current = None
        self.case = {'state_api': SimpleNamespace(tools=SimpleNamespace(files={'questions.md': 'synthetic public questions'}))}
        self.owner.case = Mock(return_value=self.case)
        sources = {axis: Path(self.stable[axis]['path']).read_text() for axis in ('R', 'H')}
        self.broker = SimpleNamespace(current_sources=lambda: sources, available_traces=lambda: [], references=lambda: {})
        self.role = SimpleNamespace(broker=self.broker, propose=self.propose)
        self.owner.role = Mock(return_value=self.role)
        self.prompts = []
        self.original = self.artifact({'synthetic_response': True})

    def propose(self, prompt, slot):
        self.prompts.append(deepcopy(prompt))
        Path(slot).mkdir(parents=True, exist_ok=False)
        engine.save(Path(slot)/'decision.json', {'original': self.original, 'decision': {
            'axis': 'continue', 'parent_pair_sha256': self.stable['id'],
            'feedback_sha256': prompt['feedback_sha256'], 'hypothesis': 'Synthetic only'}})
        return self.original

    def feedback(self):
        secret = self.artifact({'per_target': [{'actual_value': 'DO_NOT_SEND_LABEL_123'}], 'qa': 'DO_NOT_SEND_QA_456'})
        public = engine.save(self.root/'population-public-feedback.json', {'schema': 'earnings_population_public_trial_v1',
            'version_id': self.stable['id'], 'company_id': 'synthetic-prior', 'points': 1.0,
            'target_scores': [{'target_id': f'T{i:03d}', 'points_awarded': int(i == 1)} for i in range(1, 6)],
            'pool_sources': {axis: self.stable[axis]['sha256'] for axis in ('R', 'H')},
            'native_pair_sha256': 'c'*64, 'scope': 'Synthetic public projection'})
        value = {'schema': 'earnings_population_feedback_v1', 'company_id': 'synthetic-prior',
            'round_index': 1, 'stable_id': self.stable['id'], 'scope': 'Discovery',
            'results': [{'version_id': self.stable['id'], 'points': 1.0, 'evidence': [public, secret]}]}
        return self.artifact(value), public

    def test_actual_feedback_points_projected_no_hidden_score_or_qa_in_prompt(self):
        feedback, public = self.feedback()
        packet = {'company_id': 'synthetic-next', 'population': self.initial,
                  'feedback': feedback, 'parent_feedback_sha256': digest(feedback)}
        before = deepcopy(packet)
        self.owner.controller(packet, str(self.root/'controller-02'))
        prompt = self.prompts[0]
        self.assertEqual(packet, before)
        self.assertEqual(prompt['feedback_sha256'], digest(feedback))
        self.assertEqual(prompt['feedback_binding'], feedback)
        self.assertEqual(prompt['feedback']['results'][0]['points'], 1.0)
        self.assertEqual(len(prompt['feedback']['results'][0]['target_scores']), 5)
        serialized = json.dumps(prompt)
        self.assertNotIn('DO_NOT_SEND_LABEL', serialized)
        self.assertNotIn('DO_NOT_SEND_QA', serialized)
        self.assertNotIn('actual_value', serialized)
        self.assertEqual(prompt['current_programs']['R']['source_sha256'], self.stable['R']['sha256'])
        self.assertEqual(self.owner.current, 'synthetic-next')

    def test_public_feedback_join_rejects_company_version_points_and_source_drift(self):
        feedback, original = self.feedback()
        for index, changes in enumerate(({'company_id': 'another-company'},
            {'version_id': 'f'*64}, {'points': 5.0}, {'pool_sources': {'R': 'f'*64, 'H': 'f'*64}})):
            public = dict(engine.read(original), **changes)
            directory = self.root/f'public-{index}'; directory.mkdir()
            altered = engine.save(directory/'population-public-feedback.json', public)
            body = engine.read(feedback); body['results'][0]['evidence'][0] = altered
            with self.subTest(change=changes), self.assertRaises(ValueError):
                public_feedback(self.artifact(body), self.initial['versions'])

    def test_public_feedback_rejects_missing_duplicate_or_hidden_target_fields(self):
        feedback, original = self.feedback()
        public = engine.read(original)
        variants = [[], public['target_scores'][:-1],
                    [dict(public['target_scores'][0]) for _ in range(5)],
                    [dict(row, actual_value='DO_NOT_SEND_LABEL') for row in public['target_scores']]]
        for index, targets in enumerate(variants):
            directory = self.root/f'targets-{index}'; directory.mkdir()
            altered = engine.save(directory/'population-public-feedback.json', dict(public, target_scores=targets))
            body = engine.read(feedback); body['results'][0]['evidence'][0] = altered
            with self.subTest(case=index), self.assertRaises(ValueError):
                public_feedback(self.artifact(body), self.initial['versions'])

    def test_public_feedback_never_falls_back_to_raw_score_or_reads_hidden_artifact(self):
        feedback, public = self.feedback()
        body = engine.read(feedback)
        hidden = body['results'][0]['evidence'][1]
        Path(hidden['path']).write_text('changed hidden host-only scorer bytes')
        projected = public_feedback(feedback, self.initial['versions'])
        self.assertEqual(projected['results'][0]['points'], 1.0)
        for evidence in ([hidden], [public, public, hidden]):
            malformed = deepcopy(body); malformed['results'][0]['evidence'] = evidence
            with self.subTest(count=len(evidence)), self.assertRaises(ValueError):
                public_feedback(self.artifact(malformed), self.initial['versions'])

    def test_public_target_awards_reject_boolean_not_original_numeric_point(self):
        feedback, original = self.feedback()
        public = engine.read(original)
        public['target_scores'][0]['points_awarded'] = True
        directory = self.root/'boolean-points'; directory.mkdir()
        altered = engine.save(directory/'population-public-feedback.json', public)
        body = engine.read(feedback); body['results'][0]['evidence'][0] = altered
        with self.assertRaises(ValueError):
            public_feedback(self.artifact(body), self.initial['versions'])

    def test_rejected_candidate_rationale_reaches_next_actual_controller_prompt(self):
        feedback, public = self.feedback()
        outcome = engine.save(self.root/'review-01-outcome.json', {
            'schema': 'earnings_population_exploration_review_v1', 'candidate_id': 'c'*64,
            'accepted_for_exploration': False, 'rationale': 'Synthetic cold-start acquisition defect',
            'host_only_diagnostic': 'DO_NOT_SEND_INTERNAL_BLOB'})
        original = engine.read(feedback)
        original['exploration_review'] = {'candidate_id': 'c'*64, 'accepted_for_exploration': False,
                                          'evidence': [outcome, self.original]}
        bound = self.artifact(original)
        self.owner.controller({'company_id': 'synthetic-next', 'population': self.initial,
            'feedback': bound, 'parent_feedback_sha256': digest(bound)}, str(self.root/'controller-rejection'))
        reviewed = self.prompts[0]['feedback']['exploration_review']
        self.assertEqual(reviewed, {'candidate_id': 'c'*64, 'accepted_for_exploration': False,
                                    'rationale': 'Synthetic cold-start acquisition defect'})
        self.assertNotIn('DO_NOT_SEND_INTERNAL_BLOB', json.dumps(self.prompts[0]))

    def test_review_outcome_identity_or_acceptance_drift_is_rejected(self):
        feedback, public = self.feedback()
        for index, changes in enumerate(({'candidate_id': 'f'*64}, {'accepted_for_exploration': True})):
            body = dict(schema='earnings_population_exploration_review_v1', candidate_id='c'*64,
                        accepted_for_exploration=False, rationale='Synthetic rejected candidate')
            body.update(changes)
            outcome = engine.save(self.root/f'review-{index}-outcome.json', body)
            original = engine.read(feedback)
            original['exploration_review'] = {'candidate_id': 'c'*64, 'accepted_for_exploration': False,
                                              'evidence': [outcome]}
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                public_feedback(self.artifact(original), self.initial['versions'])

    def test_wrong_preceding_feedback_schema_refuses_before_controller_generation(self):
        packet = {'company_id': 'synthetic-next', 'population': self.initial,
                  'feedback': self.artifact({'schema': 'wrong'}), 'parent_feedback_sha256': 'a'*64}
        with self.assertRaises(ValueError):
            self.owner.controller(packet, str(self.root/'controller-02'))
        self.assertEqual(self.prompts, [])

    def test_factories_are_source_bound_and_borrow_dependencies_without_dispatch(self):
        factories = self.owner.factories()
        budget, client = Mock(), Mock()
        for name, factory in factories.items():
            self.assertEqual(Path(inspect.getsourcefile(factory)).resolve(), Path(services.__file__).resolve())
            bound = {'path': '/synthetic/not-opened', 'sha256': 'a'*64}
            actual = factory(bound, budget=budget, client_factory=client)
            self.assertEqual(actual, getattr(self.owner, name))
            self.assertEqual(self.owner.contexts[name], (bound, {'budget': budget, 'client_factory': client}))
        budget.assert_not_called(); client.assert_not_called()


class PopulationExecutionProjectionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = native_fixture.PopulationCaseTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.case = self.fixture.prepare()
        self.slot = self.fixture.root/'roles'/'forecast-01-00'
        self.slot.mkdir(parents=True)
        questions = '\n'.join(f'### T{i:03d} | Synthetic question' for i in range(1, 6))
        score = {'score_out_of_5': 2.5, 'target_count': 5, 'prediction_count': 5,
            'duplicate_prediction_ids': [], 'unknown_prediction_ids': [],
            'per_target': [{'target_id': f'T{i:03d}', 'points_awarded': point,
                            'actual_value': 'DO_NOT_SEND_LABEL_123', 'prediction_value': 1000}
                           for i, point in enumerate((1, 0.5, 0, 1, 0), 1)]}
        self.output = {'score': engine.save(self.slot/'score.json', score),
                       'result': engine.save(self.slot/'result.json', {'status': 'COMPLETED_SCORED', 'synthetic': True})}
        engine.save(self.slot/'effective-capacity.json', {'synthetic': True})
        self.worker = SimpleNamespace(files={'questions.md': questions}, state_api=self.case['state_api'])
        self.verified = {'consumed': {'pair_sha256': self.case['pair_sha256']},
                         'artifacts': list(self.output.values())}
        self.before_claim = Mock()

    def execute(self):
        with patch.object(execution, 'ProgramWorker', return_value=self.worker), \
             patch.object(execution, 'CapacityForecast') as forecast, \
             patch.object(execution, 'OpenTask') as task:
            forecast.return_value.forecast.return_value = self.output
            task.return_value.execution.return_value = self.verified
            return execution.execute(self.case, self.fixture.version, str(self.slot), runner=Mock(),
                context={'synthetic': True}, budget=Mock(), client_factory=Mock(),
                study={'synthetic': True}, clock={'synthetic': True},
                transport_policy={'synthetic': True}, before_claim=self.before_claim)

    def test_public_projection_uses_original_points_and_exact_native_source_mapping(self):
        result = self.execute()
        public = engine.read(result['evidence'][0])
        self.assertEqual(public['points'], 2.5)
        self.assertEqual(public['native_pair_sha256'], self.case['pair_sha256'])
        self.assertEqual(public['pool_sources'], {axis: self.fixture.version[axis]['sha256'] for axis in ('R', 'H')})
        self.assertEqual(len(public['target_scores']), 5)
        self.assertEqual(sum(row['points_awarded'] for row in public['target_scores']), 2.5)
        self.assertNotIn('DO_NOT_SEND_LABEL', json.dumps(public))
        self.assertNotIn('actual_value', json.dumps(public))
        self.assertEqual(self.case['capacity'].batch.snapshot()['capacity_work'][0]['status'], 'completed')
        self.before_claim.assert_called_once()
        self.assertFalse(self.fixture.marker.exists())

    def test_wrong_consumed_pair_stops_without_complete_or_public_result(self):
        self.verified['consumed']['pair_sha256'] = 'f'*64
        with self.assertRaises(ValueError):
            self.execute()
        self.assertFalse((self.slot/'population-public-feedback.json').exists())
        self.assertEqual(self.case['capacity'].batch.snapshot()['capacity_work'][0]['status'], 'claimed')

    def test_wrong_pool_source_mapping_stops_without_complete(self):
        self.fixture.version = deepcopy(self.fixture.version)
        self.fixture.version['R']['sha256'] = 'f'*64
        with self.assertRaises(ValueError):
            self.execute()
        self.assertEqual(self.case['capacity'].batch.snapshot()['capacity_work'][0]['status'], 'claimed')


class PopulationAuthorAndFailureTests(unittest.TestCase):
    def setUp(self):
        self.fixture = native_fixture.PopulationCaseTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.owner = services.Services.__new__(services.Services)
        self.owner.case = Mock(return_value={'synthetic': 'no admission mocked as live proof'})
        self.owner.authored, self.owner.pending, self.owner.traces = {}, [], {}
        self.owner.runner = Mock()
        self.owner.current = 'synthetic-company'
        self.owner.contexts = {'forecast': ({'synthetic_context': True}, {'budget': Mock(), 'client_factory': Mock()})}
        self.owner.runtime = {'forecast_study': {'synthetic': True}}
        self.owner.clock = self.owner.transport_policy = {'synthetic': True}
        self.state = {'versions': {self.fixture.version['id']: self.fixture.version},
                      'stable_id': self.fixture.version['id'], 'explorers': []}

    def test_author_original_projection_keeps_parent_feedback_and_changes_only_R_source(self):
        chosen = {'schema': 'earnings_capacity_decision_v1', 'axis': 'R', 'component': 'research_policy',
            'parent_pair_sha256': self.fixture.version['id'], 'feedback_sha256': 'b'*64,
            'hypothesis': 'Synthetic method change', 'expected_effect': 'Synthetic contract only',
            'retire_branch_id': 'c'*64}
        seen = []
        def author(scientific, before, slot):
            seen.append(deepcopy(scientific))
            Path(slot).mkdir(parents=True)
            return engine.save(Path(slot)/'response.json', {
                'decision_sha256': digest(scientific),
                'source_text': "PROGRAM={'axis':'R'}\ndef run(payload): return {'new_method': True}\n",
                'test_text': "CASES=[{'input': {}, 'expected': {'new_method': True}}]"})
        self.owner.role = Mock(return_value=SimpleNamespace(author=author))
        slot = self.fixture.root/'roles'/'author-01'
        child = self.owner.author(chosen, self.state, str(slot))
        self.assertEqual(child['parent'], self.fixture.version['id'])
        self.assertEqual(child['H'], self.fixture.version['H'])
        self.assertNotEqual(child['R']['sha256'], self.fixture.version['R']['sha256'])
        self.assertEqual(seen[0], {key: value for key, value in chosen.items() if key != 'retire_branch_id'})
        projection = engine.read(engine.pin(slot/'scientific-decision-projection.json'))
        self.assertEqual(projection['population_decision'], chosen)
        self.assertEqual(projection['scientific_decision'], seen[0])
        self.assertIn(child['id'], self.owner.authored)
        self.assertFalse(self.fixture.marker.exists())

    def test_failed_author_cases_reject_before_independent_paid_review(self):
        child = self.fixture.version
        self.owner.authored[child['id']] = {'source': Path(self.fixture.r['path']).read_text(),
            'parsed': {'cases': [{'input': {}, 'expected': {}}]}, 'originals': [], 'decision': {}}
        self.owner.native_root = self.fixture.root
        self.owner.role = Mock()
        with patch.object(services, 'run_cases', return_value=[{'passed': False, 'execution': {'synthetic': True}}]), \
             patch.object(services.researcher, 'run') as probe:
            result = self.owner.review(child, self.state, str(self.fixture.root/'roles'/'review-01'))
        self.assertFalse(result['accepted_for_exploration'])
        self.owner.role.assert_not_called()
        probe.assert_not_called()
        self.assertFalse(self.fixture.marker.exists())

    def cold_probe_setup(self):
        case = self.fixture.prepare(root=self.fixture.root/'review-native')
        self.owner.case = Mock(return_value=case)
        self.owner.native_root = self.fixture.root
        self.owner.current = case['company']['cik']
        source = "PROGRAM={'axis':'R'}\ndef run(payload): return {'method': 'synthetic probe candidate'}\n"
        child = services.describe(self.fixture.file('probe-candidate.py', source), self.fixture.h,
            parent=self.fixture.version['id'], axis='R', method='Synthetic cold admission',
            author='synthetic-not-model', evidence=[self.fixture.authority])
        self.owner.authored[child['id']] = {'source': source,
            'parsed': {'cases': [{'input': {}, 'expected': {'method': 'synthetic probe candidate'}}]},
            'originals': [self.fixture.authority], 'decision': {'axis': 'R'}}
        return case, child, source

    def test_R_review_runs_both_current_company_empty_state_probes_before_paid_review(self):
        case, child, source = self.cold_probe_setup()
        events, payloads, prompts = [], [], []
        def probe(runner, actual_source, payload, tools):
            events.append('run-'+payload['stage']); payloads.append(deepcopy(payload))
            self.assertIs(runner, self.owner.runner)
            self.assertEqual(actual_source, source)
            self.assertIs(tools, case['state_api'].tools)
            scripted = receipt_fixture.ScriptedReceiptRunner(self.fixture.root/('cold-'+payload['stage']),
                [{'coverage': {'extracted_cells': 0}, 'evidence': [], 'targets': [
                    {'target_id': f'T{i:03d}', 'status': 'incomplete', 'missing': ['metric']}
                    for i in range(1, 6)]}])
            return scripted.run(actual_source, payload)
        original_verify = services.researcher.verify
        def verify(run, actual_source, payload, company):
            events.append('verify-'+payload['stage'])
            self.assertEqual(company, case['company'])
            self.assertEqual(actual_source, source)
            return original_verify(run, actual_source, payload, company)
        def review(prompt, slot):
            events.append('paid-review'); prompts.append(deepcopy(prompt))
            Path(slot).mkdir(parents=True)
            original = engine.save(Path(slot)/'response.json', {'synthetic_review_response': True})
            engine.save(Path(slot)/'review.json', {'original': original,
                'review': {'accepted_for_exploration': True, 'rationale': 'Synthetic contract acceptance'}})
            return original
        self.owner.role = Mock(return_value=SimpleNamespace(review=review,
            broker=SimpleNamespace(references=lambda: {'candidate_source': child['R']['sha256']})))
        with patch.object(services, 'run_cases', return_value=[{'passed': True, 'synthetic': True}]), \
             patch.object(services.researcher, 'run', side_effect=probe), \
             patch.object(services.researcher, 'verify', side_effect=verify):
            result = self.owner.review(child, self.state, str(self.fixture.root/'roles'/'review-02'))
        self.assertTrue(result['accepted_for_exploration'])
        self.assertEqual(events, ['run-forecast', 'verify-forecast', 'run-controller', 'verify-controller', 'paid-review'])
        for payload in payloads:
            self.assertEqual(payload['records'], [])
            self.assertEqual(payload['questions'], case['state_api'].tools.files['questions.md'])
            self.assertEqual(payload['filing_index'], case['state_api'].tools.files['filing_index.tsv'])
        self.assertNotIn('feedback', payloads[0])
        self.assertIn('research_objective', payloads[1])
        self.assertEqual(prompts[0]['company_id'], case['company']['cik'])
        probes = prompts[0]['original_public_empty_state_probes']
        self.assertEqual([row['stage'] for row in probes], ['forecast', 'controller'])
        for row in probes:
            self.assertIn(row['receipt'], result['evidence'])
            self.assertEqual(engine.read(row['receipt'])['input']['records'], [])
        self.assertFalse(self.fixture.marker.exists())

    def test_failed_current_company_R_probe_stops_before_paid_review_preserving_first_probe(self):
        case, child, source = self.cold_probe_setup()
        self.owner.role = Mock()
        observed = []
        def probe(runner, actual_source, payload, tools):
            observed.append(payload['stage'])
            if payload['stage'] == 'controller':
                raise RuntimeError('Synthetic actual-interface probe failure; no automatic retry')
            scripted = receipt_fixture.ScriptedReceiptRunner(self.fixture.root/'first-cold-probe',
                [{'coverage': {'extracted_cells': 0}, 'targets': [], 'evidence': []}])
            return scripted.run(actual_source, payload)
        original_verify = services.researcher.verify
        with patch.object(services, 'run_cases', return_value=[{'passed': True, 'synthetic': True}]), \
             patch.object(services.researcher, 'run', side_effect=probe), \
             patch.object(services.researcher, 'verify', wraps=original_verify) as verify:
            with self.assertRaises(RuntimeError):
                self.owner.review(child, self.state, str(self.fixture.root/'roles'/'review-03'))
        self.assertEqual(observed, ['forecast', 'controller'])
        verify.assert_called_once()
        self.owner.role.assert_not_called()
        self.assertTrue((self.fixture.root/'review-03-forecast-probe.json').exists())
        self.assertFalse((self.fixture.root/'review-03-controller-probe.json').exists())
        self.assertFalse(self.fixture.marker.exists())

    def test_forecast_failure_keeps_claim_for_owner_reconciliation_without_retry(self):
        calls = []
        def fail(case, version, slot, **options):
            calls.append(slot)
            options['before_claim'](case, 'synthetic-claimed-work')
            raise RuntimeError('Synthetic execution interruption')
        with patch.object(services, 'execute', side_effect=fail):
            with self.assertRaises(RuntimeError):
                self.owner.forecast(self.fixture.version, self.owner.current,
                                    str(self.fixture.root/'roles'/'forecast-01-00'))
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(self.owner.pending), 1)
        self.assertEqual(self.owner.pending[0][1], 'synthetic-claimed-work')
        self.assertEqual(self.owner.traces, {})

class PopulationOrdinalSlotTests(unittest.TestCase):
    def test_actual_loop_dispatches_fixed_round_and_arm_ordinals_not_source_prefixes(self):
        fixture = loop_fixture.PopulationLoopTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        slots, original = [], fixture.forecast
        def forecast(version, company, slot):
            slots.append(str(slot))
            return original(version, company, slot)
        fixture.forecast = forecast
        result = fixture.run_loop(rounds=2)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual([Path(slot).name for slot in slots],
                         ['forecast-01-00', 'forecast-01-01', 'forecast-02-00', 'forecast-02-01'])
        fixture.run_loop(rounds=2)
        self.assertEqual(len(slots), 4)

    def test_actual_loop_carries_rejected_candidate_identity_into_next_packet(self):
        fixture = loop_fixture.PopulationLoopTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.reject_review = True
        result = fixture.run_loop(rounds=2)
        self.assertEqual(result['status'], 'completed')
        packet = fixture.calls['controller'][1]
        feedback = engine.read(packet['feedback'])
        reviewed = feedback['exploration_review']
        self.assertEqual(reviewed['candidate_id'], fixture.calls['review'][0]['id'])
        self.assertFalse(reviewed['accepted_for_exploration'])
        self.assertEqual(reviewed['evidence'], fixture.evidence)
        self.assertEqual(packet['population']['explorers'], [])


class PopulationPagedBrokerTests(unittest.TestCase):
    def setUp(self):
        self.fixture = native_fixture.PopulationCaseTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.case = self.fixture.prepare()
        self.broker = PopulationBroker(self.fixture.root/'paged-actions',
            versions={self.fixture.version['id']: self.fixture.version}, company=self.case['company'],
            capacity=self.case['capacity'], runner=Mock(), literature=Mock(), trace_slots={})

    def arguments(self, **changes):
        return dict(version_id=self.fixture.version['id'], axis='R', offset=0, characters=32, **changes)

    def test_references_are_small_and_exact_pages_are_hashed_without_host_execution(self):
        references = self.broker.references()
        self.assertNotIn('text', json.dumps(references))
        self.assertEqual(references[self.fixture.version['id']]['R']['sha256'], self.fixture.r['sha256'])
        first = self.broker.dispatch('read_population_program', self.arguments())['value']
        second_args = self.arguments(); second_args['offset'] = first['next_offset']
        second = self.broker.dispatch('read_population_program', second_args)['value']
        source = Path(self.fixture.r['path']).read_text()
        self.assertEqual(first['text'] + second['text'], source[:64])
        self.assertEqual(first['source_sha256'], self.fixture.r['sha256'])
        self.assertEqual(self.broker.calls, 2)
        self.assertFalse(self.fixture.marker.exists())

    def test_source_page_drift_and_invalid_identity_refuse_without_execution(self):
        Path(self.fixture.r['path']).write_text('changed source')
        with self.assertRaises(ValueError):
            self.broker.dispatch('read_population_program', self.arguments())
        self.assertTrue((self.broker.root/'0001'/'failure.json').is_file())
        self.assertFalse(self.fixture.marker.exists())

    def test_failed_source_page_stays_closed_to_identical_retry(self):
        arguments = self.arguments(); arguments['offset'] = 65536
        with self.assertRaises(ValueError):
            self.broker.dispatch('read_population_program', arguments)
        self.assertEqual(self.broker.calls, 1)
        with self.assertRaises(ValueError):
            self.broker.dispatch('read_population_program', arguments)
        self.assertEqual(self.broker.calls, 1)

    def test_unknown_version_or_oversized_page_rejected_before_action_claim(self):
        for changes in ({'version_id': 'f'*64}, {'characters': 4001}, {'offset': -1}):
            arguments = self.arguments(); arguments.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.broker.dispatch('read_population_program', arguments)
        self.assertEqual(self.broker.calls, 0)


if __name__ == '__main__':
    unittest.main()
