"""Inert origin/physical/prefix tests, not a production admission or live replay."""
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import earnings_population_controller_import as m
import earnings_population_recovery as recovery
from market_rsi import digest


class ImportOriginTests(unittest.TestCase):
    def setUp(self):
        self.tmp=Path(tempfile.mkdtemp()).resolve();self.addCleanup(__import__('shutil').rmtree,self.tmp)
        self.root=self.tmp/'owned';self.attempt=self.root/'attempts'/m.IDENT
        self.ledger=self.tmp/'ledger.sqlite3';self.repo=self.tmp/'repo'
        self.reader=m.history._Reader(self.root,self.ledger,self.repo,m.IDENT)
        self.rates=dict(api_model='gpt-6.1-sol',input='2',cached='0.1',write='2.5',output='10',effort='max')

    def save(self,path,value):
        path.parent.mkdir(parents=True,exist_ok=True);raw=json.dumps(value,sort_keys=True).encode();path.write_bytes(raw)
        return dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest())

    def pair(self,path,value):
        bound=self.save(path,value);self.save(path.with_suffix('.binding.json'),bound);return bound

    def origin(self):
        return dict(population={'stable_id':'stable','explorers':['parent']},feedback={'path':'latest','sha256':'a'*64},
            research_feedback={'score_state':'unscored','results':[]},last_scored_feedback={'path':'oldscore','sha256':'b'*64},
            previous_result={'path':'completed18','sha256':'c'*64},reference_candidate={'reference_only':True},evidence=[],
            recovery_context=dict(mode=recovery.AUTHOR_BASE_CAPACITY,failed_attempt={'path':'failure20','sha256':'d'*64},
                public_failed_delta={'edits':['raw original20']},implementation_base={'source':'base18'},
                input_delivery_diagnosis={'failed_attempt':{'path':'failure21','sha256':'e'*64}}))

    def bundle(self):
        return dict(schema='earnings_population_controller_proposal_import_v1',mode=m.MODE,new_model_called=False,
            failed_attempt={'path':'failure22','sha256':'f'*64},raw_response={'path':'raw22','sha256':'1'*64},
            runtime={'path':'runtime22','sha256':'2'*64},original_prompt={'path':'prompt22','sha256':'3'*64},
            original_decision_public={'axis':'R'},original_feedback_sha256='4'*64,settlement={'path':'settled22','sha256':'5'*64})

    def test_attach_preserves_exact20_patch21_input_diagnosis_pool_scores_and_references(self):
        origin=self.origin();frozen=deepcopy(origin);bundle=self.bundle()
        result=m._attach(origin,bundle,audit={'path':'audit22','sha256':'6'*64})
        self.assertEqual(origin,frozen);self.assertEqual(result['controller_stage_import'],bundle)
        stripped=deepcopy(result);stripped.pop('controller_stage_import');stripped['recovery_context'].pop('controller_delivery_diagnosis')
        self.assertEqual(stripped,origin)
        self.assertEqual(recovery.latest_failed_attempt(result),bundle['failed_attempt'])
        self.assertEqual(recovery.latest_failed_attempt(origin),origin['recovery_context']['input_delivery_diagnosis']['failed_attempt'])
        result['recovery_context']['public_failed_delta']['edits'].append('mutated copy')
        self.assertEqual(origin,frozen)

    def test_attach_never_claims_author_reuse_or_a_new_controller_call(self):
        for key,value in (('mode','foreign'),('new_model_called',True),('schema','foreign')):
            with self.subTest(key=key):
                bundle=self.bundle();bundle[key]=value
                with self.assertRaises(ValueError):m._attach(self.origin(),bundle,audit={})
        origin=self.origin();origin['author_stage_reuse']={'mode':'foreign'}
        with self.assertRaises(ValueError):m._attach(origin,self.bundle(),audit={})

    def test_foreign_or_wrong_exact_failure_refused_before_reader(self):
        from earnings_population_budget import AUTHORIZATION
        valid=dict(path=str(m.resume.OWNED/'attempts'/m.IDENT/'population-run-failure.json'),sha256=m.FAILURE_SHA)
        plan=dict(id='earnings-population-review-recovery-20261016',human_authorization=AUTHORIZATION,recovery_mode=m.MODE,failed_attempt=valid)
        for changed in (dict(valid,path='/foreign/population-run-failure.json'),dict(valid,sha256='0'*64)):
            with patch.object(m.history,'_Reader',side_effect=AssertionError('must not read')):
                with self.assertRaises(ValueError):m.load(changed,root=m.resume.OWNED,ledger=m.resume.LEDGER,repo=m.resume.REPO,plan=plan)
        for key in ('human_authorization','recovery_mode','failed_attempt'):
            changed=dict(plan,**{key:None})
            with patch.object(m.history,'_Reader',side_effect=AssertionError('must not read')):
                with self.assertRaises(ValueError):m.load(valid,root=m.resume.OWNED,ledger=m.resume.LEDGER,repo=m.resume.REPO,plan=changed)

    def physical(self):
        slot=self.attempt/'roles/controller-01';prompt=dict(feedback_sha256='a'*64,active_versions=['stable'])
        runtime=dict(rates=self.rates,limits={'controller':dict(max_input_tokens=32000,max_output_tokens=16384)},role_efforts={'controller':'max'})
        rows=[]
        for i in range(1,9):
            payload=dict(model='gpt-6.1-sol',reasoning={'effort':'max'},input=[dict(role='user',content=json.dumps(prompt))])
            request=dict(request_id=f'fixture-{i}',reserved_nano_usd=163842500,payload=payload)
            bound=self.save(slot/f'{i:02d}-request.json',request);self.save(slot/f'{i:02d}-count.json',dict(input_tokens=1))
            stem=slot/f'http-00000000-0000-0000-0000-{i:012d}'
            self.save(stem.with_suffix('.intent.json'),dict(endpoint='/v1/responses',complete_reservation=request,
                request_receipt_sha256=bound['sha256'],budget_request_id=request['request_id'],retry_allowed=False,
                payload=dict(payload,max_output_tokens=16384,service_tier='default',store=False)))
            if i<8:
                response=dict(status='completed',model='gpt-6.1-sol',service_tier='default',_request_id=f'req_fixture{i}',
                    usage=dict(input_tokens=1,output_tokens=1,total_tokens=2,input_tokens_details=dict(cached_tokens=0)))
                self.save(slot/f'{i:02d}-response.json',response);self.save(stem.with_suffix('.response.json'),response)
                self.save(stem.with_suffix('.raw.bin'),{k:v for k,v in response.items()if k!='_request_id'})
            rows.append(dict(request=bound,request_id=request['request_id'],reserved_nano_usd=163842500,
                charged_nano_usd=12500 if i<8 else 163842500,status='settled'if i<8 else 'settled_upper_bound'))
        return runtime,prompt,rows,dict(request=rows[-1]['request'])

    def test_real_reader_eight_original_physical_requests_without_final_fabrication(self):
        runtime,prompt,rows,proof=self.physical()
        evidence=m._physical(self.reader,runtime,self.attempt,prompt,rows,proof)
        self.assertEqual(len(evidence),45)
        self.assertFalse((self.attempt/'roles/controller-01/08-response.json').exists())

    def test_physical_wrong_prompt_model_usage_charge_or_final_status_refused(self):
        for variant in ('prompt','model','usage','charge','status'):
            with self.subTest(variant=variant):
                runtime,prompt,rows,proof=self.physical()
                if variant=='prompt':prompt['feedback_sha256']='b'*64
                elif variant=='model':runtime['rates']=dict(self.rates,api_model='foreign')
                elif variant=='charge':rows[0]['charged_nano_usd']=0
                elif variant=='status':rows[-1]['status']='uncertain'
                else:
                    p=self.attempt/'roles/controller-01/01-response.json';value=json.loads(p.read_text());value['usage']['input_tokens']=True
                    self.save(p,value)
                with self.assertRaises(ValueError):m._physical(self.reader,runtime,self.attempt,prompt,rows,proof)

    def prefix(self):
        path=self.attempt/'loop';path.mkdir(parents=True,exist_ok=True);(path/'.loop.lock').touch()
        source={k:dict(path=str(self.repo/k),sha256='a'*64)for k in (m.history.DRIVER,'tools/earnings_population_loop.py',
            'tools/earnings_population_run.py','tools/earnings_population_services.py','tools/earnings_population_campaign.py')}
        population={'fixture':'state'};bound=self.save(self.root/'inputs'/m.IDENT/'initial.json',population)
        runtime=dict(companies=['CIK0000017313'],initial_population=bound,sources=source);study=dict(campaign={'path':'fixturecampaign','sha256':'b'*64})
        seed=dict(companies=runtime['companies'],population=population);handlers={}
        for stage in m.history.STAGES:
            handlers[stage]=dict(stage=stage,adapter=source['tools/earnings_population_loop.py'],
                admission={'function':'execute.<locals>.admit','module':source['tools/earnings_population_run.py']},
                services={r:{'function':'Services.'+r,'module':source['tools/earnings_population_services.py']}for r in ('controller','author','review','forecast')},
                campaign_policy=source['tools/earnings_population_campaign.py'],campaign=study['campaign'])
        manifest=dict(schema='feedback_linked_loop_v1',seed=seed,seed_sha256=digest(seed),max_rounds=1,
            driver_source_sha256=source[m.history.DRIVER]['sha256'],handler_identity=handlers)
        mb=self.pair(path/'manifest.json',manifest);outputs={}
        for stage in ('input','controller'):
            current=dict(round_index=1,seed=seed,previous_result=seed,previous_feedback_sha256=digest(seed),outputs=outputs)
            claim=self.save(path/f'round-0001-{stage}.claim.json',dict(round_index=1,stage=stage,context_sha256=digest(current),
                manifest_sha256=mb['sha256'],previous_feedback_sha256=digest(seed)))
            if stage=='input':
                output=dict(packet=self.save(self.attempt/'packet.json',{'fixture':'packet'}),artifacts=[])
                self.pair(path/f'round-0001-{stage}.done.json',dict(claim_sha256=claim['sha256'],output=output,output_sha256=digest(output)))
                outputs[stage]=output
            else:self.save(path/f'round-0001-{stage}.failed.json',dict(claim_sha256=claim['sha256'],exception_type='RuntimeError',retry_allowed=False))
        return runtime,study,seed,outputs['input']

    def test_real_original_prefix_shape_accepts_only_inputdone_controllerfailed(self):
        runtime,study,seed,output=self.prefix()
        actual_seed,actual_output,evidence=m._prefix(self.reader,runtime,study,self.attempt)
        self.assertEqual((actual_seed,actual_output),(seed,output));self.assertEqual(len(evidence),5)
        self.save(self.attempt/'loop/round-0001-controller.done.json',{})
        with self.assertRaises(ValueError):m._prefix(self.reader,runtime,study,self.attempt)

    def test_changed_claim_or_failed_stage_receipt_is_rejected(self):
        runtime,study,_,_=self.prefix();p=self.attempt/'loop/round-0001-controller.failed.json'
        value=json.loads(p.read_text());value['retry_allowed']=True;self.save(p,value)
        with self.assertRaises(ValueError):m._prefix(self.reader,runtime,study,self.attempt)

    def settlement(self):
        from earnings_population_reconcile import RECEIVED_MODE,RECEIVED_POLICY
        runtime,prompt,rows,proof=self.physical();runtime.update(baseline={},budget_amendment={'fixture':'grant'})
        db=sqlite3.connect(self.ledger,isolation_level=None);self.addCleanup(db.close)
        db.executescript('CREATE TABLE requests(id TEXT,model TEXT,reserved INTEGER,charged INTEGER,status TEXT);'
            'CREATE TABLE reconciliations(request_id TEXT,evidence_sha256 TEXT,prior_status TEXT,prior_charge INTEGER,ceiling INTEGER,policy TEXT);')
        runtime['baseline']=m.history_snapshot(db)
        for row in rows:
            db.execute('INSERT INTO requests VALUES(?,?,?,?,?)',(row['request_id'],'gpt-6.1-sol',row['reserved_nano_usd'],
                row['charged_nano_usd']if row is not rows[-1]else 0,row['status']if row is not rows[-1]else 'uncertain'))
        proof['ledger_before']=m.history_snapshot(db);amount=rows[-1]['reserved_nano_usd']
        db.execute("UPDATE requests SET charged=reserved,status='settled_upper_bound'WHERE id=?",(rows[-1]['request_id'],))
        db.execute('INSERT INTO reconciliations VALUES(?,?,?,?,?,?)',(rows[-1]['request_id'],'b'*64,'uncertain',0,amount,RECEIVED_POLICY))
        settlement=dict(id=m.IDENT,original_owner_result_preserved=True,operator_return=dict(mode=RECEIVED_MODE,policy=RECEIVED_POLICY,
            actual_charge_known=False,refund_nano_usd=0,retry_allowed=False,request_id=rows[-1]['request_id'],
            before=proof['ledger_before'],after=m.history_snapshot(db),conservative_charge_nano_usd=amount,evidence={'sha256':'b'*64}))
        owner=dict(budget_summary=dict(unresolved_reserved_usd=amount/1e9))
        request=json.loads(Path(rows[-1]['request']['path']).read_text())
        return db,runtime,owner,settlement,proof,request,rows

    def test_settlement_read_only_exact_prefix_and_later_unrelated_history(self):
        from earnings_population_budget import CAP
        db,runtime,owner,settlement,proof,request,rows=self.settlement();changes=db.total_changes
        with patch.object(m,'_owned_requests',return_value=rows),patch('earnings_population_budget.validate_cap',return_value=CAP):
            self.assertEqual(m._settled(self.reader,runtime,owner,settlement,proof,request),rows)
            self.assertEqual(db.total_changes,changes)
            db.execute("INSERT INTO requests VALUES('later','gpt-6.1-sol',1,1,'settled')")
            self.assertEqual(m._settled(self.reader,runtime,owner,settlement,proof,request),rows)

    def test_unknown_fee_changed_policy_invoice_refund_or_prefix_rejected(self):
        from earnings_population_budget import CAP
        db,runtime,owner,settlement,proof,request,rows=self.settlement()
        with patch.object(m,'_owned_requests',return_value=rows),patch('earnings_population_budget.validate_cap',return_value=CAP):
            for key,value in (('mode','foreign'),('policy','original_unknown_no_raw_policy'),('actual_charge_known',True),
                    ('refund_nano_usd',1),('retry_allowed',True),('conservative_charge_nano_usd',1)):
                with self.subTest(key=key):
                    changed=deepcopy(settlement);changed['operator_return'][key]=value
                    with self.assertRaises(ValueError):m._settled(self.reader,runtime,owner,changed,proof,request)
            db.execute("UPDATE requests SET charged=0,status='uncertain'WHERE id=?",(request['request_id'],))
            with self.assertRaises(ValueError):m._settled(self.reader,runtime,owner,settlement,proof,request)


if __name__=='__main__':unittest.main()
