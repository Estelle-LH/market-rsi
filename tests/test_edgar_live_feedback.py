"""Two-round real handlers/driver/forecast on entirely invented financial fixtures.

No production ledger, protected QA, filing artifacts, credentials or network are
read. Flow tests explicitly substitute financial admission and a synthetic
scorer; admission tests use temporary invented provenance and public code only.
"""
from contextlib import ExitStack, contextmanager, redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import edgar_live_feedback as live
import earnings_clock as clock
from edgar_forecast_audit import git_blob
from edgar_forecast_budget import PilotBudget
from edgar_forecast_full_budget import activate
from edgar_forecast_tools import TOOLS

COUNT, GENERATE = "/v1/responses/input_tokens", "/v1/responses"
BOOT = "00000000-0000-0000-0000-000000000001"
SECRET = "SYNTHETIC_LABEL_NEVER_SEND"
METHOD = "Reconcile units and use calculate to evaluate 100 + 0."


def message(text):
    return {"type": "message", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "text": text}]}


def read_json(path):
    return live.e.strict_json(Path(path).read_text())


def feedback_sha(value):
    # This is the driver's JSON commitment, not the pretty-printed file hash.
    return live.e.digest(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                   ensure_ascii=True, allow_nan=False).encode())


class ScriptedRaw(live.RawOpenAIHTTP):
    """Original raw-client type with an overridden, network-free post method."""
    def __init__(self, fixture, role):
        self.fixture, self.role, self.turn = fixture, role, 0
        self.timeout, self.record_prefix = 180, None

    def post(self, endpoint, payload):
        self.fixture.calls.append((self.role, endpoint, deepcopy(payload)))
        if endpoint == COUNT:
            if self.fixture.after_count is not None:
                self.fixture.after_count(self.role, self.turn)
            return {"input_tokens": 100}
        if endpoint != GENERATE:
            raise AssertionError("Unexpected synthetic endpoint")
        self.turn += 1
        if self.fixture.failure == (self.role, self.turn):
            raise TimeoutError("invented transport failure")
        if self.role == "controller":
            packet = live.e.strict_json(payload["input"][0]["content"])
            recipe = {"schema": "earnings_research_recipe_v1", "task_id": packet["task_id"],
                      "parent_feedback_sha256": packet["parent_feedback_sha256"],
                      "research_instructions": METHOD}
            output = [message(json.dumps(recipe))]
            if self.fixture.controller_mutation is not None:
                output = self.fixture.controller_mutation(output, recipe)
        elif self.turn == 1:
            has_recipe = any(METHOD in item.get("content", "") for item in payload["input"])
            name = "calculate" if has_recipe else "read_file"
            args = {"expression": "100 + 0"} if has_recipe else {
                "path": "filing_index.tsv", "offset": 0, "characters": 100}
            output = [{"type": "function_call", "name": name,
                       "call_id": "invented-" + self.role, "arguments": json.dumps(args)}]
        else:
            output = [message(json.dumps({"predictions": [
                {"target_id": target, "predicted_value": 100} for target in self.fixture.targets]}))]
        response = {"model": payload["model"], "service_tier": "default", "status": "completed",
                    "output": output, "usage": {"input_tokens": 100, "output_tokens": 10,
                    "total_tokens": 110, "input_tokens_details": {"cached_tokens": 0}}}
        if self.role == "controller" and self.fixture.response_mutation is not None:
            self.fixture.response_mutation(response)
        return response


class SyntheticFixture:
    def __init__(self, case, name):
        temporary = tempfile.TemporaryDirectory(prefix="edgar-feedback-synthetic-")
        case.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name).resolve()
        self.pilot = self.home / "pilot"
        self.pilot.mkdir()
        self.targets = [f"T{index:03d}" for index in range(1, 6)]
        self.visible = self.home / "invented-visible"
        self.visible.mkdir()
        self.files = {
            "questions.md": "\n".join(f"### {target} | invented financial amount" for target in self.targets),
            "filing_index.tsv": "date_filed\tform_type\taccession\tpath\n"
                                "2026-01-01\t10-Q\tinvented-old\tfilings/10-Q_invented-old.md\n",
            "filings/10-Q_invented-old.md": "Invented fixture revenue: 100. No actual company data.",
        }
        self.company = {"cik": "CIK0000003545", "visible_root": str(self.visible),
                        "cutoff": "2026-02-01", "target_accession": "invented-hidden", "allowed_files": []}
        for name_, content in self.files.items():
            path = self.visible / name_
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            self.company["allowed_files"].append({"path": name_, "bytes": len(content.encode()),
                                                   "sha256": live.e.digest(content.encode())})
        self.tools = live.e.FilingTools(self.company)
        self.runtime = {"max_input_tokens": 100000, "max_output_tokens": 25000,
                        "max_turns_per_company": 2, "company_wall_seconds": 1800,
                        "models": {"gpt-6.1-sol": deepcopy(live.RATE)}}
        self.qa = {"targets": [{"target_id": target, "ground_truth_numeric": 100,
                                  "ground_truth_surface": SECRET} for target in self.targets]}
        self.plan_bound = live.save(self.pilot / "pilot-plan.json", {"companies": [self.company]})
        self.runtime_bound = live.save(self.home / "invented-runtime.json", self.runtime)
        self.recovery = self.home / "invented-recovery"
        self.dataset = self.recovery / "upstream-git-01"
        (self.dataset / "invented-bundle").mkdir(parents=True)
        (self.dataset / "scripts").mkdir()
        self.qa_bound = live.save(self.dataset / "invented-bundle/forecast_benchmark_qa.json", self.qa)
        # Admission checks bytes and public blob identities; this is never loaded.
        scorer_path = self.dataset / "scripts/edgar_forecast_bench.py"
        scorer_path.write_bytes(b"synthetic scorer commitment; never executable\n")
        self.scorer_bound = live.pin(scorer_path)
        self.manifest = {"instances": [{"cik": self.company["cik"],
            "target_accession": self.company["target_accession"], "staged_bundle_path": "invented-bundle"}]}
        live.save(self.dataset / "benchmark_manifest.json", self.manifest)
        self.metadata = {"sha": live.REVISION, "siblings": []}
        for path in (Path(self.qa_bound["path"]), scorer_path, self.dataset / "benchmark_manifest.json"):
            data = path.read_bytes()
            self.metadata["siblings"].append({"rfilename": str(path.relative_to(self.dataset)),
                                                "size": len(data), "blobId": git_blob(data)})
        live.save(self.recovery / "upstream-metadata-v2.json", self.metadata)
        self.ledger = self.pilot / "api-budget.sqlite3"
        budget = PilotBudget(self.ledger)
        budget.reserve("invented-prior", live.RATE["api_model"], 1000)
        budget.settle("invented-prior", 1000)
        budget.close()
        activate(self.ledger, "a" * 64, "b" * 40)
        with sqlite3.connect(self.ledger) as db:
            baseline = live.history_snapshot(db)
        cutoff = datetime.now(timezone.utc) + timedelta(minutes=15)
        task = "edgar-real-feedback-20261014-01"
        self.root = self.home / "canaries" / task
        self.config = {"schema": "edgar_live_feedback_canary_v1", "id": task, "root": str(self.root),
            "source_commit": "b" * 40, "sources": {source: live.pin(ROOT / source)["sha256"]
                                                      for source in live.SOURCES},
            "python": live.pin(Path(sys.executable).absolute()), "pilot_plan": self.plan_bound,
            "runtime": self.runtime_bound, "scorer": self.scorer_bound, "qa": self.qa_bound,
            "cik": self.company["cik"], "ledger": str(self.ledger), "baseline": baseline,
            "cutoff_utc": cutoff.isoformat().replace("+00:00", "Z"),
            "deadline_utc": (cutoff + timedelta(seconds=45)).isoformat().replace("+00:00", "Z"),
            "additional_cap_nano_usd": 5_000_000_000}
        self.calls, self.clients, self.score_calls = [], [], []
        self.failure = self.controller_mutation = self.response_mutation = self.after_count = None
        self.factory = Mock(side_effect=self.new_client)
        self.credentials = Mock(side_effect=AssertionError("Synthetic tests must never load credentials"))

    def new_client(self):
        role = ("forecast-01", "controller", "forecast-02")[len(self.clients)]
        client = ScriptedRaw(self, role)
        self.clients.append(client)
        return client

    def scorer(self, *, predictions_payload, benchmark_qa_payload):
        self.score_calls.append(deepcopy((predictions_payload, benchmark_qa_payload)))
        return {"score_out_of_5": 2, "target_count": 5, "prediction_count": 5,
                "duplicate_prediction_ids": [], "unknown_prediction_ids": [],
                "targets": [{"ground_truth_numeric": 100, "surface": SECRET}]}

    @contextmanager
    def flow(self):
        # A named, explicit admission stand-in; no claim of real data admission.
        data = (self.company, self.tools, self.targets, self.runtime, self.qa)
        with patch.object(live, "fixed", return_value=data), \
             patch.object(live.e, "load_scorer", return_value=(self.scorer, {})), \
             patch.object(live.e, "credential", self.credentials), \
             patch.object(clock, "boot_id", return_value=BOOT):
            yield

    @contextmanager
    def financial_admission(self):
        # Exact fixed() paths are rebased to owned invented fixtures. Source and
        # runtime are public files read in place; Git is a scripted read stand-in.
        source = "tools/edgar_live_feedback.py"
        source_bytes = (ROOT / source).read_bytes()
        self.config["sources"] = {source: live.e.digest(source_bytes)}
        self.config["runtime"] = live.pin(ROOT / "benchmarks/edgar_forecast/openai_runtime.json")
        with ExitStack() as stack:
            for fixture in (
                patch.object(live, "CANARIES", self.root.parent),
                patch.object(live, "RECOVERY", self.recovery),
                patch.object(live, "SOURCES", (source,)),
                patch.object(live, "SCORER_SHA", self.scorer_bound["sha256"]),
                patch.object(live, "METADATA_SHA", live.pin(self.recovery / "upstream-metadata-v2.json")["sha256"]),
                patch.object(live.e, "REPO", ROOT),
                patch.object(live.e, "PILOT", self.pilot),
                patch.object(live.e, "PLAN_HASH", self.plan_bound["sha256"]),
                patch.object(live.e, "credential", self.credentials),
            ):
                stack.enter_context(fixture)
            git = stack.enter_context(patch.object(live.subprocess, "run",
                                    return_value=SimpleNamespace(stdout=source_bytes)))
            yield git

    def rows(self):
        with sqlite3.connect(self.ledger) as db:
            return db.execute("SELECT rowid,id,model,reserved,charged,status FROM requests ORDER BY rowid").fetchall()

    def protected_snapshot(self):
        return {path: path.read_bytes() for path in self.home.rglob("*")
                if path.is_file() and not path.name.endswith(("-wal", "-shm"))}


class EdgarLiveFeedbackTests(unittest.TestCase):
    def fixture(self, name):
        return SyntheticFixture(self, name)

    def assert_refused_before_credentials(self, fixture, config=None):
        before = fixture.protected_snapshot()
        with self.assertRaises((ValueError, FileNotFoundError, StopIteration)):
            live.run(fixture.config if config is None else config)
        fixture.credentials.assert_not_called()
        fixture.factory.assert_not_called()
        self.assertEqual(fixture.protected_snapshot(), before)
        self.assertFalse(fixture.root.exists())

    def test_actual_seven_stages_deliver_aggregate_feedback_and_recipe_to_next_forecast(self):
        fixture = self.fixture("two-rounds")
        original = deepcopy(fixture.config)
        protected = fixture.protected_snapshot()
        with fixture.flow():
            outcome = live.run(fixture.config, client_factory=fixture.factory)
        self.assertEqual((outcome["status"], outcome["completed_rounds"]), ("completed", 2))
        self.assertEqual(fixture.config, original)
        self.assertEqual(fixture.factory.call_count, 3)
        self.assertEqual([client.role for client in fixture.clients], ["forecast-01", "controller", "forecast-02"])
        self.assertEqual(len(fixture.calls), 10)
        fixture.credentials.assert_not_called()
        manifest = read_json(fixture.root / "loop/manifest.json")
        self.assertEqual(set(manifest["handler_identity"]), set(live.driver.STAGES))
        required_helpers = {
            "research/market_rsi/supervisor_harness/account_controller_feedback_consumer.py",
            "research/market_rsi/supervisor_harness/opened_train_discovery_worker.py",
            "research/market_rsi/supervisor_harness/continuous_discovery_batch.py",
            "research/market_rsi/supervisor_harness/learning_checkpoint_assessment.py",
            "research/market_rsi/data_scientist_harness/co_evolution_loop.py",
            "research/market_rsi/data_scientist_harness/__init__.py",
            "research/market_rsi/market_rsi.py",
        }
        self.assertTrue(required_helpers <= set(live.SOURCES))
        for stage, identity in manifest["handler_identity"].items():
            self.assertEqual(identity["handler"], stage)
            self.assertEqual(set(identity["sources"]), set(live.SOURCES))
            self.assertEqual(identity["config"], live.pin(fixture.root / "config.json"))
            self.assertEqual(identity["clock"], live.pin(fixture.root / "clock.json"))
        for index in (1, 2):
            for stage in live.driver.STAGES:
                prefix = fixture.root / "loop" / f"round-{index:04d}-{stage}"
                self.assertTrue(prefix.with_suffix(".claim.json").is_file())
                done = live.read(live.pin(prefix.with_suffix(".done.json")))
                self.assertEqual(done["output_sha256"], feedback_sha(done["output"]))
                self.assertTrue(prefix.with_suffix(".done.binding.json").is_file())
                self.assertFalse(prefix.with_suffix(".failed.json").exists())
        first_controller = read_json(fixture.root / "loop/round-0001-controller.done.json")["output"]
        self.assertEqual(first_controller, {"recipe": None, "origin": "UNCHANGED_BASELINE_NO_CONTROLLER_CALL"})
        first = read_json(fixture.root / "loop/round-0001-reconcile.done.json")["output"]
        packet = read_json(fixture.root / "packet-02.json")
        self.assertEqual(packet["parent_feedback_sha256"], feedback_sha(first))
        self.assertEqual(packet["feedback"], first["feedback"])
        self.assertEqual(packet["prior_recipe"], None)
        controller_request = next(payload for role, endpoint, payload in fixture.calls
                                  if role == "controller" and endpoint == GENERATE)
        actual_input = live.e.strict_json(controller_request["input"][0]["content"])
        self.assertEqual(actual_input, live.controller.safe_input(packet))
        self.assertEqual(actual_input["parent_feedback_sha256"], feedback_sha(first))
        self.assertEqual(actual_input["feedback"]["observation"]["prediction"]["score_out_of_5"], 2)
        self.assertEqual((controller_request["tools"], controller_request["tool_choice"],
                          controller_request["parallel_tool_calls"]), ([], "none", False))
        recipe = read_json(fixture.root / "roles/controller-02/recipe.json")
        self.assertEqual(recipe["parent_feedback_sha256"], feedback_sha(first))
        self.assertEqual(recipe["research_instructions"], METHOD)
        baseline = [payload for role, endpoint, payload in fixture.calls if role == "forecast-01" and endpoint == GENERATE]
        child = [payload for role, endpoint, payload in fixture.calls if role == "forecast-02" and endpoint == GENERATE]
        self.assertEqual(len(baseline[0]["input"]), 1)
        compiled = live.e.research_recipe_message(recipe)
        self.assertIn(compiled, child[0]["input"])
        self.assertIn(compiled, child[1]["input"])
        self.assertEqual(baseline[0]["tools"], TOOLS)
        self.assertEqual(child[0]["tools"], baseline[0]["tools"])
        self.assertEqual(child[0]["instructions"], baseline[0]["instructions"])
        final_observation = next(item for item in child[1]["input"] if item.get("type") == "function_call_output")
        self.assertEqual(json.loads(final_observation["output"]), {"value": 100})
        identity = read_json(fixture.root / "roles/forecast-02/identity.json")
        self.assertEqual(identity["recipe"], live.pin(fixture.root / "roles/controller-02/recipe.json"))
        self.assertEqual(identity["feedback_packet"], live.pin(fixture.root / "packet-02.json"))
        effective = read_json(fixture.root / "roles/forecast-02/effective-recipe.json")
        self.assertEqual(effective["recipe"], recipe)
        self.assertEqual(effective["parent_feedback_sha256"], feedback_sha(first))
        for _, _, payload in fixture.calls:
            self.assertEqual(payload["model"], live.RATE["api_model"])
            self.assertEqual(payload["reasoning"], {"effort": live.RATE["effort"]})
            self.assertNotIn(SECRET, json.dumps(payload))
            self.assertNotIn("ground_truth", json.dumps(payload))
        rows = fixture.rows()
        self.assertEqual(rows[0][1:], ("invented-prior", live.RATE["api_model"], 1000, 1000, "settled"))
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(row[-1] == "settled" for row in rows))
        summary = read_json(fixture.root / "budget-summary.json")
        self.assertEqual((summary["cap_usd"], summary["model_cap_usd"], summary["night_cap_usd"]), (200, 100, 5))
        self.assertEqual(summary["prior_history_sha256"], fixture.config["baseline"]["rows_sha256"])
        terminal = read_json(fixture.root / "result.json")
        self.assertEqual((terminal["status"], terminal["transport_scope"], terminal["retry_allowed"]),
                         ("COMPLETED", "INJECTED_TEST_CLIENT", False))
        self.assertEqual(terminal["claims"], {"heldout_gain": False, "co_evolving_RH": False})
        for path, data in protected.items():
            if path != fixture.ledger:
                self.assertEqual(path.read_bytes(), data)
        self.assertEqual(len(fixture.score_calls), 2)

    def test_forecast_transport_failure_preserves_stage_and_root_evidence_without_rerun(self):
        fixture = self.fixture("forecast-failure")
        fixture.failure = ("forecast-01", 1)
        with fixture.flow():
            with self.assertRaises(live.driver.LoopHalted):
                live.run(fixture.config, client_factory=fixture.factory)
            before, calls = fixture.protected_snapshot(), deepcopy(fixture.calls)
            with self.assertRaises((ValueError, FileExistsError)):
                live.run(fixture.config, client_factory=fixture.factory)
        self.assertEqual(fixture.protected_snapshot(), before)
        self.assertEqual(fixture.calls, calls)
        self.assertEqual(fixture.factory.call_count, 1)
        failure = read_json(fixture.root / "loop/round-0001-execute.failed.json")
        self.assertEqual((failure["exception_type"], failure["retry_allowed"]), ("TimeoutError", False))
        result = read_json(fixture.root / "roles/forecast-01/result.json")
        self.assertEqual((result["status"], result["scored_targets"], result["error_type"]),
                         ("FAILED_NO_RETRY", 0, "TimeoutError"))
        self.assertFalse((fixture.root / "roles/forecast-01/score.json").exists())
        self.assertTrue(list((fixture.root / "roles/forecast-01").glob("http-*.failed.json")))
        terminal = read_json(fixture.root / "result.json")
        self.assertEqual((terminal["status"], terminal["error_type"], terminal["retry_allowed"]),
                         ("FAILED_NO_RETRY", "LoopHalted", False))
        self.assertEqual(fixture.rows()[-1][-1], "uncertain")
        self.assertTrue(read_json(fixture.root / "budget-summary.json")["blocked"])

    def test_malformed_refusal_and_tool_bearing_controller_recipes_fail_closed(self):
        def text_recipe(change):
            def mutate(output, recipe):
                change(recipe)
                return [message(json.dumps(recipe))]
            return mutate
        variants = {
            "invalid-json": lambda output, recipe: [message("not-json")],
            "duplicate-key": lambda output, recipe: [message('{"schema":"x","schema":"y"}')],
            "extra-field": text_recipe(lambda recipe: recipe.update(extra=True)),
            "wrong-task": text_recipe(lambda recipe: recipe.update(task_id="other-task")),
            "wrong-parent": text_recipe(lambda recipe: recipe.update(parent_feedback_sha256="0" * 64)),
            "empty-instructions": text_recipe(lambda recipe: recipe.update(research_instructions=" ")),
            "oversized-characters": text_recipe(lambda recipe: recipe.update(research_instructions="x" * 2201)),
            "oversized-bytes": text_recipe(lambda recipe: recipe.update(research_instructions="😀" * 1025)),
            "function-call": lambda output, recipe: [*output, {"type": "function_call", "name": "calculate"}],
            "custom-tool": lambda output, recipe: [*output, {"type": "custom_tool_call", "name": "outside"}],
            "refusal": lambda output, recipe: [{"type": "refusal", "refusal": "invented refusal"}],
        }
        for name, mutation in variants.items():
            with self.subTest(name=name):
                fixture = self.fixture(name)
                fixture.controller_mutation = mutation
                with fixture.flow():
                    with self.assertRaises(live.driver.LoopHalted):
                        live.run(fixture.config, client_factory=fixture.factory)
                    before = fixture.protected_snapshot()
                    with self.assertRaises((ValueError, FileExistsError)):
                        live.run(fixture.config, client_factory=fixture.factory)
                self.assertEqual(fixture.protected_snapshot(), before)
                self.assertEqual(fixture.factory.call_count, 2)
                self.assertFalse((fixture.root / "roles/forecast-02").exists())
                failure = read_json(fixture.root / "loop/round-0002-controller.failed.json")
                self.assertIs(failure["retry_allowed"], False)
                self.assertFalse((fixture.root / "roles/controller-02/recipe.json").exists())
                self.assertTrue((fixture.root / "roles/controller-02/01-response.json").is_file())
                self.assertEqual(read_json(fixture.root / "result.json")["status"], "FAILED_NO_RETRY")

    def test_controller_provider_metadata_is_checked_and_liability_stays_uncertain(self):
        variants = {
            "model": lambda response: response.update(model="other-model"),
            "tier": lambda response: response.update(service_tier="priority"),
            "usage": lambda response: response["usage"].update(total_tokens=999),
        }
        for name, mutation in variants.items():
            with self.subTest(name=name):
                fixture = self.fixture(name)
                fixture.response_mutation = mutation
                with fixture.flow(), self.assertRaises(live.driver.LoopHalted):
                    live.run(fixture.config, client_factory=fixture.factory)
                self.assertEqual(fixture.rows()[-1][-1], "uncertain")
                self.assertEqual(fixture.factory.call_count, 2)
                self.assertFalse((fixture.root / "roles/forecast-02").exists())
                self.assertTrue(read_json(fixture.root / "budget-summary.json")["blocked"])
                self.assertEqual(read_json(fixture.root / "loop/round-0002-controller.failed.json")["exception_type"], "ValueError")

    def test_real_fixed_and_preflight_are_readonly_on_explicit_synthetic_provenance(self):
        fixture = self.fixture("readonly")
        with fixture.financial_admission() as git:
            before = fixture.protected_snapshot()
            company, tools, targets, runtime, qa = live.preflight(fixture.config)
            self.assertEqual(company, fixture.company)
            self.assertEqual(tools.files, fixture.files)
            self.assertEqual(targets, fixture.targets)
            self.assertEqual(runtime["models"]["gpt-6.1-sol"], live.RATE)
            self.assertEqual(qa, fixture.qa)
            self.assertEqual(fixture.protected_snapshot(), before)
            git.assert_called_once_with(["git", "show", fixture.config["source_commit"] + ":tools/edgar_live_feedback.py"],
                                        cwd=ROOT, check=True, capture_output=True)
        fixture.credentials.assert_not_called()
        self.assertFalse(fixture.root.exists())

    def test_exact_config_source_python_and_paths_refuse_before_credentials(self):
        variants = {
            "field": lambda config: config.update(unreviewed=True),
            "schema": lambda config: config.update(schema="offline_replay"),
            "id": lambda config: config.update(id="unreviewed-id"),
            "root": lambda config: config.update(root=config["root"] + "-other"),
            "company": lambda config: config.update(cik="CIK0000000000"),
            "cap": lambda config: config.update(additional_cap_nano_usd=5_000_000_001),
            "bool-cap": lambda config: config.update(additional_cap_nano_usd=True),
            "commit": lambda config: config.update(source_commit="b" * 39),
            "source-hash": lambda config: config["sources"].update({"tools/edgar_live_feedback.py": "0" * 64}),
            "source-set": lambda config: config["sources"].update(unreviewed="0" * 64),
            "python": lambda config: config["python"].update(sha256="0" * 64),
            "ledger-path": lambda config: config.update(ledger=config["ledger"] + ".other"),
            "qa-path": lambda config: config["qa"].update(path=config["scorer"]["path"]),
        }
        for name, mutation in variants.items():
            with self.subTest(name=name):
                fixture = self.fixture(name)
                with fixture.financial_admission():
                    changed = deepcopy(fixture.config)
                    mutation(changed)
                    self.assert_refused_before_credentials(fixture, changed)
        fixture = self.fixture("uncommitted-source")
        with fixture.financial_admission() as git:
            git.return_value.stdout += b"\n# uncommitted synthetic difference\n"
            fixture.config["sources"]["tools/edgar_live_feedback.py"] = live.e.digest(git.return_value.stdout)
            self.assert_refused_before_credentials(fixture)

    def test_data_and_public_metadata_mismatches_refuse_before_credentials(self):
        variants = ("metadata-hash", "revision", "manifest-bytes", "accession", "qa-blob", "scorer-size",
                    "scorer-hash", "qa-target", "visible-file", "plan-hash", "runtime-hash")
        for name in variants:
            with self.subTest(name=name):
                fixture = self.fixture(name)
                with fixture.financial_admission():
                    if name in {"metadata-hash", "revision", "qa-blob", "scorer-size"}:
                        metadata = deepcopy(fixture.metadata)
                        if name in {"metadata-hash", "revision"}: metadata["sha"] = "0" * 40
                        if name == "qa-blob": metadata["siblings"][0]["blobId"] = "0" * 40
                        if name == "scorer-size": metadata["siblings"][1]["size"] += 1
                        path = fixture.recovery / "upstream-metadata-v2.json"
                        path.write_text(json.dumps(metadata))
                        if name != "metadata-hash":
                            # Independently test semantic/blob checks after admitting
                            # this invented metadata commitment in the test only.
                            live.METADATA_SHA = live.pin(path)["sha256"]
                    elif name in {"accession", "manifest-bytes"}:
                        manifest = deepcopy(fixture.manifest)
                        manifest["instances"][0]["target_accession"] = "different-hidden"
                        path = fixture.dataset / "benchmark_manifest.json"
                        path.write_text(json.dumps(manifest))
                        if name == "accession":
                            metadata = deepcopy(fixture.metadata)
                            metadata["siblings"][2].update(size=len(path.read_bytes()), blobId=git_blob(path.read_bytes()))
                            metadata_path = fixture.recovery / "upstream-metadata-v2.json"
                            metadata_path.write_text(json.dumps(metadata))
                            live.METADATA_SHA = live.pin(metadata_path)["sha256"]
                    elif name == "scorer-hash": fixture.config["scorer"]["sha256"] = "0" * 64
                    elif name == "qa-target":
                        qa = deepcopy(fixture.qa)
                        qa["targets"][0]["target_id"] = "T999"
                        path = Path(fixture.qa_bound["path"])
                        path.write_text(json.dumps(qa))
                        fixture.config["qa"] = live.pin(path)
                        metadata = deepcopy(fixture.metadata)
                        metadata["siblings"][0].update(size=len(path.read_bytes()), blobId=git_blob(path.read_bytes()))
                        metadata_path = fixture.recovery / "upstream-metadata-v2.json"
                        metadata_path.write_text(json.dumps(metadata))
                        live.METADATA_SHA = live.pin(metadata_path)["sha256"]
                    elif name == "visible-file": (fixture.visible / "questions.md").write_text("invented changed input")
                    elif name == "plan-hash": fixture.config["pilot_plan"]["sha256"] = "0" * 64
                    else: fixture.config["runtime"]["sha256"] = "0" * 64
                    self.assert_refused_before_credentials(fixture)

    def test_budget_preflight_refuses_changed_history_pending_or_new_charges_before_credentials(self):
        for name in ("allocation", "blocked", "history", "new-settled", "pending"):
            with self.subTest(name=name):
                fixture = self.fixture(name)
                with sqlite3.connect(fixture.ledger) as db:
                    if name == "allocation": db.execute("UPDATE config SET cap=cap+1")
                    elif name == "blocked": db.execute("UPDATE config SET blocked=1")
                    elif name == "history": db.execute("UPDATE requests SET charged=charged+1")
                    else:
                        db.execute("INSERT INTO requests VALUES (?,?,?,?,?)", ("invented-new", live.RATE["api_model"],
                                   1, 1 if name == "new-settled" else 0, "settled" if name == "new-settled" else "reserved"))
                with fixture.financial_admission():
                    self.assert_refused_before_credentials(fixture)

    def test_launch_window_and_grace_refuse_before_credentials(self):
        for name, seconds, grace in (("expired", -1, 45), ("too-far", 7300, 45),
                                      ("reversed", 100, -1), ("extended-grace", 100, 61)):
            with self.subTest(name=name):
                fixture = self.fixture(name)
                cutoff = datetime.now(timezone.utc) + timedelta(seconds=seconds)
                fixture.config.update(cutoff_utc=cutoff.isoformat().replace("+00:00", "Z"),
                    deadline_utc=(cutoff + timedelta(seconds=grace)).isoformat().replace("+00:00", "Z"))
                with fixture.financial_admission():
                    self.assert_refused_before_credentials(fixture)

    def test_startup_clock_failure_preserves_terminal_evidence_and_consumed_root(self):
        fixture = self.fixture("startup-clock")
        with fixture.flow(), patch.object(clock, "boot_id", side_effect=ValueError("invented boot refusal")):
            with self.assertRaises(ValueError):
                live.run(fixture.config, client_factory=fixture.factory)
            before = fixture.protected_snapshot()
            with self.assertRaises(FileExistsError):
                live.run(fixture.config, client_factory=fixture.factory)
        fixture.factory.assert_not_called()
        fixture.credentials.assert_not_called()
        self.assertEqual(fixture.protected_snapshot(), before)
        terminal = read_json(fixture.root / "result.json")
        self.assertEqual((terminal["status"], terminal["error_type"], terminal["retry_allowed"]),
                         ("FAILED_NO_RETRY", "ValueError", False))
        self.assertIsNone(terminal["outcome"])
        self.assertFalse((fixture.root / "loop").exists())
        self.assertEqual(len(fixture.rows()), 1)

    def test_immutable_helpers_reject_changed_bytes_symlinks_duplicate_and_nonfinite_json(self):
        fixture = self.fixture("bindings")
        path = fixture.home / "bound.json"
        bound = live.save(path, {"invented": 1})
        self.assertEqual(live.read(bound), {"invented": 1})
        with self.assertRaises(FileExistsError): live.save(path, {"invented": 2})
        original = path.read_bytes()
        path.write_text('{"invented":2}')
        with self.assertRaises(ValueError): live.read(bound)
        path.write_bytes(original)
        link = fixture.home / "symlink.json"
        link.symlink_to(path)
        with self.assertRaises(ValueError): live.read({"path": str(link), "sha256": bound["sha256"]})
        for index, payload in enumerate(('{"same":1,"same":2}', '{"value":NaN}')):
            raw = fixture.home / f"invalid-{index}.json"
            raw.write_text(payload)
            with self.assertRaises(ValueError): live.read(live.pin(raw))

    def test_cli_preflight_only_reports_zero_calls_without_running_or_reading_credentials(self):
        fixture = self.fixture("cli")
        binding = live.save(fixture.home / "synthetic-config.json", fixture.config)
        before = fixture.protected_snapshot()
        output = io.StringIO()
        with patch.object(live, "preflight", return_value=None) as preflight, \
             patch.object(live, "run", side_effect=AssertionError("Preflight must not run")) as run, \
             patch.object(live.e, "credential", fixture.credentials), redirect_stdout(output):
            live.main(["--config", binding["path"], "--preflight-only"])
        preflight.assert_called_once_with(fixture.config)
        run.assert_not_called()
        fixture.credentials.assert_not_called()
        self.assertEqual(json.loads(output.getvalue()), {"status": "REAL_TASK_PREFLIGHT_PASS", "new_provider_calls": 0})
        self.assertEqual(fixture.protected_snapshot(), before)
        self.assertFalse(fixture.root.exists())


if __name__ == "__main__":
    unittest.main()
