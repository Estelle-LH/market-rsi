import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from finding_aliases import alias_findings
from market_rsi import digest
from prepare_temporal_feedback import unalias, checked_result, prepare
from prepare_source_study_revision_workspace import merge_findings


class FeedbackTests(unittest.TestCase):
    def test_preserve_every_original_and_prior_roles(self):
        original=[{"id":"old","evidence":[1,2]}, {"id":"budget","amount":"old"}]
        previous=alias_findings(original); saved=copy.deepcopy(previous)
        merged=merge_findings(unalias(previous),[{"id":"review","issues":[1]},{"id":"budget","amount":"new"}],"a"*64)
        current=alias_findings(merged)
        self.assertEqual(previous,saved)
        self.assertEqual(current[0]["source_finding"],original[0])
        self.assertEqual(current[1]["source_finding"]["amount"],"old")
        self.assertEqual(current[3]["source_finding"]["amount"],"new")
        self.assertEqual(len(current),4)

    def test_reject_tampered_or_malformed_aliases(self):
        values=alias_findings([{"id":"one","fact":1}])
        for key,value in (("id","f002"),("source_finding",{"id":"one","fact":2})):
            bad=copy.deepcopy(values);bad[0][key]=value
            with self.assertRaises(ValueError):unalias(bad)
        with self.assertRaises(ValueError):unalias([])
        with self.assertRaises(ValueError):unalias([{"id":"plain"}])

    def test_reject_result_tampering(self):
        value={"fact":1};sha=digest(value);value["result_sha256"]=sha
        with patch("prepare_temporal_feedback.load_json",return_value=value):
            self.assertEqual(checked_result("unused",sha),value)
            value["fact"]=2
            with self.assertRaises(ValueError):checked_result("unused",sha)

    def test_never_reuse_existing_workspace(self):
        with tempfile.TemporaryDirectory() as t,patch("prepare_temporal_feedback.require_budget_resident") as guard:
            with self.assertRaisesRegex(ValueError,"fresh feedback"):prepare(Path(t))
            guard.assert_not_called()


if __name__=="__main__":unittest.main()
