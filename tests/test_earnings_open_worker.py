"""Program worker protocol tests; synthetic source selection is not research gain."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import edgar_forecast_openai as forecast
from earnings_open_code import DockerRunner, encoded
from earnings_open_worker import ProgramWorker
from earnings_open_program import candidate
from earnings_open_source_review import ProgramSourceReview
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_open_capacity as native_fixture
import test_earnings_research_state as state_fixture


class ReceiptFixtureRunner:
    """No candidate code execution; write explicitly synthetic runner receipts."""
    blocked = False

    def __init__(self, root): self.root, self.calls = root, 0

    def run(self, source, payload):
        self.calls += 1
        path = self.root/str(self.calls);path.mkdir(parents=True)
        value = {'fixture_advice':'inspect units'} if payload.get('stage') == 'forecast' else {'value':95}
        request, stdout = encoded({'source':source,'payload':payload}), encoded({'ok':True,'value':value})
        for name, raw in [('input.json',request),('stdout.bin',stdout),('stderr.bin',b''),
                ('intent.json',encoded({'synthetic':True})),('create.stdout',b''),('create.stderr',b'')]:
            (path/name).write_bytes(raw)
        receipt = engine.save(path/'result.json', {'synthetic':True,'status':'COMPLETED',
            'cleanup_verified':True,'host_candidate_execution':False,'exit_code':0,
            'source_sha256':hashlib.sha256(source.encode()).hexdigest(),
            'input_sha256':hashlib.sha256(request).hexdigest(),
            'stdout_sha256':hashlib.sha256(stdout).hexdigest(),
            'stderr_sha256':hashlib.sha256(b'').hexdigest()})
        return {'value':value,'receipt':receipt}


class ProgramWorkerTests(unittest.TestCase):
    def setUp(self):
        self.native = native_fixture.ProgramCapacityTests('test_kernel_and_other_axis_preserved_in_program_proposal')
        self.native.setUp();self.addCleanup(self.native.doCleanups)
        self.data = state_fixture.ResearchStateTests('test_append_preserves_parent_and_old_history')
        self.data.setUp();self.addCleanup(self.data.doCleanups)
        self.root = self.native.root
        self.runner = ReceiptFixtureRunner(self.root/'runner')

    def worker(self, *, shadow=None, runner=None):
        return ProgramWorker(self.data.company,'fixture-task',self.native.restore(),
            digest(self.native.batch.snapshot()['micro_evolution']['active_pair']),
            self.root/'memory',runner=runner or self.runner,shadow_proposal_sha256=shadow)

    def pending_H(self, runner=None):
        properties = {'path':{'type':'string'}}
        definition = {'name':'extract_numbers','description':'Extract signed numerical values from one supplied filing',
            'parameters':{'type':'object','properties':properties,'required':['path'],'additionalProperties':False}}
        source = ('PROGRAM='+repr({'axis':'H','tools':[definition]})+'\nimport re\n'
            'def run(p):\n    return {"values":[float(x) for x in re.findall(r"-?\\d+",p["files"][p["arguments"]["path"]])]}\n')
        decision = {'schema':'earnings_capacity_decision_v1','axis':'H','component':'tool_interface',
            'parent_pair_sha256':digest(self.native.micro['pair']),'feedback_sha256':digest('fixture feedback'),
            'hypothesis':'Synthetic protocol test of a new extraction function','expected_effect':'Fixture extraction'}
        authored = {'decision_sha256':digest(decision),'source_text':source,
            'test_text':"CASES=[{'input':{'tool':'extract_numbers','arguments':{'path':'filings/test.md'},'files':{'filings/test.md':'100 -5'}},'expected':{'values':[100.0,-5.0]}}]"}
        decoded = candidate(authored,{'axis':'H','tools':[]},decision)
        descriptor = {'parent_identity':self.native.before,'parent_entrypoints':self.native.entries,
            'parent_pair_sha256':decision['parent_pair_sha256'],'decision_sha256':digest(decision),
            'candidate':engine.save(self.root/'candidate-H.json',decoded),
            'author_original':engine.save(self.root/'author-H.json',authored),
            'micro_evolution':self.native.batch.snapshot()['micro_evolution']}
        class CaseFixture:
            blocked=False
            def run(self,*args): return {'value':{'values':[100.0,-5.0]},'receipt':{'synthetic':True}}
        slot=str(self.root/'review-H')
        review=ProgramSourceReview(self.native.source,slots={slot:{'candidate_id':'fixture-H1','R':'R1.py','H':'H1.py'}},
            proposer_id='fixture-author',reviewer_id='host-reviewer',runner=runner or CaseFixture())
        spec=review.review(decision,authored,descriptor,slot)
        self.native.capacity.propose(spec['after'],spec['proposal'],spec['entrypoints'],
            static_review=spec['static_review'],expected_state_sha256=self.native.batch.snapshot()['state_sha256'])
        return self.native.batch.snapshot()['micro_evolution']['pending']['record_sha256']

    def test_next_cold_worker_reexecutes_R_and_binds_actual_request_context(self):
        first=self.worker();second=self.worker()
        self.assertEqual(self.runner.calls,2)
        self.assertNotEqual(first.r_execution['receipt'],second.r_execution['receipt'])
        self.assertEqual(first.context,second.context)
        requests=[];output=self.root/'forecast';output.mkdir()
        def response(client,request,*unused,completion_request=None):
            requests.append(json.loads(json.dumps(request)))
            result={'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps({
                'predictions':[{'target_id':'T001','predicted_value':100}]})}]}]}
            return (result,False) if completion_request is not None else result
        with patch.object(forecast,'budgeted_response',side_effect=response):
            forecast.forecast(None,{'api_model':'gpt-6.1-sol','effort':'xhigh'},
                {'max_turns_per_company':3,'company_wall_seconds':30},self.data.company,None,output,capacity_worker=second)
        self.assertIn('fixture_advice',requests[0]['input'][-1]['content'])
        self.assertTrue((output/'program-executions.json').is_file())
        second.context['messages'][-1]['content']='tampered'
        with self.assertRaisesRegex(ValueError,'drift'):second._check()

    def test_new_tool_definition_and_only_named_original_public_file(self):
        pending=self.pending_H();worker=self.worker(shadow=pending)
        self.assertIn('extract_numbers',[t['name'] for t in worker.definitions])
        result=worker.dispatch('extract_numbers',{'path':'filings/old.md'})
        self.assertEqual(result,{'value':95})
        supplied=worker.executions[-1]['input']['files']
        self.assertEqual(set(supplied),{'questions.md','filing_index.tsv','filings/old.md'})
        for path in ('../qa.json','/tmp/secret','filings/hidden.md'):
            with self.assertRaises(ValueError):worker.dispatch('extract_numbers',{'path':path})
        self.assertEqual(self.runner.calls,2)

    def test_receipt_or_source_drift_refused_before_next_call(self):
        worker=self.worker()
        root=Path(worker.r_execution['receipt']['path']).parent
        (root/'stdout.bin').write_bytes(b'{"ok":true,"value":"tampered"}')
        with self.assertRaisesRegex(ValueError,'differ'):worker._check()
        self.assertEqual(self.runner.calls,1)

    def test_inherited_original_tools_and_state_stay_usable(self):
        worker=self.worker()
        self.assertEqual(worker.dispatch('calculate',{'expression':'100 - 5'}),{'value':95})
        worker.dispatch('save_research_record',{'record_json':json.dumps(self.data.fact)})
        worker._check()
        self.assertEqual(len(worker.state['records']),1)
        worker.definitions.pop()
        with self.assertRaisesRegex(ValueError,'drift'):worker._check()

    @unittest.skipUnless(os.environ.get('EARNINGS_OPEN_DOCKER_TESTS')=='1','explicit Docker integration only')
    def test_actual_container_new_H_function_on_next_cold_worker(self):
        runner=DockerRunner(self.root/'actual-docker',max_calls=6)
        pending=self.pending_H(runner)
        first=self.worker(shadow=pending,runner=runner)
        self.assertEqual(first.dispatch('extract_numbers',{'path':'filings/old.md'}),{'values':[100.0,-5.0]})
        second=self.worker(shadow=pending,runner=runner)
        self.assertNotEqual(first.r_execution['receipt'],second.r_execution['receipt'])
        self.assertEqual(second.dispatch('extract_numbers',{'path':'filings/old.md'}),{'values':[100.0,-5.0]})
        self.assertEqual(len(second.executions),1)
        self.assertEqual(runner.calls,5)


if __name__=='__main__':unittest.main()
