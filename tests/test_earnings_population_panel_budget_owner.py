"""Original owner/historical helper with explicit portable admission/Git seams.

No production ledger, full ancestry, Native, candidate, scorer or API is used.
The actual owner lock/clock/claim/contexts/budget/finally and temporary grants run;
preflight and role bodies are deliberately inert, not actual admission proof.
"""
from contextlib import ExitStack, closing, contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import inspect
from pathlib import Path
import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import earnings_capacity_runtime as owner
import earnings_clock as clock
import earnings_population_budget as original
import earnings_population_completed as completed
import earnings_population_continuation as history
import earnings_population_model_budget as model
import earnings_population_panel_budget as panel
from earnings_night_budget import NightBudget
from test_earnings_capacity_runtime import _Fixture as OrdinaryFixture, BOOT
from test_earnings_population_panel_budget import Fixture, G, save


def inert_factory(context_binding, *, budget, client_factory):
    return lambda *args:None  # Not a real Services/Native or model boundary.


def pin(path):
    path=Path(path).resolve()
    return dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def utc(value):return datetime.fromtimestamp(value,timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


class OwnerContracts(unittest.TestCase):
    def setUp(self):
        self.f=Fixture();self.addCleanup(self.f.close)
        f=self.f;root=Path(f.value['root'])
        f.value.update(purpose='capacity_episode',deadline_utc=utc(f.wall+3660),
            slots={role:[str(root/'roles'/(role+'-01'))] for role in ('controller','author','review','forecast')},
            limits={role:dict(max_input_tokens=100000,max_output_tokens=25000,wall_seconds=1800)
                for role in ('controller','author','review','forecast')},
            rates=dict(api_model=model.MODEL,effort='max',input='2',cached='.1',write='2',output='10'))
        self.factories={role:inert_factory for role in f.value['slots']}
        f.value['sources'].update({'factory_'+role:pin(inspect.getsourcefile(factory))
            for role,factory in self.factories.items()})
        f.pin_runtime()
        self.client=Mock(side_effect=AssertionError('No provider/client creation'))

    @contextmanager
    def environment(self,value=None):
        with ExitStack() as stack:
            check=stack.enter_context(patch.object(owner,'preflight_runtime',return_value=deepcopy(value or self.f.value)))
            stack.enter_context(patch.object(clock,'boot_id',return_value=BOOT))
            stack.enter_context(patch.object(owner.time,'time',side_effect=lambda:self.f.wall))
            stack.enter_context(patch.object(owner.time,'monotonic',side_effect=lambda:self.f.mono))
            stack.enter_context(patch('socket.create_connection',side_effect=AssertionError('No network')))
            yield check

    def open(self):
        return owner.open_capacity_runtime(self.f.runtime,client_factory=self.client,role_factories=self.factories)

    def terminal(self):
        ident=hashlib.sha256(self.f.ident.encode()).hexdigest()
        path=self.f.ledger.parent/'.capacity-runtime-claims'/(ident+'.result.json')
        return owner.e.strict_json(path.read_bytes())

    def test_original_owner_selects_real_panel_budget_runtime_clock_contexts_and_closes_once(self):
        closed=[];actual_close=panel.PanelBudget.close
        def close(budget):closed.append(budget);return actual_close(budget)
        with self.environment() as preflight,patch.object(panel.PanelBudget,'close',close):
            with self.open() as live:
                budget=live['budget']
                self.assertIs(type(budget),panel.PanelBudget)
                self.assertEqual(budget.runtime_binding,self.f.runtime)
                self.assertEqual(budget.additional_cap_nano_usd,50*G)
                self.assertEqual(set(live['context_bindings']),set(self.factories))
                self.assertEqual(live['window']['cutoff_monotonic'],budget.monotonic_deadline)
                for bound in live['context_bindings'].values():
                    context=owner.e.strict_json(owner.e.checked(bound))
                    self.assertEqual(context['cutoff_utc'],self.f.cutoff)
                    self.assertEqual(context['source_commit'],self.f.commit)
                budget.reserve('owned-six',model.MODEL,6*G)
                budget.check_reserved('owned-six',model.MODEL,6*G)
                budget.settle('owned-six',6*G)
            self.assertGreater(preflight.call_count,2)
        self.client.assert_not_called()
        self.assertEqual(closed,[budget])
        with self.assertRaises(sqlite3.ProgrammingError):budget.db.execute('SELECT 1')
        terminal=self.terminal()
        self.assertEqual(terminal['status'],'COMPLETED_COMPONENT_CONTEXT')
        self.assertEqual(terminal['runtime'],self.f.runtime)
        self.assertEqual(terminal['budget_summary']['night_cap_usd'],50)
        self.assertEqual(terminal['budget_summary']['night_charged_upper_bound_usd'],6)
        self.assertEqual(terminal['budget_summary']['unresolved_reserved_usd'],0)
        with self.environment(),self.assertRaises(FileExistsError):
            with self.open():pass

    def test_no_marker_named_model_and_legacy_population_routes_stay_original(self):
        for optin in (True,False):
            # Fresh temp fixture per original consumed-ID boundary.
            if not optin:
                self.f.close();self.f=Fixture();self.setUp_value()
                self.addCleanup(self.f.close)
            self.f.value.pop('panel_window_budget_authority')
            self.f.value['additional_cap_nano_usd']=5*G
            if not optin:self.f.value.pop('model_budget_amendment')
            self.f.pin_runtime()
            with self.subTest(optin=optin),self.environment(),patch.object(panel,'ceiling',side_effect=AssertionError('Legacy overlay read')):
                with self.open() as live:
                    self.assertIs(type(live['budget']),original.PopulationBudget)
                    summary=live['budget'].summary()
                    self.assertEqual(summary['night_cap_usd'],5)
                    self.assertEqual('model_budget_optin' in summary,optin)
            self.assertEqual(self.terminal()['status'],'COMPLETED_COMPONENT_CONTEXT')

    def setUp_value(self):
        f=self.f;root=Path(f.value['root'])
        f.value.update(purpose='capacity_episode',deadline_utc=utc(f.wall+3660),
            slots={role:[str(root/'roles'/(role+'-01'))] for role in self.factories},
            limits={role:dict(max_input_tokens=100000,max_output_tokens=25000,wall_seconds=1800) for role in self.factories},
            rates=dict(api_model=model.MODEL,effort='max',input='2',cached='.1',write='2',output='10'))
        f.value['sources'].update({'factory_'+role:pin(inspect.getsourcefile(factory)) for role,factory in self.factories.items()})

    def test_no_population_marker_original_night_budget_route(self):
        case=SimpleNamespace(workspace=self.f.root,wall=self.f.wall,mono=self.f.mono)
        ordinary=OrdinaryFixture(case,'old-night')
        with self.environment(ordinary.spec):
            with owner.open_capacity_runtime(ordinary.binding,client_factory=self.client,role_factories=ordinary.factories) as live:
                self.assertIs(type(live['budget']),NightBudget)
                self.assertEqual(live['budget'].additional_cap_nano_usd,20*G)
        self.client.assert_not_called()

    def test_invalid_overlay_refuses_before_budget_client_not_retried(self):
        self.f.value['panel_window_budget_authority']=None;self.f.pin_runtime()
        with self.environment(),patch.object(panel.PanelBudget,'__init__',side_effect=AssertionError('Budget opened')):
            with self.assertRaises(ValueError):
                with self.open():pass
        self.client.assert_not_called()
        self.assertEqual(self.terminal()['status'],'FAILED_NO_RETRY')
        self.assertIsNone(self.terminal()['budget_summary'])
        self.assertEqual(len(self.f.rows()),self.f.value['baseline']['request_count'])

    def test_primary_failure_retains_unknown_liability_and_closes_original_owner(self):
        with self.environment():
            with self.assertRaisesRegex(ValueError,'original failure'):
                with self.open() as live:
                    budget=live['budget']
                    budget.reserve('unknown-own',model.MODEL,6*G)
                    budget.uncertain('unknown-own')
                    raise ValueError('original failure')
        result=self.terminal()
        self.assertEqual((result['status'],result['error_type']),('FAILED_NO_RETRY','ValueError'))
        self.assertEqual(result['budget_summary']['unresolved_reserved_usd'],6)
        self.assertTrue(result['budget_summary']['blocked'])
        with sqlite3.connect(self.f.ledger) as db:
            self.assertEqual(db.execute("SELECT reserved,charged,status FROM requests WHERE id='unknown-own'").fetchone(),(6*G,0,'uncertain'))
        with self.assertRaises(sqlite3.ProgrammingError):budget.db.execute('SELECT 1')

    def test_secondary_summary_failure_does_not_mask_primary_error_or_liability(self):
        with self.environment(),patch.object(panel.PanelBudget,'summary',side_effect=RuntimeError('secondary audit failure')):
            with self.assertRaisesRegex(ValueError,'primary error'):
                with self.open() as live:
                    budget=live['budget']
                    budget.reserve('unknown-own',model.MODEL,6*G)
                    budget.uncertain('unknown-own')
                    raise ValueError('primary error')
        result=self.terminal()
        self.assertEqual((result['status'],result['error_type']),('FAILED_NO_RETRY','ValueError'))
        self.assertIsNone(result['budget_summary'])
        with sqlite3.connect(self.f.ledger) as db:
            self.assertEqual(db.execute("SELECT reserved,charged,status FROM requests WHERE id='unknown-own'").fetchone(),(6*G,0,'uncertain'))
        with self.assertRaises(sqlite3.ProgrammingError):budget.db.execute('SELECT 1')

    def test_nonpopulation_overlay_never_selects_budget_or_client(self):
        self.f.value['schema']='earnings_capacity_runtime_v1'
        self.f.value.pop('model_budget_amendment');self.f.pin_runtime()
        with self.environment(),patch.object(panel.PanelBudget,'__init__',side_effect=AssertionError('Budget opened')):
            with self.assertRaisesRegex(ValueError,'population panel50'):
                with self.open():pass
        self.client.assert_not_called()
        self.assertEqual(self.terminal()['status'],'FAILED_NO_RETRY')


class HistoricalContracts(unittest.TestCase):
    def setUp(self):
        self.f=Fixture();self.addCleanup(self.f.close)
        with closing(self.f.open()) as budget:self.summary=budget.summary()
        self.runtime=deepcopy(self.f.value)
        files={panel.SOURCE:Path(panel.__file__),**{name:Path(model.__file__ if name==model.IMPLEMENTATIONS[0] else original.__file__)
            for name in model.IMPLEMENTATIONS}}
        self.blobs={name:path.read_bytes() for name,path in files.items()}
        self.runtime['sources']={name:dict(path=str(self.f.repo/name),sha256=hashlib.sha256(raw).hexdigest())
            for name,raw in self.blobs.items()}
        self.runtime['sources'][model.PLAN]=self.f.auth
        self.runtime['cutoff_utc']='2000-01-01T00:00:00Z'  # History is not current clock admission.
        self.reader=history._Reader(self.f.owned,self.f.ledger,self.f.repo,self.f.ident)
        self.reader.register_sources(self.runtime)
        self.git=patch.object(history,'_git',side_effect=lambda repo,commit,name:self.blobs[name])
        self.git.start();self.addCleanup(self.git.stop)

    def verify(self):
        with sqlite3.connect(self.f.ledger) as db:
            return completed._model_grant(db,self.reader,self.runtime,self.summary,self.f.snapshot()['max_rowid'])

    def test_original_historical_model_grant_accepts_expired50_preserves_financial_sources(self):
        before=self.f.rows()
        self.assertEqual(self.verify(),[model.binding()])
        self.assertEqual(self.reader.extra,{Path(self.f.overlay['path']),Path(model.binding()['path'])})
        self.assertEqual(self.f.rows(),before)
        for name in model.IMPLEMENTATIONS:
            self.assertEqual(self.runtime['sources'][name]['sha256'],hashlib.sha256(self.blobs[name]).hexdigest())
        unrelated=save(self.f.owned/'not-authorized.json',{'never':'a root allowlist'})
        with self.assertRaisesRegex(ValueError,'outside exact'):self.reader.read(unrelated)

    def test_no_marker_old5_unchanged_and_old5_plus1_still_refused(self):
        self.runtime.pop('panel_window_budget_authority')
        self.runtime['sources'].pop(panel.SOURCE)
        self.reader.register_sources(self.runtime)
        self.runtime['additional_cap_nano_usd']=5*G
        self.assertEqual(self.verify(),[model.binding()])
        self.assertEqual(self.reader.extra,{Path(model.binding()['path'])})
        self.runtime['additional_cap_nano_usd']=5*G+1
        with self.assertRaisesRegex(ValueError,'historical model grant'):self.verify()

    def test_bad_amount_authority_source_or_summary_refuse(self):
        changes=[('additional_cap_nano_usd',50*G+1),('additional_cap_nano_usd',float(50*G)),
            ('panel_window_budget_authority',None),('window_minutes',180)]
        for key,value in changes:
            saved=deepcopy(self.runtime);self.runtime[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.verify()
            self.runtime=saved
        self.runtime['sources'][panel.SOURCE]['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'Unregistered'):self.verify()
        self.runtime['sources'][panel.SOURCE]['sha256']=hashlib.sha256(self.blobs[panel.SOURCE]).hexdigest()
        self.summary['model_budget_optin']=None
        with self.assertRaisesRegex(ValueError,'historical model grant'):self.verify()

    def test_old_financial_implementations_and_authority_and_closed_prefix_checks_remain(self):
        original_runtime=deepcopy(self.runtime)
        for name in model.IMPLEMENTATIONS:
            self.runtime=deepcopy(original_runtime)
            self.runtime['sources'][name]['sha256']='0'*64
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'financial implementation'):self.verify()
        self.runtime=deepcopy(original_runtime)
        self.runtime['sources'][model.PLAN]=dict(path=self.f.auth['path'],sha256='0'*64)
        with self.assertRaisesRegex(ValueError,'historical model grant'):self.verify()
        self.runtime=deepcopy(original_runtime);self.runtime['baseline']['max_rowid']=0
        with self.assertRaisesRegex(ValueError,'historical model grant'):self.verify()
        self.runtime=deepcopy(original_runtime)
        with patch.object(completed,'history_snapshot',return_value={'charged_nano_usd':401*G}):
            with self.assertRaisesRegex(ValueError,'closed prefix'):self.verify()


if __name__ == '__main__':unittest.main()
