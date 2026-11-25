"""Bounded24 budget bridge: synthetic histories only, no live ledger or API.

The original4283/5222 shape and charges are reproduced with invented rows;
their hashes are deliberately not the real ledger hashes.
"""
from contextlib import ExitStack
from copy import deepcopy
import inspect
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import earnings_capacity_runtime as runtime
import earnings_open_assembly as assembly
import earnings_open_fresh_grant as fresh
import earnings_open_resources as resources
from earnings_night_budget import NightBudget, history_snapshot
from edgar_forecast_budget import BudgetStop, PilotBudget, TOTAL_CAP
from edgar_forecast_full_budget import activate, FULL_MODEL_CAP, MODELS
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_open_fresh_grant as grant_fixture


def _inert_factory(context, *, budget, client_factory):
    """Owner wiring stand-in; no provider client is constructed or called."""
    return lambda: None


class Author24BudgetTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='invented-author24-budget-')
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name).resolve()
        self.ledger = self.home/'synthetic-only.sqlite3'
        prior = PilotBudget(self.ledger)
        prior.close()
        activate(self.ledger, 'a'*64, 'b'*40)
        with sqlite3.connect(self.ledger) as db:
            def append(start, count, total):
                base, remainder = divmod(total, count)
                db.executemany("INSERT INTO requests VALUES (?,?,?,?,'settled')",
                    [(f'invented-{i}', MODELS[i % len(MODELS)], base+(i-start < remainder),
                      base+(i-start < remainder)) for i in range(start,start+count)])
            append(0,4283,137_542_765_000)
            self.baseline = history_snapshot(db)
            append(4283,939,19_326_993_400)
            self.opening = history_snapshot(db)
        original = grant_fixture.FreshGrantTests()
        original.setUp(); self.addCleanup(original.doCleanups)
        self.body = deepcopy(original.body)
        self.body['baseline'] = deepcopy(self.baseline)
        self.body['window'] = {'issued_utc':'2099-01-01T00:00:00Z',
            'cutoff_utc':'2099-01-01T01:30:00Z','deadline_utc':'2099-01-01T01:31:00Z'}
        old_opening = dict(self.baseline,max_rowid=4955,request_count=4955,
            charged_nano_usd=151_871_303_400,rows_sha256='a'*64)
        self.body['continuation'] = {'human_authorization':fresh.AUTHOR20_AUTHORIZATION,
            'cumulative_cap_nano_usd':19_328_538_400,'rounds':1,
            'research_context':engine.save(self.home/'inert-context.json',{'synthetic':True}),
            'allocation':{'opening':old_opening,'max_new_nano_usd':5_000_000_000,
                'author_id':fresh.AUTHOR20_IDS[0],'forecast_id':fresh.AUTHOR20_IDS[1]},
            'successor':{'human_authorization':fresh.AUTHOR22_AUTHORIZATION,
                'author_id':fresh.AUTHOR22_IDS[0],'forecast_id':fresh.AUTHOR22_IDS[1],
                'author_max_input_tokens':24000,'closed_author_review':deepcopy(fresh.AUTHOR20_CLOSURE)},
            'output_followthrough':{'human_authorization':fresh.AUTHOR24_AUTHORIZATION,
                'author_id':fresh.AUTHOR24_IDS[0],'forecast_id':fresh.AUTHOR24_IDS[1],
                'author_max_input_tokens':24000,'author_max_output_tokens':49152,
                'closed_author_review':deepcopy(fresh.AUTHOR22_CLOSURE),
                'allocation':{'opening':deepcopy(self.opening),'max_new_nano_usd':2_000_000_000,
                    'author_id':fresh.AUTHOR24_IDS[0],'forecast_id':fresh.AUTHOR24_IDS[1]}}}
        self.policy = self.home/'synthetic-policy.json'
        engine.save(self.policy,self.body)
        stack = ExitStack(); self.addCleanup(stack.close)
        stack.enter_context(patch.object(fresh,'ROOT',self.home))
        stack.enter_context(patch.object(fresh,'CONFIG',self.policy))
        stack.enter_context(patch.object(fresh,'BASELINE',deepcopy(self.baseline)))
        identifier = fresh.AUTHOR24_IDS[0]
        root = self.home/'attempts'/identifier
        original_runtime = json.loads((runtime.e.REPO/'benchmarks/edgar_forecast/openai_runtime.json').read_bytes())
        sources = {name:engine.pin(Path(path).resolve()) for name,path in runtime.CORE.items()}
        sources.update(forecast_entry=engine.pin(Path(runtime.e.__file__).resolve()),
            forecaster=engine.pin(Path(inspect.getsourcefile(runtime.e.forecast)).resolve()))
        sources.update({'factory_'+name:engine.pin(Path(assembly.__file__).resolve())
            for name in ('controller','author','review','forecast')})
        caps = resources.role_limits()
        caps['forecast'] = {'max_input_tokens':original_runtime['max_input_tokens'],
            'max_output_tokens':max(original_runtime['max_output_tokens'],original_runtime.get('final_max_output_tokens',0)),
            'wall_seconds':original_runtime['company_wall_seconds']}
        self.value = {'schema':'earnings_capacity_runtime_v2','purpose':'capacity_episode',
            'id':identifier,'source_commit':'b'*40,'root':str(root),'ledger':str(self.ledger),
            'baseline':deepcopy(self.baseline),'additional_cap_nano_usd':fresh.pilot_cap(self.body),
            'cutoff_utc':self.body['window']['cutoff_utc'],'deadline_utc':self.body['window']['deadline_utc'],
            'rates':original_runtime['models']['gpt-6.1-sol'],'limits':caps,
            'slots':{name:[str(root/'roles'/(name+'-01'))] for name in caps},'sources':sources}
        self.grant = {key:deepcopy(self.value[key]) for key in ('id','root','source_commit','ledger',
            'baseline','additional_cap_nano_usd','cutoff_utc','deadline_utc')}
        self.grant.update(schema=fresh.SCHEMA,human_authorization=fresh.AUTHORIZATION,
            bootstrap_no_model_call=False,allowed_egress=deepcopy(fresh.EGRESS),
            sources={'configs/earnings_coevolution/research_followup_authority.json':engine.pin(self.policy)['sha256']})
        self.study = {'schema':'earnings_coevolution_study_v1',
            'model':{'requested_model':'gpt-6.1-sol','serving_snapshot':'unknown','serving_snapshot_verified':False},
            'runtime_config':original_runtime,'prior_batch':engine.save(self.home/'inert-prior.json',{'config':original_runtime}),
            'new_live_grant':engine.save(self.home/'synthetic-grant.json',self.grant)}
        self.value['forecast_study'] = engine.save(self.home/'synthetic-study.json',self.study)
        self.binding = engine.save(self.home/'synthetic-runtime.json',self.value)

    def budget(self, **changes):
        arguments = {'baseline':self.baseline,'deadline_utc':self.value['cutoff_utc'],
            'additional_cap_nano_usd':self.value['additional_cap_nano_usd'],'runtime_binding':self.binding}
        arguments.update(changes)
        return NightBudget(self.ledger,**arguments)

    def changed(self, change):
        value = deepcopy(self.value); change(value)
        number = len(list(self.home.glob('changed-runtime-*.json')))
        return engine.save(self.home/f'changed-runtime-{number}.json',value)

    def test_legacy_above_twenty_without_binding_rejected_before_connect(self):
        for amount in (20_000_000_001,21_326_993_400,50_000_000_001,True,0):
            with self.subTest(amount=amount),patch('edgar_forecast_full_budget.connect_existing') as connect:
                with self.assertRaises(ValueError):
                    NightBudget(self.ledger,baseline=self.baseline,deadline_utc=self.value['cutoff_utc'],
                        additional_cap_nano_usd=amount)
                connect.assert_not_called()
        budget = self.budget(additional_cap_nano_usd=20_000_000_000,runtime_binding=None)
        self.addCleanup(budget.close)
        self.assertEqual(budget.additional_cap_nano_usd,20_000_000_000)

    def test_exact_bound_route_preflight_then_new_two_with_original_history(self):
        with patch('edgar_forecast_full_budget.connect_existing',side_effect=AssertionError('No preflight ledger open')):
            self.assertEqual(runtime.preflight_runtime(self.binding),self.value)
        budget = self.budget(); self.addCleanup(budget.close)
        original = history_snapshot(budget.db,self.baseline['max_rowid'])
        budget.reserve('invented-author24','gpt-6.1-sol',2_000_000_000)
        budget.check_reserved('invented-author24','gpt-6.1-sol',2_000_000_000)
        budget.settle('invented-author24',2_000_000_000)
        with self.assertRaises(BudgetStop):budget.reserve('invented-no-extra','gpt-6.1-sol',1)
        with self.assertRaises(BudgetStop):budget.reserve('invented-author24','gpt-6.1-sol',1)
        self.assertEqual(history_snapshot(budget.db,self.baseline['max_rowid']),original)
        self.assertEqual(budget.db.execute('SELECT cap,model_cap,blocked FROM config').fetchall(),
            [(TOTAL_CAP,FULL_MODEL_CAP,0)])

    def test_adversarial_runtime_refused_before_any_ledger_connect(self):
        changes = [lambda v:v.update(id=fresh.AUTHOR22_IDS[0]),
            lambda v:v.update(additional_cap_nano_usd=v['additional_cap_nano_usd']+1),
            lambda v:v.update(baseline=dict(v['baseline'],charged_nano_usd=0)),
            lambda v:v.update(cutoff_utc='2099-01-01T01:30:01Z'),
            lambda v:v['rates'].update(output='1'),
            lambda v:v['sources']['runtime'].update(sha256='0'*64),
            lambda v:v.update(schema='earnings_capacity_runtime_v1')]
        for index,change in enumerate(changes):
            binding = self.changed(change)
            with self.subTest(index=index),patch('edgar_forecast_full_budget.connect_existing') as connect:
                with self.assertRaises(ValueError):self.budget(runtime_binding=binding)
                connect.assert_not_called()
        for change in ({'runtime_binding':{}},{'baseline':dict(self.baseline,max_rowid=0)},
                {'deadline_utc':'2099-01-01T01:31:00Z'},
                {'additional_cap_nano_usd':self.value['additional_cap_nano_usd']+1}):
            with self.subTest(change=change),patch('edgar_forecast_full_budget.connect_existing') as connect:
                with self.assertRaises((ValueError,KeyError)):self.budget(**change)
                connect.assert_not_called()
        with patch('edgar_forecast_full_budget.connect_existing') as connect:
            with self.assertRaises(ValueError):
                NightBudget(self.home/'other.sqlite3',baseline=self.baseline,
                    deadline_utc=self.value['cutoff_utc'],
                    additional_cap_nano_usd=self.value['additional_cap_nano_usd'],runtime_binding=self.binding)
            connect.assert_not_called()

    def test_owner_passes_exact_binding_only_on_reviewed_above_twenty_route(self):
        # Introspection alone is mocked so inert roles match the bound assembly
        # module. All runtime/grant/source reads and the actual budget run as-is.
        original_inspect = inspect.getsourcefile
        def source(value):
            return assembly.__file__ if value is _inert_factory else original_inspect(value)
        with patch.object(runtime.inspect,'getsourcefile',side_effect=source), \
                patch.object(runtime,'NightBudget',wraps=NightBudget) as constructor, \
                patch.object(runtime.clock,'boot_id',return_value='11111111-2222-3333-4444-555555555555'):
            with runtime.open_capacity_runtime(self.binding,client_factory=lambda:None,
                    role_factories={name:_inert_factory for name in self.value['slots']}) as owner:
                self.assertEqual(owner['budget'].additional_cap_nano_usd,self.value['additional_cap_nano_usd'])
                self.assertEqual(set(owner['roles']),set(self.value['slots']))
            self.assertEqual(constructor.call_count,1)
            self.assertEqual(constructor.call_args.kwargs['runtime_binding'],self.binding)
        self.assertEqual(engine.read(engine.pin(self.ledger.parent/'.capacity-runtime-claims'/
            (runtime.e.digest(self.value['id'].encode())+'.result.json')))['status'],'COMPLETED_COMPONENT_CONTEXT')
    def test_global_and_per_model_caps_still_enforced(self):
        budget = self.budget(); self.addCleanup(budget.close)
        with self.assertRaises(BudgetStop):budget.reserve('invented-global','gpt-6.1-sol',TOTAL_CAP)
        with self.assertRaises(BudgetStop):budget.reserve('invented-model','gpt-6.1-sol',FULL_MODEL_CAP)
        self.assertEqual(history_snapshot(budget.db),self.opening)


if __name__=='__main__':unittest.main()
