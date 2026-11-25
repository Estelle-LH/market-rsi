"""Portable registration-order tests, not historical/Native/financial admission.

PanelBudget Fixture uses invented split/authority/runtime metadata, a TEMPORARY
ledger and explicit original400/model-grant/Git seams. The Reader and ceiling
under test are real. The receiver-order test uses the existing WindowFixture's
explicit predecessor/Native/financial/projection seams and stops at its FIRST
scan; none of those substitute boundaries is claimed as successful admission.
No original company/QA/heldout/ledger or history replay is accessed.
"""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

import earnings_population_continuation as history
import earnings_population_panel_budget as panel
import earnings_population_panel_completed as receiver
from test_earnings_population_panel_budget import Fixture, save
from test_earnings_population_panel_completed import WindowFixture


class StopAtFirstScan(Exception):
    pass


class AuthorityRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.f=Fixture(); self.addCleanup(self.f.close)
        self.raw=Path(panel.__file__).read_bytes()
        self.value=deepcopy(self.f.value)
        import hashlib
        self.value['sources']={panel.SOURCE:dict(path=str(self.f.repo/panel.SOURCE),
            sha256=hashlib.sha256(self.raw).hexdigest())}
        self.reader=history._Reader(self.f.owned,self.f.ledger,self.f.repo,self.f.ident)
        self.reader.register_sources(self.value)

    def test_original_scan_refuses_global_authority_before_any_artifact_body(self):
        with patch.object(history,'_artifact_bytes',side_effect=AssertionError('ARTIFACT_BODY_READ')):
            with self.assertRaisesRegex(ValueError,'outside exact owned roots'):
                self.reader.scan({'panel_window_budget_authority':self.f.overlay})
        self.assertEqual(self.reader.extra,set())

    def test_real_strict_ceiling_registers_only_exact_authority_before_scan(self):
        with patch.object(history,'_git',return_value=self.raw):
            self.assertEqual(panel.ceiling(self.value,historical_reader=self.reader),panel.PANEL_CAP)
            self.reader.scan({'panel_window_budget_authority':self.f.overlay})
        self.assertEqual(self.reader.extra,{Path(self.f.overlay['path'])})
        sibling=save(self.f.owned/'unrelated-authority.json',{'not':'authority'})
        with patch.object(history,'_artifact_bytes',side_effect=AssertionError('SIBLING_BODY_READ')):
            with self.assertRaisesRegex(ValueError,'outside exact owned roots'):
                self.reader.read(sibling)

    def test_alias_authority_refuses_before_metadata_body(self):
        bad=deepcopy(self.value)
        bad['panel_window_budget_authority']=dict(self.f.overlay,
            path=str(self.f.owned/'authority-alias.json'))
        with patch.object(panel,'_read',side_effect=AssertionError('ALIAS_BODY_READ')):
            with self.assertRaisesRegex(ValueError,'canonical panel-budget path'):
                panel.ceiling(bad,historical_reader=self.reader)
        self.assertEqual(self.reader.extra,set())

    def test_malformed_authority_never_becomes_registered(self):
        for binding in (None,{},dict(self.f.overlay,sha256='0'*64),
                        dict(self.f.overlay,unexpected=True)):
            value=deepcopy(self.value); value['panel_window_budget_authority']=binding
            with self.subTest(binding=binding),patch.object(panel,'_read',
                    side_effect=AssertionError('MALFORMED_BODY_READ')):
                with self.assertRaises(ValueError):
                    panel.ceiling(value,historical_reader=self.reader)
            self.assertEqual(self.reader.extra,set())

    def test_same_file_byte_tamper_refuses_without_registration(self):
        Path(self.f.overlay['path']).write_bytes(b'{}')
        with patch.object(history,'_git',return_value=self.raw):
            with self.assertRaisesRegex(ValueError,'original bytes differ'):
                panel.ceiling(self.value,historical_reader=self.reader)
        self.assertEqual(self.reader.extra,set())

    def test_historical_source_mismatch_cannot_register_authority(self):
        with patch.object(history,'_git',return_value=b'# wrong registered bytes\n'):
            with self.assertRaisesRegex(ValueError,'artifact/source hash differs'):
                panel.ceiling(self.value,historical_reader=self.reader)
        self.assertEqual(self.reader.extra,set())

    def test_legacy_no_authority_remains5_with_no_extra_or_overlay_read(self):
        with patch.object(panel,'_read',side_effect=AssertionError('LEGACY_OVERLAY_READ')):
            self.assertEqual(panel.ceiling({},historical_reader=self.reader),panel.LEGACY_CAP)
            self.assertEqual(panel.ceiling({'additional_cap_nano_usd':panel.PANEL_CAP},
                historical_reader=self.reader),panel.LEGACY_CAP)
        self.assertEqual(self.reader.extra,set())


class ReceiverOrderTests(unittest.TestCase):
    def test_existing_receiver_calls_real_ceiling_before_its_first_recursive_scan(self):
        fixture=WindowFixture(); self.addCleanup(fixture.close)
        calls=[]; original=receiver.ceiling

        def ceiling(value,*,historical_reader):
            result=original(value,historical_reader=historical_reader)
            calls.append((value,historical_reader,result))
            return result

        def first_scan(reader,value):
            self.assertEqual(len(calls),1)
            self.assertIs(calls[0][1],reader)
            self.assertEqual(calls[0][0],fixture.runtime)
            self.assertEqual(calls[0][2],panel.LEGACY_CAP)
            self.assertEqual(value,fixture.runtime)
            raise StopAtFirstScan('ORDER_PROVEN_BEFORE_BUDGET_NATIVE')

        with patch.object(receiver,'ceiling',side_effect=ceiling),patch.object(
                history._Reader,'scan',autospec=True,side_effect=first_scan):
            with self.assertRaisesRegex(StopAtFirstScan,'ORDER_PROVEN'):
                fixture.load()
        fixture.financial.assert_not_called()
        fixture.native.assert_not_called()
        fixture.projection.assert_not_called()


if __name__=='__main__': unittest.main()

