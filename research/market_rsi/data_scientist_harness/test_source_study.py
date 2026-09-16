import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from data_scientist_harness.broker import Broker, TOOLS, validate_shape
from data_scientist_harness import fixtures, source_study
from data_scientist_harness.source_study_canary import workspace, proposal, fixture_contract, fixture_samples
from market_rsi import load_json, file_hash


class SourceStudyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name).resolve()/"run"
        self.b = Broker(self.root, workspace(self.root, network=True), transport=fixtures.fake_transport)
        self.status = self.b.call("inspect_harness", {})
        read = self.b.call("read_public_source", {"url": "https://example.org/research", "offset": 0})
        research = self.b.call("record_research", {"layer": "data_quality", "question": "fixture", "read_records": [read["record_id"]],
            "applicability": "fixture", "limitations": "fixture", "alternatives": "fixture", "proposed_test": "fixture"})
        self.args = proposal(self.status, research["record_id"])
        self.b.call("acknowledge_current_findings", {"finding_sha256": self.status["finding_sha256"],
            "responses": [{"id": "fixture-only", "handling": "fixture", "next_evidence": "QA"}]})
        result=self.b.call("probe_temporal_contract",{"contract":fixture_contract(),"research_record":research["record_id"]})
        self.args["temporal_probe_record"]=result["record_id"]
        result=self.b.call('probe_sample_contract',{'contract':fixture_samples(),'research_record':research['record_id']})
        self.args['sample_contract_record']=result['record_id']

    def test_missing_or_mismatched_sample_contract_rejected(self):
        a=copy.deepcopy(self.args);a.pop('sample_contract_record')
        with self.assertRaises(ValueError):self.b.call('propose_source_study',a)
        a=copy.deepcopy(self.args);a['sample_contract_record']='0001'
        with self.assertRaises(ValueError):self.b.call('propose_source_study',a)
        c=fixture_samples();c['temporal']['endpoint_tolerance_ms']=999
        r=self.b.call('probe_sample_contract',{'contract':c,'research_record':self.args['research_record']})
        a=copy.deepcopy(self.args);a['sample_contract_record']=r['record_id']
        with self.assertRaisesRegex(ValueError,'exact sample'):self.b.call('propose_source_study',a)

    def tearDown(self): self.temp.cleanup()

    def test_plan_before_admission_without_data_or_process(self):
        before = self.b.store.quality()
        with patch("data_scientist_harness.broker.subprocess.Popen") as spawn, patch.object(self.b, "_inputs") as inputs:
            result = self.b.call("propose_source_study", self.args)
            spawn.assert_not_called(); inputs.assert_not_called()
        self.assertTrue(result["registered"]); self.assertFalse(result["execution_admitted"])
        self.assertEqual(self.b.store.quality(), before)
        self.assertFalse(self.b.store.config["inputs_present"])
        with self.assertRaisesRegex(RuntimeError, "quality must pass"): self.b.store.quality_before_training()

    def test_old_source_spec_findings_or_research_ref_rejected(self):
        bad = []
        for key in ("current_spec_sha256", "finding_sha256", "research_record"):
            a = copy.deepcopy(self.args); a[key] = "f"*64; bad.append(a)
        for key in ("source_id", "raw_manifest_sha256"):
            a = copy.deepcopy(self.args); a["source"][key] = "f"*64; bad.append(a)
        for a in bad:
            with self.assertRaises((ValueError, FileNotFoundError)): self.b.call("propose_source_study", a)
        self.assertFalse((self.root/"source-study-proposal.json").exists())

    def test_protected_overlapping_reversed_and_duplicate_dates_rejected(self):
        for fit, check in [(["1970-01-02"], ["2026-08-26"]), (["1970-01-03"], ["1970-01-02"]),
                           (["1970-01-02"], ["1970-01-02"]), (["1970-01-02"]*2, ["1970-01-03"]), ([], ["1970-01-03"])]:
            a = copy.deepcopy(self.args); a["evaluation"].update(fit_dates=fit, check_dates=check)
            with self.assertRaises(ValueError): self.b.call("propose_source_study", a)

    def test_invalid_horizon_and_missing_evidence_rejected(self):
        for value in (0, -1, True):
            a = copy.deepcopy(self.args); a["objective"]["horizon_ms"] = value
            with self.assertRaises(ValueError): self.b.call("propose_source_study", a)
        a = copy.deepcopy(self.args); a["missing_evidence"] = []
        with self.assertRaises(ValueError): self.b.call("propose_source_study", a)

    def test_first_valid_proposal_cannot_be_replaced(self):
        self.b.call("propose_source_study", self.args); before = file_hash(self.root/"source-study-proposal.json")
        a = copy.deepcopy(self.args); a["proposal_id"] = "second"
        with self.assertRaisesRegex(ValueError, "permanent"): self.b.call("propose_source_study", a)
        self.assertEqual(before, file_hash(self.root/"source-study-proposal.json"))

    def test_mutated_proposal_cannot_be_archived(self):
        self.b.call("propose_source_study", self.args)
        (self.root/"source-study-proposal.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "changed"):
            self.b.call("submit_research_decision", {"action": "defer", "trial_id": "", "reason": "test"})
        self.assertFalse((self.root/"submitted-decision.json").exists())

    def test_successful_plan_is_in_archive_and_session_closes(self):
        result = self.b.call("propose_source_study", self.args)
        end = self.b.call("submit_research_decision", {"action": "defer", "trial_id": "", "reason": "test"})
        self.assertEqual(end["source_study_proposal"], result["proposal"])
        self.assertEqual(load_json(self.root/"round-archive.json")["decision"]["source_study_proposal"], result["proposal"])
        with self.assertRaisesRegex(ValueError, "closed"): self.b.call("propose_source_study", self.args)

    def test_actual_schema_defines_all_nested_properties(self):
        schema = next(t["inputSchema"] for t in TOOLS if t["name"] == "propose_source_study")
        validate_shape(self.args, schema)
        self.assertEqual(schema["properties"]["objective"]["required"], ["quantity", "units", "horizon_ms", "availability_and_label_rule"])
        self.assertFalse(schema["properties"]["evaluation"]["additionalProperties"])

    def test_missing_failed_mismatched_or_forged_probe_cannot_register(self):
        a=copy.deepcopy(self.args);a["temporal_probe_record"]="0001"
        with self.assertRaises(ValueError):self.b.call("propose_source_study",a)
        a=copy.deepcopy(self.args);a["objective"]["horizon_ms"]=5000
        with self.assertRaisesRegex(ValueError,"same-horizon"):self.b.call("propose_source_study",a)
        bad=fixture_contract();bad["missing_endpoint"]="zero"
        receipt=self.b.call("probe_temporal_contract",{"contract":bad,"research_record":self.args["research_record"]})
        self.assertFalse(receipt["checks_passed"])
        a=copy.deepcopy(self.args);a["temporal_probe_record"]=receipt["record_id"]
        with self.assertRaisesRegex(ValueError,"same-horizon"):self.b.call("propose_source_study",a)
        self.assertFalse((self.root/"source-study-proposal.json").exists())


if __name__ == "__main__": unittest.main()
