"""Portable role-policy fixtures, not provider/Native admission evidence."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import earnings_capacity_runtime as owner
import earnings_entry as e
import earnings_population_live_guard as guard
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine


class RoleFixture:
    """Real hash/path reads; full historical admission/resident/ledger are inert."""
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory(); self.base = Path(self.temp.name).resolve()
        self.root = self.base/'attempt'; self.root.mkdir(); self.native = self.base/'native'; self.native.mkdir()
        self.full_calls = []; self.ledger_calls = []
        self.source = {a:self.raw(a+'.py', ('fixture '+a).encode()) for a in ('R','H')}
        self.version = dict(id=digest({a:self.source[a]['sha256'] for a in self.source}), **self.source)
        self.population = dict(stable_id=self.version['id'], explorers=[], versions={self.version['id']:self.version})
        self.feedback = self.save('feedback.json', {'kind':'scored_dev', 'fixture':True})
        self.packet = dict(company_id='CIK0000017313', population=self.population, feedback=self.feedback)
        self.save('packet-01.json',self.packet); self.save('frozen-pool-01.json',self.population)
        self.metadata = {k:self.raw(k+'.bin',k.encode()) for k in
            ('FULL_PLAN','METADATA','MANIFEST','RUNTIME','SCORER','qa','forecaster','filing')}
        company = dict(cik=self.packet['company_id'],visible_root=str(self.root),
            allowed_files=[dict(path='filing.bin',sha256=self.metadata['filing']['sha256'],bytes=6)])
        self.resident = dict(company=company,runtime={'fixture':True},case={'fixture':True},
            kernel={'scorer':self.metadata['SCORER'],'qa':self.metadata['qa']},data_binding=self.metadata['FULL_PLAN'])
        study = {k:self.save(k+'.json', {'fixture':k}) for k in ('campaign','campaign_origin','campaign_resume','prior_batch')}
        self.value = dict(schema='earnings_population_runtime_v1',id='edgar-population-20261016-44',
            root=str(self.root),source_commit='a'*40,validation_policy=guard.POLICY,
            budget_amendment=self.save('amendment.json',{}),companies=[company['cik']],
            initial_population=self.save('population.json',self.population),forecast_study=self.save('study.json',study),
            population_plan=self.save('plan.json',{}),review=self.save('review.json',{}),
            sources={'forecaster':self.metadata['forecaster']},
            slots={r:[str(self.root/'roles'/(r+'-01'+(f'-{i:02d}' if r=='forecast' else '')))
                for i in (range(3) if r=='forecast' else [0])]for r in ('controller','author','review','forecast')})
        self.binding=self.save('runtime.json',self.value)
        self.manager=guard.RoleValidation(self.binding,self.value,self.full)
        self.manager.native=self.native  # Explicit inert root seam; no original Native process.

    def raw(self,name,value):
        path=self.root/name;path.write_bytes(value);return engine.pin(path)
    def save(self,name,value):return self.raw(name,json.dumps(value,sort_keys=True).encode())
    def full(self):self.full_calls.append('full');return deepcopy(self.value)
    def patches(self):
        return [patch.object(guard.tasks,'resident',return_value=deepcopy(self.resident)),
            *[patch.object(guard.tasks,k,self.metadata[k])for k in ('FULL_PLAN','METADATA','MANIFEST','RUNTIME','SCORER')],
            patch('earnings_population_runtime._sources',side_effect=lambda v:[owner._read(b)for b in v['sources'].values()]),
            patch('earnings_population_runtime._ledger',side_effect=lambda v:self.ledger_calls.append('live'))]
    def case(self,slot,version=None):
        version=deepcopy(version or self.version);root=self.native/Path(slot).name;root.mkdir()
        (root/'source').mkdir()
        for name,bound in [('researcher_v0.py',version['R']),('harness_v0.py',version['H']),
                ('evaluation_scorer.py',self.metadata['SCORER']),('evaluation_qa.json',self.metadata['qa']),
                ('predictor.py',self.metadata['forecaster'])]:
            (root/'source'/name).write_bytes(Path(bound['path']).read_bytes())
        initial=self.save(Path(slot).name+'-initial.json',{'fixture':True})
        value=dict(source_commit=self.value['source_commit'],pool_version=version,authority=self.binding,
            **{k:deepcopy(self.resident[k])for k in ('company','runtime','kernel','case')},
            data=self.resident['data_binding'],manifest={'fixture':True},initial_state=initial)
        context=engine.save(root/'context.json',value)
        return dict(context=context,company=value['company'],kernel=value['kernel'],manifest=value['manifest'],initial_state=initial)
    def args(self,role,arm=0):
        slot=self.value['slots'][role][arm]
        if role=='controller':return (deepcopy(self.packet),slot)
        if role=='author':return ({'parent_pair_sha256':self.version['id'],'feedback_sha256':digest(self.feedback)},deepcopy(self.population),slot)
        if role=='review':
            child=deepcopy(self.version);child['parent']=self.version['id'];return(child,deepcopy(self.population),slot)
        return(deepcopy(self.version),self.packet['company_id'],slot)
    def close(self):self.temp.cleanup()


class RoleValidationTests(unittest.TestCase):
    def setUp(self):
        self.f=RoleFixture();self.addCleanup(self.f.close)
        for p in self.f.patches():p.start();self.addCleanup(p.stop)

    def test_all_roles_and_each_forecast_arm_have_full_entry_exit(self):
        for role,arm in [('controller',0),('author',0),('review',0),*[( 'forecast',n)for n in range(3)]]:
            def callback(*args):
                self.f.manager.register_case(self.f.case(args[-1],self.f.manager.current['version']))
                self.f.manager.check(args[-1]);self.f.manager.check(args[-1]);return {'fixture':'result'}
            self.assertEqual(self.f.manager.wrap(role,callback)(*self.f.args(role,arm)),{'fixture':'result'})
        self.assertEqual(len(self.f.full_calls),12);self.assertEqual(len(self.f.ledger_calls),18)
        self.assertEqual(len(list((self.f.root/'role-validation').glob('*.json'))),6)

    def test_current_selected_source_tamper_refused(self):
        def callback(*args):
            self.f.manager.register_case(self.f.case(args[-1]));Path(self.f.source['R']['path']).write_bytes(b'changed R')
            self.f.manager.check(args[-1])
        with self.assertRaises(ValueError):self.f.manager.wrap('controller',callback)(*self.f.args('controller'))
        self.assertIsNone(self.f.manager.current)

    def test_selected_case_cannot_self_consistently_substitute_other_source(self):
        def callback(*args):
            bad=deepcopy(self.f.version);bad['id']='f'*64
            self.f.manager.register_case(self.f.case(args[-1],bad))
        with self.assertRaises(ValueError):self.f.manager.wrap('controller',callback)(*self.f.args('controller'))

    def test_declared_other_slot_cannot_send(self):
        def callback(*args):
            self.f.manager.register_case(self.f.case(args[-1]));self.f.manager.check(self.f.value['slots']['forecast'][0])
        with self.assertRaises(ValueError):self.f.manager.wrap('controller',callback)(*self.f.args('controller'))

    def test_current_case_tamper_after_last_http_cannot_return_accepted_output(self):
        def callback(*args):
            self.f.manager.register_case(self.f.case(args[-1]));self.f.manager.check(args[-1])
            (self.f.native/Path(args[-1]).name/'source/researcher_v0.py').write_bytes(b'changed')
            return 'not accepted'
        with self.assertRaises(ValueError):self.f.manager.wrap('controller',callback)(*self.f.args('controller'))
        receipt=json.loads((self.f.root/'role-validation/controller-01.json').read_text())
        self.assertFalse(receipt['output_accepted']);self.assertEqual(receipt['exit_full_audit'],'PASS')
        self.assertEqual(receipt['exit_current_guard'],'NOT_PASSED')

    def test_archived_corruption_is_deferred_but_output_never_accepted(self):
        calls=[]
        def full():
            calls.append(True)
            if len(calls)>1:raise ValueError('archived fixture changed')
            return deepcopy(self.f.value)
        self.f.manager.full_check=full
        def callback(*args):
            self.f.manager.register_case(self.f.case(args[-1]));self.f.manager.check(args[-1]);return 'not accepted'
        with self.assertRaisesRegex(ValueError,'archived'):self.f.manager.wrap('controller',callback)(*self.f.args('controller'))
        receipt=json.loads((self.f.root/'role-validation/controller-01.json').read_text())
        self.assertFalse(receipt['output_accepted']);self.assertEqual(receipt['exit_full_audit'],'FAILED')

    def test_secondary_audit_failure_preserves_original_exception_and_liability(self):
        original=RuntimeError('original fixture error');liabilities=[19]
        def full():
            if self.f.full_calls:raise ValueError('closure fixture failed')
            return self.f.full()
        self.f.manager.full_check=full
        def callback(*args):raise original
        with self.assertRaises(RuntimeError)as caught:self.f.manager.wrap('controller',callback)(*self.f.args('controller'))
        self.assertIs(caught.exception,original);self.assertEqual(liabilities,[19]);self.assertIsNone(self.f.manager.current)

    def test_wrapper_identity_is_honest_and_plain_legacy_identity_unchanged(self):
        def original(*args):return None
        wrapped=self.f.manager.wrap('controller',original);identity=guard.service_identity(wrapped)
        self.assertEqual(identity['function'],'_role_boundary.<locals>.invoke')
        self.assertEqual(identity['original'],engine.source_of(original));self.assertNotEqual(identity['module'],identity['original']['module'])
        self.assertEqual(guard.service_identity(original),engine.source_of(original))

    def test_historical_expected_identities_include_wrapper_and_real_service(self):
        from earnings_population_continuation import expected_services
        from earnings_population_services import Services
        value=deepcopy(self.f.value)
        value['sources'].update({'tools/earnings_population_services.py':engine.pin(__import__('inspect').getsourcefile(Services)),
            'tools/earnings_population_live_guard.py':engine.pin(guard.__file__)})
        expected=expected_services(value)
        for role in self.f.value['slots']:
            wrapped=self.f.manager.wrap(role,getattr(Services,role))
            self.assertEqual(guard.service_identity(wrapped),expected[role])
        value.pop('validation_policy')
        self.assertEqual(expected_services(value),{role:engine.source_of(getattr(Services,role))for role in value['slots']})

    def test_policy_is_strict_and_absent_is_legacy(self):
        self.assertFalse(guard.enabled({}))
        for bad in (None,True,90,{},'future'):
            with self.subTest(bad=bad),self.assertRaises(ValueError):guard.enabled(dict(self.f.value,validation_policy=bad))
        for key in ('budget_amendment','schema'):
            value=deepcopy(self.f.value);value.pop(key)
            with self.assertRaises(ValueError):guard.enabled(value)

    def test_no_native_registration_cannot_dispatch_or_accept_result(self):
        def callback(*args):self.f.manager.check(args[-1])
        with self.assertRaises(ValueError):self.f.manager.wrap('controller',callback)(*self.f.args('controller'))

    def test_current_feedback_after_last_http_cannot_be_accepted(self):
        def callback(*args):
            self.f.manager.register_case(self.f.case(args[-1]));self.f.manager.check(args[-1])
            Path(self.f.feedback['path']).write_bytes(b'feedback was replaced')
            return 'not accepted'
        with self.assertRaises(ValueError):self.f.manager.wrap('controller',callback)(*self.f.args('controller'))

    def test_owned_http_checks_actual_physical_slot_twice_without_changing_default(self):
        class Fake(owner.RawOpenAIHTTP):
            def post(self,path,payload):return {'input_tokens':7}
        slot=Path(self.f.value['slots']['controller'][0]);slot.mkdir(parents=True)
        payload={'model':'fixture','reasoning':{'effort':'max'}};prefix=slot/'http-fixture'
        engine.save(prefix.with_suffix('.intent.json'),{'endpoint':'/v1/responses/input_tokens','payload':payload})
        raw=Fake('fixture');raw.record_prefix=prefix;old=[];live=[]
        client=owner._OwnedHTTP(raw,lambda loan:old.append(loan),{str(slot):{}},{'api_model':'fixture','effort':'max'},live_check=lambda loan,s:live.append((loan,s)))
        self.assertEqual(client.post('/v1/responses/input_tokens',payload),{'input_tokens':7})
        self.assertEqual(live,[(None,slot),(None,slot)]);self.assertEqual(old,[])
        raw.record_prefix=prefix;client.live_check=None;client.post('/v1/responses/input_tokens',payload)
        self.assertEqual(old,[None,None])


if __name__=='__main__':unittest.main()
