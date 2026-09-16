import hashlib
from pathlib import Path
import pickle
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from reconstruct_selected_candidate import reconstruct,require_identical_arrays,load_trusted_bytes,predict_saved,versions
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
import test_historical_grid_learning as fixtures
from historical_grid_learning import evaluate


class ReconstructionTests(unittest.TestCase):
    def test_identical_recipe_and_reload_predict_exactly(self):
        inputs,plan=fixtures.GridLearningTests().fixture('hist_gradient_boosting')
        plan['normalizer']='none';plan['missing_input_action']='native_nan'
        inputs['x']['values'][7,1]=np.nan
        _,expected=evaluate(inputs,plan)
        estimator,_,actual=reconstruct(inputs,plan);require_identical_arrays(expected,actual)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'model.pkl';payload=pickle.dumps(estimator,protocol=5);path.write_bytes(payload)
            loaded=load_trusted_bytes(path,hashlib.sha256(payload).hexdigest(),versions())
            predicted,_=predict_saved(loaded,inputs,plan,expected['check'])
            require_identical_arrays({'p':expected['prediction_delta_probability']},{'p':predicted})

    def test_differing_prediction_is_not_accepted_by_same_score(self):
        with self.assertRaisesRegex(ValueError,'differs'):
            require_identical_arrays({'p':np.array([.1,-.1])},{'p':np.array([-.1,.1])})

    def test_hash_or_runtime_mismatch_fails_before_unpickle(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'model.pkl';path.write_bytes(b'not a trusted model')
            with patch('reconstruct_selected_candidate.pickle.loads',side_effect=AssertionError('unsafe load')):
                with self.assertRaisesRegex(ValueError,'bytes changed'):load_trusted_bytes(path,'0'*64,versions())
                with self.assertRaisesRegex(ValueError,'runtime'):load_trusted_bytes(path,'0'*64,{})

    def test_unsupported_recipe_cannot_be_silently_substituted(self):
        i,p=fixtures.GridLearningTests().fixture()
        with self.assertRaisesRegex(ValueError,'scoped'):reconstruct(i,p)


if __name__=='__main__':unittest.main()
