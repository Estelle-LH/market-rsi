import unittest

import numpy as np

from historical_conditional_diagnostics import summarize, diagnose_conditional, validate_selection
from market_rsi import digest
import test_historical_grid_learning as fixtures


class ConditionalDiagnosticTests(unittest.TestCase):
    def fixture(self):
        rng = np.random.default_rng(23); n = 600
        control = rng.normal(size=n); independent = rng.normal(size=n)
        matrix = np.column_stack([control + independent, control])
        target = 2 * control + independent + rng.normal(scale=.05, size=n)
        args = dict(eligible_fit=np.arange(n) < 300, check=np.arange(n) >= 300,
            label_available=np.ones(n, dtype=bool), dates=np.array(['a']*300+['b']*150+['c']*150),
            groups=np.array(['fit']*300+['check-one']*150+['check-two']*150), names=['candidate','control'])
        return matrix, target, args

    def test_distinct_signal_survives_controls(self):
        x,y,a=self.fixture(); r=summarize(x,y,**a)
        self.assertGreater(r['check']['prior_linear_residual_ic'],.99)
        self.assertGreater(r['fit']['candidate_residual_variance_fraction'],.3)
        self.assertEqual(r['nuisance_regressions_fitted'],4)
        self.assertEqual(r['prediction_model_trials_started'],0)
        self.assertFalse(r['fresh_holdout'])

    def test_duplicate_signal_has_undefined_residual_ic(self):
        x,y,a=self.fixture(); x[:,0]=x[:,1]
        r=summarize(x,y,**a)
        self.assertIsNone(r['check']['prior_linear_residual_ic'])
        self.assertIsNone(r['check']['prior_rank_residual_ic'])
        self.assertLess(r['fit']['candidate_residual_variance_fraction'],1e-24)
        self.assertTrue(r['projection_fits']['raw']['candidate_plus_controls_singular'])
        self.assertIsNone(r['projection_fits']['raw']['candidate_plus_controls_condition_number'])

    def test_later_features_and_targets_do_not_change_nuisance_fit(self):
        x,y,a=self.fixture(); r=summarize(x,y,**a)
        x[300:]*=100; y[300:]*=-99
        s=summarize(x,y,**a)
        self.assertEqual(r['projection_fits'],s['projection_fits'])
        self.assertEqual(r['fit'],s['fit'])

    def test_missing_and_quiet_rows_are_not_removed_from_evaluation(self):
        x,y,a=self.fixture(); x[350,0]=np.nan; x[400,1]=np.nan; y[500:]=0
        a['label_available'][301]=False
        before=x.copy(); r=summarize(x,y,**a)
        self.assertEqual(r['support']['check_population_rows'],300)
        self.assertEqual(r['support']['check_labelled_rows'],299)
        self.assertEqual(r['support']['check_diagnostic_rows'],297)
        self.assertEqual(r['support']['check_labelled_missing_inputs'],2)
        self.assertEqual(r['evaluation_rows_removed'],0)
        np.testing.assert_array_equal(x,before)

    def test_constant_and_empty_check_groups_are_defined_honestly(self):
        x,y,a=self.fixture(); y[:]=0; a['label_available'][450:]=False
        r=summarize(x,y,**a)
        self.assertIsNone(r['check']['raw_pearson_ic'])
        self.assertIsNone(r['check']['prior_rank_residual_ic'])
        self.assertEqual(r['check_by_date']['c']['rows'],0)
        self.assertEqual(r['check_date_breadth']['raw_pearson_ic']['defined'],0)

    def test_zero_controls_and_bad_shapes(self):
        x,y,a=self.fixture(); a['names']=['candidate']
        r=summarize(x[:,:1],y,**a)
        self.assertAlmostEqual(r['check']['raw_pearson_ic'],r['check']['prior_linear_residual_ic'])
        a['check'][1]=True
        with self.assertRaisesRegex(ValueError,'overlap'):summarize(x[:,:1],y,**a)

    def test_causal_cutoff_is_strict_and_whole_market_isolation_applies(self):
        i,p=fixtures.GridLearningTests().fixture(); i['y']['label_available_ms'][0]=2*86400000
        trial={'trial_id':'test','plan':p,'result_sha256':'a'*64}
        r=diagnose_conditional(i,trial,'x',[])
        self.assertEqual(r['support']['nuisance_fit_rows'],5)
        self.assertLess(r['latest_nuisance_fit_label_available_ms'],r['strict_label_cutoff_ms'])
        i['x']['market'][6:]='a'
        with self.assertRaisesRegex(ValueError,'insufficient'):diagnose_conditional(i,trial,'x',[])

    def test_selection_requires_existing_distinct_features(self):
        i,p=fixtures.GridLearningTests().fixture(); trial={'plan':p}
        before=digest(p)
        for candidate, controls in [('unknown',[]),('x',['x']),('x',['unknown']),('x','x')]:
            with self.assertRaises(ValueError):validate_selection(trial,candidate,controls)
        self.assertEqual(validate_selection(trial,'x',[]),p['features'])
        self.assertEqual(digest(p),before)

    def test_linear_residuals_match_direct_unscaled_reference(self):
        x,y,a=self.fixture(); r=summarize(x,y,**a)
        z=np.column_stack([np.ones(len(y)),x[:,1]])
        outcomes=np.column_stack([x[:,0],y])
        coef=np.linalg.lstsq(z[:300],outcomes[:300],rcond=None)[0]
        residual=outcomes[300:]-z[300:]@coef
        expected=np.corrcoef(residual.T)[0,1]
        self.assertAlmostEqual(r['check']['prior_linear_residual_ic'],expected,places=12)


if __name__=='__main__':unittest.main()
