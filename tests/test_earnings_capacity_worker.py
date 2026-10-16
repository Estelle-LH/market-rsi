"""Actual forecaster with native profile and fact tools, but no real provider."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import edgar_forecast_openai as forecast
import earnings_capacity_worker as w
from market_rsi import digest
import test_earnings_capacity_adapter as capacity_fixture
import test_earnings_research_state as state_fixture


class CapacityWorkerTests(unittest.TestCase):
    def setUp(self):
        self.native = capacity_fixture.EarningsCapacityTests("test_earnings_reject_keeps_parent_and_history")
        self.native.setUp();self.addCleanup(self.native.doCleanups)
        self.data = state_fixture.ResearchStateTests("test_append_preserves_parent_and_old_history")
        self.data.setUp();self.addCleanup(self.data.doCleanups)
        self.root = self.native.root
        self.company = self.data.company
        self.rate = {"api_model":"gpt-6.1-sol","effort":"xhigh"}
        self.config = {"max_turns_per_company":3,"company_wall_seconds":30}
        self.requests = []

    def worker(self,state=None):
        return w.CapacityWorker(self.company,"fixture-task",self.native.restore(),
            digest(self.native.batch.snapshot()["micro_evolution"]["active_pair"]),self.root/"memory",state)

    def invoke(self,worker=None,*,fail=False):
        output=self.root/('forecast-'+str(len(list(self.root.glob('forecast-*')))))
        output.mkdir()
        def response(client,request,*unused,completion_request=None):
            self.requests.append(json.loads(json.dumps(request)))
            if worker is not None and len(self.requests)==1:
                result={"output":[{"type":"function_call","call_id":"save-fact", "name":"save_research_record",
                                   "arguments":json.dumps({"record_json":json.dumps(self.data.fact)})}]}
            else:
                if fail: raise RuntimeError("invented provider failure; no retry")
                result={"output":[{"type":"message","content":[{"type":"output_text","text":json.dumps({
                    "predictions":[{"target_id":"T001","predicted_value":100}]})}]}]}
            return (result,False) if completion_request is not None else result
        with patch.object(forecast,"budgeted_response",side_effect=response):
            return forecast.forecast(None,self.rate,self.config,self.company,None,output,capacity_worker=worker),output

    def test_forecast_calls_fact_tool_and_cold_next_worker_uses_record(self):
        worker=self.worker()
        result,output=self.invoke(worker)
        self.assertEqual(result["tool_calls"],1)
        self.assertEqual(worker.state["records"][0]["record"]["value"],100)
        effective=json.loads((output/'effective-capacity.json').read_text())
        self.assertEqual(effective['context']['receipts'][0]['selected_pair_sha256'],worker.pair)
        saved=json.loads((output/'research-state-output.json').read_text())['state']
        self.requests=[]
        cold=self.worker(saved)
        self.invoke(cold)
        note=json.loads(self.requests[0]['input'][1]['content'].split('\n',1)[1])
        self.assertEqual(note['records'][0]['record']['value'],100)
        self.assertEqual(cold.state_receipt['state_sha256'],saved['sha256'])

    def test_original_default_wire_and_tools_unchanged(self):
        self.invoke()
        self.assertEqual(self.requests[0]['input'],[{'role':'user','content':self.data.files['questions.md']}])
        self.assertEqual(self.requests[0]['tools'],forecast.TOOLS)
        self.assertNotIn('save_research_record',[x['name'] for x in self.requests[0]['tools']])

    def test_actual_selected_H_clamps_tool_execution_and_preserves_original_ceiling(self):
        old,new=self.native.propose('H')
        self.native.adapter.review(self.native.review_receipt(old,new),
                                  expected_state_sha256=self.native.batch.snapshot()['state_sha256'])
        worker=self.worker()
        # Source fixture is short; repeated text tests actual length/next offset.
        worker.tools.files['filings/old.md']='x'*5000
        result=worker.dispatch('read_file',{'path':'filings/old.md','offset':0,'characters':5000})
        self.assertEqual((len(result['text']),result['next_offset']),(1000,1000))
        with self.assertRaises(ValueError):
            worker.dispatch('read_file',{'path':'filings/old.md','offset':0,'characters':20001})

    def test_failure_keeps_saved_fact_and_request_receipts_no_automatic_retry(self):
        worker=self.worker()
        with self.assertRaisesRegex(RuntimeError,'no retry'):self.invoke(worker,fail=True)
        self.assertEqual(len(self.requests),2)
        self.assertEqual(worker.state_api.load(worker.state_binding)['records'][0]['record']['value'],100)
        self.assertTrue(next(self.root.glob('forecast-*')).joinpath('01-tool-'+forecast.digest(b'save-fact')[:12]+'.json').exists())

    def test_selected_source_drift_refuses_before_provider_call(self):
        worker=self.worker()
        (self.root/'researcher_v1.py').write_text('import os\n')
        with self.assertRaises(ValueError):self.invoke(worker)
        self.assertEqual(self.requests,[])

    def test_unrelated_worker_and_competing_recipe_are_refused(self):
        worker=self.worker()
        output=self.root/'wrong';output.mkdir()
        with self.assertRaises(ValueError):
            forecast.forecast(None,self.rate,self.config,self.company,None,output,capacity_worker=object())
        changed=dict(self.company,cik='CIK0000000002')
        # Same content is not enough to bind another company context.
        with self.assertRaises(ValueError):
            forecast.forecast(None,self.rate,self.config,changed,None,output,capacity_worker=worker)
        with self.assertRaises(ValueError):
            w.CapacityWorker(changed,'fixture-task',self.native.adapter,worker.pair,self.root/'other',worker.state_binding)


if __name__=='__main__':unittest.main()
