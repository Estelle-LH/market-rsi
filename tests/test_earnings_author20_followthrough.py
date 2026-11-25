"""Author20 TC: source-bound brief and invented original-table delivery only."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import earnings_open_broker as broker_module
import earnings_open_context as context_module
import earnings_open_roles as roles
import earnings_open_author_followthrough as flow
import earnings_open_fresh_grant as fresh
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_open_roles as role_fixture
import test_earnings_open_fresh_grant as grant_fixture


REPO=Path(__file__).resolve().parents[1]
CONTEXT=REPO/'configs/earnings_coevolution/author_followthrough_context.json'
CONTEXT_SHA='e7cf230d44e3744c4ded2152e07446a5aef40af661f27a6e6225ccf8f4511277'
HISTORICAL20='3f01d57b47f8bd0a3ec0eb1065fa424e072e6b54'


def historical20(name):
    """Read only the three explicitly authorized immutable old20 fixtures."""
    if name not in {'configs/earnings_coevolution/author_followthrough_context.json',
            'tools/earnings_open_context.py','tools/earnings_open_resources.py'}:
        raise ValueError('Unapproved historical fixture path')
    return subprocess.run(['git','show',HISTORICAL20+':'+name],cwd=REPO,
        check=True,capture_output=True).stdout


SOURCE18_SHA='ef007c3b5a0366d6406c113aea1293c9d4d44ec310249febf727e9e5fbb2ea0c'
REVIEW18_SHA='5137791789fd295d2457ef8857bc92fbd279ef43237c66fb772270025bbf8caa'
FEB='filings/10-Q_2025-02-12_0000003545-25-000030.md'
MAY='filings/10-Q_2025-05-13_0000003545-25-000079.md'
APPROVAL20='允许，按这个计划执行。先离线更新到18版诊断、补测试并独立审查；通过且共享运行空闲后，从现有追加$50余额中划拨最多$5，开新的90分钟窗口，跑真实Author修复和一个Alico预测，验证新版本确实被使用。数据、scorer和原$200总预算不变，每个改动单独提交，失败先诊断、不自动重试，不动其他Supervisor。'


class Author20ContextTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(prefix='author20-context-synthetic-')
        self.addCleanup(temporary.cleanup); self.root=Path(temporary.name).resolve()
        frozen=self.root/'historical20-context.json'
        frozen.write_bytes(historical20('configs/earnings_coevolution/author_followthrough_context.json'))
        self.binding=engine.pin(frozen); self.brief=engine.read(self.binding)
        self.seed=('| Invented original table | Period | USD |\n'+'| Synthetic row | 2025 | (17) |\n'*500)
        tail='FEB_ORIGINAL_SEED_TAIL'
        self.seed=self.seed[:10000-len(tail)]+tail
        self.assertEqual(len(self.seed),10000)
        self.may_seed=('MAY_INVENTED_ORIGINAL_TABLE\n'+'invented row\n'*600)[:6000]
        self.files={'questions.md':'### T001 | Invented financial quantity',
            'filing_index.tsv':'date_filed\tform_type\taccession\tpath\n'
                f'2025-02-12\t10-Q\told-feb\t{FEB}\n2025-05-13\t10-Q\told-may\t{MAY}\n',
            FEB:'F'*22000+self.seed+'AFTER_BOUNDED_SEED',MAY:'M'*44000+self.may_seed+'AFTER_MAY'}
        self.company={'visible_root':str(self.root/'visible'),'target_accession':'hidden-target',
            'cutoff':'2025-06-01','allowed_files':[]}
        for name,text in self.files.items():
            path=self.root/'visible'/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_text(text)
            self.company['allowed_files'].append({'path':name,'bytes':len(text.encode()),
                'sha256':hashlib.sha256(text.encode()).hexdigest()})
        self.runner,self.literature,self.capacity=mock.Mock(),mock.Mock(),mock.Mock()

    def broker(self):
        return broker_module.ResearchBroker(self.root/'broker',company=self.company,
            capacity=self.capacity,runner=self.runner,literature=self.literature,
            trace_slots={},research_context_binding=self.binding)

    def test_actual_context_pins_rejected18_not14_or_selected_parent(self):
        self.assertEqual(self.binding['sha256'],CONTEXT_SHA)
        reference=self.brief['prior_candidate']
        self.assertEqual(reference['axis'],'R')
        self.assertEqual(reference['status'],'actual18_financial_review_rejected_not_selected')
        self.assertEqual(reference['source']['sha256'],SOURCE18_SHA)
        self.assertTrue(reference['source']['path'].endswith('/edgar-research-20261015-18/researcher.py'))
        # Read/hash public archived bytes only; never import or execute them.
        raw=Path(reference['source']['path']).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),SOURCE18_SHA)
        self.assertEqual(len(raw),22901); self.assertEqual(reference['source_bytes'],22901)
        self.assertEqual(reference['source_delivery'],'paged_reference'); self.assertNotIn('source_text',reference)
        observations=self.brief['observations']
        self.assertEqual(observations['independent_review']['sha256'],REVIEW18_SHA)
        self.assertTrue(observations['independent_review']['path'].endswith('/AUTHOR18-CANDIDATE-REVIEW.json'))
        self.assertEqual(observations['actual18_cases']['original_table_regressions'],0)
        self.assertEqual(observations['selected_parent_R_sha256'],
            'c3296f1b75cc10a6e67f746b0137f99f2f6765740b19f59b716acd29fa3907be')

    def test_brief_preserves_working_fixes_and_requires_original_semantic_regressions(self):
        obs=self.brief['observations']; verification='\n'.join(self.brief['verification'])
        for text in ('1911','Citrus','Land','acquisition'):
            self.assertIn(text,obs['preserve_observed_working_behavior'])
        for text in ('attributable','operating_expenses','section_measure'):
            self.assertIn(text,obs['wrong_measure_failure'])
        for text in ('Non-controlling Interest','Retained Earnings','Total Equity'):
            self.assertIn(text,obs['equity_dimension_failure'])
        for text in ('Land and Other Leasing','Land Management','unknown'):
            self.assertIn(text,obs['leasing_coverage_failure'])
        for text in ('literal CASES','actual table slices','attributable-income','equity/NCI','leasing',
                'questions/index/records:[]','SAME source','Independent original-table financial review'):
            self.assertIn(text,verification)
        self.assertIn('fresh human-approved20 attempt',self.brief['human_task'])
        text=json.dumps(self.brief)
        self.assertNotIn('2026-10-15T23:50:19Z',text); self.assertNotIn('2026-10-16T01:20:19Z',text)
        self.assertNotIn('/edgar-research-20261015-14/researcher.py',text)

    def test_exact_declared_first_Feb_seed_and_second_May_hint_no_inline_reference(self):
        hints=self.brief['observations']['actual_original_read_locations']
        self.assertEqual([{'tool':row['tool'],'arguments':row['arguments']} for row in hints],[
            {'tool':'read_file','arguments':{'path':FEB,'offset':22000,'characters':10000}},
            {'tool':'read_file','arguments':{'path':MAY,'offset':44000,'characters':6000}}])
        broker=self.broker(); plain=broker.research_context()
        self.assertNotIn('initial_original_evidence',plain); self.assertEqual(broker.files.calls,0)
        full=broker.research_context(include_source=True); evidence=full['initial_original_evidence']
        self.assertEqual(evidence['request'],{'tool':'read_file','arguments':hints[0]['arguments']})
        self.assertEqual(evidence['result']['value']['text'],self.seed)
        self.assertEqual(evidence['source_sha256'],hashlib.sha256(self.files[FEB].encode()).hexdigest())
        self.assertEqual(engine.read(evidence['result']['research_receipt']),
            {'value':evidence['result']['value'],'untrusted_evidence':True})
        self.assertEqual(evidence['provided_by'],'harness_preparation_not_model_tool_choice')
        self.assertEqual((broker.calls,broker.files.calls),(1,1))
        self.assertEqual(broker.research_context(include_source=True),full)
        self.assertEqual((broker.calls,broker.files.calls),(1,1))
        self.assertNotIn('source_text',full['prior_candidate'])
        self.assertNotIn(Path(full['prior_candidate']['source']['path']).read_text(),json.dumps(full))
        self.runner.run.assert_not_called(); self.literature.dispatch.assert_not_called(); self.capacity.resolve.assert_not_called()

    def test_mocked_Author_initial_first_final_request_preserve_exact_H_body_and_source_binding(self):
        broker=self.broker(); f=role_fixture.OpenRoleTests(); f.setUp(); self.addCleanup(f.doCleanups)
        f.broker=broker; f.service(author=True,max_turns=2,
            limits={'max_input_tokens':10000,'max_output_tokens':32768,'wall_seconds':900})
        transport=json.loads(f.context_path.read_bytes()); transport['rates']['effort']='high'
        f.context_path.write_text(json.dumps(transport))
        service=roles.OpenAuthor(engine.pin(f.context_path),budget=f.budget,client_factory=f.factory,
            broker=broker,max_turns=2)
        chosen=f.choice('R')
        f.generations=[f.tool_response(f.call(name='calculate',arguments={'expression':'1+1'})),
            f.message({'decision_sha256':digest(chosen),'source_text':"PROGRAM={'axis':'R'}\ndef run(p): return {}\n",
                'test_text':"CASES=[{'input':{},'expected':{}}]"})]
        with mock.patch.object(roles,'pack',side_effect=lambda _c,request,*_a,**_k:deepcopy(request)),\
                mock.patch.object(roles,'budgeted_response',side_effect=f.fake_paid):
            service.author(chosen,{'axis':'R'},str(f.slot))
        effective=json.loads((f.slot/'effective-input.json').read_bytes())
        self.assertEqual(len(f.requests),2)
        for request in f.requests:
            self.assertEqual(json.loads(request['input'][0]['content']),effective)
            self.assertEqual(request['reasoning'],{'effort':'high'})
            self.assertEqual(request['model'],'gpt-6.1-sol')
        self.assertEqual(f.requests[0]['tool_choice'],'auto'); self.assertEqual(f.requests[-1]['tool_choice'],'none')
        evidence=effective['research_context']['initial_original_evidence']
        self.assertEqual(evidence['result']['value']['text'],self.seed)
        self.assertIn('FEB_ORIGINAL_SEED_TAIL',f.requests[-1]['input'][0]['content'])
        self.assertEqual(effective['research_context']['prior_candidate']['source']['sha256'],SOURCE18_SHA)
        self.assertNotIn('source_text',effective['research_context']['prior_candidate'])
        self.assertEqual(evidence['provided_by'],'harness_preparation_not_model_tool_choice')
        intents=[engine.read(engine.pin(broker.root/name/'intent.json'))['name'] for name in ('0001','0002')]
        self.assertEqual(intents,['read_file','calculate'])
        self.assertEqual(json.loads((f.slot/'result.json').read_bytes())['tool_calls'],1)
        # Only synthetic calculate was model-selected; the filing read was H-preparation.
        final,_=context_module.author_final_view(f.requests[-1],100,
            preserve_call_ids=context_module.author_preserved_outputs(f.requests[-1]))
        self.assertEqual(final['input'][0],f.requests[-1]['input'][0])
        self.assertEqual(json.loads(final['input'][0]['content'])['research_context']['initial_original_evidence'],evidence)
        self.assertEqual(service.context['limits']['max_input_tokens'],10000)
        self.runner.run.assert_not_called(); self.literature.dispatch.assert_not_called(); self.capacity.resolve.assert_not_called()


class Author20EntryTests(unittest.TestCase):
    def setUp(self):
        self.f=grant_fixture.FreshGrantTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.root=self.f.home; self.number=0
        self.context={'schema':'earnings_repair_context_v1','human_task':'Invented18 repair context',
            'prior_candidate':{'source':{'path':str(self.root/'reference.py'),'sha256':SOURCE18_SHA}},
            'observations':{'independent_review':{'path':str(self.root/'synthetic-review18.json'),'sha256':REVIEW18_SHA}}}
        self.context_binding=engine.save(self.root/'initial-context.json',self.context)
        self.opening={'max_rowid':4807,'request_count':4807,
            'charged_nano_usd':fresh.BASELINE['charged_nano_usd']+9_500_000_000,'rows_sha256':'a'*64}
        self.allocation={'opening':self.opening,'max_new_nano_usd':5_000_000_000,
            'author_id':'edgar-research-20261016-20','forecast_id':'edgar-research-20261016-21'}
        self.body=deepcopy(self.f.body)
        self.body['author_configuration']=deepcopy(fresh.AUTHOR_CONFIGURATION)
        self.body['window']={'issued_utc':'2099-01-01T00:00:00Z','cutoff_utc':'2099-01-01T01:29:00Z',
            'deadline_utc':'2099-01-01T01:30:00Z'}
        self.body['continuation']={'human_authorization':APPROVAL20,'cumulative_cap_nano_usd':14_500_000_000,
            'rounds':1,'research_context':self.context_binding,'allocation':self.allocation}

    def test_allocation_formula_retains_4283_history_50_200_100_and_maximum5(self):
        self.assertEqual(fresh.AUTHOR20_AUTHORIZATION,APPROVAL20)
        self.assertEqual(fresh.AUTHOR20_IDS,('edgar-research-20261016-20','edgar-research-20261016-21'))
        body=self.f.policy(self.body)
        self.assertEqual(fresh.pilot_cap(body),14_500_000_000)
        self.assertEqual(fresh.allocation(body),self.allocation); self.assertEqual(fresh.requested_rounds(body),1)
        self.assertEqual(body['baseline'],fresh.BASELINE)
        self.assertEqual(fresh.BASELINE,{'max_rowid':4283,'request_count':4283,'charged_nano_usd':137542765000,
            'rows_sha256':'7ee9ae3ce1b56ddcd8972f58d40447b83082cf6f7a777a888b1ea22ec5ee5da8'})
        self.assertEqual((body['original_total_cap_nano_usd'],body['original_per_model_cap_nano_usd'],
            body['new_subgrant_nano_usd']),(200_000_000_000,100_000_000_000,50_000_000_000))
        smaller=deepcopy(self.body); smaller['continuation']['allocation']['max_new_nano_usd']=1
        smaller['continuation']['cumulative_cap_nano_usd']=9_500_000_001
        self.assertEqual(fresh.pilot_cap(self.f.policy(smaller)),9_500_000_001)

    def test_allocation_strict_types_opening_identity_formula_and_night20_boundary(self):
        variants=[]
        for value in (True,0,-1,5_000_000_001,5_000_000_000.0,'5000000000'):
            body=deepcopy(self.body); body['continuation']['allocation']['max_new_nano_usd']=value; variants.append(body)
        for key,value in (('max_rowid',4806),('request_count',4806),('request_count',True),
                ('charged_nano_usd',fresh.BASELINE['charged_nano_usd']-1),('rows_sha256','bad')):
            body=deepcopy(self.body); body['continuation']['allocation']['opening'][key]=value; variants.append(body)
        for change in ({'author_id':'edgar-research-20261015-18'},{'forecast_id':'edgar-research-20261015-19'},
                {'extra':True}):
            body=deepcopy(self.body); body['continuation']['allocation'].update(change); variants.append(body)
        for value in (5_000_000_000,14_500_000_001,14_500_000_000.0,True):
            body=deepcopy(self.body); body['continuation']['cumulative_cap_nano_usd']=value; variants.append(body)
        for change in ({'human_authorization':'unapproved'},{'rounds':2},{'rounds':True}):
            body=deepcopy(self.body); body['continuation'].update(change); variants.append(body)
        body=deepcopy(self.body); body['continuation'].pop('allocation'); variants.append(body)
        body=deepcopy(self.body); body['continuation']['allocation']['opening']['charged_nano_usd']+=6_000_000_000
        body['continuation']['cumulative_cap_nano_usd']+=6_000_000_000; variants.append(body)
        for index,body in enumerate(variants):
            with self.subTest(index=index),self.assertRaises(ValueError): self.f.policy(body)

    def test_new_allocation_cannot_renew_oldIDs_rebase_or_widen_original_caps_window(self):
        self.f.body=deepcopy(self.body)
        identifiers=list(fresh.AUTHOR20_IDS)+[f'edgar-research-20261015-{number}' for number in range(12,20)]
        for identifier in identifiers:
            grant=dict(self.f.grant,id=identifier,root=str(self.root/'attempts'/identifier),additional_cap_nano_usd=14_500_000_000,
                **{k:self.body['window'][k] for k in ('cutoff_utc','deadline_utc')})
            if identifier in fresh.AUTHOR20_IDS: self.assertEqual(self.f.validate(grant),self.body)
            else:
                with self.assertRaises(ValueError): self.f.validate(grant)
        for change in ({'original_total_cap_nano_usd':201_000_000_000},{'original_per_model_cap_nano_usd':101_000_000_000},
                {'new_subgrant_nano_usd':51_000_000_000},{'baseline':dict(fresh.BASELINE,max_rowid=4807)},
                {'window':dict(self.body['window'],cutoff_utc='2099-01-01T01:30:01Z')}):
            with self.subTest(change=change),self.assertRaises(ValueError): self.f.policy(dict(self.body,**change))

    def scope(self):
        return {'schema':'earnings_author_followthrough_authority_v1','human_authorization':flow.AUTHORIZATION,
            'author_id':fresh.AUTHOR20_IDS[0],'forecast_id':fresh.AUTHOR20_IDS[1],
            'parent':'edgar-feedback-20261015-11','parent_result':{'sha256':flow.PARENT_RESULT_SHA},
            'parent_audit':{'sha256':flow.PARENT_AUDIT_SHA},'baseline_row':4283,'no_retry':True,
            'continuation_cumulative_cap_nano_usd':14_500_000_000,'original_total_cap_nano_usd':200_000_000_000,
            'window':self.body['window'],'allocation':self.allocation,'continuation_human_approval':APPROVAL20,
            'requires_cold_probe':True,'opening_rows':4807,'opening_rows_sha256':'a'*64,
            'failed_author_result':{'path':str(self.root/'synthetic-author18.json'),'sha256':'b'*64},
            'failed_candidate_review':self.context['observations']['independent_review']}

    def authority(self, *, scope_change=None, context_change=None, original_sha=None,
                  policy_context_change=None, review_verdict='REJECT_AUTHOR_CANDIDATE_ONE_FORECAST'):
        self.number+=1; home=self.root/f'authority-{self.number}'; home.mkdir()
        context=deepcopy(self.context); context.update(context_change or {})
        cp=home/'context.json'; cb=engine.save(cp,context)
        body=deepcopy(self.body); body['continuation']['research_context']=cb
        if policy_context_change is not None:
            body['continuation']['research_context']=engine.save(home/'policy-context.json',
                dict(deepcopy(context),**policy_context_change))
        self.f.path.write_text(json.dumps(body)); scope=self.scope(); scope.update(scope_change or {})
        sp=home/'scope.json'; engine.save(sp,scope)
        def read(binding):
            if binding['path'].endswith('synthetic-author18.json'):
                return {'original':{'sha256':original_sha or '961e18a652ad91cbc0494111a435866e6414bdcaf327d028add2673329a7b9c2'}}
            if binding['path'].endswith('synthetic-review18.json'): return {'verdict':review_verdict}
            return engine.read(binding)
        with mock.patch.object(fresh,'CONFIG',self.f.path),mock.patch.object(flow,'SCOPE',sp),\
                mock.patch.object(flow,'CONTEXT',cp),mock.patch.object(flow,'read',side_effect=read):
            return flow.authority()

    def test_exact20_scope_rejected18_review_source_context_opening_and_cold_required(self):
        self.assertEqual(self.authority(),self.scope())
        variants=[{'continuation_human_approval':'unapproved'},{'requires_cold_probe':False},
            {'forecast_id':'edgar-research-20261015-19'},{'opening_rows':4808},{'opening_rows_sha256':'0'*64},
            {'allocation':dict(self.allocation,max_new_nano_usd=1)},
            {'failed_candidate_review':dict(self.context['observations']['independent_review'],sha256='0'*64)}]
        for change in variants:
            with self.subTest(change=change),self.assertRaises(ValueError): self.authority(scope_change=change)
        with self.assertRaises(ValueError): self.authority(original_sha='0'*64)
        with self.assertRaises(ValueError): self.authority(context_change={'prior_candidate':{'source':{'sha256':'0'*64}}})
        with self.assertRaises(ValueError): self.authority(policy_context_change={'human_task':'different delivered context'})
        with self.assertRaises(ValueError): self.authority(review_verdict='PASS_AUTHOR_CANDIDATE_ONE_FORECAST')

    def ledger(self):
        path=self.root/'synthetic-only.sqlite3'; db=sqlite3.connect(path)
        self.addCleanup(db.close)
        db.execute('CREATE TABLE config (id INTEGER PRIMARY KEY,cap INTEGER,model_cap INTEGER,blocked INTEGER)')
        db.execute('INSERT INTO config VALUES (1,200000000000,100000000000,0)')
        db.execute('CREATE TABLE requests (id TEXT PRIMARY KEY,model TEXT,reserved INTEGER,charged INTEGER,status TEXT)')
        rows=[]
        for number in range(1,4808):
            amount=80_000_000_000 if number==1 else (57_542_765_000 if number==2 else (9_500_000_000 if number==4284 else 0))
            rows.append((f'invented-{number}','invented-other' if number==2 else 'invented-model',max(1,amount),amount,'settled'))
        db.executemany('INSERT INTO requests VALUES (?,?,?,?,?)',rows); db.commit()
        baseline=flow.history_snapshot(db,4283); opening=flow.history_snapshot(db,4807)
        scope={'opening_rows':4807,'opening_rows_sha256':opening['rows_sha256'],
            'allocation':{'opening':opening},'continuation_cumulative_cap_nano_usd':14_500_000_000}
        return path,db,baseline,scope

    def test_real_temp_accounting_later_sharedfees_reduce_and_pending_or_opening_drift_stop(self):
        path,db,baseline,scope=self.ledger()
        with mock.patch.object(fresh,'BASELINE',baseline):
            first=flow.accounting(scope,path); self.assertEqual(first['remaining_nano_usd'],5_000_000_000)
            db.execute("INSERT INTO requests VALUES ('later-shared','other',1200000000,1200000000,'settled')"); db.commit()
            self.assertEqual(flow.accounting(scope,path)['remaining_nano_usd'],3_800_000_000)
            db.execute("INSERT INTO requests VALUES ('pending','other',1,0,'uncertain')"); db.commit()
            with self.assertRaises(ValueError): flow.accounting(scope,path)
            db.execute("DELETE FROM requests WHERE id='pending'"); db.commit()
            bad=deepcopy(scope); bad['allocation']['opening']['charged_nano_usd']+=1
            with self.assertRaises(ValueError): flow.accounting(bad,path)
            db.execute("UPDATE requests SET charged=charged+1 WHERE id='invented-4807'"); db.commit()
            with self.assertRaisesRegex(ValueError,'Original settled ledger'): flow.accounting(scope,path)
            db.execute("UPDATE requests SET charged=charged-1 WHERE id='invented-4807'"); db.commit()
            db.execute("INSERT INTO requests VALUES ('more-shared','other',3800000000,3800000000,'settled')"); db.commit()
            with self.assertRaisesRegex(ValueError,'allowance consumed'): flow.accounting(scope,path)

    def test_sourceclosure_only_exact_accepted_Hpins_and_declared_fresh_change(self):
        repo=self.root/'source-copy'; names=['tools/earnings_open_context.py','tools/earnings_open_broker.py',
            'tools/earnings_open_fresh_grant.py','tools/earnings_open_author_followthrough.py','tools/protected.py',
            'configs/scope.json','configs/context.json','tools/earnings_open_resources.py']
        for name in names:
            path=repo/name; path.parent.mkdir(parents=True,exist_ok=True)
            raw=(historical20(name) if name in {'tools/earnings_open_context.py','tools/earnings_open_resources.py'}
                else ((REPO/name).read_bytes() if (REPO/name).is_file() else b'invented protected source'))
            path.write_bytes(raw)
        old={'sources':{name:dict(engine.pin(repo/name),sha256='0'*64) for name in names[:3]}}
        old['sources']['tools/protected.py']=engine.pin(repo/'tools/protected.py')
        old['sources']['tools/earnings_open_resources.py']=engine.pin(repo/'tools/earnings_open_resources.py')
        with mock.patch.object(flow.e,'REPO',repo),mock.patch.object(flow,'__file__',str(repo/names[3])),\
                mock.patch.object(flow,'SCOPE',repo/'configs/scope.json'),mock.patch.object(flow,'CONTEXT',repo/'configs/context.json'):
            result=flow.source_bindings(old,scope={'author_id':fresh.AUTHOR20_IDS[0]})
            self.assertEqual(result['tools/earnings_open_context.py']['sha256'],
                '07a655e977b084c1baed5e009aeed6159b4288cf5e90418d13282e848665725c')
            self.assertEqual(result['tools/earnings_open_broker.py']['sha256'],
                'a2e6d408037a924d18cb881c404ad9169375ad460424a0375c806ab3316fdc88')
            with self.assertRaises(ValueError): flow.source_bindings(old)
            legacy=deepcopy(old)
            for name in ('tools/earnings_open_context.py','tools/earnings_open_broker.py'):
                legacy['sources'][name]=engine.pin(repo/name)
            with self.assertRaisesRegex(ValueError,'fresh_grant'):
                flow.source_bindings(legacy,scope={'author_id':'edgar-research-20261015-18'})
            for name in ('tools/protected.py','tools/earnings_open_broker.py','tools/earnings_open_context.py'):
                path=repo/name; original=path.read_bytes(); path.write_bytes(original+b'\n# drift')
                with self.assertRaises(ValueError): flow.source_bindings(old,scope={'author_id':fresh.AUTHOR20_IDS[0]})
                path.write_bytes(original)

    def test_shared80_counts_all_closed_research_and_forecastIDs_not_per_attempt_reset(self):
        roots=[('edgar-research-20261015-12',name) for name in ('code','review-code')]
        roots.extend(('edgar-research-20261015-'+identifier,name) for identifier in ('14','16','18')
            for name in ('code','review-code','cold-probe-code'))
        roots.extend(('edgar-research-20261015-'+identifier,'code') for identifier in ('13','15','17','19'))
        roots.extend((fresh.AUTHOR20_IDS[0],name) for name in ('code','review-code','cold-probe-code'))
        roots.append((fresh.AUTHOR20_IDS[1],'code'))
        for index,(identifier,name) in enumerate(roots):
            home=self.root/'attempts'/identifier/name; home.mkdir(parents=True)
            for n in range(7 if index==len(roots)-1 else 4):
                call=home/f'call-{n:032x}'; call.mkdir(); engine.save(call/'result.json',{'status':'FAILED_NO_RETRY'})
        self.assertEqual(len(roots),19)
        with mock.patch.object(flow,'ROOT',self.root),mock.patch.object(flow,'authority',return_value=self.scope()):
            self.assertEqual(flow.containers_remaining(),1)
            (self.root/'attempts/edgar-research-20261015-19/code'/('call-'+'f'*32)).mkdir()
            with self.assertRaises(ValueError): flow.containers_remaining()

    def test_actual_prepare_propagates_cap_preserving_limits_rates_efforts_and_consumedID_guard(self):
        self.f.body=deepcopy(self.body); self.f.path.write_text(json.dumps(self.body))
        oldgrant=dict(self.f.grant,ledger=str(self.root/'unused.sqlite3'),python={'synthetic':True})
        oldruntime={'rates':{'api_model':'fixed-model'},'limits':{'max_input_tokens':10000},
            'role_efforts':{'author':'high','controller':'max','forecast':'max'},'additional_cap_nano_usd':10_000_000_000,
            'ledger':oldgrant['ledger'],'baseline':deepcopy(fresh.BASELINE)}
        oldstudy={'cases':[{'invented':True}],'runtime_config':{'request_timeout_seconds':180},'program_lineage':{'old':True}}
        old={'handoff':{'old_runtime':engine.save(self.root/'old-runtime.json',oldruntime),
            'old_episode':engine.save(self.root/'old-episode.json',{'grant':engine.save(self.root/'old-grant.json',oldgrant),
                'study':engine.save(self.root/'old-study.json',oldstudy)})}}
        scope=self.scope(); scopepath=self.root/'scope.json'; engine.save(scopepath,scope)
        trusted=engine.save(self.root/'inert-trusted.json',{'inert':True})
        with mock.patch.object(flow,'ROOT',self.root),mock.patch.object(fresh,'ROOT',self.root),\
                mock.patch.object(fresh,'CONFIG',self.f.path),mock.patch.object(flow,'SCOPE',scopepath),\
                mock.patch.object(flow,'authority',return_value=scope),mock.patch.object(flow,'prior',return_value=old),\
                mock.patch.object(flow,'accounting'),mock.patch.object(flow,'verify_current_python'),\
                mock.patch.object(flow.namespace,'native_paths',return_value={}),\
                mock.patch.object(flow.subprocess,'run',side_effect=[SimpleNamespace(stdout=b''),SimpleNamespace(stdout='c'*40)]) as git,\
                mock.patch.object(flow,'source_bindings',return_value={'inert':trusted}),mock.patch.object(flow,'verify_sources'),\
                mock.patch.object(flow,'CORE',{}),mock.patch.object(flow,'preflight_runtime',side_effect=engine.read):
            prepared=engine.read(flow.prepare('author'))
            grant=engine.read(prepared['grant']); runtime=engine.read(prepared['runtime'])
            self.assertEqual(grant['additional_cap_nano_usd'],14_500_000_000)
            self.assertEqual(runtime['additional_cap_nano_usd'],14_500_000_000)
            for field in ('rates','limits','role_efforts'): self.assertEqual(runtime[field],oldruntime[field])
            self.assertEqual(grant['baseline'],fresh.BASELINE); self.assertEqual(grant['ledger'],oldgrant['ledger'])
            self.assertEqual(grant['id'],fresh.AUTHOR20_IDS[0]); self.assertEqual(prepared['provider_calls'],0)
            with self.assertRaises(FileExistsError): flow.prepare('author')
            self.assertEqual(git.call_count,2)


if __name__=='__main__': unittest.main()
