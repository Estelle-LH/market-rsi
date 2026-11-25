"""Real default path metadata, without ledger/data/admission or activation.

ROOT, LEDGER and AUTHORITY are never substituted. The ceiling probe stops at
its first Source read; it does not accept a synthetic authority or runtime.
"""
import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch

import earnings_population_budget as original
import earnings_population_model_budget as model
import earnings_population_panel_budget as panel
import earnings_population_training25 as training


AUTHORITY_SHA = '6996d8ef270b45cd2eb9dcbb15c644674b3650f33c4a3459f2f61fd358525447'


class CanonicalPanelBudgetPaths(unittest.TestCase):
    def test_real_default_root_is_training_authority_namespace(self):
        expected = original.LEDGER.parents[2] / 'edgar-population-20261016'
        self.assertEqual(panel.ROOT, expected)
        self.assertEqual(panel.ROOT, training.ROOT)
        self.assertEqual(panel.ROOT.resolve(), panel.ROOT)

    def test_real_authority_binding_and_metadata_bytes_are_exact(self):
        expected = training.ROOT / 'TRAIN25-DIRECT-WINDOW50-AUTHORITY.json'
        self.assertEqual(panel.AUTHORITY, dict(path=str(expected), sha256=AUTHORITY_SHA))
        self.assertEqual(panel._binding(panel.AUTHORITY, expected), expected)
        self.assertEqual(hashlib.sha256(expected.read_bytes()).hexdigest(), AUTHORITY_SHA)

    def test_canonical_ceiling_metadata_reaches_first_source_read_only(self):
        identifier = 'edgar-population-20261016-41'
        source_path = Path(panel.__file__).resolve()
        source = dict(path=str(source_path),
                      sha256=hashlib.sha256(source_path.read_bytes()).hexdigest())
        value = dict(schema='earnings_population_runtime_v1', id=identifier,
            root=str(training.ROOT / 'attempts' / identifier),
            ledger=str(original.LEDGER), companies=['CIK0000003545'],
            training_policy=training.POLICY, frozen_panel_policy=panel.POLICY,
            window_minutes=90, additional_cap_nano_usd=panel.PANEL_CAP,
            panel_window_budget_authority=dict(panel.AUTHORITY),
            budget_amendment=dict(path=str(original.LEDGER.parent / original.NAME), sha256='0' * 64),
            model_budget_amendment=dict(path=str(original.LEDGER.parent / model.NAME), sha256='0' * 64),
            sources={panel.SOURCE: source})

        class StopBeforeBody(Exception):
            pass

        with patch.object(panel, '_read', side_effect=StopBeforeBody) as read:
            with self.assertRaises(StopBeforeBody):
                panel.ceiling(value)
        read.assert_called_once_with(source, source_path, binary=True)

    def test_wrong_parent_and_alias_refuse_the_metadata_join(self):
        expected = training.ROOT / 'TRAIN25-DIRECT-WINDOW50-AUTHORITY.json'
        wrong = original.LEDGER.parent.parent / 'edgar-population-20261016' / expected.name
        alias = str(training.ROOT / '..' / training.ROOT.name / expected.name)
        with patch.object(panel, '_read', side_effect=AssertionError('No body read')) as read:
            for path in (str(wrong), alias):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    panel._binding(dict(path=path, sha256=AUTHORITY_SHA), expected)
        read.assert_not_called()

    def test_legacy_no_optin_keeps_five_without_reads(self):
        with patch.object(panel, '_read', side_effect=AssertionError('No overlay read')) as read:
            self.assertEqual(panel.ceiling({}), 5_000_000_000)
            self.assertEqual(panel.ceiling(dict(additional_cap_nano_usd=50_000_000_000)),
                             5_000_000_000)
        read.assert_not_called()


if __name__ == '__main__':
    unittest.main()
