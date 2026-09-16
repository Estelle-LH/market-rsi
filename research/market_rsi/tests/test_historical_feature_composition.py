import copy
import unittest
import numpy as np

import historical_grid_features as primitive
from historical_feature_composition import derive, validate_feature, feature_engine_sha256
from market_rsi import file_hash


def leaf(name='x', source='x', transform='identity', lookback=0, count=1):
    return {'name':name,'source':source,'transform':transform,'lookback_ms':lookback,
            'minimum_observations':count,'minimum_window_coverage':1}


class CompositionTests(unittest.TestCase):
    def setUp(self):
        self.entity=np.array([0,0,0,1,1,1])
        self.time=np.array([60000,120000,180000]*2,dtype=np.int64)
        self.values=np.array([[1,1,0],[2,1,0],[3,1,0],[1,0,1],[2,0,1],[3,0,1]],dtype=float)
        self.names=['x','a','b']

    def run_feature(self,spec,values=None):
        return derive(self.entity,self.time,self.values if values is None else values,
                      self.names,spec=spec,cadence_ms=60000)

    def composed(self):
        return {'name':'joint','operator':'product','operands':[leaf(),
            {'name':'difference','operator':'difference','operands':[leaf('a','a'),leaf('b','b')]}]}

    def test_explicit_composition_and_missingness(self):
        spec=self.composed()
        np.testing.assert_array_equal(self.run_feature(spec)['values'],[1,2,3,-1,-2,-3])
        values=self.values.copy();values[0,0]=np.nan;values[0,1:]=0
        self.assertTrue(np.isnan(self.run_feature(spec,values)['values'][0]))

    def test_legacy_outputs_and_engine_hash_are_unchanged(self):
        for transform,lag,count in [('identity',0,1),('log1p',0,1),('square',0,1),
                ('lag_delta',60000,2),('lag_log_return',60000,2),
                ('trailing_mean_delta',60000,2),('trailing_std',60000,2)]:
            spec=leaf(transform=transform,lookback=lag,count=count)
            before=primitive.derive(self.entity,self.time,self.values,self.names,spec=spec,cadence_ms=60000)
            after=self.run_feature(spec)
            self.assertEqual(set(before),set(after))
            for key in ('values','available','observations_used','feature_available_ms'):
                self.assertEqual(before[key].tobytes(),after[key].tobytes())
            self.assertEqual(feature_engine_sha256(spec),file_hash(primitive.__file__))

    def test_future_mutation_cannot_change_past_composition(self):
        spec=self.composed();spec['operands'][0]=leaf(transform='lag_delta',lookback=60000,count=2)
        values=self.values.copy();values[2,0]=9999
        np.testing.assert_array_equal(self.run_feature(spec)['values'][:2],self.run_feature(spec,values)['values'][:2])

    def test_bounds_unknown_operations_hidden_labels_and_overflow_rejected(self):
        invalid=[{'name':'x','operator':'divide','operands':[leaf(),leaf()]},
                 {'name':'x','operator':'difference','operands':[leaf(),leaf(),leaf()]},
                 {**self.composed(),'target':1}]
        deep=leaf()
        for _ in range(4):deep={'name':'x','operator':'sum','operands':[leaf(),deep]}
        invalid.append(deep)
        invalid.append({'name':'big','operator':'sum','operands':[self.composed()]*4})
        for spec in invalid:
            with self.assertRaises(ValueError):validate_feature(spec,self.names,60000)
        values=self.values.copy();values[:,0]=1e308
        with self.assertRaisesRegex(ValueError,'overflow'):
            self.run_feature({'name':'overflow','operator':'product','operands':[leaf(),leaf()]},values)

    def test_no_input_mutation(self):
        spec=self.composed();old=copy.deepcopy(spec);values=self.values.copy()
        self.run_feature(spec)
        self.assertEqual(spec,old);np.testing.assert_array_equal(values,self.values)


if __name__=='__main__':unittest.main()
