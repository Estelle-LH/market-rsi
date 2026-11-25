"""Offline transport integration, not a worker/model/Native/scorer execution.

The real CapacityForecast constructor runs through its slot/resource checks;
only its later live clock/kernel _check is explicitly mocked. Rebind metadata
uses saved public accepted68 bytes; Git read transport is an explicit unit seam.
No original evidence, ledger or candidate is modified or executed.
"""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import earnings_population_company_batch as batch
import earnings_population_clean_slate as clean
import earnings_population_runtime as runtime
from earnings_entry import CapacityForecast
from supervisor_harness import capacity_feedback_engine as e


def deny_network(event,args):
    if event in ('socket.connect','socket.bind'):raise AssertionError('OFFLINE: no network')
sys.addaudithook(deny_network)


class NeverPaid:
    def refused(self,*a,**kw):raise AssertionError('OFFLINE: budget/API not available')
    active=reserve=settle=uncertain=summary=refused


class SlotProjectionTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.root=Path(t.name).resolve()
        self.rates=dict(api_model='gpt-6.1-sol',effort='max',input='1.25',cached='0.125',write=None,output='10')
        self.limits=dict(max_input_tokens=100000,max_output_tokens=25000,wall_seconds=1800)
        self.resize(9)
        old=dict(models={'gpt-6.1-sol':self.rates},max_input_tokens=100000,max_output_tokens=25000,
            company_wall_seconds=1800,max_turns_per_company=24,request_timeout_seconds=600)
        self.prior=e.save(self.root/'prior.json',dict(config=old))
        self.scorer=e.save(self.root/'synthetic-scorer-binding.json',dict(synthetic=True))
        self.study=e.save(self.root/'study.json',dict(schema='earnings_coevolution_study_v1',
            model=dict(requested_model='gpt-6.1-sol',serving_snapshot='unknown',serving_snapshot_verified=False),
            prior_batch=self.prior,runtime_config=old,scorer=self.scorer))
        self.clock=e.save(self.root/'clock.json',dict(synthetic=True))

    def resize(self,n):
        self.ids=[f'CIK{i:010d}' for i in range(n)]
        self.slots=[str(self.root/'roles'/f'forecast-01-{i:02d}') for i in range(n)]
        self.value=dict(clean_slate_policy=clean.POLICY,clean_learning_round=3,
            clean_company_concurrency=batch.ROLLING8,source_commit='a'*40,root=str(self.root),
            companies=self.ids,slots=dict(forecast=self.slots),rates=self.rates,
            limits=dict(forecast=self.limits),cutoff_utc='2026-10-22T00:00:00Z')
        self.parent=dict(schema='earnings_capacity_forecast_transport_v1',source_commit='a'*40,
            root=str(self.root),slots=self.slots,rates=self.rates,limits=self.limits,
            cutoff_utc=self.value['cutoff_utc'],cutoff_monotonic=123.0)

    def constructor(self,context,name):
        b=e.save(self.root/name,context)
        # Not a claim of live guard acceptance: this seam follows the slot check.
        with patch.object(CapacityForecast,'_check',return_value=None):
            return CapacityForecast(b,budget=NeverPaid(),client_factory=NeverPaid().refused,
                study_binding=self.study,evaluation_kernel=dict(scorer=self.scorer),clock_binding=self.clock)

    def test_original_constructor_reproduces_queue9_legacy_failure(self):
        with self.assertRaisesRegex(ValueError,'Canonical unique declared forecast slots'):
            self.constructor(self.parent,'original-nine.json')

    def test_real_constructor_accepts_each_single_slot_for_9_and_25_queue(self):
        for n in (9,25):
            self.resize(n)
            for i,(company,slot) in enumerate(zip(self.ids,self.slots)):
                child=batch.company_forecast_context(self.value,self.parent,company,slot)
                self.assertEqual(child,dict(self.parent,slots=[slot]))
                obj=self.constructor(child,f'projected-{n}-{i}.json')
                self.assertEqual(obj.context['limits'],self.limits)
                self.assertEqual(obj.context['rates'],self.rates)
                self.assertFalse(Path(slot).exists())

    def test_legacy_constructor_limit_and_old_policy_are_not_relaxed(self):
        legacy=dict(self.value,clean_company_concurrency=batch.ROLLING)
        self.assertEqual(batch.company_forecast_context(legacy,self.parent,self.ids[0],self.slots[0]),self.parent)
        with self.assertRaises(ValueError):self.constructor(self.parent,'unchanged-legacy.json')

    def test_cross_company_or_changed_parent_resources_are_rejected(self):
        for key,other in [('source_commit','b'*40),('root',str(self.root/'other')),
                          ('cutoff_utc','2027-01-01T00:00:00Z'),('slots',self.slots[:-1]),
                          ('limits',dict(self.limits,wall_seconds=1801)),('rates',dict(self.rates,effort='high'))]:
            wrong=dict(self.parent,**{key:other})
            with self.subTest(key=key),self.assertRaises(ValueError):
                batch.company_forecast_context(self.value,wrong,self.ids[0],self.slots[0])
        with self.assertRaises(ValueError):batch.company_forecast_context(self.value,self.parent,self.ids[0],self.slots[1])
        for marker in (True,3.0,5):
            with self.assertRaises(ValueError):batch.company_forecast_context(dict(self.value,clean_learning_round=marker),self.parent,self.ids[0],self.slots[0])

    def test_actual_identity_must_consume_exact_projected_binding(self):
        parent=e.save(self.root/'context-forecast.json',self.parent);slot=self.slots[0];company=self.ids[0]
        (self.root/'company-contexts').mkdir()
        child=e.save(self.root/'company-contexts'/'forecast-01-00.json',
            batch.company_forecast_context(self.value,self.parent,company,slot))
        binding=dict(path=str(self.root/'runtime.json'),sha256='a'*64)
        record=e.save(self.root/'company-contexts'/'forecast-01-00-binding.json',dict(
            schema='earnings_clean_single_company_transport_v1',runtime=binding,company_id=company,
            slot=slot,parent=parent,projected=child,changed_fields=['slots']))
        Path(slot).mkdir(parents=True)
        identity=e.save(Path(slot)/'identity.json',dict(context=child))
        self.assertEqual(batch.company_context_evidence(binding,self.value,company,slot),[parent,child,record,identity])
        original=e.read
        with patch.object(e,'read',side_effect=lambda b:dict(context=parent) if b['path'].endswith('/identity.json') else original(b)):
            with self.assertRaisesRegex(ValueError,'actual consumption'):batch.company_context_evidence(binding,self.value,company,slot)


class ExecutionRebindTests(unittest.TestCase):
    def setUp(self):
        self.authority=runtime._local(clean.SLOT_REBIND_AUTHORITY)
        self.old=runtime._local(self.authority['accepted_descriptor'])
        closure=runtime._local(self.authority['accepted_closure']);self.old_runtime=runtime._local(closure['runtime'])
        self.sources=deepcopy(self.old_runtime['sources'])
        for name in self.authority['allowed_production_changes']:self.sources[name]=e.pin(clean.e.REPO/name)
        self.receipt=dict(schema='edgar25_single_slot_execution_rebind_v1',authority=clean.SLOT_REBIND_AUTHORITY,
            original_descriptor=self.authority['accepted_descriptor'],original_source_commit=self.old['source_commit'],
            new_source_commit='b'*40,sources=deepcopy(self.sources))
        self.rb=dict(path=str(clean.training.ROOT/'TRAIN25-CLEAN70-EXECUTION-REBIND.json'),sha256='c'*64)
        self.binding=dict(path=str(clean.training.ROOT/'TRAIN25-CLEAN70-REBIND-FROZEN-CANDIDATE.json'),sha256='d'*64)
        self.descriptor=dict(deepcopy(self.old),source_commit='b'*40,execution_rebind=self.rb)
        self.original_local=runtime._local

    def local(self,b):return deepcopy(self.receipt) if b==self.rb else self.original_local(b)

    def git(self,args,**kwargs):
        self.assertEqual(args[0],'git')
        if args[1]=='diff':raw='\n'.join(self.authority['allowed_production_changes']+self.authority['allowed_test_changes'])+'\n';return SimpleNamespace(stdout=raw)
        self.assertEqual(args[1],'show');revision,path=args[2].split(':',1)
        p=clean.training.ROOT/path.removeprefix('original/') if path.startswith('original/') else clean.e.REPO/path
        return SimpleNamespace(stdout=p.read_bytes())

    def verify(self,descriptor=None):
        with patch.object(runtime,'_local',side_effect=self.local),patch.object(clean.subprocess,'run',side_effect=self.git):
            return clean.slot_execution_rebind(self.binding,descriptor or self.descriptor)

    def test_accepted_R_H_and_original_review_are_preserved(self):
        v=self.verify();self.assertEqual(v['candidate'],self.old['candidate'])
        self.assertEqual(v['runtime']['source_commit'],self.old['source_commit'])
        self.assertEqual(v['task']['round2_origin'],self.old['parent_basis'])

    def test_rebind_and_authority_are_in_per_send_input_guards(self):
        with patch.object(e,'read',return_value=self.descriptor):
            self.assertEqual(clean.frozen_inputs(self.binding),[self.binding,self.rb,clean.SLOT_REBIND_AUTHORITY])
        with patch.object(e,'read',return_value=self.old):
            self.assertEqual(clean.frozen_inputs(self.binding),[self.binding])

    def test_candidate_resource_forecast_source_or_parent_substitution_refused(self):
        for key,other in [('candidate',dict(self.old['candidate'],id='0'*64)),
                          ('forecast_limits',dict(self.old['forecast_limits'],wall_seconds=1801)),
                          ('forecast_sources',{}),('parent_basis',self.rb),('proposal',self.rb)]:
            with self.subTest(key=key),self.assertRaises(ValueError):self.verify(dict(self.descriptor,**{key:other}))

    def test_unapproved_source_or_checkpoint_scope_refused(self):
        name='forecaster';self.receipt['sources'][name]=dict(self.sources[name],sha256='0'*64)
        with self.assertRaisesRegex(ValueError,'two approved adapter'):self.verify()
        self.receipt['sources']=deepcopy(self.sources)
        original=self.git
        def broad(args,**kw):
            if args[1]=='diff':return SimpleNamespace(stdout='tools/earnings_entry.py\n')
            return original(args,**kw)
        with patch.object(runtime,'_local',side_effect=self.local),patch.object(clean.subprocess,'run',side_effect=broad):
            with self.assertRaisesRegex(ValueError,'exceeds finite'):clean.slot_execution_rebind(self.binding,self.descriptor)

    def test_failed_original_cannot_be_declared_accepted(self):
        original=self.local
        def wrong(b):
            value=original(b)
            return dict(value,status='FAILED_NO_RETRY') if b==self.authority['accepted_closure'] else value
        with patch.object(runtime,'_local',side_effect=wrong),self.assertRaises(ValueError):
            clean.slot_execution_rebind(self.binding,self.descriptor)


if __name__=='__main__':unittest.main()
