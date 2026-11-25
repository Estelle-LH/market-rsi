"""Temporary-ledger proofs only; grant validation is an explicitly mocked seam."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

import earnings_population_reconcile as m
from edgar_forecast_budget import BudgetStop
import test_earnings_population_reconcile as fixtures


class ReceivedRawOperator(unittest.TestCase):
    save = fixtures.Conservative400Operator.save
    refresh = fixtures.Conservative400Operator.refresh
    book = fixtures.Conservative400Operator.book

    def setUp(self):
        fixtures.Conservative400Operator.setUp(self)
        self.runtime.update(rates=dict(api_model='gpt-6.1-sol',input='2',cached='0.1',write='2.5',output='10',effort='max'),
            role_efforts=dict(controller='max'),source_commit='a'*40,
            limits=dict(controller=dict(max_input_tokens=32000,max_output_tokens=16384,wall_seconds=900)))
        self.request.update(reserved_nano_usd=243042500,payload=dict(model='gpt-6.1-sol',reasoning={'effort':'max'},input=[]))
        self.db.execute("UPDATE requests SET reserved=? WHERE id='uncertain'",(243042500,));self.refresh()
        ident=self.runtime['id'];self.slot=Path(self.runtime['root'])/'roles/controller-01'
        self.runtime['slots']={'controller':[str(self.slot)]}
        self.runtime_binding=self.save(self.root/'inputs'/ident/'runtime-reviewed.json',self.runtime)
        owner=self.save(self.ledger.parent/'.capacity-runtime-claims'/(hashlib.sha256(ident.encode()).hexdigest()+'.result.json'),
            dict(runtime=self.runtime_binding,status='FAILED_NO_RETRY',retry_allowed=False,error_type='LoopHalted',
                budget_summary=dict(blocked=True,cap_usd=400,model_cap_usd=100,unresolved_reserved_usd=.2430425,
                    charged_upper_bound_usd=self.proof['ledger_before']['charged_nano_usd']/1e9,
                    generation_requests_reserved=self.proof['ledger_before']['request_count'])))
        request=self.save(self.slot/'08-request.json',self.request)
        self.stem=self.slot/'http-00000000-0000-0000-0000-000000000001'
        intent=self.save(self.stem.with_suffix('.intent.json'),dict(endpoint='/v1/responses',complete_reservation=self.request,
            request_receipt_sha256=request['sha256'],budget_request_id='uncertain',retry_allowed=False,
            payload=dict(self.request['payload'],max_output_tokens=16384,service_tier='default',store=False)))
        failure=self.save(self.stem.with_suffix('.failed.json'),dict(exception_type='BudgetStop',retry_allowed=False))
        context=self.save(Path(self.runtime['root'])/'context-controller.json',dict(schema='earnings_capacity_controller_transport_v1',
            source_commit=self.runtime['source_commit'],root=self.runtime['root'],slots=self.runtime['slots']['controller'],
            rates=self.runtime['rates'],limits=self.runtime['limits']['controller']))
        identity=self.save(self.slot/'identity.json',dict(context=context,source_commit=self.runtime['source_commit'],max_turns=8))
        result=self.save(self.slot/'result.json',dict(status='FAILED_NO_RETRY',error_type='BudgetStop',retry_allowed=False,
            turns=8,final_numbered_response='07-response.json',wall_seconds=900.1))
        previous=self.save(self.slot/'07-response.json',dict(status='completed'))
        count=self.save(self.slot/'08-count.json',dict(input_tokens=31681))
        self.raw=dict(id='resp_fixture',object='response',status='completed',error=None,model='gpt-6.1-sol',service_tier='default',
            created_at=100,completed_at=200,usage=dict(input_tokens=31681,output_tokens=7863,total_tokens=39544,
                input_tokens_details=dict(cached_tokens=0,cache_write_tokens=31606),output_tokens_details=dict(reasoning_tokens=7446)),
            output=[dict(type='reasoning',summary=[]),dict(type='message',role='assistant',status='completed',
                content=[dict(type='output_text',text='fixture final only')])])
        raw=self.save(self.stem.with_suffix('.raw.bin'),self.raw)
        self.evidence=dict(schema=m.RECEIVED_SCHEMA,mode=m.RECEIVED_MODE,id=ident,runtime=self.runtime_binding,owner_result=owner,
            request=request,http_intent=intent,http_failure=failure,ledger_before=self.proof['ledger_before'],
            actual_charge_known=False,retry_allowed=False,raw_response=raw,received_usage=self.raw['usage'],
            input_count=count,role_identity=identity,role_result=result,last_numbered_response=previous)

    def bound(self):
        return self.save(self.root/('FEE-EVIDENCE-'+self.runtime['id']+'.json'),self.evidence)

    def change_receipt(self,key,value):
        self.evidence[key]=self.save(Path(self.evidence[key]['path']),value)

    def test_read_only_inspection_and_distinct_full_ceiling_once_preserve_raw(self):
        bound=self.bound();before=self.db.total_changes;rawbytes=Path(self.evidence['raw_response']['path']).read_bytes()
        proof,runtime,request=m.inspect_received_raw_evidence(bound)
        self.assertEqual(self.db.total_changes,before);self.assertEqual(request,self.request)
        result=m.reconcile_received_raw_at_ceiling(bound)
        self.assertEqual(result['conservative_charge_nano_usd'],243042500)
        self.assertEqual(result['policy'],m.RECEIVED_POLICY);self.assertEqual(result['mode'],m.RECEIVED_MODE)
        self.assertFalse(result['actual_charge_known']);self.assertEqual(result['refund_nano_usd'],0)
        self.assertEqual(self.db.execute('SELECT policy FROM reconciliations').fetchone(),(m.RECEIVED_POLICY,))
        self.assertEqual(Path(self.evidence['raw_response']['path']).read_bytes(),rawbytes)
        self.assertFalse((self.slot/'08-response.json').exists());self.assertFalse(self.stem.with_suffix('.response.json').exists())
        with self.assertRaises(BudgetStop):m.reconcile_received_raw_at_ceiling(bound)

    def test_legacy_route_still_refuses_new_schema_and_received_raw(self):
        with self.assertRaises(ValueError):m.inspect_evidence(self.bound())
        self.evidence['schema']='earnings_population_fee_evidence_v1';self.evidence.pop('mode')
        with self.assertRaises(ValueError):m.inspect_evidence(self.bound())
        with self.assertRaises(ValueError):m.inspect_received_raw_evidence(self.bound())

    def test_any_existing_response_refuses_distinct_route(self):
        for path in (self.slot/'08-response.json',self.stem.with_suffix('.response.json')):
            with self.subTest(path=path.name):
                path.touch()
                with self.assertRaises(ValueError):m.inspect_received_raw_evidence(self.bound())
                path.unlink()

    def test_changed_binding_or_foreign_raw_path_refused(self):
        bound=self.bound();Path(self.evidence['raw_response']['path']).write_bytes(b'{}')
        with self.assertRaises(ValueError):m.inspect_received_raw_evidence(bound)
        self.evidence['raw_response']=self.save(self.tmp/'foreign.raw.bin',self.raw)
        with self.assertRaises(ValueError):m.inspect_received_raw_evidence(self.bound())

    def test_status_model_tier_message_and_malformed_usage_refused(self):
        variants=[('status','incomplete'),('error',{'code':'fixture'}),('model','foreign'),('service_tier','flex'),
            ('output',[]),('output',[dict(type='function_call')]),('completed_at',99),('usage',[])]
        variants += [('usage',dict(self.raw['usage'],**{key:value})) for key,value in (
            ('input_tokens',True),('output_tokens',-1),('total_tokens',39545),('input_tokens_details',[]),
            ('input_tokens_details',dict(cached_tokens=31682)),('output_tokens_details',dict(reasoning_tokens=7864)))]
        for key,value in variants:
            with self.subTest(key=key,value=value):
                raw=deepcopy(self.raw);raw[key]=value;self.change_receipt('raw_response',raw);self.evidence['received_usage']=raw['usage']
                with self.assertRaises(ValueError):m.inspect_received_raw_evidence(self.bound())

    def test_public_usage_copy_and_count_or_reservation_drift_refused(self):
        self.evidence['received_usage']=dict(self.raw['usage'],total_tokens=1)
        with self.assertRaises(ValueError):m.inspect_received_raw_evidence(self.bound())
        self.evidence['received_usage']=deepcopy(self.raw['usage'])
        self.evidence['received_usage']['input_tokens_details']['cached_tokens']=False
        with self.assertRaises(ValueError):m.inspect_received_raw_evidence(self.bound())
        self.evidence['received_usage']=self.raw['usage'];self.change_receipt('input_count',dict(input_tokens=31680))
        with self.assertRaises(ValueError):m.inspect_received_raw_evidence(self.bound())

    def test_nonterminal_role_wrong_turn_last_response_source_or_context_refused(self):
        for key,value in (('status','RUNNING'),('error_type','ValueError'),('turns',True),('turns',7),('final_numbered_response','06-response.json')):
            with self.subTest(key=key):
                result=dict(status='FAILED_NO_RETRY',error_type='BudgetStop',retry_allowed=False,turns=8,final_numbered_response='07-response.json')
                result[key]=value;self.change_receipt('role_result',result)
                with self.assertRaises(ValueError):m.inspect_received_raw_evidence(self.bound())

    def test_physical_payload_reservation_failure_and_owner_tampering_refused(self):
        for receipt,key,value in (('http_intent','payload',{}),('http_intent','budget_request_id','foreign'),
                ('http_failure','exception_type','ValueError'),('owner_result','status','RUNNING')):
            with self.subTest(receipt=receipt,key=key):
                original=json.loads(Path(self.evidence[receipt]['path']).read_text());changed=dict(original,**{key:value})
                self.change_receipt(receipt,changed)
                with self.assertRaises(ValueError):m.inspect_received_raw_evidence(self.bound())
                self.change_receipt(receipt,original)

    def test_original_context_and_raw_single_message_shape_remain_strict(self):
        identity=json.loads(Path(self.evidence['role_identity']['path']).read_text())
        original=json.loads(Path(identity['context']['path']).read_text())
        for key,value in (('source_commit','b'*40),('slots',[]),('rates',{}),('limits',{}),('schema','foreign')):
            with self.subTest(key=key):
                context=dict(original,**{key:value});identity['context']=self.save(Path(identity['context']['path']),context)
                self.change_receipt('role_identity',identity)
                with self.assertRaises(ValueError):m.inspect_received_raw_evidence(self.bound())
        identity['context']=self.save(Path(identity['context']['path']),original);self.change_receipt('role_identity',identity)
        for output in ([self.raw['output'][-1]]*2,[dict(self.raw['output'][-1],role='user')],
                [dict(self.raw['output'][-1],content=[dict(type='refusal',refusal='fixture')])]):
            with self.subTest(output=output):
                self.change_receipt('raw_response',dict(self.raw,output=output))
                with self.assertRaises(ValueError):m.inspect_received_raw_evidence(self.bound())

    def test_foreign_pending_or_changed_prefix_keeps_original_block(self):
        bound=self.bound();self.db.execute("INSERT INTO requests VALUES('foreign','gpt-6.1-sol',1,0,'reserved')")
        with self.assertRaises(BudgetStop):m.reconcile_received_raw_at_ceiling(bound)
        self.evidence['ledger_before']=m.history_snapshot(self.db)
        owner=json.loads(Path(self.evidence['owner_result']['path']).read_text());owner['budget_summary']['generation_requests_reserved']+=1
        self.change_receipt('owner_result',owner)
        with self.assertRaises(BudgetStop):m.reconcile_received_raw_at_ceiling(self.bound())
        self.assertEqual(self.db.execute('SELECT blocked FROM config').fetchone(),(1,))
        self.assertEqual(self.db.execute("SELECT charged,status FROM requests WHERE id='uncertain'").fetchone(),(0,'uncertain'))


if __name__=='__main__':unittest.main()
