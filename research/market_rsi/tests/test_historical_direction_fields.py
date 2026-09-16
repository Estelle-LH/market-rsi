import copy
import unittest

from historical_direction_fields import (DOWN, MAKER, MAPPING_ASSUMPTION, QUOTE_VOLUME,
    UP, direction_contract, latest_reported_direction, project_reported_orientation,
    project_reported_trade, require_reported_direction)
from historical_source_contract import CLOCK_ASSUMPTION, project


class ReportedDirectionTests(unittest.TestCase):
    now = 1775260800000

    def item(self, stream='binance_trades'):
        return {'path': f'unified/{stream}/date=2026-04-04/part-000001.parquet', 'lfs_sha256': 'a'*64}

    def trade(self, ordinal=0, **changes):
        row = dict(trade_id=4, trade_time=self.now, received_at=self.now+100,
                   price=50000., quantity=.2, quote_volume=10000., is_buyer_maker=1)
        row.update(changes)
        return project_reported_trade(row, self.item(), ordinal)

    def value(self, record, field=MAKER, when=None, **kwargs):
        return require_reported_direction(record, field, self.now+200 if when is None else when,
            max_age_ms=1000, clock_assumption=CLOCK_ASSUMPTION, **kwargs)

    def orientation(self, row_changes=None, meta_changes=None):
        row = dict(market_slug='m', asset_id='a', side_label='UP', event_type='book',
            source_ts_ms=self.now, ingest_ts_ms=self.now+100, best_bid=.4, best_ask=.5)
        meta = dict(market_slug='m', up_token_id='a', down_token_id='b', first_seen_ms=self.now-100,
                    up_price=999, down_price=-100, last_seen_ms=self.now+900000)
        row.update(row_changes or {}); meta.update(meta_changes or {})
        return project_reported_orientation(row, self.item('polymarket_ticks_ms'), 3,
            meta, self.item('market_meta'), 7)

    def test_old_price_projection_is_unchanged(self):
        row = dict(trade_id=1, trade_time=self.now, received_at=self.now+1,
                   price=10., quantity=2., quote_volume=20., is_buyer_maker=0)
        original=copy.deepcopy(row); old=project(row,self.item(),9)
        new=project_reported_trade(row,self.item(),9)
        self.assertEqual(row,original)
        self.assertEqual({k:v for k,v in new['values'].items() if k in old['values']},old['values'])
        self.assertEqual(new['source'],old['source'])
        self.assertEqual(self.value(new),0)

    def test_valid_flag_and_amount_are_observations_not_selected_flow(self):
        record=self.trade()
        self.assertEqual(self.value(record),1)
        self.assertEqual(self.value(record,QUOTE_VOLUME),10000.)
        self.assertTrue(record['maker_upstream_default_cannot_be_disambiguated'])
        self.assertFalse(record['individual_execution_count_verified'])
        self.assertFalse(direction_contract()['aggregation_windows_selected'])
        with self.assertRaisesRegex(ValueError,'alias'):
            self.value(record,'signed_flow')

    def test_missing_and_invalid_maker_are_never_defaulted_to_false(self):
        for value in (None, True, False, '0', .0, 2, -1, float('nan')):
            with self.subTest(value=value):
                record=self.trade(is_buyer_maker=value)
                self.assertNotIn(MAKER,record['values'])
                with self.assertRaisesRegex(ValueError,'flagged direction'):self.value(record)
                self.assertEqual(self.value(record,QUOTE_VOLUME),10000.)

    def test_bad_amount_does_not_erase_valid_maker_observation(self):
        for amount in (None,-1,float('inf'),9999):
            record=self.trade(quote_volume=amount)
            self.assertEqual(self.value(record),1)
            with self.assertRaises(ValueError):self.value(record,QUOTE_VOLUME)

    def test_future_stale_negative_lag_and_invalid_price_are_blocked(self):
        for record in (self.trade(received_at=self.now+300), self.trade(received_at=self.now-1),
                       self.trade(trade_time=self.now-10000), self.trade(price=-1)):
            with self.assertRaises(ValueError):self.value(record)

    def test_explicit_receipt_clock_assumption_required(self):
        with self.assertRaisesRegex(ValueError,'assumption'):
            require_reported_direction(self.trade(),MAKER,self.now+200,max_age_ms=1000,clock_assumption='truth')

    def latest(self, records):
        return latest_reported_direction(records,MAKER,self.now+200,max_age_ms=1000,clock_assumption=CLOCK_ASSUMPTION)

    def test_latest_bad_flag_cannot_revive_older_good(self):
        record=self.trade(1,received_at=self.now+150,is_buyer_maker=None)
        self.assertIsNone(self.latest([self.trade(),record])['value'])

    def test_conflicting_same_time_flags_have_no_arbitrary_winner(self):
        a,b=self.trade(),self.trade(1,is_buyer_maker=0)
        self.assertEqual(self.latest([a,b])['reason'],'conflicting_same_receipt_direction_values')
        self.assertIsNone(self.latest([b,a])['value'])
        result=self.latest([a,self.trade(2)])
        self.assertEqual(result['value'],1); self.assertEqual(len(result['sources']),2)

    def test_no_visible_and_wrong_stream(self):
        self.assertEqual(self.latest([self.trade(received_at=self.now+300)])['reason'],'no_visible_observation')
        with self.assertRaises(ValueError):self.latest([self.orientation()])

    def test_orientation_has_two_sources_and_no_future_prices(self):
        record=self.orientation()
        self.assertEqual(self.value(record,UP,mapping_assumption=MAPPING_ASSUMPTION),1)
        self.assertEqual(self.value(record,DOWN,mapping_assumption=MAPPING_ASSUMPTION),0)
        self.assertNotEqual(record['source']['physical_row_id'],record['metadata_source']['physical_row_id'])
        self.assertFalse(record['settlement_outcome_verified'])
        for field in ('up_price','down_price','last_seen_ms','question'):
            self.assertNotIn(field,record['values'])

    def test_orientation_requires_mapping_assumption_and_prior_metadata(self):
        with self.assertRaisesRegex(ValueError,'mapping assumption'):self.value(self.orientation(),UP)
        record=self.orientation(meta_changes={'first_seen_ms':self.now+500})
        with self.assertRaisesRegex(ValueError,'not yet recorded'):
            self.value(record,UP,mapping_assumption=MAPPING_ASSUMPTION)

    def test_orientation_disagreements_never_relabel(self):
        for row,meta in (({'side_label':'DOWN'},{}),({'asset_id':'unknown'},{}),
                         ({'market_slug':'wrong'},{}),({'side_label':None},{}),
                         ({},{'first_seen_ms':None}),({},{'down_token_id':'a'})):
            record=self.orientation(row,meta)
            with self.assertRaises(ValueError):self.value(record,UP,mapping_assumption=MAPPING_ASSUMPTION)
            self.assertEqual(record['entity'],[row.get('market_slug','m'),row.get('asset_id','a')])

    def test_physical_reference_and_contract_must_match(self):
        record=self.trade();record['direction_contract_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'contract'):self.value(record)
        with self.assertRaises(ValueError):self.trade(ordinal=-1)


if __name__ == '__main__':
    unittest.main()
