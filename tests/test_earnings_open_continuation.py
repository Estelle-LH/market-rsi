"""Synthetic continuation interfaces, not a replay of the real closed pilot.

All historical pins, financial originals, provenance and owner facts below are
invented in owned temporary storage. Completed-core auditing is explicitly
mocked. Assembly integration uses fake HTTP and synthetic program receipts;
it does not establish actual model authorship or actual container execution.
No real prior PINS, protected QA, API ledger, credentials or network are read.
"""
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, patch

import test_earnings_capacity_forecast as raw_fixture
import test_earnings_open_assembly as assembly_fixture
import test_earnings_research_state as state_fixture
import earnings_open_assembly as assembly
import earnings_open_continuation as continuation
import earnings_open_task as task_module
import prepare_earnings_open as preparer
from earnings_capacity_task import EarningsTask
from earnings_feedback import project_feedback
from earnings_research_state import ResearchState
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine


def historical_feedback(task_id, cik):
    result = {"status": "COMPLETED_SCORED", "planned_targets": 5,
              "scored_targets": 5, "points": 1, "turns": 2, "tool_calls": 2}
    score = {"score_out_of_5": 1, "target_count": 5, "prediction_count": 5,
        "duplicate_prediction_ids": [], "unknown_prediction_ids": [],
        "per_target": [{"target_id": f"T{i:03d}", "points_awarded": 1 if i == 1 else 0,
                        "ground_truth_numeric": 7000, "relative_error": 0.123,
                        "private_free_text": "SYNTHETIC_QA_NEVER_FORWARD"} for i in range(1, 6)]}
    observation = project_feedback(result, score, task_id=task_id, cik=cik)
    feedback = {"observation": observation, "baseline_score_out_of_5": 0.5,
        "research_diagnostics": {"schema": "earnings_research_diagnostics_v1",
            "execution": {"turns": 2, "tool_calls": 2, "input_tokens": 24, "output_tokens": 14,
                "tool_return_characters": 1200, "repeated_reads": 0, "rejected_tools": 0,
                "records_added": 1, "initial_records": 0, "score_out_of_5": 1},
            "review": {"verdict": "continue", "reason": "NOT_MEASURED", "metric": None,
                "direction": None, "min_delta": None, "observed_delta": None,
                "score_delta": None, "benefit_observed": False}}}
    return result, score, feedback


class _HistoricalFixture:
    """Exercise prior() with actual temporary bindings but mocked core audit."""
    def __init__(self, owner):
        self.data = state_fixture.ResearchStateTests("test_append_preserves_parent_and_old_history")
        self.data.setUp()
        owner.addCleanup(self.data.doCleanups)
        self.root, self.serial = self.data.root / "invented-history", 0
        self.root.mkdir()
        questions = "\n".join(f"### T{i:03d} | invented quantity" for i in range(1, 6))
        path = Path(self.data.company["visible_root"]) / "questions.md"
        path.write_text(questions)
        row = next(row for row in self.data.company["allowed_files"] if row["path"] == "questions.md")
        row.update(bytes=len(questions.encode()), sha256=sha256(questions.encode()).hexdigest())
        self.sources = {}
        for axis, name in (("R", "researcher_selected.py"), ("H", "harness_selected.py")):
            meta = {"axis": axis} if axis == "R" else {"axis": axis, "tools": []}
            source = self.root / name
            source.write_text("PROGRAM = " + repr(meta) + "\ndef run(payload):\n    return {'inherited': True}\n")
            self.sources[axis] = engine.pin(source)
        self.manifest = {"K": "a" * 64, "C": "b" * 64, "M": "c" * 64,
            "runtime": {"python": {"path": str(self.root / "invented-python"), "sha256": "d" * 64}},
            "components": {axis: {"sources": {Path(bound["path"]).name: bound["sha256"]}}
                           for axis, bound in self.sources.items()}}
        self.selected = {"manifest": self.manifest,
            "entrypoints": {axis: Path(bound["path"]).name for axis, bound in self.sources.items()},
            "static_review": None}
        self.pair = {"R": "e" * 64, "H": "f" * 64}
        self.state = {"micro_evolution": {"active_pair": self.pair, "pending": None}}
        result, score, feedback = historical_feedback(continuation.PRIOR_ID, self.data.company["cik"])
        self.output = {"pair_sha256": digest(self.pair), "result": self.save("result-original", result),
                       "score": self.save("score-original", score)}
        self.outcome = {"status": "completed", "completed_rounds": 2,
            "result": {"pair_sha256": digest(self.pair), "feedback": feedback}}
        self.envelope = {"id": continuation.PRIOR_ID, "root": str(self.root / "closed-episode"),
            "cik": self.data.company["cik"], "grant": self.save("inert-grant", {"fixture_only": True})}
        self.core = {"invented_current_core": self.sources["R"]}
        self.terminal = {"status": "COMPLETED_COMPONENT_CONTEXT", "error_type": None,
            "retry_allowed": False, "budget_summary": {"blocked": False, "unresolved_reserved_usd": 0}}
        self.audit = {"blocking_findings": [], "episode_id": continuation.PRIOR_ID}
        self.body = {"episode": self.save("episode", self.envelope), "outcome": self.outcome,
            "sources": self.core, "selected_version": self.save("selected", self.selected),
            "selected_sources": list(self.sources.values())}
        self.publish()

    def save(self, name, value):
        self.serial += 1
        return engine.save(self.root / f"{self.serial:03d}-{name}.json", value)

    def publish(self):
        self.body["runtime_terminal"] = self.save("terminal", self.terminal)
        closed = self.save("closure", self.body)
        result = self.save("open-result", {"completed_driver": closed, "outcome": self.outcome})
        binds = {"result": result, "closure": closed, "audit": self.save("audit", self.audit),
                 "root_audit": self.save("root-audit", {"fixture_only": True})}
        self.pins = {key: (str(Path(bound["path"]).relative_to(self.root)), bound["sha256"])
                     for key, bound in binds.items()}

    @contextmanager
    def scope(self):
        with ExitStack() as stack:
            stack.enter_context(patch.object(continuation, "PRIOR_ROOT", self.root))
            stack.enter_context(patch.object(continuation, "PINS", self.pins))
            stack.enter_context(patch.object(continuation.completed, "sources", return_value=self.core))
            self.snapshots = stack.enter_context(patch.object(continuation.completed, "_native_snapshot",
                side_effect=lambda _: deepcopy(self.state)))
            self.selection = stack.enter_context(patch.object(continuation.completed, "_selected"))
            self.work = stack.enter_context(patch.object(continuation.completed, "_work"))
            stack.enter_context(patch.object(engine.driver, "_read_pair", return_value={"output": self.output}))
            self.task = stack.enter_context(patch.object(continuation.original, "task",
                return_value=(self.data.company, {})))
            stack.enter_context(patch.object(continuation.e, "credential", side_effect=AssertionError("No keys")))
            stack.enter_context(patch.object(continuation.e, "NightBudget", side_effect=AssertionError("No owner")))
            yield


class HistoricalLineageTests(unittest.TestCase):
    def test_prior_reads_only_exact_selected_programs_and_sanitizes_old_feedback(self):
        f = _HistoricalFixture(self)
        before = {str(path): path.read_bytes() for path in f.root.rglob("*") if path.is_file()}
        with f.scope():
            value = continuation.prior()
        self.assertEqual(value["sources"], f.sources)
        self.assertEqual(value["prior_pair_sha256"], digest(f.pair))
        self.assertEqual(value["selected_version"], f.body["selected_version"])
        self.assertEqual(value["protected"], {key: f.manifest[key] for key in ("K", "C", "M", "runtime")})
        self.assertEqual(value["feedback"]["observation"]["task_id"], continuation.PRIOR_ID)
        self.assertEqual(value["feedback"]["target_scores"], [
            {"target_id": f"T{i:03d}", "points_awarded": 1 if i == 1 else 0} for i in range(1, 6)])
        self.assertEqual(set(value["trace_slots"]), {"prior-forecast-01", "prior-forecast-02"})
        self.assertTrue(all(Path(path).is_relative_to(Path(f.envelope["root"]) / "roles")
                            for path in value["trace_slots"].values()))
        self.assertIn("Historical", value["scope"])
        for secret in ("ground_truth_numeric", "relative_error", "private_free_text", "SYNTHETIC_QA_NEVER_FORWARD"):
            self.assertNotIn(secret, json.dumps(value["feedback"]))
        self.assertEqual(f.snapshots.call_count, 2)
        f.selection.assert_called_once()
        f.work.assert_called_once()
        self.assertEqual({str(path): path.read_bytes() for path in f.root.rglob("*") if path.is_file()}, before)

    def test_pending_history_changed_active_pair_or_wrong_execution_cannot_become_baseline(self):
        for kind in ("pending", "active-pair", "ordinary-pair", "incomplete", "audit"):
            with self.subTest(kind=kind):
                f = _HistoricalFixture(self)
                if kind == "pending": f.state["micro_evolution"]["pending"] = {"fixture_pending": True}
                elif kind == "active-pair": f.state["micro_evolution"]["active_pair"] = {"R": "1" * 64, "H": "2" * 64}
                elif kind == "ordinary-pair": f.output["pair_sha256"] = "1" * 64
                elif kind == "incomplete": f.outcome["completed_rounds"] = 1
                else: f.audit["blocking_findings"] = ["synthetic unresolved blocker"]
                f.publish()
                with f.scope(), self.assertRaises(ValueError):
                    continuation.prior()

    def test_uncertain_failed_or_blocked_historical_owner_is_never_reopened(self):
        for change in ({"status": "FAILED_NO_RETRY"}, {"error_type": "SyntheticFailure"},
                       {"retry_allowed": True}, {"budget_summary": {"blocked": True, "unresolved_reserved_usd": 0}},
                       {"budget_summary": {"blocked": False, "unresolved_reserved_usd": 0.1}}):
            with self.subTest(change=change):
                f = _HistoricalFixture(self)
                f.terminal.update(change)
                f.publish()
                with f.scope(), self.assertRaises(ValueError):
                    continuation.prior()

    def test_selected_source_byte_drift_and_duplicate_source_refuse(self):
        for kind in ("bytes", "duplicate"):
            with self.subTest(kind=kind):
                f = _HistoricalFixture(self)
                if kind == "bytes":
                    source = Path(f.sources["H"]["path"])
                    source.write_bytes(source.read_bytes() + b"# Explicit synthetic drift\n")
                else:
                    f.body["selected_sources"].append(deepcopy(f.sources["H"]))
                    f.publish()
                with f.scope(), self.assertRaises(ValueError):
                    continuation.prior()

    def test_verify_recomputes_prior_and_refuses_fabricated_sources_feedback_or_scope(self):
        f = _HistoricalFixture(self)
        with f.scope():
            expected = continuation.prior()
            bound = f.save("legitimate-synthetic-lineage", expected)
            self.assertEqual(continuation.verify(bound), expected)
            for kind in ("source", "feedback", "pair", "scope", "extra"):
                changed = deepcopy(expected)
                if kind == "source": changed["sources"]["H"]["sha256"] = "0" * 64
                elif kind == "feedback": changed["feedback"]["target_scores"][0]["points_awarded"] = 0
                elif kind == "pair": changed["prior_pair_sha256"] = "0" * 64
                elif kind == "scope": changed["scope"] = "New heldout predictive gain"
                else: changed["new_authority"] = True
                with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, "fabricated|drift"):
                    continuation.verify(f.save("fabricated-lineage", changed))


class ContinuationTaskTests(unittest.TestCase):
    def test_seed_retains_new_empty_task_and_labels_old_feedback_historical_without_aliasing(self):
        f = _HistoricalFixture(self)
        new_id = "invented-new-continuation"
        api = ResearchState(f.data.company, new_id)
        initial = api.save(f.root / "new-empty-memory", api.empty())
        with f.scope():
            lineage = continuation.prior()
            lineage_binding = f.save("lineage", lineage)
            envelope = {"id": new_id, "cik": f.data.company["cik"], "initial_state": initial,
                        "study": f.save("new-study", {"program_lineage": lineage_binding})}
            result = task_module.OpenTask().seed(envelope)
        self.assertEqual(result["state"], initial)
        self.assertEqual(api.load(result["state"]), api.empty())
        self.assertEqual(result["feedback"]["observation"]["task_id"], new_id)
        self.assertEqual(result["feedback"]["observation"]["execution"]["error_type"], "NoForecastYet")
        self.assertIsNone(result["feedback"]["observation"]["prediction"]["score_out_of_5"])
        self.assertIsNone(result["feedback"]["baseline_score_out_of_5"])
        inherited = result["feedback"]["inherited_research"]
        self.assertEqual(inherited, {"prior_pair_sha256": lineage["prior_pair_sha256"],
                                    "feedback": lineage["feedback"], "scope": lineage["scope"]})
        self.assertEqual(result["artifacts"], [initial, lineage_binding])
        inherited["feedback"]["target_scores"][0]["points_awarded"] = 0
        self.assertEqual(engine.read(lineage_binding)["feedback"]["target_scores"][0]["points_awarded"], 1)

    def test_baseline_seed_unchanged_and_lineage_skips_only_the_human_bootstrap(self):
        f = _HistoricalFixture(self)
        envelope = {"id": "invented-new", "cik": f.data.company["cik"],
                    "initial_state": f.save("inert-empty-state", {}), "study": f.save("baseline-study", {})}
        task = task_module.OpenTask()
        self.assertEqual(task.seed(envelope), EarningsTask().seed(envelope))
        prompt = {"parent_pair_sha256": "a" * 64, "feedback_sha256": "b" * 64}
        with patch.object(task, "admit_live", return_value=True) as admission:
            baseline = task.bootstrap_control(envelope, prompt, 1)
            self.assertEqual((baseline["axis"], baseline["component"]), ("continue", "none"))
            self.assertEqual(baseline["parent_pair_sha256"], prompt["parent_pair_sha256"])
            admission.assert_called_once_with(envelope)
        with f.scope():
            lineage = continuation.prior()
            inherited = dict(envelope, grant=f.save('fresh-initial-controller-flag',{'bootstrap_no_model_call':False}),
                study=f.save("inherited-study", {"program_lineage": f.save("inherited-lineage", lineage)}))
            with patch.object(task, "admit_live", return_value=True) as admission:
                self.assertIsNone(task.bootstrap_control(inherited, prompt, 1))
                admission.assert_called_once_with(inherited)
            with patch.object(task, "admit_live", side_effect=AssertionError("No later bootstrap admission")):
                self.assertIsNone(task.bootstrap_control(inherited, prompt, 2))
            legacy=dict(inherited,grant=f.save('legacy-human-bootstrap-flag',{'bootstrap_no_model_call':True}))
            with patch.object(task,'admit_live',return_value=True):
                self.assertEqual(task.bootstrap_control(legacy,prompt,1)['axis'],'continue')


class ContinuationAssemblyTests(unittest.TestCase):
    def fixture(self):
        helper = assembly_fixture.OpenAssemblyTests()
        self.addCleanup(helper.doCleanups)
        f = helper.fixture()
        _, _, feedback = historical_feedback("invented-prior-only", f.raw.company["cik"])
        selected = f.save("invented-prior-selected", {"manifest": deepcopy(f.native["baseline"])})
        sources = {axis: engine.pin(f.paths["source_root"] / name)
                   for axis, name in f.native["entrypoints"].items()}
        traces = {f"prior-forecast-{i:02d}": str(f.home / "invented-prior" / "roles" / f"forecast-{i:02d}")
                  for i in (1, 2)}
        for path in traces.values(): Path(path).mkdir(parents=True)
        lineage = {"schema": "earnings_verified_program_lineage_v1",
            "prior_episode": f.save("invented-prior-episode", {"fixture_only": True}),
            "provenance": {"fixture_only": True}, "prior_pair_sha256": digest({"fixture": "old selected pair"}),
            "selected_version": selected, "sources": sources,
            "protected": {key: deepcopy(f.native["baseline"][key]) for key in ("K", "C", "M", "runtime")},
            "feedback": dict(feedback, target_scores=[{"target_id": f"T{i:03d}",
                "points_awarded": 1 if i == 1 else 0} for i in range(1, 6)]),
            "trace_slots": traces, "scope": "Historical synthetic Discovery; not new observations or authority"}
        return helper, f, lineage

    def bind_lineage(self, f, lineage):
        grant=engine.read(f.envelope['grant'])
        f.envelope['grant']=f.save('explicit-first-model-controller',dict(grant,bootstrap_no_model_call=False))
        study = engine.read(f.envelope["study"])
        study["program_lineage"] = f.save("invented-lineage", lineage)
        f.envelope["study"] = f.save("study-with-lineage", study)
        f.runtime["forecast_study"] = f.envelope["study"]
        f.runtime_binding = f.save("lineage-runtime", f.runtime)
        f.episode_binding = f.save("lineage-episode", f.envelope)
        f.plan["episode"] = f.episode_binding
        baseline = f.native["baseline"]
        f.native["micro_config"]["fixed_context"] = {
            "model_sha256": baseline["M"], "evaluation_sha256": baseline["K"],
            "data_scope_sha256": digest({"study": f.envelope["study"], "cik": f.envelope["cik"],
                                        "kernel": f.envelope["evaluation_kernel"]}),
            "authority_sha256": digest({key: f.envelope[key] for key in ("mode", "grant", "window")}),
            "resource_policy_sha256": digest(f.runtime_binding)}
        f.assembly.update(episode=f.episode_binding, runtime=f.runtime_binding,
            native=f.save("lineage-native", f.native), matched_plan=f.save("lineage-plan", f.plan))
        review = engine.read(f.assembly["independent_review"])
        review.update(episode=f.episode_binding, reviewed_configuration_sha256=digest(
            {key: value for key, value in f.assembly.items() if key != "independent_review"}))
        f.assembly["independent_review"] = f.save("lineage-fixture-review", review)
        f.assembly_binding = f.save("lineage-assembly", f.assembly)

    def test_read_only_assembly_accepts_exact_inherited_sources_before_any_owner(self):
        helper, f, lineage = self.fixture()
        self.bind_lineage(f, lineage)
        before = f.retained_tree()
        with helper.scope(f), patch.object(continuation, "prior", return_value=deepcopy(lineage)), \
                patch.object(assembly, "open_capacity_runtime", side_effect=AssertionError("No owner")):
            value = assembly.validate(f.episode_binding, f.assembly_binding)
        self.assertEqual(value[2], f.native)
        self.assertEqual(f.retained_tree(), before)
        self.assertEqual(f.factory_calls, 0)

    def test_actual_prepared_baseline_bytes_must_match_verified_inherited_source_hash(self):
        helper, f, lineage = self.fixture()
        path = f.home / "different-prior-harness.py"
        path.write_bytes((f.paths["source_root"] / f.native["entrypoints"]["H"]).read_bytes()
                         + b"# Different synthetic inherited program\n")
        lineage["sources"]["H"] = engine.pin(path)
        self.bind_lineage(f, lineage)
        before = f.retained_tree()
        with helper.scope(f), patch.object(continuation, "prior", return_value=deepcopy(lineage)), \
                patch.object(assembly, "open_capacity_runtime", side_effect=AssertionError("No owner")), \
                self.assertRaisesRegex(ValueError, "inherit.*exact.*program|exact.*adopted"):
            assembly.validate(f.episode_binding, f.assembly_binding)
        self.assertEqual(f.retained_tree(), before)
        self.assertEqual(f.factory_calls, 0)

    def test_continuation_calls_real_controller_path_first_and_keeps_historical_feedback_distinct(self):
        helper, f, lineage = self.fixture()
        self.bind_lineage(f, lineage)
        sequence = [helper.choose(f, "continue"), f.raw.research(), f.raw.final(),
                    helper.choose(f, "continue"), f.raw.research(), f.raw.final(), helper.choose(f, "continue")]
        with helper.scope(f), patch.object(continuation, "prior", return_value=deepcopy(lineage)), f.exchange(sequence):
            result = engine.read(assembly.run(f.episode_binding, f.assembly_binding))
        self.assertEqual(result["outcome"]["completed_rounds"], 2)
        first = json.loads(f.raw.calls[1][1]["input"][0]["content"])
        self.assertEqual(first["feedback"]["inherited_research"]["feedback"], lineage["feedback"])
        self.assertEqual(first["feedback"]["observation"]["task_id"], f.envelope["id"])
        self.assertIsNone(first["feedback"]["observation"]["prediction"]["score_out_of_5"])
        self.assertEqual(first["feedback"]["inherited_research"]["feedback"]["observation"]["task_id"], "invented-prior-only")
        self.assertTrue(set(lineage["trace_slots"]) <= set(first["registered_traces"]))
        self.assertTrue((Path(f.slots[0]["controller"]) / "decision.json").is_file())
        self.assertIs(engine.read(f.envelope['grant'])['bootstrap_no_model_call'],False)
        first_request=engine.read(engine.pin(Path(f.slots[0]['controller'])/'01-request.json'))
        ledger_row=next(row for row in f.ledger_rows() if row[0]==first_request['request_id'])
        self.assertGreater(first_request['reserved_nano_usd'],0)
        self.assertEqual(ledger_row[-1],'settled')
        terminal = engine.read(result["next_actual_controller"])
        terminal_packet = engine.read(terminal["packet"])
        self.assertEqual(terminal_packet["feedback"], result["outcome"]["result"]["feedback"])
        self.assertFalse(terminal["applied"])
        self.assertEqual(len(f.raw.calls), 14)
        self.assertTrue(all(row[4] == "settled" for row in f.ledger_rows()))


class ContinuationPreparationTests(unittest.TestCase):
    def fixture(self):
        f = _HistoricalFixture(self)
        f.repo = f.root / "invented-source-repository"
        names = ("tools/edgar_forecast_openai.py", "configs/earnings_coevolution/program_R0.py",
                 "configs/earnings_coevolution/program_H0.py")
        for name, data in zip(names, (b"# Synthetic protected predictor\n",
                b"PROGRAM={'axis':'R'}\ndef run(p): return {'fresh': True}\n",
                b"PROGRAM={'axis':'H','tools':[]}\ndef run(p): return {'fresh': True}\n")):
            path = f.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        f.source_names = list(names)
        f.pilot_root = f.root / "inert-open-pilot"
        f.native_root = f.root / "inert-native-episodes"
        f.ledger_path = f.root / "never-opened-real-ledger.sqlite3"
        f.scorer = f.root / "synthetic-scorer.py"
        f.scorer.write_bytes(b"# Invented protected scorer copy; never executed\n")
        f.qa = f.root / "invented-qa.json"
        f.qa.write_bytes(b'{"fixture_only":true}\n')
        f.python = f.root / "inert-python"
        f.python.write_bytes(b"fixture runtime identity, never executed\n")
        f.runtime = {"max_input_tokens": 10000, "max_output_tokens": 16384,
            "company_wall_seconds": 600, "request_timeout_seconds": 60, "models": {"gpt-6.1-sol": {}}}
        f.old = {"ledger": str(f.ledger_path), "pilot_plan": f.save("inert-data-plan", {"fixture_only": True}),
            "runtime": f.save("inert-runtime", f.runtime), "scorer": engine.pin(f.scorer),
            "qa": engine.pin(f.qa), "cik": f.data.company["cik"]}
        f.baseline = {"charged_nano_usd": preparer.live.BASELINE_CHARGED,
            "request_count": preparer.live.BASELINE_ROWS, "max_rowid": preparer.live.BASELINE_ROWS,
            "rows_sha256": "9" * 64}
        return f

    @contextmanager
    def scope(self, f, lineage=None, *, closed=False):
        sql = MagicMock()
        sql.__enter__ = Mock(return_value=sql)
        sql.__exit__ = Mock(return_value=False)
        def execute(statement):
            if statement == "SELECT * FROM config":
                return Mock(fetchall=Mock(return_value=[(1, 200_000_000_000, 100_000_000_000, 0)]))
            if "status NOT IN" in statement: return Mock(fetchone=Mock(return_value=None))
            if "SUM(charged)" in statement:
                return Mock(fetchone=Mock(return_value=(preparer.live.BASELINE_CHARGED + 500_000_000,)))
            if statement == "BEGIN": return Mock()
            raise AssertionError("Unexpected synthetic DB query")
        sql.execute = Mock(side_effect=execute)
        now = datetime(2026, 10, 15, 0, 21, 33, tzinfo=timezone.utc) if closed else datetime(
            2026, 10, 14, 23, 0, 0, tzinfo=timezone.utc)
        def source_pin(path):
            return engine.pin(f.python) if Path(path) == Path(preparer.sys.executable).absolute() else f.old["runtime"]
        with ExitStack() as stack:
            stack.enter_context(patch.object(preparer.live.e, "REPO", f.repo))
            stack.enter_context(patch.object(preparer.live, "ROOT", f.pilot_root))
            stack.enter_context(patch.object(preparer.namespace, "NATIVE_RUNTIME_ROOT", f.native_root))
            stack.enter_context(patch.object(preparer.subprocess, "run", side_effect=[
                SimpleNamespace(stdout="1" * 40 + "\n"), SimpleNamespace(stdout=b"")]))
            stack.enter_context(patch.object(preparer.sqlite3, "connect", return_value=sql))
            stack.enter_context(patch.object(preparer.live, "history_snapshot", return_value=f.baseline))
            stack.enter_context(patch.object(preparer.live, "sources", return_value=f.source_names))
            stack.enter_context(patch.object(preparer.live, "read", return_value=f.old))
            stack.enter_context(patch.object(preparer.live.original.original, "pin", side_effect=source_pin))
            stack.enter_context(patch.object(preparer.live.original, "task", return_value=(f.data.company, f.runtime)))
            stack.enter_context(patch.object(preparer, "datetime", Mock(now=Mock(return_value=now))))
            f.prior = stack.enter_context(patch.object(continuation, "prior", return_value=deepcopy(lineage)))
            f.validation = stack.enter_context(patch.object(preparer.assembly, "validate", return_value=None))
            stack.enter_context(patch.object(preparer.live.e, "credential", side_effect=AssertionError("No credentials")))
            stack.enter_context(patch.object(preparer.assembly, "open_capacity_runtime", side_effect=AssertionError("No owner")))
            stack.enter_context(patch.object(preparer.assembly, "DockerRunner", side_effect=AssertionError("No Docker")))
            yield

    def test_preparer_copies_exact_prior_programs_without_relabeling_old_task_memory(self):
        f = self.fixture()
        with f.scope(): lineage = continuation.prior()
        with self.scope(f, lineage):
            bound = preparer.prepare(95, carry_forward=True)
        prepared = engine.read(bound)
        envelope = engine.read(prepared["episode"])
        assembled = engine.read(prepared["assembly"])
        native = engine.read(assembled["native"])
        study = engine.read(envelope["study"])
        self.assertEqual(engine.read(study["program_lineage"]), lineage)
        for axis, name in (("R", "researcher_v0.py"), ("H", "harness_v0.py")):
            copied = Path(native["source_root"]) / name
            self.assertEqual(copied.read_bytes(), Path(lineage["sources"][axis]["path"]).read_bytes())
            self.assertEqual(sha256(copied.read_bytes()).hexdigest(), lineage["sources"][axis]["sha256"])
            self.assertEqual(native["baseline"]["components"][axis]["sources"][name], lineage["sources"][axis]["sha256"])
        api = ResearchState(f.data.company, envelope["id"])
        self.assertEqual(api.load(envelope["initial_state"]), api.empty())
        grant = engine.read(envelope["grant"])
        self.assertEqual(envelope["window"], preparer.live.PILOT_WINDOW)
        self.assertEqual(grant["baseline"], f.baseline)
        self.assertEqual(grant["additional_cap_nano_usd"], preparer.live.PILOT_CAP)
        self.assertEqual(prepared["provider_calls"], 0)
        self.assertEqual(prepared["status"], "AWAITING_DISTINCT_REVIEW_NO_OWNER")
        f.prior.assert_called_once_with()
        f.validation.assert_called_once()

    def test_default_preparation_keeps_fresh_baseline_and_has_no_historical_lineage(self):
        f = self.fixture()
        with self.scope(f): bound = preparer.prepare(96)
        prepared = engine.read(bound)
        envelope = engine.read(prepared["episode"])
        assembled = engine.read(prepared["assembly"])
        native = engine.read(assembled["native"])
        self.assertNotIn("program_lineage", engine.read(envelope["study"]))
        for axis, name in (("R", "researcher_v0.py"), ("H", "harness_v0.py")):
            self.assertEqual((Path(native["source_root"]) / name).read_bytes(),
                (f.repo / "configs/earnings_coevolution" / f"program_{axis}0.py").read_bytes())
        f.prior.assert_not_called()

    def test_carry_forward_cannot_reopen_or_extend_the_closed_original_window(self):
        f = self.fixture()
        with self.scope(f, closed=True), self.assertRaisesRegex(ValueError, "window closed"):
            preparer.prepare(97, carry_forward=True)
        f.prior.assert_not_called()
        f.validation.assert_not_called()
        self.assertFalse(f.pilot_root.exists())
        self.assertFalse(f.native_root.exists())


if __name__ == "__main__":
    unittest.main()
