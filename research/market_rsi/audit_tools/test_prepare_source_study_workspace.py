import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from market_rsi import digest
from prepare_source_study_workspace import prepare, verify_planning_canary


class SourceStudyPreparationTests(unittest.TestCase):
    def value(self):
        v = {"schema": "source_study_codex_canary_v1", "passed": True, "actual_codex_cli": True,
            "actual_tinker_calls": 0, "fits": 0, "source_admitted": False, "model_authorship_proven": False,
            "tool_calls": 6, "source_hashes": {"test": "a"*64}}
        v["result_sha256"] = digest(v); return v

    def test_exact_source_passing_zero_paid_canary_required(self):
        v = self.value()
        with patch("prepare_source_study_workspace.source_hashes", return_value=v["source_hashes"]):
            verify_planning_canary(v, {"source_hashes": v["source_hashes"]})
            for key, value in [("actual_tinker_calls", 1), ("tool_calls", 5), ("source_admitted", True), ("fits", 1), ("passed", False)]:
                bad = copy.deepcopy(v); bad[key] = value
                bad["result_sha256"] = digest({k: x for k, x in bad.items() if k != "result_sha256"})
                with self.assertRaises(ValueError): verify_planning_canary(bad, {"source_hashes": v["source_hashes"]})
            with self.assertRaises(ValueError): verify_planning_canary(v, {"source_hashes": {"test": "b"*64}})

    def test_existing_workspace_never_prepared_again(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch("prepare_source_study_workspace.read_bundle") as read:
                with self.assertRaisesRegex(ValueError, "fresh source-study"):
                    prepare(Path(temp), Path(temp)/"release", Path(temp)/"canary")
                read.assert_not_called()


if __name__ == "__main__": unittest.main()
