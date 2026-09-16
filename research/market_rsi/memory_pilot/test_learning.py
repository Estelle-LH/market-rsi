import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from market_rsi import fresh_json,file_hash,load_json
from memory_pilot.learning import BASE,validate,matrix,fit,evaluate
from memory_pilot.broker import Broker,run_worker


def fixture_cache(root,date,n=120):
    d=Path(root)/date;d.mkdir();rng=np.random.default_rng(23)
    x=rng.normal(0,.01,n);y=-.2*x+rng.normal(0,.001,n);y[::7]=0
    raw=np.column_stack([x,np.full(n,.5),np.full(n,.1),np.full(n,5),y,np.arange(n)%4]).astype('<f8')
    raw.tofile(d/'rows.f64')
    h=dict(shape=[n,6],bytes=raw.nbytes,sha256=file_hash(d/'rows.f64'),old_kernel_mask_unchanged=True,
        valid_zero_labels_retained=True,features_causal=True,paired_rows_sha256='a'*64)
    fresh_json(d/'header.json',h)
    return dict(date=date,path=str(d),header_sha256=file_hash(d/'header.json'),cache_sha256=h['sha256'])


class LearningTests(unittest.TestCase):
    def test_exact_one_changed_stage(self):
        for p in (BASE,dict(features=['abs_lag'],model={'algorithm':'ridge','parameters':{'alpha':1.,'fit_intercept':False}},normalizer='none')):
            with self.assertRaises(ValueError):validate(p,BASE)
        validate(dict(BASE,features=['lag_delta','lag_times_spread']),BASE)

    def test_future_label_not_feature(self):
        a=np.array([[.1,.4,.2,5.,.3,0],[.2,.5,.1,3.,.1,1.]])
        b=a.copy();b[:,4]=100
        from memory_pilot.learning import FEATURES
        np.testing.assert_array_equal(matrix(a,FEATURES),matrix(b,FEATURES))

    def test_train_only_scale_and_fit(self):
        with tempfile.TemporaryDirectory() as tmp:
            train=fixture_cache(tmp,'2026-01-01');check=fixture_cache(tmp,'2026-01-02')
            model,details=fit(dict(BASE,normalizer='fit_mean_std'),[train])
            before=model['model'].coef_.copy();scale=model['scaler'].mean_.copy()
            result=evaluate(model,check,Path(tmp)/'p.npy')
            self.assertEqual(result['n'],120);self.assertEqual(result['zero_labels'],18)
            np.testing.assert_array_equal(before,model['model'].coef_);np.testing.assert_array_equal(scale,model['scaler'].mean_)
            with self.assertRaises(ValueError):evaluate(model,train,Path(tmp)/'wrong.npy')

    def test_cache_mutation_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=fixture_cache(tmp,'2026-01-01')
            with (Path(r['path'])/'rows.f64').open('ab') as f:f.write(b'bad')
            with self.assertRaises(ValueError):fit(BASE,[r])

    def test_all_four_actual_trainers(self):
        models=[BASE['model'],{'algorithm':'elastic_net','parameters':dict(alpha=.000001,l1_ratio=.5,fit_intercept=False,max_iter=100,tol=.0001)},
            {'algorithm':'random_forest','parameters':dict(n_estimators=2,max_depth=2,min_samples_leaf=2,max_features=1.)},
            {'algorithm':'hist_gradient_boosting','parameters':dict(learning_rate=.1,max_iter=3,max_leaf_nodes=3,l2_regularization=1.,min_samples_leaf=3)}]
        with tempfile.TemporaryDirectory() as tmp:
            r=fixture_cache(tmp,'2026-01-01');check=fixture_cache(tmp,'2026-01-02')
            for i,m in enumerate(models):
                out=run_worker(dict(plan=dict(BASE,model=m),train=[r],check=[check]),Path(tmp)/f'worker{i}')
                self.assertTrue(out['success'],out);self.assertEqual(out['result']['fit']['fit_rows'],120)


if __name__=='__main__':unittest.main()
