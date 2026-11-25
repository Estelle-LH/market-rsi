"""Synthetic receipts/temp ledgers; grant and known-incident pins are explicit seams.

No production ledger, actual fee action, source execution, provider or QA reads.
Real receipt hashing/canonical ownership, shared-lock/transaction and once-only
booking execute against temporary originals; no actual30 inspection claimed.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import earnings_population_reconcile as m
from edgar_forecast_budget import BudgetStop
import test_earnings_population_reconcile as fixtures


class SourceGuardOperator(unittest.TestCase):
    save = fixtures.Conservative400Operator.save
    refresh = fixtures.Conservative400Operator.refresh

    def setUp(self):
        fixtures.Conservative400Operator.setUp(self)
        ident = m.SOURCE_GUARD_ID
        self.runtime.update(id=ident, root=str(self.root/'attempts'/ident),
            source_commit=m.SOURCE_GUARD_COMMIT, rates=dict(api_model='gpt-6.1-sol',
                input='2',cached='0.1',write='2.5',output='10',effort='max'),
            role_efforts=dict(author='high'),
            limits=dict(author=dict(max_input_tokens=96000,max_output_tokens=49152,wall_seconds=1200)))
        old='/private/tmp/market-rsi-earnings-overnight-FGRfBI/checkout'
        self.runtime['sources']={name:dict(path=old+'/'+name,sha256='a'*64)for name in m.SOURCE_GUARD_MISSING}
        self.runtime['sources']['clock']=self.runtime['sources']['tools/earnings_clock.py']
        self.slot=Path(self.runtime['root'])/'roles/author-01'
        self.runtime['slots']={'author':[str(self.slot)]}
        self.db.execute("UPDATE requests SET id=?,reserved=? WHERE id='uncertain'",(m.SOURCE_GUARD_REQUEST,599450000))
        self.refresh()
        self.request=dict(request_id=m.SOURCE_GUARD_REQUEST,reserved_nano_usd=599450000,
            payload=dict(model='gpt-6.1-sol',reasoning={'effort':'high'},input=[]))
        runtime=self.save(self.root/'inputs'/ident/'runtime-reviewed.json',self.runtime)
        owner=self.save(self.ledger.parent/'.capacity-runtime-claims'/(hashlib.sha256(ident.encode()).hexdigest()+'.result.json'),
            dict(runtime=runtime,status='FAILED_NO_RETRY',retry_allowed=False,error_type='LoopHalted',
                budget_summary=dict(blocked=True,cap_usd=400,model_cap_usd=100,unresolved_reserved_usd=.59945,
                    charged_upper_bound_usd=self.proof['ledger_before']['charged_nano_usd']/1e9,
                    generation_requests_reserved=self.proof['ledger_before']['request_count'])))
        request=self.save(self.slot/'08-request.json',self.request)
        self.stem=self.slot/'http-00000000-0000-0000-0000-000000000001'
        intent=self.save(self.stem.with_suffix('.intent.json'),dict(endpoint='/v1/responses',complete_reservation=self.request,
            request_receipt_sha256=request['sha256'],budget_request_id=m.SOURCE_GUARD_REQUEST,retry_allowed=False,
            payload=dict(self.request['payload'],max_output_tokens=49152,service_tier='default',store=False)))
        failure=self.save(self.stem.with_suffix('.failed.json'),dict(exception_type='ValueError',retry_allowed=False))
        context=self.save(Path(self.runtime['root'])/'context-author.json',dict(schema='earnings_capacity_author_transport_v2',
            source_commit=self.runtime['source_commit'],root=self.runtime['root'],slots=self.runtime['slots']['author'],
            rates=dict(self.runtime['rates'],effort='high'),limits=self.runtime['limits']['author']))
        identity=self.save(self.slot/'identity.json',dict(context=context,source_commit=self.runtime['source_commit'],max_turns=8))
        result=self.save(self.slot/'result.json',dict(status='FAILED_NO_RETRY',error_type='ValueError',retry_allowed=False,
            turns=8,final_numbered_response='07-response.json',wall_seconds=452.1))
        previous=self.save(self.slot/'07-response.json',dict(status='completed'))
        count=self.save(self.slot/'08-count.json',dict(input_tokens=43172))
        self.raw=dict(id='resp_fixture',object='response',status='completed',error=None,model='gpt-6.1-sol',service_tier='default',
            created_at=100,completed_at=200,usage=dict(input_tokens=43172,output_tokens=17686,total_tokens=60858,
                input_tokens_details=dict(cached_tokens=0,cache_write_tokens=43097),output_tokens_details=dict(reasoning_tokens=10225)),
            output=[dict(type='reasoning',summary=[]),dict(type='message',role='assistant',status='completed',
                content=[dict(type='output_text',text='public fixture final only')])])
        raw=self.save(self.stem.with_suffix('.raw.bin'),self.raw)
        boundary=self.save(Path(self.runtime['root'])/'role-validation/author-01.json',
            dict(schema='earnings_population_role_validation_v1',runtime=runtime,role='author',slot=str(self.slot),
                entry_full_audit='PASS',exit_full_audit='FAILED',audit_error='ValueError',original_error='RuntimeError',
                output_accepted=False,retry_allowed=False))
        incident=self.save(self.root/'ROOT-SOURCE-INCIDENT30.json',dict(schema='earnings_owned_source_incident_v1',
            attempt=ident,owner='Root',source_commit=m.SOURCE_GUARD_COMMIT,checkout=old,true_exit_code=1,
            failure_class='POST_RESPONSE_SOURCE_INTEGRITY_FAILURE',source_inventory=dict(bound_names=133,
                unchanged_present_names=124,changed_present_names=[],missing_names=9,missing_unique_files=list(m.SOURCE_GUARD_MISSING))))
        self.evidence=dict(schema=m.SOURCE_GUARD_SCHEMA,mode=m.SOURCE_GUARD_MODE,id=ident,runtime=runtime,owner_result=owner,
            request=request,http_intent=intent,http_failure=failure,ledger_before=self.proof['ledger_before'],
            actual_charge_known=False,retry_allowed=False,raw_response=raw,received_usage=self.raw['usage'],
            input_count=count,role_identity=identity,role_result=result,last_numbered_response=previous,
            source_incident=incident,role_boundary=boundary)
        self.closure=dict(runtime=runtime,source_commit=m.SOURCE_GUARD_COMMIT,original_owner={'binding':owner},
            accounting={'snapshot':self.proof['ledger_before']},
            source_verification=dict(missing_binding_names=sorted(('clock',*m.SOURCE_GUARD_MISSING))),
            transport_verification=dict(raw_received_unaccepted=dict(binding=request,request_id=m.SOURCE_GUARD_REQUEST,
                physical=dict(intent=intent,raw=raw,failure={'binding':failure},numbered_response=None,sidecar=None))),
            per_role={'author-01':{'result_binding':result}})
        self.evidence['closure_audit']=self.save(self.root/'CUMULATIVE400-LIVE30-CLOSURE-AUDIT.json',self.closure)
        # Synthetic originals cannot have the real immutable incident hashes.
        self.pins={key:self.evidence[key]['sha256']for key in m.SOURCE_GUARD_PINS}
        self.stack.enter_context(patch.object(m,'SOURCE_GUARD_PINS',self.pins))
        self.stack.enter_context(patch.object(m,'SOURCE_GUARD_PREFIX',deepcopy(self.proof['ledger_before'])))

    def bound(self):
        return self.save(self.root/('FEE-EVIDENCE-'+self.runtime['id']+'.json'),self.evidence)

    def read(self,key):
        return json.loads(Path(self.evidence[key]['path']).read_bytes())

    def change(self,key,value,*,retie=True):
        self.evidence[key]=self.save(Path(self.evidence[key]['path']),value)
        self.pins[key]=self.evidence[key]['sha256']
        if retie and key!='closure_audit':
            self.closure.update(runtime=self.evidence['runtime'],original_owner={'binding':self.evidence['owner_result']})
            self.closure['per_role']['author-01']['result_binding']=self.evidence['role_result']
            row=self.closure['transport_verification']['raw_received_unaccepted']
            row['binding']=self.evidence['request'];row['physical'].update(intent=self.evidence['http_intent'],
                raw=self.evidence['raw_response'],failure={'binding':self.evidence['http_failure']})
            self.change('closure_audit',self.closure,retie=False)

    def assert_blocked(self):
        self.assertEqual(self.db.execute('SELECT blocked FROM config').fetchone(),(1,))
        self.assertEqual(self.db.execute('SELECT charged,status FROM requests WHERE id=?',(m.SOURCE_GUARD_REQUEST,)).fetchone(),(0,'uncertain'))
        self.assertEqual(self.db.execute('SELECT count(*) FROM reconciliations').fetchone(),(0,))

    def test_readonly_then_full_ceiling_once_preserves_all_originals_and_caps(self):
        bound=self.bound();oldrows=self.db.execute('SELECT * FROM requests WHERE id!=?',(m.SOURCE_GUARD_REQUEST,)).fetchall()
        originals={key:Path(b['path']).read_bytes()for key,b in self.evidence.items()if isinstance(b,dict)and set(b)=={'path','sha256'}}
        changes=self.db.total_changes
        proof,runtime,request=m.inspect_source_guard_received_raw_evidence(bound)
        self.assertEqual(self.db.total_changes,changes);self.assertEqual(request,self.request)
        result=m.reconcile_source_guard_received_raw_at_ceiling(bound)
        self.assertEqual(result['conservative_charge_nano_usd'],599450000)
        self.assertNotEqual(result['conservative_charge_nano_usd'],284790000)
        self.assertEqual(result['mode'],m.SOURCE_GUARD_MODE);self.assertEqual(result['policy'],m.SOURCE_GUARD_POLICY)
        self.assertEqual(result['source_incident'],self.evidence['source_incident'])
        self.assertIs(result['actual_charge_known'],False);self.assertIs(result['provider_usage_received'],True)
        self.assertEqual(result['refund_nano_usd'],0);self.assertIs(result['retry_allowed'],False)
        self.assertEqual(self.db.execute('SELECT * FROM requests WHERE id!=?',(m.SOURCE_GUARD_REQUEST,)).fetchall(),oldrows)
        self.assertEqual(self.db.execute('SELECT cap,model_cap,blocked FROM config').fetchone(),(400000000000,100000000000,0))
        self.assertEqual(self.db.execute('SELECT policy FROM reconciliations').fetchone(),(m.SOURCE_GUARD_POLICY,))
        self.grant.assert_called_once()
        for key,original in originals.items():self.assertEqual(Path(self.evidence[key]['path']).read_bytes(),original)
        self.assertFalse((self.slot/'08-response.json').exists());self.assertFalse(self.stem.with_suffix('.response.json').exists())
        with self.assertRaises(BudgetStop):m.reconcile_source_guard_received_raw_at_ceiling(bound)

    def test_old_routes_never_accept_new_mode_or_valueerror(self):
        for inspect in (m.inspect_evidence,m.inspect_received_raw_evidence):
            with self.assertRaises(ValueError):inspect(self.bound())
        self.evidence.update(schema=m.RECEIVED_SCHEMA,mode=m.RECEIVED_MODE)
        with self.assertRaises(ValueError):m.inspect_received_raw_evidence(self.bound())
        self.evidence['schema']='earnings_population_fee_evidence_v1';self.evidence.pop('mode')
        with self.assertRaises(ValueError):m.inspect_evidence(self.bound())
        self.assert_blocked()

    def test_every_known_pin_and_id_required_before_originals_open(self):
        original=deepcopy(self.evidence)
        for key in self.pins:
            with self.subTest(key=key):
                self.evidence=deepcopy(original);self.evidence[key]['sha256']='f'*64
                with patch.object(m,'_read',wraps=m._read)as reader:
                    with self.assertRaises(ValueError):m.inspect_source_guard_received_raw_evidence(self.bound())
                    self.assertEqual(reader.call_count,1)
        self.evidence=deepcopy(original);self.evidence['id']='edgar-population-20261016-31'
        with self.assertRaises(ValueError):m.inspect_source_guard_received_raw_evidence(self.bound())
        self.assert_blocked()

    def test_foreign_incident_closure_boundary_paths_refuse_before_open(self):
        original=deepcopy(self.evidence)
        for key in ('source_incident','closure_audit','role_boundary','raw_response'):
            with self.subTest(key=key):
                self.evidence=deepcopy(original);self.evidence[key]['path']=str(self.tmp/'foreign.json')
                with self.assertRaises(ValueError):m.inspect_source_guard_received_raw_evidence(self.bound())
        self.assert_blocked()

    def test_bound_bytes_symlinks_and_hardlinks_refuse(self):
        bound=self.bound();path=Path(self.evidence['source_incident']['path']);original=path.read_bytes()
        path.write_bytes(original+b' ')
        with self.assertRaises(ValueError):m.inspect_source_guard_received_raw_evidence(bound)
        path.write_bytes(original);copy=self.tmp/'incident.json';path.rename(copy);path.symlink_to(copy)
        with self.assertRaises(ValueError):m.inspect_source_guard_received_raw_evidence(bound)
        path.unlink();copy.rename(path);os.link(path,self.tmp/'hardlink.json')
        with self.assertRaises(ValueError):m.inspect_source_guard_received_raw_evidence(bound)
        self.assert_blocked()

    def test_incident_semantic_class_inventory_and_source_context_remain_strict(self):
        original=self.read('source_incident')
        variants=[dict(original,failure_class='ARBITRARY_VALUEERROR'),dict(original,source_commit='b'*40),
            dict(original,true_exit_code=True),dict(original,attempt='edgar-population-20261016-31'),
            dict(original,checkout=str(self.tmp)),dict(original,owner='foreign')]
        for key,value in (('missing_unique_files',[]),('missing_names',8),('bound_names',132),('changed_present_names',['foreign'])):
            variant=deepcopy(original);variant['source_inventory'][key]=value;variants.append(variant)
        for variant in variants:
            with self.subTest(variant=variant):
                self.change('source_incident',variant)
                with self.assertRaises(ValueError):m.inspect_source_guard_received_raw_evidence(self.bound())
        self.assert_blocked()

    def test_boundary_cannot_claim_success_or_hide_secondary_original_failure(self):
        original=self.read('role_boundary')
        for key,value in (('entry_full_audit','FAILED'),('exit_full_audit','PASS'),('output_accepted',True),
                ('audit_error','BudgetStop'),('original_error',None),('retry_allowed',True),('role','review')):
            with self.subTest(key=key):
                self.change('role_boundary',dict(original,**{key:value}))
                with self.assertRaises(ValueError):m.inspect_source_guard_received_raw_evidence(self.bound())
        self.assert_blocked()

    def test_closure_joins_cannot_substitute_owner_runtime_raw_or_source_absence(self):
        original=deepcopy(self.closure)
        for name in ('owner','runtime','raw','source','prefix'):
            changed=deepcopy(original)
            if name=='owner':changed['original_owner']['binding']={'path':'foreign','sha256':'a'*64}
            if name=='runtime':changed['runtime']={'path':'foreign','sha256':'a'*64}
            if name=='raw':changed['transport_verification']['raw_received_unaccepted']['physical']['raw']={'path':'foreign','sha256':'a'*64}
            if name=='source':changed['source_verification']['missing_binding_names']=[]
            if name=='prefix':changed['accounting']['snapshot']=dict(self.proof['ledger_before'],charged_nano_usd=0)
            with self.subTest(name=name):
                self.change('closure_audit',changed,retie=False)
                with self.assertRaises(ValueError):m.inspect_source_guard_received_raw_evidence(self.bound())
        self.assert_blocked()

    def test_exact_valueerror_pair_turn_and_last_response_required(self):
        for receipt,key,value in (('http_failure','exception_type','BudgetStop'),('http_failure','exception_type','RuntimeError'),
                ('role_result','error_type','BudgetStop'),('role_result','turns',7),('role_result','turns',True),
                ('role_result','final_numbered_response','06-response.json'),('role_result','status','RUNNING')):
            with self.subTest(receipt=receipt,key=key,value=value):
                original=self.read(receipt);self.change(receipt,dict(original,**{key:value}))
                with self.assertRaises(ValueError):m.inspect_source_guard_received_raw_evidence(self.bound())
                self.change(receipt,original)
        self.assert_blocked()

    def test_complete_raw_usage_model_tier_message_count_and_payload_stay_strict(self):
        variants=[dict(self.raw,status='incomplete'),dict(self.raw,model='foreign'),dict(self.raw,service_tier='flex'),
            dict(self.raw,output=[dict(type='function_call')]),dict(self.raw,usage=dict(self.raw['usage'],input_tokens=True)),
            dict(self.raw,usage=dict(self.raw['usage'],total_tokens=60859)),
            dict(self.raw,usage=dict(self.raw['usage'],input_tokens_details=dict(cached_tokens=0,cache_write_tokens=43173)))]
        for raw in variants:
            with self.subTest(raw=raw):
                self.change('raw_response',raw);self.evidence['received_usage']=raw['usage']
                with self.assertRaises(ValueError):m.inspect_source_guard_received_raw_evidence(self.bound())
        self.change('raw_response',self.raw);self.evidence['received_usage']=self.raw['usage']
        self.change('input_count',{'input_tokens':43171})
        with self.assertRaises(ValueError):m.inspect_source_guard_received_raw_evidence(self.bound())
        self.change('input_count',{'input_tokens':43172})
        original=self.read('http_intent');self.change('http_intent',dict(original,payload={}))
        with self.assertRaises(ValueError):m.inspect_source_guard_received_raw_evidence(self.bound())
        self.assert_blocked()

    def test_any_sidecar_or_numbered_response_and_nonteminal_owner_refused(self):
        for path in (self.slot/'08-response.json',self.stem.with_suffix('.response.json')):
            with self.subTest(path=path):
                path.touch()
                with self.assertRaises(ValueError):m.inspect_source_guard_received_raw_evidence(self.bound())
                path.unlink()
        original=self.read('owner_result');self.change('owner_result',dict(original,status='RUNNING'))
        with self.assertRaises(ValueError):m.inspect_source_guard_received_raw_evidence(self.bound())
        self.assert_blocked()

    def test_fresh_prefix_foreign_liability_wrong_caps_and_oneonce_are_not_bypassed(self):
        bound=self.bound()
        proof,runtime,request=m.inspect_source_guard_received_raw_evidence(bound)
        proof['_binding']=bound
        for query in ("INSERT INTO requests VALUES('foreign','gpt-6.1-sol',1,0,'reserved')",
                "UPDATE config SET cap=200000000000", "UPDATE config SET model_cap=200000000000",
                "UPDATE requests SET charged=charged-1 WHERE id='known'",
                "UPDATE requests SET status='reserved' WHERE id='"+m.SOURCE_GUARD_REQUEST+"'",
                "INSERT INTO reconciliations(request_id) VALUES('"+m.SOURCE_GUARD_REQUEST+"')"):
            with self.subTest(query=query):
                self.db.execute('SAVEPOINT variant');self.db.execute(query)
                try:
                    # Use this existing temp connection while its SAVEPOINT is
                    # open; the public wrapper opens another connection/WAL.
                    with self.assertRaises(BudgetStop):m._book(self.db,proof,runtime,request)
                finally:
                    self.db.execute('ROLLBACK TO variant');self.db.execute('RELEASE variant')
        self.assert_blocked()


if __name__=='__main__':unittest.main()
