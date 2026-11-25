"""Historical initial feedback keeps its original contract, not a relabel.

Inert callbacks only. Actual original/contract provenance remains the separate
source-bound admission/recovery check, never this pure campaign fixture.
"""
from copy import deepcopy
from pathlib import Path
import unittest

import earnings_population_campaign as campaign
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
from test_earnings_population_campaign import CampaignContracts, CAPITAL


class HistoricalInitialContract(unittest.TestCase):
    def fixture(self):
        f = CampaignContracts('runTest'); f.setUp(); self.addCleanup(f.doCleanups)
        f.run_campaign(rounds=1)
        old = engine.pin(f.loop_root/'feedback-01.json')
        current = deepcopy(f.contract)
        current['review_input_tokens'] = 20000
        return f, old, current

    def manifest(self, f, old, current, **changes):
        value = dict(initial_feedback=old, contract=current,
            comparison_policy=campaign.PARENT_COMPARISON,
            initial_feedback_contract_sha256=digest(f.contract))
        value.update(changes)
        return f.manifest(rounds=1, **value)

    def test_explicit_historical_initial_contract_preserves_old_feedback_bytes(self):
        f, old, current = self.fixture()
        before = Path(old['path']).read_bytes()
        bound = self.manifest(f, old, current)
        result = campaign.load(bound, f.initial, [CAPITAL], 1)
        self.assertEqual(result['initial_feedback_contract_sha256'], digest(f.contract))
        self.assertEqual(result['last_scored_feedback'], f.scored)
        self.assertNotEqual(digest(current), digest(f.contract))
        self.assertEqual(Path(old['path']).read_bytes(), before)

    def test_without_explicit_history_mapping_contract_drift_still_rejected(self):
        f, old, current = self.fixture()
        bound = f.manifest(rounds=1, initial_feedback=old, contract=current,
                           comparison_policy=campaign.PARENT_COMPARISON)
        with self.assertRaises(ValueError):
            campaign.load(bound, f.initial, [CAPITAL], 1)

    def test_wrong_or_malformed_historical_contract_still_rejected(self):
        f, old, current = self.fixture()
        for sha in ('f'*64, None, 'bad', 20000):
            with self.subTest(sha=sha), self.assertRaises(ValueError):
                campaign.load(self.manifest(f, old, current, initial_feedback_contract_sha256=sha),
                              f.initial, [CAPITAL], 1)

    def test_history_mapping_requires_explicit_parent_comparison_mode(self):
        f, old, current = self.fixture()
        bound = self.manifest(f, old, current, comparison_policy='other')
        with self.assertRaises(ValueError):
            campaign.load(bound, f.initial, [CAPITAL], 1)


if __name__ == '__main__':
    unittest.main()
