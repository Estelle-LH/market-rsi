import copy
import unittest
from market_rsi import digest
from review_message_clock_origin import review
from prepare_clock_feedback import feedback


def seal(v):return {**v,'result_sha256':digest(v)}


def fixture():
    base={'complete':True,'ssh_reaped':True,'exit_code':0,'source_admitted':False,
        'transport':{'compressed_sha256':'a','decoded_sha256':'b','decoded_records':3}}
    p={'quote_event_counts_by_kind':{'rest_snapshot':{'quote_events':1,'adjacent_source_regressions':1,'below_source_highwater':1},
            'price_change':{'quote_events':2}},
       'source_regression_transition_counts':{'price_change -> rest_snapshot':1},'within_kind_source_regressions':{},
       'min_source_ms_by_kind':{},'max_source_ms_by_kind':{},'wrapper_adjacent_difference_counts':{}}
    old={'source_clock_totals':{'counts':{'quote_rows':3,'below_prior_highwater_rows':1},'adjacent_gap_histogram':{'regression':1}}}
    return seal({**copy.deepcopy(base),'profile':p}),seal({**copy.deepcopy(base),'profile':old})


class ClockFeedbackTests(unittest.TestCase):
    def test_separate_attribution_not_admission(self):
        r=review(*fixture());self.assertTrue(r['all_observed_regressions_between_kinds'])
        self.assertFalse(r['source_admitted']);self.assertFalse(r['policy_changed'])
    def test_modified_report_rejected(self):
        a,b=fixture();a['profile']['within_kind_source_regressions']={'book':2}
        with self.assertRaisesRegex(ValueError,'receipt'):review(a,b)
    def test_different_source_copy_rejected(self):
        a,b=fixture();a.pop('result_sha256');a['transport']['decoded_sha256']='c'
        with self.assertRaisesRegex(ValueError,'source copy'):review(seal(a),b)
    def test_counts_must_reconcile(self):
        a,b=fixture();a.pop('result_sha256');a['profile']['source_regression_transition_counts']={}
        with self.assertRaisesRegex(ValueError,'denominators'):review(seal(a),b)
    def test_incomplete_receipt_rejected(self):
        a,b=fixture();a.pop('result_sha256');a['complete']=False
        with self.assertRaisesRegex(ValueError,'incomplete'):review(seal(a),b)
    def test_within_kind_cannot_be_called_all_cross_kind(self):
        a,b=fixture();a.pop('result_sha256');a['profile']['source_regression_transition_counts']={'price_change -> price_change':1}
        self.assertFalse(review(seal(a),b)['all_observed_regressions_between_kinds'])
    def test_feedback_preserves_evidence_and_no_activation(self):
        refs=[{'findings':{'example':1}}];proposal={'example':'unchanged'};r=feedback(refs,proposal)
        self.assertEqual(r['bound_reviews'],refs);self.assertEqual(r['parent_proposal'],proposal)
        self.assertFalse(r['reference_kernel_not_activated']['source_admitted'])
        self.assertEqual(r['reference_kernel_not_activated']['fits'],0)
        self.assertIn('NOT chosen WS-only',r['current_task'])


if __name__=='__main__':unittest.main()
