"""Independent inert fixed-panel campaign contracts, not live admission proof.

The original pure pool and seven-stage journal run against temporary originals.
Controller/Author/review/forecast and admission are explicit synthetic callbacks;
there is no model, Docker, scorer, real ledger or financial-gain claim.
"""
from copy import deepcopy
from pathlib import Path
import unittest

import earnings_population as pool
import earnings_population_campaign as campaign
import earnings_population_loop as loop
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
from supervisor_harness import feedback_linked_loop as journal
from test_earnings_population import PopulationFixture


CAPITAL = 'CIK0000017313'
VALIDATION = 'CIK0000021076'


class CampaignContracts(PopulationFixture):
    def setUp(self):
        super().setUp()
        self.initial, self.r1 = self.retained(child=self.child(label='starting-R1'))
        scores = [{'version_id': ident, 'points': points, 'evidence': self.evidence}
                  for ident, points in ((self.stable['id'], 2.5), (self.r1['id'], 3.5))]
        self.scored = self.artifact({'schema': 'earnings_population_feedback_v1',
            'company_id': CAPITAL, 'stable_id': self.stable['id'], 'round_index': 1,
            'results': scores, 'synthetic': True}, 'last-scored')
        self.initial = pool.observe(self.initial, CAPITAL, scores, feedback=self.scored)
        self.rejection = self.artifact({'schema': 'earnings_population_rejection_feedback_v1',
            'company_id': CAPITAL, 'kind': 'review_rejected', 'score_state': 'unscored',
            'population_sha256': digest(self.initial), 'active_parent_id': self.r1['id'],
            'last_scored_feedback': self.scored,
            'scope': 'Synthetic rejection seed; closed real-run verification is not mocked as proof.'}, 'rejection')
        self.plan = self.artifact({'schema': 'supervisor_bottleneck_plan_v1',
                                   'id': 'synthetic-campaign-plan'}, 'plan')
        self.contract = {'schema': 'synthetic_fixed_contract_v1', 'model_sha256': self.protected['M'],
                         'kernel_sha256': self.protected['K'], 'initial_records': []}
        self.loop_root = self.root/'campaign'
        self.calls = {name: [] for name in ('controller', 'author', 'review', 'forecast')}
        self.trace = ['R', 'R']
        self.accepted = [False, True]
        self.derive_from_latest = False
        self.retire_latest = False
        self.retire_baseline = False
        self.retire_stable = False
        self.bad_feedback = False
        self.fail_forecast_at = None
        self.drift_on_baseline = False
        self.children = []
        self.identities = {stage: {'synthetic_campaign_callback': stage} for stage in journal.STAGES}

    def manifest(self, rounds=2, **changes):
        value = {'schema': 'earnings_population_campaign_v1', 'source_plan': self.plan,
                 'panel': [CAPITAL], 'baseline_version_id': self.r1['id'], 'max_decisions': rounds,
                 'initial_population_sha256': digest(self.initial), 'initial_feedback': self.rejection,
                 'last_scored_feedback': self.scored, 'contract': deepcopy(self.contract),
                 'validation_company_id': VALIDATION}
        value.update(changes)
        return self.artifact(value, 'campaign-manifest')

    def controller(self, packet, slot):
        self.calls['controller'].append((deepcopy(packet), slot))
        index = packet['round_index']-1
        state = packet['population']
        parent = self.r1['id']
        if self.derive_from_latest and self.children and self.children[-1]['id'] in state['explorers']:
            parent = self.children[-1]['id']
        decision = {'schema': 'earnings_capacity_decision_v1', 'axis': self.trace[index],
                    'component': 'research_policy', 'parent_pair_sha256': parent,
                    'feedback_sha256': 'f'*64 if self.bad_feedback else digest(packet['feedback']),
                    'hypothesis': 'Synthetic discriminating repair; no financial correctness claim.'}
        if self.retire_stable:
            decision['retire_branch_id'] = state['stable_id']
        elif self.retire_baseline and len(state['explorers']) == 2:
            decision['retire_branch_id'] = self.r1['id']
        elif self.retire_latest and len(state['explorers']) == 2:
            decision['retire_branch_id'] = self.children[-1]['id']
        return self.artifact(decision, 'decision')

    def author(self, chosen, state, slot):
        # The real service consumes Controller-cached context; this inert
        # callback asserts only the actual decision's exact feedback binding.
        packet = self.calls['controller'][-1][0]
        self.assertEqual(chosen['feedback_sha256'], digest(packet['feedback']))
        self.calls['author'].append((deepcopy(chosen), deepcopy(state), slot))
        child = self.child(parent=state['versions'][chosen['parent_pair_sha256']],
                           axis=chosen['axis'], label=f'campaign-child-{len(self.children)+1}')
        self.children.append(child)
        return child

    def review(self, child, state, slot):
        index = len(self.calls['review'])
        self.calls['review'].append((deepcopy(child), deepcopy(state), slot))
        return {'accepted_for_exploration': self.accepted[index],
                'evidence': [self.artifact({'synthetic_review': True, 'candidate_id': child['id'],
                                             'accepted': self.accepted[index]}, 'review')]}

    def forecast(self, version, company_id, slot):
        self.calls['forecast'].append((deepcopy(version), company_id, slot))
        if self.fail_forecast_at == len(self.calls['forecast']):
            raise RuntimeError('Synthetic failed forecast; must not repeat callbacks')
        if self.drift_on_baseline and len(self.calls['forecast']) == 1:
            Path(version['R']['path']).write_text('Synthetic changed baseline after first forecast')
        points = 3.5 if version['id'] == self.r1['id'] else 4.0
        return {'version_id': version['id'], 'points': points,
                'evidence': [self.artifact({'synthetic': True, 'company_id': company_id,
                                             'version_id': version['id'], 'slot': slot}, 'forecast')]}

    def services(self):
        return {name: getattr(self, name) for name in self.calls}

    def run_campaign(self, binding=None, *, rounds=2):
        if binding is None:
            binding = self.manifest(rounds)
        return loop.run(self.loop_root, self.initial, [CAPITAL]*rounds, self.services(),
                        admit=lambda ctx: True, max_rounds=rounds,
                        identity=lambda: self.identities, campaign=binding)

    def feedback_at(self, index):
        return engine.read(engine.pin(self.loop_root/f'feedback-{index:02d}.json'))

    def test_actual_new_parent_is_measured_separately_from_fixed_control_next_round(self):
        self.accepted = [True, True]
        self.derive_from_latest = True
        self.retire_baseline = True
        manifest = self.manifest(comparison_policy=campaign.PARENT_COMPARISON)
        result = self.run_campaign(manifest)
        self.assertEqual(result['completed_rounds'], 2)
        first, second = self.children
        self.assertEqual(second['parent'], first['id'])
        self.assertEqual([v[0]['id'] for v in self.calls['forecast']],
            [self.r1['id'], first['id'], self.r1['id'], first['id'], second['id']])
        feedback = self.feedback_at(2)
        self.assertEqual(feedback['chosen_parent_id'], first['id'])
        self.assertEqual([v['version_id'] for v in feedback['results']],
                         [self.r1['id'], first['id'], second['id']])
        self.assertEqual(self.calls['controller'][1][0]['feedback'],
                         engine.pin(self.loop_root/'feedback-01.json'))
        self.assertNotEqual(feedback['chosen_parent_id'], feedback['baseline_version_id'])

    def test_unknown_parent_comparison_policy_is_rejected_before_any_callback(self):
        with self.assertRaises(ValueError):
            self.run_campaign(self.manifest(comparison_policy='pretend_old_score_is_parent'))
        self.assertFalse(any(self.calls.values()))

    def test_rejection_flows_to_next_controller_and_author_without_score_or_activation(self):
        before = deepcopy(self.initial)
        bound = self.manifest()
        result = self.run_campaign(bound)
        self.assertEqual((result['status'], result['completed_rounds']), ('completed', 2))
        first, second = self.feedback_at(1), self.feedback_at(2)
        self.assertEqual((first['kind'], first['score_state'], first['results']),
                         ('review_rejected', 'unscored', []))
        packet2 = self.calls['controller'][1][0]
        self.assertEqual(packet2['feedback'], engine.pin(self.loop_root/'feedback-01.json'))
        self.assertEqual(packet2['population'], before)
        self.assertEqual(packet2['last_scored_feedback'], self.scored)
        self.assertEqual(self.calls['author'][1][0]['feedback_sha256'], digest(packet2['feedback']))
        self.assertEqual(first['candidate']['id'], self.children[0]['id'])
        self.assertNotIn(self.children[0]['id'], packet2['population']['versions'])
        self.assertEqual(first['previous_feedback'], self.rejection)
        self.assertEqual(second['previous_feedback'], packet2['feedback'])
        self.assertEqual([row[0]['id'] for row in self.calls['forecast']],
                         [self.r1['id'], self.children[1]['id']])
        final = result['result']
        self.assertEqual(final['latest_feedback'], final['feedback'])
        self.assertEqual(final['last_scored_feedback'], final['feedback'])
        self.assertEqual(final['population']['observations'], before['observations'])
        self.assertEqual(final['population']['exposed_companies'], before['exposed_companies'])
        self.assertEqual(self.initial, before)
        self.assertEqual(final['population']['stable_id'], before['stable_id'])

    def test_two_accepted_decisions_score_fresh_starting_baseline_even_when_parent_changes(self):
        self.accepted = [True, True]
        self.derive_from_latest = self.retire_latest = True
        bound = self.manifest()
        result = self.run_campaign(bound)
        self.assertEqual([row[0]['id'] for row in self.calls['forecast']],
                         [self.r1['id'], self.children[0]['id'], self.r1['id'], self.children[1]['id']])
        self.assertEqual(self.children[1]['parent'], self.children[0]['id'])
        second = self.feedback_at(2)
        self.assertEqual(second['chosen_parent_id'], self.children[0]['id'])
        self.assertEqual(second['baseline_version_id'], self.r1['id'])
        self.assertEqual(second['kind'], 'scored_dev')
        self.assertEqual(len(result['result']['population']['explorers']), 2)
        self.assertIn(self.children[0]['id'], result['result']['population']['versions'])
        self.assertNotIn(self.children[0]['id'], result['result']['population']['explorers'])
        self.assertEqual([Path(row[2]).name for row in self.calls['forecast']],
                         ['forecast-01-00', 'forecast-01-01', 'forecast-02-00', 'forecast-02-01'])
        counts = {name: len(calls) for name, calls in self.calls.items()}
        self.assertEqual(self.run_campaign(bound), result)
        self.assertEqual({name: len(calls) for name, calls in self.calls.items()}, counts)

    def test_all_rejected_decisions_keep_pool_and_last_score_and_never_forecast(self):
        self.accepted = [False, False]
        result = self.run_campaign()
        self.assertEqual(result['result']['population'], self.initial)
        self.assertEqual(result['result']['last_scored_feedback'], self.scored)
        self.assertEqual(self.calls['forecast'], [])
        for index in (1, 2):
            value = self.feedback_at(index)
            self.assertEqual((value['kind'], value['score_state'], value['results']),
                             ('review_rejected', 'unscored', []))
            self.assertTrue((self.loop_root/f'decision-{index:02d}.json').is_file())

    def test_no_change_is_unscored_without_author_review_forecast_or_explicit_retirement(self):
        self.trace = ['continue', 'continue']
        result = self.run_campaign()
        self.assertEqual(result['result']['population'], self.initial)
        self.assertEqual(result['result']['last_scored_feedback'], self.scored)
        self.assertEqual({name: len(self.calls[name]) for name in ('author', 'review', 'forecast')},
                         {'author': 0, 'review': 0, 'forecast': 0})
        for index in (1, 2):
            self.assertEqual((self.feedback_at(index)['kind'], self.feedback_at(index)['results']),
                             ('no_change', []))

    def test_rejected_replacement_cannot_retire_existing_explorer(self):
        self.accepted = [True, False]
        self.retire_latest = True
        result = self.run_campaign()
        first = engine.read(engine.pin(self.loop_root/'population-01.json'))
        self.assertEqual(result['result']['population'], first)
        self.assertEqual(len(self.calls['forecast']), 2)
        self.assertNotIn(self.children[1]['id'], first['versions'])
        self.assertEqual(result['result']['last_scored_feedback'], engine.pin(self.loop_root/'feedback-01.json'))

    def test_archived_starting_baseline_still_has_fresh_matched_forecast(self):
        self.accepted = [True, True]
        self.derive_from_latest = self.retire_baseline = True
        result = self.run_campaign()
        final = result['result']['population']
        self.assertNotIn(self.r1['id'], final['explorers'])
        self.assertIn(self.r1['id'], final['versions'])
        self.assertEqual([version['id'] for version, _, _ in self.calls['forecast']],
                         [self.r1['id'], self.children[0]['id'], self.r1['id'], self.children[1]['id']])

    def test_continue_cannot_retire_a_valid_existing_explorer(self):
        self.trace = ['R', 'continue']
        self.accepted = [True]
        self.retire_latest = True
        result = self.run_campaign()
        self.assertEqual(result['result']['population'], engine.read(engine.pin(self.loop_root/'population-01.json')))
        self.assertEqual(len(self.calls['forecast']), 2)
        self.assertEqual(self.feedback_at(2)['kind'], 'no_change')

    def test_generated_rejection_can_seed_next_campaign_without_reopening_old_journal(self):
        self.accepted = [False]
        first = self.run_campaign(rounds=1)
        old_root = self.loop_root
        original_bytes = {str(p): p.read_bytes() for p in old_root.rglob('*') if p.is_file()}
        self.loop_root = self.root/'second-campaign'
        self.trace = ['continue']
        bound = self.manifest(1, initial_feedback=first['result']['latest_feedback'],
                              last_scored_feedback=first['result']['last_scored_feedback'])
        second = self.run_campaign(bound, rounds=1)
        self.assertEqual(self.calls['controller'][-1][0]['feedback'], first['result']['latest_feedback'])
        self.assertEqual(second['result']['last_scored_feedback'], self.scored)
        self.assertEqual(second['result']['population'], self.initial)
        self.assertEqual(original_bytes, {str(p): p.read_bytes() for p in old_root.rglob('*') if p.is_file()})

    def test_inherited_campaign_contract_or_unscored_results_drift_is_rejected(self):
        self.accepted = [False]
        first = self.run_campaign(rounds=1)
        value = engine.read(first['result']['feedback'])
        for changes in ({'campaign_contract_sha256': 'f'*64}, {'score_state': 'scored'},
                        {'results': [{'version_id': self.r1['id'], 'points': 5, 'evidence': self.evidence}]}):
            seed = self.artifact(dict(value, **changes), 'bad-campaign-feedback')
            bound = self.manifest(1, initial_feedback=seed)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                campaign.load(bound, self.initial, [CAPITAL], 1)

    def test_changed_bound_plan_bytes_and_stale_campaign_bindings_are_rejected(self):
        binding = self.manifest()
        Path(self.plan['path']).write_text('Synthetic changed plan bytes')
        with self.assertRaises(ValueError):
            campaign.load(binding, self.initial, [CAPITAL, CAPITAL], 2)
        self.assertEqual(sum(map(len, self.calls.values())), 0)

    def test_full_pool_without_explicit_retirement_stops_before_second_author(self):
        self.accepted = [True, True]
        with self.assertRaises(journal.LoopHalted):
            self.run_campaign()
        self.assertEqual((len(self.calls['author']), len(self.calls['forecast'])), (1, 2))

    def test_stable_retirement_and_stale_feedback_stop_before_author(self):
        for kind in ('stable', 'feedback'):
            self.loop_root = self.root/kind
            self.retire_stable, self.bad_feedback = kind == 'stable', kind == 'feedback'
            with self.subTest(kind=kind), self.assertRaises(journal.LoopHalted):
                self.run_campaign()
        self.assertEqual(self.calls['author'], [])
        self.assertEqual(self.calls['forecast'], [])

    def test_genuine_stage_failure_preserved_no_next_decision_or_automatic_retry(self):
        self.accepted = [True, True]
        self.fail_forecast_at = 2
        bound = self.manifest()
        with self.assertRaises(journal.LoopHalted):
            self.run_campaign(bound)
        self.assertEqual(len(self.calls['controller']), 1)
        failure = self.loop_root/'loop/round-0001-execute.failed.json'
        self.assertFalse(engine.read(engine.pin(failure))['retry_allowed'])
        self.assertFalse((self.loop_root/'feedback-01.json').exists())
        counts = {name: len(calls) for name, calls in self.calls.items()}
        with self.assertRaises(journal.LoopHalted):
            self.run_campaign(bound)
        self.assertEqual({name: len(calls) for name, calls in self.calls.items()}, counts)

    def test_source_drift_after_baseline_stops_before_candidate_forecast(self):
        self.accepted = [True, True]
        self.drift_on_baseline = True
        with self.assertRaises(journal.LoopHalted):
            self.run_campaign()
        self.assertEqual(len(self.calls['forecast']), 1)

    def test_default_fresh_company_guards_unchanged_without_campaign(self):
        for companies in ([CAPITAL], ['new', 'new']):
            with self.subTest(companies=companies), self.assertRaises(ValueError):
                loop.run(self.loop_root, self.initial, companies, self.services(),
                         admit=lambda ctx: True, max_rounds=len(companies), identity=lambda: self.identities)
        self.assertEqual(sum(map(len, self.calls.values())), 0)

    def test_campaign_manifest_rejects_wrong_scope_bounds_baseline_seed_and_contract(self):
        changes = ({'panel': [VALIDATION]}, {'max_decisions': 0}, {'max_decisions': 3},
                   {'max_decisions': True}, {'baseline_version_id': 'f'*64},
                   {'initial_population_sha256': 'f'*64}, {'contract': {}},
                   {'validation_company_id': CAPITAL}, {'extra_cache': {'points': 5}})
        for change in changes:
            bound = self.manifest(**change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                campaign.load(bound, self.initial, [CAPITAL, CAPITAL], 2)
        self.assertEqual(sum(map(len, self.calls.values())), 0)

    def test_campaign_rejection_seed_cannot_carry_or_rename_fake_score(self):
        for changes in ({'points': 5}, {'results': []}, {'score_state': 'scored'},
                        {'kind': 'scored_dev'}, {'last_scored_feedback': self.plan},
                        {'company_id': VALIDATION}):
            value = dict(engine.read(self.rejection), **changes)
            binding = self.manifest(initial_feedback=self.artifact(value, 'bad-seed'))
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                campaign.load(binding, self.initial, [CAPITAL, CAPITAL], 2)

    def test_last_scored_pointer_requires_matching_company_baseline_and_real_score_rows(self):
        original = engine.read(self.scored)
        for changes in ({'company_id': VALIDATION}, {'results': []},
                        {'results': [{'version_id': self.stable['id'], 'points': 3, 'evidence': self.evidence}]},
                        {'results': [{'version_id': self.r1['id'], 'points': 6, 'evidence': self.evidence}]}):
            last = self.artifact(dict(original, **changes), 'bad-last-score')
            rejection = self.artifact(dict(engine.read(self.rejection), last_scored_feedback=last), 'bad-prior')
            binding = self.manifest(initial_feedback=rejection, last_scored_feedback=last)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                campaign.load(binding, self.initial, [CAPITAL, CAPITAL], 2)


if __name__ == '__main__':
    unittest.main()
