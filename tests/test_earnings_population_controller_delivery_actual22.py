"""Opt-in original22→21→20→18 verification, read-only and no model/scorer.

No admission, fee, history, public-decoder or source check is mocked. Guards
deny writes/network/nondevelopment bodies and protected QA decoding.
"""
from contextlib import ExitStack
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
from unittest.mock import patch

import earnings_population_recovery as recovery
import earnings_population_tasks as tasks
from earnings_population_roles import decode_proposal
from supervisor_harness import capacity_feedback_engine as engine


@unittest.skipUnless(os.environ.get('MARKET_RSI_VERIFY_CONTROLLER_RAW22')=='1',
                     'Root-only guarded original22→21→20→18 and public proposal import')
class ActualControllerRaw22(unittest.TestCase):
    def test_original22_failed_owner_public_proposal_settlement_and_exact21_20_origin(self):
        tempfile.gettempdir()
        allowed={'CIK0000003545','CIK0000004457','CIK0000017313'};qa=set()
        resident,decode,database=tasks.resident,json.loads,sqlite3.connect
        def dev(cik):
            if cik not in allowed:raise AssertionError('No held-out resident')
            result=resident(cik);qa.add(result['kernel']['qa']['sha256']);return result
        def public(raw,*a,**kw):
            b=raw.encode()if isinstance(raw,str)else raw
            if isinstance(b,(bytes,bytearray))and hashlib.sha256(b).hexdigest()in qa:raise AssertionError('No QA decode')
            return decode(raw,*a,**kw)
        def readonly(function):
            def guarded(path,*a,**kw):
                mode=kw.get('mode',a[0]if a else'r')
                if type(mode)is str and any(c in mode for c in 'wax+'):raise AssertionError('No writes')
                if type(mode)is int and mode&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND):raise AssertionError('No writable fd')
                if not isinstance(path,int)and set(re.findall(r'CIK[0-9]{10}',os.fsdecode(path)))-allowed:raise AssertionError('No nondev')
                return function(path,*a,**kw)
            return guarded
        def ro_db(path,*a,**kw):
            if '?mode=ro'not in str(path)or kw.get('uri')is not True:raise AssertionError('Read-only SQLite')
            return database(path,*a,**kw)
        with ExitStack()as stack:
            stack.enter_context(patch.object(tasks,'resident',side_effect=dev));stack.enter_context(patch.object(json,'loads',side_effect=public))
            stack.enter_context(patch.object(sqlite3,'connect',side_effect=ro_db));stack.enter_context(patch.object(socket.socket,'connect',side_effect=AssertionError('No network')))
            for module in (builtins,io,os):stack.enter_context(patch.object(module,'open',readonly(module.open)))
            with recovery.history.validation_epoch():
                original_runtime = engine.read(engine.pin(recovery.resume.OWNED/
                    'inputs/edgar-population-20261016-23/runtime-reviewed.json'))
                self.assertEqual(original_runtime['source_commit'], '4c73652f14b26fd3d4845435d779984e5d124487')
                historical = recovery.history._Reader(recovery.resume.OWNED, recovery.resume.LEDGER,
                    recovery.resume.REPO, 'edgar-population-20261016-22')
                historical.commit = original_runtime['source_commit']
                historical.sources = {(b['path'],b['sha256']) for b in original_runtime['sources'].values()}
                value=recovery.load(engine.pin(recovery.resume.OWNED/'attempts/edgar-population-20261016-22/population-run-failure.json'),
                    root=recovery.resume.OWNED,ledger=recovery.resume.LEDGER,repo=recovery.resume.REPO,
                    plan_binding=original_runtime['sources'][recovery.PLAN], historical_reader=historical)
                bundle=value['controller_stage_import']
                self.assertFalse(bundle['new_model_called'])
                self.assertEqual(bundle['raw_response']['sha256'],'b245420b9264406d0243e5b43630e60386df614e1aae260333d161bb06b49c40')
                self.assertEqual(bundle['original_decision_public'],decode_proposal(
                    engine.read(bundle['raw_response']),engine.read(bundle['original_prompt'])))
                self.assertEqual(bundle['original_decision_public']['axis'],'R')
                self.assertEqual(value['recovery_context']['public_failed_delta_sha256'],
                    '995fa166e77b3d93cb5d32531dc39bd117802d6b28af157cfc268cc0d952472e')
                self.assertEqual(value['recovery_context']['input_delivery_diagnosis']['observed_input_tokens'],[66307,67013])
                self.assertEqual(value['last_scored_feedback']['sha256'],
                    '170098840c76fd15e192b626526baede6a9d5214e762a73a27cd580f4a8a46b9')
                self.assertEqual(recovery.latest_failed_attempt(value),bundle['failed_attempt'])
                self.assertNotIn('author_stage_reuse',value)
                old=recovery.resume.OWNED/'attempts/edgar-population-20261016-22/roles/controller-01'
                self.assertEqual(engine.read(engine.pin(old/'result.json'))['status'],'FAILED_NO_RETRY')
                self.assertFalse((old/'08-response.json').exists())
                self.assertFalse((old/'decision.json').exists())


if __name__=='__main__':unittest.main()
