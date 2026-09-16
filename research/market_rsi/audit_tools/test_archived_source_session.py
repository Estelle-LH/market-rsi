import copy
from pathlib import Path
import tempfile
import unittest
from market_rsi import digest, file_hash, fresh_json, load_json
from archived_source_session import ArchivedSourceSession
from prepare_temporal_workspace import prepare


def fixture(root):
    root.mkdir();(root/"code").mkdir();(root/"records").mkdir();(root/"session/turn-001").mkdir(parents=True)
    (root/"code/historical.py").write_text("raise RuntimeError('archived code must never run')\n")
    fresh_json(root/"findings.json",[{"id":"old-fact","value":"not admission"}])
    fresh_json(root/"archive-input.json",{"prior_rounds":[]})
    sources={"historical.py":file_hash(root/"code/historical.py")}
    release={"harness_version":"legacy-fixture","runtime":{"old":"environment"},
        "harness_change_origin":"human_directed_engineering","source_hashes":sources,
        "publication":{"origin":"https://github.com/Estelle-LH/RSIBench-Data.git"}}
    release["release_sha256"]=digest(release)
    files={str(p):file_hash(p) for p in (root/"code/historical.py",root/"findings.json",root/"archive-input.json")}
    config={"schema":"data_scientist_workspace_v1","session_id":root.name,"purpose":"source_research",
        "inputs_present":False,"allowed_train_dates":[],"formal_evaluation_allowed":False,"paid_execution_tools":False,
        "release":release,"harness_version":"legacy-fixture","runtime":release["runtime"],
        "harness_change_origin":"human_directed_engineering","files":files}
    fresh_json(root/"workspace.json",config);manifest=file_hash(root/"workspace.json")
    rid={"release_sha256":release["release_sha256"]}
    proposal={"manifest_sha256":manifest,"proposal":{"test":"exact original"}}
    proposal["proposal_sha256"]=digest(proposal);fresh_json(root/"source-study-proposal.json",proposal)
    ref={"path":str(root/"source-study-proposal.json"),"sha256":file_hash(root/"source-study-proposal.json")}
    fresh_json(root/"research-trace.json",{"trials":[]});(root/"research-trace.md").write_text("No fits\n")
    trace={"json_sha256":file_hash(root/"research-trace.json"),"markdown_sha256":file_hash(root/"research-trace.md")}
    decision={"action":"defer","source_study_proposal":ref,"research_trace":trace}
    fresh_json(root/"submitted-decision.json",decision)
    steps=[("propose_source_study",proposal["proposal"],{"proposal":ref}),
           ("submit_research_decision",{},dict(decision,bytes=1))]
    events=[]
    for i,(tool,args,result) in enumerate(steps,1):
        path=root/"records"/f"{i:04d}.json"
        fresh_json(path,{"tool":tool,"arguments":args,"result":result,"status":"ok","harness_release":rid})
        event={"sequence":i,"previous":events[-1]["record_sha256"] if events else None,"tool":tool,
            "record":{"path":str(path),"sha256":file_hash(path)}}
        event["record_sha256"]=digest(event);events.append(event)
    import json
    (root/"activity.jsonl").write_text("".join(json.dumps(e)+"\n" for e in events))
    archive={"schema":"data_scientist_round_archive_v1","manifest_sha256":manifest,"decision":decision,
        "pre_submission_activity":events[:-1],"current_findings":load_json(root/"findings.json"),
        "trial_summaries":[],"research_trace":trace}
    fresh_json(root/"round-archive.json",archive)
    assessment={"manifest_sha256":manifest,"exit_code":0,"valid":True,"process_reaped":True,
        "evidence_mode":"paid_controller","source_hashes":sources,"harness_release":rid,
        "unresolved_accounting":[],"tool_calls":2,"turns":1}
    fresh_json(root/"session/assessment.json",assessment)
    response=root/"session/turn-001/response.json";fresh_json(response,{"receipt":{"metered_cost_usd":"0.2"}})
    job_id=root.name+"-turn-001";job={"state":"metered_terminal","metered_usd":"0.2"}
    audit={"workspace":str(root),"manifest_sha256":manifest,"controller_valid":True,"process_reaped":True,
        "fits_completed":0,"integrity_and_cost_check_passed":True,"assessment_sha256":file_hash(root/"session/assessment.json"),
        "harness_release":rid,"tools":[{"tool":t,"status":"ok","count":1} for t,_,_ in steps],
        "decision_sha256":file_hash(root/"submitted-decision.json"),"decision":decision,
        "turns":[dict(job,job_id=job_id,response_sha256=file_hash(response))],"session_metered_usd":"0.2","session_uncertain_upper_usd":"0"}
    audit["result_sha256"]=digest(audit);audit_path=root.parent/"audit.json";fresh_json(audit_path,audit)
    pins={"manifest":manifest,"proposal":ref["sha256"],"release":release["release_sha256"],
        "audit":audit["result_sha256"],"archive":file_hash(root/"round-archive.json")}
    return audit_path,{"jobs":{job_id:job}},pins


class ArchivedTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve()/"old-source"
        self.audit,self.budget,self.pins=fixture(self.root)

    def tearDown(self):self.temp.cleanup()

    def verify(self):return ArchivedSourceSession(self.root,self.audit,self.budget,self.pins)

    def test_legacy_read_without_running_or_rewriting_it(self):
        before={p:file_hash(p) for p in self.root.rglob("*") if p.is_file()}
        old=self.verify()
        self.assertEqual(old.receipt["old_version"],"legacy-fixture")
        self.assertFalse(old.receipt["old_runtime_executed"])
        self.assertFalse(hasattr(old,"save"))
        self.assertEqual(before,{p:file_hash(p) for p in before})

    def test_source_tampering_rejected(self):
        (self.root/"code/historical.py").write_text("pass\n")
        with self.assertRaisesRegex(ValueError,"hash differs"):self.verify()

    def test_receipt_tampering_rejected(self):
        (self.root/"records/0001.json").write_text("{}")
        with self.assertRaisesRegex(ValueError,"hash differs"):self.verify()

    def test_outside_event_reference_rejected(self):
        import json
        path=self.root/"activity.jsonl";events=[json.loads(x) for x in path.read_text().splitlines()]
        events[0]["record"]["path"]=str(self.root.parent/"outside.json")
        events[0]["record_sha256"]=digest({k:v for k,v in events[0].items() if k!="record_sha256"})
        path.write_text("".join(json.dumps(e)+"\n" for e in events))
        with self.assertRaisesRegex(ValueError,"event chain"):self.verify()

    def test_active_or_changed_cost_rejected(self):
        job=next(iter(self.budget["jobs"].values()))
        for key,value in (("state","dispatched"),("metered_usd","0.3")):
            previous=job[key];job[key]=value
            with self.assertRaisesRegex(ValueError,"provider cost"):self.verify()
            job[key]=previous

    def test_injected_archive_rejected(self):
        path=self.root/"round-archive.json";value=load_json(path);value["current_findings"]=[]
        path.write_text(__import__("json").dumps(value))
        self.pins["archive"]=file_hash(path)
        with self.assertRaisesRegex(ValueError,"archive differs"):self.verify()

    def test_wrong_version_binding_rejected(self):
        path=self.root/"workspace.json";value=load_json(path);value["harness_version"]="new-version"
        path.write_text(__import__("json").dumps(value));self.pins["manifest"]=file_hash(path)
        with self.assertRaisesRegex(ValueError,"release binding"):self.verify()

    def test_existing_output_is_never_reused(self):
        with self.assertRaisesRegex(ValueError,"fresh cross-version"):prepare(self.root)


if __name__=="__main__":unittest.main()
