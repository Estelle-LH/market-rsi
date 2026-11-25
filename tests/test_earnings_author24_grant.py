"""Inert Author24 allocation authority; no real ledger, provider or window."""
from copy import deepcopy
import unittest
from unittest.mock import patch

import earnings_open_fresh_grant as fresh
import test_earnings_author22_context as previous


class Author24GrantTests(unittest.TestCase):
    def setUp(self):
        self.old=previous.Author22EntryTests(); self.old.setUp()
        self.addCleanup(self.old.doCleanups)
        self.body=deepcopy(self.old.body)
        opening=dict(fresh.BASELINE,max_rowid=5222,request_count=5222,
            charged_nano_usd=156869758400,rows_sha256='a'*64)
        self.body['continuation']['output_followthrough']={
            'human_authorization':fresh.AUTHOR24_AUTHORIZATION,
            'author_id':fresh.AUTHOR24_IDS[0],'forecast_id':fresh.AUTHOR24_IDS[1],
            'author_max_input_tokens':24000,'author_max_output_tokens':49152,
            'closed_author_review':deepcopy(fresh.AUTHOR22_CLOSURE),
            'allocation':{'opening':opening,'max_new_nano_usd':2_000_000_000,
                'author_id':fresh.AUTHOR24_IDS[0],'forecast_id':fresh.AUTHOR24_IDS[1]}}

    def test_new_two_is_cumulative_without_changing_old_allocation_or_fifty(self):
        self.assertEqual(self.old.old.f.policy(self.body),self.body)
        self.assertEqual(self.body['continuation']['allocation'],self.old.body['continuation']['allocation'])
        self.assertEqual(fresh.allocation(self.body)['max_new_nano_usd'],2_000_000_000)
        self.assertEqual(fresh.pilot_cap(self.body),21_326_993_400)
        self.assertEqual(self.body['baseline'],fresh.BASELINE)

    def test_strict_output_input_ids_two_cap_and_history(self):
        changes=[('human_authorization','yes'),('author_id',fresh.AUTHOR22_IDS[0]),
            ('forecast_id',fresh.AUTHOR22_IDS[1]),('author_max_input_tokens',24001),
            ('author_max_output_tokens',49152.0),('author_max_output_tokens',49153),
            ('closed_author_review',dict(fresh.AUTHOR22_CLOSURE,sha256='0'*64)),('extra',True)]
        for key,value in changes:
            body=deepcopy(self.body); body['continuation']['output_followthrough'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.old.old.f.policy(body)
        for value in (True,0,2_000_000_001):
            body=deepcopy(self.body); body['continuation']['output_followthrough']['allocation']['max_new_nano_usd']=value
            with self.subTest(cap=value),self.assertRaises(ValueError):self.old.old.f.policy(body)
        body=deepcopy(self.body); body['continuation']['allocation']['opening']['charged_nano_usd']-=1
        with self.assertRaises(ValueError):self.old.old.f.policy(body)
        body=deepcopy(self.body); del body['continuation']['successor']
        with self.assertRaises(ValueError):self.old.old.f.policy(body)

    def test_only_new_pair_can_validate_no_reopening_closed_twenty_or_twentytwo(self):
        self.old.old.f.body=deepcopy(self.body)
        for identifier in (*fresh.AUTHOR20_IDS,*fresh.AUTHOR22_IDS,*fresh.AUTHOR24_IDS):
            grant=dict(self.old.old.f.grant,id=identifier,
                root=str(self.old.root/'attempts'/identifier),additional_cap_nano_usd=fresh.pilot_cap(self.body),
                **{k:self.body['window'][k] for k in ('cutoff_utc','deadline_utc')})
            if identifier in fresh.AUTHOR24_IDS:self.assertEqual(self.old.old.f.validate(grant),self.body)
            else:
                with self.assertRaises(ValueError):self.old.old.f.validate(grant)


if __name__=='__main__':unittest.main()
