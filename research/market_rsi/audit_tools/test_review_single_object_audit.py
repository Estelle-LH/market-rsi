import copy
import unittest
from market_rsi import digest
from review_single_object_audit import findings


def fixture():
    r=dict.fromkeys(('source_admitted','qa_pass','labels_computed','features_computed','fits','provider_calls','raw_rows_exported','raw_identifiers_exported','new_test_opened','request_fulfilled_in_full'),False)
    r.update(complete=True,ssh_reaped=True,exit_code=0,scope={'object':{'date':'2026-09-08','hour':'12','advertised_bytes':5}},
        transport={'decoder_reaped':True,'feeder_reaped':True,'source_unchanged_verified':True,'compressed_hash_is_complete':True,
            'source_open_passes':1,'compressed_bytes_read':5,'decoded_records':2,'decoded_bytes':9,'compressed_sha256':'a'*64,'decoded_sha256':'b'*64},
        profile={'population':{'input_counts':{'raw_records':2,'quote_observations':2},'totals':{
            'counts':{'adjacent_valid_mid_pairs':1,'equal_mid_pairs':1,'changed_mid_pairs':0},'source_status':{'uncrossed':2}},'breadth':{'entities':1}},
            'source_clock_totals':{'counts':{'quote_rows':2,'adjacent_timestamp_pairs':1},'adjacent_gap_histogram':{'0ms':1}},
            'source_clock_entities':[{'counts':{'quote_rows':2},'min_source_ms':1787791013385,'max_source_ms':1787791013385}]})
    r['result_sha256']=digest(r);return r


class ReviewTests(unittest.TestCase):
    def test_old_source_clock_not_interpreted_as_outage(self):
        f=findings(fixture());self.assertEqual(f['clock_observations']['entities_with_all_source_times_before_named_hour'],1)
        self.assertFalse(f['clock_observations']['timestamp_semantics_or_outage_inferred'])
        self.assertEqual(f['observation_activity']['equal_mid_fraction'],1)
        self.assertFalse(f['source_admitted'])

    def test_changed_receipt_rejected(self):
        r=fixture();r['complete']=False
        with self.assertRaises(ValueError):findings(r)

    def test_denominator_error_even_with_new_hash_rejected(self):
        r=fixture();r['profile']['population']['totals']['counts']['changed_mid_pairs']=1
        r['result_sha256']=digest({k:v for k,v in r.items() if k!='result_sha256'})
        with self.assertRaises(ValueError):findings(r)

    def test_no_admission_or_cleanup_promotion(self):
        for field in ('source_admitted','labels_computed','request_fulfilled_in_full'):
            r=fixture();r[field]=True;r['result_sha256']=digest({k:v for k,v in r.items() if k!='result_sha256'})
            with self.assertRaises(ValueError):findings(r)

    def test_empty_pair_denominator_is_unknown_not_zero(self):
        r=fixture();c=r['profile']['population']['totals']['counts'];c['equal_mid_pairs']=c['adjacent_valid_mid_pairs']=0
        r['result_sha256']=digest({k:v for k,v in r.items() if k!='result_sha256'})
        self.assertIsNone(findings(r)['observation_activity']['equal_mid_fraction'])


if __name__=='__main__':unittest.main()
