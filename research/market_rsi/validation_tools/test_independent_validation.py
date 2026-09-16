import copy
from datetime import date, datetime, timedelta, timezone
import unittest

import independent_validation as gate
from market_rsi import digest


def stamp(value):
    return int(datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp() * 1000)


def fixture():
    context = {'schema': 'historical_independent_validation_context_v1',
               'experiment_id': 'fixture-study', 'budget_cap_usd': '200',
               'budget_authorization_sha256': 'f' * 64, 'model_sha256': 'a' * 64,
               'selected_plan_sha256': 'b' * 64, 'objective_sha256': 'c' * 64,
               'source_contract_sha256': 'd' * 64, 'minimum_final_utc_days': 20,
               'known_opened_dates_lower_bound': ['2026-05-14'], 'allow_refit': False,
               'allow_target_or_feature_change': False, 'claim_scope': 'prediction_only_not_pnl_or_rsi'}
    context['context_sha256'] = digest(context)
    days = [(date(2026, 6, 1) + timedelta(days=i)).isoformat() for i in range(20)]
    proposal = {'proposal_id': 'fixture-validation', 'context_sha256': context['context_sha256'],
                'source_contract_sha256': context['source_contract_sha256'], 'utc_dates': days,
                'embargo_ms': 1800000, 'minimum_coverage_fraction': .8,
                'minimum_market_groups_per_day': 2,
                'interval': {'unit': 'utc_date', 'block_days': 2, 'replicates': 200, 'confidence': .95},
                'reason': 'Synthetic metadata only; no market prices or simulated performance.'}
    runner = {'schema': 'historical_validation_runner_evidence_v1',
              'budget_authorization_sha256': context['budget_authorization_sha256'],
              'proposal_sha256': digest(proposal), 'context_sha256': context['context_sha256'],
              'reviewed_proof_hashes': {k: 'e' * 64 for k in gate.PROOF_KINDS},
              'source_compatible': True, 'exposure_audit_complete': True,
              'whole_market_isolation': True, 'causal_timestamps_verified': True,
              'quiet_rows_retained': True, 'same_evaluation_population': True,
              'policy_frozen_before_new_label_access': True, 'cohort_never_scored': True,
              'source_values_imputed': False, 'future_value_filter': False,
              'new_labels_exposed_to_controller': False, 'refit_requested': False,
              'latest_learning_label_available_ms': stamp('2026-05-14') + 1800000,
              'opened_market_groups': ['already-opened-market'],
              'sessions': [{'utc_date': d, 'exposure_state': 'verified_untouched', 'closed': True,
                            'coverage_fraction': .9, 'market_groups': [d + '-a', d + '-b'],
                            'first_feature_available_ms': stamp(d)} for d in days],
              'runner_cost_upper_usd': '2.5', 'new_download_bytes_upper': 0,
              'authorized_download_headroom_bytes': 0, 'vendor_purchase_usd': '0'}
    for k in ('model_sha256', 'selected_plan_sha256', 'objective_sha256', 'source_contract_sha256'):
        runner[k] = context[k]
    budget = {'experiment_id': 'fixture-study', 'cap_usd': '200', 'available_usd': '170',
              'buckets': {'final': {'available_usd': '50'}}}
    return proposal, context, runner, budget


class IndependentValidationTests(unittest.TestCase):
    def setUp(self):
        self.p, self.c, self.r, self.b = fixture()

    def check(self):
        return gate.check_runner_evidence(self.p, self.c, self.r, self.b)

    def blocked(self, text):
        result = self.check()
        self.assertFalse(result['metadata_gate_passed'])
        self.assertTrue(any(text in reason for reason in result['blockers']), result)
        self.assertFalse(result['execution_admitted'])

    def test_valid_metadata_is_not_permission_or_dispatch(self):
        result = self.check()
        self.assertTrue(result['metadata_gate_passed'])
        self.assertTrue(result['dates_are_not_yet_admitted'])
        self.assertFalse(result['execution_admitted'])
        self.assertFalse(result['dispatch_token_created'])
        self.assertFalse(result['scientific_power_proven'])

    def test_model_or_objective_changes_rejected(self):
        for key in ('model_sha256', 'selected_plan_sha256', 'objective_sha256', 'source_contract_sha256'):
            with self.subTest(key=key):
                _, _, self.r, _ = fixture()
                self.r[key] = 'f' * 64
                with self.assertRaisesRegex(ValueError, 'would change'):
                    self.check()

    def test_controller_cannot_self_assert_freshness(self):
        self.p['exposure_audit_complete'] = True
        with self.assertRaisesRegex(ValueError, 'exact validation proposal'):
            self.check()

    def test_new_source_requires_separate_data_stage(self):
        self.p['source_contract_sha256'] = 'f' * 64
        with self.assertRaisesRegex(ValueError, 'separate data-stage'):
            self.check()

    def test_model_parameters_not_controller_fields(self):
        self.p['learning_rate'] = .1
        with self.assertRaisesRegex(ValueError, 'no model/target edits'):
            self.check()

    def test_context_tampering_rejected(self):
        self.c['allow_refit'] = True
        with self.assertRaisesRegex(ValueError, 'commitment changed'):
            self.check()

    def test_even_rehashed_context_cannot_relax_final_minimum(self):
        self.c['minimum_final_utc_days'] = 3
        self.c['context_sha256'] = digest({k: v for k, v in self.c.items() if k != 'context_sha256'})
        with self.assertRaisesRegex(ValueError, 'validation boundary'):
            self.check()

    def test_too_few_dates_rejected(self):
        self.p['utc_dates'] = self.p['utc_dates'][:19]
        with self.assertRaisesRegex(ValueError, '20 distinct'):
            self.check()

    def test_repeating_dates_does_not_increase_sessions(self):
        self.p['utc_dates'][-1] = self.p['utc_dates'][-2]
        with self.assertRaisesRegex(ValueError, 'unique and sorted'):
            self.check()

    def test_old_dates_not_allowed(self):
        self.p['utc_dates'][0] = '2026-05-14'
        with self.assertRaisesRegex(ValueError, 'all known opened'):
            self.check()

    def test_absent_proofs_block(self):
        self.r['reviewed_proof_hashes'].pop('exposure_history')
        self.blocked('proof_set_incomplete')

    def test_unknown_exposure_blocks(self):
        self.r['sessions'][0]['exposure_state'] = 'unknown'
        self.blocked('exposure_unknown')

    def test_incomplete_global_audit_blocks(self):
        self.r['exposure_audit_complete'] = False
        self.blocked('exposure_audit_complete_not_verified')

    def test_live_unclosed_session_blocks(self):
        self.r['sessions'][0]['closed'] = False
        self.blocked('session_not_closed')

    def test_missing_date_not_silently_dropped(self):
        self.r['sessions'].pop()
        self.blocked('session_dates_not_exactly')

    def test_insufficient_coverage_blocks(self):
        self.r['sessions'][0]['coverage_fraction'] = .1
        self.blocked('insufficient_coverage')

    def test_nan_coverage_not_accepted(self):
        self.r['sessions'][0]['coverage_fraction'] = float('nan')
        with self.assertRaisesRegex(ValueError, 'invalid observed'):
            self.check()

    def test_market_overlap_even_across_file_dates_blocks(self):
        self.r['sessions'][0]['market_groups'][0] = 'already-opened-market'
        self.blocked('market_group_already_opened')

    def test_label_embargo_boundary_is_strict(self):
        self.r['latest_learning_label_available_ms'] = stamp('2026-06-01') - self.p['embargo_ms']
        self.blocked('learning_label_embargo_overlap')

    def test_timestamp_date_inconsistency_rejected(self):
        self.r['sessions'][0]['first_feature_available_ms'] += 86400000
        with self.assertRaisesRegex(ValueError, 'date and feature clock'):
            self.check()

    def test_future_movement_filter_blocks(self):
        self.r['future_value_filter'] = True
        self.blocked('future_value_filter_not_false')

    def test_removing_quiet_records_blocks(self):
        self.r['quiet_rows_retained'] = False
        self.blocked('quiet_rows_retained_not_verified')

    def test_repeat_test_blocks(self):
        self.r['cohort_never_scored'] = False
        self.blocked('cohort_never_scored_not_verified')

    def test_runner_cost_cannot_consume_learning_bucket(self):
        self.r['runner_cost_upper_usd'] = '50.01'
        self.blocked('available_final_budget')

    def test_total_available_includes_existing_reservations(self):
        self.b['available_usd'] = '2.49'
        self.blocked('available_final_budget')

    def test_another_budget_is_not_a_reset(self):
        self.b['experiment_id'] = 'other-study'
        with self.assertRaisesRegex(ValueError, 'another experiment budget'):
            self.check()

    def test_new_download_requires_positive_authorized_headroom(self):
        self.r['new_download_bytes_upper'] = 1
        self.blocked('new_download_not_authorized')

    def test_same_named_experiment_cannot_reset_cap(self):
        self.b['cap_usd'] = '400'
        with self.assertRaisesRegex(ValueError, 'no budget reset'):
            self.check()

    def test_another_authorization_is_not_interchangeable(self):
        self.r['budget_authorization_sha256'] = 'e' * 64
        with self.assertRaisesRegex(ValueError, 'no budget reset'):
            self.check()

    def test_vendor_purchase_not_hidden_in_tinker_budget(self):
        self.r['vendor_purchase_usd'] = '1'
        self.blocked('vendor_purchase_authority')

    def test_no_row_bootstrap(self):
        self.p['interval']['unit'] = 'row'
        with self.assertRaisesRegex(ValueError, 'row-independent'):
            self.check()

    def test_boolean_and_nonfinite_parameters_rejected(self):
        for key, value in [('embargo_ms', True), ('minimum_coverage_fraction', float('inf'))]:
            self.p, self.c, self.r, self.b = fixture()
            self.p[key] = value
            with self.assertRaises(ValueError):
                self.check()

    def test_pure_check_does_not_mutate_input_metadata(self):
        before = copy.deepcopy((self.p, self.c, self.r, self.b))
        self.check()
        self.assertEqual(before, (self.p, self.c, self.r, self.b))


if __name__ == '__main__':
    unittest.main()
