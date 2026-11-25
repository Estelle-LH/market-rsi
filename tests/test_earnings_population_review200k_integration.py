"""Prospective Review input only; synthetic authority/history/provider seams.

Real prepare/training-contract, Reviewer/packing and temporary HTTP/ledger are
exercised separately. No live provider, production budget, Native or new Review
verdict is authenticated by these portable tests.
"""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import earnings_open_resources as resources
import earnings_open_roles as open_roles
import earnings_population_runtime as runtime
import earnings_population_campaign_admission as admission
from earnings_population_roles import PopulationReviewer
from earnings_population_services import Services
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_population_review200k_policy as policy_fixture
import test_earnings_population_panel_proposal_runtime as producer_fixture
import test_earnings_population_review_headroom as role_fixture
import test_earnings_population_runtime as runtime_fixture
import test_earnings_prepared_count_handoff as wire_fixture
from edgar_forecast_budget import BudgetStop


class IntegrationTests(unittest.TestCase):
    def fixture(self, kind):
        value=kind(methodName='runTest');value.setUp();self.addCleanup(value.doCleanups)
        return value

    def authority(self):
        return self.fixture(policy_fixture.Review200PolicyTests)

    def test_real_producer_and_independent_training_contract_only_change_review_input(self):
        self.authority();f=self.fixture(producer_fixture.ProducerTests)
        bound=f.prepare_proposal(review_input_policy=resources.REVIEW200_POLICY)
        value=engine.read(bound);study=engine.read(value['forecast_study'])
        contract=engine.read(study['campaign'])['contract']
        self.assertEqual(value['review_input_policy'],resources.REVIEW200_POLICY)
        self.assertEqual(contract['review_input_policy'],resources.REVIEW200_POLICY)
        expected=dict(resources.population_role_limits(value),forecast=dict(
            max_input_tokens=100000,max_output_tokens=25000,wall_seconds=1800))
        self.assertEqual(value['limits'],expected);self.assertEqual(contract['limits'],expected)
        self.assertEqual(runtime.proposal_task(value)['round0_manifest'],f.comparator)
        self.assertEqual(value['additional_cap_nano_usd'],5_000_000_000)
        state=engine.read(value['initial_population'])
        for changed in (dict(value,review_input_policy=None),
                        {k:v for k,v in value.items() if k!='review_input_policy'}):
            with self.subTest(changed_marker=changed.get('review_input_policy')),self.assertRaises(ValueError):
                admission._training_validate(changed,study,state)
        self.assertFalse((f.root/'attempts'/f.id).exists())

    def test_marker_requires_explicit_proposal_before_outputs_or_old_history(self):
        self.authority();f=self.fixture(producer_fixture.ProducerTests)
        for policy in (None,False,'unknown'):
            if policy is None:continue
            with self.subTest(policy=policy),self.assertRaises(ValueError):
                f.prepare_proposal(review_input_policy=policy)
        with self.assertRaises(ValueError):
            f.prepare_panel(review_input_policy=resources.REVIEW200_POLICY)
        f.old_loader.assert_not_called();self.assertFalse((f.root/'inputs'/f.id).exists())

    def test_exact_runtime_resource_receiver_and_marker_erasure(self):
        self.authority();f=self.fixture(runtime_fixture.Fixture)
        value=deepcopy(f.value)
        value.update(review_input_policy=resources.REVIEW200_POLICY,
            training_proposal_policy=runtime.PROPOSAL_POLICY,training_policy='synthetic_admitted_scope')
        value['limits']['review']['max_input_tokens']=200000
        # Real runtime/source/resource/financial admission; historical training
        # study and public projection are explicit seams in this isolated test.
        with patch.object(runtime,'_study',return_value=f.original),\
                patch('earnings_population_public_predictions.runtime_policy'):
            self.assertEqual(runtime.preflight(f.bound(value))['limits'],value['limits'])
            bad_values=[]
            bad=deepcopy(value);bad.pop('review_input_policy');bad_values.append(bad)
            for role,key,n in [('review','max_input_tokens',200001),('review','max_output_tokens',16385),
                               ('review','wall_seconds',901),('controller','max_input_tokens',200000),
                               ('author','max_input_tokens',200000),('forecast','max_output_tokens',25001)]:
                bad=deepcopy(value);bad['limits'][role][key]=n;bad_values.append(bad)
            for bad in bad_values:
                with self.subTest(limits=bad['limits']),self.assertRaises(ValueError):
                    runtime.preflight(f.bound(bad))

    def high_role(self, f):
        old,slot,client,factory=f.reviewer(resources.role_limits()['review'])
        context=deepcopy(old.context);context['limits']['max_input_tokens']=200000
        ctx=engine.save(f.root/'context-review.json',context)
        value=dict(schema='earnings_population_runtime_v1',review_input_policy=resources.REVIEW200_POLICY,
            source_commit=context['source_commit'],root=context['root'],cutoff_utc=context['cutoff_utc'],
            rates=context['rates'],role_efforts=deepcopy(resources.ROLE_EFFORTS),
            slots={'review':context['slots']},limits=resources.population_role_limits(
                {'review_input_policy':resources.REVIEW200_POLICY}))
        bound=engine.save(f.root/'runtime-reviewed.json',value)
        kwargs=dict(budget=old.budget,client_factory=factory,broker=old.broker,max_turns=1)
        role=PopulationReviewer(ctx,population_runtime_binding=bound,**kwargs)
        return role,slot,client,factory,ctx,bound,value,kwargs

    def test_real_review_pack_accepts_observed37_counts_not_a_paid_verdict(self):
        self.authority()
        for count in (32976,33290,200000):
            with self.subTest(count=count):
                f=self.fixture(role_fixture.ReviewHeadroomTests)
                result=self.high_role(f);role,slot,client,factory=result[:4]
                f.reviewer=lambda limits,count=count:(role,slot,client,factory)
                client.post.return_value={'input_tokens':count,'synthetic_count':True}
                f.invoke(role.context['limits'],count=count)
                self.assertEqual(role.context['limits']['max_output_tokens'],16384)
                self.assertEqual(role.context['limits']['wall_seconds'],900)

    def test_real_review_pack_over200k_stops_before_generation(self):
        self.authority();f=self.fixture(role_fixture.ReviewHeadroomTests)
        result=self.high_role(f);role,slot,client,factory=result[:4]
        f.reviewer=lambda limits,count=200001:(role,slot,client,factory)
        client.post.return_value={'input_tokens':200001,'synthetic_count':True}
        f.invoke(role.context['limits'],count=200001,expect_failure=True)

    def test_bound_runtime_context_and_authority_drift_refuse(self):
        authority=self.authority();f=self.fixture(role_fixture.ReviewHeadroomTests)
        role,slot,client,factory,ctx,bound,value,kwargs=self.high_role(f)
        for key,wrong in [('source_commit','b'*40),('root',str(f.root/'other')),
                          ('cutoff_utc','2099-01-01T00:00:00Z'),('slots',{'review':[]})]:
            bad=dict(value,**{key:wrong});changed=engine.save(f.root/f'wrong-runtime-{key}.json',bad)
            with self.subTest(key=key),self.assertRaises(ValueError):
                PopulationReviewer(ctx,population_runtime_binding=changed,**kwargs)
        bad=deepcopy(value);bad.pop('review_input_policy')
        with self.assertRaises(ValueError):
            PopulationReviewer(ctx,population_runtime_binding=engine.save(f.root/'old.json',bad),**kwargs)
        with self.assertRaises(ValueError):PopulationReviewer(ctx,**kwargs)
        factory.assert_not_called()
        Path(bound['path']).write_text('{}')
        with self.assertRaises(ValueError):role._context()
        Path(authority.bound['path']).write_text('{}')
        with self.assertRaises(ValueError):role._resource_ceiling()
        factory.assert_not_called()

    def test_services_passes_runtime_only_to_opted_in_reviewer(self):
        service=Services.__new__(Services);service.binding={'path':'synthetic-runtime','sha256':'a'*64}
        service.runtime={'review_input_policy':resources.REVIEW200_POLICY}
        service.contexts={role:({'synthetic':role},{}) for role in ('review','controller','author')}
        service.broker=Mock(return_value=SimpleNamespace())
        kind=Mock()
        service.role('review',kind,{},'slot')
        self.assertEqual(kind.call_args.kwargs['population_runtime_binding'],service.binding)
        for role in ('controller','author'):
            service.role(role,kind,{},'slot');self.assertNotIn('population_runtime_binding',kind.call_args.kwargs)
        service.runtime={};service.role('review',kind,{},'slot')
        self.assertNotIn('population_runtime_binding',kind.call_args.kwargs)

    def test_original_temp_wire_reserves_actual_count_not_ceiling(self):
        f=self.fixture(wire_fixture.PreparedCountHandoffTests)
        f.f.limits['max_input_tokens']=200000
        f.f.context_binding=engine.save(f.f.root/'context-review200k.json',f.f.context)
        f.counts=[33290]
        request,handoff=f.prepare();f.send(request,handoff)
        rows=f.f.budget.db.execute("SELECT reserved,status FROM requests WHERE id!='fixture-prior'").fetchall()
        self.assertEqual(rows,[(33290*2500+1024*10000,'settled')])  # Original max(input,cached,write).
        self.assertEqual([x[0] for x in f.wire_calls],['/v1/responses/input_tokens','/v1/responses'])

    def test_original_temp_wire_over200k_has_no_loan_or_generation(self):
        f=self.fixture(wire_fixture.PreparedCountHandoffTests)
        f.f.limits['max_input_tokens']=200000
        f.f.context_binding=engine.save(f.f.root/'context-review200k.json',f.f.context)
        f.counts=[200001]
        with self.assertRaises(BudgetStop):f.prepare()
        self.assertEqual(f.f.budget.db.execute("SELECT count(*) FROM requests WHERE id!='fixture-prior'").fetchone()[0],0)
        self.assertEqual([x[0] for x in f.wire_calls],['/v1/responses/input_tokens'])


if __name__=='__main__':unittest.main()
