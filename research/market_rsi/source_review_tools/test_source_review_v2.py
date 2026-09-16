import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import controller_source_review as core
import controller_source_review_v2 as review
from market_rsi import canonical,digest,fresh_json
from test_controller_source_review import fixture


def fixture_v2():
    visible,plan,request=fixture()
    inv={'schema':'public_source_recursive_metadata_review_v1','passed':True,
        'dataset':'fixture/source','revision':'a'*40,'objects':[{'path':'data/day.parquet','type':'file',
            'advertised_bytes':123,'advertised_sha256':'b'*64}],
        'raw_contents_verified':False,'acquisition_admitted':False}
    inv['result_sha256']=digest(inv)
    text='CREATE TABLE fixture (id INTEGER);'
    receipt={'schema':'controller_requested_pinned_source_document_v1','passed':True,
        'dataset':'fixture/source','revision':'a'*40,'name':'schema.sql',
        'document_sha256':hashlib.sha256(text.encode()).hexdigest()}
    receipt['result_sha256']=digest(receipt)
    followup={'schema':'controller_source_metadata_followup_v1','passed':True,
        'source_selected':False,'acquisition_admitted':False,'fresh_test_admitted':False,'sample_files_opened':False,
        'request_id':'fixture-old-request','interface_failure_correction':{'fixture_only':True},
        'joseph_inventory':inv,'pinned_documentation':[{'receipt':receipt,'text':text}]}
    followup['result_sha256']=digest(followup)
    visible['evidence.json']['source_metadata_followup']=followup
    visible['readiness.json']['source_review_interface_version']=2
    plan['objects'][0]['path']='data/day.parquet'
    return visible,plan,request


class V2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve()/'workspace'
        self.visible,self.plan,self.request=fixture_v2()
        self.sha=core.make_workspace(self.root,self.visible,'fixture-source-v2','transport_canary')
        self.b=review.Broker(self.root,self.sha)

    def tearDown(self):self.tmp.cleanup()

    def test_full_schema_and_exact_ids_are_served(self):
        reply=self.b.call('inspect_source_context',{})
        self.assertEqual(reply['source_review_interface_version'],2)
        self.assertIn('bytes',reply['source_plan_json_schema']['properties']['objects']['items']['properties'])
        self.assertIn('fixture/source',reply['known_source_ids'])
        self.assertNotIn('not_yet_wired_into_paid_dispatcher',reply)
        t=next(t for t in review.TOOLS if t['name']=='propose_source_plan')
        self.assertEqual(t['inputSchema']['properties']['plan'],reply['source_plan_json_schema'])

    def test_document_and_file_retrieval_without_raw_access(self):
        docs=self.b.call('search_source_notes',{'query':'schema.sql'})
        self.assertEqual(docs['documents'][0]['text'],'CREATE TABLE fixture (id INTEGER);')
        rows=self.b.call('search_source_notes',{'query':'day.parquet'})
        self.assertEqual(rows['metadata_file_matches'][0]['path'],'data/day.parquet')
        self.assertEqual(rows['matching_file_count'],1)

    def test_projection_explicitly_not_a_root_receipt(self):
        p=review.recursive_projection(self.visible['evidence.json']['source_metadata_followup'])
        self.assertEqual(p['projection_of_schema'],'public_source_recursive_metadata_review_v1')
        self.assertIn('not_root',p['metadata_scope'])
        self.assertEqual(p['objects'][0]['path'],'data/day.parquet')
        self.assertFalse(p['acquisition_admitted'])

    def test_recursive_file_plan_and_first_terminal_still_guarded(self):
        self.b.call('inspect_source_context',{});self.b.call('inspect_source_readiness',{})
        r=self.b.call('propose_source_plan',{'plan':self.plan})
        self.assertEqual(r['advertised_payload_bytes_not_authority'],123)
        self.assertFalse(r['acquisition_admitted'])
        self.b.call('submit_source_review_decision',{'action':'propose','artifact_id':self.plan['plan_id'],
            'reason':'Synthetic fixture, no model or acquisition.'})
        self.assertTrue(review.assess_activity(self.root,self.sha)['valid'])
        with self.assertRaisesRegex(ValueError,'no continuation'):self.b.call('inspect_source_context',{})

    def test_old_workspace_cannot_silently_become_v2(self):
        visible,_,_=fixture();root=Path(self.tmp.name).resolve()/'old'
        sha=core.make_workspace(root,visible,'fixture-old','transport_canary')
        with self.assertRaisesRegex(ValueError,'explicit v2'):review.Broker(root,sha)

    def test_document_and_inventory_tampering_rejected_even_followup_resealed(self):
        for kind in ('document','inventory'):
            f=copy.deepcopy(self.visible['evidence.json']['source_metadata_followup'])
            if kind=='document':f['pinned_documentation'][0]['text']='changed'
            else:f['joseph_inventory']['objects'][0]['advertised_bytes']=1
            f['result_sha256']=digest({k:v for k,v in f.items() if k!='result_sha256'})
            with self.subTest(kind=kind),self.assertRaises(ValueError):review.validate_followup(f)

    def test_network_still_unavailable_in_fixture(self):
        with self.assertRaisesRegex(ValueError,'network unavailable'):
            self.b.call('inspect_public_source_directory',{'dataset':'fixture/source','revision':'a'*40})

    def test_unknown_download_tool_rejected(self):
        with self.assertRaisesRegex(ValueError,'unknown tool'):self.b.call('download',{})

    def test_real_stdio_advertises_v2_complete_schema(self):
        requests=[{'jsonrpc':'2.0','id':1,'method':'initialize'},
                  {'jsonrpc':'2.0','id':2,'method':'tools/list'},
                  {'jsonrpc':'2.0','id':3,'method':'tools/call',
                   'params':{'name':'search_source_notes','arguments':{'query':'schema.sql'}}}]
        p=subprocess.run([sys.executable,review.__file__,'--workspace',str(self.root),
            '--manifest-sha256',self.sha],input=''.join(canonical(r)+'\n' for r in requests),
            capture_output=True,text=True,timeout=20)
        self.assertEqual(p.returncode,0,p.stderr)
        replies=[json.loads(x) for x in p.stdout.splitlines()]
        self.assertEqual(replies[0]['result']['serverInfo']['version'],'2')
        self.assertEqual(replies[1]['result']['tools'],review.TOOLS)
        self.assertFalse(replies[2]['result']['isError'])


if __name__=='__main__':unittest.main()
