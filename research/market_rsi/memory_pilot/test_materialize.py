import json
from pathlib import Path
import tempfile
import unittest
from test_typed_raw_profile import message,T,contract
from typed_raw_profile import Profile
from memory_pilot.materialize import CacheProfile,write_cache,ROW
from market_rsi import file_hash


class MaterializeTests(unittest.TestCase):
    def profile(self, rows):
        p=CacheProfile(contract(),T)
        for i,r in enumerate(rows,1): p.consume(json.dumps(r).encode(),i)
        return p

    def rows(self):
        return [message(T+i*10000,bid=f'{.2+.01*(i%3):.2f}',ask=f'{.6+.01*(i%3):.2f}') for i in range(26)]

    def test_exact_original_mask_and_moments(self):
        rows=self.rows();p=self.profile(rows);old=Profile(contract(),T)
        for i,r in enumerate(rows,1):old.consume(json.dumps(r).encode(),i)
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)/'cache';h=write_cache(p,d)
            self.assertEqual(h['quality'],old.summary())
            self.assertEqual(h['sha256'],file_hash(d/'rows.f64'))
            values=list(ROW.iter_unpack((d/'rows.f64').read_bytes()))
            self.assertEqual(len(values),h['shape'][0])
            self.assertTrue(all(v[2]==.4 for v in values))
            self.assertEqual(h['bytes'],len(values)*48)

    def test_future_values_cannot_change_past_features(self):
        original=self.rows();changed=self.rows()
        for r in changed[16:]:
            for c in r['m']['price_changes']:c.update(best_bid='.1',best_ask='.9')
        with tempfile.TemporaryDirectory() as tmp:
            a=Path(tmp)/'a';b=Path(tmp)/'b';write_cache(self.profile(original),a);write_cache(self.profile(changed),b)
            x=list(ROW.iter_unpack((a/'rows.f64').read_bytes()));y=list(ROW.iter_unpack((b/'rows.f64').read_bytes()))
            self.assertEqual([v[:4] for v in x[:8]],[v[:4] for v in y[:8]])

    def test_fresh_directory_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileExistsError):write_cache(self.profile(self.rows()),Path(tmp))

    def test_decimal_spread_boundary(self):
        rows=self.rows()
        for r in rows:
            r['m']['price_changes'][0].update(best_bid='.1',best_ask='.2')
        p=self.profile(rows)
        self.assertTrue(all(v==.1 for v in next(iter(p.spreads.values()))))


if __name__=='__main__':unittest.main()
