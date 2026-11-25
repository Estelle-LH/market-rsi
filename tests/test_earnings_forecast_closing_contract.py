"""Exact forward policy declaration on synthetic immutable replay origins."""
from copy import deepcopy
import unittest

import earnings_population_campaign_admission as admission
from edgar_forecast_openai import capacity_forecast_closing_policy
from market_rsi import digest
import test_earnings_population_control_history as history_fixture


class ClosingContractTests(unittest.TestCase):
    def setUp(self):
        self.f = history_fixture.HistoryBridgeTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)

    def test_exact_forward_policy_and_existing_resource_bridges_keep_original_contract(self):
        for old in (self.f.historical, self.f.current):
            old = deepcopy(old)
            new = deepcopy(self.f.current)
            new['limits']['author']['max_input_tokens'] = 96000
            new['limits']['review']['max_input_tokens'] = 32000
            new['forecast_closing_policy'] = capacity_forecast_closing_policy()
            origin = self.f.origin_for_contract(old)
            self.assertEqual(admission.last_scored_contract_sha256(origin, new), digest(old))
            self.assertNotEqual(digest(old), digest(new))

    def test_same_policy_keeps_identity_without_a_waiver(self):
        contract = dict(deepcopy(self.f.current), forecast_closing_policy=capacity_forecast_closing_policy())
        origin = self.f.origin_for_contract(contract)
        self.assertEqual(admission.last_scored_contract_sha256(origin, contract), digest(contract))

    def test_wrong_types_reverse_nearby_reserves_or_lossy_history_rejected(self):
        old = deepcopy(self.f.current)
        policy = capacity_forecast_closing_policy()
        for key, value in (('reserve_seconds', 600.0), ('reserve_seconds', True),
                           ('reserve_seconds', 599), ('reserve_seconds', 601),
                           ('deadline_source', 'new_relative_timer'), ('history_policy', 'truncate'),
                           ('retry_allowed', 0), ('retry_allowed', True), ('scope', 'all_forecasts')):
            changed = dict(policy, **{key: value})
            with self.subTest(key=key, value=value):
                origin = self.f.origin_for_contract(old)
                with self.assertRaisesRegex(ValueError, 'finalization policy'):
                    admission.last_scored_contract_sha256(origin, dict(old, forecast_closing_policy=changed))
                origin = self.f.origin_for_contract(dict(old, forecast_closing_policy=changed))
                with self.assertRaisesRegex(ValueError, 'finalization policy'):
                    admission.last_scored_contract_sha256(origin, dict(old, forecast_closing_policy=policy))
        origin = self.f.origin_for_contract(dict(old, forecast_closing_policy=policy))
        with self.assertRaisesRegex(ValueError, 'finalization policy'):
            admission.last_scored_contract_sha256(origin, old)

    def test_declared_policy_does_not_authorize_other_scientific_drift(self):
        old = deepcopy(self.f.current)
        origin = self.f.origin_for_contract(old)
        for key in ('data', 'scorer', 'model', 'runtime', 'unreviewed_waiver'):
            new = dict(deepcopy(old), forecast_closing_policy=capacity_forecast_closing_policy())
            new[key] = {'changed': True}
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'fixed task'):
                admission.last_scored_contract_sha256(origin, new)


if __name__ == '__main__':
    unittest.main()
