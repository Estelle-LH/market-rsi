"""Portable trusted role-selection tests, not real forecast/Native admission.

Full historical preflight, resident/scope/ledger and P2 metadata selection are
explicit fixture seams. The original wrapper, current byte reads, Native case
registration and exit receipts remain real. P2 tests and Root integration cover
the producer/metadata receiver; a later real pilot covers original execution.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import earnings_entry as entry
import earnings_population_live_guard as guard
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
from test_earnings_population_role_validation import RoleFixture


class FrozenPanelSelectionTests(unittest.TestCase):
    def setUp(self):
        self.f = RoleFixture(); self.addCleanup(self.f.close)
        for seam in self.f.patches():
            seam.start(); self.addCleanup(seam.stop)
        self.company = self.f.packet['company_id']
        self.scope = dict(training=[self.company], heldout=['CIK0001005101'])
        self.descriptor = self.f.save('descriptor.json', {'fixture': 'same-frozen-candidate'})
        self.window = self.f.save('panel-window.json', {'fixture': 'one-company-three-arms'})
        split = self.f.save('split.json', self.scope)
        comparator = self.f.save('comparator.json', {'fixture': 'plain-Round0'})
        link = self.f.save('training-link.json', dict(split=split, comparator=comparator))
        study = entry.strict_json(entry.checked(self.f.value['forecast_study']))
        study.update(training_state_link=link, frozen_panel_policy='fixture-panel-v1',
                     frozen_panel=self.descriptor, frozen_panel_window=self.window)
        self.f.value.update(training_policy='fixture-training',
            frozen_panel_policy='fixture-panel-v1', frozen_panel=self.descriptor,
            frozen_panel_window=self.window, model_budget_amendment=self.f.save('model-grant.json', {}),
            forecast_study=self.f.save('panel-study.json', study))
        self.f.binding = self.f.save('panel-runtime.json', self.f.value)
        self.f.manager = guard.RoleValidation(self.f.binding, self.f.value, self.f.full)
        self.f.manager.native = self.f.native  # Original fixture's explicit inert Native root.
        self.versions = []
        for index in range(3):
            source = self.f.raw('R-%s.py' % index, ('fixture R arm%s' % index).encode())
            self.versions.append(dict(id=digest({'R': source['sha256'], 'H': self.f.source['H']['sha256']}),
                                      R=source, H=deepcopy(self.f.source['H'])))
        for name, value in [('earnings_population_public_predictions.runtime_scope', self.scope)]:
            seam = patch(name, return_value=value); seam.start(); self.addCleanup(seam.stop)
        seam = patch('earnings_population_training25.admit', side_effect=self.admit)
        seam.start(); self.addCleanup(seam.stop)
        seam = patch('earnings_population_runtime.panel_selection', side_effect=self.select)
        self.selector = seam.start(); self.addCleanup(seam.stop)

    def admit(self, scope, company):
        if scope != self.scope or company not in scope['training'] or company in scope['heldout']:
            raise ValueError('Fixture training admission refused')
        return company

    def select(self, value, slot):
        self.assertEqual(value, self.f.value)
        index = self.f.value['slots']['forecast'].index(str(slot))
        return dict(company_id=self.company, arm=('control', 'parent', 'candidate')[index],
                    window={'company_id': self.company}, version=deepcopy(self.versions[index]),
                    bindings=[self.descriptor, self.window])

    def args(self, index=0):
        return deepcopy(self.versions[index]), self.company, self.f.value['slots']['forecast'][index]

    def receipt(self, index=0):
        name = Path(self.args(index)[-1]).name
        return entry.strict_json((self.f.root/'role-validation'/(name+'.json')).read_bytes())

    def register(self, version, company, slot):
        self.f.manager.register_case(self.f.case(slot, version))
        self.f.manager.check(slot)
        return {'fixture': 'registered-original-role-checks'}

    def test_three_exact_forecast_arms_need_no_ordinary_packets_or_loop_seals(self):
        for name in ('packet-01.json', 'frozen-pool-01.json'):
            (self.f.root/name).unlink()  # Owned temporary invented fixture only.
        for index in range(3):
            self.assertEqual(self.f.manager.wrap('forecast', self.register)(*self.args(index)),
                             {'fixture': 'registered-original-role-checks'})
            receipt = self.receipt(index)
            self.assertTrue(receipt['output_accepted'])
            self.assertEqual(receipt['selected_version_id'], self.versions[index]['id'])
            self.assertEqual(receipt['entry_full_audit'], 'PASS')
            self.assertEqual(receipt['exit_full_audit'], 'PASS')
            self.assertEqual(receipt['exit_current_guard'], 'PASS')
        self.assertEqual(len(self.f.full_calls), 6)

    def test_mutation_roles_refused_before_callback_or_metadata_selection(self):
        for role in ('controller', 'author', 'review'):
            with self.subTest(role=role), self.assertRaisesRegex(ValueError, 'forecasts only'):
                self.f.manager.wrap(role, lambda *args: self.fail('mutation role called'))(*self.f.args(role))
        self.selector.assert_not_called()

    def test_wrong_callback_version_or_company_refused_before_resident(self):
        for index in (0, 1):
            args = list(self.args())
            if index == 0: args[0] = deepcopy(self.versions[1])
            else: args[1] = 'CIK0000003545'
            with self.subTest(index=index), patch.object(guard.tasks, 'resident', side_effect=AssertionError('body read')):
                with self.assertRaisesRegex(ValueError, 'arguments differ'):
                    self.f.manager.wrap('forecast', lambda *a: self.fail('callback called'))(*args)

    def test_foreign_selected_company_refused_before_resident(self):
        bad = self.select(self.f.value, self.args()[-1]); bad['company_id'] = 'CIK0001005101'
        self.selector.side_effect = lambda *a: bad
        args = list(self.args()); args[1] = bad['company_id']
        with patch.object(guard.tasks, 'resident', side_effect=AssertionError('heldout body read')):
            with self.assertRaises(ValueError):
                self.f.manager.wrap('forecast', lambda *a: self.fail('callback called'))(*args)

    def test_malformed_independent_selection_never_enters_callback(self):
        valid = self.select(self.f.value, self.args()[-1])
        malformed = [None, {}, dict(valid, extra=True), dict(valid, bindings=[]), dict(valid, version={})]
        for value in malformed:
            self.selector.side_effect = lambda *a, value=value: deepcopy(value)
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.f.manager.wrap('forecast', lambda *a: self.fail('callback called'))(*self.args())

    def assert_binding_tamper_refused(self, target):
        def callback(version, company, actual_slot):
            self.f.manager.register_case(self.f.case(actual_slot, version))
            path = Path(target['path']); before = path.stat(); raw = path.read_bytes()
            path.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
            os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
            self.f.manager.check(actual_slot)
        with self.assertRaises(ValueError):
            self.f.manager.wrap('forecast', callback)(*self.args())
        self.assertFalse(self.receipt()['output_accepted'])

    def test_descriptor_rehashed_even_with_restored_size_mtime(self):
        self.assert_binding_tamper_refused(self.descriptor)

    def test_window_rehashed_even_with_restored_size_mtime(self):
        self.assert_binding_tamper_refused(self.window)

    def test_selected_arm_cannot_substitute_another_physical_slot(self):
        bad = self.select(self.f.value, self.args()[-1]); bad['arm'] = 'candidate'
        self.selector.side_effect = lambda *a: bad
        with self.assertRaisesRegex(ValueError, 'slot differs'):
            self.f.manager.wrap('forecast', lambda *a: self.fail('callback called'))(*self.args())

    def test_no_native_registration_cannot_accept_result(self):
        with self.assertRaises(ValueError):
            self.f.manager.wrap('forecast', lambda *a: 'not accepted')(*self.args())
        self.assertFalse(self.receipt()['output_accepted'])

    def test_self_consistent_kernel_substitution_cannot_register(self):
        def callback(version, company, slot):
            case = self.f.case(slot, version)
            value = entry.strict_json(entry.checked(case['context']))
            value['kernel'] = case['kernel'] = {'fixture': 'wrong-kernel'}
            path = Path(case['context']['path']); path.write_text(json.dumps(value, sort_keys=True))
            case['context'] = engine.pin(path)
            self.f.manager.register_case(case)
        with self.assertRaises(ValueError):
            self.f.manager.wrap('forecast', callback)(*self.args())
        self.assertFalse(self.receipt()['output_accepted'])


if __name__ == '__main__': unittest.main()
