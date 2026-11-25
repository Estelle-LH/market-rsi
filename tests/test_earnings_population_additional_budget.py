"""Offline synthetic SQLite. No production writes, model, scorer or network.

Old400 Git/ledger proof is the disclosed existing fixture; real old named300
and new additional100 activation/reservation code executes on temporary files.
"""
from contextlib import closing
from copy import deepcopy
import hashlib
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

import earnings_population_additional_budget as a
import earnings_population_model_budget as m
import earnings_population_budget as p
from test_earnings_population_model_budget import Fixture,G


class AdditionalFixture(Fixture):
    def __init__(self):
        original_repo=p.REPO
        super().__init__()
        self.old_model=self.activate()
        self.old_model_bytes=Path(self.old_model['path']).read_bytes()
        self.financial_authority=dict(schema='edgar25_additional100_financial_authority_v1',grant_id=a.GRANT,
            direct_human=a.HUMAN,sole_ledger=str(self.ledger),**a.TERMS,
            preserve_legacy_config_and_grants=True,explicit_prospective_optin_required=True,
            no_reset_refund_reactivation_or_resource_change=True,heldout_authorized=False)
        self.financial_file=self.repo/a.PLAN
        self.write_financial_authority()
        for name in set(a.IMPLEMENTATIONS)|set(m.IMPLEMENTATIONS):
            target=self.repo/name;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes((original_repo/name).read_bytes())
        prior=p._git
        def git(commit,name):
            if name==a.PLAN or name in a.IMPLEMENTATIONS:
                if commit!=self.commit:raise ValueError('Unknown fixture commit')
                return (self.repo/name).read_bytes()
            return prior(commit,name)
        self.patch(p,'_git',git)

    def write_financial_authority(self):
        self.financial_file.write_bytes(p._encoded(self.financial_authority))
        self.financial_bound=p._pin(self.financial_file)

    def expand(self):
        return a.activate(self.ledger,authority_binding=self.financial_bound,source_commit=self.commit,expected_prefix=self.snapshot())

    def expanded_budget(self,optin=None,**kw):
        import time
        return a.AdditionalBudget(self.ledger,additional_amendment_binding=a.binding() if optin is None else optin,
            amendment_binding=p.amendment_binding(),model_amendment_binding=m.binding(),baseline=self.snapshot(),
            deadline_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime(time.time()+3000)),
            additional_cap_nano_usd=kw.get('amount',5*G))


class AdditionalBudgetTests(unittest.TestCase):
    def setUp(self):self.f=AdditionalFixture();self.addCleanup(self.f.close)

    def test_activate_once_original_config_grants_requests_reconciliations_unchanged(self):
        before=self.f.snapshot();bound=self.f.expand()
        self.assertEqual(before,self.f.snapshot())
        self.assertEqual(self.f.old_model_bytes,Path(self.f.old_model['path']).read_bytes())
        self.assertEqual(self.f.old_bytes,self.f.old_grant.read_bytes())
        with sqlite3.connect(self.f.ledger) as db:
            self.assertEqual(db.execute('SELECT * FROM config').fetchall(),[(1,400*G,100*G,0)])
            self.assertEqual(a.read_grant(db,required_binding=bound)['gpt61_ceiling_nano_usd'],400*G)
            self.assertEqual(m.read_grant(db)['new_model_cap_nano_usd'],300*G)
        with self.assertRaises(p.BudgetStop):self.f.expand()

    def test_no_optin_preserves_stage200_and_new_optin_extends_not_resets(self):
        self.f.expand();self.f.insert('old-stage-199',m.MODEL,199*G)
        with closing(self.f.budget(optin=True)) as b:
            with self.assertRaises(p.BudgetStop):b.reserve('old-dispatch',m.MODEL,2*G)
        with closing(self.f.expanded_budget()) as b:
            b.reserve('new',m.MODEL,G);b.check_reserved('new',m.MODEL,G);b.check_reserved('new',m.MODEL,G)
            with self.assertRaises(p.BudgetStop):b.reserve('another',m.MODEL,1)
            b.settle('new',G)
            self.assertEqual(b.summary()['cap_usd'],500)
            self.assertEqual(b.summary()['dispatch_model_caps_usd'],{m.MODEL:400,'other_models':100})
            with self.assertRaises(p.BudgetStop):b.reserve('new',m.MODEL,1)
        for bound in ({},dict(path='wrong',sha256='0'*64),False):
            with self.assertRaises(ValueError):self.f.expanded_budget(optin=bound)

    def test_stage300_global500_named400_other100_each_and_all_pending_count(self):
        bound=self.f.expand()
        projections=[(499*G,{m.MODEL:399*G,p.MODELS[0]:100*G}),
            (450*G,{m.MODEL:399*G,p.MODELS[0]:51*G}),
            (487*G,{m.MODEL:390*G,p.MODELS[0]:97*G}),
            (290*G,{m.MODEL:191*G,p.MODELS[0]:99*G})]
        for total,models in projections:
            selected=p.MODELS[0] if total==290*G else m.MODEL
            with self.subTest(total=total),sqlite3.connect(self.f.ledger) as db,patch.object(m,'_totals',return_value=(total,models)):
                with self.assertRaises(p.BudgetStop):a.dispatch_totals(db,selected,2*G,bound)
        self.f.insert('pending',m.MODEL,3*G,pending=True)
        with sqlite3.connect(self.f.ledger) as db:
            total,models=m._totals(db)
            self.assertEqual(total,self.f.stage['charged_nano_usd']+3*G)
            self.assertEqual(a.dispatch_totals(db,m.MODEL,3*G,bound,own_request='pending')[0],total-3*G)
            for own,model,amount in [('wrong',m.MODEL,3*G),('pending',p.MODELS[0],3*G),('pending',m.MODEL,3*G+1)]:
                with self.assertRaises(p.BudgetStop):a.dispatch_totals(db,model,amount,bound,own_request=own)

    def test_original_window5_and_settlement_overcharge_block_are_inherited(self):
        self.f.expand()
        with closing(self.f.expanded_budget()) as b:
            with self.assertRaises(p.BudgetStop):b.reserve('too-much',m.MODEL,5*G+1)
            b.reserve('tiny',m.MODEL,10)
            with self.assertRaises(p.BudgetStop):b.settle('tiny',11)
            with self.assertRaises(p.BudgetStop):b.active()
        with self.assertRaises(ValueError):self.f.expanded_budget(amount=5*G+1)

    def test_typed_authority_and_source_changes_refuse_before_grant_write(self):
        for key,value in [('gpt61_ceiling_nano_usd',400000000000.0),('heldout_authorized',True),
                          ('stage_additional_ceiling_nano_usd',True),('other_models_ceiling_nano_usd',400*G)]:
            before=deepcopy(self.f.financial_authority);self.f.financial_authority[key]=value;self.f.write_financial_authority()
            with self.subTest(key=key),self.assertRaises(ValueError):self.f.expand()
            self.f.financial_authority=before;self.f.write_financial_authority()
        self.assertFalse((self.f.root/a.NAME).exists())

    def test_pending_blocked_or_wrong_prefix_prevents_activation(self):
        self.f.insert('inflight',m.MODEL,1,pending=True)
        with self.assertRaises(p.BudgetStop):self.f.expand()
        with sqlite3.connect(self.f.ledger) as db:
            db.execute("DELETE FROM requests WHERE id='inflight'");db.execute('UPDATE config SET blocked=1')
        with self.assertRaises(p.BudgetStop):self.f.expand()
        self.assertFalse((self.f.root/a.NAME).exists())

    def test_preexisting_settled_stage_over200_cannot_be_legalized_by_new_grant(self):
        self.f.insert('old-illegal-stage201',m.MODEL,201*G)
        with self.assertRaises(p.BudgetStop):self.f.expand()
        self.assertFalse((self.f.root/a.NAME).exists())

    def test_old_model_authority_or_inherited_implementation_source_join_cannot_be_replaced(self):
        sources={name:p._pin(self.f.repo/name) for name in (m.PLAN,*m.IMPLEMENTATIONS)}
        with sqlite3.connect(self.f.ledger) as db:
            a.legacy_sources(db,sources,self.f.commit)
            for name in (m.PLAN,*m.IMPLEMENTATIONS):
                changed=deepcopy(sources);changed[name]=dict(changed[name],sha256='0'*64)
                with self.subTest(name=name),self.assertRaises(ValueError):a.legacy_sources(db,changed,self.f.commit)
        target=self.f.repo/m.IMPLEMENTATIONS[0];target.write_bytes(target.read_bytes()+b'\n# replaced\n')
        with self.assertRaises(ValueError):self.f.expand()
        self.assertFalse((self.f.root/a.NAME).exists())

    def test_file_before_sql_interrupt_is_not_retried_or_repaired(self):
        original=a.save_bytes
        def fail(path,raw):original(path,raw);raise RuntimeError('synthetic interruption')
        with patch.object(a,'save_bytes',side_effect=fail),self.assertRaises(RuntimeError):self.f.expand()
        self.assertTrue((self.f.root/a.NAME).exists())
        with self.assertRaises(p.BudgetStop):self.f.expand()

    def test_grant_sql_hash_and_old_prefix_tamper_refuse(self):
        self.f.expand();path=self.f.root/a.NAME;raw=path.read_bytes()
        path.write_bytes(raw+b' ')
        with sqlite3.connect(self.f.ledger) as db,self.assertRaises(p.BudgetStop):a.read_grant(db)
        path.write_bytes(raw)
        with sqlite3.connect(self.f.ledger) as db:
            db.execute("UPDATE requests SET charged=charged-1 WHERE id='gpt-prior'")
            with self.assertRaises(p.BudgetStop):a.read_grant(db)

    def test_rolling_terms_select_only_explicit_optin_and_old_modules_unchanged(self):
        from types import SimpleNamespace
        self.assertEqual(a.budget_caps(SimpleNamespace()),(400*G,200*G))
        self.assertEqual(a.budget_caps(SimpleNamespace(additional_amendment_binding={'fixture':True})),(500*G,300*G))
        self.assertEqual((p.CAP,m.NAMED,m.STAGE_CAP),(400*G,300*G,200*G))


if __name__=='__main__':unittest.main()
