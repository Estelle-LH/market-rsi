"""Read-only saved public metadata tests; no model/Native/scorer/ledger runner."""
from copy import deepcopy
from pathlib import Path
import unittest
import earnings_population_clean_slate as clean
from supervisor_harness import capacity_feedback_engine as e
A=Path(__file__).resolve().parents[2]/'edgar-population-20261016'
origin=e.read(e.pin(A/'TRAIN25-CLEAN-ROUND15-03A-SECOND-ORIGIN134.json'))
latest=e.read(origin['prior_comparison']);feedback=e.read(origin['public_feedback'])
class Metadata(unittest.TestCase):
    def test_authentic_full_diagnostic_accepted(self):
        clean.validate_current_feedback_metadata(feedback,latest,origin,15)
    def test_bounded_projection_preserves_current_facts(self):
        before=deepcopy(feedback);value=deepcopy(feedback)
        value['actual_R_H_diagnostic']=clean.current_feedback_diagnostic(origin,14,feedback['version_id'])
        clean.validate_current_feedback_metadata(value,latest,origin,15)
        facts=e.read(origin['supervisor_diagnostic'])
        self.assertEqual(value['actual_R_H_diagnostic']['summary'],{k:v for k,v in facts.items() if k!='period_rows'})
        self.assertEqual(feedback,before)
        for key in ('rows','actual_parent','selection_incumbent','version_id','company_equal_mean','manifest'):
            self.assertEqual(value[key],feedback[key])
    def test_stale_round_rejected(self):
        value=deepcopy(feedback);value['logical_round']=13
        with self.assertRaises(ValueError):clean.validate_current_feedback_metadata(value,latest,origin,15)
    def test_stale_diagnostic_rejected(self):
        value=deepcopy(feedback);value['actual_R_H_diagnostic']=value['historical_round13_diagnostic']
        with self.assertRaises(ValueError):clean.validate_current_feedback_metadata(value,latest,origin,15)
    def test_missing_diagnostic_rejected(self):
        value=deepcopy(feedback);value.pop('actual_R_H_diagnostic')
        with self.assertRaises(ValueError):clean.validate_current_feedback_metadata(value,latest,origin,15)
    def test_wrong_projection_version_rejected(self):
        value=deepcopy(feedback);value['actual_R_H_diagnostic']=clean.current_feedback_diagnostic(origin,14,'wrong')
        with self.assertRaises(ValueError):clean.validate_current_feedback_metadata(value,latest,origin,15)
    def test_missing_current_fact_rejected(self):
        value=deepcopy(feedback);value['actual_R_H_diagnostic']=clean.current_feedback_diagnostic(origin,14,feedback['version_id'])
        value['actual_R_H_diagnostic']['summary'].pop('learning_status')
        with self.assertRaises(ValueError):clean.validate_current_feedback_metadata(value,latest,origin,15)
    def test_wrong_evidence_binding_rejected(self):
        value=deepcopy(feedback);value['actual_R_H_diagnostic']=clean.current_feedback_diagnostic(origin,14,feedback['version_id'])
        value['actual_R_H_diagnostic']['evidence']['sha256']='0'*64
        with self.assertRaises(ValueError):clean.validate_current_feedback_metadata(value,latest,origin,15)
    def test_legacy14_not_reinterpreted(self):
        value=deepcopy(feedback);value['logical_round']=1;value.pop('actual_R_H_diagnostic')
        clean.validate_current_feedback_metadata(value,latest,origin,14)
    def test_historical_feedback_has_not_been_mutated(self):
        self.assertEqual(e.read(origin['public_feedback']),feedback)
if __name__=='__main__':unittest.main()
