import copy
import unittest
import numpy as np

from historical_grid_learning import evaluate,validate_plan


class GridLearningTests(unittest.TestCase):
    def fixture(self,algorithm='ridge'):
        n=12;d=86400000
        time=np.r_[d+np.arange(6)*60000,2*d+np.arange(6)*60000].astype(np.int64)
        values=np.column_stack([np.linspace(.2,.8,n),np.linspace(-1,1,n)])
        x={'row_id':np.array([str(i) for i in range(n)]),'entity':np.r_[np.zeros(6),np.ones(6)].astype(np.int64),
           'decision_ms':time,'date':np.array(['1970-01-02']*6+['1970-01-03']*6),
           'values':values,'market':np.array(['a']*6+['b']*6)}
        y={'delta_probability':.1*values[:,1],'available':np.ones(n,dtype=bool),'label_available_ms':time+60000}
        inputs={'x':x,'y':y,'names':['polymarket_ticks_ms.midpoint_from_reported_bbo','x'],
                'cadence_ms':60000,'objective':{'proposal_sha256':'a'*64}}
        models={'ridge':{'alpha':1,'fit_intercept':True},
                'elastic_net':{'alpha':.001,'l1_ratio':.5,'fit_intercept':True,'max_iter':100,'tol':1e-5},
                'random_forest':{'n_estimators':2,'max_depth':2,'min_samples_leaf':1,'max_features':1.},
                'hist_gradient_boosting':{'learning_rate':.1,'max_iter':2,'max_leaf_nodes':3,'l2_regularization':1.,'min_samples_leaf':2}}
        plan={'features':[{'name':'x','source':'x','transform':'identity','lookback_ms':0,
                'minimum_observations':1,'minimum_window_coverage':1}],
              'model':{'algorithm':algorithm,'parameters':models[algorithm]},'normalizer':'fit_mean_std',
              'train_utc_dates':['1970-01-02'],'check_utc_dates':['1970-01-03'],
              'train_weighting':'equal_row','score_aggregation':'equal_row',
              'missing_input_action':'persistence','output_transform':'none','seed':23,'rationale':'fixture'}
        return inputs,plan

    def test_all_four_model_operators_really_fit(self):
        for algorithm in ['ridge','elastic_net','random_forest','hist_gradient_boosting']:
            with self.subTest(algorithm=algorithm):
                i,p=self.fixture(algorithm);r,a=evaluate(i,p)
                self.assertEqual(r['fit_rows'],6)
                self.assertEqual(r['score']['label_rows'],6)
                self.assertTrue(np.all(np.isfinite(a['prediction_delta_probability'][a['check']])))
                self.assertFalse(r['fresh_holdout'])

    def test_check_targets_cannot_change_fit_or_predictions(self):
        i,p=self.fixture();r,a=evaluate(i,p)
        i['y']['delta_probability'][6:]=.7
        q,b=evaluate(i,p)
        np.testing.assert_array_equal(a['prediction_delta_probability'],b['prediction_delta_probability'])
        self.assertEqual(r['learned_coefficients'],q['learned_coefficients'])
        self.assertEqual(r['normalizer_mean'],q['normalizer_mean'])

    def test_check_features_cannot_change_normalizer(self):
        i,p=self.fixture();r,_=evaluate(i,p)
        i['x']['values'][6:,1]=999
        q,_=evaluate(i,p)
        self.assertEqual(r['normalizer_mean'],q['normalizer_mean'])

    def test_missing_check_input_retains_row_with_declared_fallback(self):
        i,p=self.fixture();i['x']['values'][7,1]=np.nan
        r,a=evaluate(i,p)
        self.assertEqual(r['check_persistence_fallback_rows'],1)
        self.assertEqual(r['score']['label_rows'],6)
        self.assertEqual(a['prediction_delta_probability'][7],0)
        self.assertTrue(np.isnan(i['x']['values'][7,1]))

    def test_native_nan_really_fits_missing_rows_without_fill_or_drop(self):
        i,p=self.fixture('hist_gradient_boosting');p['missing_input_action']='native_nan';p['normalizer']='none'
        i['x']['values'][1,1]=np.nan;i['x']['values'][7,1]=np.nan
        original=i['x']['values'].copy();r,a=evaluate(i,p)
        self.assertEqual(r['fit_rows'],6);self.assertEqual(r['fit_rows_with_missing_inputs'],1)
        self.assertEqual(r['check_model_rows_with_missing_inputs'],1)
        self.assertEqual(r['check_persistence_fallback_rows'],0)
        self.assertEqual(r['check_model_prediction_rows'],6)
        self.assertEqual(r['score']['label_rows'],6)
        self.assertTrue(a['check_model_prediction'][7]);self.assertFalse(r['source_values_imputed'])
        np.testing.assert_array_equal(i['x']['values'],original)

    def test_native_nan_does_not_learn_from_later_labels(self):
        i,p=self.fixture('hist_gradient_boosting');p['missing_input_action']='native_nan';p['normalizer']='none'
        i['x']['values'][1,1]=np.nan;i['x']['values'][7,1]=np.nan
        _,a=evaluate(i,p);i['y']['delta_probability'][6:]=.99;_,b=evaluate(i,p)
        np.testing.assert_array_equal(a['prediction_delta_probability'],b['prediction_delta_probability'])

    def test_native_nan_requires_explicit_supported_method_and_no_normalizer(self):
        i,p=self.fixture();p['missing_input_action']='native_nan'
        with self.assertRaisesRegex(ValueError,'native_nan currently requires'):evaluate(i,p)
        i,p=self.fixture('hist_gradient_boosting');p['missing_input_action']='native_nan'
        with self.assertRaisesRegex(ValueError,'native_nan currently requires'):evaluate(i,p)

    def test_whole_market_cross_split_guard(self):
        i,p=self.fixture();i['x']['market'][6:]='a'
        with self.assertRaisesRegex(ValueError,'insufficient'):
            evaluate(i,p)

    def test_target_crossing_day_boundary_not_fitted(self):
        i,p=self.fixture();i['y']['label_available_ms'][0]=2*86400000
        r,a=evaluate(i,p)
        self.assertFalse(a['fit'][0]);self.assertEqual(r['fit_rows'],5)

    def test_cannot_change_seed_or_skip_dates_or_omit_parameters(self):
        for field,value in [('seed',24),('check_utc_dates',[]),('normalizer','default')]:
            i,p=self.fixture();p[field]=value
            with self.assertRaises(ValueError):validate_plan(p,i)
        i,p=self.fixture();del p['model']['parameters']['alpha']
        with self.assertRaises(ValueError):validate_plan(p,i)

    def test_weight_and_prediction_transform_choices_explicit(self):
        for weight in ['equal_row','equal_day','equal_market']:
            i,p=self.fixture();p['train_weighting']=weight;p['output_transform']='clip_to_probability_delta_bounds'
            r,a=evaluate(i,p);self.assertEqual(r['score']['label_rows'],6)


if __name__=='__main__':unittest.main()
