import json
import unittest
from concentration_audit import Detail,distribution,summarize
from preliminary_comparison import score
from typed_raw_profile import Profile,canonical_kernel,sample_at,DAY
from test_typed_raw_profile import T,contract,message


def fixture():
    p=Profile(contract(),T);d=Detail(['a','b']);rows=[]
    for i,t in enumerate(range(0,300001,10000),1):
        lo,hi=(.1,.9) if i%2 else (.2,.4)
        r=message(T+t,asset='a',bid=str(lo),ask=str(hi));r['m']['price_changes'][0].update(size='0',side='BUY')
        r['m']['price_changes'].append(dict(asset_id='b',best_bid=str(1-hi),best_ask=str(1-lo),size='0',side='SELL'))
        rows.append(r);raw=json.dumps(r).encode();p.consume(raw,i);d.consume(raw,i)
    expected=[]
    for s in p.entities.values():
        k=canonical_kernel(s.rows(),contract());prefix=list(range(len(s.t)+1));x=[];y=[]
        for i in range(1,len(s.t)):
            f,l=sample_at(k,i,contract(),prefix,T+DAY)
            if f['available'] and l['available']:x.append(f['feature']);y.append(l['label'])
        expected.append(score(x,y,-.2,False))
    return p,d,expected,rows


class AuditTests(unittest.TestCase):
    def test_complementary_pair_is_one_market(self):
        p,d,e,_=fixture();r=summarize(p,d,[0,1],-.2,e)
        self.assertTrue(r['same_market']);self.assertEqual(r['complementary_bbo_pairs'],31)
        self.assertEqual(r['identical_full_message_repeats'],0)
        self.assertNotIn('fixture-market',json.dumps(r));self.assertTrue(r['no_new_fit'])
        self.assertGreater(r['tokens'][0]['large_mid_jump_count'],0)
        self.assertTrue(r['tokens'][0]['diagnostic_score_buckets'])

    def test_duplicate_message_count_not_dedup(self):
        _,d,_,rs=fixture();n=len(d.quotes['a']);d.consume(json.dumps(rs[-1]).encode(),100)
        self.assertEqual(d.duplicates,1);self.assertEqual(len(d.quotes['a']),n+1)

    def test_source_mismatch_rejected(self):
        p,d,e,_=fixture();d.quotes['a'][0]['mid']+=.1
        with self.assertRaises(ValueError):summarize(p,d,[0,1],-.2,e)

    def test_expected_moments_mismatch_rejected(self):
        p,d,e,_=fixture();e[0]['moments']['sum_xy']+=1
        with self.assertRaises(ValueError):summarize(p,d,[0,1],-.2,e)

    def test_empty_and_quantiles(self):
        self.assertEqual(distribution([]),dict(n=0));self.assertEqual(distribution([2,1,3])['median'],2)


if __name__=='__main__':unittest.main()
