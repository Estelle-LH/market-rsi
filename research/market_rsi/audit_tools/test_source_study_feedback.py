import copy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from market_rsi import digest
from source_study_feedback import validate
from prepare_source_study_revision_workspace import prepare


class FeedbackTests(unittest.TestCase):
    def test_bound_review_no_admission(self):
        v={"schema":"source_study_independent_feedback_v1","parent_manifest_sha256":"p",
            "source_admitted":False,"fits":0,"new_market_data_read":False,"provider_calls":0,
            "review_origin":"human_directed_independent_review","proposal":{"path":"plan","sha256":"a"},
            "audit_ref":{"path":"audit","sha256":"a"},"parent_archive":{"path":"archive","sha256":"a"}}
        v["result_sha256"]=digest(v); parent=SimpleNamespace(expected="p")
        with patch("source_study_feedback.current",return_value=v["proposal"]),patch("source_study_feedback.file_hash",return_value="a"):
            validate(v,parent)
            for key,value in [("parent_manifest_sha256","wrong"),("source_admitted",True),("fits",1),("provider_calls",1),("new_market_data_read",True)]:
                bad=copy.deepcopy(v);bad[key]=value
                bad["result_sha256"]=digest({k:x for k,x in bad.items() if k!="result_sha256"})
                with self.assertRaises(ValueError):validate(bad,parent)
            with patch("source_study_feedback.file_hash",return_value="changed"):
                with self.assertRaises(ValueError):validate(v,parent)
            with patch("source_study_feedback.current",return_value=None):
                with self.assertRaises(ValueError):validate(v,parent)

    def test_fresh_workspace_before_any_prepare(self):
        with tempfile.TemporaryDirectory() as t,patch("prepare_source_study_revision_workspace.Store") as store:
            with self.assertRaisesRegex(ValueError,"fresh revision"):
                prepare(Path(t)/"parent","a",Path(t)/"feedback",Path(t))
            store.assert_not_called()


if __name__=="__main__":unittest.main()
