import json
import math
import unittest
import warnings
import numpy as np
from scipy.stats import spearmanr
from sklearn.linear_model import LinearRegression
from preliminary_comparison import fit,moments,score,ranks,evaluate,aggregate
from typed_raw_profile import Profile
from test_typed_raw_profile import contract,message,T


class ComparisonTests(unittest.TestCase):
    def test_fit_matches_sklearn(self):
        rng=np.random.default_rng(23)
        for _ in range(20):
            x=rng.normal(size=100).tolist();y=rng.normal(size=100).tolist()
            b=fit(moments(x,y))['beta']
            reference=LinearRegression(fit_intercept=False).fit(np.array(x)[:,None],y).coef_[0]
            self.assertAlmostEqual(b,reference,places=13)

    def test_no_sign_constraint(self):
        self.assertEqual(fit(moments([1,2],[-2,-4]))['beta'],-2)

    def test_unidentifiable_rejected(self):
        with self.assertRaises(ValueError):fit(moments([0,0],[1,1]))

    def test_nonfinite_and_empty_rejected(self):
        for x,y in [([],[]),([1],[math.nan]),([1,2],[1])]:
            with self.assertRaises(ValueError):moments(x,y)

    def test_predictions_not_refitted(self):
        b=fit(moments([1,2],[2,4]))['beta']
        a=score([1,2],[-2,-4],b)
        self.assertGreater(a['candidate_mse'],a['baseline_mse'])
        self.assertEqual(b,2)

    def test_direct_and_analytic_mse(self):
        x=[-.4,0,.3];y=[.2,0,.1];b=-.2
        self.assertAlmostEqual(score(x,y,b)['candidate_mse'],np.mean((np.array(y)-b*np.array(x))**2))

    def test_rank_with_ties(self):
        x=[0,0,2,1,1,-1];y=[2,0,0,1,1,2]
        for b in (-.2,0,.5):
            with warnings.catch_warnings():
                warnings.simplefilter('ignore');reference=spearmanr(np.array(x)*b,y).statistic
            r=score(x,y,b)['candidate_rank_ic']
            if math.isnan(reference):self.assertIsNone(r)
            else:self.assertAlmostEqual(r,reference)
        self.assertEqual(list(ranks([3,1,1])),[3,1.5,1.5])

    def test_constant_baseline_is_undefined(self):
        r=score([0,1,2],[1,2,3],.3)
        self.assertIsNone(r['baseline_pearson_ic']);self.assertIsNone(r['baseline_rank_ic'])

    def test_nonzero_constant_candidate_is_undefined(self):
        r=score([.1]*17,list(range(17)),.3)
        self.assertIsNone(r['candidate_pearson_ic']);self.assertIsNone(r['candidate_calibration_slope'])

    def test_zero_labels_kept(self):
        r=score([1,1,1],[0,0,1],.2)
        self.assertEqual(r['n'],3);self.assertEqual(r['zero_labels'],2)

    def test_frozen_sample_parity_and_no_raw_export(self):
        p=Profile(contract(),T)
        for i,t in enumerate(range(0,240001,10000),1):
            v=.2+(.01 if i%3 else -.01)
            p.consume(json.dumps(message(T+t,bid=str(v),ask=str(v+.02))).encode(),i)
        a=evaluate(p,-.2);b=evaluate(p,.1)
        self.assertEqual(a['paired_rows_sha256'],b['paired_rows_sha256'])
        self.assertEqual(a['baseline_predictions_sha256'],b['baseline_predictions_sha256'])
        self.assertNotEqual(a['candidate_predictions_sha256'],b['candidate_predictions_sha256'])
        self.assertEqual(a['metrics']['n'],p.summary()['counts']['numerically_available'])
        self.assertNotIn('fixture-token',json.dumps(a));self.assertEqual(a['fits_on_check'],0)

    def test_missing_date_not_silently_omitted(self):
        self.assertFalse(aggregate([],['a','b'])['complete'])

    def test_equal_date_not_equal_row_aggregate(self):
        rs=[dict(complete=True,spec=dict(date=d),evaluation=dict(metrics=dict(n=n,baseline_mse=b,candidate_mse=c,improvement=b-c)))
            for d,n,b,c in [('a',1,1,.5),('b',1000,3,4)]]
        r=aggregate(rs,['a','b']);self.assertEqual(r['baseline_mse'],2);self.assertEqual(r['candidate_mse'],2.25)
        rs[0]['complete']=False;self.assertFalse(aggregate(rs,['a','b'])['complete'])


if __name__=='__main__':unittest.main()
