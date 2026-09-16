import unittest
import numpy as np

from audit_conditional_diagnostic import midcdf,reference_statistics,compare
from historical_conditional_diagnostics import summarize


class ConditionalAuditTests(unittest.TestCase):
    def test_prior_midcdf_ties_outside_and_between_support(self):
        expected=np.array([0,.25,.5,.625,.75,.875,1.])
        actual=midcdf(np.array([1.,1.,3.,5.]),np.array([0.,1.,2.,3.,4.,5.,6.]))
        np.testing.assert_array_equal(actual,expected)

    def test_independent_unscaled_ols_matches_original_normalized_diagnostic(self):
        rng=np.random.default_rng(23);n=600;c=rng.normal(size=n)
        x=np.column_stack([c+rng.normal(size=n),c,.001*rng.normal(size=n)])
        y=.1*x[:,0]+.3*c+rng.normal(scale=.01,size=n)
        fit=np.arange(n)<300;check=~fit;dates=np.array(['a']*300+['b']*150+['c']*150)
        groups=np.array(['fit']*300+['left']*150+['right']*150)
        ref=reference_statistics(x,y,fit,check,dates,groups)
        saved=summarize(x,y,eligible_fit=fit,check=check,label_available=np.ones(n,dtype=bool),
            dates=dates,groups=groups,names=['candidate','control','small_scale_control'])
        compare(ref['fit'],saved['fit']);compare(ref['check'],saved['check'])
        for d,v in ref['check_by_date'].items():compare(v,saved['check_by_date'][d])
        changed=reference_statistics(x,np.where(check,y+1,y),fit,check,dates,groups)
        self.assertEqual(ref['verification_coefficients'],changed['verification_coefficients'])

    def test_mismatched_number_or_undefined_correlation_fails(self):
        with self.assertRaises(ValueError):compare({'ic':None},{'ic':0})
        with self.assertRaises(ValueError):compare({'ic':.1},{'ic':.2})


if __name__=='__main__':unittest.main()
