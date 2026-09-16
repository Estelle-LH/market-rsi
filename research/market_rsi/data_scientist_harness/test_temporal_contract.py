import copy
import unittest
from data_scientist_harness import temporal_contract as t


def fixture_contract():
    return {"clock":"source_ms","decision_rule":"after_each_record","label_origin":"decision_time",
        "horizon_ms":60000,"endpoint_rule":"backward_asof","endpoint_tolerance_ms":1000,
        "missing_endpoint":"unavailable","invalid_quote":"invalidate","claim":"recorded_observation_only"}


class TemporalTests(unittest.TestCase):
    def test_supported_policy_matrix(self):
        for clock in ("source_ms","wrapper_ms"):
            for rule in ("after_each_record","after_timestamp_group"):
                for endpoint in ("backward_asof","forward_asof"):
                    for horizon in (4,100,60000):
                        for tolerance in (0,1,horizon-1):
                            c=fixture_contract();c.update(clock=clock,decision_rule=rule,endpoint_rule=endpoint,horizon_ms=horizon,endpoint_tolerance_ms=tolerance)
                            r=t.probe(c)
                            self.assertTrue(r["checks_passed"],(c,r["errors"]))
                            self.assertEqual(r["cases"]["observed_equal"]["label"],0)
                            self.assertIsNone(r["cases"]["missing_tail"]["label"])
                            self.assertFalse(r["real_source_validated"])

    def test_unsafe_requested_semantics_are_not_executed(self):
        for field,value,error in [("missing_endpoint","zero","missing_observation"),
                                  ("invalid_quote","carry_last_valid","invalid_quote"),
                                  ("claim","continuous_market_state","external_capture")]:
            c=fixture_contract();c[field]=value;r=t.probe(c)
            self.assertFalse(r["checks_passed"])
            self.assertTrue(any(error in e for e in r["errors"]))
            self.assertEqual(r["raw_market_rows_read"],0)

    def test_group_timestamp_is_not_the_later_prediction_time(self):
        c=fixture_contract();c.update(decision_rule="after_timestamp_group",label_origin="group_time")
        r=t.probe(c);self.assertFalse(r["checks_passed"])
        self.assertEqual(r["cases"]["observed_change"]["reason"],"target_starts_before_prediction_is_available")

    def test_later_same_ms_value_cannot_rewrite_record_prediction(self):
        c=fixture_contract();rows=t.fixtures(c)["observed_change"];a=t.evaluate(rows,c)
        rows[1]["value"]=0.99;b=t.evaluate(rows,c)
        self.assertEqual(a["feature_last_key"],[0,0,0,0])
        self.assertEqual(a["feature_value"],b["feature_value"])

    def test_regression_and_invalid_state_are_not_filled(self):
        c=fixture_contract();r=t.probe(c)
        self.assertEqual(r["cases"]["regression"]["reason"],"clock_regression")
        self.assertEqual(r["cases"]["invalid_endpoint"]["reason"],"invalid_endpoint_quote")

    def test_duplicate_keys_and_out_of_bounds_parameters_fail(self):
        c=fixture_contract();rows=t.fixtures(c)["observed_change"]
        rows[1]["key"]=rows[0]["key"]
        with self.assertRaises(ValueError):t.evaluate(rows,c)
        for field,value in [("horizon_ms",True),("horizon_ms",0),("endpoint_tolerance_ms",-1),("endpoint_tolerance_ms",60000)]:
            bad=copy.deepcopy(c);bad[field]=value
            with self.assertRaises(ValueError):t.probe(bad)


if __name__=="__main__":unittest.main()
