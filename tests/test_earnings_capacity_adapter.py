"""Real native selection/journal on human-authored literal earnings fixtures."""
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import unittest

import earnings_capacity_adapter as a
from supervisor_harness import test_research_capacity_activation as legacy
from supervisor_harness.continuous_discovery_batch import ContinuousDiscoveryBatch
from supervisor_harness import research_capacity_identity as identity
from market_rsi import digest

BASE, sha = legacy.BASE, legacy.sha


class EarningsCapacityTests(legacy.CapacityActivationTests):
    # Reuse artifact/receipt helpers only; inherited execution tests are disabled
    # below since they expect executable legacy modules rather than literals.
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.files = {"kernel.py": "pass\n", "candidate.py": "pass\n", "python": "fixture-runtime\n",
            "researcher_v1.py": "PROFILE = {'axis':'R','research_instructions':'','reuse_facts':True}\n",
            "researcher_v2.py": "PROFILE = {'axis':'R','research_instructions':'Verify signs with calculate','reuse_facts':True}\n",
            "harness_v1.py": "PROFILE = {'axis':'H','read_chunk_limit':20000,'search_hit_limit':50}\n",
            "harness_v2.py": "PROFILE = {'axis':'H','read_chunk_limit':1000,'search_hit_limit':50}\n"}
        for name, text in self.files.items():
            (self.root / name).write_text(text)
        source = lambda name: {"sources": {name: sha(self.files[name])}, "configuration_sha256": sha("fixed")}
        self.args = dict(kernel=source("kernel.py"), predictor=source("candidate.py"),
            harness=source("harness_v1.py"), researcher=source("researcher_v1.py"), memory=sha("empty"),
            model={"requested_model":"gpt-6.1-sol","serving_snapshot":"unknown","serving_snapshot_verified":False},
            runtime={"python":{"path":str(self.root/"python"),"sha256":sha(self.files["python"])},"dependencies":{}})
        self.before = identity.manifest(**self.args)
        self.entry = {"R":"researcher_v1.py","H":"harness_v1.py"}
        self.batch = ContinuousDiscoveryBatch(self.root / "batch", allow_temporary=True,
            test_clock=lambda: BASE, allow_test_clock=True)
        self.batch.initialize(batch_id="earnings-profile-fixture",start_utc=BASE,deadline_utc=BASE+timedelta(hours=1),
            max_attempts=3,active_pool_capacity=2,learning_checkpoint_version=1,
            initial_incumbent={"candidate_id":"baseline","candidate_sha256":self.before["C"],
                              "scorecard_sha256":sha("card"),"review_sha256":"0"*64})
        self.config = {"pair":a.activation.pair(self.before),"fixed_context":{
            "model_sha256":self.before["M"],"evaluation_sha256":self.before["K"],"data_scope_sha256":sha("public"),
            "authority_sha256":sha("offline"),"resource_policy_sha256":sha("zero-paid")},
            "allowed_write_paths":{"researcher":["researcher_v1.py","researcher_v2.py"],
                                   "harness":["harness_v1.py","harness_v2.py"]},
            "protected_paths":["kernel.py","candidate.py","python"],"reviewer_id":"independent-auditor"}
        self.batch.record_micro_evolution("initialize",self.config,expected_state_sha256=self.batch.snapshot()["state_sha256"])
        self.adapter = self.restore()
        self.count = 0

    def restore(self):
        return a.EarningsCapacity(self.batch,source_root=self.root,registry_root=self.root/"versions",
                                  baseline=self.before,entrypoints=self.entry)

    def propose(self, axis, before=None, *, component=None):
        before = before or self.before
        args = deepcopy(self.args)
        args["harness"], args["researcher"] = before["components"]["H"], before["components"]["R"]
        kind = {"R":"researcher","H":"harness"}[axis]
        name = kind + "_v2.py"
        args[kind] = {"sources":{name:sha(self.files[name])},"configuration_sha256":sha("fixed")}
        after = identity.manifest(**args)
        entries = {k:next(iter(after["components"][k]["sources"])) for k in ("R","H")}
        state = self.batch.snapshot()
        proposal = {"candidate_id":axis+"-v2","proposer_id":"fixture-author","axis":kind,
            "component":component or ("research_policy" if axis=="R" else "tool_interface"),
            "behavior_change":"Fixture selected profile reaches worker","problem_evidence_sha256":sha("fixture gap"),
            "parent_pair_sha256":digest(state["micro_evolution"]["active_pair"]),"pair":a.activation.pair(after),
            "fixed_context":self.config["fixed_context"],"write_paths":list(before["components"][axis]["sources"])+[name],
            "patch_sha256":a.activation.patch_digest(before,after)}
        scope = self.artifact({"passed":True,"reviewer_id":"independent-auditor","proposer_id":"fixture-author",
                              "identity_sha256":digest(after),"entrypoints":entries})
        self.adapter.propose(after,proposal,entries,static_review=scope,expected_state_sha256=state["state_sha256"])
        return before,after

    def review_receipt(self, before, after, *, accept=True):
        state = self.batch.snapshot(); pending = state["micro_evolution"]["pending"]
        active = digest(state["micro_evolution"]["active_pair"])
        axis = "R" if pending["axis"] == "researcher" else "H"
        old = self.adapter.resolve(axis,expected_pair_sha256=active)
        new = self.adapter.resolve(axis,expected_pair_sha256=active,shadow_proposal_sha256=pending["record_sha256"])
        self.assertNotEqual(old["profile"],new["profile"])
        bound = {"proposal_sha256":pending["record_sha256"],"before_identity_sha256":digest(before),
            "after_identity_sha256":digest(after),"tested_pair_sha256":digest(pending["pair"]),
            "anchor_pair_sha256":digest(state["micro_evolution"]["anchor_pair"])}
        evidence = self.artifact({"synthetic":True,"outputs":{"old":old,"new":new},"binding":bound,
            "checks":{k:True for k in a.activation.micro.MICRO_CHECKS}})
        benefit = self.artifact({"proposal_sha256":pending["record_sha256"],"before_identity_sha256":digest(before),
            "after_identity_sha256":digest(after),"matched_outputs_sha256":evidence["sha256"],
            "effect":pending["behavior_change"],"benefit_observed":True})
        review = {"reviewer_id":"independent-auditor","proposal_sha256":pending["record_sha256"],
            "decision":"accept" if accept else "reject","reason":"Fixture-only hook compatibility",
            "tested_pair_sha256":digest(pending["pair"]),"anchor_pair_sha256":bound["anchor_pair_sha256"],
            "checks":{k:{"passed":True,"evidence_sha256":evidence["sha256"]} for k in a.activation.micro.MICRO_CHECKS},
            "benefit_observed":True,"benefit_evidence_sha256":benefit["sha256"],"actual_write_paths":pending["write_paths"]}
        return self.artifact({"review":review,"evidence":{evidence["sha256"]:evidence["path"],benefit["sha256"]:benefit["path"]}})

    def test_earnings_R_then_H_selected_hook_cold_restart_and_rollback(self):
        before, r = self.propose("R")
        self.adapter.review(self.review_receipt(before,r),expected_state_sha256=self.batch.snapshot()["state_sha256"])
        _, h = self.propose("H",r)
        self.adapter.review(self.review_receipt(r,h),expected_state_sha256=self.batch.snapshot()["state_sha256"])
        selected = digest(a.activation.pair(h))
        packet = self.restore().prepare(expected_pair_sha256=selected,questions="fixture questions",
                                       state_message={"role":"user","content":"verified fixture facts"})
        self.assertEqual(packet["tool_bounds"]["read_chunk_limit"],1000)
        self.assertEqual(packet["messages"][1]["content"],"Verify signs with calculate")
        self.assertEqual(packet["messages"][2]["content"],"verified fixture facts")
        self.assertTrue(all(x["selected_pair_sha256"]==selected and not x["model_code_executed"] for x in packet["receipts"]))
        state = self.batch.snapshot()
        check = self.artifact({"passed":True,"from_pair":state["micro_evolution"]["active_pair"],
            "to_pair":state["micro_evolution"]["previous_pair"],"before_state_sha256":state["state_sha256"]})
        receipt = self.artifact({"receipt":{"reviewer_id":"independent-auditor","reason":"fixture rollback",
            "evidence_sha256":check["sha256"]},"evidence":check})
        self.adapter.rollback(receipt,expected_state_sha256=state["state_sha256"])
        self.assertEqual(self.restore().resolve("H",expected_pair_sha256=digest(a.activation.pair(r)))["profile"]["read_chunk_limit"],20000)
        self.assertEqual(len(self.batch.snapshot()["micro_evolution"]["history"]),3)

    def test_earnings_reject_keeps_parent_and_history(self):
        before, after = self.propose("R")
        self.adapter.review(self.review_receipt(before,after,accept=False),expected_state_sha256=self.batch.snapshot()["state_sha256"])
        self.assertEqual(self.batch.snapshot()["micro_evolution"]["active_pair"],a.activation.pair(before))
        self.assertEqual(len(self.batch.snapshot()["micro_evolution"]["history"]),1)

    def test_earnings_stale_pair_and_source_drift_refused(self):
        with self.assertRaises(ValueError):
            self.adapter.resolve("R",expected_pair_sha256="a"*64)
        (self.root/"researcher_v1.py").write_text("import os\n")
        with self.assertRaises(ValueError):
            self.adapter.resolve("R",expected_pair_sha256=digest(a.activation.pair(self.before)))

    def test_earnings_wrong_component_refused_before_journal_proposal(self):
        with self.assertRaisesRegex(ValueError,"One named earnings"):
            self.propose("H",component="feedback_delivery")
        self.assertIsNone(self.batch.snapshot()["micro_evolution"]["pending"])


# Do not collect legacy executable-module tests under this subclass. They run
# separately unchanged below; only the three explicit earnings tests belong here.
for _name in dir(legacy.CapacityActivationTests):
    if _name.startswith("test_"):
        setattr(EarningsCapacityTests, _name, None)


class LiteralAdmissionTests(unittest.TestCase):
    def chosen(self, axis="R",component="research_policy"):
        return a.decision({"schema":"earnings_capacity_decision_v1","axis":axis,"component":component,
            "parent_pair_sha256":"a"*64,"feedback_sha256":"b"*64,"hypothesis":"Use verified signs",
            "expected_effect":"Fewer invented numbers"},parent_pair_sha256="a"*64,feedback_sha256="b"*64)

    def test_typed_decision_continue_and_unsupported_scope(self):
        self.assertEqual(self.chosen("continue","none")["axis"],"continue")
        for axis,component in (("K","scorer"),("H","network"),("R","new_provider")):
            with self.assertRaises(ValueError): self.chosen(axis,component)
        choice=self.chosen();choice["feedback_sha256"]="c"*64
        with self.assertRaises(ValueError):
            a.decision(choice,parent_pair_sha256="a"*64,feedback_sha256="b"*64)

    def test_literal_author_source_and_cases_bind_exact_decision(self):
        choice=self.chosen()
        old={"axis":"R","research_instructions":"","reuse_facts":True}
        source="PROFILE = {'axis':'R','research_instructions':'Check signs','reuse_facts':True}"
        authored={"decision_sha256":digest(choice),"source_text":source,
                  "test_text":"CASES = [{'field':'research_instructions','expected':'Check signs'}]"}
        decoded=a.author_candidate(authored,old,choice)
        self.assertEqual(decoded["profile"]["research_instructions"],"Check signs")
        self.assertFalse(decoded["tests_executed"])
        for update in ({"decision_sha256":"c"*64},{"test_text":"import os"},
                       {"test_text":"CASES=[]"},{"source_text":source.replace("True","False")}):
            with self.assertRaises(ValueError): a.author_candidate(dict(authored,**update),old,choice)

    def test_malicious_AST_and_bounds_never_execute(self):
        for text in ("import os\nPROFILE={}","PROFILE=__import__('os').system('false')",
                     "PROFILE={}\nopen('/tmp/should-not-exist','w')", "PROFILE={'axis':'K'}"):
            with self.assertRaises((ValueError,SyntaxError)):
                a.profile(text.encode(),"R")
        for value in ({"axis":"H","read_chunk_limit":20001,"search_hit_limit":50},
                      {"axis":"H","read_chunk_limit":True,"search_hit_limit":50},
                      {"axis":"H","read_chunk_limit":1000,"search_hit_limit":51}):
            with self.assertRaises(ValueError): a.profile(("PROFILE="+repr(value)).encode(),"H")


if __name__ == "__main__": unittest.main()
