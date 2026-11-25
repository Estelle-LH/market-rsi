"""Exact28 child metadata with synthetic reviews; no live ledger or window."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

import earnings_open_fresh_grant as fresh
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_forecast27_grant as previous


class Forecast28GrantTests(unittest.TestCase):
    def setUp(self):
        self.old=previous.Forecast27GrantTests();self.old.setUp();self.addCleanup(self.old.doCleanups)
        self.fixture=self.old.fixture;self.root=self.old.root
        self.legacy=deepcopy(self.old.body);self.body=deepcopy(self.legacy)
        self.reviews={};self.review_raw={}
        for name,filename,verdict in (
                ('FORECAST27_CLOSURE','synthetic27-closure.json',
                    'VERIFIED_FORECAST27_CONTEXT_LIMIT_FAILURE_SOURCE_TRANSFER_AND_AUTOCLOSURE'),
                ('FORECAST28_HEADROOM_REVIEW','synthetic28-headroom.json','PASS_FORECAST28_HEADROOM_OFFLINE_ONLY')):
            value={'verdict':verdict,'reviewer':'independent-synthetic-reviewer','blocking_findings':[]}
            path=self.root/filename;binding=engine.save(path,value)
            self.reviews[name]=(path,value,binding)
            self.review_raw[name]=path.read_bytes()
            guard=patch.object(fresh,name,binding);guard.start();self.addCleanup(guard.stop)
        self.body['forecast_headroom_authority']={
            'human_authorization':fresh.FORECAST28_AUTHORIZATION,'forecast_id':fresh.FORECAST28_ID,
            'closed_forecast_review':deepcopy(fresh.FORECAST27_CLOSURE),
            'headroom_review':deepcopy(fresh.FORECAST28_HEADROOM_REVIEW),
            'allocation':{'opening':{'max_rowid':5603,'request_count':5603,
                'charged_nano_usd':164_293_917_000,'rows_sha256':'a'*64},
                'max_new_nano_usd':2_000_000_000,'author_id':fresh.AUTHOR24_IDS[0],
                'forecast_id':fresh.FORECAST28_ID},
            'window':{'issued_utc':'2099-01-01T00:00:00Z','cutoff_utc':'2099-01-01T01:29:00Z',
                'deadline_utc':'2099-01-01T01:30:00Z'}}

    def policy(self,body=None):return self.fixture.policy(self.body if body is None else body)

    def grant(self,identifier):
        return dict(self.fixture.grant,id=identifier,root=str(self.root/'attempts'/identifier),
            additional_cap_nano_usd=fresh.pilot_cap(self.body),
            **{key:fresh.current_window(self.body)[key] for key in ('cutoff_utc','deadline_utc')})

    def test_new_child_chooses28_but_all_historical_fields_are_preserved(self):
        before=deepcopy(self.body);body=self.policy()
        self.assertEqual(body,before)
        self.assertEqual({k:v for k,v in body.items() if k!='forecast_headroom_authority'},self.legacy)
        self.assertEqual(fresh.effective_forecast_id(body),fresh.FORECAST28_ID)
        self.assertEqual(fresh.current_window(body),body['forecast_headroom_authority']['window'])
        self.assertEqual(body['window'],fresh.FORECAST26_WINDOW)
        self.assertEqual(body['forecast_recovery']['allocation']['forecast_id'],fresh.FORECAST26_ID)
        self.assertEqual(fresh.allocation(body),body['forecast_headroom_authority']['allocation'])
        self.assertEqual(fresh.pilot_cap(body),28_751_152_000)
        self.assertEqual((body['original_total_cap_nano_usd'],body['original_per_model_cap_nano_usd'],
            body['new_subgrant_nano_usd']),(200_000_000_000,100_000_000_000,50_000_000_000))

    def test_only28_validates_new_deadlines_no_old_id_or_author_reopening(self):
        self.fixture.body=deepcopy(self.body)
        for identifier in (*fresh.AUTHOR20_IDS,*fresh.AUTHOR22_IDS,*fresh.AUTHOR24_IDS,
                fresh.FORECAST26_ID,fresh.FORECAST27_ID,fresh.FORECAST28_ID,'edgar-research-20261016-29'):
            with self.subTest(identifier=identifier):
                if identifier==fresh.FORECAST28_ID:self.assertEqual(self.fixture.validate(self.grant(identifier)),self.body)
                else:
                    with self.assertRaises(ValueError):self.fixture.validate(self.grant(identifier))
        grant=self.grant(fresh.FORECAST28_ID)
        for change in ({'additional_cap_nano_usd':26_304_267_300},
                {'baseline':dict(fresh.BASELINE,charged_nano_usd=0)},
                {key:self.body['window'][key] for key in ('cutoff_utc','deadline_utc')}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                self.fixture.validate(dict(grant,**change))

    def test_without_child_legacy27_stays_exact_and28_not_admitted(self):
        self.assertEqual(self.policy(self.legacy),self.legacy)
        self.assertIsNone(fresh.forecast_headroom_authority(self.legacy))
        self.assertEqual(fresh.current_window(self.legacy),self.legacy['window'])
        self.assertEqual(fresh.effective_forecast_id(self.legacy),fresh.FORECAST27_ID)
        self.assertEqual(fresh.allocation(self.legacy),self.legacy['forecast_recovery']['allocation'])
        self.assertEqual(fresh.pilot_cap(self.legacy),26_304_267_300)
        self.fixture.body=deepcopy(self.legacy)
        with self.assertRaises(ValueError):self.fixture.validate(self.grant(fresh.FORECAST28_ID))

    def test_strict_child_schema_old27_chain_and_review_identity_required(self):
        variants=[]
        for key,value in (('human_authorization','yes'),('forecast_id',fresh.FORECAST27_ID),
                ('headroom_review',dict(fresh.FORECAST28_HEADROOM_REVIEW,sha256='0'*64)),
                ('closed_forecast_review',dict(fresh.FORECAST27_CLOSURE,sha256='0'*64)),('extra',True)):
            body=deepcopy(self.body);body['forecast_headroom_authority'][key]=value;variants.append(body)
        for key in ('candidate_transfer_authority','forecast_recovery'):
            body=deepcopy(self.body);del body[key];variants.append(body)
        body=deepcopy(self.body);body['candidate_transfer_authority']['forecast_id']=fresh.FORECAST28_ID;variants.append(body)
        for index,body in enumerate(variants):
            with self.subTest(index=index),self.assertRaises(ValueError):self.policy(body)

    def test_exact90_minutes_new_window_no_old_window_rewrite_or_time_extension(self):
        variants=[]
        for key,value in (('issued_utc',fresh.FORECAST26_WINDOW['deadline_utc']),
                ('issued_utc','2026-10-16T19:13:47Z'),('cutoff_utc','2099-01-01T01:29:01Z'),
                ('deadline_utc','2099-01-01T01:30:01Z'),('deadline_utc','2099-01-01T01:29:59Z')):
            body=deepcopy(self.body);body['forecast_headroom_authority']['window'][key]=value;variants.append(body)
        body=deepcopy(self.body);body['window']=deepcopy(body['forecast_headroom_authority']['window']);variants.append(body)
        body=deepcopy(self.body);body['forecast_headroom_authority']['window']['extra']=True;variants.append(body)
        for index,body in enumerate(variants):
            with self.subTest(index=index),self.assertRaises(ValueError):self.policy(body)

    def test_new_opening_allocation_cannot_refund_overspend_or_raise_original50(self):
        variants=[]
        for key,value in (('max_new_nano_usd',True),('max_new_nano_usd',0),('max_new_nano_usd',2_000_000_001),
                ('max_new_nano_usd',2_000_000_000.0),('author_id',fresh.AUTHOR22_IDS[0]),('forecast_id',fresh.FORECAST27_ID)):
            body=deepcopy(self.body);body['forecast_headroom_authority']['allocation'][key]=value;variants.append(body)
        for key,value in (('max_rowid',5602),('request_count',5602),('request_count',True),
                ('charged_nano_usd',164_293_916_999),('rows_sha256','bad')):
            body=deepcopy(self.body);body['forecast_headroom_authority']['allocation']['opening'][key]=value;variants.append(body)
        body=deepcopy(self.body)
        body['forecast_headroom_authority']['allocation']['opening']['charged_nano_usd']=(
            fresh.BASELINE['charged_nano_usd']+48_000_000_001)
        variants.append(body)
        for index,body in enumerate(variants):
            with self.subTest(index=index),self.assertRaises(ValueError):self.policy(body)
        body=deepcopy(self.body);body['forecast_headroom_authority']['allocation']['max_new_nano_usd']=1
        self.assertEqual(fresh.pilot_cap(self.policy(body)),26_751_152_001)

    def test_distinct_closed27_and_headroom_reviews_are_both_required(self):
        for name,(path,original,binding) in self.reviews.items():
            key='closed_forecast_review' if name=='FORECAST27_CLOSURE' else 'headroom_review'
            for change in ({'reviewer':'Root'},{'reviewer':'/root'},{'reviewer':' '},
                    {'verdict':'PASS_OTHER'},{'blocking_findings':['unresolved']}):
                path.write_text(json.dumps(dict(original,**change)));changed=engine.pin(path)
                body=deepcopy(self.body);body['forecast_headroom_authority'][key]=changed
                with self.subTest(name=name,change=change),patch.object(fresh,name,changed),self.assertRaises(ValueError):
                    self.policy(body)
            path.write_text(json.dumps(original))
            # A caller cannot substitute refreshed bytes without exact pinning.
            with self.subTest(name=name),self.assertRaises(ValueError):self.policy(self.body)
            path.write_bytes(self.review_raw[name])

    def test_pure_bound_runtime_cap_only_new28_and_exact_child_deadlines(self):
        self.policy()
        with patch.object(fresh,'CONFIG',self.fixture.path):
            for identifier in (fresh.FORECAST28_ID,fresh.FORECAST27_ID,fresh.AUTHOR24_IDS[0]):
                grant=dict(self.grant(identifier),ledger=str(self.root/'inert-ledger-not-opened'),source_commit='a'*40,
                    sources={'configs/earnings_coevolution/research_followup_authority.json':engine.pin(self.fixture.path)['sha256']})
                study=engine.save(self.root/(identifier+'-child-study.json'),{'new_live_grant':
                    engine.save(self.root/(identifier+'-child-grant.json'),grant)})
                runtime=dict(grant,schema='earnings_capacity_runtime_v2',purpose='capacity_episode',forecast_study=study)
                with self.subTest(identifier=identifier):
                    if identifier==fresh.FORECAST28_ID:self.assertEqual(fresh.authorized_cumulative_cap(runtime),28_751_152_000)
                    else:
                        with self.assertRaises(ValueError):fresh.authorized_cumulative_cap(runtime)


if __name__=='__main__':unittest.main()
