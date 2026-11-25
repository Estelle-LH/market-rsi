"""B2 producer/receiver wiring, with explicit B1 and old-origin fixture seams.

No production ledger, provider, Native, candidate or scorer is used. B1's
canonical financial validation is covered separately; these tests retain real
prepare/metadata and check the new optional field cannot downgrade to legacy.
"""
from copy import deepcopy
from unittest.mock import patch
import unittest

import earnings_population_panel_budget as budget
import earnings_population_run as run
import earnings_population_runtime as runtime
from supervisor_harness import capacity_feedback_engine as engine
from test_earnings_population_frozen_panel_runtime import PanelFixture
from test_earnings_population_runtime import Fixture


class ProducerTests(PanelFixture):
    def test_exact_overlay_is_explicit_and_mirrored_without_changing_other_limits(self):
        # Authority bytes and prior full-history origin are synthetic seams;
        # real B1 budget mechanics are not claimed by this producer test.
        with patch.object(budget,'_read',return_value={'fixture':'direct authority'}) as read:
            value=engine.read(self.prepare_panel(panel_window_budget_authority=budget.AUTHORITY))
        study=engine.read(value['forecast_study'])
        self.assertEqual(value['additional_cap_nano_usd'],budget.PANEL_CAP)
        self.assertEqual(value['window_minutes'],90)
        self.assertEqual(value['baseline'],self.baseline)
        self.assertEqual(value['model_budget_amendment'],self.model)
        self.assertEqual(value['panel_window_budget_authority'],budget.AUTHORITY)
        self.assertEqual(study['panel_window_budget_authority'],budget.AUTHORITY)
        read.assert_called_once_with(budget.AUTHORITY,__import__('pathlib').Path(budget.AUTHORITY['path']))
        self.assertFalse((self.root/'attempts'/self.id).exists())

    def test_absent_overlay_keeps_legacy_five_and_no_new_marker(self):
        value=engine.read(self.prepare_panel())
        self.assertEqual(value['additional_cap_nano_usd'],budget.LEGACY_CAP)
        self.assertNotIn('panel_window_budget_authority',value)
        self.assertNotIn('panel_window_budget_authority',engine.read(value['forecast_study']))

    def test_wrong_or_nonpanel_authority_refuses_before_any_input_or_origin_read(self):
        for marker,panel in (({},self.descriptor_binding),
                (dict(budget.AUTHORITY,sha256='f'*64),self.descriptor_binding),
                (budget.AUTHORITY,None)):
            with self.subTest(marker=marker,panel=panel),patch.object(budget,'_read') as read:
                with self.assertRaisesRegex(ValueError,'exact prospective authority'):
                    self.prepare_panel(frozen_panel=panel,panel_window_budget_authority=marker)
            read.assert_not_called()
            self.assertFalse((self.root/'inputs'/self.id).exists())
            self.old_loader.assert_not_called()

    def test_tampered_authority_refuses_before_input_creation(self):
        with patch.object(budget,'_read',side_effect=ValueError('bound bytes differ')):
            with self.assertRaisesRegex(ValueError,'bytes differ'):
                self.prepare_panel(panel_window_budget_authority=budget.AUTHORITY)
        self.assertFalse((self.root/'inputs'/self.id).exists())
        self.old_loader.assert_not_called()

    def test_runtime_or_study_only_marker_erasure_cannot_downgrade(self):
        value=engine.read(self.prepare_panel());study=engine.read(value['forecast_study'])
        for side in ('runtime','study'):
            v,s=deepcopy(value),deepcopy(study)
            (v if side=='runtime' else s)['panel_window_budget_authority']=budget.AUTHORITY
            v['forecast_study']=engine.save(self.root/('study-'+side+'.json'),s)
            # Own canonical metadata path remains enforced; patch only that
            # path namespace here to exercise the marker join in _study.
            with self.subTest(side=side),patch('earnings_population_campaign._training_input'):
                with self.assertRaisesRegex(ValueError,'companion panel-window budget'):
                    runtime._study(v)

    def test_present_null_is_not_absent_and_authenticates_before_origin(self):
        value=engine.read(self.prepare_panel());study=engine.read(value['forecast_study'])
        value['panel_window_budget_authority']=None;study['panel_window_budget_authority']=None
        value['forecast_study']=engine.save(self.root/'null-study.json',study)
        with patch('earnings_population_campaign._training_input'):
            with self.assertRaises(ValueError):runtime._study(value)


class RuntimeBoundaryTests(Fixture):
    def test_legacy_ceiling_does_not_import_or_read_overlay(self):
        with patch.object(budget,'ceiling',side_effect=AssertionError('overlay touched')):
            self.assertEqual(runtime._window_ceiling(self.value),budget.LEGACY_CAP)
            self.assertEqual(runtime.preflight(self.bound())['additional_cap_nano_usd'],budget.LEGACY_CAP)

    def test_explicit_ceiling_delegates_exact_value_to_b1(self):
        value=deepcopy(self.value);value['panel_window_budget_authority']=budget.AUTHORITY
        with patch.object(budget,'ceiling',return_value=budget.PANEL_CAP) as ceiling:
            self.assertEqual(runtime._window_ceiling(value),budget.PANEL_CAP)
        ceiling.assert_called_once_with(value)

    def test_large_cap_without_marker_and_malformed_with_marker_fail_before_study(self):
        for marker in ('absent',None,{},budget.AUTHORITY):
            value=deepcopy(self.value);value['additional_cap_nano_usd']=budget.PANEL_CAP
            if marker!='absent':value['panel_window_budget_authority']=marker
            with self.subTest(marker=marker),patch.object(runtime,'_study',side_effect=AssertionError('study reached')):
                with self.assertRaises(ValueError):runtime.preflight(self.bound(value))

    def test_b1_validated_ceiling_allows_field_through_to_original_study(self):
        class Reached(Exception):pass
        value=deepcopy(self.value);value['additional_cap_nano_usd']=budget.PANEL_CAP
        value['panel_window_budget_authority']=deepcopy(budget.AUTHORITY)
        with patch.object(budget,'ceiling',return_value=budget.PANEL_CAP),patch.object(runtime,'_study',side_effect=Reached):
            with self.assertRaises(Reached):runtime.preflight(self.bound(value))


if __name__=='__main__':unittest.main()
