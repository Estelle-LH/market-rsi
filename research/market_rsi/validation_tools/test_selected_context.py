import copy
import unittest
from market_rsi import digest
from freeze_selected_context import verify_selected_bindings


class SelectedContextTests(unittest.TestCase):
    def setUp(self):
        self.plan = {'fixture': 'no data or predictor execution'}
        self.decision = {'action': 'select', 'trial_id': 'selected-fixture'}
        self.trial = {'trial_id': 'selected-fixture', 'plan': copy.deepcopy(self.plan)}
        self.rebuilt = {'selected_trial_id': 'selected-fixture', 'passed': True,
                        'all_original_prediction_arrays_identical': True, 'reload_predictions_identical': True,
                        'selected_plan_sha256': digest(self.plan),
                        'selected_plan_file_sha256': 'a' * 64, 'model_sha256': 'b' * 64}

    def check(self):
        return verify_selected_bindings(self.decision, self.trial, self.rebuilt, self.plan,
                                        'b' * 64, 'a' * 64)

    def test_exact_selected_metadata_passes(self):
        self.check()

    def test_defer_not_reinterpreted_as_select(self):
        self.decision['action'] = 'defer'
        with self.assertRaisesRegex(ValueError, 'SELECT'):
            self.check()

    def test_another_selected_candidate_rejected(self):
        self.rebuilt['selected_trial_id'] = 'another-trial'
        with self.assertRaisesRegex(ValueError, 'SELECT'):
            self.check()

    def test_changed_model_bytes_rejected(self):
        self.rebuilt['model_sha256'] = 'c' * 64
        with self.assertRaisesRegex(ValueError, 'model bytes changed'):
            self.check()

    def test_changed_saved_plan_rejected(self):
        self.plan['learning_rate'] = .1
        with self.assertRaisesRegex(ValueError, 'plan differs'):
            self.check()

    def test_unverified_reload_rejected(self):
        self.rebuilt['reload_predictions_identical'] = False
        with self.assertRaisesRegex(ValueError, 'equivalence'):
            self.check()


if __name__ == '__main__':
    unittest.main()
