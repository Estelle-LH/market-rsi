"""Independent public-only prediction provenance adversaries.

Real original researcher/diagnostic/physical verification replays synthetic
Docker-shaped originals. ScriptedReceiptRunner only writes receipts: no candidate
Python, API, real ledger, scorer/QA, heldout body or historical replay runs here.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import earnings_population_broker as broker
import earnings_population_campaign_context as contexts
import earnings_population_public_predictions as public_api
from edgar_forecast_tools import FilingTools
from edgar_forecast_openai import final_request
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_population_diagnostics as receipt_fixtures

TARGETS = receipt_fixtures.TARGETS


class PublicPredictionAdversarial(unittest.TestCase):
    def setUp(self):
        self.h = receipt_fixtures.DiagnosticExecutionVerificationTests('runTest')
        self.h.setUp(); self.addCleanup(self.h.doCleanups)
        # New public policy is DEV-only; replace the old fixture's fictional CIK
        # with a synthetic Capital resident, not the production Capital data.
        self.resident = self.h.fixture.company('CIK0000017313')
        self.h.company = self.resident['company']
        self.h.tools = FilingTools(self.h.company)
        self.h.payload = {'stage': 'forecast', 'questions': self.h.tools.files['questions.md'],
                          'filing_index': self.h.tools.files['filing_index.tsv'], 'records': []}
        self.version, self.company = self.h.fixture.version, self.h.company
        self.advice = {'coverage': {'extracted_cells': 0}, 'evidence': [],
            'targets': [{'target_id': target, 'status': 'complete', 'missing': [],
                         'predicted_value': value} for target, value in zip(TARGETS, [10, 20, 33, 40, 334.1])],
            'nested': {'T002': {'predicted_value': 999999}},
            'actual_value': 'SYNTHETIC_PRIVATE_GOLD_MUST_NOT_PROJECT'}
        self.advice['targets'][1].update(status='incomplete', predicted_value=888888)
        self.predictions = {'predictions': [{'target_id': t, 'predicted_value': v}
                            for t, v in zip(TARGETS, [10, 20, 30, 40, 310])]}
        self.h.value = lambda: deepcopy(self.advice)
        for seam in (patch('earnings_population_tasks.resident', return_value=deepcopy(self.resident)),
                     patch.object(public_api, 'company', return_value=deepcopy(self.company))):
            seam.start(); self.addCleanup(seam.stop)

    def rewrite(self, bound, value):
        path = Path(bound['path']); path.write_text(json.dumps(value, sort_keys=True))
        return engine.pin(path)

    def fixture(self, *, predictions=None):
        predictions = deepcopy(self.predictions if predictions is None else predictions)
        def response(value):
            value['output'] = [
                {'type': 'reasoning', 'encrypted_content': 'SYNTHETIC_PRIVATE_REASONING_MUST_NOT_PROJECT'},
                {'type': 'message', 'role': 'assistant', 'status': 'completed',
                 'content': [{'type': 'output_text', 'text': json.dumps(predictions)}]}]
        public, programs, runner = self.h.trial(final=True, response_mutator=response)
        record = self.h.trials[programs['path']]
        root = record['root']
        submitted = engine.save(root/'predictions.json', predictions)
        result = engine.save(root/'result.json', dict(status='COMPLETED_SCORED', turns=1,
            planned_targets=5, scored_targets=5, points=3))
        value = engine.read(public)
        value.update(schema='earnings_population_public_trial_v1', points=3,
            target_scores=[{'target_id': t, 'points_awarded': p}
                           for t, p in zip(TARGETS, [1, 0, .5, 1, .5])])
        public = self.rewrite(public, value)
        evidence = [public, *self.h.evidence(programs), submitted, result,
                    record['intent'], record['physical_response'], record['raw']]
        return dict(public=public, programs=programs, runner=runner, record=record,
                    predictions=submitted, result=result, evidence=evidence)

    def project(self, f, **kwargs):
        return public_api.project(kwargs.get('public', f['public']), kwargs.get('evidence', f['evidence']),
                                  kwargs.get('version', self.version), kwargs.get('company', self.company))

    def rows(self, comparison):
        return {r['target_id']: r for r in comparison['targets']}

    def feedback(self, f):
        return engine.save(f['record']['root']/'feedback.json', {
            'schema': 'earnings_population_feedback_v1', 'company_id': self.company['cik'],
            'round_index': 1, 'stable_id': self.version['id'], 'scope': 'Synthetic DEV observation only',
            'results': [{'version_id': self.version['id'], 'points': 3, 'evidence': f['evidence']}]})

    def test_real_receipt_projection_preserves_final_vs_advice_and_public_awards(self):
        f = self.fixture(); before = {str(p): p.read_bytes() for p in f['record']['root'].rglob('*') if p.is_file()}
        diagnostics, comparison = self.project(f)
        rows = self.rows(comparison)
        self.assertEqual(comparison['schema'], 'earnings_population_public_predictions_v1')
        self.assertEqual([r['target_id'] for r in comparison['targets']], TARGETS)
        self.assertEqual(set(rows['T005']), {'target_id', 'predicted_value', 'R_advice_value', 'matches_R_advice', 'points_awarded'})
        self.assertEqual((rows['T005']['predicted_value'], rows['T005']['R_advice_value']), (310, 334.1))
        self.assertIs(rows['T005']['matches_R_advice'], False)
        self.assertIsNone(rows['T002']['R_advice_value']); self.assertIsNone(rows['T002']['matches_R_advice'])
        self.assertEqual(rows['T005']['points_awarded'], .5)
        self.assertEqual(diagnostics['source_sha256'], self.version['R']['sha256'])
        self.assertEqual(f['runner'].calls, 1); self.assertFalse(self.h.fixture.marker.exists())
        self.assertEqual(before, {str(p): p.read_bytes() for p in f['record']['root'].rglob('*') if p.is_file()})
        serialized = json.dumps(comparison)
        self.assertNotIn('SYNTHETIC_PRIVATE', serialized); self.assertNotIn('999999', serialized)
        self.assertIn('not causal', comparison['limitation'])

    def test_missing_nested_or_incomplete_R_advice_is_null_not_reconstructed(self):
        original = deepcopy(self.advice)
        for mode in ('missing_targets', 'nested_only', 'missing_value', 'incomplete_value', 'unreported'):
            with self.subTest(mode=mode):
                self.advice = deepcopy(original)
                if mode == 'missing_targets': self.advice.pop('targets')
                elif mode == 'nested_only': self.advice['targets'][4].pop('predicted_value')
                elif mode == 'missing_value': self.advice['targets'][4].pop('predicted_value')
                elif mode == 'incomplete_value': self.advice['targets'][4]['status'] = 'incomplete'
                else: self.advice['targets'][4].pop('status')
                self.advice['nested']['T005'] = {'predicted_value': 310}
                _, result = self.project(self.fixture())
                self.assertIsNone(self.rows(result)['T005']['R_advice_value'])
                self.assertIsNone(self.rows(result)['T005']['matches_R_advice'])
                self.advice = original

    def test_legal_nonobject_R_output_has_no_advice_not_a_projection_crash(self):
        # Existing researcher.requests and diagnostics deliberately permit
        # algorithm-specific JSON outputs without imposing a targets schema.
        for value in (None, [], 42, 'Synthetic custom algorithm output'):
            with self.subTest(value=value):
                self.advice = value
                diagnostics, comparison = self.project(self.fixture())
                self.assertIn('output_not_object', diagnostics['diagnostic_flags'])
                self.assertTrue(all(row['R_advice_value'] is None and row['matches_R_advice'] is None
                                    for row in comparison['targets']))

    def test_submitted_numeric_strings_stay_verbatim_equality_is_only_numeric(self):
        predicted = deepcopy(self.predictions)
        predicted['predictions'][0]['predicted_value'] = '1e1'
        self.advice['targets'][0]['predicted_value'] = '10.00'
        _, result = self.project(self.fixture(predictions=predicted))
        row = self.rows(result)['T001']
        self.assertEqual(row['predicted_value'], '1e1'); self.assertEqual(row['R_advice_value'], '10.00')
        self.assertIs(row['matches_R_advice'], True)
        self.assertIn('not causal', result['limitation'])

    def test_complete_nonfinite_or_malformed_R_advice_refused(self):
        for bad in (None, True, 'NaN', 'Infinity', '-Infinity', '1e9999', [1, 2], {'value': 1}):
            with self.subTest(bad=bad):
                self.advice['targets'][4]['predicted_value'] = bad
                f = self.fixture()
                with self.assertRaises((ValueError, TypeError)): self.project(f)

    def test_duplicate_R_target_ids_are_ambiguous_even_if_one_incomplete(self):
        for status in ('complete', 'incomplete'):
            with self.subTest(status=status):
                self.advice['targets'].append(dict(self.advice['targets'][0], status=status))
                f = self.fixture()
                with self.assertRaises(ValueError): self.project(f)
                self.advice['targets'].pop()

    def test_nonfinite_boolean_missing_unknown_or_duplicate_submissions_refused(self):
        for mode in ('NaN', 'Infinity', '1e9999', 'boolean', 'missing', 'unknown', 'duplicate'):
            with self.subTest(mode=mode):
                predicted = deepcopy(self.predictions)
                if mode in ('NaN', 'Infinity', '1e9999'): predicted['predictions'][0]['predicted_value'] = mode
                elif mode == 'boolean': predicted['predictions'][0]['predicted_value'] = True
                elif mode == 'missing': predicted['predictions'].pop()
                elif mode == 'unknown': predicted['predictions'][4]['target_id'] = 'T999'
                else: predicted['predictions'].append(deepcopy(predicted['predictions'][0]))
                f = self.fixture(predictions=predicted)
                with self.assertRaises((ValueError, TypeError)): self.project(f)

    def test_wrong_company_version_R_or_H_source_refused(self):
        for mode in ('company', 'version', 'R', 'H'):
            with self.subTest(mode=mode):
                f = self.fixture(); trial = engine.read(f['public'])
                if mode == 'company': trial['company_id'] = 'CIK0000017313' if self.company['cik'] != 'CIK0000017313' else 'CIK0000004457'
                elif mode == 'version': trial['version_id'] = 'f'*64
                else: trial['pool_sources'][mode] = 'f'*64
                changed = self.rewrite(f['public'], trial)
                with self.assertRaises(ValueError): self.project(f, public=changed)

    def test_awards_require_original_five_exact_targets_and_sum(self):
        for mode in ('duplicate', 'unknown', 'missing', 'order', 'bad_award', 'sum'):
            with self.subTest(mode=mode):
                f = self.fixture(); trial = engine.read(f['public'])
                if mode == 'duplicate': trial['target_scores'][4]['target_id'] = 'T001'
                elif mode == 'unknown': trial['target_scores'][4]['target_id'] = 'T999'
                elif mode == 'missing': trial['target_scores'].pop()
                elif mode == 'order': trial['target_scores'].reverse()
                elif mode == 'bad_award': trial['target_scores'][0]['points_awarded'] = True
                else: trial['points'] = 4
                with self.assertRaises(ValueError): self.project(f, public=self.rewrite(f['public'], trial))

    def test_changed_submission_with_refreshed_filehash_cannot_override_final_response(self):
        f = self.fixture(); predicted = engine.read(f['predictions'])
        predicted['predictions'][4]['predicted_value'] = 999
        changed = self.rewrite(f['predictions'], predicted)
        evidence = [changed if b == f['predictions'] else b for b in f['evidence']]
        with self.assertRaises(ValueError): self.project(f, evidence=evidence)

    def test_missing_duplicate_or_foreign_original_evidence_refused(self):
        for key in ('predictions', 'result'):
            for mode in ('missing', 'duplicate', 'foreign'):
                with self.subTest(key=key, mode=mode):
                    f = self.fixture(); selected = f[key]
                    evidence = [b for b in f['evidence'] if b != selected]
                    if mode == 'duplicate': evidence.extend([selected, selected])
                    elif mode == 'foreign':
                        other = self.h.fixture.root/('foreign-'+str(len(self.h.runners)))
                        other.mkdir(); (other/Path(selected['path']).name).write_bytes(Path(selected['path']).read_bytes())
                        evidence.append(engine.pin(other/Path(selected['path']).name))
                    with self.assertRaises(ValueError): self.project(f, evidence=evidence)

    def test_physical_intent_raw_and_sidecar_must_remain_original_bound_bytes(self):
        for key in ('intent', 'raw', 'physical_response'):
            with self.subTest(key=key):
                f = self.fixture(); selected = f['record'][key]
                path = Path(selected['path'])
                # Valid JSON/identical meaning, but changed immutable bytes.
                path.write_bytes(path.read_bytes()+b'\n ')
                with self.assertRaises(ValueError): self.project(f)

    def test_optional_physical_origin_binding_cannot_be_duplicated(self):
        for key in ('intent', 'raw', 'physical_response'):
            with self.subTest(key=key):
                f = self.fixture(); selected = f['record'][key]
                evidence = [b for b in f['evidence'] if b != selected]
                evidence.extend([selected, selected])
                with self.assertRaises(ValueError): self.project(f, evidence=evidence)

    def without_wire_bindings(self, f):
        # Real OpenTask -> earnings_execution_receipt.verify returns numbered
        # requests/responses/predictions, NOT ReceiptHTTP intent/raw/sidecar.
        # The three files still exist; they are now retrospective observations.
        wires = [f['record'][key] for key in ('intent', 'raw', 'physical_response')]
        return [b for b in f['evidence'] if b not in wires]

    def test_actual_producer_shaped_evidence_without_wire_pins_is_explicitly_retrospective(self):
        f = self.fixture(); evidence = self.without_wire_bindings(f)
        _, comparison = self.project(f, evidence=evidence)
        expected = {Path(b['path']).name: b['sha256'] for b in evidence}
        self.assertEqual(comparison['evidence']['originals'], expected)
        self.assertEqual(len(expected), 7)
        observation = comparison['evidence']['readonly_physical_observation']
        self.assertEqual(observation['originally_bound_files'], [])
        self.assertEqual(observation['files'], {Path(f['record'][key]['path']).name: f['record'][key]['sha256']
                          for key in ('intent', 'raw', 'physical_response')})
        self.assertIn('Retrospective read-only', observation['qualification'])
        self.assertIn('not proof these bytes were historically pinned', observation['qualification'])
        self.assertEqual(self.rows(comparison)['T005']['predicted_value'], 310)
        self.assertEqual(self.rows(comparison)['T005']['R_advice_value'], 334.1)

    def test_retrospective_unbound_wire_semantic_tamper_still_refuses(self):
        for key in ('intent', 'raw', 'physical_response'):
            with self.subTest(key=key):
                f = self.fixture(); evidence = self.without_wire_bindings(f)
                value = engine.read(f['record'][key])
                if key == 'intent': value['complete_reservation']['request_id'] = 'not-original'
                else: value['output'] = []
                self.rewrite(f['record'][key], value)
                with self.assertRaises(ValueError): self.project(f, evidence=evidence)

    def test_unbound_wire_whitespace_change_is_not_false_frozen_byte_proof(self):
        for key in ('intent', 'raw', 'physical_response'):
            with self.subTest(key=key):
                f = self.fixture(); evidence = self.without_wire_bindings(f)
                path = Path(f['record'][key]['path'])
                path.write_bytes(path.read_bytes()+b'\n ')
                new = engine.pin(path)
                self.assertNotEqual(new, f['record'][key])
                _, comparison = self.project(f, evidence=evidence)
                observation = comparison['evidence']['readonly_physical_observation']
                self.assertEqual(observation['files'][path.name], new['sha256'])
                self.assertEqual(observation['originally_bound_files'], [])
                self.assertNotIn(path.name, comparison['evidence']['originals'])
                self.assertIn('not proof these bytes were historically pinned', observation['qualification'])
                self.assertEqual(self.rows(comparison)['T005']['predicted_value'], 310)

    def test_mixed_optional_wire_provenance_never_upgrades_unbound_files(self):
        f = self.fixture(); evidence = [*self.without_wire_bindings(f), f['record']['raw']]
        path = Path(f['record']['intent']['path']); path.write_bytes(path.read_bytes()+b'\n')
        _, comparison = self.project(f, evidence=evidence)
        observation = comparison['evidence']['readonly_physical_observation']
        self.assertEqual(observation['originally_bound_files'], [Path(f['record']['raw']['path']).name])
        self.assertEqual(observation['files'][path.name], engine.pin(path)['sha256'])
        # The optional raw binding really was supplied: stale bytes still refuse.
        raw = Path(f['record']['raw']['path']); raw.write_bytes(raw.read_bytes()+b'\n')
        with self.assertRaises(ValueError): self.project(f, evidence=evidence)

    def test_numbered_final_response_drift_or_uncompleted_status_refused(self):
        for mode in ('model', 'status', 'output'):
            with self.subTest(mode=mode):
                f = self.fixture(); bound = f['record']['response']; value = engine.read(bound)
                if mode == 'model': value['model'] = 'foreign-model'
                elif mode == 'status': value['status'] = 'incomplete'
                else: value['output'] = []
                changed = self.rewrite(bound, value)
                evidence = [changed if b == bound else b for b in f['evidence']]
                with self.assertRaises(ValueError): self.project(f, evidence=evidence)

    def test_symlink_and_hardlink_public_originals_are_not_accepted_as_aliases(self):
        for mode in ('symlink', 'hardlink'):
            with self.subTest(mode=mode):
                f = self.fixture(); path = Path(f['predictions']['path'])
                other = path.with_name('alias-target.json'); other.write_bytes(path.read_bytes())
                path.unlink()
                if mode == 'symlink': path.symlink_to(other)
                else: os.link(other, path)
                with self.assertRaises(ValueError): self.project(f)

    def test_private_extra_evidence_is_not_read_or_copied(self):
        f = self.fixture()
        secret = engine.save(f['record']['root']/'do-not-open-gold.json', {'label': 'SYNTHETIC_GOLD_SENTINEL'})
        original_read = Path.read_bytes
        def guarded(path):
            if path == Path(secret['path']): raise AssertionError('private evidence opened')
            return original_read(path)
        with patch.object(Path, 'read_bytes', guarded):
            _, result = self.project(f, evidence=[*f['evidence'], secret])
        text = json.dumps(result)
        self.assertNotIn('do-not-open-gold', text); self.assertNotIn('SYNTHETIC_', text)

    def test_absent_policy_preserves_exact_legacy_projection_and_never_reads_predictions(self):
        f = self.fixture(); bound = self.feedback(f)
        with patch.object(public_api, 'project', side_effect=AssertionError('legacy unexpectedly opted in')):
            legacy = broker.public_feedback(bound, {self.version['id']: self.version})
            explicit_none = broker.public_feedback(bound, {self.version['id']: self.version}, policy=None)
        self.assertEqual(legacy, explicit_none)
        self.assertNotIn('public_predictions', legacy['results'][0])
        self.assertIn('research_diagnostics', legacy['results'][0])
        opted_in = broker.public_feedback(bound, {self.version['id']: self.version}, policy=public_api.POLICY)
        self.assertEqual(self.rows(opted_in['results'][0]['public_predictions'])['T005']['predicted_value'], 310)

    def test_original_legacy_missing_program_receipt_does_not_invent_public_predictions(self):
        f = self.fixture(); public = engine.read(f['public'])
        original = {'schema': 'earnings_population_feedback_v1', 'company_id': self.company['cik'],
            'round_index': 1, 'stable_id': self.version['id'], 'scope': 'Legacy synthetic original',
            'results': [{'version_id': self.version['id'], 'points': 3, 'evidence': [f['public']]}]}
        value = broker._public_scored(original, {self.version['id']: self.version})
        self.assertEqual(value['results'][0]['research_diagnostics'], {'availability': 'unavailable_missing_execution_evidence'})
        self.assertNotIn('public_predictions', value['results'][0])
        opted_in = broker._public_scored(original, {self.version['id']: self.version}, policy=public_api.POLICY)
        self.assertEqual(opted_in, value)  # Explicit missing evidence, never fabricated values.

    def test_later_unscored_observation_retains_exact_optional_comparison_not_fake_score(self):
        f = self.fixture(); bound = self.feedback(f); versions = {self.version['id']: self.version}
        def project_scored(original, selected): return broker._public_scored(original, selected, policy=public_api.POLICY)
        carried = contexts._last_scored(bound, self.company['cik'], versions, project_scored)
        expected = broker.public_feedback(bound, versions, policy=public_api.POLICY)['results'][0]['public_predictions']
        self.assertEqual(carried['results'][0]['public_predictions'], expected)
        legacy = contexts._last_scored(bound, self.company['cik'], versions, broker._public_scored)
        self.assertNotIn('public_predictions', legacy['results'][0])
        self.assertEqual(set(carried), {'binding', 'company_id', 'results'})

    def test_actual_unscored_campaign_projection_carries_comparison_without_results(self):
        f = self.fixture(); bound = self.feedback(f); versions = {self.version['id']: self.version}
        original = {'schema': 'earnings_population_campaign_feedback_v1', 'kind': 'no_change',
            'score_state': 'unscored', 'company_id': self.company['cik'], 'round_index': 2,
            'decision': bound, 'chosen_parent_id': self.version['id'], 'baseline_version_id': self.version['id'],
            'previous_feedback': bound, 'campaign_contract_sha256': 'a'*64, 'last_scored_feedback': bound,
            'scope': 'Synthetic unscored carry only', 'candidate': None,
            'exploration_review': {'accepted_for_exploration': False, 'evidence': []}, 'results': []}
        def project_scored(value, selected): return broker._public_scored(value, selected, policy=public_api.POLICY)
        projected = contexts.project(original, versions, project_scored)
        self.assertEqual(projected['score_state'], 'unscored'); self.assertNotIn('results', projected)
        comparison = projected['last_scored_observation']['results'][0]['public_predictions']
        self.assertEqual(self.rows(comparison)['T005']['predicted_value'], 310)
        self.assertIs(self.rows(comparison)['T005']['matches_R_advice'], False)
        self.assertEqual(projected['last_scored_observation']['binding'], bound)

    def test_multiturn_terminal_response_is_not_replaced_by_first_generation(self):
        """Original first-consumption verifier plus distinct exact final originals."""
        f = self.fixture(); root = f['record']['root']
        # Rebuild first physical transcript as an ordinary research call.
        first_request = engine.read(f['record']['request'])
        first_request['payload']['tool_choice'] = 'auto'
        first_request['payload']['input'] = engine.read(f['record']['effective'])['context']['messages']
        first_binding = self.rewrite(f['record']['request'], first_request)
        first_response = engine.read(f['record']['response'])
        first_response['output'] = [{'type': 'function_call', 'call_id': 'synthetic-public-read',
                                    'name': 'calculate', 'arguments': '{"expression":"1+1"}'}]
        first_response_binding = self.rewrite(f['record']['response'], first_response)
        intent = engine.read(f['record']['intent'])
        intent.update(complete_reservation=first_request, request_receipt_sha256=first_binding['sha256'],
            payload=dict(first_request['payload'], max_output_tokens=1024, service_tier='default', store=False))
        first_intent = self.rewrite(f['record']['intent'], intent)
        first_side = self.rewrite(f['record']['physical_response'], first_response)
        first_raw = self.rewrite(f['record']['raw'], {k: v for k, v in first_response.items() if k != '_request_id'})
        replaced = {f['record'][key]['path']: new for key, new in (
            ('request', first_binding), ('response', first_response_binding), ('intent', first_intent),
            ('physical_response', first_side), ('raw', first_raw))}
        evidence = [replaced.get(b['path'], b) for b in f['evidence']]
        history = [*first_request['payload']['input'], *first_response['output'],
                   {'type': 'function_call_output', 'call_id': 'synthetic-public-read', 'output': '{"value":2}'}]
        payload = final_request(history, {'api_model': 'gpt-6.1-sol', 'effort': 'max'}, TARGETS)
        final = engine.save(root/'02-request.json', {'request_id': 'synthetic-distinct-final',
            'reserved_nano_usd': 1000000, 'payload': payload})
        request = engine.read(final)
        response = dict(first_response, output=[{'type': 'message', 'role': 'assistant',
            'content': [{'type': 'output_text', 'text': json.dumps(self.predictions)}]}])
        numbered = engine.save(root/'02-response.json', response)
        final_intent = engine.save(root/'http-terminal.intent.json', {
            'endpoint': '/v1/responses', 'utc_epoch': 0, 'retry_allowed': False,
            'budget_request_id': request['request_id'], 'complete_reservation': request,
            'request_receipt_sha256': final['sha256'],
            'payload': dict(payload, max_output_tokens=1024, service_tier='default', store=False)})
        side = engine.save(root/'http-terminal.response.json', response)
        raw = engine.save(root/'http-terminal.raw.bin', {k: v for k, v in response.items() if k != '_request_id'})
        completed = dict(engine.read(f['result']), turns=2)
        result_binding = self.rewrite(f['result'], completed)
        evidence = [result_binding if b == f['result'] else b for b in evidence]
        evidence.extend([final, numbered, final_intent, side, raw])
        _, comparison = self.project(f, evidence=evidence)
        self.assertIn('02-response.json', comparison['evidence']['originals'])
        self.assertEqual(self.rows(comparison)['T005']['predicted_value'], 310)
        self.assertFalse(self.h.fixture.marker.exists())
        # Even semantically unchanged final wire bytes cannot refresh original proof.
        Path(raw['path']).write_bytes(Path(raw['path']).read_bytes()+b'\n')
        with self.assertRaises(ValueError): self.project(f, evidence=evidence)


class PublicPolicyAdversarial(unittest.TestCase):
    def setUp(self):
        self.grant = {'path': '/invented/only-a-policy-unit-seam.json', 'sha256': 'a'*64}
        self.runtime = {'schema': 'earnings_population_runtime_v1', 'public_feedback_policy': public_api.POLICY,
                        'budget_amendment': self.grant, 'companies': ['CIK0000017313']}
        self.study = {'campaign': {'fixture': True}, 'campaign_resume': {'fixture': True}, 'continuation': None}
        self.patcher = patch('earnings_population_budget.amendment_binding', return_value=self.grant)
        self.patcher.start(); self.addCleanup(self.patcher.stop)

    def test_unknown_policy_and_present_null_refused_but_absence_legacy(self):
        self.assertIsNone(public_api.runtime_policy({}))
        self.assertEqual(public_api.runtime_policy(self.runtime, self.study), public_api.POLICY)
        for value in (True, 1, {}, [], '', 'future', None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                public_api.runtime_policy(dict(self.runtime, public_feedback_policy=value), self.study)

    def test_runtime_must_be_resumed_DEV_with_exact_original_grant(self):
        for key, value in (('budget_amendment', None), ('budget_amendment', dict(self.grant, sha256='b'*64)),
                           ('companies', []), ('companies', ['CIK0000021076']), ('companies', 'CIK0000017313')):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                public_api.runtime_policy(dict(self.runtime, **{key: value}), self.study)
        for key, value in (('campaign', None), ('campaign_resume', None), ('continuation', {'fixture': True})):
            with self.subTest(key=key), self.assertRaises(ValueError):
                public_api.runtime_policy(self.runtime, dict(self.study, **{key: value}))

    def test_unknown_broker_policy_refused_even_for_seed_feedback(self):
        for policy in ('future', True, {}, 1):
            with self.subTest(policy=policy), self.assertRaises(ValueError):
                broker.public_feedback({'schema': 'earnings_population_seed_v1'}, {}, policy=policy)

    def test_wrong_runtime_placement_rejected_and_old_runtime_not_opted_in(self):
        for schema in ('earnings_capacity_runtime_v1', 'future', None):
            with self.subTest(schema=schema), self.assertRaises(ValueError):
                public_api.runtime_policy(dict(self.runtime, schema=schema), self.study)
        original = {k: v for k, v in self.runtime.items() if k != 'public_feedback_policy'}
        with patch.object(public_api, 'policy', side_effect=AssertionError('global new policy leaked to old runtime')):
            self.assertIsNone(public_api.runtime_policy(original, self.study))

    def test_company_descriptor_is_metadata_only_and_refuses_nonDEV_before_lookup(self):
        cik = 'CIK0000017313'; row = {'cik': cik, 'target_accession': 'synthetic-original-accession'}
        universe = ({'companies': [row]}, {'instances': [{'cik': cik, 'target_count': 5,
                     'target_accession': row['target_accession']}]}, {'metadata': 'synthetic'})
        with patch('earnings_population_tasks._universe', return_value=universe) as metadata, \
                patch('earnings_population_tasks.resident', side_effect=AssertionError('body/QA resident not permitted')):
            self.assertEqual(public_api.company(cik), row); metadata.assert_called_once()
        with patch('earnings_population_tasks._universe', side_effect=AssertionError('no metadata for sealed company')):
            for bad in ('CIK0000021076', None, {}, True):
                with self.subTest(bad=bad), self.assertRaises(ValueError): public_api.company(bad)


if __name__ == '__main__': unittest.main()
