import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import controller_source_review as review
from controller_activity_log import read_activity_events
from market_rsi import canonical, digest, fresh_json
from public_source_metadata import run as metadata_run
from test_controller_design import visible_fixture


def fixture():
    old, _, _ = visible_fixture()
    receipt = {'schema': 'public_source_directory_metadata_review_v1', 'passed': True,
        'dataset': 'fixture/source', 'revision': 'a' * 40, 'acquisition_admitted': False,
        'objects': [{'path': 'tape.db.zst', 'type': 'file', 'advertised_bytes': 123,
                     'advertised_sha256': 'b' * 64}]}
    receipt['result_sha256'] = digest(receipt)
    catalog = {'schema': 'historical_public_source_review_catalog_v1', 'source_selected': None,
               'acquisition_authorized': False, 'sources': [{'id': 'fixture/source', 'note': 'Synthetic metadata.'}]}
    visible = {n: old[n] for n in ('context.json', 'source-contract.json', 'archive.json', 'literature.json')}
    visible.update({'source-review-catalog.json': catalog,
        'prior-source-catalog.json': {'sources': [{'source_id': 'synthetic-market-simulator'}]},
        'evidence.json': {'directory_receipts': [receipt]}, 'readiness.json': {'no_data_authority': True},
        'limits.json': copy.deepcopy(review.LIMITS)})
    plan = {'plan_id': 'fixture-plan', 'context_sha256': old['context.json']['context_sha256'],
        'review_catalog_sha256': digest(catalog), 'stage': 'new_data_stage', 'source_ids': ['fixture/source'],
        'objects': [{'source_id': 'fixture/source', 'revision': 'a' * 40, 'path': 'tape.db.zst',
                     'bytes': 123, 'sha256': 'b' * 64}],
        'requested_window': ['2026-06-01', '2026-06-30'], 'minimum_complete_sessions': 20,
        'question': 'Synthetic field-compatibility study; no actual market research.',
        'source_contract_changes': ['Declare new source.'], 'required_streams': ['fixture_quotes'],
        'field_mapping': [{'required_field': 'fixture_quote', 'proposed_field': 'payload',
                          'availability_clock': 'local receipt', 'status': 'requires_raw_check',
                          'evidence': 'Synthetic metadata only.'}],
        'clock_policy': 'Preserve causal receipt and same-time ordinal.',
        'gap_policy': 'Report gaps without imputing.', 'coverage_policy': 'Independent whole-day QA.',
        'unresolved_questions': ['No raw validation performed.'], 'artifact_use': 'opened_data_qa_train_only',
        'quiet_rows': 'preserve_raw_no_future_filter', 'validation_claim': 'none'}
    request = {'request_id': 'fixture-request', 'source_name': 'another/source',
        'public_metadata_urls': ['https://example.com/dataset-schema'],
        'questions': ['Where are the timestamp definitions?'], 'relevance': 'Metadata research, no auto-fetch.'}
    return visible, plan, request


class SourceReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name).resolve() / 'workspace'
        self.visible, self.plan, self.request = fixture()
        self.sha = review.make_workspace(self.root, self.visible, 'fixture-source-review', 'transport_canary')
        self.broker = review.Broker(self.root, self.sha)

    def tearDown(self):
        self.tmp.cleanup()

    def inspect(self):
        self.broker.call('inspect_source_context', {})
        self.broker.call('inspect_source_readiness', {})

    def plan_result(self):
        return review.validate_plan(self.plan, self.visible, self.visible['evidence.json']['directory_receipts'])

    def test_separate_stage_not_download_permission(self):
        result = self.plan_result()
        self.assertEqual(result['advertised_payload_bytes_not_authority'], 123)
        self.assertTrue(result['objects_require_additional_authority'])
        for key in ('raw_compatibility_verified', 'source_contract_changed_by_submission',
                    'acquisition_admitted', 'execution_admitted'):
            self.assertFalse(result[key])
        self.assertEqual(result['fresh_dates_admitted'], [])

    def test_exact_advertised_fields_not_rounded_or_invented(self):
        for field, value in [('bytes', 124), ('bytes', True), ('path', 'unobserved.parquet'),
                             ('revision', 'main'), ('sha256', 'c' * 64)]:
            with self.subTest(field=field):
                old = copy.deepcopy(self.plan)
                self.plan['objects'][0][field] = value
                with self.assertRaises(ValueError): self.plan_result()
                self.plan = old

    def test_duplicate_objects_cannot_double_count_payload(self):
        self.plan['objects'].append(copy.deepcopy(self.plan['objects'][0]))
        with self.assertRaises(ValueError): self.plan_result()

    def test_empty_objects_allowed_only_as_unexecuted_requirement(self):
        self.plan['objects'] = []
        result = self.plan_result()
        self.assertEqual(result['advertised_payload_bytes_not_authority'], 0)
        self.assertFalse(result['unlisted_transfer_bytes_estimated'])
        self.assertFalse(result['execution_admitted'])

    def test_no_implied_compatibility_or_new_test(self):
        for key, value in [('stage', 'independent_t7_validation'), ('validation_claim', 'fresh'),
                           ('artifact_use', 'final_test'), ('quiet_rows', 'delete_quiet')]:
            old = copy.deepcopy(self.plan); self.plan[key] = value
            with self.assertRaises(ValueError): self.plan_result()
            self.plan = old

    def test_no_added_self_authority_or_unbound_context(self):
        self.plan['download_authorized'] = True
        with self.assertRaises(ValueError): self.plan_result()
        self.plan.pop('download_authorized'); self.plan['context_sha256'] = 'd' * 64
        with self.assertRaises(ValueError): self.plan_result()

    def test_unknown_source_requires_metadata_request_not_fabricated_manifest(self):
        self.plan['source_ids'] = ['unknown/source']
        with self.assertRaises(ValueError): self.plan_result()
        self.assertFalse(review.validate_request(self.request)['automatic_fetch'])

    def test_simulator_is_not_primary_data(self):
        self.plan['source_ids'] = ['synthetic-market-simulator']; self.plan['objects'] = []
        with self.assertRaises(ValueError): self.plan_result()

    def test_dates_and_session_minimum_are_requirements_not_coverage_proof(self):
        for minimum, window in [(19, ['2026-06-01', '2026-06-30']),
                                (20, ['2026-06-01', '2026-06-03']),
                                (True, ['2026-06-01', '2026-06-30']),
                                (20, ['2026-06-30', '2026-06-01'])]:
            self.plan['minimum_complete_sessions'] = minimum; self.plan['requested_window'] = window
            with self.assertRaises(ValueError): self.plan_result()

    def test_field_mapping_uncertainty_required_and_unique(self):
        self.plan['field_mapping'][0]['status'] = 'verified'
        with self.assertRaises(ValueError): self.plan_result()
        self.plan['field_mapping'][0]['status'] = 'unavailable'
        self.plan['field_mapping'].append(copy.deepcopy(self.plan['field_mapping'][0]))
        with self.assertRaises(ValueError): self.plan_result()

    def test_manifest_and_visible_changes_fail(self):
        (self.root / 'readiness.json').write_text('{"changed":true}')
        with self.assertRaises(ValueError): self.broker.call('inspect_source_context', {})

    def test_workspace_symlink_escape_fails(self):
        target = self.root / 'readiness.json'; target.unlink(); target.symlink_to('/etc/hosts')
        with self.assertRaises(OSError): self.broker.call('inspect_source_readiness', {})

    def test_unknown_tool_has_no_file_or_python_execution(self):
        for name in ('download', 'evaluate', 'train', 'read_file', 'execute_python'):
            self.assertNotIn(name, review.ALLOWED_TOOLS)
            with self.assertRaises(ValueError): self.broker.call(name, {})

    def test_canary_never_uses_real_public_network(self):
        self.broker.directory_inspector = lambda *a: self.fail('network should not be invoked')
        with self.assertRaisesRegex(ValueError, 'network unavailable'):
            self.broker.call('inspect_public_source_directory', {'dataset': 'fixture/source', 'revision': 'a' * 40})

    def test_claim_reuse_rejected_after_failed_proposal(self):
        self.plan['validation_claim'] = 'fresh'
        with self.assertRaises(ValueError): self.broker.call('propose_source_plan', {'plan': self.plan})
        self.assertTrue((self.root / 'plans/fixture-plan/failure.json').exists())
        self.plan['validation_claim'] = 'none'
        with self.assertRaises(FileExistsError): self.broker.call('propose_source_plan', {'plan': self.plan})

    def test_successful_plan_cannot_be_replaced(self):
        self.broker.call('propose_source_plan', {'plan': self.plan})
        self.plan['plan_id'] = 'new-selection'
        with self.assertRaisesRegex(ValueError, 'one valid'):
            self.broker.call('propose_source_plan', {'plan': self.plan})

    def test_context_read_required_and_terminal_cannot_continue(self):
        a = {'action': 'defer', 'artifact_id': '', 'reason': 'Synthetic fixture.'}
        with self.assertRaisesRegex(ValueError, 'inspect current'):
            self.broker.call('submit_source_review_decision', a)
        self.inspect(); self.broker.call('submit_source_review_decision', a)
        with self.assertRaisesRegex(ValueError, 'no continuation'):
            self.broker.call('inspect_source_archive', {})
        self.assertTrue(review.assess_activity(self.root, self.sha)['valid'])

    def test_propose_terminal_preserves_exact_claim_and_ack(self):
        from codex_glm_provider import successful_submission
        self.inspect(); self.broker.call('propose_source_plan', {'plan': self.plan})
        reply = self.broker.call('submit_source_review_decision', {'action': 'propose',
            'artifact_id': self.plan['plan_id'], 'reason': 'Metadata fixture, not real selection.'})
        self.assertTrue(reply['submitted']); self.assertGreater(reply['bytes'], 0)
        self.assertFalse(review.assess_activity(self.root, self.sha)['model_authorship_proven'])
        request = {'input': [
            {'type': 'function_call', 'name': 'submit_source_review_decision',
             'namespace': 'mcp__controller_tools', 'call_id': 'call-1', 'arguments': '{}'},
            {'type': 'function_call_output', 'call_id': 'call-1', 'output': canonical(reply)}]}
        self.assertEqual(successful_submission(request, 'submit_source_review_decision'), 'call-1')

    def test_submission_and_post_submission_tampering_rejected(self):
        self.inspect(); self.broker.call('propose_source_plan', {'plan': self.plan})
        path = self.root / 'plans/fixture-plan/result.json'; original = path.read_bytes()
        path.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.broker.call('submit_source_review_decision', {'action': 'propose',
                'artifact_id': self.plan['plan_id'], 'reason': 'Fixture.'})
        path.write_bytes(original)
        self.broker.call('submit_source_review_decision', {'action': 'propose',
            'artifact_id': self.plan['plan_id'], 'reason': 'Fixture.'})
        path.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'changed'): review.assess_activity(self.root, self.sha)

    def test_new_source_metadata_request_can_close_without_fetching(self):
        self.inspect(); result = self.broker.call('request_source_metadata', {'request': self.request})
        self.assertFalse(result['automatic_fetch'])
        self.broker.call('submit_source_review_decision', {'action': 'request_metadata',
            'artifact_id': self.request['request_id'], 'reason': 'Need metadata, not raw files.'})
        self.assertEqual(review.assess_activity(self.root, self.sha)['action'], 'request_metadata')

    def test_source_notes_search_is_honestly_frozen(self):
        result = self.broker.call('search_source_notes', {'query': 'fixture'})
        self.assertEqual(result['mode'], 'frozen_metadata_notes_not_live_web')

    def test_real_stdio_transport_and_terminal_fixture(self):
        requests = [{'jsonrpc': '2.0', 'id': 1, 'method': 'initialize'},
                    {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'}]
        for i, name in enumerate(('inspect_source_context', 'inspect_source_readiness'), 3):
            requests.append({'jsonrpc': '2.0', 'id': i, 'method': 'tools/call',
                'params': {'name': name, 'arguments': {}}})
        requests.append({'jsonrpc': '2.0', 'id': 5, 'method': 'tools/call', 'params': {
            'name': 'submit_source_review_decision', 'arguments': {'action': 'defer',
            'artifact_id': '', 'reason': 'Synthetic stdio fixture, no model authorship.'}}})
        p = subprocess.run([sys.executable, review.__file__, '--workspace', str(self.root),
            '--manifest-sha256', self.sha], input=''.join(canonical(r)+'\n' for r in requests),
            capture_output=True, text=True, timeout=15)
        self.assertEqual(p.returncode, 0, p.stderr)
        responses = [json.loads(line) for line in p.stdout.splitlines()]
        self.assertEqual(len(responses), 5)
        self.assertEqual(responses[1]['result']['tools'], review.TOOLS)
        self.assertFalse(any(r.get('error') or r['result'].get('isError') for r in responses))
        self.assertTrue(review.assess_activity(self.root, self.sha)['valid'])


class PublicMetadataBrokerTests(unittest.TestCase):
    def test_new_directory_metadata_can_inform_plan_but_not_authorize(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / 'workspace'; visible, plan, _ = fixture()
            sha = review.make_workspace(root, visible, 'fixture-net-tools', 'source_review')
            body = json.dumps([{'type': 'file', 'path': 'tape.db.zst', 'oid': 'd'*40, 'size': 99,
                               'lfs': {'oid': 'e'*64, 'size': 99}}]).encode()
            def inspector(dataset, revision, target):
                return metadata_run(dataset, revision, target, getter=lambda _: (body, {}))
            broker = review.Broker(root, sha, directory_inspector=inspector)
            result = broker.call('inspect_public_source_directory', {'dataset': 'new/source', 'revision': 'f'*40})
            self.assertFalse(result['acquisition_admitted'])
            with self.assertRaisesRegex(ValueError, 'duplicate'):
                broker.call('inspect_public_source_directory', {'dataset': 'new/source', 'revision': 'f'*40})
            plan['source_ids'] = ['new/source']; plan['objects'] = [{
                'source_id': 'new/source', 'revision': 'f'*40, 'path': 'tape.db.zst', 'sha256': 'e'*64, 'bytes': 99}]
            result = broker.call('propose_source_plan', {'plan': plan})
            self.assertEqual(result['advertised_payload_bytes_not_authority'], 99)
            self.assertFalse(result['execution_admitted'])
            self.assertFalse((root / 'tape.db.zst').exists())


if __name__ == '__main__':
    unittest.main()
