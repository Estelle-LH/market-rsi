import unittest
import numpy as np

from historical_grid_objectives import GridPanel, profile, targets, validate_spec


class GridObjectiveTests(unittest.TestCase):
    def panel(self):
        return GridPanel(entity=np.array([0,0,0,0]),time_ms=np.array([60000,120000,180000,240000]),
            midpoint=np.array([.4,.5,.6,.5]),quote_age_ms=np.zeros(4),
            date=np.array(['2026-04-04']*4),phase=np.array(['within_nominal_window']*4),cadence_ms=60000,max_age_ms=300000)

    def spec(self,**changes):
        return {**dict(family='point_delta',window_start_ms=60000,window_end_ms=60000,
            half_life_ms=None,minimum_observations=1,minimum_window_coverage=1.,label_max_age_ms=300000),**changes}

    def test_point_delta_units_and_missing_last_row(self):
        r=targets(self.panel(),self.spec());np.testing.assert_allclose(r['delta_probability_bps'][:3],[1000,1000,-1000])
        self.assertFalse(r['available'][-1]);self.assertEqual(r['full_population_rows'],4)
        self.assertEqual(list(r['label_available_ms']),[120000,180000,240000,300000])

    def test_future_mean_is_not_a_current_feature(self):
        r=targets(self.panel(),self.spec(family='forward_mean_delta',window_end_ms=120000,minimum_observations=2))
        self.assertAlmostEqual(r['delta_probability'][0],.15)
        self.assertEqual(r['label_available_ms'][0],180000)
        self.assertEqual(int(r['available'].sum()),2)

    def test_forward_ewma_requires_explicit_half_life(self):
        spec=self.spec(family='forward_ewma_delta',window_end_ms=120000,half_life_ms=60000,minimum_observations=2)
        r=targets(self.panel(),spec)
        self.assertAlmostEqual(r['delta_probability'][0],(.5*.5+.6)/1.5-.4)
        with self.assertRaisesRegex(ValueError,'half life'):validate_spec({**spec,'half_life_ms':None},60000,300000)

    def test_no_dense_observations_fabricated_between_grid_ticks(self):
        with self.assertRaisesRegex(ValueError,'actual recorded grid'):
            targets(self.panel(),self.spec(window_start_ms=45000,window_end_ms=75000,family='forward_mean_delta'))

    def test_gap_never_replaced_by_nearest_future_row(self):
        p=self.panel();p.time_ms=np.array([60000,180000,240000,300000])
        r=targets(p,self.spec());self.assertFalse(r['available'][0])

    def test_asset_identity_cannot_cross_for_a_label(self):
        p=self.panel();p.entity=np.array([0,1,0,0])
        r=targets(p,self.spec());self.assertFalse(r['available'][0]);self.assertFalse(r['available'][1])

    def test_freshness_restriction_is_explicit(self):
        p=self.panel();p.quote_age_ms[1]=2000
        r=targets(p,self.spec(label_max_age_ms=1000));self.assertFalse(r['available'][0])

    def test_constant_target_does_not_drop_quiet_rows(self):
        p=self.panel();p.midpoint[:]=.5;r=profile(p,self.spec())
        self.assertEqual(r['all_rows']['population_rows'],4)
        self.assertEqual(r['all_rows']['covered_rows'],3)
        self.assertEqual(r['all_rows']['persistence_mse_probability'],0)
        self.assertEqual(r['all_rows']['unchanged_fraction_among_covered'],1)

    def test_missing_current_quote_stays_in_denominator(self):
        p=self.panel();p.midpoint[0]=np.nan;r=profile(p,self.spec())
        self.assertEqual(r['all_rows']['population_rows'],4)
        self.assertEqual(r['all_rows']['covered_rows'],2)
        self.assertEqual(r['missing_label_reasons']['current_quote_unavailable'],1)

    def test_future_changes_cannot_alter_other_rows_current_inputs(self):
        p=self.panel();before=p.midpoint.copy();targets(p,self.spec())
        np.testing.assert_array_equal(p.midpoint,before)

    def test_finite_quote_cannot_hide_a_missing_source_age(self):
        p=self.panel();p.quote_age_ms[0]=np.nan
        with self.assertRaisesRegex(ValueError,'source-invalid'):targets(p,self.spec())

    def test_infinity_is_not_missing(self):
        p=self.panel();p.midpoint[0]=np.inf
        with self.assertRaisesRegex(ValueError,'infinite'):targets(p,self.spec())

    def test_fractional_time_cannot_create_a_grid(self):
        p=self.panel();p.time_ms=p.time_ms.astype(float)
        with self.assertRaisesRegex(ValueError,'integer millisecond'):targets(p,self.spec())

    def test_source_cadence_must_be_valid_before_spec_validation(self):
        with self.assertRaisesRegex(ValueError,'positive grid cadence'):validate_spec(self.spec(),0,300000)

    def test_non_binary_constant_level_has_exact_zero_mean_label(self):
        p=self.panel();p.midpoint[:]=.49
        spec=self.spec(family='forward_mean_delta',window_end_ms=180000,minimum_observations=3)
        result=targets(p,spec)
        self.assertEqual(result['delta_probability'][0],0)
        self.assertTrue(result['all_observed_future_quotes_equal_current'][0])

    def test_non_binary_constant_level_has_exact_zero_ewma_label(self):
        p=self.panel();p.midpoint[:]=.49
        spec=self.spec(family='forward_ewma_delta',window_end_ms=180000,half_life_ms=60000,minimum_observations=3)
        self.assertEqual(targets(p,spec)['delta_probability'][0],0)

    def test_stability_fix_does_not_hide_a_real_tiny_change(self):
        p=self.panel();p.midpoint[:]=.49;p.midpoint[1]=np.nextafter(.49,1.)
        result=targets(p,self.spec(family='forward_mean_delta',window_end_ms=180000,minimum_observations=3))
        self.assertGreater(result['delta_probability'][0],0)
        self.assertFalse(result['all_observed_future_quotes_equal_current'][0])

    def test_real_failure_level_and_window_reproduce_then_fix_roundoff(self):
        level=.505;n=32;p=self.panel()
        p.entity=np.zeros(n,dtype=np.int64);p.time_ms=np.arange(1,n+1,dtype=np.int64)*60000
        p.midpoint=np.full(n,level);p.quote_age_ms=np.zeros(n)
        p.date=np.array(['2026-04-04']*n);p.phase=np.array(['before_nominal_window']*n)
        # Exact old operation demonstrably invented a nonzero answer on this input.
        self.assertNotEqual(float(np.sum(np.full(30,level))/30-level),0)
        spec=self.spec(family='forward_mean_delta',window_end_ms=1800000,minimum_observations=15,minimum_window_coverage=.5)
        result=targets(p,spec)
        self.assertTrue(np.all(result['delta_probability'][result['available']]==0))


if __name__=='__main__':unittest.main()
