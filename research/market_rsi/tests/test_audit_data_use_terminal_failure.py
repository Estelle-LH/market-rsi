import copy
import unittest
from market_rsi import canonical
from audit_data_use_terminal_failure import check_failure


class TerminalFailureAuditTests(unittest.TestCase):
    def setUp(self):
        self.assessment = dict(valid=False, failed=False, exit_code=0, controller_stage='data_use',
            codex_harness_runtime_unchanged=True, submitted_decision_present=True,
            required_tools_complete=True, terminal_handshake=None, unresolved_accounting=[])
        self.decision = dict(action='select', proposal_id='p1', reason='Diagnostic')
        self.result = dict(submitted=True, action='select', training_admitted=False,
                           materializer_execution_verified=False)
        self.events = [dict(tool='submit_data_use_decision', status='ok',
                            arguments=self.decision, result=self.result)]
        self.request = {'input':[
            dict(type='function_call', name='submit_data_use_decision', call_id='one', arguments=canonical(self.decision)),
            dict(type='function_call_output', call_id='one', output=canonical(self.result))]}
        self.trailing = dict(valid=True, kind='message', tool_names=[])

    def check(self):return check_failure(self.assessment,self.events,self.decision,self.request,self.trailing)

    def test_only_local_canary_is_allowed_and_failure_preserved(self):
        result=self.check()
        self.assertTrue(result['eligible_for_local_materializer_canary'])
        self.assertFalse(result['original_session_valid'])
        self.assertFalse(result['training_admitted'])
        self.assertFalse(result['terminal_handshake_repaired_retroactively'])

    def test_real_model_failure_is_not_reclassified(self):
        self.assessment['failed']=True
        with self.assertRaisesRegex(ValueError,'isolated'):self.check()

    def test_later_tool_activity_blocks_recovery(self):
        self.events.append(dict(tool='inspect_data_readiness',status='ok'))
        with self.assertRaisesRegex(ValueError,'subsequent'):self.check()

    def test_new_model_plan_is_not_accepted(self):
        self.trailing['kind']='function_call';self.trailing['tool_names']=['propose_data_use']
        with self.assertRaisesRegex(ValueError,'terminal text'):self.check()

    def test_mismatched_wire_receipt_blocks_recovery(self):
        self.request['input'][-1]['output']='{}'
        with self.assertRaisesRegex(ValueError,'receipt differs'):self.check()

    def test_original_decision_cannot_be_changed(self):
        self.request['input'][0]['arguments']=canonical({**self.decision,'proposal_id':'new'})
        with self.assertRaisesRegex(ValueError,'exact last'):self.check()


if __name__=='__main__':unittest.main()
