"""Fresh descriptor receiving with explicit prospective verifier seam.

Invented source/task metadata, not real Author/Native/history proof. The future
load_proposal verifier is an exact scripted boundary, never an inferred receipt.
"""
from copy import deepcopy
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

import earnings_population as population
import earnings_population_frozen_panel as panel
from supervisor_harness import capacity_feedback_engine as engine
from test_earnings_population_frozen_panel import PanelFixture


class FreshProposalDescriptorTests(unittest.TestCase):
    def setUp(self):
        self.f=PanelFixture();self.addCleanup(self.f.close)
        self.authority=self.f.save(self.f.root/'new-authority.json',dict(
            human_answer='让 Author 根据完整25家公司 Round0反馈提出新候选，旧34–36仅归档参考'))
        self.enterContext(patch.object(panel,'NEW_AUTHORITY',self.authority))
        self.parent=self.f.state['versions'][self.f.state['stable_id']]
        self.proposal=self.f.save(self.f.root/'proposal.json',{'inert':'not actual closure'})
        r=self.f.source(self.f.root/'freshR.py','# New inert method, never executed.\n')
        self.child=population.version(r,self.parent['H'],parent=self.parent['id'],axis='R',
            method='Invented wholepanel proposal',author='scripted verifier seam',evidence=[self.proposal])
        bound=self.f.base['evidence'][0];runtime=engine.read(bound)
        self.verified=dict(schema='earnings_training25_verified_proposal_v1',accepted=True,proposal=self.proposal,
            base_origin=deepcopy(self.f.base),task=dict(authority=self.authority,split=self.f.split,
                round0_manifest=self.f.comparator,training_companies=self.f.training,smoke_only=True),
            candidate=deepcopy(self.child),parent=deepcopy(self.parent),
            decision=dict(axis='R',parent_pair_sha256=self.parent['id']),evidence=[self.proposal],
            runtime=runtime,runtime_binding=bound,review={'accepted_for_exploration':True})
        self.loader=Mock(side_effect=lambda *a,**k:deepcopy(self.verified))
        self.enterContext(patch.dict(sys.modules,{'earnings_population_proposal_completed':SimpleNamespace(load_proposal=self.loader)}))

    def freeze(self):
        return panel.freeze_proposal_descriptor(self.proposal,split_binding=self.f.split,
            comparator_binding=self.f.comparator,authority_binding=self.authority,
            root=self.f.root,ledger=self.f.root/'unused.sqlite',repo=self.f.repo)

    def test_fresh_child_actual_parent_and_all25_not_old_r35_or_measured_result(self):
        result=self.freeze();value=result['descriptor']
        self.assertEqual(value['proposal'],self.proposal)
        self.assertEqual(value['authority'],self.authority)
        self.assertEqual(value['members']['candidate'],self.child)
        self.assertEqual(value['members']['parent'],self.parent)
        self.assertNotEqual(value['members']['candidate']['id'],self.f.child['id'])
        self.assertEqual([r['company_id'] for r in value['companies']],self.f.training)
        self.assertIn('zero measured',value['scope'])
        self.assertNotIn('scores',value)
        self.assertEqual(self.f.load(value)['descriptor'],value)
        self.assertEqual(self.loader.call_count,2)
        self.assertFalse(list(self.f.root.glob('**/capacity_work*')))

    def test_h_axis_is_a_real_single_component_change_not_forced_r_only(self):
        h=self.f.source(self.f.root/'freshH.py','# New inert observation adapter.\n')
        child=population.version(self.parent['R'],h,parent=self.parent['id'],axis='H')
        self.verified.update(candidate=child,decision=dict(axis='H',parent_pair_sha256=self.parent['id']))
        self.assertEqual(self.freeze()['descriptor']['members']['candidate'],child)

    def test_rejected_continue_archived_or_existing_candidate_never_freezes(self):
        original=deepcopy(self.verified)
        variants=[dict(accepted=False),dict(candidate=None),dict(candidate=self.f.child),
            dict(parent=self.f.child),dict(task=dict(original['task'],training_companies=self.f.training[::-1])),
            dict(decision=dict(axis='H',parent_pair_sha256=self.parent['id']))]
        for changes in variants:
            self.verified=dict(deepcopy(original),**changes)
            with self.subTest(changes=changes),self.assertRaises(ValueError):self.freeze()

    def test_both_axis_drift_or_hash_drift_or_changed_forecast_policy_refuses(self):
        original=deepcopy(self.verified)
        child=deepcopy(self.child);child['H']=self.f.source(self.f.root/'alsoH.py','# Also changed H\n')
        variants=[dict(candidate=child),dict(candidate=dict(self.child,id='f'*64))]
        raw=deepcopy(original['runtime']);raw['sources']['forecaster']['sha256']='f'*64
        variants.append(dict(runtime=raw))
        for changes in variants:
            self.verified=dict(deepcopy(original),**changes)
            with self.subTest(changes=changes),self.assertRaises(ValueError):self.freeze()

    def test_descriptor_cannot_substitute_old_singlecompany_child_or_erase_proposal(self):
        value=self.freeze()['descriptor']
        changed=deepcopy(value);changed['members']['candidate']=self.f.child
        with self.assertRaises(ValueError):self.f.load(changed)
        changed=deepcopy(value);changed.pop('proposal')
        with self.assertRaises(ValueError):self.f.load(changed)

    def test_wrong_new_authority_or_reordered_membership_refuses_before_loader(self):
        with self.assertRaises(ValueError):
            panel.freeze_proposal_descriptor(self.proposal,split_binding=self.f.split,
                comparator_binding=self.f.comparator,authority_binding=self.f.authority,
                root=self.f.root,ledger=self.f.root/'unused.sqlite',repo=self.f.repo)
        self.loader.assert_not_called()
        value=self.freeze()['descriptor'];self.loader.reset_mock()
        value['companies'].reverse()
        with self.assertRaises(ValueError):self.f.load(value)
        self.loader.assert_not_called()


if __name__=='__main__':unittest.main()
