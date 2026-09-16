import unittest
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from test_historical_grid_learning_controller import GridLearningBrokerTests
from audit_grid_learning_result import independently_score, trial_audit
from market_rsi import canonical, digest, load_json


class IndependentAuditTests(unittest.TestCase):
    def setUp(self):
        self.fixture=GridLearningBrokerTests();self.fixture.setUp()
        self.fixture.inspect();self.fixture.profile();self.fixture.trial()
        self.root=self.fixture.root/'trials/t1'

    def tearDown(self):self.fixture.tearDown()

    def test_actual_synthetic_fit_audits_without_refit(self):
        result=trial_audit(self.root,self.fixture.inputs)
        self.assertTrue(result['passed']);self.assertEqual(result['refits'],0)
        self.assertEqual(result['counts']['fit_rows'],6)

    def test_changed_score_rejected_even_with_resigned_result(self):
        result=load_json(self.root/'result.json');result['report']['score']['model_mse_probability']+=.01
        result['result_sha256']=digest({k:v for k,v in result.items() if k!='result_sha256'})
        (self.root/'result.json').write_text(canonical(result))
        with self.assertRaisesRegex(ValueError,'independent score mismatch'):
            trial_audit(self.root,self.fixture.inputs)

    def test_group_mean_arithmetic_is_not_row_weighted(self):
        y=np.array([0.,0.,3.]);p=np.ones(3);d=np.array(['a','a','b'])
        day=independently_score(y,p,d,d,'equal_day')
        row=independently_score(y,p,d,d,'equal_row')
        self.assertAlmostEqual(day['model_mse_probability'],2.5)
        self.assertAlmostEqual(row['model_mse_probability'],2.)
        self.assertAlmostEqual(day['persistence_mse_probability'],4.5)

    def test_missing_prediction_is_never_dropped(self):
        with self.assertRaisesRegex(ValueError,'finite predictions'):
            independently_score(np.array([0.,1.]),np.array([0.,np.nan]),
                                np.array(['a','b']),np.array(['a','b']),'equal_day')


if __name__=='__main__':unittest.main()
