"""New-ID feedback-only bridge with invented history and owned fake HTTP.

Real09 pins and policy are patched ONLY for these temporary synthetic records.
No original ledger, financial data, provider credential, Docker or scorer used.
"""
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import earnings_controller_handoff as handoff
import earnings_capacity_runtime as runtime
import earnings_clock as clock
import earnings_live_capacity as live
import earnings_open_fresh_grant as fresh
from earnings_open_roles import OpenAuthor
from earnings_open_task import OpenTask
import earnings_open_researcher as researcher
from earnings_open_code import DockerRunner
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_capacity_controller_transport as fixture


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.home=Path(self.stack.enter_context(tempfile.TemporaryDirectory())).resolve()
        self.f=fixture._TransportFixture(self,self.home/'transport')
        self.f.budget.close()
        self.stack.enter_context(patch.object(handoff,'ROOT',self.home))
        self.stack.enter_context(patch.object(clock,'boot_id',return_value='11111111-1111-4111-8111-111111111111'))
        oldroot=self.home/'attempts'/handoff.PRIOR;oldroot.mkdir(parents=True)
        self.cutoff=datetime.fromtimestamp(time.time()+180,timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        deadline=datetime.fromtimestamp(time.time()+240,timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        self.old={'id':handoff.PRIOR,'root':str(oldroot),'source_commit':'a'*40,
            'ledger':str(self.f.ledger),'baseline':self.f.baseline,
            'cutoff_utc':self.cutoff,'deadline_utc':deadline,
            'rates':dict(self.f.rates,effort='max')}
        clock.capture_or_load(oldroot,{'source_commit':self.old['source_commit'],
            'new_request_cutoff_utc':self.cutoff,'deadline_utc':deadline})
        (oldroot/'loop').mkdir()
        self.stack.enter_context(patch.object(handoff,'PIN_CLOCK_SEAL',engine.pin(oldroot/'clock.binding.json')['sha256']))
        save=lambda name,body:engine.save(self.home/name,body)
        old_runtime=save('old-runtime.json',self.old)
        marker=save('invented-protected-marker.json',{'synthetic':True})
        python={'path':str(Path(handoff.e.sys.executable).absolute()),
            'sha256':handoff.e.digest(Path(handoff.e.sys.executable).read_bytes())}
        grant=save('old-grant.json',dict({key:marker for key in ('data','runtime','qa','scorer')},python=python,sources={}))
        episode=save('old-episode.json',{'id':handoff.PRIOR,'grant':grant})
        self.stack.enter_context(patch.object(handoff,'PIN_EPISODE',episode['sha256']))
        ownerdir=self.f.ledger.parent/'.capacity-runtime-claims';ownerdir.mkdir()
        owner=engine.save(ownerdir/(handoff.e.digest(handoff.PRIOR.encode())+'.result.json'),{
            'status':'FAILED_NO_RETRY','retry_allowed':False,'runtime':old_runtime,
            'clock':engine.pin(oldroot/'clock.json'),
            'budget_summary':{'blocked':False,'unresolved_reserved_usd':0}})
        self.stack.enter_context(patch.object(handoff,'PIN_OWNER',owner['sha256']))
        nativehome=self.home/'native';(nativehome/'versions').mkdir(parents=True)
        (nativehome/'source').mkdir();(nativehome/'batch').mkdir()
        source={'R':"PROGRAM={'axis':'R'}\ndef run(p): return {}\n",
                'H':"PROGRAM={'axis':'H','tools':[]}\ndef run(p): return {}\n"}
        manifest={'components':{}}
        for axis,text in source.items():
            path=nativehome/'source'/(axis+'.py');path.write_text(text)
            manifest['components'][axis]={'sources':{path.name:engine.pin(path)['sha256']}}
        active={'researcher_sha256':'a'*64,'harness_sha256':'b'*64};pair=digest(active)
        selected=engine.save(nativehome/'versions'/(pair+'.json'),{
            'manifest':manifest,'entrypoints':{'R':'R.py','H':'H.py'}})
        self.stack.enter_context(patch.object(handoff,'PIN_SELECTED',selected['sha256']))
        native=engine.save(nativehome/'batch/batch.json',{'micro_evolution':{'active_pair':active,'pending':None}})
        self.stack.enter_context(patch.object(handoff,'PIN_NATIVE',native['sha256']))
        previous={'pair_sha256':pair,'feedback':{'target_scores':[{'target_id':'T001','points_awarded':0}],
            'observation':{'prediction':{'score_out_of_5':1,'planned_targets':5,'scored_targets':5}}}}
        reconciled=engine.save(oldroot/'loop/round-0001-reconcile.done.json',{'output':previous})
        packet={'task_id':handoff.PRIOR,'parent_pair_sha256':pair,'feedback_sha256':digest(previous),
            'parent_feedback_sha256':digest(previous),'feedback':previous['feedback'],'program_sources':source,
            'researcher_guidance':{'synthetic_advice':1},'guidance_execution':{'value':{'synthetic_advice':1}},
            'research_context':{'dispatch':{'synthetic_original_first_slot':True},'human_task':'Historical task'}}
        self.oldpacket=deepcopy(packet)
        old_packet=engine.save(oldroot/'terminal-controller-packet.json',packet)
        self.stack.enter_context(patch.object(handoff,'PIN_PACKET',old_packet['sha256']))
        self.value={'schema':'earnings_controller_feedback_handoff_v1','human_authorization':handoff.AUTHORIZATION,
            'id':'edgar-feedback-20261015-10','root':str(self.home/'attempts/edgar-feedback-20261015-10'),
            'source_commit':'c'*40,'old_runtime':old_runtime,'old_episode':episode,'old_packet':old_packet,
            'old_owner':owner,'old_selected':selected,'old_native':native,'old_reconciled':reconciled,
            'sources':{'tools/earnings_controller_handoff.py':engine.pin(handoff.__file__)}}
        self.spec={'schema':'earnings_capacity_runtime_v1','purpose':'controller_protocol',
            **{k:self.value[k] for k in ('id','root','source_commit')},
            **{k:self.old[k] for k in ('ledger','baseline','cutoff_utc','deadline_utc','rates')},
            'additional_cap_nano_usd':1_000_000_000,'limits':{'controller':handoff.role_limits()['controller']},
            'slots':{'controller':[str(Path(self.value['root'])/'roles/controller-01')]},
            'sources':{**{key:engine.pin(path) for key,path in runtime.CORE.items()},
                'factory_controller':engine.pin(handoff.__file__)},
            'feedback_handoff':save('handoff.json',self.value)}
        self.stack.enter_context(patch.object(fresh,'BASELINE',self.f.baseline))
        self.stack.enter_context(patch.object(fresh,'policy',return_value={'window':{
            'cutoff_utc':self.cutoff,'deadline_utc':deadline}}))
        self.stack.enter_context(patch.object(fresh,'pilot_cap',return_value=1_000_000_000))

    def bindings(self):
        runtime_binding=engine.save(self.home/'runtime.json',self.spec)
        review=engine.save(self.home/'review.json',{'verdict':'PASS_CONTROLLER_FEEDBACK_HANDOFF_ONLY',
            'blocking_findings':[],'reviewer':'distinct-invented-reviewer','runtime':runtime_binding,
            'reviewed_sources':self.value['sources']})
        return runtime_binding,review

    def test_single_owner_count_send_settle_consumes_feedback_and_inherits_original_clock(self):
        config,review=self.bindings();prompt=handoff.packet_view(self.value)
        self.f.prompt=prompt
        response=self.f.response(self.f.decision('continue'))
        with patch('earnings_http.http.client.HTTPSConnection',self.f.fake_connection(fixture._wire(response))), \
             patch.object(live,'provider_client',return_value=self.f.http), \
             patch.object(OpenTask,'packet',side_effect=AssertionError('No R rerun')), \
             patch.object(OpenAuthor,'author',side_effect=AssertionError('No Author')), \
             patch.object(handoff.e,'forecast',side_effect=AssertionError('No forecast or scorer')), \
             patch.object(researcher,'run',side_effect=AssertionError('No R execution')), \
             patch.object(DockerRunner,'run',side_effect=AssertionError('No container execution')):
            result=engine.read(handoff.run(config,review))
        self.assertFalse(result['decision_applied']);self.assertEqual(result['new_forecasts'],0)
        self.assertEqual([endpoint for endpoint,_ in self.f.calls],['/v1/responses/input_tokens','/v1/responses'])
        sent=handoff.e.strict_json(self.f.calls[-1][1]['input'][0]['content'])
        self.assertEqual(sent['feedback'],self.oldpacket['feedback'])
        self.assertEqual(sent['feedback_sha256'],self.oldpacket['feedback_sha256'])
        self.assertNotIn('dispatch',sent['research_context'])
        self.assertEqual(sent['historical_dispatch']['status'],'completed_original09_assignment_not_reissued')
        self.assertEqual(self.f.calls[-1][1]['tool_choice'],'none')
        self.assertFalse((Path(self.value['root'])/'clock.json').exists())
        context=engine.read(engine.pin(Path(self.value['root'])/'context-controller.json'))
        oldclock=engine.read(handoff.inherited_clock(self.spec)['binding'])
        self.assertEqual(context['cutoff_monotonic'],oldclock['cutoff_monotonic'])
        claims=self.f.ledger.parent/'.capacity-runtime-claims'
        terminal=engine.read(engine.pin(claims/(handoff.e.digest(self.spec['id'].encode())+'.result.json')))
        self.assertEqual(terminal['status'],'COMPLETED_COMPONENT_CONTEXT')
        self.assertEqual(terminal['budget_summary']['unresolved_reserved_usd'],0)
        with self.assertRaises(FileExistsError):handoff.run(config,review)
        self.assertEqual(len(self.f.calls),2)

    def test_generic_v1_still_refuses16k_without_exact_handoff_optin(self):
        self.spec.pop('feedback_handoff');config,_=self.bindings()
        with self.assertRaises(ValueError):runtime.preflight_runtime(config)

    def test_original_interpreter_alias_still_requires_exact_path_and_bytes(self):
        target=self.home/'invented-python-target';target.write_bytes(b'invented-runtime-bytes')
        alias=self.home/'invented-python';alias.symlink_to(target)
        binding={'path':str(alias),'sha256':handoff.e.digest(target.read_bytes())}
        with patch.object(handoff.e.sys,'executable',str(alias)):
            self.assertEqual(handoff.verify_current_python(binding),b'invented-runtime-bytes')
            with self.assertRaises(ValueError):
                handoff.verify_current_python(dict(binding,path=str(target)))
            target.write_bytes(b'changed-invented-runtime')
            with self.assertRaises(ValueError):handoff.verify_current_python(binding)

    def test_role_budget_model_window_factory_and_namespace_expansions_reject(self):
        for update in ({'purpose':'capacity_episode'},{'id':handoff.PRIOR},
                       {'additional_cap_nano_usd':2_000_000_000},{'cutoff_utc':'2099-01-01T00:00:00Z'},
                       {'rates':dict(self.spec['rates'],effort='high')},
                       {'limits':{'controller':dict(self.spec['limits']['controller'],max_input_tokens=16001)}}):
            with self.subTest(update=update),self.assertRaises(ValueError):
                handoff.validate_handoff(dict(self.spec,**update))

    def test_missing_review_refuses_before_owner_root_or_provider(self):
        config,review=self.bindings();body=engine.read(review);body['reviewer']='Root'
        bad=engine.save(self.home/'bad-review.json',body)
        with patch.object(live,'provider_client') as client,self.assertRaises(ValueError):handoff.run(config,bad)
        client.assert_not_called();self.assertFalse(Path(self.value['root']).exists())

    def test_generation_failure_preserves_settled_charge_and_closed_new_id(self):
        config,review=self.bindings();self.f.prompt=handoff.packet_view(self.value)
        response=self.f.response(self.f.decision('continue'));response['output']=[]
        with patch('earnings_http.http.client.HTTPSConnection',self.f.fake_connection(fixture._wire(response))), \
             patch.object(live,'provider_client',return_value=self.f.http),self.assertRaises(RuntimeError):
            handoff.run(config,review)
        self.assertEqual(len(self.f.calls),2)
        root=Path(self.value['root'])
        self.assertFalse((root/'handoff-result.json').exists())
        terminal=engine.read(engine.pin(self.f.ledger.parent/'.capacity-runtime-claims'/(
            handoff.e.digest(self.spec['id'].encode())+'.result.json')))
        self.assertEqual(terminal['status'],'FAILED_NO_RETRY')
        self.assertEqual(terminal['budget_summary']['unresolved_reserved_usd'],0)
        with self.assertRaises(FileExistsError):handoff.run(config,review)
        self.assertEqual(len(self.f.calls),2)

    def test_source_packet_and_original_clock_mutation_reject(self):
        config,_=self.bindings()
        Path(self.value['old_packet']['path']).write_bytes(b'{}')
        with self.assertRaises(ValueError):runtime.preflight_runtime(config)

    def test_original_clock_and_seal_drift_reject_before_owner(self):
        config,_=self.bindings()
        bound=handoff.inherited_clock(self.spec)['binding']
        seal=Path(bound['path']).with_name('clock.binding.json')
        seal.write_bytes(b'{}')
        with self.assertRaises(ValueError):runtime.preflight_runtime(config)

    def test_wrong_boot_rejected_by_existing_inherited_clock_validator(self):
        config,_=self.bindings()
        inherited=handoff.inherited_clock(self.spec)
        with patch.object(clock,'boot_id',return_value='22222222-2222-4222-8222-222222222222'),self.assertRaises(ValueError):
            clock.capture_or_load(Path(self.value['root']),{'source_commit':self.value['source_commit'],
                'new_request_cutoff_utc':self.cutoff,'deadline_utc':self.spec['deadline_utc'],
                'inherited_clock':inherited})


if __name__=='__main__':unittest.main()
