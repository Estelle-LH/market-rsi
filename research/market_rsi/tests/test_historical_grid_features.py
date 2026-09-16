import unittest
import numpy as np

from historical_grid_features import derive
from historical_delta_evaluation import raw_feature_diagnostic, score_delta


class CausalFeatureTests(unittest.TestCase):
    def setUp(self):
        self.entity = np.array([0,0,0,0,1,1])
        self.time = np.array([60000,120000,180000,240000,60000,180000], dtype=np.int64)
        self.values = np.array([[1.],[2.],[4.],[8.],[.5],[.7]])

    def feature(self, transform, lag, count, coverage=1, values=None):
        spec = {'name':'test', 'source':'x', 'transform':transform, 'lookback_ms':lag,
                'minimum_observations':count, 'minimum_window_coverage':coverage}
        return derive(self.entity,self.time,self.values if values is None else values,['x'],spec=spec,cadence_ms=60000)

    def test_exact_lag_and_no_market_or_gap_substitution(self):
        result = self.feature('lag_delta',60000,2)['values']
        np.testing.assert_allclose(result,[np.nan,1,2,4,np.nan,np.nan],equal_nan=True)

    def test_future_mutation_does_not_change_past_features(self):
        a = self.feature('trailing_mean_delta',120000,2,.5)['values']
        values = self.values.copy(); values[3] = 9999
        b = self.feature('trailing_mean_delta',120000,2,.5,values)['values']
        np.testing.assert_array_equal(a[:3],b[:3])

    def test_centre_before_mean_and_std_keeps_constant_exact(self):
        values = np.full_like(self.values,.505)
        for transform in ['trailing_mean_delta','trailing_std']:
            result = self.feature(transform,120000,2,.5,values)['values']
            self.assertTrue(np.all(result[np.isfinite(result)]==0))

    def test_negative_or_subgrid_lookback_rejected(self):
        for lag in [-60000,1]:
            with self.assertRaises(ValueError): self.feature('lag_delta',lag,2)

    def test_missing_current_not_filled_by_past(self):
        values = self.values.copy(); values[2] = np.nan
        result = self.feature('trailing_mean_delta',120000,2,.5,values)
        self.assertTrue(np.isnan(result['values'][2]))

    def test_log_domain_is_missing_not_zero(self):
        values=self.values.copy(); values[1]=-1
        self.assertTrue(np.isnan(self.feature('log1p',0,1,values=values)['values'][1]))

    def test_trailing_population_std_definition(self):
        result=self.feature('trailing_std',120000,3)['values']
        self.assertAlmostEqual(result[2],np.std([1,2,4]))

    def test_no_label_field_accepted_in_feature_spec(self):
        spec={'name':'x','source':'x','transform':'identity','lookback_ms':0,
              'minimum_observations':1,'minimum_window_coverage':1,'target':.2}
        with self.assertRaisesRegex(ValueError,'hidden fields'):
            derive(self.entity,self.time,self.values,['x'],spec=spec,cadence_ms=60000)


class DeltaScorerTests(unittest.TestCase):
    def setUp(self):
        self.y=np.array([-.2,.1,0.,np.nan]); self.ok=np.array([True,True,True,False])
        self.d=np.array(['d1','d1','d2','d2']); self.g=np.array(['g1','g2','g3','g4'])

    def score(self,p,aggregation='equal_row'):
        return score_delta(self.y,np.array(p),label_available=self.ok,dates=self.d,groups=self.g,aggregation=aggregation)

    def test_negative_prediction_is_not_clipped_like_old_price_interface(self):
        score=self.score([-.2,.1,0.,np.nan])
        self.assertEqual(score['model_mse_probability'],0)
        self.assertEqual(score['mse_skill_vs_persistence'],1)
        self.assertFalse(score['output_clipping_applied_by_scorer'])

    def test_persistence_zero_skill_and_bps_units(self):
        score=self.score([0,0,0,np.nan])
        self.assertEqual(score['mse_skill_vs_persistence'],0)
        self.assertAlmostEqual(score['model_rmse_probability_bps'],np.sqrt(.05/3)*10000)

    def test_cannot_remove_bad_or_quiet_prediction_rows(self):
        with self.assertRaisesRegex(ValueError,'selective omission'):
            self.score([np.nan,.1,0,np.nan])
        self.assertEqual(self.score([0,0,0,np.nan])['label_rows'],3)

    def test_aggregation_must_be_explicit_and_changes_both_model_and_baseline(self):
        with self.assertRaises(ValueError): self.score([0,0,0,np.nan],'default')
        score=self.score([0,0,0,np.nan],'equal_day')
        self.assertAlmostEqual(score['persistence_mse_probability'],.05/4)
        self.assertEqual(score['mse_skill_vs_persistence'],0)

    def test_flat_baseline_ratio_undefined(self):
        self.y[:3]=0
        self.assertIsNone(self.score([0,0,0,np.nan])['mse_skill_vs_persistence'])

    def test_raw_association_reports_full_population_and_matched_subset(self):
        result=raw_feature_diagnostic(np.array([-.2,np.nan,0,1]),self.y,self.ok,self.d)
        self.assertEqual(result['all_rows']['population_rows'],4)
        self.assertEqual(result['all_rows']['paired_rows'],2)
        self.assertFalse(result['model_fitted'])


if __name__=='__main__': unittest.main()
