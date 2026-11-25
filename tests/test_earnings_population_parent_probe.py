"""Matched Review inputs on invented public data and scripted execution receipts.

Services, FilingTools, R request/receipt verification, diagnostics and packing
are real. The runner never executes source; Author cases and model Review are
inert fixtures, not live admission, model authorship or financial evidence.
"""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from edgar_forecast_tools import FilingTools
import earnings_open_context as packing
import earnings_population_services as services
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_open_researcher as receipts
import test_earnings_population_case as fixtures


class MatchedParentProbeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.PopulationCaseTests()
        self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.company = self.fixture.resident['company']
        parent_source = "PROGRAM={'axis':'R'}\ndef run(payload): return {'parent': True}\n"
        self.parent = services.describe(self.fixture.file('selected-parent.py', parent_source),
            self.fixture.h, parent=self.fixture.version['id'], axis='R',
            method='Selected synthetic explorer', evidence=[self.fixture.authority])
        self.child_source = "PROGRAM={'axis':'R'}\ndef run(payload): return {'child': True}\n"
        self.child = services.describe(self.fixture.file('child.py', self.child_source),
            self.fixture.h, parent=self.parent['id'], axis='R',
            method='Synthetic candidate', evidence=[self.fixture.authority])
        self.state = dict(stable_id=self.fixture.version['id'], explorers=[self.parent['id']],
            versions={row['id']: deepcopy(row) for row in (self.fixture.version, self.parent)})
        self.owner = services.Services.__new__(services.Services)
        self.owner.native_root = self.root
        self.owner.prior_feedback = {'company_id': self.company['cik']}
        self.owner.campaign_context = {'feedback_binding': self.fixture.authority,
            'original_R_evidence_abi': {'synthetic': True}}
        self.case = {'company': self.company,
            'state_api': SimpleNamespace(tools=FilingTools(self.company))}
        self.owner.case = Mock(return_value=self.case)
        self.owner.authored = {self.child['id']: self.authored(self.child_source)}
        self.child_request = {'research_requests': [{'tool': 'search_files', 'arguments': {
            'query': 'revenue', 'path_prefix': 'filings/', 'max_hits': 5}}]}
        self.parent_request = {'research_requests': [{'tool': 'search_files', 'arguments': {
            'query': 'reported', 'path_prefix': 'filings/', 'max_hits': 5}}]}
        self.owner.runner = receipts.ScriptedReceiptRunner(self.root/'runner',
            [self.child_request, self.advice('child'), self.child_request, self.advice('child'),
             self.parent_request, self.advice('parent'), self.parent_request, self.advice('parent')])
        self.prompts, self.role_versions = [], []
        self.accepted = False
        self.owner.role = Mock(side_effect=self.role)
        self.slot = self.root/'roles'/'review-01'

    def authored(self, source):
        return {'source': source, 'parsed': {'cases': [{'input': {}, 'expected': {}}]},
            'originals': [self.fixture.authority], 'decision': {'axis': 'R'}}

    @staticmethod
    def advice(label):
        return {'coverage': {'extracted_cells': 1}, 'evidence': [], 'method': label,
            'targets': [{'target_id': f'T{i:03d}', 'status': 'incomplete', 'missing': ['metric']}
                        for i in range(1, 6)]}

    def role(self, name, kind, case, slot):
        self.role_versions.append(deepcopy(self.owner.role_versions))
        return SimpleNamespace(review=self.review,
            broker=SimpleNamespace(references=lambda: deepcopy(self.owner.role_versions)))

    def review(self, prompt, slot):
        self.prompts.append(deepcopy(prompt)); Path(slot).mkdir(parents=True)
        original = engine.save(Path(slot)/'response.json', {'synthetic_review_transport': True})
        engine.save(Path(slot)/'review.json', {'original': original, 'review': {
            'accepted_for_exploration': self.accepted, 'rationale': 'Synthetic independent decision'}})
        return original

    def invoke(self):
        with patch.object(services, 'run_cases', return_value=[{'passed': True, 'synthetic': True}]):
            return self.owner.review(self.child, self.state, str(self.slot))

    def test_fresh_selected_parent_same_initial_inputs_not_same_queries(self):
        before = deepcopy(self.state)
        fresh = []
        def tools(company):
            result = FilingTools(company); self.assertEqual(result.calls, 0)
            fresh.append(result); return result
        with patch.object(services, 'FilingTools', side_effect=tools):
            result = self.invoke()
        self.assertEqual(self.state, before)
        self.assertFalse(result['accepted_for_exploration'])
        self.assertEqual(self.owner.runner.calls, 8)
        calls = self.owner.runner.invocations
        for child, parent in ((calls[0], calls[4]), (calls[2], calls[6])):
            self.assertEqual(child['payload'], parent['payload'])
            self.assertEqual(parent['source'], Path(self.parent['R']['path']).read_text())
            self.assertNotEqual(child['source'], parent['source'])
        self.assertEqual(calls[0]['payload']['records'], [])
        self.assertEqual(calls[0]['payload']['stage'], 'forecast')
        self.assertEqual(calls[2]['payload']['stage'], 'controller')
        self.assertEqual(len(fresh), 2); self.assertIsNot(fresh[0], fresh[1])
        self.assertTrue(all(row.calls == 1 for row in fresh))
        self.assertEqual(self.case['state_api'].tools.calls, 2)
        prompt = self.prompts[0]
        child_probes = prompt['original_public_empty_state_probes']
        parents = prompt['matched_active_parent_empty_state_probes']
        self.assertEqual([row['stage'] for row in parents], ['forecast', 'controller'])
        self.assertEqual(set(self.role_versions[0]), {self.child['id'], self.parent['id']})
        for own, other in zip(child_probes, parents):
            self.assertNotEqual(own['receipt'], other['receipt'])
            self.assertTrue(own['receipt']['path'].endswith('-probe.json'))
            self.assertTrue(other['receipt']['path'].endswith('-comparison.json'))
            saved = engine.read(other['receipt'])
            self.assertEqual(saved['matched_child_probe'], own['receipt'])
            self.assertEqual(saved['input'], engine.read(own['receipt'])['input'])
            self.assertEqual(saved['initial_input_sha256'], digest(saved['input']))
            self.assertEqual(saved['parent_version_id'], self.parent['id'])
            self.assertEqual(saved['parent_programs'], {a: self.parent[a] for a in ('R', 'H')})
            self.assertEqual(saved['diagnostics']['source_sha256'], self.parent['R']['sha256'])
            self.assertEqual(other['verified_public_R_output']['value']['method'], 'parent')
            self.assertIn(other['receipt'], result['evidence'])
            self.assertIn(own['receipt'], result['evidence'])
        self.assertEqual(prompt['active_parent_comparison']['status'], 'matched_R_probes_completed')
        self.assertNotIn('score', prompt['active_parent_comparison'])
        self.assertFalse(self.fixture.marker.exists())

    def test_program_reported_incompleteness_does_not_override_model_verdict(self):
        self.accepted = True
        self.assertTrue(self.invoke()['accepted_for_exploration'])
        self.assertEqual(self.prompts[0]['matched_active_parent_empty_state_probes'][0]
            ['diagnostics']['reported_target_completion'][0]['status'], 'incomplete')

    def test_legacy_review_does_not_add_parent_work_or_fields(self):
        self.owner.campaign_context = None
        self.invoke()
        self.assertEqual(self.owner.runner.calls, 4)
        self.assertNotIn('matched_active_parent_empty_state_probes', self.prompts[0])
        self.assertNotIn('active_parent_comparison', self.prompts[0])
        self.assertEqual(set(self.role_versions[0]), {self.child['id']})

    def test_H_candidate_has_no_fabricated_R_comparison_or_H_claim(self):
        child = services.describe(self.parent['R'], self.fixture.file('child-H.py',
            "PROGRAM={'axis':'H','tools':[]}\ndef run(p): return {}\n"),
            parent=self.parent['id'], axis='H', method='Synthetic H', evidence=[self.fixture.authority])
        self.child = child; self.owner.authored[child['id']] = self.authored('synthetic H not executed')
        self.invoke()
        self.assertEqual(self.owner.runner.calls, 0)
        self.assertEqual(self.prompts[0]['matched_active_parent_empty_state_probes'], [])
        self.assertEqual(self.prompts[0]['active_parent_comparison']['status'], 'not_run_H_candidate')

    def test_inactive_or_wrong_other_axis_parent_refused_before_execution(self):
        self.state['explorers'] = []
        with self.assertRaisesRegex(ValueError, 'selected active parent'):
            self.invoke()
        self.assertEqual(self.owner.runner.calls, 0); self.owner.case.assert_not_called()
        self.state['explorers'] = [self.parent['id']]
        self.child['H'] = self.fixture.file('wrong-H.py', 'not the unchanged other axis')
        with self.assertRaisesRegex(ValueError, 'selected active parent'):
            self.invoke()
        self.assertEqual(self.owner.runner.calls, 0)

    def test_parent_source_drift_refused_before_execution(self):
        Path(self.parent['R']['path']).write_text('changed after source binding')
        with self.assertRaises(ValueError): self.invoke()
        self.assertEqual(self.owner.runner.calls, 0); self.owner.role.assert_not_called()

    def test_parent_invalid_execution_stops_before_paid_review_without_retry(self):
        self.owner.runner.values[5] = self.parent_request
        with self.assertRaisesRegex(ValueError, 'another evidence phase'):
            self.invoke()
        self.assertEqual(self.owner.runner.calls, 6)
        self.owner.role.assert_not_called()
        self.assertTrue((self.root/'review-01-forecast-probe.json').exists())
        self.assertTrue((self.root/'review-01-controller-probe.json').exists())
        self.assertFalse((self.root/'review-01-parent-forecast-comparison.json').exists())

    def test_wrong_child_input_binding_refuses_parent_dispatch(self):
        payload = {'stage': 'forecast', 'questions': 'wrong public questions',
            'filing_index': self.case['state_api'].tools.files['filing_index.tsv'], 'records': []}
        bad = engine.save(self.root/'bad-child-probe.json', {'company_id': self.company['cik'],
            'input': payload, 'diagnostics': {'source_sha256': self.child['R']['sha256']}})
        with self.assertRaisesRegex(ValueError, 'exact original child initial input'):
            self.owner.matched_parent_probes(self.parent, self.child, self.case, [bad, bad], str(self.slot))
        self.assertEqual(self.owner.runner.calls, 0)

    def test_parent_public_view_has_explicit_bound_and_complete_original_digest(self):
        self.owner.runner.values[5]['public_long_text'] = 'invented public advice '*500
        self.invoke()
        row = self.prompts[0]['matched_active_parent_empty_state_probes'][0]
        public = row['verified_public_R_output']
        self.assertFalse(public['complete']); self.assertEqual(len(public['json_prefix']), 3000)
        self.assertIn('qualification', public)
        saved = engine.read(row['receipt'])
        value = services.researcher.verify(saved['execution'], Path(self.parent['R']['path']).read_text(),
            saved['input'], self.company)
        self.assertEqual(public['value_sha256'], digest(value))

    def test_matched_parent_fields_survive_real_review_observation_fallback(self):
        self.invoke(); prompt = self.prompts[0]
        initial = json.dumps(prompt, sort_keys=True)
        request = {'instructions': 'Exact independent Review task',
            'input': [{'role': 'user', 'content': initial},
            {'type': 'function_call', 'name': 'read_population_program', 'call_id': 'old', 'arguments': '{}'},
            {'type': 'function_call_output', 'call_id': 'old', 'output': 'public previous output '*3000},
            {'type': 'reasoning', 'id': 'synthetic-opaque-continuity-not-read'}],
            'tool_choice': 'auto', 'text': {'format': {'name': 'earnings_population_review_v1',
                'schema': {'properties': {k: {} for k in ('candidate_id','accepted_for_exploration','rationale')}}}}}
        received = []
        def count(endpoint, payload):
            self.assertEqual(endpoint, '/v1/responses/input_tokens'); received.append(deepcopy(payload))
            return {'input_tokens': 20001 if len(received) == 1 else 19000}
        output = self.root/'packing'; output.mkdir()
        completion = dict(request, tool_choice='none',
            instructions=request['instructions']+' Complete only the Review object.')
        packed = packing.pack(SimpleNamespace(post=count), request, {'max_input_tokens': 20000}, output, 2,
            completion_request=completion)
        self.assertEqual(len(received), 2)
        self.assertEqual(packed['input'][0]['content'], initial)
        for candidate in received:
            decoded = json.loads(candidate['input'][0]['content'])
            self.assertEqual(decoded['matched_active_parent_empty_state_probes'],
                             prompt['matched_active_parent_empty_state_probes'])
            self.assertEqual(decoded['active_parent_comparison'], prompt['active_parent_comparison'])
        snapshot = json.loads(packed['input'][1]['content'])
        self.assertEqual(snapshot['schema'], 'earnings_review_final_public_snapshot_v1')
        self.assertEqual(snapshot['records'][1]['output'], request['input'][2]['output'])


if __name__ == '__main__':
    unittest.main()
