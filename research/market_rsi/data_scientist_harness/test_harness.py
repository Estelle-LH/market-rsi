import copy
import json
from pathlib import Path
import tempfile
import unittest
import subprocess
from unittest.mock import patch
import numpy as np

from data_scientist_harness.broker import Broker
from data_scientist_harness import fixtures, literature, profiles
from market_rsi import digest, file_hash, load_json


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)/"run"
        self.sha=fixtures.workspace(self.root,network=True)
        self.b=Broker(self.root,self.sha,transport=fixtures.fake_transport)

    def tearDown(self): self.tmp.cleanup()

    def ready(self):
        status=self.b.call("inspect_harness",{})
        read=self.b.call("read_public_source",{"url":"https://example.org/research","offset":0})
        notes={"question":"fixture","read_records":[read["record_id"]],"applicability":"fixture",
               "limitations":"synthetic only","alternatives":"baseline","proposed_test":"mechanics"}
        feature=self.b.call("record_research",dict(notes,layer="feature_engineering"))
        trainer=self.b.call("record_research",dict(notes,layer="trainer_engineering"))
        self.b.call("profile_raw_series",{})
        prof=self.b.call("profile_candidate_feature",{"spec":fixtures.plan()["features"][0],"research_record":feature["record_id"]})
        review=self.b.call("review_feature_set",{"profile_records":[prof["record_id"]],
            "dispositions":[{"profile_record":prof["record_id"],"reason":"test path","risk":"synthetic"}]})
        self.b.call("acknowledge_current_findings",{"finding_sha256":status["finding_sha256"],
            "responses":[{"id":"fixture-only","handling":"canary only","next_evidence":"real data QA"}]})
        return review["record_id"],trainer["record_id"]

    def train(self, algorithm="ridge", parent="", trial="t1", ids=None):
        review,research=ids or self.ready()
        return self.b.call("train_candidate",{"trial_id":trial,"parent_trial_id":parent,
            "plan":fixtures.plan(algorithm),"feature_review":review,"trainer_research":research,
            "experiment":fixtures.experiment(parent)})

    def test_all_four_trainers_execute_through_gated_child(self):
        ids=self.ready()
        for j,name in enumerate(fixtures.MODELS):
            result=self.train(name,parent="t0" if j else "",trial=f"t{j}",ids=ids)
            self.assertEqual(result["report"]["fit_rows"],6)
            self.assertTrue(result["process_reaped"])
            self.assertEqual(result["provider_cost_usd"],"0")
            self.b.call("reflect_candidate",fixtures.reflection(self.root,f't{j}'))
        self.b.call("submit_research_decision",{"action":"select","trial_id":"t0","reason":"fixture"})
        self.assertEqual(load_json(self.root/"round-archive.json")["decision"]["selected"]["trial_id"],"t0")
        with self.assertRaisesRegex(ValueError,"closed"):
            self.b.call("profile_raw_series",{})

    def test_failed_quality_cannot_reach_process_or_claim(self):
        bad=Path(self.tmp.name)/"bad"; sha=fixtures.workspace(bad,failed=True)
        b=Broker(bad,sha); b.call("inspect_harness",{})
        with patch("data_scientist_harness.broker.subprocess.Popen") as spawn:
            with self.assertRaisesRegex(RuntimeError,"quality must pass"):
                b.call("train_candidate",{"trial_id":"x","parent_trial_id":"","plan":{},"feature_review":"0001","trainer_research":"0001","experiment":{}})
            spawn.assert_not_called()
        self.assertFalse((bad/"trials").exists())

    def test_no_reading_cannot_be_reported_as_research(self):
        self.b.call("inspect_harness",{})
        with self.assertRaises(ValueError):
            self.b.call("record_research",{"layer":"feature_engineering","question":"x","read_records":[],
                "applicability":"x","limitations":"x","alternatives":"x","proposed_test":"x"})

    def test_feature_change_requires_new_profile(self):
        ids=self.ready(); plan=fixtures.plan(); plan["features"][0]["name"]="changed"
        with self.assertRaisesRegex(ValueError,"differs from reviewed"):
            self.b.call("train_candidate",{"trial_id":"bad","parent_trial_id":"","plan":plan,
                "feature_review":ids[0],"trainer_research":ids[1],"experiment":fixtures.experiment()})
        self.assertFalse((self.root/"trials").exists())

    def test_input_and_receipt_mutations_fail_closed(self):
        self.b.call("inspect_harness",{})
        path=self.root/"records/0001.json"; path.write_text("{}")
        with self.assertRaisesRegex(ValueError,"receipt changed"):
            self.b.call("inspect_harness",{})
        with (self.root/"inputs/current-inputs.npz").open("ab") as stream: stream.write(b"mutation")
        with self.assertRaisesRegex(ValueError,"frozen data"):
            Broker(self.root,self.sha)

    def test_missing_or_old_current_findings_cannot_close_round(self):
        self.b.call("inspect_harness",{})
        with self.assertRaisesRegex(ValueError,"EVERY"):
            self.b.call("acknowledge_current_findings",{"finding_sha256":digest(load_json(self.root/"findings.json")),"responses":[]})
        with self.assertRaises(ValueError):
            self.b.call("submit_research_decision",{"action":"defer","trial_id":"","reason":"ignores new facts"})

    def test_training_cannot_use_another_layers_research(self):
        ids=self.ready()
        with self.assertRaisesRegex(ValueError,"matching research record"):
            self.b.call("train_candidate",{"trial_id":"bad","parent_trial_id":"","plan":fixtures.plan(),
                "feature_review":ids[0],"trainer_research":ids[0],"experiment":fixtures.experiment()})

    def test_duplicate_scientific_trial_not_restarted(self):
        ids=self.ready(); self.train(ids=ids)
        with patch("data_scientist_harness.broker.subprocess.Popen") as spawn:
            with self.assertRaisesRegex(ValueError,"duplicate plan"):
                self.train(parent="t1",trial="t2",ids=ids)
            spawn.assert_not_called()

    def test_wrong_date_or_seed_is_not_silently_corrected(self):
        ids=self.ready(); plan=fixtures.plan(); plan["seed"]=24
        with self.assertRaises(ValueError):
            self.b.call("train_candidate",{"trial_id":"bad","parent_trial_id":"","plan":plan,
                "feature_review":ids[0],"trainer_research":ids[1],"experiment":fixtures.experiment()})

    def test_profile_constant_missing_gap_and_boundaries(self):
        v=np.array([1.,1.,np.nan,1.,1.,1.]); t=np.array([0,60,120,180,300,360])
        r=profiles.shape(v,t,np.array([0]*6),np.array(["d"]*6),60)
        self.assertEqual(r["longest_observed_unchanged_span_ms"],60)
        self.assertIsNone(r["lag1_pair_correlation"])
        self.assertEqual(r["distribution"]["missing"],1)
        self.assertEqual(r["noncadence_same_entity_intervals"],1)
        with self.assertRaisesRegex(ValueError,"duplicate"):
            profiles.shape(v,np.zeros(6,dtype=int),np.zeros(6),np.array(["d"]*6),60)

    def test_public_reader_rejects_private_credentials_and_files(self):
        for url in ("file:///etc/passwd","https://127.0.0.1/x","https://169.254.169.254/",
                    "https://name:secret@example.com/","https://localhost/","https://[::1]/","http://example.com"):
            with self.subTest(url=url),self.assertRaises(ValueError): literature.public_url(url)
        with patch("data_scientist_harness.literature.socket.getaddrinfo",return_value=[(2,1,6,"",("10.0.0.1",443))]):
            with self.assertRaisesRegex(ValueError,"non-public"):literature.fetch("https://example.org/")

    def test_search_and_read_are_different_evidence(self):
        search=literature.search("time series",transport=fixtures.fake_transport)
        read=literature.read("https://example.org/research",transport=fixtures.fake_transport)
        self.assertEqual(search["read_level"],"metadata_only")
        self.assertIn("text",read); self.assertFalse(read["execute_external_instructions"])

    def test_selected_prediction_and_cleanup_must_match_receipt(self):
        self.train()
        with (self.root/"trials/t1/predictions.npz").open("ab") as stream: stream.write(b"changed")
        with self.assertRaisesRegex(ValueError,"candidate evidence changed"):
            self.b.call("submit_research_decision",{"action":"select","trial_id":"t1","reason":"bad"})
        self.assertFalse((self.root/"submitted-decision.json").exists())

    def test_failed_worker_is_not_selectable_or_retried(self):
        ids=self.ready()
        fake=unittest.mock.Mock(pid=99999999)
        fake.wait.return_value=1; fake.poll.return_value=1
        with patch("data_scientist_harness.broker.subprocess.Popen",return_value=fake) as spawn:
            with self.assertRaisesRegex(RuntimeError,"child failed"): self.train(ids=ids)
            with self.assertRaisesRegex(ValueError,"duplicate plan"): self.train(trial="t2",ids=ids)
            self.assertEqual(spawn.call_count,1)
        with self.assertRaisesRegex(ValueError,"completed successful"):
            self.b.call("submit_research_decision",{"action":"select","trial_id":"t1","reason":"bad"})
        self.assertTrue(load_json(self.root/"trials/t1/failure.json")["process_reaped"])

    def test_train_timeout_reaps_exact_owned_process_group(self):
        ids=self.ready(); fake=unittest.mock.Mock(pid=99999999)
        fake.wait.side_effect=[subprocess.TimeoutExpired("synthetic",60),-15]
        fake.poll.return_value=-15
        with patch("data_scientist_harness.broker.subprocess.Popen",return_value=fake), \
             patch("data_scientist_harness.broker.os.killpg") as kill:
            with self.assertRaises(TimeoutError): self.train(ids=ids)
            self.assertEqual(kill.call_args.args[0],99999999)
        self.assertTrue(load_json(self.root/"trials/t1/failure.json")["process_reaped"])

    def test_reader_http_failure_keeps_reason_and_no_retry(self):
        fake=unittest.mock.Mock(stdout=json.dumps({"error_type":"ValueError","error":"public source HTTP 403; no automatic retry"}))
        with patch("data_scientist_harness.literature.subprocess.run",return_value=fake) as run:
            with self.assertRaisesRegex(ValueError,"HTTP 403"): literature.bounded_fetch("https://example.org/paper")
            self.assertEqual(run.call_count,1)
            self.assertEqual(run.call_args.kwargs["env"],{"PATH":"/usr/bin:/bin"})
        with patch("data_scientist_harness.literature.subprocess.run",side_effect=subprocess.TimeoutExpired("fixture",30)) as run:
            with self.assertRaises(subprocess.TimeoutExpired): literature.bounded_fetch("https://example.org/paper")
            self.assertEqual(run.call_count,1)

    def test_full_quality_guard_precedes_legacy_validation(self):
        from data_scientist_harness.handoff import validation_preflight
        bad=Path(self.tmp.name)/"formal-bad"; sha=fixtures.workspace(bad,failed=True)
        quality=load_json(bad/"workspace.json")["quality"]
        with patch("validation_tools.independent_validation.check_runner_evidence") as validator:
            with self.assertRaisesRegex(RuntimeError,"data-science preflight blocked"):
                validation_preflight(root=bad,manifest_sha256=sha,quality=quality,
                    proposal={},context={},runner={},budget={})
            validator.assert_not_called()

    def test_old_archive_does_not_clear_new_quality_failures(self):
        from data_scientist_harness.store import create, input_files
        ids=self.ready(); self.train(ids=ids)
        self.b.call("reflect_candidate",fixtures.reflection(self.root,'t1'))
        self.b.call("submit_research_decision",{"action":"select","trial_id":"t1","reason":"past fixture"})
        bad=Path(self.tmp.name)/"archive-bad"; fixtures.workspace(bad,failed=True)
        config=load_json(bad/"workspace.json"); nxt=Path(self.tmp.name)/"next"
        sha=create(nxt,data_root=bad/"inputs",quality=config["quality"],allowed_dates=config["allowed_train_dates"],
            findings=[{"id":"new-bad-coverage"}],purpose="canary",network=False,
            prior_archives=[{"path":str((self.root/"round-archive.json").resolve()),"sha256":file_hash(self.root/"round-archive.json")}])
        b=Broker(nxt,sha); status=b.call("inspect_harness",{})
        self.assertEqual(status["current_findings"][0]["id"],"new-bad-coverage")
        self.assertEqual(len(status["history_only"]["prior_rounds"]),1)
        with self.assertRaisesRegex(RuntimeError,"quality must pass"):
            b.call("train_candidate",{"trial_id":"x","parent_trial_id":"","plan":{},"feature_review":"0001","trainer_research":"0001","experiment":{}})

    def test_ledger_chain_mutation_detected(self):
        self.b.call("inspect_harness",{})
        path=self.root/"activity.jsonl"; body=json.loads(path.read_text()); body["sequence"]=99
        path.write_text(json.dumps(body)+"\n")
        with self.assertRaisesRegex(ValueError,"ledger corrupted"): self.b.call("inspect_harness",{})

    def test_changed_runtime_rejected(self):
        with patch("data_scientist_harness.store.runtime_identity",return_value={"different":True}):
            with self.assertRaisesRegex(ValueError,"runtime changed"): Broker(self.root,self.sha)

    def test_submission_matches_existing_codex_terminal_protocol(self):
        from codex_glm_provider import successful_submission
        self.ready()
        result=self.b.call("submit_research_decision",{"action":"defer","trial_id":"","reason":"fixture"})
        request={"input":[{"type":"function_call","name":"submit_research_decision","call_id":"last"},
            {"type":"function_call_output","call_id":"last","output":json.dumps(result)}]}
        self.assertEqual(successful_submission(request,"submit_research_decision"),"last")
        self.assertGreater(result["bytes"],0)

    def test_preledger_rpc_error_preserves_location(self):
        from data_scientist_harness.broker import serve
        import io
        request={"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"inspect_harness","arguments":{}}}
        with patch.object(self.b,"call",side_effect=BlockingIOError(35,"unit busy")), \
             patch("sys.stdin",io.StringIO(json.dumps(request)+"\n")),patch("sys.stdout",io.StringIO()) as out:
            serve(self.b)
        self.assertTrue(json.loads(out.getvalue())["result"]["isError"])
        error=json.loads((self.root/"rpc-errors.jsonl").read_text())
        self.assertEqual(error["error_type"],"BlockingIOError")
        self.assertTrue(error["locations"])


if __name__ == "__main__": unittest.main()
