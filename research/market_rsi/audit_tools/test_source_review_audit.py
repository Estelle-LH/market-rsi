import copy
import unittest
from audit_source_review_result import response_calls, match_calls


class TranscriptTests(unittest.TestCase):
    def test_single_terminal_call(self):
        calls=response_calls('<tool_call>mcp__controller_tools__submit_source_review_decision'
            '<arg_key>action</arg_key><arg_value>defer</arg_value>'
            '<arg_key>artifact_id</arg_key><arg_value></arg_value>'
            '<arg_key>reason</arg_key><arg_value>Fixture only</arg_value></tool_call>')
        self.assertEqual(len(calls),1);self.assertEqual(calls[0]['arguments']['action'],'defer')

    def test_parallel_order_is_not_required_but_exact_calls_are(self):
        calls=response_calls('<tool_call>mcp__controller_tools__inspect_source_context</tool_call>'
            '<tool_call>mcp__controller_tools__inspect_source_readiness</tool_call>')
        events=[{'tool':c['name'].removeprefix('mcp__controller_tools__'),'arguments':c['arguments']}
                for c in reversed(calls)]
        match_calls(calls,events,2)
        with self.assertRaisesRegex(ValueError,'transcript'):match_calls(calls,events+events[:1],2)
        changed=copy.deepcopy(events);changed[0]['arguments']={'extra':True}
        with self.assertRaisesRegex(ValueError,'transcript'):match_calls(calls,changed,2)

    def test_unknown_tool_rejected(self):
        with self.assertRaises(ValueError):response_calls('<tool_call>mcp__controller_tools__download</tool_call>')


if __name__=='__main__':unittest.main()
