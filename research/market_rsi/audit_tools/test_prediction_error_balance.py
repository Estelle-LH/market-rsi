import unittest
import numpy as np

from audit_prediction_error_balance import balance


class ErrorBalanceTests(unittest.TestCase):
    def test_exact_identity_and_original_weighted_subgroups(self):
        y=np.array([0.,0.,.2,-.3]);p=np.array([.1,-.1,.4,-.4])
        dates=np.array(['a','a','a','b']);markets=np.array(['x','y','y','z'])
        for aggregation in ('equal_row','equal_day','equal_group'):
            r=balance(y,p,dates,markets,aggregation)
            self.assertAlmostEqual(r['mse_delta_vs_persistence'],r['prediction_energy']-r['twice_target_alignment'])
            self.assertAlmostEqual(sum(v['original_weight_share'] for v in r['additive_subgroups'].values()),1)
            self.assertAlmostEqual(sum(v['contribution_to_mse_delta'] for v in r['additive_subgroups'].values()),r['mse_delta_vs_persistence'])
            self.assertFalse(r['scaled_prediction_or_optimal_scale_computed'])

    def test_persistence_and_perfect_predictor(self):
        y=np.array([0.,.1,-.2]);dates=np.array(['a']*3);groups=np.array(['x']*3)
        zero=balance(y,np.zeros(3),dates,groups,'equal_day')
        perfect=balance(y,y,dates,groups,'equal_day')
        self.assertEqual(zero['mse_delta_vs_persistence'],0)
        self.assertAlmostEqual(perfect['model_mse_probability'],0)
        self.assertAlmostEqual(perfect['mse_delta_vs_persistence'],-perfect['persistence_mse_probability'])

    def test_missing_predictions_are_errors_not_silent_filtering(self):
        with self.assertRaises(ValueError):
            balance(np.array([0.,.1]),np.array([0.,np.nan]),np.array(['a','a']),np.array(['x','x']),'equal_day')

    def test_population_is_not_mutated_or_quiet_filtered(self):
        y=np.array([0.,0.,.2]);p=np.array([.1,.1,.1]);before=p.copy()
        r=balance(y,p,np.array(['a']*3),np.array(['x']*3),'equal_row')
        self.assertEqual(r['rows'],3);self.assertEqual(r['additive_subgroups']['quiet_label']['rows'],2)
        np.testing.assert_array_equal(p,before)


if __name__=='__main__':unittest.main()
