import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import controller_design as design
from controller_activity_log import read_activity_events
from market_rsi import canonical, digest, file_hash
from test_independent_validation import fixture


def visible_fixture():
    proposal, context, _, _ = fixture()
    plan = {'fixture': 'metadata-only; not a real model'}
    source = {'schema': 'metadata_fixture_not_a_real_source'}
    source['contract_sha256'] = digest(source)
    context['source_contract_sha256'] = source['contract_sha256']
    context['selected_plan_sha256'] = digest(plan)
    context['context_sha256'] = digest({k: v for k, v in context.items() if k != 'context_sha256'})
    proposal['context_sha256'] = context['context_sha256']
    proposal['source_contract_sha256'] = source['contract_sha256']
    visible = {'context.json': context, 'source-contract.json': source, 'selected-plan.json': plan,
               'readiness.json': {'execution_admitted': False}, 'inventory.json': {'fixture': True},
               'exposure.json': {'exposure_audit_complete': False}, 'archive.json': {'fixture': True},
               'literature.json': {'papers': [{'title': 'Fixture note only'}]},
               'limits.json': {'max_tool_calls': 32, 'max_successful_plans': 1,
                   'max_successful_data_requests': 1, 'max_claims_per_kind': 4,
                   'authorized_download_headroom_bytes': 0, 'vendor_purchase_authorized': False,
                   'execution_tools_present': False}}
    request = {'request_id': 'fixture-request', 'context_sha256': context['context_sha256'],
               'source_contract_sha256': source['contract_sha256'], 'minimum_sessions': 20,
               'earliest_utc_date': '2026-06-01', 'latest_utc_date': '2026-06-30',
               'required_fields': ['fixture_source_field'], 'max_new_download_bytes': 1000000,
               'max_vendor_spend_usd': '10', 'reason': 'Fixture request, no actual acquisition.',
               'limitations': 'No real data or controller authorship.'}
    return visible, proposal, request


class ControllerDesignTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'workspace'
        self.visible, self.plan, self.request = visible_fixture()
        design.make_workspace(self.root, self.visible, 'fixture-session', 'transport_canary')
        self.broker = design.Broker(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def inspect(self):
        self.broker.call('inspect_validation_context', {})
        self.broker.call('inspect_validation_readiness', {})

    def test_tool_inventory_has_no_execution_or_arbitrary_file_tools(self):
        self.assertNotIn('execute_python', design.ALLOWED_TOOLS)
        self.assertNotIn('read_file', design.ALLOWED_TOOLS)
        self.assertNotIn('download', design.ALLOWED_TOOLS)
        with self.assertRaisesRegex(ValueError, 'unknown'):
            self.broker.call('read_file', {'path': '/tmp/not-read'})

    def test_plan_submission_is_not_execution(self):
        self.inspect()
        r = self.broker.call('propose_validation_plan', {'proposal': self.plan})
        self.assertFalse(r['execution_admitted'])
        r = self.broker.call('submit_validation_decision', {'action': 'propose',
            'artifact_id': self.plan['proposal_id'], 'reason': 'Fixture policy only.'})
        self.assertFalse(r['execution_admitted'])
        self.assertTrue(design.assess_activity(self.root)['valid'])
        self.assertFalse(design.assess_activity(self.root)['model_authorship_proven_by_this_audit'])

    def test_request_never_authorizes_purchase_or_download(self):
        r = self.broker.call('request_validation_data', {'request': self.request})
        self.assertTrue(r['new_authority_needed'])
        self.assertFalse(r['download_authorized'])
        self.assertFalse(r['purchase_authorized'])
        self.assertFalse(r['execution_admitted'])

    def test_defer_with_data_requirement(self):
        self.inspect()
        self.broker.call('request_validation_data', {'request': self.request})
        self.broker.call('submit_validation_decision', {'action': 'defer',
            'artifact_id': self.request['request_id'], 'reason': 'Data missing, not a test result.'})
        self.assertEqual(design.assess_activity(self.root)['action'], 'defer')

    def test_plain_defer_is_valid_but_terminal(self):
        self.inspect()
        self.broker.call('submit_validation_decision', {'action': 'defer',
            'artifact_id': '', 'reason': 'Capability unavailable.'})
        with self.assertRaisesRegex(ValueError, 'already submitted'):
            self.broker.call('inspect_validation_context', {})

    def test_terminal_reply_matches_unchanged_provider_handshake(self):
        from codex_glm_provider import successful_submission
        self.inspect()
        reply = self.broker.call('submit_validation_decision', {'action': 'defer',
            'artifact_id': '', 'reason': 'Synthetic transport compatibility check.'})
        self.assertEqual(reply['bytes'], (self.root / design.DECISION).stat().st_size)
        request = {'input': [
            {'type': 'function_call', 'call_id': 'fixture-submit',
             'namespace': 'mcp__controller_tools', 'name': 'submit_validation_decision'},
            {'type': 'function_call_output', 'call_id': 'fixture-submit',
             'output': [{'type': 'input_text', 'text': canonical(reply)}]}]}
        self.assertEqual(successful_submission(request, 'submit_validation_decision'), 'fixture-submit')
        del reply['bytes']
        request['input'][1]['output'][0]['text'] = canonical(reply)
        self.assertIsNone(successful_submission(request, 'submit_validation_decision'))

    def test_inspections_required_before_terminal(self):
        with self.assertRaisesRegex(ValueError, 'inspect context'):
            self.broker.call('submit_validation_decision', {'action': 'defer',
                'artifact_id': '', 'reason': 'Not yet inspected.'})

    def test_failure_claim_cannot_be_reused(self):
        bad = copy.deepcopy(self.plan); bad['utc_dates'] = bad['utc_dates'][:1]
        with self.assertRaises(ValueError):
            self.broker.call('propose_validation_plan', {'proposal': bad})
        target = self.root / 'plans' / self.plan['proposal_id']
        self.assertTrue((target / 'claim.json').is_file())
        self.assertTrue((target / 'failure.json').is_file())
        with self.assertRaises(FileExistsError):
            self.broker.call('propose_validation_plan', {'proposal': self.plan})
        self.assertFalse((target / 'result.json').exists())

    def test_one_successful_plan_only(self):
        self.broker.call('propose_validation_plan', {'proposal': self.plan})
        self.plan['proposal_id'] = 'second-plan'
        with self.assertRaisesRegex(ValueError, 'one successful'):
            self.broker.call('propose_validation_plan', {'proposal': self.plan})

    def test_data_request_wrong_source_rejected(self):
        self.request['source_contract_sha256'] = 'a' * 64
        with self.assertRaisesRegex(ValueError, 'compatibility'):
            self.broker.call('request_validation_data', {'request': self.request})

    def test_impossible_date_window_rejected(self):
        self.request['latest_utc_date'] = '2026-06-05'
        with self.assertRaisesRegex(ValueError, 'cannot contain'):
            self.broker.call('request_validation_data', {'request': self.request})

    def test_old_dates_rejected(self):
        self.request['earliest_utc_date'] = '2026-05-14'
        with self.assertRaisesRegex(ValueError, 'opened history'):
            self.broker.call('request_validation_data', {'request': self.request})

    def test_frozen_file_change_detected(self):
        (self.root / 'inventory.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'frozen metadata'):
            self.broker.call('inspect_validation_readiness', {})

    def test_manifest_rehash_does_not_hide_mid_session_mutation(self):
        (self.root / 'inventory.json').write_text('{}')
        m = design.load(self.root / 'workspace.json')
        m['files']['inventory.json'] = file_hash(self.root / 'inventory.json')
        (self.root / 'workspace.json').write_text(canonical(m))
        with self.assertRaisesRegex(ValueError, 'manifest changed'):
            self.broker.call('inspect_validation_context', {})

    def test_claim_tampering_detected_at_terminal(self):
        self.inspect()
        self.broker.call('request_validation_data', {'request': self.request})
        path = self.root / 'data-requests' / self.request['request_id'] / 'claim.json'
        path.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'claim changed'):
            self.broker.call('submit_validation_decision', {'action': 'defer',
                'artifact_id': self.request['request_id'], 'reason': 'Fixture.'})

    def test_extra_tool_args_cannot_inject_runner_proofs(self):
        with self.assertRaisesRegex(ValueError, 'unexpected tool'):
            self.broker.call('inspect_validation_context', {'exposure_audit_complete': True})

    def test_catalog_search_is_not_reported_as_live(self):
        r = self.broker.call('search_public_literature', {'query': 'fixture'})
        self.assertEqual(r['mode'], 'frozen_catalog_not_live_search')

    def test_real_stdio_handshake_and_terminal_no_provider(self):
        messages = [{'jsonrpc': '2.0', 'id': 1, 'method': 'initialize'},
                    {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'}]
        for i, name in enumerate(('inspect_validation_context', 'inspect_validation_readiness'), 3):
            messages.append({'jsonrpc': '2.0', 'id': i, 'method': 'tools/call',
                             'params': {'name': name, 'arguments': {}}})
        messages.append({'jsonrpc': '2.0', 'id': 5, 'method': 'tools/call', 'params': {
            'name': 'submit_validation_decision', 'arguments': {'action': 'defer', 'artifact_id': '',
            'reason': 'Transport fixture; not a real controller decision.'}}})
        child = subprocess.run([sys.executable, str(Path(design.__file__)), '--workspace', str(self.root)],
            input=''.join(canonical(m) + '\n' for m in messages), capture_output=True, text=True, timeout=15)
        self.assertEqual(child.returncode, 0, child.stderr)
        responses = [json.loads(line) for line in child.stdout.splitlines()]
        self.assertEqual(len(responses), len(messages))
        self.assertEqual(responses[1]['result']['tools'], design.TOOLS)
        self.assertTrue(all(not r.get('error') and not r['result'].get('isError') for r in responses))
        self.assertTrue(design.assess_activity(self.root)['valid'])
        self.assertEqual(len(read_activity_events(self.root / design.LOG)), 3)


if __name__ == '__main__':
    unittest.main()
