"""Preflight fixtures only; never construct a provider backend."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import json
from data_scientist_harness import fixtures
from data_scientist_harness import run_controller as r
from data_scientist_harness.store import Store
from market_rsi import digest,file_hash,fresh_json,load_json
from paid_budget import PaidBudget
from data_scientist_harness import VERSION
from data_scientist_harness.release import TAG, ORIGIN, CHANGE_ORIGIN


class DispatcherTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.base=Path(self.tmp.name).resolve()
        self.root=self.base/"research"; fixtures.workspace(self.root)
        value=load_json(self.root/"workspace.json"); value["purpose"]="opened_train_research"
        (self.root/"workspace.json").write_text(json.dumps(value)); self.sha=file_hash(self.root/"workspace.json")
        self.canary=self.base/"canary"; tested=fixtures.workspace(self.canary)
        (self.canary/"session").mkdir()
        self.assessment=self.canary/"session/assessment.json"
        fresh_json(self.assessment,{"valid":True,"evidence_mode":"synthetic_transport_fixture",
            "process_reaped":True,"turns":18,"tool_calls":18,"model_authorship_proven":False})
        self.binary=self.base/"codex-fixture"; self.binary.write_text("Unit fixture, never executed")
        self.canary_file=self.canary/"canary.json"
        self.proof={"schema":"data_scientist_codex_canary_v1","passed":True,"actual_tinker_calls":0,
            "source_hashes":r.source_hashes(Store(self.root,self.sha)),"manifest_sha256":tested,
            "assessment_sha256":file_hash(self.assessment),"codex_sha256":file_hash(self.binary)}
        self.seal()
        self.publication={"origin":ORIGIN,"tag":TAG,"commit":"a"*40,"tag_object":"b"*40,
                          "tree":"c"*40,"checked_utc":"synthetic fixture","source_prefix":"research/market_rsi"}
        release={"schema":"data_scientist_release_v1","harness_version":VERSION,
                 "harness_change_origin":CHANGE_ORIGIN,
                 "source_hashes":self.proof["source_hashes"],"runtime":value["runtime"],
                 "publication":self.publication,"canary":{"sha256":file_hash(self.canary_file)}}
        release["release_sha256"]=digest(release)
        value["release"]=release
        (self.root/"workspace.json").write_text(json.dumps(value)); self.sha=file_hash(self.root/"workspace.json")
        self.budget=PaidBudget.create(self.base/"budget",{"experiment_id":"unit-budget","cap_usd":"200",
            "target_usd":"200","buckets_usd":{"learning":"200"},"authority":"Unit test only; no execution or spend."})

    def tearDown(self): self.tmp.cleanup()

    def seal(self):
        self.proof.pop("result_sha256",None); self.proof["result_sha256"]=digest(self.proof)
        self.canary_file.write_text(json.dumps(self.proof))

    def check(self):
        with patch.object(r.harness,"CODEX",self.binary), \
             patch.object(r,"verify_git_publication",return_value=self.publication):
            return r.paid_preflight(self.root,self.sha,self.base/"budget",
                file_hash(self.base/"budget/authorization.json"),self.canary_file)

    def test_preflight_is_read_only_not_spending(self):
        result=self.check()
        self.assertFalse(result["new_dev_test_admitted"])
        self.assertEqual(self.budget.snapshot()["metered_usd"],"0")
        self.assertFalse((self.root/"dispatch-claim.json").exists())

    def test_active_dispatch_prevents_duplicate(self):
        self.budget.reserve("unit-turn-001","learning","1","unit","a"*64)
        self.budget.dispatch("unit-turn-001")
        with self.assertRaisesRegex(ValueError,"active or unresolved"): self.check()

    def test_reserved_bound_is_not_actual_spend(self):
        self.budget.reserve("held","learning","199","unit","a"*64)
        with self.assertRaisesRegex(ValueError,"exceeds available"): self.check()
        self.assertEqual(self.budget.snapshot()["metered_usd"],"0")

    def test_claim_is_permanent(self):
        fresh_json(self.root/"dispatch-claim.json",{"unit":True})
        with self.assertRaisesRegex(ValueError,"no ID reuse"): self.check()

    def test_unpublished_version_cannot_start_paid_dispatch(self):
        value=load_json(self.root/"workspace.json"); value["release"]=None
        (self.root/"workspace.json").write_text(json.dumps(value)); self.sha=file_hash(self.root/"workspace.json")
        with self.assertRaisesRegex(ValueError,"published harness release required"):
            self.check()
        self.assertFalse((self.root/"dispatch-claim.json").exists())
        self.assertEqual(self.budget.snapshot()["metered_usd"],"0")

    def test_remote_check_failure_happens_before_any_dispatch(self):
        with patch.object(r.harness,"CODEX",self.binary), \
             patch.object(r,"verify_git_publication",side_effect=RuntimeError("remote unavailable")):
            with self.assertRaisesRegex(RuntimeError,"remote unavailable"):
                r.paid_preflight(self.root,self.sha,self.base/"budget",
                    file_hash(self.base/"budget/authorization.json"),self.canary_file)
        self.assertFalse((self.root/"dispatch-claim.json").exists())
        self.assertEqual(self.budget.snapshot()["metered_usd"],"0")

    def test_canary_source_mismatch_rejected(self):
        self.proof["source_hashes"]={}; self.seal()
        with self.assertRaisesRegex(ValueError,"exact-code"): self.check()

    def test_failure_even_with_resealed_assessment_rejected(self):
        value=load_json(self.assessment); value["valid"]=False
        self.assessment.write_text(json.dumps(value))
        self.proof["assessment_sha256"]=file_hash(self.assessment); self.seal()
        with self.assertRaisesRegex(ValueError,"terminal proof differs"): self.check()


if __name__=="__main__": unittest.main()
