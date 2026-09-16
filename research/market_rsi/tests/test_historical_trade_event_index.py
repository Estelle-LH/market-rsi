import unittest
import numpy as np
from historical_trade_event_index import project_batch


class TradeIndexTests(unittest.TestCase):
    def fixture(self):
        t=int(np.datetime64('2026-04-04','ms').astype(np.int64))
        return {'received_at':np.array([t,t,t+86400000],dtype=np.int64),
            'trade_time':np.array([t-1,t-2,t+86399999],dtype=np.int64),
            'trade_id':np.array([12,13,14],dtype=np.int64),'price':np.array([2.,3.,4.]),
            'quantity':np.array([3.,4.,5.]),'quote_volume':np.array([6.,12.,20.]),
            'is_buyer_maker':np.array([0,1,0],dtype=np.int64)}

    def test_receipt_date_selection_retains_ties_ordinals_and_raw_values(self):
        v=self.fixture();r=project_batch(v,2,100,['2026-04-04'])
        np.testing.assert_array_equal(r['row_ordinal'],[100,101])
        np.testing.assert_array_equal(r['aggregate_trade_id'],[12,13])
        np.testing.assert_array_equal(r['reported_maker'],[0,1])
        np.testing.assert_array_equal(r['quality_bits'],[0,0])
        self.assertEqual(len(v['received_at']),3)

    def test_bad_values_are_flagged_not_dropped_or_filled(self):
        v=self.fixture();v['is_buyer_maker'][0]=4;v['quote_volume'][0]=np.nan
        v['trade_time'][1]=v['received_at'][1]+1
        r=project_batch(v,0,0,['2026-04-04'])
        self.assertEqual(len(r['received_ms']),2)
        self.assertTrue(r['quality_bits'][0]&2);self.assertTrue(r['quality_bits'][0]&4)
        self.assertEqual(r['reported_maker'][0],4);self.assertTrue(np.isnan(r['reported_quote_volume'][0]))
        self.assertTrue(r['quality_bits'][1]&8)

    def test_unplaceable_clock_or_changed_schema_fails_closed(self):
        v=self.fixture();v['received_at']=v['received_at'].astype(float)
        with self.assertRaisesRegex(ValueError,'integer'):project_batch(v,0,0,['2026-04-04'])
        v=self.fixture();v['extra']=np.zeros(3)
        with self.assertRaisesRegex(ValueError,'columns'):project_batch(v,0,0,['2026-04-04'])


if __name__=='__main__':unittest.main()
