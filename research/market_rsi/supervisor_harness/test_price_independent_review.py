"""Independent review boundary fixtures; mock account, synthetic saved results.

Generated numeric smoke tests use a real pinned Python child on synthetic arrays.
No live account calls, resident Train reads, scientific fitting or performance.
"""
from copy import deepcopy
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import Mock, patch

from supervisor_harness import price_independent_review as review
from supervisor_harness import test_price_loop_services as fixtures

ZERO_SOURCE = """import numpy as np
def fit_predict(x, y, weights, xc, history, check_history, *, seed):
    return np.zeros(len(xc))
"""
ZERO_TEST = """import numpy as np
from candidate import fit_predict
def test_candidate():
    result = fit_predict(np.zeros((2, 13)), np.zeros(2), np.ones(2), np.zeros((3, 13)), [[], []], [[], [], []], seed=314159)
    assert result.shape == (3,)
    assert np.isfinite(result).all()
if __name__ == '__main__':
    test_candidate()
"""


class FitBudgetTests(TestCase):
    def test_one_explicit_fit_and_preprocessing_fit_transform_admitted(self):
        source = """def fit_predict(x):
    x = scaler.fit_transform(x)
    model = Forest(n_jobs=1)
    model.fit(x, y)
    return model.predict(x)
"""
        checks = review.fit_budget_checks(source)
        self.assertEqual(checks['explicit_model_fit_calls'], 1)
        self.assertFalse(checks['general_program_fit_bound_proven'])

    def test_multiple_fit_parallelism_loops_and_repeated_helpers_rejected(self):
        bad = ("model.fit(x,y)\nmodel.fit(x,y)", "model = Forest(n_jobs=-1)",
               "model = Forest(n_jobs=True)", "model = Forest(n_jobs=jobs)",
               "for x in xs:\n    model.fit(x,y)", "out = [model.fit(x,y) for x in xs]",
               "def helper():\n    model.fit(x,y)\nhelper()\nhelper()",
               "def helper():\n    model.fit(x,y)\nfor i in xs:\n    helper()")
        for source in bad:
            with self.subTest(source=source), self.assertRaises(ValueError): review.fit_budget_checks(source)


class IndependentReviewTests(TestCase):
    def setUp(self):
        self.s = fixtures.PriceServiceTests()
        self.addCleanup(self.s.doCleanups)
        self.s.setUp()
        self.runtime = self.s.runtime
        self.calls = []
        self.transport = Mock(side_effect=self.synthetic_role)
        role_grant = self.s.h.f.write('synthetic-review-grant', {'account_roles': {'max_input_bytes': 32768}})
        self.reviewer = review.IndependentPriceReviewer(self.runtime, self.transport, role_grant_binding=role_grant)

    def synthetic_role(self, role, packet, schema, **kwargs):
        self.calls.append((role, deepcopy(packet), kwargs))
        stage = packet['stage']
        valid = stage == 'result' and packet['material']['outcome'] == 'succeeded'
        response = {'schema': 'market_rsi_independent_price_verdict_v1',
            'input_sha256': schema['properties']['input_sha256']['const'], 'stage': stage, 'verdict': 'PASS',
            'finding': 'Synthetic review fixture; no actual scientific finding.',
            'evidence': ['Supplied synthetic artifact hash and independently re-scored synthetic forecasts.'],
            'research_credit': 2 if valid else 0,
            'research_outcome': 'refute' if valid else 'inconclusive' if stage == 'result' else 'not_applicable',
            'route_action': 'branch' if valid else 'stop' if stage == 'result' else 'not_applicable'}
        call_id = kwargs['operation_id']
        return {'response': response, 'call_id': call_id, 'usage': {'synthetic': True}, 'serving_snapshot': 'unknown',
            **{key + '_binding': self.s.h.f.write('review-role-' + stage + '-' + key,
                {'synthetic': True, 'role': role, 'call_id': call_id}) for key in ('input', 'response', 'process', 'completion')}}

    def input_material(self):
        ctx = {'round_index': 1, 'previous_result': self.s.seed}
        original = self.s.service().input(ctx)
        return {key: original[key] for key in ('input', 'authorization', 'configuration')}

    def source_material(self):
        h = self.s.h
        candidate = h.candidate.with_name('candidate.py'); candidate.write_text(ZERO_SOURCE)
        test = candidate.parent / 'test_candidate.py'; test.write_text(ZERO_TEST)
        response = h.response
        author_input = h.f.write('original-author-input', {'role': 'author', 'role_id': 'synthetic-author',
            'payload': {'original_controller_decision': response}})
        role = {'call_id': 'synthetic-author', 'input_binding': author_input,
            'response_binding': h.f.write('original-author-response', {'decision_sha256': review.t.c._digest(response),
                'candidate_id': response['candidate']['candidate_id'], 'candidate_source': ZERO_SOURCE,
                'test_source': ZERO_TEST, 'method_family': h.spec['method_family']}),
            **{key + '_binding': h.f.write('original-author-' + key, {'synthetic': True})
               for key in ('process', 'completion')}}
        author = {'schema': 'price_candidate_author_receipt_v1', 'original_decision_sha256': review.t.c._digest(response),
            'candidate_id': response['candidate']['candidate_id'], 'candidate': review.r.pin(candidate),
            'test': review.r.pin(test), 'generated_tests_executed': False, 'awaiting_independent_source_review': True,
            'role_call': role}
        receipt = candidate.parent / 'author_receipt.json'; review.w.save(receipt, author)
        h.spec.update(candidate_binding=review.r.pin(candidate), files={str(path.relative_to(h.repo)): review.w.sha(path)
            for path in (h.runner, candidate, test, receipt)}, python_binding={
            'launch_path': '/Users/estelle/Library/Application Support/MarketRSI/runtimes/ds-py312-20260912-01/bin/python',
            'binary': review.r.pin(Path('/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12'))})
        return h.prepare()

    def typed_input_material(self):
        material = self.input_material()
        packet = review.t.c._read(material['input'])
        identity = deepcopy(self.s.base['identity_configuration'])
        namespace = 'research/market_rsi/research_capacities/' + self.runtime.fixed_grant['batch_id'] + '/'
        identity['allowed_write_paths'] = {'researcher': [namespace + 'r1.py', namespace + 'r2.py'],
            'harness': [namespace + 'h1.py', namespace + 'h2.py']}
        context = {'schema': 'price_controller_action_context_v1', 'identity_configuration': identity,
            'available_actions': ['prediction', 'researcher', 'harness', 'request_closed_authority']}
        packet.update(schema='controller_price_feedback_input_v2', action_context=context)
        packet['source_context']['controller_action_context'] = deepcopy(context)
        packet['bindings']['source_context'] = self.s.h.f.write('typed-source-context', packet['source_context'])
        material['input'] = self.s.h.f.write('typed-controller-input', packet)
        return material

    def test_typed_input_review_binds_original_schema_scope_before_reservation(self):
        material = self.typed_input_material()
        binding = self.reviewer.review('input', material)
        packet = review.t.c._read(material['input'])
        receipt = review.t._review(packet, material['input'], self.runtime.authority, binding, self.runtime.repo,
            configuration_binding=self.runtime.configuration, config=self.runtime.config)
        self.assertEqual(receipt['action_context_sha256'], review.t.c._digest(packet['action_context']))
        self.assertEqual(receipt['decision_schema_sha256'], review.t.c._digest(review.t.SCHEMA_V2))
        self.assertEqual(self.calls[0][1]['material']['reviewed_decision_schema'], review.t.SCHEMA_V2)
        self.assertFalse(self.calls[0][1]['trusted_checks']['capacity_execution_authorized'])
        self.assertEqual(review.t._file(self.runtime.root / 'ledger.json')['attempts'], [])
        with self.assertRaises(FileExistsError): self.reviewer.review('input', material)
        self.assertEqual(len(self.calls), 1)

    def test_typed_unbound_scope_or_permission_drift_rejected_before_role(self):
        original = self.typed_input_material()
        for field in ('unbound', 'authority', 'resources', 'kernel', 'foreign_batch', 'protected', 'composite'):
            packet = deepcopy(review.t.c._read(original['input']))
            config = packet['action_context']['identity_configuration']
            if field == 'unbound': packet['action_context']['available_actions'] = ['prediction']
            elif field == 'authority': config['fixed_context']['authority_sha256'] = 'f' * 64
            elif field == 'resources': config['fixed_context']['resource_policy_sha256'] = 'f' * 64
            elif field == 'kernel': config['allowed_write_paths']['researcher'] = ['supervisor_harness/run_price_discovery.py']
            elif field == 'foreign_batch': config['allowed_write_paths']['researcher'] = ['research/market_rsi/research_capacities/OTHER/r2.py']
            elif field == 'protected': config['allowed_write_paths']['researcher'] = ['experiments/nfl_ingame_price_score.py']
            else: packet['action_context']['available_actions'] = ['composite']
            if field != 'unbound':
                packet['source_context']['controller_action_context'] = deepcopy(packet['action_context'])
                packet['bindings']['source_context'] = self.s.h.f.write('typed-bad-source-' + field, packet['source_context'])
            material = {**original, 'input': self.s.h.f.write('typed-bad-input-' + field, packet)}
            with self.subTest(field=field), self.assertRaises(ValueError): self.reviewer.review('input', material)
        self.assertEqual(len(self.calls), 0)

    def test_legacy_input_does_not_accept_capacity_context(self):
        material = self.typed_input_material()
        packet = review.t.c._read(material['input']); packet['schema'] = 'controller_price_feedback_input_v1'
        material['input'] = self.s.h.f.write('legacy-extra-capacity-context', packet)
        with self.assertRaises(ValueError): self.reviewer.review('input', material)
        self.assertEqual(len(self.calls), 0)

    def test_actual_callback_input_binds_separate_role_and_exact_operation(self):
        material = self.input_material()
        binding = self.reviewer.review('input', material)
        receipt = review.t.c._read(binding)
        self.assertTrue(receipt['passed'])
        self.assertEqual(receipt['input_sha256'], material['input']['sha256'])
        self.assertEqual(receipt['account_role'], 'input_review')
        self.assertEqual(self.calls[0][2]['operation_id'], receipt['original_account_call']['call_id'])
        self.assertEqual(review.t._review(review.t.c._read(material['input']), material['input'],
            self.runtime.authority, binding, self.runtime.repo, configuration_binding=self.runtime.configuration,
            config=self.runtime.config), receipt)
        with self.assertRaises(FileExistsError): self.reviewer.review('input', material)
        self.assertEqual(len(self.calls), 1)

    def test_larger_input_review_uses_distinct_bound_controller_and_role_limits(self):
        material = self.input_material()
        packet = review.t.c._read(material['input'])
        grant = deepcopy(self.runtime.fixed_grant)
        grant['account_transfer']['max_input_bytes'] = 262144
        self.runtime.authority = self.s.h.f.write('authorization', grant)
        self.runtime.fixed_grant = grant
        material['authorization'] = self.runtime.authority; packet['authority'] = grant
        packet['memory']['synthetic_extra_context'] = 'x' * 40000
        packet['bindings']['memory'] = self.s.h.f.write('large-review-memory', packet['memory'])
        material['input'] = self.s.h.f.write('large-review-input', packet)
        self.reviewer.grant = self.s.h.f.write('large-review-grant', {'account_roles': {'max_input_bytes': 262144}})
        self.reviewer.review('input', material)
        self.assertEqual(len(self.calls), 1)
        self.assertGreater(len(Path(material['input']['path']).read_bytes()), 32768)
        self.reviewer.grant = self.s.h.f.write('old-size-review-grant', {'account_roles': {'max_input_bytes': 32768}})
        with self.assertRaisesRegex(ValueError, 'input byte budget'): self.reviewer.review('input', material)
        self.assertEqual(len(self.calls), 1)

    def test_formal_native_contract_requires_actual_ack_before_account_review(self):
        from supervisor_harness import price_account_roles as roles
        grant = deepcopy(self.runtime.fixed_grant); grant['account_roles'] = {'approved': True}
        self.runtime.authority = self.s.h.f.write('authorization', grant)
        self.runtime.fixed_grant = grant
        material = self.input_material()
        with self.assertRaises(FileNotFoundError): self.reviewer.review('input', material)
        self.assertEqual(len(self.calls), 0)
        directory = self.runtime.root / 'account-runtime-preflight'; directory.mkdir()
        policy = {'contract': roles.transport_contract(), 'environment_acknowledged': True,
            'thread_start_result': {'thread': {'environments': []}, 'model': review.t.c.MODEL, 'instructionSources': []}}
        review.w.save(directory / 'runtime-policy.json', policy)
        proof = {'authorization': self.runtime.authority, 'transport_contract': roles.transport_contract(),
            'operational_ready': True, 'model_calls': 0, 'private_payload_transfer': False,
            'evidence': {str(directory / 'runtime-policy.json'): review.w.sha(directory / 'runtime-policy.json')}}
        review.w.save(self.runtime.root / 'account-runtime-preflight.json', proof)
        receipt = review.t.c._read(self.reviewer.review('input', material))
        self.assertEqual(receipt['controller_transport'], roles.transport_contract())
        self.assertTrue(self.calls[0][1]['trusted_checks']['actual_native_no_environment_preflight'])
        self.assertEqual(self.calls[0][1]['material']['runtime_policy']['path'], str(self.runtime.root / 'account-runtime-preflight.json'))

    def test_drift_bad_hash_extra_raw_evidence_fails_before_role(self):
        original = self.input_material()
        for field in ('authority', 'provided_parents', 'schema', 'bindings'):
            material = deepcopy(original)
            packet = review.t.c._read(material['input'])
            if field == 'authority': packet[field] = {}
            elif field == 'provided_parents': packet[field] = ['not-a-hash']
            elif field == 'schema': packet['evidence_session'] = {'raw': True}
            else: packet[field]['feedback']['sha256'] = 'f' * 64
            material['input'] = self.s.h.f.write('bad-' + field, packet)
            with self.subTest(field=field), self.assertRaises(ValueError): self.reviewer.review('input', material)
        self.assertEqual(len(self.calls), 0)

    def test_metadata_credit_bool_out_of_range_and_nonscientific_credit_rejected(self):
        original = self.synthetic_role
        prepared = self.input_material()
        for value in (True, 3, -1, 1.5, 1):
            def bad(*args, **kwargs):
                result = original(*args, **kwargs); result['response']['research_credit'] = value; return result
            self.transport.side_effect = bad
            material = deepcopy(prepared)
            packet = review.t.c._read(material['input']); packet['memory']['fixture_marker'] = str(value)
            mem = self.s.h.f.write('credit-memory-' + str(value), packet['memory'])
            packet['bindings']['memory'] = mem
            material['input'] = self.s.h.f.write('credit-input-' + str(value), packet)
            with self.subTest(value=value), self.assertRaises(ValueError): self.reviewer.review('input', material)

    def test_rejection_preserved_no_generated_test_or_resample(self):
        def rejected(*args, **kwargs):
            result = self.synthetic_role(*args, **kwargs); result['response']['verdict'] = 'REJECT'; return result
        self.transport.side_effect = rejected
        material = self.input_material()
        with self.assertRaises(RuntimeError): self.reviewer.review('input', material)
        receipt = review.t._file(next((self.runtime.root / 'independent-reviews').glob('*/review.json')))
        self.assertFalse(receipt['passed'])
        with self.assertRaises(FileExistsError): self.reviewer.review('input', material)
        self.assertEqual(len(self.calls), 1)

    def test_source_original_author_review_then_actual_synthetic_numeric_test(self):
        material = self.source_material()
        with patch.object(review.w, 'sample_rss', return_value=32):
            binding = self.reviewer.review('source', material)
        receipt = review.t.c._read(binding)
        smoke = review.t.c._read(receipt['generated_test_receipt'])
        self.assertEqual(smoke['exit_code'], 0)
        self.assertEqual(smoke['sampled_peak_rss_bytes'], 32768)
        self.assertTrue(smoke['synthetic_inputs_only'])
        self.assertEqual(self.calls[0][0], 'source_review')
        self.assertEqual(self.calls[0][1]['stage'], 'source')
        finalized = review.h.finalize(self.runtime, material, binding)
        self.assertEqual(finalized['review'], binding)

    def test_source_unsafe_code_request_or_author_drift_before_role(self):
        material = self.source_material()
        request = review.t.c._read(material['request']); request['max_fits'] = 5
        bad = self.s.h.f.write('source-bad-request', request)
        material['request'] = bad
        with self.assertRaises(ValueError): self.reviewer.review('source', material)
        self.assertEqual(len(self.calls), 0)

    def test_generated_test_drift_after_review_never_executes(self):
        material = self.source_material()
        spec = review.t.c._read(material['specification'])
        test = Path(spec['candidate_binding']['path']).parent / 'test_candidate.py'
        def mutate(*args, **kwargs):
            result = self.synthetic_role(*args, **kwargs)
            test.write_text(ZERO_TEST + '\n# changed after reviewed packet\n')
            return result
        self.transport.side_effect = mutate
        with patch.object(review.subprocess, 'Popen') as launch, self.assertRaisesRegex(ValueError, 'test drift'):
            self.reviewer.review('source', material)
        self.assertFalse(launch.called)
        self.assertEqual(len(self.calls), 1)

    def test_result_frozen_scorer_independent_rerun_no_raw_forecast_transfer(self):
        self.s.run_service(1)
        material = next(data for stage, data in self.s.reviews if stage == 'result')
        binding = self.reviewer.review('result', material)
        receipt = review.t.c._read(binding)
        self.assertEqual(receipt['research_credit'], 2)
        packet = self.calls[0][1]
        self.assertTrue(packet['trusted_checks']['independent_local_scorer_rerun'])
        self.assertNotIn('predictions', packet['material'])
        self.assertNotIn('per_game', packet['material']['metrics'])
        self.assertEqual(packet['material']['metrics']['decision'], 'REVERT')

    def test_result_drift_fails_before_review_call(self):
        self.s.run_service(1)
        material = next(data for stage, data in self.s.reviews if stage == 'result')
        card = review.t.c._read(material['comparison']); card['decision'] = 'KEEP'
        material['comparison'] = self.s.h.f.write('wrong-comparison', card)
        with self.assertRaises(ValueError): self.reviewer.review('result', material)
        self.assertEqual(len(self.calls), 0)

    def test_failed_execution_preserved_not_scientific_credit(self):
        self.s.fail_first_child = True; self.s.run_service(1)
        material = next(data for stage, data in self.s.reviews if stage == 'result')
        receipt = review.t.c._read(self.reviewer.review('result', material))
        self.assertEqual(receipt['research_credit'], 0)
        self.assertIsNone(receipt['comparison'])
        self.assertTrue(self.calls[0][1]['trusted_checks']['failed_execution_has_no_score'])


if __name__ == '__main__': main()
