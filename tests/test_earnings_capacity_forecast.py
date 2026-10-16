"""CP3a borrowed forecast: invented raw HTTP, actual worker/scorer, no network.

Compose fixture setup objects, never inherit their TestCases or manufacture a
successful service result. Original forecast and Task.execution execute as-is.
"""
from contextlib import ExitStack
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import Mock, patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "research" / "market_rsi"))

import edgar_forecast_openai as original
import earnings_clock as clock
import earnings_controller as controller
import earnings_entry as entry
import earnings_execution_receipt as measurement
import earnings_transport_fixture as transport
from earnings_capacity_task import EarningsTask
from earnings_capacity_worker import CapacityWorker
from earnings_http import RawOpenAIHTTP
from earnings_night_budget import NightBudget, history_snapshot
from edgar_forecast_budget import PilotBudget, BudgetStop
from edgar_forecast_full_budget import FullBudget, activate
from market_rsi import digest
import test_earnings_capacity_adapter as native_fixture
import test_earnings_research_state as state_fixture

BOOT = "11111111-2222-3333-4444-555555555555"
SOURCE_COMMIT = "1fbe65d477298cf55211223b54f0ed4a6065db29"
PRIVATE = "CP3_PRIVATE_FAILURE_TEXT_MUST_NOT_REACH_RESULT"
MODEL = "gpt-6.1-sol"
DEADLINE_INIT = entry.DeadlineHTTP.__init__


def _wire(value):
    return (json.dumps(value, ensure_ascii=False, indent=3, allow_nan=False) + "\n\n").encode()


def _pin(path):
    return {"path": str(path), "sha256": sha256(path.read_bytes()).hexdigest()}


def _save(path, value):
    entry.durable_json(path, value)
    return _pin(path)


class _ForecastFixture:
    def __init__(self, owner):
        self.native = native_fixture.EarningsCapacityTests("test_earnings_reject_keeps_parent_and_history")
        self.native.setUp()
        owner.addCleanup(self.native.doCleanups)
        self.data = state_fixture.ResearchStateTests("test_append_preserves_parent_and_old_history")
        self.data.setUp()
        owner.addCleanup(self.data.doCleanups)
        self.root = self.native.root
        self.company = self.data.company
        questions = "\n".join(f"### T{i:03d} | invented quantity" for i in range(1, 6))
        filing = self.data.files["filings/old.md"] + "\n" + "Invented public filing paragraph. " * 200
        for name, text in (("questions.md", questions), ("filings/old.md", filing)):
            (Path(self.company["visible_root"]) / name).write_text(text)
            row = next(row for row in self.company["allowed_files"] if row["path"] == name)
            row.update(bytes=len(text.encode()), sha256=sha256(text.encode()).hexdigest())
        self.data.fact["source_sha256"] = next(row["sha256"] for row in self.company["allowed_files"]
                                                  if row["path"] == "filings/old.md")
        self.task_id = "fixture-task"
        self.runtime = json.loads((REPO / "benchmarks/edgar_forecast/openai_runtime.json").read_bytes())
        self.rate = deepcopy(self.runtime["models"][MODEL])
        self.kernel = transport.make_kernel(self.root)
        self.prior_path = self.root / "invented-prior-batch.json"
        prior = _save(self.prior_path, {"config": self.runtime, "fixture_only": True})
        data = _save(self.root / "invented-public-plan.json", {"companies": [self.company]})
        self.study_path = self.root / "invented-study.json"
        self.study = {"schema": "earnings_coevolution_study_v1", "new_live_grant": None,
            "new_episode_deadline": None, "closed_episode": {"reopen": False,
                "status": "completed_bounded_overnight", "binding": _save(self.root / "invented-closed.json",
                    {"status": "completed_bounded_overnight", "fixture_only": True})},
            "data": data, "model": deepcopy(self.native.args["model"]), "runtime_config": self.runtime,
            "prior_batch": prior, "scorer": self.kernel["scorer"], "python": self.native.args["runtime"]["python"],
            "sole_ledger": str(self.root / "owned-ledger.sqlite3"),
            "cases": [{k: self.company[k] for k in ("cik", "cutoff", "target_accession", "visible_root")}]}
        self.study["cases"][0].update(evaluation_kernel=self.kernel,
            allowed_manifest_sha256=entry.digest(json.dumps(self.company["allowed_files"], sort_keys=True,
                                                            separators=(",", ":")).encode()))
        self.study_binding = _save(self.study_path, self.study)
        self.role_root = self.root / "runtime"
        self.config = {"source_commit": SOURCE_COMMIT, "new_request_cutoff_utc": "2099-01-01T00:00:00Z",
                       "deadline_utc": "2099-01-01T00:05:00Z"}
        with patch.object(clock, "boot_id", return_value=BOOT):
            self.window, self.clock_binding = clock.capture_or_load(self.role_root, self.config)
        self.wall, self.monotonic = time.time(), time.monotonic()
        ledger = self.root / "owned-ledger.sqlite3"
        prior_budget = PilotBudget(ledger)
        try:
            prior_budget.reserve("fixture-prior", MODEL, 10000)
            prior_budget.settle("fixture-prior", 1000)
        finally:
            prior_budget.close()
        activate(ledger, "a" * 64, SOURCE_COMMIT)
        full = FullBudget(ledger)
        try:
            self.baseline = history_snapshot(full.db)
        finally:
            full.close()
        self.budget = NightBudget(ledger, baseline=self.baseline, deadline_utc=self.config["new_request_cutoff_utc"],
            captured_deadline=self.window["cutoff_monotonic"], clock=lambda: self.wall, monotonic=lambda: self.monotonic)
        owner.addCleanup(self.budget.close)
        self.slots = [str(self.role_root / "roles" / f"forecast-{i:02d}") for i in range(1, 7)]
        self.context = {"schema": "earnings_capacity_forecast_transport_v1", "source_commit": SOURCE_COMMIT,
            "root": str(self.role_root), "rates": self.rate, "limits": self.limits(), "slots": self.slots,
            "cutoff_utc": self.window["cutoff_utc"], "cutoff_monotonic": self.window["cutoff_monotonic"]}
        self.context_path = self.root / "forecast-context.json"
        self.context_binding = _save(self.context_path, self.context)
        self.calls, self.connections, self.raws = [], [], []
        self.after_count = self.after_generation = None
        self.http = RawOpenAIHTTP("", timeout=self.runtime["request_timeout_seconds"])
        self.factory = Mock(return_value=self.http)

    def limits(self):
        return {"max_input_tokens": self.runtime["max_input_tokens"],
                "max_output_tokens": max(self.runtime["max_output_tokens"],
                                         self.runtime.get("final_max_output_tokens", self.runtime["max_output_tokens"])),
                "wall_seconds": self.runtime["company_wall_seconds"]}

    def rewrite_context(self, value):
        self.context_path.write_bytes(_wire(value))
        self.context, self.context_binding = deepcopy(value), _pin(self.context_path)

    def rewrite_study(self, value):
        self.study_path.write_bytes(_wire(value))
        self.study, self.study_binding = deepcopy(value), _pin(self.study_path)

    def set_original_runtime(self, update):
        runtime = dict(self.runtime, **update)
        self.runtime = runtime
        self.prior_path.write_bytes(_wire({"config": runtime, "fixture_only": True}))
        self.rewrite_study(dict(self.study, runtime_config=runtime, prior_batch=_pin(self.prior_path)))
        self.rewrite_context(dict(self.context, limits=self.limits()))

    def worker(self, state=None, *, selected=False):
        if selected:
            before, after = self.native.propose("R")
            self.native.adapter.review(self.native.review_receipt(before, after),
                expected_state_sha256=self.native.batch.snapshot()["state_sha256"])
            before, after = self.native.propose("H", after)
            self.native.adapter.review(self.native.review_receipt(before, after),
                expected_state_sha256=self.native.batch.snapshot()["state_sha256"])
        capacity = self.native.restore()
        pair = digest(capacity.batch.snapshot()["micro_evolution"]["active_pair"])
        return CapacityWorker(self.company, self.task_id, capacity, pair, self.root / "memory", state)

    def service(self, **changes):
        args = {"budget": self.budget, "client_factory": self.factory, "study_binding": self.study_binding,
                "evaluation_kernel": self.kernel, "clock_binding": self.clock_binding}
        args.update(changes)
        with patch.object(clock, "boot_id", return_value=BOOT):
            return entry.CapacityForecast(self.context_binding, **args)

    def response(self, output):
        return {"id": "resp_invented_forecast", "object": "response", "status": "completed", "error": None,
            "model": MODEL, "service_tier": "default", "usage": {"input_tokens": 12, "output_tokens": 7,
            "total_tokens": 19, "input_tokens_details": {"cached_tokens": 3}}, "output": output}

    def final(self, predictions=None):
        if predictions is None:
            predictions = {"predictions": [{"target_id": f"T{i:03d}", "predicted_value": 100} for i in range(1, 6)]}
        return self.response([{"type": "message", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "text": json.dumps(predictions)}]}])

    def research(self):
        return self.response([
            {"type": "function_call", "call_id": "save-fact", "name": "save_research_record",
             "arguments": json.dumps({"record_json": json.dumps(self.data.fact)})},
            {"type": "function_call", "call_id": "read-filing", "name": "read_file",
             "arguments": json.dumps({"path": "filings/old.md", "offset": 0, "characters": 5000})}])

    def fake_connection(self, replies):
        fixture = self
        class Connection:
            def __init__(self, host, timeout):
                if host != "api.openai.com": raise AssertionError("Unexpected fake host")
                self.timeout, self.closed = timeout, False
                fixture.connections.append(self)

            def request(self, method, endpoint, body, headers):
                expected = "/v1/responses/input_tokens" if len(fixture.calls) % 2 == 0 else "/v1/responses"
                if method != "POST" or endpoint != expected: raise AssertionError("Unexpected dispatch/retry")
                self.endpoint, self.turn = endpoint, len(fixture.calls) // 2
                if self.turn >= len(replies): raise AssertionError("Unexpected extra turn or retry")
                fixture.calls.append((endpoint, json.loads(body)))

            def getresponse(self):
                if self.endpoint.endswith("input_tokens"):
                    raw = _wire({"input_tokens": 20})
                    callback = fixture.after_count
                else:
                    value = replies[self.turn]
                    if isinstance(value, BaseException): raise value
                    raw = value if isinstance(value, bytes) else _wire(value)
                    callback = fixture.after_generation
                fixture.raws.append((self.endpoint, self.turn, raw))
                if callback is not None: callback(self.turn)
                return Mock(status=200, getheader=Mock(return_value="req_cp3_fixture"), read=Mock(side_effect=lambda limit: raw[:limit]))

            def close(self): self.closed = True
        return Connection

    def invoke(self, worker=None, *, replies=None, slot=0, service=None):
        worker = self.worker() if worker is None else worker
        replies = [self.research(), self.final()] if replies is None else replies
        def init_deadline(transport_obj, client, **options):
            options.update(clock=lambda: self.wall, monotonic=lambda: self.monotonic)
            DEADLINE_INIT(transport_obj, client, **options)
        with ExitStack() as stack:
            stack.enter_context(patch("earnings_http.http.client.HTTPSConnection", side_effect=self.fake_connection(replies)))
            stack.enter_context(patch.object(entry, "credential", side_effect=AssertionError("No credentials")))
            stack.enter_context(patch.object(entry, "NightBudget", side_effect=AssertionError("No ledger reopen")))
            stack.enter_context(patch.object(clock, "boot_id", return_value=BOOT))
            stack.enter_context(patch.object(entry.time, "time", side_effect=lambda: self.wall))
            stack.enter_context(patch.object(entry.time, "monotonic", side_effect=lambda: self.monotonic))
            stack.enter_context(patch.object(entry.DeadlineHTTP, "__init__", new=init_deadline))
            return (self.service() if service is None else service).forecast(worker, self.slots[slot] if type(slot) is int else slot)

    def rows(self):
        return self.budget.db.execute("SELECT reserved,charged,status FROM requests WHERE id!='fixture-prior' ORDER BY rowid").fetchall()

    def originals(self, slot=0):
        return {path.name: path.read_bytes() for path in Path(self.slots[slot]).iterdir() if path.is_file()}


class CapacityForecastTests(unittest.TestCase):
    def fixture(self): return _ForecastFixture(self)

    def terminal(self, fixture, *, error_type=None):
        output = Path(fixture.slots[0])
        result = json.loads((output / "result.json").read_bytes())
        self.assertEqual(result["status"], "FAILED_NO_RETRY")
        self.assertNotIn(PRIVATE, json.dumps(result))
        self.assertNotEqual(result.get("scored_targets"), 5)
        if error_type is not None: self.assertEqual(result["error_type"], error_type)
        return output

    def test_two_actual_raw_turns_save_fact_read_filing_and_unchanged_task_execution(self):
        fixture = self.fixture()
        worker = fixture.worker(selected=True)
        with patch.object(fixture.budget, "close", wraps=fixture.budget.close) as closed, \
             patch.object(entry, "forecast", wraps=original.forecast) as invoked:
            output = fixture.invoke(worker)
            closed.assert_not_called()
        args, kwargs = invoked.call_args
        self.assertIs(args[4], fixture.budget)
        self.assertIs(kwargs["capacity_worker"], worker)
        self.assertEqual(args[2], fixture.runtime)
        self.assertNotIn("research_recipe", kwargs)
        root = Path(fixture.slots[0])
        self.assertEqual(output, {"result": _pin(root / "result.json"), "score": _pin(root / "score.json")})
        result, score = (json.loads(entry.checked(output[key])) for key in ("result", "score"))
        self.assertEqual((result["status"], result["turns"], result["tool_calls"], result["points"]),
                         ("COMPLETED_SCORED", 2, 2, 5))
        self.assertEqual(score["score_out_of_5"], 5)
        task = EarningsTask()
        task.kernel = fixture.kernel
        verified = task.execution(output, worker, root)
        self.assertEqual(verified["consumed"]["pair_sha256"], worker.pair)
        self.assertEqual(verified["state"], worker.state_binding)
        self.assertEqual(worker.state["records"][0]["record"]["value"], 100)
        self.assertIn("Verify signs with calculate", json.dumps(fixture.calls[0][1]))
        self.assertNotIn("ground_truth", json.dumps(fixture.calls))
        self.assertNotIn(fixture.kernel["qa"]["path"], json.dumps(fixture.calls))
        tools = list(root.glob("01-tool-*.json"))
        read = next(json.loads(p.read_bytes()) for p in tools if json.loads(p.read_bytes())["call_id"] == "read-filing")
        read_value = json.loads(read["output"])
        self.assertEqual((len(read_value["text"]), read_value["next_offset"]), (1000, 1000))
        self.assertEqual(fixture.rows(), [(250050000, 92800, "settled"), (250050000, 92800, "settled")])
        self.assertEqual(history_snapshot(fixture.budget.db, fixture.baseline["max_rowid"]), fixture.baseline)
        self.assertEqual(len(fixture.calls), 4)
        self.assertTrue(all(c.closed for c in fixture.connections))
        fixture.factory.assert_called_once()
        fixture.budget.active()
        for turn in (1, 2):
            count = json.loads((root / f"{turn:02d}-count.json").read_bytes())
            reservation = json.loads((root / f"{turn:02d}-request.json").read_bytes())
            self.assertEqual(count["input_tokens"], 20)
            self.assertEqual(reservation["payload"], fixture.calls[(turn - 1) * 2][1])
        raw_files = list(root.glob("http-*.raw.bin"))
        self.assertEqual(len(raw_files), 4)
        self.assertEqual(sorted(p.read_bytes() for p in raw_files), sorted(raw for _, _, raw in fixture.raws))
        intents = [json.loads(p.read_bytes()) for p in root.glob("http-*.intent.json")]
        self.assertEqual(len(intents), 4)
        self.assertTrue(all(row["retry_allowed"] is False for row in intents))

    def test_cold_worker_consumes_saved_record_in_actual_first_request(self):
        fixture = self.fixture()
        worker = fixture.worker()
        fixture.invoke(worker)
        previous = worker.state_binding
        old_bytes = Path(previous["path"]).read_bytes()
        # Each invocation is a distinct declared slot; fake transport starts a new exchange.
        fixture.calls, fixture.connections, fixture.raws = [], [], []
        cold = fixture.worker(previous)
        output = fixture.invoke(cold, replies=[fixture.final()], slot=1)
        payload = fixture.calls[0][1]["input"]
        note = next(json.loads(row["content"].split("\n", 1)[1]) for row in payload
                    if row["content"].startswith("PUBLIC RESEARCH RECORDS"))
        self.assertEqual(note["records"][0]["record"]["value"], 100)
        self.assertEqual(Path(previous["path"]).read_bytes(), old_bytes)
        task = EarningsTask(); task.kernel = fixture.kernel
        self.assertEqual(task.execution(output, cold, Path(fixture.slots[1]))["consumed"]["state_sha256"], previous["sha256"])
        self.assertEqual(len(fixture.rows()), 3)

    def test_original_twenty_four_turns_and_final_output_override_unchanged(self):
        fixture = self.fixture()
        fixture.set_original_runtime({"final_max_output_tokens": 30000})
        worker = fixture.worker()
        # Original no-op read tools keep history valid until the unchanged final turn.
        replies = [fixture.response([{"type": "function_call", "call_id": f"read-{n}", "name": "read_file",
            "arguments": json.dumps({"path": "filings/old.md", "offset": 0, "characters": 10})}]) for n in range(1, 24)]
        replies.append(fixture.final())
        result = fixture.invoke(worker, replies=replies)
        final_count, final_send = fixture.calls[-2][1], fixture.calls[-1][1]
        self.assertEqual(final_count["tools"], original.TOOLS)
        self.assertEqual(final_count["tool_choice"], "none")
        self.assertEqual(final_send["max_output_tokens"], 30000)
        self.assertEqual(fixture.calls[1][1]["max_output_tokens"], 25000)
        self.assertEqual(json.loads(entry.checked(result["result"]))["turns"], 24)
        task = EarningsTask(); task.kernel = fixture.kernel
        task.execution(result, worker, Path(fixture.slots[0]))
        self.assertEqual(len(fixture.rows()), 24)

    def test_controller_caps_cannot_silently_narrow_original_forecast_config(self):
        fixture = self.fixture()
        fixture.rewrite_context(dict(fixture.context, limits={"max_input_tokens": 10000, "max_output_tokens": 16384, "wall_seconds": 600}))
        with self.assertRaises(ValueError): fixture.service()
        fixture.factory.assert_not_called()
        self.assertEqual(fixture.rows(), [])
        self.assertFalse(Path(fixture.slots[0]).exists())

    def test_model_rates_prior_config_and_kernel_mismatch_refuse_before_factory(self):
        for kind in ("model", "effort", "price", "prior-config", "scorer", "case-kernel"):
            with self.subTest(kind=kind):
                fixture = self.fixture()
                study = deepcopy(fixture.study)
                if kind == "model": study["model"]["requested_model"] = "gpt-5.5"
                elif kind in ("effort", "price"):
                    rate = dict(fixture.rate, **({"effort": "xhigh"} if kind == "effort" else {"input": "3"}))
                    fixture.rewrite_context(dict(fixture.context, rates=rate))
                elif kind == "prior-config": study["runtime_config"] = dict(fixture.runtime, max_turns_per_company=23)
                elif kind == "scorer": study["scorer"] = dict(fixture.kernel["scorer"], sha256="c" * 64)
                else: study["cases"][0]["evaluation_kernel"] = dict(fixture.kernel, qa=dict(fixture.kernel["qa"], sha256="d" * 64))
                fixture.rewrite_study(study)
                with self.assertRaises(ValueError):
                    if kind == "case-kernel": fixture.invoke(fixture.worker())
                    else: fixture.service()
                fixture.factory.assert_not_called()
                self.assertEqual(fixture.rows(), [])

    def test_wrong_worker_company_and_selected_source_refuse_before_factory(self):
        for kind in ("object", "company", "manifest", "selected-source", "state"):
            with self.subTest(kind=kind):
                fixture = self.fixture()
                worker = fixture.worker()
                if kind == "object": worker = object()
                elif kind == "company": worker.state_api.company["cik"] = "CIK0000000002"
                elif kind == "manifest": worker.tools.files["filings/old.md"] = "unbound filing"
                elif kind == "selected-source": (fixture.root / "researcher_v1.py").write_text("PROFILE = {}\n")
                else: Path(worker.state_binding["path"]).write_bytes(b'{"records":[]}\n')
                with self.assertRaises(ValueError): fixture.invoke(worker)
                fixture.factory.assert_not_called()
                self.assertEqual(fixture.calls, [])
                self.assertFalse(Path(fixture.slots[0]).exists())

    def test_study_company_cik_cutoff_accession_manifest_drift_refuses_before_factory(self):
        for key, value in (("cik", "CIK0000000002"), ("cutoff", "2026-03-01"), ("target_accession", "other"),
                           ("allowed_manifest_sha256", "f" * 64)):
            with self.subTest(key=key):
                fixture = self.fixture()
                worker = fixture.worker()
                study = deepcopy(fixture.study)
                study["cases"][0][key] = value
                fixture.rewrite_study(study)
                with self.assertRaises(ValueError): fixture.invoke(worker)
                fixture.factory.assert_not_called()
                self.assertEqual(fixture.rows(), [])

    def test_semantic_final_errors_keep_settled_originals_without_dummy_score(self):
        for kind in ("duplicate-target", "multi-value", "refusal", "incomplete", "malformed"):
            with self.subTest(kind=kind):
                fixture = self.fixture()
                response = fixture.final()
                payload = json.loads(response["output"][0]["content"][0]["text"])
                if kind == "duplicate-target": payload["predictions"][4]["target_id"] = "T001"
                elif kind == "multi-value": payload["predictions"][0]["predicted_value"] = "100 +/- 5"
                elif kind == "refusal": response["output"][0]["content"] = [{"type": "refusal", "refusal": PRIVATE}]
                elif kind == "incomplete": response["status"] = "incomplete"
                if kind not in ("refusal", "incomplete"):
                    response["output"][0]["content"][0]["text"] = "{" + PRIVATE if kind == "malformed" else json.dumps(payload)
                with self.assertRaises(RuntimeError): fixture.invoke(replies=[response])
                output = self.terminal(fixture)
                self.assertEqual(fixture.rows(), [(250050000, 92800, "settled")])
                self.assertTrue((output / "01-response.json").exists())
                self.assertFalse((output / "score.json").exists())
                self.assertEqual(len(fixture.calls), 2)
                fixture.budget.active()

    def test_existing_single_numeric_string_prediction_definition_is_preserved(self):
        fixture = self.fixture()
        worker = fixture.worker()
        predictions = {"predictions": [{"target_id": f"T{i:03d}", "predicted_value": "100"} for i in range(1, 6)]}
        output = fixture.invoke(worker, replies=[fixture.final(predictions)])
        task = EarningsTask(); task.kernel = fixture.kernel
        task.execution(output, worker, Path(fixture.slots[0]))
        self.assertEqual(json.loads(entry.checked(output["score"]))["score_out_of_5"], 5)
        self.assertEqual(json.loads((Path(fixture.slots[0]) / "predictions.json").read_bytes()), predictions)

    def test_second_turn_timeout_keeps_first_fact_and_sticky_uncertain_liability(self):
        fixture = self.fixture()
        worker = fixture.worker()
        with self.assertRaises(RuntimeError): fixture.invoke(worker, replies=[fixture.research(), TimeoutError(PRIVATE)])
        output = self.terminal(fixture, error_type="TimeoutError")
        self.assertEqual(worker.state_api.load(worker.state_binding)["records"][0]["record"]["value"], 100)
        self.assertEqual(fixture.rows(), [(250050000, 92800, "settled"), (250050000, 0, "uncertain")])
        self.assertTrue((output / "01-response.json").exists())
        self.assertTrue((output / "02-request.json").exists())
        self.assertFalse((output / "02-response.json").exists())
        self.assertFalse((output / "score.json").exists())
        self.assertEqual(len(fixture.calls), 4)
        before, rows = fixture.originals(), fixture.rows()
        with self.assertRaises(FileExistsError): fixture.invoke(worker)
        self.assertEqual(fixture.originals(), before)
        self.assertEqual(fixture.rows(), rows)
        self.assertEqual(len(fixture.calls), 4)
        with self.assertRaises(BudgetStop): fixture.budget.active()

    def test_wrong_model_and_invalid_wire_are_uncertain_originals_not_resampled(self):
        for kind in ("model", "wire"):
            with self.subTest(kind=kind):
                fixture = self.fixture()
                response = dict(fixture.final(), model="gpt-5.5") if kind == "model" else b'{"output":[],"output":[]}'
                with self.assertRaises(RuntimeError): fixture.invoke(replies=[response])
                root = self.terminal(fixture)
                self.assertEqual(fixture.rows(), [(250050000, 0, "uncertain")])
                self.assertFalse((root / "score.json").exists())
                self.assertEqual(len(list(root.glob("http-*.raw.bin"))), 2)

    def test_declared_six_slots_and_canonical_symlinks_are_enforced(self):
        fixture = self.fixture()
        worker, service = fixture.worker(), fixture.service()
        for slot in (str(fixture.role_root / "roles" / "foreign"), str(fixture.root / "outside"),
                     str(fixture.role_root / "roles") + "/../roles/forecast-01", "roles/forecast-01"):
            with self.subTest(slot=slot), self.assertRaises(ValueError): fixture.invoke(worker, service=service, slot=slot)
        outside = fixture.root / "outside-dir"; outside.mkdir()
        roles = fixture.role_root / "roles"; roles.mkdir()
        Path(fixture.slots[0]).symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError): fixture.invoke(worker, service=service)
        self.assertEqual(list(outside.iterdir()), [])
        fixture.factory.assert_not_called()
        self.assertEqual(fixture.rows(), [])

    def test_completed_slot_reuse_preserves_originals_and_does_not_close_budget(self):
        fixture = self.fixture()
        worker, service = fixture.worker(), fixture.service()
        with patch.object(fixture.budget, "close", wraps=fixture.budget.close) as closed:
            fixture.invoke(worker, service=service)
            before, rows = fixture.originals(), fixture.rows()
            with self.assertRaises(FileExistsError): fixture.invoke(worker, service=service)
            closed.assert_not_called()
        self.assertEqual(fixture.originals(), before)
        self.assertEqual(fixture.rows(), rows)
        fixture.factory.assert_called_once()
        self.assertEqual(len(fixture.calls), 4)

    def test_bound_context_study_prior_kernel_clock_drift_before_factory(self):
        for kind in ("context", "study", "prior", "qa", "clock"):
            with self.subTest(kind=kind):
                fixture = self.fixture()
                worker, service = fixture.worker(), fixture.service()
                path = {"context": fixture.context_path, "study": fixture.study_path, "prior": fixture.prior_path,
                        "qa": Path(fixture.kernel["qa"]["path"]), "clock": Path(fixture.clock_binding["path"])}[kind]
                path.write_bytes(path.read_bytes() + b" ")
                with self.assertRaises(ValueError): fixture.invoke(worker, service=service)
                fixture.factory.assert_not_called()
                self.assertFalse(Path(fixture.slots[0]).exists())

    def test_context_or_qa_drift_after_count_prevents_generation_and_keeps_liability(self):
        for kind in ("context", "qa"):
            with self.subTest(kind=kind):
                fixture = self.fixture()
                path = fixture.context_path if kind == "context" else Path(fixture.kernel["qa"]["path"])
                fixture.after_count = lambda turn: path.write_bytes(path.read_bytes() + b" ")
                with self.assertRaises(RuntimeError): fixture.invoke()
                root = self.terminal(fixture, error_type="ValueError")
                self.assertEqual(len(fixture.calls), 1)
                self.assertEqual(fixture.rows(), [(250050000, 0, "uncertain")])
                self.assertFalse((root / "01-response.json").exists())

    def test_reboot_and_expired_budget_refuse_before_slot_and_factory(self):
        fixture = self.fixture()
        worker, service = fixture.worker(), fixture.service()
        with patch.object(clock, "boot_id", return_value="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"), \
             patch("earnings_http.http.client.HTTPSConnection", side_effect=AssertionError("No unexpected network")), \
             self.assertRaises(ValueError):
            service.forecast(worker, fixture.slots[0])
        fixture.budget.monotonic_deadline = fixture.monotonic - 1
        with self.assertRaises(BudgetStop): fixture.invoke(worker, service=service)
        fixture.factory.assert_not_called()
        self.assertFalse(Path(fixture.slots[0]).exists())

    def test_late_factory_cannot_dispatch_any_count_request(self):
        fixture = self.fixture()
        fixture.budget.monotonic_deadline = fixture.monotonic + 5
        def late():
            fixture.monotonic += 6
            return fixture.http
        fixture.factory.side_effect = late
        with self.assertRaises(RuntimeError): fixture.invoke()
        self.terminal(fixture, error_type="BudgetStop")
        self.assertEqual(fixture.calls, [])
        self.assertEqual(fixture.rows(), [])

    def test_external_budget_clips_physical_timeout_and_count_to_generation(self):
        fixture = self.fixture()
        fixture.budget.monotonic_deadline = fixture.monotonic + 5
        fixture.after_count = lambda turn: setattr(fixture, "monotonic", fixture.monotonic + 2)
        fixture.invoke(replies=[fixture.final()])
        self.assertGreater(fixture.connections[0].timeout, 0)
        self.assertLessEqual(fixture.connections[0].timeout, 5)
        self.assertGreater(fixture.connections[1].timeout, 0)
        self.assertLessEqual(fixture.connections[1].timeout, 3)

    def test_late_generation_retains_known_charge_but_no_accepted_result(self):
        fixture = self.fixture()
        fixture.budget.monotonic_deadline = fixture.monotonic + 5
        fixture.after_generation = lambda turn: setattr(fixture, "monotonic", fixture.monotonic + 6)
        with self.assertRaises(RuntimeError): fixture.invoke(replies=[fixture.final()])
        root = self.terminal(fixture, error_type="BudgetStop")
        self.assertEqual(fixture.rows()[0][1:], (92800, "settled"))
        self.assertTrue((root / "01-response.json").exists())

    def test_late_scoring_and_budget_summary_cannot_create_success(self):
        for kind in ("score", "summary"):
            with self.subTest(kind=kind):
                fixture = self.fixture()
                fixture.budget.monotonic_deadline = fixture.monotonic + 5
                service = fixture.service()
                if kind == "summary":
                    summary = fixture.budget.summary
                    def late_summary():
                        value = summary(); fixture.monotonic += 6; return value
                    patcher = patch.object(fixture.budget, "summary", side_effect=late_summary)
                else:
                    load = measurement.load_scorer
                    def late_loader(path):
                        scorer, token = load(path)
                        def scored(**kwargs):
                            result = scorer(**kwargs); fixture.monotonic += 6; return result
                        return scored, token
                    patcher = patch.object(measurement, "load_scorer", side_effect=late_loader)
                with patcher, self.assertRaises(RuntimeError): fixture.invoke(replies=[fixture.final()], service=service)
                self.terminal(fixture, error_type="BudgetStop")
                self.assertEqual(fixture.rows()[0][1:], (92800, "settled"))

    def test_terminal_summary_exception_is_sanitized_and_does_not_close_budget(self):
        fixture = self.fixture()
        with patch.object(fixture.budget, "summary", side_effect=ValueError(PRIVATE)), \
             patch.object(fixture.budget, "close", wraps=fixture.budget.close) as closed, self.assertRaises(RuntimeError):
            fixture.invoke(replies=[fixture.final()])
        closed.assert_not_called()
        self.terminal(fixture, error_type="ValueError")
        self.assertEqual(fixture.rows()[0][1:], (92800, "settled"))

    def test_mutated_score_result_effective_context_and_turn_originals_fail_task_verification(self):
        for kind in ("score", "result", "effective", "original"):
            with self.subTest(kind=kind):
                fixture = self.fixture()
                worker = fixture.worker()
                output = fixture.invoke(worker)
                root = Path(fixture.slots[0])
                if kind in ("score", "result"):
                    value = json.loads(entry.checked(output[kind]))
                    value["score_out_of_5" if kind == "score" else "points"] = 0
                    path = Path(output[kind]["path"]); path.write_bytes(_wire(value)); output[kind] = _pin(path)
                elif kind == "effective":
                    path = root / "effective-capacity.json"
                    value = json.loads(path.read_bytes()); value["context"]["tool_bounds"]["read_chunk_limit"] = 1
                    path.write_bytes(_wire(value))
                else: (root / "01-count.json").write_bytes(_wire({"input_tokens": 0}))
                task = EarningsTask(); task.kernel = fixture.kernel
                with self.assertRaises(ValueError): task.execution(output, worker, root)


if __name__ == "__main__": unittest.main()
