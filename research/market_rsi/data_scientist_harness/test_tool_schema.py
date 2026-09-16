"""Regression for the real 20260910-02 controller's undocumented item fields."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from data_scientist_harness import fixtures
from data_scientist_harness.broker import Broker, serve, validate_shape


class ToolSchemaTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)/'work'
        self.b=Broker(self.root,fixtures.workspace(self.root))
        output=io.StringIO()
        with patch('sys.stdin',io.StringIO('{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n')),patch('sys.stdout',output):
            serve(self.b)
        self.schemas={t['name']:t['inputSchema'] for t in json.loads(output.getvalue())['result']['tools']}
        self.status=self.b.call('inspect_harness',{})

    def tearDown(self): self.tmp.cleanup()

    def test_actual_served_schema_describes_and_accepts_every_item(self):
        schema=self.schemas['acknowledge_current_findings']['properties']['responses']['items']
        self.assertEqual(set(schema['required']),{'id','handling','next_evidence'})
        self.assertFalse(schema['additionalProperties'])
        # Build from advertised keys, not an undisclosed fixture payload.
        response={key:('fixture-only' if key=='id' else 'synthetic schema test') for key in schema['required']}
        value={'finding_sha256':self.status['finding_sha256'],'responses':[response]}
        validate_shape(value,self.schemas['acknowledge_current_findings'])
        self.assertFalse(self.b.call('acknowledge_current_findings',value)['clears_qa_failures'])

    def test_observed_string_item_is_clear_logged_error_not_attribute_error(self):
        with self.assertRaisesRegex(ValueError,r'responses\[0\]: expected object'):
            self.b.call('acknowledge_current_findings',{'finding_sha256':self.status['finding_sha256'],'responses':['fixture-only']})
        self.assertEqual(self.b.store.records()[-1]['result']['error_type'],'ValueError')

    def test_wrong_keys_name_the_required_keys(self):
        with self.assertRaisesRegex(ValueError,'id, handling, next_evidence'):
            self.b.call('acknowledge_current_findings',{'finding_sha256':self.status['finding_sha256'],
                'responses':[{'id':'fixture-only','response':'wrong'}]})

    def test_other_nested_tools_and_enums_are_advertised(self):
        review=self.schemas['review_feature_set']['properties']
        self.assertEqual(review['profile_records']['items']['type'],'string')
        self.assertEqual(set(review['dispositions']['items']['required']),{'profile_record','reason','risk'})
        self.assertIn('evaluation',self.schemas['record_research']['properties']['layer']['enum'])
        self.assertEqual(self.schemas['submit_research_decision']['properties']['action']['enum'],['select','defer'])
        self.assertIn('infrastructure_failure',self.schemas['reflect_candidate']['properties']['conclusion']['enum'])

    def test_wrong_or_duplicate_ids_still_fail(self):
        with self.assertRaisesRegex(ValueError,'EVERY'):
            self.b.call('acknowledge_current_findings',{'finding_sha256':self.status['finding_sha256'],
                'responses':[{'id':'not-current','handling':'x','next_evidence':'x'}]})

    def test_source_only_defer_format_is_explicit_and_works_without_a_trial(self):
        self.b.call('acknowledge_current_findings',{'finding_sha256':self.status['finding_sha256'],
            'responses':[{'id':'fixture-only','handling':'synthetic','next_evidence':'real source audit'}]})
        with self.assertRaisesRegex(ValueError,'empty string'):
            self.b.call('submit_research_decision',{'action':'defer','trial_id':'invented-plan','reason':'fixture'})
        args=self.status['defer_submission_format'].copy();args['reason']='No empirical data admitted; fixture only.'
        result=self.b.call('submit_research_decision',args)
        self.assertTrue(result['submitted']);self.assertIsNone(result['selected'])
        self.assertFalse((self.root/'trials').exists())

    def test_wrong_research_reference_error_names_the_needed_tool(self):
        with self.assertRaisesRegex(ValueError,'expected read_public_source'):
            self.b.store.get('0001','read_public_source')


if __name__=='__main__': unittest.main()
