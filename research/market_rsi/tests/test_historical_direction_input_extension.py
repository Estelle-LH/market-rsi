import copy
import gzip
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from historical_direction_fields import MAKER, QUOTE_VOLUME, project_reported_trade
from historical_direction_input_extension import ADDED_FIELDS, agree_field, original_rows, verify_addition, sampling_ancestry
from market_rsi import digest


class DirectionInputExtensionTests(unittest.TestCase):
    now=1775260800000

    def arrays(self):
        x={'row_id':np.array(['a','b']),'entity':np.array(['m','m']),
           'date':np.array(['2026-04-04']*2),'decision_ms':np.array([self.now,self.now+1000]),
           'field_names':np.array(['price','size']),'values':np.array([[.5,np.nan],[-0.,2.]])}
        n={k:v.copy() for k,v in x.items() if k not in ('field_names','values')}
        n.update(field_names=np.array(['price','size',*ADDED_FIELDS]),
                 values=np.column_stack((x['values'],[[1,50,1,0],[0,30,np.nan,np.nan]])))
        return x,n

    def test_annotated_plan_can_reuse_only_identical_sampling(self):
        old={'proposal_id':'old','plan':{'max_age_ms':300000,'cadence_ms':60000,'rationale':'original'}}
        old['proposal_sha256']=digest(old)
        new={'proposal_id':'new','plan':dict(old['plan'])};new['proposal_sha256']=digest(new)
        material={'proposal_sha256':old['proposal_sha256']}
        self.assertTrue(sampling_ancestry(material,old,new)['same_sampling_verified'])
        new['plan']['max_age_ms']=400000;del new['proposal_sha256'];new['proposal_sha256']=digest(new)
        with self.assertRaisesRegex(ValueError,'sampling parameters'):sampling_ancestry(material,old,new)
        with self.assertRaisesRegex(ValueError,'ancestor'):sampling_ancestry({'proposal_sha256':'wrong'},old,old)

    def test_old_nan_and_signed_zero_preserved(self):
        x,n=self.arrays();result=verify_addition(x,n)
        self.assertTrue(result['all_original_arrays_and_values_byte_identical'])
        n['values'][1,0]=0.
        with self.assertRaisesRegex(ValueError,'byte-identical'):verify_addition(x,n)

    def test_no_old_fill_drop_reorder_or_clock_change(self):
        for change in ('fill','rename','reorder','clock','extra'):
            x,n=self.arrays()
            if change=='fill':n['values'][0,1]=0
            elif change=='rename':n['field_names'][0]='renamed'
            elif change=='reorder':n['row_id']=n['row_id'][::-1]
            elif change=='clock':n['decision_ms'][0]+=1
            else:n['field_names']=np.append(n['field_names'],'unapproved')
            with self.subTest(change=change),self.assertRaises(ValueError):verify_addition(x,n)

    def test_new_fields_still_obey_domains_and_role_consistency(self):
        for column,value in ((2,.5),(3,-1),(4,.5),(4,0),(5,np.nan)):
            x,n=self.arrays();n['values'][0,column]=value
            with self.assertRaises(ValueError):verify_addition(x,n)

    def trade(self, ordinal=0, **changes):
        row=dict(trade_id=1,trade_time=self.now,received_at=self.now+100,
                 price=10.,quantity=2.,quote_volume=20.,is_buyer_maker=1)
        row.update(changes)
        return project_reported_trade(row,{'path':'unified/binance_trades/date=2026-04-04/part-000001.parquet',
                                          'lfs_sha256':'a'*64},ordinal)

    def test_tied_fields_are_checked_independently_without_arbitrary_order(self):
        a,b=self.trade(),self.trade(1,is_buyer_maker=0)
        v,reason=agree_field([a,b],MAKER,self.now+1000,300000)
        self.assertTrue(np.isnan(v));self.assertIn('conflicting',reason)
        self.assertEqual(agree_field([b,a],QUOTE_VOLUME,self.now+1000,300000),(20.,'present'))

    def test_missing_future_stale_and_different_timestamps_are_blocked(self):
        for records in ([],[self.trade(is_buyer_maker=None)],[self.trade(received_at=self.now+2000)],
                        [self.trade(trade_time=self.now-400000)]):
            value,reason=agree_field(records,MAKER,self.now+1000,300000)
            self.assertTrue(np.isnan(value));self.assertNotEqual(reason,'present')
        with self.assertRaisesRegex(ValueError,'unequal receipt'):
            agree_field([self.trade(),self.trade(1,received_at=self.now+500)],MAKER,self.now+1000,300000)

    def test_panel_iterator_keeps_quiet_missing_rows_and_rejects_future_labels(self):
        row={'market_slug':'m','asset_id':'a','decision_ms':self.now,'utc_date':'2026-04-04',
             'target':None,'training_admitted':False,'observations':{}}
        row['row_id']=digest({k:row[k] for k in ('market_slug','asset_id','decision_ms')})
        x={'row_id':np.array([row['row_id']]),'decision_ms':np.array([self.now]),'date':np.array(['2026-04-04'])}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'rows.jsonl.gz'
            with gzip.open(path,'wt') as stream:stream.write(json.dumps(row)+'\n')
            self.assertEqual(list(original_rows(path,x,['2026-04-04'])),[row])
            bad=copy.deepcopy(row);bad['target']=.2
            with gzip.open(path,'wt') as stream:stream.write(json.dumps(bad)+'\n')
            with self.assertRaisesRegex(ValueError,'unlabelled'):list(original_rows(path,x,['2026-04-04']))


if __name__=='__main__':unittest.main()
