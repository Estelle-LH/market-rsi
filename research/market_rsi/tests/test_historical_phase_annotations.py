import copy
import unittest

from historical_phase_annotations import annotate, require_same_sampling


class PhaseAnnotationTests(unittest.TestCase):
    start=1770890400000
    def row(self, offset=0):
        return {'market_slug':'btc-updown-15m-1770890400','row_id':'fixture',
            'decision_ms':self.start+offset,'pm_events_since_previous_grid_tick':0,
            'observations':{'polymarket_ticks_ms':{'values':{},'reason':'observation exceeds declared staleness','sources':[]}}}

    def test_phase_at_boundaries_is_causal_not_settlement(self):
        for offset,phase in [(-1,'before_nominal_window'),(0,'within_nominal_window'),(899999,'within_nominal_window'),(900000,'after_nominal_window')]:
            value=annotate(self.row(offset));self.assertEqual(value['nominal_phase'],phase)
            self.assertFalse(value['nominal_window_is_verified_settlement'])

    def test_missing_or_stale_row_is_kept_without_fabricating_age(self):
        value=annotate(self.row())
        self.assertTrue(value['observation_states']['polymarket_ticks_ms']['stale'])
        self.assertIsNone(value['observation_states']['polymarket_ticks_ms']['recorded_arrival_age_ms'])
        self.assertTrue(value['quiet_since_previous_grid_tick'])
        self.assertIsNone(value['row_weight']);self.assertIsNone(value['target'])

    def test_source_row_is_unchanged(self):
        row=self.row();before=copy.deepcopy(row);annotate(row);self.assertEqual(row,before)

    def test_future_available_flag_cannot_be_hidden_in_annotation(self):
        row=self.row();row['observations']['polymarket_ticks_ms']['available_ms']=self.start+1
        with self.assertRaisesRegex(ValueError,'future'):annotate(row)

    def test_changed_sampling_cannot_reuse_old_population(self):
        old={'plan':{'cadence_ms':60000,'feature_ideas':['old'],'rationale':'a','limitations':'a'}}
        new=copy.deepcopy(old);new['plan']['feature_ideas']=['new']
        require_same_sampling(old,new)
        new['plan']['cadence_ms']=1000
        with self.assertRaisesRegex(ValueError,'sampling parameters'):require_same_sampling(old,new)

    def test_unsupported_slug_never_invents_a_clock(self):
        row=self.row();row['market_slug']='unknown'
        with self.assertRaisesRegex(ValueError,'no supported'):annotate(row)


if __name__=='__main__':unittest.main()
