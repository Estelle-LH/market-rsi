"""Portable overlay mechanics, not production grant/admission or paid readiness.

The inherited ModelFixture activates a TEMPORARY model grant, mocks original400
verification/Git/prefix identities explicitly, and keeps real dispatch/transaction
code. No production ledger, API, candidate, scorer, QA or company body is opened.
"""
from contextlib import closing
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

import earnings_population_budget as original
import earnings_population_model_budget as model
import earnings_population_panel_budget as panel
import earnings_population_training25 as training
from earnings_night_budget import NightBudget
from test_earnings_population_model_budget import Fixture as ModelFixture

G = 1_000_000_000


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(json.dumps(value,sort_keys=True,separators=(',',':')).encode())
    return dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())


class Fixture(ModelFixture):
    def __init__(self):
        super().__init__()
        self.activate()  # Synthetic ledger only; real model-grant validator thereafter.
        self.owned = self.root/'population'
        self.ident = 'edgar-population-20261016-37'
        self.directory = self.owned/'inputs'/self.ident
        self.patch(panel,'ROOT',self.owned)
        self.patch(training,'ROOT',self.owned)
        training_ids = sorted(training.KNOWN3 | {'CIK%010d'%n for n in range(1,23)})
        split = save(self.owned/'split.json',dict(schema='edgar_retrospective_prospectively_sealed_split_v1',
            status='FROZEN_RETROSPECTIVE_PROSPECTIVE_SEAL',historical_isolation_certified=False,
            training=training_ids,heldout=['CIK%010d'%n for n in range(100,125)]))
        self.patch(training,'SPLIT',Path(split['path']))
        self.patch(training,'SPLIT_SHA',split['sha256'])
        self.company = training_ids[0]
        self.overlay = save(self.owned/'TRAIN25-DIRECT-WINDOW50-AUTHORITY.json',dict(
            schema='earnings_training25_direct_panel_window_cap_authority_v1',
            Root_selected_window_cap_nano_usd=panel.PANEL_CAP,old_window_cap_nano_usd=panel.LEGACY_CAP,
            sole_ledger=str(self.ledger)))
        self.patch(panel,'AUTHORITY',self.overlay)
        descriptor = save(self.owned/'frozen.json',dict(schema='earnings_training25_frozen_panel_v1',
            policy=panel.POLICY,split=split))
        link = save(self.directory/'training-state-link.json',dict(split=split))
        self.window_path = self.directory/'frozen-panel-window.json'
        window = save(self.window_path,dict(schema='earnings_training25_frozen_panel_window_v1',
            policy=panel.POLICY,descriptor=descriptor,company_id=self.company))
        self.study = dict(training_state_link=link,panel_window_budget_authority=self.overlay,frozen_panel_policy=panel.POLICY,
            frozen_panel=descriptor,frozen_panel_window=window)
        self.study_bound = save(self.directory/'study.json',self.study)
        self.wall = 2_000_000_000
        self.mono = 100
        from datetime import datetime, timezone
        self.cutoff = datetime.fromtimestamp(self.wall+3600,timezone.utc).isoformat().replace('+00:00','Z')
        self.value = dict(schema='earnings_population_runtime_v1',id=self.ident,
            root=str(self.owned/'attempts'/self.ident),ledger=str(self.ledger),source_commit=self.commit,
            companies=[self.company],window_minutes=90,training_policy=training.POLICY,
            budget_amendment=original.amendment_binding(),model_budget_amendment=model.binding(),
            panel_window_budget_authority=self.overlay,frozen_panel_policy=panel.POLICY,
            frozen_panel=descriptor,frozen_panel_window=window,forecast_study=self.study_bound,
            additional_cap_nano_usd=panel.PANEL_CAP,baseline=self.snapshot(),cutoff_utc=self.cutoff,
            sources={panel.SOURCE:dict(path=str(Path(panel.__file__).resolve()),
                sha256=hashlib.sha256(Path(panel.__file__).read_bytes()).hexdigest())})
        self.runtime_path = self.directory/'runtime-reviewed.json'
        self.pin_runtime()

    def pin_runtime(self):
        self.runtime = save(self.runtime_path,self.value)
        return self.runtime

    def open(self, **changes):
        kwargs = dict(runtime_binding=self.runtime,baseline=self.value['baseline'],deadline_utc=self.cutoff,
            amendment_binding=self.value['budget_amendment'],model_amendment_binding=self.value['model_budget_amendment'],
            additional_cap_nano_usd=panel.PANEL_CAP,clock=lambda:self.wall,monotonic=lambda:self.mono)
        kwargs.update(changes)
        return panel.PanelBudget(self.ledger,**kwargs)

    def rows(self):
        with sqlite3.connect(self.ledger) as db:
            return db.execute('SELECT rowid,* FROM requests').fetchall()


class PanelBudgetTests(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()
        self.addCleanup(self.f.close)

    def test_absent_marker_is_exact_legacy5_without_reads(self):
        with patch.object(panel,'_read',side_effect=AssertionError('No overlay read')):
            self.assertEqual(panel.ceiling({}),5*G)
            self.assertEqual(panel.ceiling(dict(additional_cap_nano_usd=50*G)),5*G)
        for value in (None,[],True):
            with self.subTest(value=value),self.assertRaises(ValueError):panel.ceiling(value)

    def test_original_classes_and_global_constants_are_unchanged(self):
        self.assertEqual(model.WINDOW_CAP,5*G)
        with self.assertRaises(ValueError):self.f.budget(optin=True,amount=50*G)
        with self.assertRaises(ValueError):
            NightBudget(self.f.ledger,baseline=self.f.snapshot(),deadline_utc=self.cutoff(),additional_cap_nano_usd=50*G)
        expected = {'reserve','check_reserved','active','summary','settle','uncertain','close',
                    'transaction','reconcile_uncertain_at_ceiling'}
        self.assertTrue(all(getattr(panel.PanelBudget,name) is getattr(original.PopulationBudget,name) for name in expected))
        self.assertEqual(set(panel.PanelBudget.__dict__) & expected,set())

    def cutoff(self):return self.f.cutoff

    def test_original_constructor_receives_literal5_before_overlay_no_reservation(self):
        before = self.f.rows()
        actual = original.PopulationBudget.__init__
        seen = []
        def construct(instance,path,**kwargs):
            seen.append(kwargs['additional_cap_nano_usd'])
            self.assertNotIn('runtime_binding',kwargs)
            actual(instance,path,**kwargs)
            self.assertEqual(instance.additional_cap_nano_usd,5*G)
            self.assertEqual(self.f.rows(),before)
        with patch.object(original.PopulationBudget,'__init__',construct),closing(self.f.open()) as budget:
            self.assertEqual(seen,[5*G])
            self.assertEqual(budget.additional_cap_nano_usd,50*G)
            self.assertEqual(budget.summary()['night_cap_usd'],50)
        self.assertEqual(self.f.rows(),before)

    def test_real_inherited_reserve_check_settle_summary_no_config_or_grant_mutation(self):
        old = self.f.old_grant.read_bytes()
        grant = (self.f.root/model.NAME).read_bytes()
        baseline = self.f.snapshot()
        with closing(self.f.open()) as budget:
            budget.reserve('above-old5',model.MODEL,6*G)
            budget.check_reserved('above-old5',model.MODEL,6*G)
            budget.check_reserved('above-old5',model.MODEL,6*G)
            budget.settle('above-old5',6*G)
            summary = budget.summary()
            self.assertEqual(summary['night_charged_upper_bound_usd'],6)
            self.assertEqual(summary['dispatch_model_caps_usd'],{model.MODEL:300,'other_models':100})
            self.assertEqual(summary['night_cap_usd'],50)
            self.assertEqual(summary['model_cap_usd'],100)
        self.assertEqual(self.f.old_grant.read_bytes(),old)
        self.assertEqual((self.f.root/model.NAME).read_bytes(),grant)
        with sqlite3.connect(self.f.ledger) as db:
            self.assertEqual(db.execute('SELECT cap,model_cap,blocked FROM config').fetchone(),(400*G,100*G,0))
            self.assertEqual(original.history_snapshot(db,baseline['max_rowid']),baseline)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM reconciliations').fetchone(),(1,))

    def test_exact50_and_window50_plus1_boundary(self):
        with closing(self.f.open()) as budget:
            before = self.f.rows()
            with self.assertRaises(original.BudgetStop):budget.reserve('too-much',model.MODEL,50*G+1)
            self.assertEqual(self.f.rows(),before)
            budget.reserve('exact50',model.MODEL,50*G)
            budget.check_reserved('exact50',model.MODEL,50*G)
            budget.settle('exact50',50*G)
            with self.assertRaises(original.BudgetStop):budget.reserve('after50',model.MODEL,1)

    def test_malformed_overlay_refuses_before_backend(self):
        cases = [('panel_window_budget_authority',None),('panel_window_budget_authority',{}),
            ('frozen_panel_policy',None),('training_policy','ordinary'),('window_minutes',180),
            ('window_minutes',90.0),('companies',[self.f.company,self.f.company]),('companies',[]),
            ('additional_cap_nano_usd',50*G+1),('additional_cap_nano_usd',float(50*G)),
            ('budget_amendment',None),('model_budget_amendment',None)]
        for key,value in cases:
            with self.subTest(key=key,value=value):
                saved=deepcopy(self.f.value)
                self.f.value[key]=value;self.f.pin_runtime()
                with patch.object(original.PopulationBudget,'__init__',side_effect=AssertionError('Backend opened')):
                    with self.assertRaises((ValueError,TypeError)):self.f.open()
                self.f.value=saved;self.f.pin_runtime()

    def test_erased_overlay_or_companion_cannot_enter_panel_constructor(self):
        for key in ('panel_window_budget_authority','frozen_panel','frozen_panel_window'):
            saved=deepcopy(self.f.value);self.f.value.pop(key);self.f.pin_runtime()
            with self.subTest(key=key),patch.object(original.PopulationBudget,'__init__',side_effect=AssertionError('Backend opened')):
                with self.assertRaises(ValueError):self.f.open()
            self.f.value=saved;self.f.pin_runtime()

    def test_heldout_rejected_before_descriptor_body_and_backend(self):
        self.f.value['companies']=['CIK0000000100'];self.f.pin_runtime()
        descriptor=Path(self.f.value['frozen_panel']['path'])
        descriptor.unlink()
        with patch.object(original.PopulationBudget,'__init__',side_effect=AssertionError('Backend opened')):
            with self.assertRaisesRegex(ValueError,'Training admission'):self.f.open()

    def test_study_authority_missing_null_or_changed_refuses_before_backend(self):
        for replacement in ('missing',None,dict(path=self.f.overlay['path'],sha256='0'*64)):
            study=deepcopy(self.f.study)
            if replacement == 'missing':study.pop('panel_window_budget_authority')
            else:study['panel_window_budget_authority']=replacement
            self.f.value['forecast_study']=save(self.f.directory/'study.json',study)
            self.f.pin_runtime()
            with self.subTest(replacement=replacement),patch.object(original.PopulationBudget,'__init__',side_effect=AssertionError('Backend opened')):
                with self.assertRaisesRegex(ValueError,'companion'):self.f.open()

    def test_runtime_authority_alias_symlink_and_hardlink_refuse(self):
        alias=deepcopy(self.f.runtime);alias['path']=str(self.f.directory/'..'/self.f.ident/'runtime-reviewed.json')
        with self.assertRaises(ValueError):self.f.open(runtime_binding=alias)
        path=Path(self.f.overlay['path']);raw=path.read_bytes()
        target=path.with_name('target.json');path.rename(target);path.symlink_to(target)
        with self.assertRaises(ValueError):self.f.open()
        path.unlink();path.write_bytes(raw)
        hard=path.with_name('hard.json');os.link(path,hard)
        with self.assertRaisesRegex(ValueError,'single-link'):self.f.open()

    def test_source_and_same_size_runtime_or_authority_tamper_refuse(self):
        self.f.value['sources'][panel.SOURCE]['sha256']='0'*64;self.f.pin_runtime()
        with self.assertRaisesRegex(ValueError,'bytes differ'):self.f.open()
        self.f.value['sources'][panel.SOURCE]['sha256']=hashlib.sha256(Path(panel.__file__).read_bytes()).hexdigest()
        self.f.pin_runtime()
        with closing(self.f.open()) as budget:
            path=Path(self.f.overlay['path']);raw=path.read_bytes();stamp=path.stat()
            path.write_bytes(raw.replace(b'50000000000',b'50000000001',1))
            os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
            with self.assertRaisesRegex(ValueError,'bytes differ'):budget.reserve('authority-tamper',model.MODEL,1)
            path.write_bytes(raw)
            raw=self.f.runtime_path.read_bytes();stamp=self.f.runtime_path.stat()
            self.f.runtime_path.write_bytes(raw.replace(b'"window_minutes":90',b'"window_minutes":91'))
            os.utime(self.f.runtime_path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
            with self.assertRaisesRegex(ValueError,'bytes differ'):budget.reserve('runtime-tamper',model.MODEL,1)

    def test_original_pending_blocked_duplicate_unknown_and_operator_guards(self):
        with closing(self.f.open()) as budget:
            budget.reserve('own',model.MODEL,G)
            with self.assertRaises(original.BudgetStop):budget.reserve('second',model.MODEL,1)
            with self.assertRaises(original.BudgetStop):budget.check_reserved('wrong',model.MODEL,G)
            self.f.insert('foreign',model.MODEL,1,pending=True)
            with self.assertRaises(original.BudgetStop):budget.check_reserved('own',model.MODEL,G)
            with sqlite3.connect(self.f.ledger) as db:db.execute("DELETE FROM requests WHERE id='foreign'")
            budget.settle('own',G)
            with self.assertRaises(original.BudgetStop):budget.reserve('own',model.MODEL,1)
            with self.assertRaises(original.BudgetStop):budget.reconcile_uncertain_at_ceiling('own','a'*64)
            budget.reserve('unknown',model.MODEL,G);budget.uncertain('unknown')
            self.assertTrue(budget.summary()['blocked'])
            with self.assertRaises(original.BudgetStop):budget.reserve('after-unknown',model.MODEL,1)

    def test_stage200_and_other100_are_not_widened(self):
        self.f.insert('prior-stage199',model.MODEL,199*G)
        with closing(self.f.open()) as budget:
            with self.assertRaisesRegex(original.BudgetStop,'stage200'):budget.reserve('stage201',model.MODEL,2*G)
        with sqlite3.connect(self.f.ledger) as db:db.execute("DELETE FROM requests WHERE id='prior-stage199'")
        self.f.insert('other99',original.MODELS[0],29*G)
        with closing(self.f.open()) as budget:
            with self.assertRaises(original.BudgetStop):budget.reserve('other101',original.MODELS[0],2*G)

    def test_global400_and_named300_guards_with_explicit_liability_projection(self):
        with closing(self.f.open()) as budget:
            # Source-stage fixture already costs107.49 in other models; isolate
            # each subordinate limit using only an explicit dispatch projection.
            for total,same,cap in ((399*G,200*G,300*G),(350*G,299*G,300*G)):
                with self.subTest(total=total,same=same),patch.object(model,'dispatch_totals',return_value=(total,same,cap)):
                    with self.assertRaises(original.BudgetStop):budget.reserve('projected',model.MODEL,2*G)
            self.assertNotIn('projected',[row[1] for row in self.f.rows()])

    def test_deadline_and_instance_terms_cannot_be_renewed(self):
        with closing(self.f.open()) as budget:
            budget.additional_cap_nano_usd=51*G
            with self.assertRaises(original.BudgetStop):budget.reserve('mutated',model.MODEL,1)
            budget.additional_cap_nano_usd=50*G
            self.f.mono=3700
            with self.assertRaisesRegex(original.BudgetStop,'deadline'):budget.reserve('expired',model.MODEL,1)
        with self.assertRaises(ValueError):self.f.open(deadline_utc='2099-01-01T00:00:00Z')

    def test_post_initialize_recheck_failure_closes_without_new_rows(self):
        runtime=panel._runtime;seen=[];closed=[]
        def changed(bound):
            seen.append(1)
            if len(seen)>1:raise ValueError('fixture changed after initialization')
            return runtime(bound)
        actual_close=original.PopulationBudget.close
        def close(budget):closed.append(True);actual_close(budget)
        before=self.f.rows()
        with patch.object(panel,'_runtime',changed),patch.object(original.PopulationBudget,'close',close):
            with self.assertRaisesRegex(ValueError,'after initialization'):self.f.open()
        self.assertEqual(closed,[True]);self.assertEqual(self.f.rows(),before)

    def test_wrong_kwargs_refuse_before_backend(self):
        for change in ({'additional_cap_nano_usd':5*G},{'additional_cap_nano_usd':float(50*G)},
                {'additional_cap_nano_usd':True},{'baseline':{}},
                {'amendment_binding':None},{'model_amendment_binding':None}):
            with self.subTest(change=change),patch.object(original.PopulationBudget,'__init__',side_effect=AssertionError('Backend opened')):
                with self.assertRaises(ValueError):self.f.open(**change)

    def test_registered_historical_source_no_clock_readmission_exact_extra_only(self):
        import earnings_population_continuation as history
        value=deepcopy(self.f.value);raw=Path(panel.__file__).read_bytes()
        value['sources']={panel.SOURCE:dict(path=str(self.f.repo/panel.SOURCE),sha256=hashlib.sha256(raw).hexdigest())}
        value['cutoff_utc']='2000-01-01T00:00:00Z'
        reader=history._Reader(self.f.owned,self.f.ledger,self.f.repo,self.f.ident)
        reader.register_sources(value)
        with patch.object(history,'_git',return_value=raw) as git:
            self.assertEqual(panel.ceiling(value,historical_reader=reader),50*G)
            git.assert_called_once_with(self.f.repo,self.f.commit,panel.SOURCE)
        self.assertEqual(reader.extra,{Path(self.f.overlay['path'])})
        sibling=save(self.f.owned/'unrelated.json',{'never':'allowed'})
        with self.assertRaisesRegex(ValueError,'outside exact'):reader.read(sibling)
        unregistered=history._Reader(self.f.owned,self.f.ledger,self.f.repo,self.f.ident)
        with self.assertRaisesRegex(ValueError,'registered historical reader'):panel.ceiling(value,historical_reader=unregistered)
        with self.assertRaisesRegex(ValueError,'registered historical reader'):panel.ceiling(value,historical_reader=object())
        value['source_commit']='b'*40
        with self.assertRaisesRegex(ValueError,'registered historical reader'):panel.ceiling(value,historical_reader=reader)

    def test_historical_owned_artifact_cannot_impersonate_registered_helper_source(self):
        import earnings_population_continuation as history
        value=deepcopy(self.f.value);raw=Path(panel.__file__).read_bytes()
        bound=dict(path=str(self.f.repo/panel.SOURCE),sha256=hashlib.sha256(raw).hexdigest())
        value['sources']={panel.SOURCE:bound}
        reader=history._Reader(self.f.owned,self.f.ledger,self.f.repo,self.f.ident)
        reader.register_sources(value)
        fake=save(self.f.directory/'fake-source.json',{'not':'source'})
        value['sources'][panel.SOURCE]=fake
        with self.assertRaisesRegex(ValueError,'outside exact current or original checkout'):
            panel.ceiling(value,historical_reader=reader)
        self.assertEqual(reader.extra,set())


if __name__ == '__main__':unittest.main()
