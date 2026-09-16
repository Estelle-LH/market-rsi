import unittest
import numpy as np
from audit_direction_pairing import inspect_pairs


class PairingTests(unittest.TestCase):
    def fixture(self, target):
        n = len(target)
        return ({'market': np.array(['a', 'a', 'b', 'b'][:n]),
                 'decision_ms': np.array([1, 1, 2, 2][:n]),
                 'row_id': np.arange(n), 'entity': np.arange(n),
                 'date': np.array(['2026-04-04'] * n),
                 'values': np.array([2., 2., 4., 4.][:n])[:, None]},
                {'available': np.isfinite(target), 'delta_probability': np.array(target)})

    def test_opposite_labels_cancel_shared_feature_without_dropping_quiet_pairs(self):
        x, y = self.fixture([.2, -.2, 0., 0.])
        r = inspect_pairs(x, y, ['shared'])
        self.assertEqual(r['exact_opposite_label_pairs'], 2)
        self.assertEqual(r['both_zero_label_pairs_retained'], 1)
        self.assertEqual(r['population_rows'], 4)
        self.assertEqual(r['field_pairing']['shared']['absolute_sum_of_pair_feature_target_products'], 0)

    def test_asymmetry_is_reported_not_forced_to_cancel(self):
        x, y = self.fixture([.2, -.1])
        r = inspect_pairs(x, y, ['shared'])
        self.assertEqual(r['exact_opposite_label_pairs'], 0)
        self.assertAlmostEqual(r['max_abs_pair_label_sum'], .1)

    def test_missing_label_is_preserved_and_excluded_only_from_pair_arithmetic(self):
        x, y = self.fixture([.2, np.nan, 0., 0.])
        r = inspect_pairs(x, y, ['shared'])
        self.assertEqual(r['one_label_only_pairs'], 1)
        self.assertEqual(r['population_rows'], 4)
        self.assertEqual(r['both_labels_pairs'], 1)


if __name__ == '__main__':
    unittest.main()
