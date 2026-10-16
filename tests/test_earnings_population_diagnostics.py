"""Independent label-free diagnostics; synthetic preserved execution originals.

Real researcher.verify/execution_value replays synthetic Docker-format receipts.
No candidate Python is evaluated, no Docker/API/scorer/real ledger is used.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from edgar_forecast_tools import FilingTools
from edgar_forecast_openai import final_request
import earnings_open_researcher as researcher
import earnings_population_diagnostics as diagnostics
from earnings_research_state import ResearchState
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_open_researcher as receipt_fixture
import test_earnings_population_case as public_fixture


TARGETS = [f'T{i:03d}' for i in range(1, 6)]
SOURCE_SHA = 'a'*64
EXECUTION_SHA = 'b'*64
KEYS = {'schema', 'source_sha256', 'execution_sha256', 'program_reported_coverage',
        'output_evidence_items', 'reported_target_completion', 'diagnostic_flags', 'limitation'}
COUNTERS = ('accepted_reads', 'requested_reads', 'failed_reads', 'extracted_cells',
            'omitted_cells', 'records', 'facts', 'calculations', 'assumptions',
            'observations', 'omitted_items')


class DiagnosticProjectionTests(unittest.TestCase):
    def project(self, value, **changes):
        options = dict(source_sha256=SOURCE_SHA, execution_sha256=EXECUTION_SHA, target_ids=TARGETS)
        options.update(changes)
        return diagnostics.project(value, **options)

    def test_exact_bounded_output_and_explicit_self_report_limit(self):
        result = self.project({})
        self.assertEqual(set(result), KEYS)
        self.assertEqual(result['schema'], 'earnings_population_research_diagnostics_v1')
        self.assertEqual(result['source_sha256'], SOURCE_SHA)
        self.assertEqual(result['execution_sha256'], EXECUTION_SHA)
        self.assertEqual(result['program_reported_coverage'], {})
        self.assertIsNone(result['output_evidence_items'])
        self.assertEqual([row['target_id'] for row in result['reported_target_completion']], TARGETS)
        self.assertTrue(all(row['status'] == 'unreported' for row in result['reported_target_completion']))
        self.assertTrue(all(row['missing_fields_count'] is None for row in result['reported_target_completion']))
        self.assertIsInstance(result['limitation'], str)
        self.assertIn('report', result['limitation'].lower())
        self.assertIn('correct', result['limitation'].lower())
        self.assertLess(len(json.dumps(result)), 8192)

    def test_reported_coverage_accepts_only_declared_nonnegative_integer_counters(self):
        value = {'coverage': {name: index for index, name in enumerate(COUNTERS)}}
        result = self.project(value)
        self.assertEqual(result['program_reported_coverage'], value['coverage'])
        result = self.project({'coverage': {'extracted_cells': 1_000_000_000}})
        self.assertEqual(result['program_reported_coverage']['extracted_cells'], 1_000_000_000)

    def test_malformed_or_financial_coverage_never_becomes_valid_counter(self):
        for value in (True, False, -1, 1.5, '104', None, float('nan'), float('inf'),
                      1_000_000_001, {'actual_value': 'PRIVATE_ACTUAL'}):
            with self.subTest(value=repr(value)):
                result = self.project({'coverage': {'extracted_cells': value, 'accepted_reads': 2,
                                                    'actual_eps': 'PRIVATE_ACTUAL'}})
                self.assertNotIn('extracted_cells', result['program_reported_coverage'])
                self.assertEqual(result['program_reported_coverage'].get('accepted_reads'), 2)
                self.assertNotIn('PRIVATE_ACTUAL', json.dumps(result))
                self.assertNotIn('actual_eps', json.dumps(result))

    def test_missing_or_unusual_algorithm_output_is_not_rejected(self):
        for value in (None, 0, False, 'Unrelated algorithm result PRIVATE_VALUE', [],
                      [{'metric': 123}], {'custom_algorithm': {'arbitrary': 123}},
                      {'coverage': []}, {'coverage': 'PRIVATE_VALUE'}, {'targets': 'PRIVATE_VALUE'}):
            with self.subTest(kind=type(value).__name__):
                result = self.project(value)
                self.assertEqual(set(result), KEYS)
                self.assertTrue(all(row['status'] == 'unreported' for row in result['reported_target_completion']))
                self.assertNotIn('PRIVATE_VALUE', json.dumps(result))

    def test_evidence_and_missing_fields_are_counted_without_copying_contents(self):
        value = {'evidence': [{'quote': 'PRIVATE_QUOTE', 'value': 987654321}], 'targets': [
            {'target_id': 'T001', 'status': 'incomplete', 'missing': ['PRIVATE_FIELD_1', 'PRIVATE_FIELD_2']}]}
        result = self.project(value)
        self.assertEqual(result['output_evidence_items'], 1)
        self.assertEqual(result['reported_target_completion'][0],
                         {'target_id': 'T001', 'status': 'incomplete', 'missing_fields_count': 2})
        self.assertNotIn('PRIVATE_', json.dumps(result))
        self.assertNotIn('987654321', json.dumps(result))

    def test_nonlist_evidence_is_unavailable_not_an_asserted_zero(self):
        for evidence in (None, {}, 100, 'PRIVATE_QUOTE'):
            with self.subTest(evidence=repr(evidence)):
                self.assertIsNone(self.project({'evidence': evidence})['output_evidence_items'])
        self.assertEqual(self.project({'evidence': []})['output_evidence_items'], 0)

    def test_target_reports_follow_declared_question_order_without_inference(self):
        rows = [{'target_id': target, 'status': 'complete', 'missing': []} for target in reversed(TARGETS)]
        result = self.project({'targets': rows})
        self.assertEqual(result['reported_target_completion'],
                         [{'target_id': target, 'status': 'complete', 'missing_fields_count': 0} for target in TARGETS])

    def test_absent_target_reports_are_unreported_not_complete(self):
        result = self.project({'targets': [{'target_id': 'T001', 'status': 'complete', 'missing': []}]})
        self.assertEqual(result['reported_target_completion'][0]['status'], 'complete')
        self.assertTrue(all(row['status'] == 'unreported' for row in result['reported_target_completion'][1:]))

    def test_duplicate_target_identity_cannot_sneak_completeness(self):
        for rows in ([{'target_id': 'T001', 'status': 'complete', 'missing': []}]*2,
                     [{'target_id': 'T001', 'status': 'incomplete', 'missing': ['x']},
                      {'target_id': 'T001', 'status': 'complete', 'missing': []}]):
            with self.subTest(rows=rows):
                first = self.project({'targets': rows})['reported_target_completion'][0]
                self.assertEqual(first['status'], 'unreported')
                self.assertIsNone(first['missing_fields_count'])

    def test_unknown_target_identity_or_arbitrary_status_not_projected(self):
        value = {'targets': [{'target_id': 'T999', 'status': 'complete', 'missing': []},
                             {'target_id': 'PRIVATE_TARGET', 'status': 'PRIVATE_STATUS'},
                             {'target_id': 'T001', 'status': 'PRIVATE_STATUS', 'missing': 'PRIVATE_MISSING'}]}
        result = self.project(value)
        self.assertTrue(all(row['status'] == 'unreported' for row in result['reported_target_completion']))
        self.assertNotIn('PRIVATE_', json.dumps(result))
        self.assertNotIn('T999', json.dumps(result))

    def test_malformed_target_rows_do_not_reject_other_valid_report(self):
        rows = [None, [], 'PRIVATE_ROW', {'target_id': ['T001'], 'status': 'complete'},
                {'target_id': 'T002', 'status': 'incomplete', 'missing': []}]
        result = self.project({'targets': rows})
        self.assertEqual(result['reported_target_completion'][1]['status'], 'incomplete')
        self.assertNotIn('PRIVATE_ROW', json.dumps(result))

    def test_malformed_missing_field_is_unavailable_without_copying_text(self):
        result = self.project({'targets': [{'target_id': 'T001', 'status': 'incomplete', 'missing': 'PRIVATE_STRING'}]})
        self.assertIsNone(result['reported_target_completion'][0]['missing_fields_count'])
        self.assertNotIn('PRIVATE_STRING', json.dumps(result))

    def test_arbitrary_free_text_quotes_predictions_and_financial_values_never_project(self):
        value = {'coverage': {'extracted_cells': 0}, 'evidence': [{'financial_value': 987654321}],
                 'prediction': 987654321, 'quote': 'PRIVATE_QUOTE', 'rationale': 'PRIVATE_RATIONALE',
                 'advice': 'PRIVATE_ADVICE', 'actual_value': 'PRIVATE_LABEL',
                 'targets': [{'target_id': 'T001', 'status': 'incomplete', 'missing': ['PRIVATE_FIELD'],
                              'prediction': 987654321, 'quote': 'PRIVATE_QUOTE'}]}
        serialized = json.dumps(self.project(value))
        self.assertNotIn('PRIVATE_', serialized)
        self.assertNotIn('987654321', serialized)

    def test_projection_does_not_mutate_value_or_declared_target_ids(self):
        value = {'coverage': {'extracted_cells': 0}, 'targets': [
            {'target_id': 'T001', 'status': 'incomplete', 'missing': ['x']}], 'evidence': []}
        before, target_before = deepcopy(value), list(TARGETS)
        self.project(value)
        self.assertEqual(value, before)
        self.assertEqual(TARGETS, target_before)

    def test_invalid_source_or_execution_identity_rejected(self):
        for name in ('source_sha256', 'execution_sha256'):
            for value in (None, 1, 'x'*64, 'A'*64, 'a'*63, 'a'*65):
                with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                    self.project({}, **{name: value})

    def test_exact_five_unique_declared_question_ids_required(self):
        for ids in ([], TARGETS[:4], TARGETS+['T006'], ['T001']*5,
                    ['T001', 'T002', 'T003', 'T004', 'PRIVATE_TARGET'], [1, 2, 3, 4, 5]):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                self.project({}, target_ids=ids)

    def test_diagnostic_flags_are_fixed_bounded_labels_not_candidate_text(self):
        allowed = {'output_not_object', 'coverage_unreported', 'invalid_coverage_counter',
                   'evidence_count_unreported', 'target_completion_unreported',
                   'unrecognized_target_report', 'duplicate_target_report', 'invalid_target_status'}
        value = {'coverage': {'extracted_cells': 'PRIVATE_COUNTER'}, 'targets': [
            {'target_id': 'T001', 'status': 'PRIVATE_STATUS'},
            {'target_id': 'T001', 'status': 'complete'}, {'target_id': 'PRIVATE_TARGET'}]}
        result = self.project(value)
        self.assertIsInstance(result['diagnostic_flags'], list)
        self.assertTrue(set(result['diagnostic_flags']) <= allowed)
        self.assertEqual(len(result['diagnostic_flags']), len(set(result['diagnostic_flags'])))
        self.assertNotIn('PRIVATE_', json.dumps(result))


class DiagnosticExecutionVerificationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = public_fixture.PopulationCaseTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.company = self.fixture.resident['company']
        self.tools = FilingTools(self.company)
        self.payload = {'stage': 'forecast', 'questions': self.tools.files['questions.md'],
                        'filing_index': self.tools.files['filing_index.tsv'], 'records': []}
        self.source = Path(self.fixture.r['path']).read_text()
        self.runners = []
        self.trials = {}

    def runner(self, outputs):
        runner = receipt_fixture.ScriptedReceiptRunner(self.fixture.root/f'runner-{len(self.runners)}', outputs)
        self.runners.append(runner)
        return runner

    def value(self):
        return {'coverage': {'extracted_cells': 0, 'accepted_reads': 1}, 'evidence': [],
                'targets': [{'target_id': target, 'status': 'incomplete', 'missing': ['metric', 'period']}
                            for target in TARGETS], 'financial_value': 'PRIVATE_VALUE'}

    def test_real_original_verifier_replays_synthetic_receipts_without_running_candidate(self):
        value = self.value()
        runner = self.runner([value])
        execution = runner.run(self.source, self.payload)
        result = diagnostics.verify_execution(execution, self.source, self.payload, self.company)
        self.assertEqual(result['source_sha256'], hashlib.sha256(self.source.encode()).hexdigest())
        self.assertEqual(result['execution_sha256'], execution['receipt']['sha256'])
        self.assertEqual(result['program_reported_coverage']['extracted_cells'], 0)
        self.assertTrue(all(row['status'] == 'incomplete' for row in result['reported_target_completion']))
        self.assertEqual(runner.calls, 1)
        self.assertFalse(self.fixture.marker.exists())
        self.assertNotIn('PRIVATE_', json.dumps(result))

    def test_tampered_projected_value_is_refused_against_original_stdout(self):
        runner = self.runner([self.value()])
        execution = runner.run(self.source, self.payload)
        execution['value']['coverage']['extracted_cells'] = 104
        with self.assertRaises(ValueError):
            diagnostics.verify_execution(execution, self.source, self.payload, self.company)
        self.assertEqual(runner.calls, 1)

    def test_changed_source_payload_or_original_bytes_refused(self):
        for index, kind in enumerate(('source', 'payload', 'stdout')):
            runner = self.runner([self.value()])
            execution = runner.run(self.source, self.payload)
            source, payload = self.source, deepcopy(self.payload)
            if kind == 'source': source += '\n# source drift\n'
            elif kind == 'payload': payload['records'] = [{'unverified': True}]
            else: (Path(execution['receipt']['path']).parent/'stdout.bin').write_bytes(b'changed stdout')
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                diagnostics.verify_execution(execution, source, payload, self.company)
            self.assertEqual(runner.calls, 1)

    def test_failed_cleanup_receipt_refused_not_projected_as_success(self):
        runner = self.runner([self.value()])
        execution = runner.run(self.source, self.payload)
        old = engine.read(execution['receipt'])
        execution['receipt'] = engine.save(Path(execution['receipt']['path']).parent/'bad-result.json',
                                           dict(old, cleanup_verified=False))
        with self.assertRaises(ValueError):
            diagnostics.verify_execution(execution, self.source, self.payload, self.company)

    def test_two_phase_original_evidence_is_reverified_without_new_runner_calls(self):
        request = {'research_requests': [{'tool': 'calculate', 'arguments': {'expression': '1+2'}}]}
        runner = self.runner([request, self.value()])
        execution = researcher.run(runner, self.source, self.payload, self.tools)
        before = deepcopy(execution)
        result = diagnostics.verify_execution(execution, self.source, self.payload, self.company)
        self.assertEqual(execution, before)
        self.assertEqual(runner.calls, 2)
        self.assertEqual(result['program_reported_coverage']['extracted_cells'], 0)
        execution['research_observations'][0]['output']['value'] = 999
        with self.assertRaises(ValueError):
            diagnostics.verify_execution(execution, self.source, self.payload, self.company)

    def test_unfulfilled_evidence_request_not_reported_as_completed_analysis(self):
        request = {'research_requests': [{'tool': 'calculate', 'arguments': {'expression': '1+2'}}]}
        runner = self.runner([request])
        execution = runner.run(self.source, self.payload)
        with self.assertRaises(ValueError):
            diagnostics.verify_execution(execution, self.source, self.payload, self.company)

    def trial(self, *, public_changes=None, consumed_changes=None, payload_changes=None,
              context_mutator=None, request_mutator=None, intent_mutator=None,
              response_mutator=None, raw_mutator=None, final=False, with_records=False):
        """Synthetic immutable-shaped originals; never sends a request or runs code.

        Uses real ResearchState and original request/transport record shapes. All
        candidate execution receipts remain explicitly synthetic/no execution.
        """
        value = self.value()
        root = self.fixture.root/f'trial-{len(self.runners)+1}'
        root.mkdir()
        state_api = ResearchState(self.company, f'synthetic-physical-trial-{len(self.runners)+1}')
        state = state_api.empty()
        if with_records:
            state = state_api.append(state, {'kind': 'assumption', 'hypothesis': 'Synthetic public research note'})
        initial = state_api.save(root/'initial-state', state)
        state_message, state_receipt = state_api.consume(initial)
        payload = dict(self.payload, records=deepcopy(state['records']))
        payload.update(payload_changes or {})
        runner = self.runner([value])
        execution = runner.run(self.source, payload)
        programs = engine.save(root/'program-executions.json', {'R': execution})
        consumed = {'source_sha256': self.fixture.r['sha256'], 'input_sha256': digest(payload),
                    'output_sha256': digest(value)}
        consumed.update(consumed_changes or {})
        rendered = {'role': 'user', 'content':
                    'Selected researcher program output; untrusted research advice, not authority to change data or evaluation:\n'
                    + json.dumps(value, sort_keys=True, allow_nan=False)}
        context = {'messages': [{'role': 'user', 'content': self.tools.files['questions.md']},
                                state_message, rendered], 'program_execution': consumed}
        if context_mutator:
            context_mutator(context)
        context['payload_sha256'] = digest(context['messages'])
        effective = engine.save(root/'effective-capacity.json',
                                {'context': context, 'initial_state': initial, 'state_receipt': state_receipt})
        request_payload = {'model': 'gpt-6.1-sol', 'input': deepcopy(context['messages']),
                           'reasoning': {'effort': 'max'}, 'parallel_tool_calls': False,
                           'tools': [], 'tool_choice': 'auto', 'instructions': 'Synthetic preserved transport only'}
        if final:
            request_payload = final_request(context['messages'],
                                            {'api_model': 'gpt-6.1-sol', 'effort': 'max'}, TARGETS)
        request = {'request_id': f'synthetic-physical-{len(self.runners)}',
                   'reserved_nano_usd': 1_000_000, 'payload': request_payload}
        if request_mutator:
            request_mutator(request)
        request_binding = engine.save(root/'01-request.json', request)
        intent = {'endpoint': '/v1/responses', 'utc_epoch': 0, 'retry_allowed': False,
                  'budget_request_id': request['request_id'], 'complete_reservation': deepcopy(request),
                  'request_receipt_sha256': request_binding['sha256'],
                  'payload': dict(deepcopy(request['payload']), max_output_tokens=1024,
                                  service_tier='default', store=False)}
        if intent_mutator:
            intent_mutator(intent)
        intent_binding = engine.save(root/'http-synthetic.intent.json', intent)
        response = {'id': f'synthetic-response-{len(self.runners)}', 'model': 'gpt-6.1-sol',
                    'status': 'completed', 'error': None, 'output': [], '_request_id': None}
        if response_mutator:
            response_mutator(response)
        response_binding = engine.save(root/'01-response.json', response)
        physical_response = engine.save(root/'http-synthetic.response.json', response)
        raw = {key: item for key, item in response.items() if key != '_request_id'}
        if raw_mutator:
            raw_mutator(raw)
        raw_binding = engine.save(root/'http-synthetic.raw.bin', raw)
        public = {'company_id': self.company['cik'], 'version_id': self.fixture.version['id'],
                  'pool_sources': {axis: self.fixture.version[axis]['sha256'] for axis in ('R', 'H')},
                  'effective_input': effective}
        public.update(public_changes or {})
        self.trials[programs['path']] = dict(root=root, evidence=[programs, effective, request_binding, response_binding],
                                           effective=effective, request=request_binding, response=response_binding,
                                           intent=intent_binding, physical_response=physical_response, raw=raw_binding)
        return engine.save(root/'population-public-feedback.json', public), programs, runner

    def evidence(self, programs):
        return self.trials[programs['path']]['evidence']

    def test_trial_join_uses_verified_original_execution_and_consumed_output(self):
        public, programs, runner = self.trial()
        originals_before = Path(public['path']).read_bytes(), Path(programs['path']).read_bytes()
        result = diagnostics.from_trial(public, self.evidence(programs), self.fixture.version, self.company)
        self.assertEqual(result['program_reported_coverage']['extracted_cells'], 0)
        self.assertEqual(len(result['reported_target_completion']), 5)
        self.assertTrue(all(row['status'] == 'incomplete' for row in result['reported_target_completion']))
        self.assertEqual(runner.calls, 1)
        self.assertEqual((Path(public['path']).read_bytes(), Path(programs['path']).read_bytes()), originals_before)

    def test_trial_company_version_source_or_consumption_drift_rejected(self):
        for changes in ({'company_id': 'CIK9999999999'}, {'version_id': 'f'*64},
                        {'pool_sources': {'R': 'f'*64, 'H': self.fixture.h['sha256']}}):
            public, programs, runner = self.trial(public_changes=changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                diagnostics.from_trial(public, self.evidence(programs), self.fixture.version, self.company)
        for field in ('source_sha256', 'input_sha256', 'output_sha256'):
            public, programs, runner = self.trial(consumed_changes={field: 'f'*64})
            with self.subTest(field=field), self.assertRaises(ValueError):
                diagnostics.from_trial(public, self.evidence(programs), self.fixture.version, self.company)

    def test_trial_requires_one_original_program_receipt_at_exact_trial_slot(self):
        public, programs, runner = self.trial()
        rest = self.evidence(programs)[1:]
        for evidence in (rest, [programs, programs, *rest]):
            with self.subTest(count=len(evidence)), self.assertRaises(ValueError):
                diagnostics.from_trial(public, evidence, self.fixture.version, self.company)
        other = engine.save(self.fixture.root/'program-executions.json', engine.read(programs))
        with self.assertRaises(ValueError):
            diagnostics.from_trial(public, [other, *rest], self.fixture.version, self.company)

    def test_physical_original_join_accepts_final_request_and_original_nonempty_state(self):
        for final, with_records in ((True, False), (False, True)):
            public, programs, runner = self.trial(final=final, with_records=with_records)
            records = self.trials[programs['path']]
            before = {str(path): path.read_bytes() for path in records['root'].rglob('*') if path.is_file()}
            with self.subTest(final=final, with_records=with_records):
                result = diagnostics.from_trial(public, self.evidence(programs), self.fixture.version, self.company)
                self.assertEqual(result['program_reported_coverage']['extracted_cells'], 0)
                self.assertEqual(runner.calls, 1)
                self.assertFalse(self.fixture.marker.exists())
                self.assertEqual(before, {str(path): path.read_bytes() for path in records['root'].rglob('*') if path.is_file()})

    def test_exact_original_effective_request_and_response_bindings_required(self):
        for missing in ('effective', 'request', 'response'):
            public, programs, _ = self.trial()
            selected = self.trials[programs['path']][missing]
            evidence = [binding for binding in self.evidence(programs) if binding != selected]
            with self.subTest(missing=missing), self.assertRaises(ValueError):
                diagnostics.from_trial(public, evidence, self.fixture.version, self.company)
        for duplicate in ('effective', 'request', 'response'):
            public, programs, _ = self.trial()
            evidence = [*self.evidence(programs), self.trials[programs['path']][duplicate]]
            with self.subTest(duplicate=duplicate), self.assertRaises(ValueError):
                diagnostics.from_trial(public, evidence, self.fixture.version, self.company)

    def test_unrelated_or_missing_physical_intent_cannot_prove_consumption(self):
        mutations = [lambda value: value.update(endpoint='/v1/responses/input_tokens'),
                     lambda value: value.update(budget_request_id='other-attempt')]
        for mutate in mutations:
            public, programs, _ = self.trial(intent_mutator=mutate)
            with self.subTest(mutation=repr(mutate)), self.assertRaises(ValueError):
                diagnostics.from_trial(public, self.evidence(programs), self.fixture.version, self.company)
        public, programs, _ = self.trial()
        path = Path(self.trials[programs['path']]['intent']['path'])
        path.rename(path.with_name('preserved-not-a-generation.json'))
        with self.assertRaises(ValueError):
            diagnostics.from_trial(public, self.evidence(programs), self.fixture.version, self.company)

    def test_duplicated_matching_physical_attempt_is_refused_not_silently_selected(self):
        public, programs, _ = self.trial()
        records = self.trials[programs['path']]
        engine.save(records['root']/'http-duplicate.intent.json', engine.read(records['intent']))
        with self.assertRaises(ValueError):
            diagnostics.from_trial(public, self.evidence(programs), self.fixture.version, self.company)

    def test_physical_request_identity_reservation_and_payload_must_match(self):
        mutations = {
            'reservation': lambda value: value['complete_reservation'].update(reserved_nano_usd=2_000_000),
            'request_sha': lambda value: value.update(request_receipt_sha256='f'*64),
            'retry': lambda value: value.update(retry_allowed=True),
            'max_tokens': lambda value: value['payload'].update(max_output_tokens=0),
            'store': lambda value: value['payload'].update(store=True),
            'tier': lambda value: value['payload'].update(service_tier='flex'),
            'actual_input': lambda value: value['payload']['input'].append({'role': 'user', 'content': 'Drift'}),
            'extra_field': lambda value: value['payload'].update(unreserved_transport_setting=True),
        }
        for kind, mutate in mutations.items():
            public, programs, _ = self.trial(intent_mutator=mutate)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                diagnostics.from_trial(public, self.evidence(programs), self.fixture.version, self.company)

    def test_reserved_actual_request_cannot_drop_verified_context_or_change_model(self):
        mutations = {
            'input': lambda value: value['payload'].update(input=[]),
            'model': lambda value: value['payload'].update(model='different-fixed-model'),
            'reservation': lambda value: value.update(reserved_nano_usd=0),
            'request_id': lambda value: value.update(request_id=''),
        }
        for kind, mutate in mutations.items():
            public, programs, _ = self.trial(request_mutator=mutate)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                diagnostics.from_trial(public, self.evidence(programs), self.fixture.version, self.company)

    def test_rendered_researcher_output_is_exact_and_once_in_physical_messages(self):
        mutations = {
            'missing': lambda value: value['messages'].pop(),
            'changed': lambda value: value['messages'][-1].update(content='Metadata said consumed; actual output missing'),
            'duplicate': lambda value: value['messages'].append(deepcopy(value['messages'][-1])),
            'wrong_role': lambda value: value['messages'][-1].update(role='assistant'),
            'initial_state_missing': lambda value: value['messages'].pop(1),
        }
        for kind, mutate in mutations.items():
            public, programs, _ = self.trial(context_mutator=mutate)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                diagnostics.from_trial(public, self.evidence(programs), self.fixture.version, self.company)

    def test_self_consistent_execution_cannot_replace_original_questions_index_or_records(self):
        changes = ({'stage': 'controller'}, {'questions': self.payload['questions']+'\nExtra target'},
                   {'filing_index': self.payload['filing_index']+'\nUnprovided filing'},
                   {'records': [{'unverified': 'Injected record'}]})
        for change in changes:
            public, programs, runner = self.trial(payload_changes=change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                diagnostics.from_trial(public, self.evidence(programs), self.fixture.version, self.company)
            self.assertEqual(runner.calls, 1)
        # Emptying a valid nonempty original state is also input drift.
        public, programs, _ = self.trial(with_records=True, payload_changes={'records': []})
        with self.assertRaises(ValueError):
            diagnostics.from_trial(public, self.evidence(programs), self.fixture.version, self.company)

    def test_physical_raw_response_must_match_saved_completed_response(self):
        public, programs, _ = self.trial(raw_mutator=lambda value: value.update(output=[{'changed': True}]))
        with self.assertRaises(ValueError):
            diagnostics.from_trial(public, self.evidence(programs), self.fixture.version, self.company)
        for field, value in (('status', 'incomplete'), ('error', {'message': 'Synthetic failure'}),
                             ('model', 'wrong-model')):
            public, programs, _ = self.trial(response_mutator=lambda response: response.update({field: value}))
            with self.subTest(field=field), self.assertRaises(ValueError):
                diagnostics.from_trial(public, self.evidence(programs), self.fixture.version, self.company)
        for missing in ('physical_response', 'raw'):
            public, programs, _ = self.trial()
            path = Path(self.trials[programs['path']][missing]['path'])
            path.rename(path.with_name(path.name+'.preserved'))
            with self.subTest(missing=missing), self.assertRaises((ValueError, FileNotFoundError)):
                diagnostics.from_trial(public, self.evidence(programs), self.fixture.version, self.company)


if __name__ == '__main__':
    unittest.main()
