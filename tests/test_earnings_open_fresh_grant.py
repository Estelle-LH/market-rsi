"""Inert follow-up authority boundaries; no real grant/ledger/QA/provider."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import earnings_open_fresh_grant as fresh


class FreshGrantTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.home=Path(temporary.name).resolve();self.path=self.home/'policy.json'
        self.body={'schema':'earnings_research_followup_authority_v1','human_authorization':fresh.AUTHORIZATION,
            'original_total_cap_nano_usd':200_000_000_000,'original_per_model_cap_nano_usd':100_000_000_000,
            'new_subgrant_nano_usd':50_000_000_000,'first_window_cap_nano_usd':5_000_000_000,
            'baseline':deepcopy(fresh.BASELINE),
            'scope':'Existing financial data/scorer/model/sole ledger, fresh IDs only; prior grants remain closed; no retries/refunds/purchases/pushes.',
            'window':{'issued_utc':'2026-10-15T01:00:00Z','cutoff_utc':'2026-10-15T02:30:00Z','deadline_utc':'2026-10-15T02:31:00Z'}}
        self.grant={'schema':fresh.SCHEMA,'human_authorization':fresh.AUTHORIZATION,
            'bootstrap_no_model_call':False,
            'allowed_egress':deepcopy(fresh.EGRESS),'id':'edgar-research-20261015-99',
            'root':str(self.home/'attempts'/'edgar-research-20261015-99'),
            'baseline':deepcopy(fresh.BASELINE),'additional_cap_nano_usd':5_000_000_000,
            **{k:self.body['window'][k] for k in ('cutoff_utc','deadline_utc')}}

    def policy(self,body=None):
        self.path.write_text(json.dumps(self.body if body is None else body))
        with patch.object(fresh,'CONFIG',self.path),patch.object(fresh,'ROOT',self.home):
            return fresh.policy()

    def validate(self,grant=None):
        self.path.write_text(json.dumps(self.body))
        with patch.object(fresh,'CONFIG',self.path),patch.object(fresh,'ROOT',self.home):
            return fresh.validate(self.grant if grant is None else grant)

    def test_new_fifty_allowance_does_not_raise_original_caps_or_first_five_window(self):
        self.assertEqual(self.validate(),self.body)
        self.assertEqual(self.body['original_total_cap_nano_usd'],200_000_000_000)
        for key,value in [('original_total_cap_nano_usd',250_000_000_000),
                ('original_per_model_cap_nano_usd',150_000_000_000),
                ('first_window_cap_nano_usd',50_000_000_000),('new_subgrant_nano_usd',51_000_000_000)]:
            with self.subTest(key=key),self.assertRaises(ValueError):self.policy(dict(self.body,**{key:value}))

    def test_unset_or_extended_window_is_not_dispatch_authority(self):
        invalid=[None,{},dict(self.body['window'],cutoff_utc='2026-10-15T02:30:01Z'),
            dict(self.body['window'],deadline_utc='2026-10-15T02:31:01Z'),
            dict(self.body['window'],issued_utc='2026-10-15T02:30:00Z')]
        for value in invalid:
            with self.subTest(window=value),self.assertRaises(ValueError):self.policy(dict(self.body,window=value))
        for key,value in [('cutoff_utc','2026-10-15T02:30:01Z'),('deadline_utc','2026-10-15T02:31:01Z')]:
            with self.subTest(key=key),self.assertRaises(ValueError):self.validate(dict(self.grant,**{key:value}))

    def test_old_id_old_root_old_schema_or_unapproved_egress_cannot_reopen(self):
        for key,value in [('id','edgar-open-20261014-04'),('schema','earnings_open_grant_v1'),
                ('human_authorization','yes'),('allowed_egress',['hidden_answers']),
                ('root',str(self.home/'old-root'))]:
            with self.subTest(key=key),self.assertRaises(ValueError):self.validate(dict(self.grant,**{key:value}))

    def test_prefix_and_first_window_cap_cannot_be_rebased_or_refunded(self):
        for key,value in [('baseline',dict(fresh.BASELINE,charged_nano_usd=0)),
                ('baseline',dict(fresh.BASELINE,max_rowid=4284)),
                ('additional_cap_nano_usd',5_000_000_001),('additional_cap_nano_usd',True)]:
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):self.validate(dict(self.grant,**{key:value}))
        body=deepcopy(self.body);body['baseline']['rows_sha256']='0'*64
        with self.assertRaises(ValueError):self.policy(body)

    def test_fresh_initial_controller_flag_is_exact_false_not_old_human_bootstrap(self):
        self.assertEqual(self.validate(),self.body)
        for value in (True,None,0,1,'False'):
            with self.subTest(flag=value),self.assertRaises(ValueError):
                self.validate(dict(self.grant,bootstrap_no_model_call=value))
        missing=deepcopy(self.grant);del missing['bootstrap_no_model_call']
        with self.assertRaises(ValueError):self.validate(missing)


if __name__=='__main__':unittest.main()
