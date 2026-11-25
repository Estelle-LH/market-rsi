"""Scripted CLI canary for schema3 real-path R/H transport and next use.

Only original financial/source/accounting admission is a named fixture
whitelist. Raw HTTPS bytes, boot clock and external Native namespace are
invented. Actual CLI, task, Controller, Author, SourceReview, matched review,
Native worker, scorer, common driver, owner, ledger and replay run unchanged.
Input-token effects are explicitly scripted fixture effects, not model gains.
No production data, protected answers, credentials, live ledger or network.
"""
from contextlib import contextmanager, ExitStack, redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

import earnings_capacity_assembly as assembly
import earnings_capacity_runtime as runtime
import earnings_clock as clock
import earnings_completed_replay as completed
import earnings_controller as controller
import earnings_entry as entry
import earnings_feedback_loop as flow
import earnings_live_capacity as live
import earnings_round_plan as round_plan
from earnings_capacity_adapter import author_payload
from earnings_research_state import ResearchState
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
from supervisor_harness import continuous_discovery_batch as native
from test_earnings_capacity_assembly import AssemblyFixture


RULE = 'Verify signs and units against the provided filing before forecasting.'


class LivePathFixture(AssemblyFixture):
    """Three-round owned fixture with v3 episode/runtime and v2 assembly."""
    def __init__(self, owner):
        super().__init__(owner, rounds=3)

    def client_factory(self):
        self.factory_calls += 1
        client = type(self.raw.http)('', timeout=600)
        self.clients.append(client)
        return client

    def seal(self):
        # Preserve the existing invented fact span while making the actual H
        # clamp observable: both requested 20000 and child 18000 are available.
        filing = Path(self.raw.company['visible_root'])/'filings/old.md'
        content = filing.read_text() + '\n' + 'Long invented public filing paragraph. ' * 1000
        filing.write_text(content)
        token = entry.digest(filing.read_bytes())
        row = next(row for row in self.raw.company['allowed_files'] if row['path']=='filings/old.md')
        row.update(bytes=len(filing.read_bytes()), sha256=token)
        self.raw.data.fact['source_sha256'] = token
        self.raw.runtime['request_timeout_seconds'] = 180
        self.raw.rate = deepcopy(self.raw.runtime['models']['gpt-6.1-sol'])
        if self.raw.rate['effort'] != 'max':
            raise AssertionError('Fixture must reuse the current original max runtime')
        original_runtime = self.save('original-runtime-config', self.raw.runtime)
        self.raw.study['data'] = self.save('invented-current-public-plan', {'companies':[self.raw.company]})
        self.raw.study['runtime_config'] = deepcopy(self.raw.runtime)
        self.raw.study['prior_batch'] = self.save('original-runtime-snapshot', {
            'schema':'original_runtime_snapshot_v1', 'source':original_runtime,
            'config':deepcopy(self.raw.runtime)})
        self.raw.study['cases'][0]['allowed_manifest_sha256'] = entry.digest(json.dumps(
            self.raw.company['allowed_files'],sort_keys=True,separators=(',',':')).encode())
        self.raw.study_binding = self.save('real-path-study', self.raw.study)
        self.runtime.update(schema='earnings_capacity_runtime_v3',
            rates=deepcopy(self.raw.rate), additional_cap_nano_usd=10000000000,
            deadline_utc='2099-01-01T00:00:45Z', forecast_study=self.raw.study_binding)
        self.native['batch_config']['deadline_utc'] = self.runtime['deadline_utc']
        # C3 independently tests true namespace/source/runtime/data admission;
        # this fixture whitelist admits only this owned invented namespace.
        grant = {'schema':'earnings_real_rh_grant_v1','id':self.id,'root':str(self.root),
            'source_commit':self.envelope['source_commit'],'sources':deepcopy(self.envelope['sources']),
            'python':self.raw.study['python'],'data':self.raw.study['data'],'runtime':original_runtime,
            'scorer':self.raw.kernel['scorer'],'qa':self.raw.kernel['qa'],'cik':self.envelope['cik'],
            'ledger':self.runtime['ledger'],'baseline':deepcopy(self.runtime['baseline']),
            'cutoff_utc':self.runtime['cutoff_utc'],'deadline_utc':self.runtime['deadline_utc'],
            'additional_cap_nano_usd':10000000000,'human_authorization':live.AUTHORIZATION,
            'allowed_egress':deepcopy(live.EGRESS),'bootstrap_no_model_call':True}
        self.grant = grant
        self.envelope.update(schema=live.SCHEMA,mode='real_provider',study=self.raw.study_binding,
            grant=self.save('real-path-grant',grant),window={k:grant[k] for k in ('cutoff_utc','deadline_utc')})
        self.episode_binding = self.save('episode-v3',self.envelope)
        self.plan = {'schema':'earnings_matched_plan_v1','episode':self.episode_binding,'rounds':self.plan_rows}
        self.plan_binding = self.save('matched-plan-v3',self.plan)
        self.runtime.update(episode=self.episode_binding,matched_plan=self.plan_binding)
        self.runtime['sources']['round_plan'] = engine.pin(round_plan.__file__)
        self.runtime_binding = self.save('runtime-v3',self.runtime)
        self.native['micro_config']['fixed_context'] = {
            'model_sha256':self.native['baseline']['M'],'evaluation_sha256':self.native['baseline']['K'],
            'data_scope_sha256':digest({'study':self.envelope['study'],'cik':self.envelope['cik'],
                                       'kernel':self.envelope['evaluation_kernel']}),
            'authority_sha256':digest({k:self.envelope[k] for k in ('mode','grant','window')}),
            'resource_policy_sha256':digest(self.runtime_binding)}
        self.transport_policy = {'schema':'edgar_foreground_slow_call_policy_v1',
            'source_commit':grant['source_commit'],'original_runtime_request_timeout_seconds':180,
            'effective_socket_timeout_seconds':600,'role_and_global_deadlines_unchanged':True,'retry_allowed':False}
        self.assembly = {'schema':'earnings_capacity_assembly_v2','mode':'real_provider',
            'episode':self.episode_binding,'runtime':self.runtime_binding,
            'native':self.save('native-v3',self.native),'matched_plan':self.plan_binding,
            'effect_registration':self.save('effect-registration-v3',self.registration),
            'source_review':self.save('source-review-v3',self.review),
            'constructors':assembly.constructor_sources(),'transport':engine.source_of(self.client_factory),
            'transport_policy':self.save('foreground600-policy',self.transport_policy),
            'claims':{'model_authorship':False,'predictive_gain':False}}
        self.assembly_binding = self.save('assembly-v2-real',self.assembly)

    def invented_task_source_accounting_admission(self,envelope):
        """Exact fixture whitelist, NOT original EDGAR financial admission."""
        if (envelope != self.envelope or engine.read(envelope['grant']) != self.grant
                or envelope['evaluation_kernel'] != self.raw.kernel
                or engine.read(envelope['study']) != self.raw.study):
            raise ValueError('Only this exact invented financial/source/accounting fixture is admitted')
        state = ResearchState(self.raw.company,self.id)
        if state.load(envelope['initial_state']) != state.empty():
            raise ValueError('Fixture original empty state changed')
        return self.raw.company,state

    @contextmanager
    def actual_path(self,replies):
        with self.exchange(replies),patch.object(live,'admit',
                side_effect=self.invented_task_source_accounting_admission) as admitted:
            yield admitted


class ScriptedMicroReplies:
    """Invent original response bytes only; inspect each actual role request."""
    def __init__(self,fixture,axes=('R','H'),*,scripted_R_benefit=True,unknown_R_effect=False):
        self.fixture,self.axes = fixture,list(axes)
        self.scripted_R_benefit,self.unknown_R_effect = scripted_R_benefit,unknown_R_effect
        self.controller_inputs,self.controller_payloads,self.decisions = [],[],[]
        self.author_inputs,self.author_payloads,self.authored = [],[],[]
        self.forecast_inputs = []

    def message(self,value):
        return self.fixture.raw.response([{'type':'message','role':'assistant','status':'completed',
            'content':[{'type':'output_text','text':json.dumps(value)}]}])

    def choose(self,payload):
        if payload['text']['format']['name']!='earnings_capacity_decision_v1':
            raise AssertionError('Actual Controller request expected')
        safe = json.loads(payload['input'][0]['content'])
        axis = self.axes[len(self.controller_inputs)]
        component = {'R':'research_policy','H':'tool_interface','continue':'none'}[axis]
        metric = 'input_tokens' if axis=='R' else 'tool_return_characters'
        effect = 'Retain the exact selected parent' if axis=='continue' else (
            f'earnings-shadow-v1|{component}|{metric}|lower|1|score_nonregression|matched_trial_only')
        if axis=='R' and self.unknown_R_effect: effect='Unknown scripted effect, deliberately not adoptable'
        decision = {'schema':'earnings_capacity_decision_v1','axis':axis,'component':component,
            'parent_pair_sha256':safe['parent_pair_sha256'],'feedback_sha256':safe['feedback_sha256'],
            'hypothesis':'Scripted fixture exercises one bounded source change; not autonomous discovery',
            'expected_effect':effect}
        self.controller_inputs.append(deepcopy(safe));self.controller_payloads.append(deepcopy(payload))
        self.decisions.append(deepcopy(decision))
        return self.message(decision)

    def author(self,payload):
        if payload['text']['format']['name']!='earnings_capacity_author_v1':
            raise AssertionError('Actual Author request expected')
        safe = json.loads(payload['input'][0]['content']);chosen=safe['decision']
        if chosen!=self.decisions[-1] or safe['decision_sha256']!=digest(chosen):
            raise AssertionError('Unchanged actual Controller decision must reach Author')
        after = deepcopy(safe['before_profile'])
        if chosen['axis']=='R':
            field='research_instructions';old=after[field]
            after[field]=old+('' if not old or old.endswith('\n') else '\n')+RULE
        else:
            field='read_chunk_limit';after[field]=18000
        value={'decision_sha256':safe['decision_sha256'],'source_text':'PROFILE = '+repr(after)+'\n',
               'test_text':'CASES = '+repr([{'field':field,'expected':after[field]}])+'\n'}
        self.author_inputs.append(deepcopy(safe));self.author_payloads.append(deepcopy(payload))
        self.authored.append(deepcopy(value))
        return self.message(value)

    def usage(self,response,payload):
        self.forecast_inputs.append(deepcopy(payload))
        has_R = any(RULE in item.get('content','') for item in payload['input'])
        # Deliberately scripted usage values exercise original-trace comparison;
        # neither this arithmetic nor acceptance establishes real efficiency.
        if self.scripted_R_benefit and has_R:
            response['usage']['input_tokens']=11
            response['usage']['total_tokens']=11+response['usage']['output_tokens']
        return response

    def research(self,payload,*,save_fact=False):
        output=[]
        if save_fact:
            output.append({'type':'function_call','call_id':'save-fact','name':'save_research_record',
                'arguments':json.dumps({'record_json':json.dumps(self.fixture.raw.data.fact)})})
        output.append({'type':'function_call','call_id':'read-long-filing','name':'read_file',
            'arguments':json.dumps({'path':'filings/old.md','offset':0,'characters':20000})})
        return self.usage(self.fixture.raw.response(output),payload)

    def final(self,payload):
        return self.usage(self.fixture.raw.final(),payload)

    def sequence(self):
        replies=[lambda payload:self.research(payload,save_fact=True),self.final]
        for axis in self.axes:
            replies.append(self.choose)
            if axis!='continue':replies.append(self.author)
            forecasts=1 if axis=='continue' or axis=='R' and self.unknown_R_effect else 3
            for _ in range(forecasts):replies.extend([self.research,self.final])
        return replies


class LiveCapacityPathTests(unittest.TestCase):
    def main_result(self,arguments,*,client_factory=None):
        output=io.StringIO()
        with redirect_stdout(output):flow.main(arguments,client_factory=client_factory)
        return json.loads(output.getvalue())

    def args(self,fixture,*extra):
        return ['--envelope',fixture.episode_binding['path'],'--assembly',fixture.assembly_binding['path'],*extra]

    def done(self,fixture,index,stage):
        return engine.driver._read_pair(fixture.root/'loop'/f'round-{index:04d}-{stage}.done.json')['output']

    def batch(self,fixture):
        return engine.read(engine.pin(fixture.paths['batch_root']/'batch.json'))

    def effective(self,path):
        return engine.read(engine.pin(Path(path)/'effective-capacity.json'))

    def read_receipt(self,path):
        values=[engine.read(engine.pin(p)) for p in Path(path).glob('01-tool-*.json')]
        result=next(value for value in values if value['call_id']=='read-long-filing')
        return entry.strict_json(result['output'])

    def assert_edges(self,fixture,replies):
        for index in (2,3):
            previous=self.done(fixture,index-1,'reconcile')
            safe=replies.controller_inputs[index-2]
            self.assertEqual(safe['feedback'],previous['feedback'])
            self.assertEqual(safe['feedback_sha256'],digest(previous))
            self.assertEqual(safe['parent_pair_sha256'],previous['pair_sha256'])
            packet=engine.read(engine.pin(fixture.root/f'packet-{index:02d}.json'))
            self.assertEqual(packet,safe)
            execute=self.done(fixture,index,'execute')
            self.assertEqual(execute['parent_state'],previous['state'])
            self.assertEqual(execute['consumed']['state_sha256'],previous['state']['sha256'])
            self.assertEqual(execute['consumed']['pair_sha256'],execute['pair_sha256'])
            physical=engine.read(engine.pin(Path(fixture.slots[index-1]['controller'])/'01-request.json'))
            self.assertEqual(json.loads(physical['payload']['input'][0]['content']),safe)
        first=self.done(fixture,1,'controller')
        self.assertEqual(engine.read(first['decision'])['axis'],'continue')
        self.assertNotIn('original',first)
        self.assertFalse(Path(fixture.slots[0]['controller']).exists())
        self.assertFalse(Path(fixture.slots[0]['author']).exists())
        self.assertEqual(len(replies.controller_inputs),2)
        self.assertEqual(self.done(fixture,1,'execute')['consumed']['state_sha256'],fixture.initial['sha256'])
        self.assertEqual(len(engine.read(self.done(fixture,1,'reconcile')['state'])['records']),1)

    def assert_cold(self,fixture,outcome):
        before=fixture.retained_tree();calls=len(fixture.raw.calls);factories=fixture.factory_calls
        args=['--envelope',fixture.episode_binding['path'],'--completed-replay',str(fixture.root/'completed-replay.json')]
        with ExitStack() as stack:
            spies=[stack.enter_context(patch.object(target,name,
                side_effect=AssertionError('Cold replay must not call '+name))) for target,name in (
                (live,'admit'),(assembly,'open_capacity_runtime'),(assembly,'_native'),
                (entry,'preflight_capacity_episode'),(clock,'capture_or_load'),(sqlite3,'connect'),
                (native.ContinuousDiscoveryBatch,'__init__'),(native.ContinuousDiscoveryBatch,'snapshot'),
                (engine.driver.c,'save'),(entry,'durable_json'))]
            replay=self.main_result(args)
        self.assertEqual(replay,outcome)
        for spy in spies:spy.assert_not_called()
        self.assertEqual(fixture.retained_tree(),before)
        self.assertEqual((len(fixture.raw.calls),fixture.factory_calls),(calls,factories))

    def test_actual_CLI_baseline_R_then_H_micro_adoption_next_use_and_cold_replay(self):
        fixture=LivePathFixture(self);replies=ScriptedMicroReplies(fixture)
        with fixture.actual_path(replies.sequence()) as admitted:
            outcome=self.main_result(self.args(fixture),client_factory=fixture.client_factory)
        self.assertEqual((outcome['status'],outcome['completed_rounds']),('completed',3))
        self.assertGreater(admitted.call_count,2)
        self.assertEqual(len(fixture.raw.calls),36)
        self.assertEqual(fixture.factory_calls,11)
        self.assertEqual(len(replies.author_inputs),2)
        for payload in replies.controller_payloads + replies.author_payloads:
            self.assertIn(controller.MICRO_INSTRUCTIONS,payload['instructions'])
        self.assert_edges(fixture,replies)
        snapshot=self.batch(fixture);micro=snapshot['micro_evolution'];history=micro['history']
        self.assertEqual(len(snapshot['capacity_work']),7)
        self.assertEqual([row['proposal']['axis'] for row in history],['researcher','harness'])
        self.assertEqual([row['review']['decision'] for row in history],['accept','accept'])
        self.assertEqual([row['review']['reason'] for row in history],['MATCHED_OPERATIONAL_BENEFIT']*2)
        self.assertIsNone(micro['pending'])
        self.assertEqual(micro['active_pair'],history[-1]['proposal']['pair'])
        for offset,index in enumerate((2,3)):
            chosen=replies.decisions[offset]
            authored=engine.read(engine.pin(Path(fixture.slots[index-1]['author'])/'response.json'))
            self.assertEqual(author_payload(authored),replies.authored[offset])
            spec=engine.read(engine.pin(Path(fixture.slots[index-1]['review'])/'response.json'))
            self.assertEqual(spec['proposal']['problem_evidence_sha256'],chosen['feedback_sha256'])
            self.assertIsNone(spec['review_receipt'])
            self.assertEqual((fixture.paths['source_root']/spec['entrypoints'][chosen['axis']]).read_bytes(),
                             replies.authored[offset]['source_text'].encode())
            for protected in ('K','M','C','memory_sha256','runtime_sha256'):
                self.assertEqual(spec['after'][protected],fixture.native['baseline'][protected])
            row=fixture.plan_rows[index-1];previous=self.done(fixture,index-1,'reconcile')
            for arm in ('parent','candidate','downstream'):
                effective=self.effective(row[arm])
                self.assertEqual(effective['initial_state']['sha256'],previous['state']['sha256'])
                self.assertEqual(entry.checked(effective['initial_state']),entry.checked(previous['state']))
                self.assertEqual('shadow' in effective,arm=='candidate')
            child=self.effective(row['candidate']);downstream=self.effective(row['downstream'])
            expected_pair=digest(history[offset]['proposal']['pair'])
            self.assertTrue(all(receipt['selected_pair_sha256']==expected_pair
                and receipt['shadow'] is False for receipt in downstream['context']['receipts']))
            self.assertTrue(all(receipt['selected_pair_sha256']==expected_pair
                and receipt['shadow'] is True for receipt in child['context']['receipts']))
            for arm in ('candidate','downstream'):
                payload=engine.read(engine.pin(Path(row[arm])/'01-request.json'))['payload']
                self.assertTrue(any(RULE in item.get('content','') for item in payload['input']))
            self.assertEqual(engine.read(engine.pin(Path(row['downstream'])/'score.json'))['score_out_of_5'],5)
        Rrow,Hrow=fixture.plan_rows[1],fixture.plan_rows[2]
        self.assertEqual(len(self.read_receipt(Rrow['downstream'])['text']),20000)
        self.assertEqual(len(self.read_receipt(Hrow['parent'])['text']),20000)
        for arm in ('candidate','downstream'):
            observed=self.read_receipt(Hrow[arm]);self.assertEqual(len(observed['text']),18000)
            self.assertEqual(observed['next_offset'],18000)
            request=engine.read(engine.pin(Path(Hrow[arm])/'01-response.json'))
            read=next(call for call in request['output'] if call.get('name')=='read_file')
            self.assertEqual(json.loads(read['arguments'])['characters'],20000)
        diag=replies.controller_inputs[1]['feedback']['research_diagnostics']['review']
        self.assertEqual((diag['verdict'],diag['metric'],diag['score_delta']),('accept','input_tokens',0))
        self.assertLessEqual(diag['observed_delta'],-1)  # Deliberately scripted usage, not a real gain.
        rows=fixture.ledger_rows()
        self.assertEqual(len(rows)-fixture.runtime['baseline']['request_count'],18)
        self.assertTrue(all(row[4]=='settled' for row in rows))
        self.assertTrue(all(payload['reasoning']=={'effort':'max'} for _,payload in fixture.raw.calls))
        retained=engine.read(engine.pin(fixture.root/'completed-replay.json'))
        terminal=engine.read(retained['runtime_terminal'])
        self.assertEqual(terminal['status'],'COMPLETED_COMPONENT_CONTEXT')
        self.assertEqual(terminal['budget_summary']['night_cap_usd'],10)
        self.assertEqual(terminal['budget_summary']['unresolved_reserved_usd'],0)
        self.assertFalse(terminal['budget_summary']['blocked'])
        self.assertFalse(retained['claims']['predictive_gain'])
        self.assertFalse(retained['claims']['model_authorship'])
        self.assertTrue(all(connection.closed for connection in fixture.raw.connections))
        self.assert_cold(fixture,outcome)

    def test_valid_R_no_matched_benefit_is_rejected_then_continue_retains_parent(self):
        fixture=LivePathFixture(self)
        replies=ScriptedMicroReplies(fixture,axes=('R','continue'),scripted_R_benefit=False)
        with fixture.actual_path(replies.sequence()):
            outcome=self.main_result(self.args(fixture),client_factory=fixture.client_factory)
        self.assertEqual((outcome['status'],outcome['completed_rounds']),('completed',3))
        self.assertEqual(len(fixture.raw.calls),26)
        self.assertEqual(fixture.factory_calls,8)
        self.assertEqual(len(replies.author_inputs),1)
        self.assert_edges(fixture,replies)
        snapshot=self.batch(fixture);micro=snapshot['micro_evolution']
        self.assertEqual(len(snapshot['capacity_work']),5)
        self.assertEqual(len(micro['history']),1)
        self.assertEqual(micro['history'][0]['review']['decision'],'reject')
        self.assertEqual(micro['history'][0]['review']['reason'],'NO_MATCHED_BENEFIT')
        self.assertEqual(micro['active_pair'],micro['anchor_pair'])
        self.assertIsNone(micro['pending'])
        candidate=self.effective(fixture.plan_rows[1]['candidate'])
        self.assertTrue(any(RULE in item.get('content','') for item in candidate['context']['messages']))
        for index in (2,3):
            downstream=self.effective(fixture.slots[index-1]['forecast'])
            self.assertFalse(any(RULE in item.get('content','') for item in downstream['context']['messages']))
            self.assertNotIn('shadow',downstream)
            self.assertTrue(all(receipt['selected_pair_sha256']==digest(micro['anchor_pair'])
                for receipt in downstream['context']['receipts']))
        diag=replies.controller_inputs[1]['feedback']['research_diagnostics']['review']
        self.assertEqual((diag['verdict'],diag['reason']),('reject','NO_MATCHED_BENEFIT'))
        self.assertEqual(diag['observed_delta'],0)
        self.assertFalse(Path(fixture.slots[2]['author']).exists())
        self.assertFalse(Path(fixture.slots[2]['review']).exists())
        self.assert_cold(fixture,outcome)

    def test_unknown_effect_is_retained_rejected_without_shadow_or_fake_benefit(self):
        fixture=LivePathFixture(self)
        replies=ScriptedMicroReplies(fixture,axes=('R','continue'),unknown_R_effect=True)
        with fixture.actual_path(replies.sequence()):
            outcome=self.main_result(self.args(fixture),client_factory=fixture.client_factory)
        self.assertEqual((outcome['status'],outcome['completed_rounds']),('completed',3))
        self.assert_edges(fixture,replies)
        micro=self.batch(fixture)['micro_evolution']
        self.assertEqual(micro['history'][0]['review']['decision'],'reject')
        self.assertEqual(micro['history'][0]['review']['reason'],'UNKNOWN_EFFECT_SEMANTICS')
        self.assertFalse(Path(fixture.plan_rows[1]['parent']).exists())
        self.assertFalse(Path(fixture.plan_rows[1]['candidate']).exists())
        self.assertEqual(micro['active_pair'],micro['anchor_pair'])
        self.assertEqual(len(fixture.raw.calls),18)
        self.assert_cold(fixture,outcome)

    def test_schema3_CLI_preflight_has_no_owner_provider_native_or_mutation(self):
        fixture=LivePathFixture(self);before=fixture.retained_tree()
        with fixture.scope(),patch.object(live,'admit',
                side_effect=fixture.invented_task_source_accounting_admission) as admitted, \
                patch.object(assembly,'open_capacity_runtime',side_effect=AssertionError('No owner')) as owner, \
                patch.object(assembly,'_native',side_effect=AssertionError('No Native constructor')) as construct, \
                patch.object(entry,'credential',side_effect=AssertionError('No credentials')) as key:
            outcome=self.main_result(self.args(fixture,'--preflight-only'),client_factory=fixture.client_factory)
        self.assertEqual(outcome,{'status':'REAL_CAPACITY_ASSEMBLY_PREFLIGHT_PASS','new_provider_calls':0})
        self.assertGreater(admitted.call_count,0)
        for spy in (owner,construct,key):spy.assert_not_called()
        self.assertEqual(fixture.factory_calls,0)
        self.assertEqual(fixture.raw.calls,[])
        self.assertEqual(fixture.retained_tree(),before)


if __name__=='__main__':unittest.main()
