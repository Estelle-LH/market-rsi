import unittest
from source_inventory_context import summarize, finding, INVENTORY


class InventoryContextTests(unittest.TestCase):
    def value(self):
        return {"schema":"capture_raw_file_inventory_v1","host":"173.255.231.4",
            "source_root":"/opt/d10/raw/data/polymarket","source_admitted":False,
            "complete_content_verified":False,"raw_rows_read":0,
            "days":[{"date":"2026-08-21","files_present":1,"compressed_bytes":10},
                    {"date":"2026-08-22","files_present":0,"compressed_bytes":0}],
            "files":[{"date":"2026-08-21","filename":"polymarket-20260821T00.jsonl.zst","compressed_bytes":10}]}

    def test_missing_does_not_become_complete_or_outage(self):
        v=summarize(self.value(),["2026-08-21","2026-08-22"])
        self.assertEqual(v["no_files_observed_dates"],["2026-08-22"])
        self.assertFalse(v["complete_sessions_proven"]);self.assertFalse(v["source_admitted"])

    def test_wrong_source_scope_or_admission_rejected(self):
        for key,value in [("source_root","wrong"),("host","wrong"),("source_admitted",True),("raw_rows_read",1)]:
            v=self.value();v[key]=value
            with self.assertRaises(ValueError):summarize(v,["2026-08-21","2026-08-22"])
        with self.assertRaises(ValueError):summarize(self.value(),["2026-08-21","2026-08-26"])

    def test_bad_counts_duplicate_or_invalid_files_rejected(self):
        variants=[]
        v=self.value();v["days"][0]["files_present"]=2;variants.append(v)
        v=self.value();v["days"][0]["compressed_bytes"]=11;variants.append(v)
        v=self.value();v["files"]*=2;variants.append(v)
        v=self.value();v["files"][0]["filename"]="polymarket-20260821T99.jsonl.zst";variants.append(v)
        v=self.value();v["files"][0]["compressed_bytes"]=True;variants.append(v)
        for v in variants:
            with self.assertRaises(ValueError):summarize(v,["2026-08-21","2026-08-22"])

    @unittest.skipUnless(INVENTORY.is_file(), "Local frozen metadata integration check")
    def test_real_pinned_metadata_only_inventory(self):
        # This is a check of existing small metadata, not an empirical data run.
        v=finding({"source_id":"d10_polymarket_raw","opened_diagnostic_dates":
            ["2026-08-21","2026-08-22","2026-08-23","2026-08-24","2026-08-25","2026-09-07","2026-09-08","2026-09-09"]})
        self.assertEqual(v["inventory"]["files_observed"],122)
        self.assertEqual(v["inventory"]["compressed_bytes_observed"],11889232674)
        self.assertEqual(v["inventory"]["no_files_observed_dates"],["2026-08-23","2026-08-24"])


if __name__=="__main__":unittest.main()
