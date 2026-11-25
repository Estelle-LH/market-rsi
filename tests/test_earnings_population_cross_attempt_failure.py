"""Cross-attempt source provenance, real projector and counted receiving path.

Portable saved executions are invented receipts, never candidate execution.
The opt-in actual12 tests read development-only originals; one receiving test
uses synthetic HTTP counts/generation and an independent temporary ledger.
Neither constitutes a live Controller, admission proof or a scored experiment.
"""
from contextlib import ExitStack, contextmanager
from copy import deepcopy
import builtins
import hashlib
import io
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

import earnings_open_roles as roles
import earnings_open_researcher as researcher
import earnings_population_broker as brokers
import earnings_population_campaign_context as contexts
import earnings_population_failure_context as failure
import earnings_population_services as services
import earnings_population_tasks as tasks
from earnings_open_resources import role_limits
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_population_after03_delivery as old_fixture
from test_earnings_capacity_controller_transport import _TransportFixture, _wire
import test_earnings_population_case as native_fixture

CAPITAL='CIK0000017313'
DEV={CAPITAL,'CIK0000003545','CIK0000004457'}
OWNED=tasks.ARTIFACTS/'edgar-population-20261016'


class CrossAttemptProjector(unittest.TestCase):
    def setUp(self):
        self.f=old_fixture.PublicFailureExamples();self.f.setUp();self.addCleanup(self.f.doCleanups)

    def inherited(self):
        path=self.f.owned/'attempts/edgar-population-20261016-98/roles/author-02/candidate.py'
        path.parent.mkdir(parents=True);path.write_bytes(Path(self.f.source['path']).read_bytes())
        self.f.source=engine.pin(path);return self.f.probe()

    def project(self,bound,source=None):
        with patch.object(researcher,'run',side_effect=AssertionError('No candidate execution')):
            return failure.project(bound,source_binding=source or self.f.source,company=self.f.company)

    def test_cross_attempt_and_different_author_round_preserve_original_receipts(self):
        bound=self.inherited();before=deepcopy(engine.read(bound));result=self.project(bound)
        self.assertEqual((result['source_attempt_id'],result['source_author_round']),('edgar-population-20261016-98','02'))
        self.assertEqual((result['execution_attempt_id'],result['execution_review_round']),('edgar-population-20261016-99','01'))
        self.assertEqual(result['source'],self.f.source);self.assertEqual(result['probe'],bound)
        self.assertEqual(result['original_request_count'],4);self.assertEqual(len(result['examples']),3)
        self.assertLessEqual(len(json.dumps(result,ensure_ascii=False).encode()),24576)
        self.assertEqual(engine.read(bound),before);self.assertFalse(self.f.data.marker.exists())

    def test_same_attempt_behavior_and_original_source_execution_joins_remain(self):
        bound=self.f.probe();result=self.project(bound)
        self.assertEqual(result['source_attempt_id'],result['execution_attempt_id'])
        self.assertEqual(result['source_author_round'],result['execution_review_round'])
        self.assertEqual(result['original_request_count'],4)

    def test_newly_repinned_wrong_source_cannot_relabel_original_execution(self):
        bound=self.inherited();path=Path(self.f.source['path']);path.write_text(path.read_text()+'\n# different bytes\n')
        with self.assertRaises(ValueError):self.project(bound,engine.pin(path))

    def test_foreign_QA_symlink_hardlink_and_oversize_refused_before_body(self):
        bound=self.inherited();root=self.f.owned/'attempts/edgar-population-20261016-97/roles'
        candidates=[self.f.data.qa,dict(self.f.source,path='/private/tmp/foreign/candidate.py')]
        for name,kind in (('author-01','symlink'),('author-02','hardlink'),('author-03','oversize')):
            path=root/name/'candidate.py';path.parent.mkdir(parents=True)
            if kind=='symlink':path.symlink_to(self.f.source['path'])
            elif kind=='hardlink':os.link(self.f.source['path'],path)
            else:path.write_bytes(b'x'*65537)
            candidates.append(engine.pin(path))
        with patch.object(failure,'checked',side_effect=AssertionError('No forbidden body read')):
            for source in candidates:
                with self.subTest(source=source['path']),self.assertRaises(ValueError):self.project(bound,source)

    def test_execution_receipts_stay_strictly_probe_attempt_owned(self):
        bound=self.inherited();probe=engine.read(bound);original=probe['execution']['receipt']
        other=self.f.owned/'attempts/edgar-population-20261016-98/code/call-00000000000000000000000000000002/result.json'
        other.parent.mkdir(parents=True);other.write_bytes(Path(original['path']).read_bytes())
        probe['execution']['receipt']=engine.pin(other)
        Path(bound['path']).write_text(json.dumps(probe));bound=engine.pin(Path(bound['path']))
        with self.assertRaisesRegex(ValueError,'binding required before read'):self.project(bound)


@contextmanager
def actual_read_guard(*,temporary_root=None):
    """Real originals read-only; optional receiver writes only its temp fixture."""
    tempfile.gettempdir();qa_hashes=set();stats={'opens':0,'residents':set(),'readonly_db':0}
    original_resident,original_json,original_db=tasks.resident,json.loads,sqlite3.connect
    original_os_open=os.open; descriptor_paths={}
    def resident(cik):
        if cik not in DEV:raise AssertionError('No non-development resident')
        stats['residents'].add(cik);v=original_resident(cik);qa_hashes.add(v['kernel']['qa']['sha256']);return v
    def guarded(fn):
        def opening(path,*args,**kwargs):
            mode=kwargs.get('mode',args[0] if args else 'r')
            writing=(isinstance(mode,str) and any(c in mode for c in 'wax+')) or (isinstance(mode,int) and mode&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
            if not isinstance(path,int):
                text=os.fsdecode(path)
                if set(re.findall(r'CIK[0-9]{10}',text))-DEV:raise AssertionError('No non-development body')
                actual=Path(text)
                if not actual.is_absolute():
                    base=descriptor_paths.get(kwargs.get('dir_fd'),Path.cwd())
                    actual=base/actual
                if writing and (temporary_root is None or not actual.is_relative_to(temporary_root)):
                    raise AssertionError('No production/historical writes')
            elif writing:
                actual=descriptor_paths.get(path)
                if actual is None or temporary_root is None or not actual.is_relative_to(temporary_root):
                    raise AssertionError('No writable descriptor outside owned temporary fixture')
            stats['opens']+=1;value=fn(path,*args,**kwargs)
            if fn is original_os_open:descriptor_paths[value]=actual
            return value
        return opening
    def decoding(raw,*args,**kwargs):
        data=raw.encode() if isinstance(raw,str) else raw
        if isinstance(data,(bytes,bytearray)) and hashlib.sha256(data).hexdigest() in qa_hashes:raise AssertionError('No QA decode')
        return original_json(raw,*args,**kwargs)
    def database(path,*args,**kwargs):
        if temporary_root is not None and Path(str(path).split('?')[0]).is_relative_to(temporary_root):
            return original_db(path,*args,**kwargs)
        if '?mode=ro' not in str(path) or kwargs.get('uri') is not True:raise AssertionError('No production ledger mutation')
        stats['readonly_db']+=1;return original_db(path,*args,**kwargs)
    with ExitStack() as stack:
        stack.enter_context(patch.object(tasks,'resident',side_effect=resident))
        stack.enter_context(patch.object(services,'resident',side_effect=resident))
        stack.enter_context(patch.object(json,'loads',side_effect=decoding))
        stack.enter_context(patch.object(sqlite3,'connect',side_effect=database))
        stack.enter_context(patch.object(socket.socket,'connect',side_effect=AssertionError('No real network')))
        stack.enter_context(patch.object(researcher,'run',side_effect=AssertionError('No code execution')))
        for module in (builtins,io,os):stack.enter_context(patch.object(module,'open',guarded(module.open)))
        yield stats


def actual12_context():
    runtime=engine.read(engine.pin(OWNED/'inputs/edgar-population-20261016-12/runtime-reviewed.json'))
    packet=engine.read(engine.pin(OWNED/'attempts/edgar-population-20261016-12/packet-01.json'))
    public=brokers.public_feedback(packet['feedback'],packet['population']['versions'])
    context=contexts.prepare(runtime,packet,public)
    return runtime,packet,public,context


@unittest.skipUnless(os.environ.get('MARKET_RSI_VERIFY_CROSS_ATTEMPT12')=='1','Explicit real12 read-only/context receiving opt-in')
class Actual12Context(unittest.TestCase):
    def test_actual_failed_packet_unmocked_projector_and_planning_view(self):
        with actual_read_guard() as stats:
            runtime,packet,public,context=actual12_context();evidence=context['failure_evidence_context']
            view=contexts.controller_view(context['research_context'])
            self.assertEqual(evidence['source_attempt_id'],'edgar-population-20261016-10')
            self.assertEqual(evidence['execution_attempt_id'],'edgar-population-20261016-11')
            self.assertEqual(evidence['source']['sha256'],'b3935bed3bfcbde0f7192a06d8bcaabafafbae4b75d6b498545c93556c689b0d')
            self.assertEqual(evidence['probe']['sha256'],'cbdf2182523b3fd3e9efacf56356380f653f009ea6b70a3f9349a5167c47fe07')
            self.assertEqual(context['feedback_binding']['sha256'],'f763d4fe26cf01e19a2c4ec1429f00d1c665e3794a9bcbd8296395f88da00097')
            self.assertIn('evidence-acquisition regression',public['exploration_review']['rationale'])
            self.assertTrue(evidence['examples']);self.assertLessEqual(len(json.dumps(evidence,ensure_ascii=False).encode()),24576)
            self.assertEqual(context['original_R_evidence_abi']['max_requests'],8)
            self.assertEqual(context['original_R_evidence_abi']['request_phases'],1)
            self.assertIsNone(context['repair_assignment'])
            self.assertEqual(view['observations']['public_failure_examples']['source'],evidence['source'])
            self.assertTrue(all(x['outer_public_context']['text_omitted_from_controller_view'] for x in view['observations']['public_failure_examples']['examples']))
        self.assertTrue(stats['opens']);self.assertLessEqual(stats['residents'],DEV)

    def test_original_Services_counted_transport_receives_real_unmocked_context(self):
        with tempfile.TemporaryDirectory(prefix='cross-attempt-receiver-') as name:
            root=Path(name).resolve()
            transport=_TransportFixture(self,root/'transport')
            transport.rates['effort']='max'
            slot=Path(transport.slots[0]);context=dict(transport.context,limits=role_limits()['controller'])
            context_binding=engine.save(root/'controller-context.json',context)
            native=native_fixture.PopulationCaseTests();native.setUp();self.addCleanup(native.doCleanups)
            # Native preparation writes only this independent inert fixture root.
            # Actual failed12 authority/admission is not mocked or replay-executed.
            with actual_read_guard() as stats:
                runtime,packet,public,expected=actual12_context()
                resident=tasks.resident(CAPITAL)
            state=packet['population'];stable=state['versions'][state['stable_id']]
            with actual_read_guard(temporary_root=root):
                case=native.prepare(resident=resident,version=stable,root=root/'native-case')
            owner=services.Services.__new__(services.Services)
            owner.runtime,owner.native_root=runtime,root/'native';owner.native_root.mkdir()
            owner.runner,owner.literature,owner.traces,owner.authored=Mock(),Mock(),{},{}
            owner.case=Mock(return_value=case)
            owner.contexts={'controller':(context_binding,{'budget':transport.budget,'client_factory':transport.factory})}
            chosen=dict(transport.decision('continue'),parent_pair_sha256=state['stable_id'],feedback_sha256=packet['parent_feedback_sha256'],retire_branch_id='none')
            generated=[];test=self
            class Connection:
                def __init__(self,host,timeout):
                    test.assertEqual(host,'api.openai.com');self.timeout=timeout
                def request(self,method,endpoint,body,headers):
                    test.assertEqual(method,'POST');self.endpoint=endpoint
                    transport.calls.append((endpoint,json.loads(body)))
                def getresponse(self):
                    if self.endpoint=='/v1/responses/input_tokens':raw=_wire({'input_tokens':20})
                    elif self.endpoint=='/v1/responses':
                        test.assertEqual(generated,[]);generated.append(True);raw=_wire(transport.response(chosen))
                    else:raise AssertionError('Unexpected invented endpoint')
                    return Mock(status=200,getheader=Mock(return_value='req_inert_context_receiver'),
                        read=Mock(side_effect=lambda limit:raw[:limit]))
                def close(self):pass
            with actual_read_guard(temporary_root=root),patch('earnings_http.http.client.HTTPSConnection',side_effect=Connection):
                decision=owner.controller(packet,str(slot))
                self.assertIsNone(owner.reused_author())
            payload=json.loads((slot/'01-request.json').read_text())['payload']
            prompt=json.loads([x for x in payload['input'] if x.get('role')=='user'][0]['content'])
            evidence=prompt['research_context']['observations']['public_failure_examples']
            self.assertEqual(evidence['source'],expected['failure_evidence_context']['source'])
            self.assertEqual(evidence['probe'],expected['failure_evidence_context']['probe'])
            self.assertEqual(prompt['feedback_binding'],packet['feedback'])
            self.assertEqual(prompt['feedback']['exploration_review']['rationale'],public['exploration_review']['rationale'])
            self.assertEqual(prompt['research_context']['observations']['current_public_diagnostics'],public['probes'])
            self.assertTrue(evidence['examples'][0]['outer_public_context']['read_arguments'])
            self.assertNotIn('repair_assignment',prompt)
            self.assertEqual(payload['text']['format']['schema']['properties']['axis']['enum'],['R','H','continue'])
            self.assertEqual(engine.read(decision)['axis'],'continue')
            self.assertEqual(len(generated),1)
            self.assertTrue(any(endpoint.endswith('input_tokens') for endpoint,_ in transport.calls))
            self.assertEqual(transport.budget.db.execute("SELECT status FROM requests WHERE id!='fixture-prior'").fetchall(),[('settled',)])
            self.assertFalse(native.marker.exists())


if __name__=='__main__':unittest.main()
