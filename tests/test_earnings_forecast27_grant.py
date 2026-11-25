"""Inert27 successor: synthetic review/metadata only, no ledger or clock."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

import earnings_open_fresh_grant as fresh
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_forecast26_grant as previous


class Forecast27GrantTests(unittest.TestCase):
    def setUp(self):
        self.old=previous.Forecast26GrantTests();self.old.setUp();self.addCleanup(self.old.doCleanups)
        self.fixture=self.old.fixture;self.root=self.old.root
        self.body=deepcopy(self.old.body)
        self.body['window']=deepcopy(fresh.FORECAST26_WINDOW)
        self.body['forecast_recovery']['allocation']['opening']=deepcopy(fresh.FORECAST26_OPENING)
        self.review={'verdict':'VERIFIED_FORECAST26_CONTEXT_ADMISSION_FAILURE_NO_API',
            'reviewer':'independent-synthetic-reviewer','blocking_findings':[
                {'id':'F26-PROPOSAL-CONTEXT-MISMATCH'},{'id':'F26-PREFLIGHT-INTEGRATION-COVERAGE'}]}
        self.review_path=self.root/'FORECAST26-FAILURE-REVIEW.json'
        self.binding=engine.save(self.review_path,self.review)
        for name,value in (('FORECAST26_CLOSURE',self.binding),
                ('FORECAST26_NATIVE_CLOSURE_SHA',self.old.review['sha256'])):
            guard=patch.object(fresh,name,value);guard.start();self.addCleanup(guard.stop)
        self.body['candidate_transfer_authority']={'human_authorization':fresh.FORECAST27_AUTHORIZATION,
            'forecast_id':fresh.FORECAST27_ID,'closed_forecast_review':self.binding}

    def policy(self,body=None):return self.fixture.policy(self.body if body is None else body)

    def grant(self,identifier):
        return dict(self.fixture.grant,id=identifier,root=str(self.root/'attempts'/identifier),
            additional_cap_nano_usd=26_304_267_300,
            **{k:self.body['window'][k] for k in ('cutoff_utc','deadline_utc')})

    def test_only27_new_effective_id_preserves_all26_metadata_and_old_cost(self):
        before=deepcopy(self.body['forecast_recovery']);body=self.policy()
        self.assertEqual(fresh.effective_forecast_id(body),fresh.FORECAST27_ID)
        self.assertEqual(fresh.allocation(body),before['allocation'])
        self.assertEqual(fresh.allocation(body)['forecast_id'],fresh.FORECAST26_ID)
        self.assertEqual(fresh.pilot_cap(body),26_304_267_300)
        self.assertEqual(body['forecast_recovery'],before)
        self.fixture.body=deepcopy(body)
        for identifier in (*fresh.AUTHOR20_IDS,*fresh.AUTHOR22_IDS,*fresh.AUTHOR24_IDS,
                fresh.FORECAST26_ID,fresh.FORECAST27_ID,'edgar-research-20261016-28'):
            with self.subTest(identifier=identifier):
                if identifier==fresh.FORECAST27_ID:self.assertEqual(self.fixture.validate(self.grant(identifier)),body)
                else:
                    with self.assertRaises(ValueError):self.fixture.validate(self.grant(identifier))

    def test_old26_without_successor_stays_original_behavior(self):
        body=deepcopy(self.body);del body['candidate_transfer_authority']
        self.assertEqual(self.policy(body),body)
        self.assertEqual(fresh.effective_forecast_id(body),fresh.FORECAST26_ID)
        self.fixture.body=body
        self.assertEqual(self.fixture.validate(self.grant(fresh.FORECAST26_ID)),body)
        with self.assertRaises(ValueError):self.fixture.validate(self.grant(fresh.FORECAST27_ID))

    def test_no_clock_allocation_original_caps_or_recovery_mutation(self):
        variants=[]
        for key,value in (('human_authorization','yes'),('forecast_id',fresh.FORECAST26_ID),
                ('closed_forecast_review',dict(self.binding,sha256='0'*64)),('extra',True)):
            body=deepcopy(self.body);body['candidate_transfer_authority'][key]=value;variants.append(body)
        for key in ('issued_utc','cutoff_utc','deadline_utc'):
            body=deepcopy(self.body);body['window'][key]='2026-10-16T19:13:49Z';variants.append(body)
        for key,value in (('max_new_nano_usd',2_000_000_001),('max_new_nano_usd',1),
                ('forecast_id',fresh.FORECAST27_ID),('author_id',fresh.AUTHOR22_IDS[0])):
            body=deepcopy(self.body);body['forecast_recovery']['allocation'][key]=value;variants.append(body)
        for key,value in (('max_rowid',5420),('request_count',5418),('charged_nano_usd',161847032301),
                ('rows_sha256','0'*64)):
            body=deepcopy(self.body);body['forecast_recovery']['allocation']['opening'][key]=value;variants.append(body)
        for key in ('original_total_cap_nano_usd','original_per_model_cap_nano_usd','new_subgrant_nano_usd'):
            body=deepcopy(self.body);body[key]+=1;variants.append(body)
        body=deepcopy(self.body);del body['forecast_recovery'];variants.append(body)
        for index,body in enumerate(variants):
            with self.subTest(index=index),self.assertRaises(ValueError):self.policy(body)

    def test_distinct_diagnosis_retains_both_blockers_not_fake_pass(self):
        for change in ({'reviewer':'Root'},{'reviewer':'/root'},{'reviewer':' '},
                {'verdict':'PASS_TESTS_ONLY'},{'blocking_findings':[]},
                {'blocking_findings':[{'id':'F26-PROPOSAL-CONTEXT-MISMATCH'}]},
                {'blocking_findings':[{'id':'F26-PROPOSAL-CONTEXT-MISMATCH'},{'id':'OTHER'}]}):
            self.review_path.write_text(json.dumps(dict(self.review,**change)))
            binding=engine.pin(self.review_path);body=deepcopy(self.body)
            body['candidate_transfer_authority']['closed_forecast_review']=binding
            with self.subTest(change=change),patch.object(fresh,'FORECAST26_CLOSURE',binding),self.assertRaises(ValueError):
                self.policy(body)
        with self.assertRaises(ValueError):self.policy()  # Original review bytes remain bound.

    def test_pure_cumulative_runtime_only_accepts27_under_active_successor(self):
        self.policy()
        with patch.object(fresh,'CONFIG',self.fixture.path):
            for identifier in (fresh.FORECAST27_ID,fresh.FORECAST26_ID,fresh.AUTHOR24_IDS[0]):
                grant=dict(self.grant(identifier),ledger=str(self.root/'inert-ledger-not-opened'),
                    source_commit='a'*40,sources={
                        'configs/earnings_coevolution/research_followup_authority.json':engine.pin(self.fixture.path)['sha256']})
                study=engine.save(self.root/(identifier+'-study.json'),{'new_live_grant':
                    engine.save(self.root/(identifier+'-grant.json'),grant)})
                runtime=dict(grant,schema='earnings_capacity_runtime_v2',purpose='capacity_episode',forecast_study=study)
                with self.subTest(identifier=identifier):
                    if identifier==fresh.FORECAST27_ID:self.assertEqual(fresh.authorized_cumulative_cap(runtime),26_304_267_300)
                    else:
                        with self.assertRaises(ValueError):fresh.authorized_cumulative_cap(runtime)


if __name__=='__main__':unittest.main()
