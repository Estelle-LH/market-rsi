import copy
import unittest
from pathlib import Path
from unittest.mock import patch
from source_study_object_scope import resolve, require_full_binding, finding_for_parent, audit


class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.dates=["2026-08-21","2026-08-22","2026-08-23"]
        self.inventory={"schema":"capture_raw_file_inventory_v1","host":"173.255.231.4",
            "source_root":"/opt/d10/raw/data/polymarket","source_admitted":False,
            "complete_content_verified":False,"raw_rows_read":0,
            "days":[{"date":d,"files_present":int(i!=1),"compressed_bytes":100*int(i!=1)} for i,d in enumerate(self.dates)],
            "files":[{"date":d,"filename":"polymarket-"+d.replace("-","")+"T00.jsonl.zst","compressed_bytes":100} for i,d in enumerate(self.dates) if i!=1]}
        self.proposal={"source":{"source_id":"d10_polymarket_raw"},
            "evaluation":{"fit_dates":[self.dates[0]],"check_dates":[self.dates[2]]}}
        self.manifest={"source_id":"d10_polymarket_raw","objects":[self.obj(self.inventory["files"][0])]}

    def obj(self,f):
        return {"host":self.inventory["host"],"path":self.inventory["source_root"]+"/"+f["filename"],"bytes":f["compressed_bytes"],"sha256":"a"*64}

    def result(self):return resolve(self.proposal,self.inventory,self.manifest,self.dates,self.dates)

    def test_removing_empty_date_does_not_shrink_work(self):
        result=self.result()
        self.assertEqual(result["removed_dates"],[self.dates[1]])
        self.assertEqual(result["removed_file_count"],0)
        self.assertEqual(result["requested_files"],result["previous_files"])
        self.assertEqual(result["manifest_unbound_files"],1)
        with self.assertRaisesRegex(ValueError,"no scan admitted"):require_full_binding(result)

    def test_full_binding_is_not_source_admission(self):
        self.manifest["objects"].append(self.obj(self.inventory["files"][1]))
        result=self.result();require_full_binding(result)
        self.assertFalse(result["content_integrity_rechecked"])
        self.assertFalse(result["current_remote_availability_verified"])

    def test_conflicting_or_duplicate_object_fails(self):
        before=copy.deepcopy(self.manifest)
        self.manifest["objects"][0]["bytes"]=101
        with self.assertRaisesRegex(ValueError,"size conflict"):self.result()
        self.manifest=before;self.manifest["objects"]*=2
        with self.assertRaisesRegex(ValueError,"duplicate"):self.result()

    def test_forbidden_dates_and_wrong_source_fail(self):
        self.proposal["evaluation"]["check_dates"]=["2026-09-06"]
        with self.assertRaisesRegex(ValueError,"opened"):self.result()
        self.proposal["evaluation"]["check_dates"]=[self.dates[2]]
        self.manifest["source_id"]="different"
        with self.assertRaisesRegex(ValueError,"another source"):self.result()

    def test_handoff_shares_scope_without_dumping_object_list(self):
        with patch("source_study_object_scope.scope_for_plan",return_value=self.result()):
            store=type("StoreFixture",(),{"config":{"planning_context":{"opened_diagnostic_dates":self.dates}}})()
            value=finding_for_parent(store,{"source":{"raw_manifest_sha256":"a"*64}})
        self.assertEqual(value["parent_requested_scope"]["manifest_unbound_files"],1)
        self.assertNotIn("unbound_inventory_objects",value["parent_requested_scope"])
        self.assertIn("runner handoff correction",value["handoff_correction"])

    def test_local_completed_artifact_scope(self):
        root=Path(__file__).resolve().parents[1]/"artifacts/source-study-inventory-controller-20260911-01"
        if not (root/"session/assessment.json").exists():self.skipTest("local evidence not committed")
        result=audit(root)
        self.assertEqual(result["scope"]["requested_files"],122)
        self.assertEqual(result["scope"]["removed_file_count"],0)
        self.assertEqual(result["scope"]["manifest_bound_files"],1)
        self.assertEqual(result["scope"]["manifest_unbound_files"],121)
        self.assertIsNotNone(result["binding_guard_error"])
        self.assertFalse(result["execution_admitted"])


if __name__=="__main__":unittest.main()
