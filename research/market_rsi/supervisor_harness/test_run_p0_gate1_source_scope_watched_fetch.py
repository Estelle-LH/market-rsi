"""Offline parent/child/watchdog tests; every transport is a local fake."""
from __future__ import annotations

from copy import deepcopy
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from market_rsi import digest, fresh_json
from supervisor_harness import p0_gate1_source_scope_fetch_adapter as adapter
from supervisor_harness import p0_gate1_source_scope_watched_fetch_child as child
from supervisor_harness import run_p0_gate1_source_scope_watched_fetch as parent
from supervisor_harness.supervisor_watchdog import SupervisorWatchdog
from supervisor_harness.global_state_gate import SupervisorGlobalState
from paid_budget import PaidBudget
from supervisor_harness.test_p0_gate1_source_scope_fetch_adapter import (
    RUNTIME, bundle, make_binding,
)


COMMAND_SHA = "e" * 64
BUDGET_SHA = "f" * 64


def offline(binding, runner):
    root = Path(binding["output_root"])
    root.mkdir(mode=0o700)
    fresh_json(root / "authorization.json",
               json.loads(Path(binding["authorization_path"]).read_text()))
    fresh_json(root / "request-plan-bundle.json", bundle())
    fresh_json(root / "runtime.json", RUNTIME)
    fresh_json(root / "canary-verification.json",
               binding["canary_verification"])
    fresh_json(root / "binding.json", binding)
    watchdog = SupervisorWatchdog(root / "watchdog")
    watchdog.initialize()
    parent._claim(
        watchdog=watchdog, binding=binding, pid=os.getpid(),
        command_sha256=COMMAND_SHA, budget_snapshot_sha256=BUDGET_SHA,
        claim_path=root / "supervisor-claim.json", parent_pid=os.getpid(),
        parent_command_sha256="a" * 64,
        global_state_head_sha256="b" * 64,
        decision_doc_sha256="c" * 64,
        global_state_root=root / "test-state",
        decision_doc=root / "test-decision",
        budget_root=root / "test-budget")
    try:
        with patch.object(child, "_shared_preclaimed_runner",
                          return_value=runner):
            child.execute(
                binding=binding, output=root / "snapshot", watchdog=watchdog,
                pid=os.getpid(), process_command_sha256=COMMAND_SHA,
                budget_snapshot_sha256=BUDGET_SHA)
        return parent._finish_success(
            binding=binding, watchdog=watchdog, pid=os.getpid(),
            command_sha256=COMMAND_SHA, child_exit_code=0,
            terminal_process_absent=True, terminal_container_absent=True)
    except Exception as exc:
        parent._report_once(
            watchdog=watchdog, pid=os.getpid(), command_sha256=COMMAND_SHA,
            budget_snapshot_sha256=BUDGET_SHA, error=exc,
            process_present=False)
        raise


def fake_runner(*, watchdog, task_id, task, admission, output, pid,
                process_command_sha256, budget_snapshot_sha256,
                receipt_validator, clock=None):
    active = watchdog.snapshot()["active_task"]
    input_sha = digest({"task": task, "admission": admission})
    if (active["task_id"] != task_id or active["input_sha256"] != input_sha
            or active["process_identity"] != {
                "pid": pid, "command_sha256": process_command_sha256}
            or not isinstance(budget_snapshot_sha256, str)
            or len(budget_snapshot_sha256) != 64):
        raise ValueError("fake observed missing exact parent claim")
    watchdog.heartbeat(task_id, material_progress=True,
                       progress_sha256=input_sha,
                       now=None if clock is None else clock())
    output.mkdir(mode=0o700)
    snapshot = b"official documentation fixture\n"
    snapshot_path = output / "public-source.snapshot"
    snapshot_path.write_bytes(snapshot)
    receipt = {
        "schema": adapter.SNAPSHOT_RECEIPT_SCHEMA,
        "attempt_id": adapter.ATTEMPT_ID,
        "task_canonical_sha256": digest(task),
        "admission_canonical_sha256": digest(admission),
        "request_plan_canonical_sha256": adapter.REQUEST_PLAN_SHA256,
        "authorization_file_sha256": task["authorization_file_sha256"],
        "release_source_sha256": task["release"]["source_sha256"],
        "source_id": adapter.SOURCE_ID,
        "url_sha256": adapter.DOCUMENT_URL_SHA256,
        "final_url": adapter.DOCUMENT_URL, "status": 200,
        "content_encoding": None,
        "content_type": "text/html", "response_headers": {"etag": "fixture"},
        "snapshot_bytes": len(snapshot),
        "snapshot_sha256": hashlib.sha256(snapshot).hexdigest(),
        "requests_made": 1, "redirects_followed": 0,
        "automatic_retries": 0, "provider_calls": 0,
        "actual_provider_cost_usd": "0", "rights_proven": False,
        "sealed_data_read": False, "formal_data_admitted": False,
        "train_dev_final_read": False,
        "training_or_evaluation_performed": False,
        "snapshot_redistributed": False,
        "prediction_improvement_proven": False,
    }
    fresh_json(output / "receipt.json", receipt)
    receipt_validator(receipt, snapshot_path)
    receipt_sha = hashlib.sha256((output / "receipt.json").read_bytes()).hexdigest()
    watchdog.heartbeat(task_id, material_progress=True,
                       progress_sha256=receipt_sha,
                       now=None if clock is None else clock())
    return receipt


class SourceScopeWatchedFetchTests(unittest.TestCase):
    def live_fixture(self, base):
        root = base / adapter.ATTEMPT_ID
        with patch.object(adapter, "RUN_ROOT", root):
            binding, auth, _ = make_binding(base)
        decision = base / "decision.md"
        decision.write_text("# decision\n")
        state_root = base / "state"
        state = SupervisorGlobalState(state_root, decision)
        state_before = state.initialize()
        budget_root = base / "budget"
        budget = PaidBudget.create(budget_root, {
            "experiment_id": "live-fixture", "cap_usd": "0",
            "target_usd": "0", "buckets_usd": {"free": "0"},
            "authority": "fixture",
        })
        canary_path = Path(binding["canary_verification"]["receipt_path"])
        args = SimpleNamespace(
            output_root=root, global_state_root=state_root,
            decision_doc=decision, budget_root=budget_root,
            bundle=base / "bundle.json", runtime_receipt=base / "runtime.json",
            authorization=auth,
            expected_authorization_sha256=binding["authorization_file_sha256"],
            canary_receipt=canary_path,
            expected_canary_receipt_sha256=
                binding["task"]["prior_canary_receipt_sha256"],
            expected_state_head_sha256=state_before["head_sha256"],
            expected_decision_sha256=state_before["decision_doc_sha256"],
            expected_budget_snapshot_sha256=digest(budget.snapshot()),
        )
        return root, binding, state, budget, args

    def live_patches(self, stack, root, binding, state, budget, args):
        stack.enter_context(patch.object(adapter, "RUN_ROOT", root))
        stack.enter_context(patch.object(parent, "RUN_ROOT", root))
        stack.enter_context(patch.object(parent, "GLOBAL_STATE_ROOT", state.root))
        stack.enter_context(patch.object(parent, "DECISION_DOC", state.decision_doc))
        stack.enter_context(patch.object(parent, "BUDGET_ROOT", budget.root))
        stack.enter_context(patch.object(parent, "_durable_root",
                                         return_value=(root, ((1, 2, 3, 4),))))
        stack.enter_context(patch.object(parent, "_durable_ancestor_identity",
                                         return_value=((1, 2, 3, 4),)))
        stack.enter_context(patch.object(
            parent, "_canonical_json",
            side_effect=lambda path, **_kwargs: (
                json.loads(Path(path).read_text())
                if Path(path).exists() else {})))
        stack.enter_context(patch.object(parent, "_runtime_receipt",
                                         return_value={}))
        stack.enter_context(patch.object(parent, "prepare_execution_binding",
                                         return_value=binding))
        auth = json.loads(Path(args.authorization).read_text())
        stack.enter_context(patch.object(
            parent, "load_authorization",
            return_value=(auth, args.expected_authorization_sha256)))
        stack.enter_context(patch.object(parent, "process_command_sha256",
                                         return_value=("a" * 64, True)))
        stack.enter_context(patch.object(parent, "stable_process_command_sha256",
                                         return_value=COMMAND_SHA))
        stack.enter_context(patch.object(parent, "container_identity",
                                         return_value=(None, False)))
        class Control:
            def __init__(self, **_kwargs): pass
            def evidence(self, task, _tail):
                return {
                    "process": {"checked": True,
                                "pid": task["process_identity"]["pid"],
                                "command_sha256": task["process_identity"][
                                    "command_sha256"], "present": False},
                    "container": {"checked": True, "name": None,
                                  "label": None, "present": False},
                    "data": {"gate_status": "not_applicable",
                             "evidence_sha256": None},
                    "budget": {"checked": True, "task_id": task["task_id"],
                               "state": "none",
                               "snapshot_sha256": digest(budget.snapshot())},
                    "log_tail_sha256": "0" * 64,
                }
        stack.enter_context(patch.object(parent, "LocalProcessDockerControl", Control))
        stack.enter_context(patch.object(child, "_shared_preclaimed_runner",
                                         return_value=fake_runner))

    def test_live_success_claims_global_before_popen_and_leaves_review_pending(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            root, binding, state, budget, args = self.live_fixture(base)
            holder = {}
            class Process:
                pid = 4321
                returncode = None
                def poll(self):
                    if self.returncode is None:
                        watchdog = SupervisorWatchdog(root / "watchdog")
                        child.execute(
                            binding=binding, output=root / "snapshot",
                            watchdog=watchdog, pid=self.pid,
                            process_command_sha256=COMMAND_SHA,
                            budget_snapshot_sha256=digest(budget.snapshot()))
                        self.returncode = 0
                    return self.returncode
                def wait(self, timeout=None): return self.returncode
                def terminate(self): self.returncode = -15
                def kill(self): self.returncode = -9
            with ExitStack() as stack:
                self.live_patches(stack, root, binding, state, budget, args)
                def launch(command, **kwargs):
                    self.assertEqual(state.snapshot()["active_cycle"],
                                     adapter.ATTEMPT_ID)
                    self.assertEqual(kwargs["cwd"], parent.SOURCE_ROOT)
                    self.assertEqual(kwargs["env"], parent._child_environment())
                    self.assertEqual(command[1:3], ["-I", "-B"])
                    self.assertEqual(Path(command[3]), parent.CHILD_ENTRY)
                    self.assertNotIn("-m", command)
                    return Process()
                stack.enter_context(patch.object(parent.subprocess, "Popen",
                                                 side_effect=launch))
                result = parent.run(args)
            self.assertTrue(result["passed"])
            self.assertEqual(state.snapshot()["active_cycle"], adapter.ATTEMPT_ID)

    def test_live_popen_failure_consumes_id_and_closes_global_failed(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            root, binding, state, budget, args = self.live_fixture(base)
            with ExitStack() as stack:
                self.live_patches(stack, root, binding, state, budget, args)
                def fail_launch(*_args, **_kwargs):
                    self.assertEqual(state.snapshot()["active_cycle"],
                                     adapter.ATTEMPT_ID)
                    raise RuntimeError("launch failed")
                stack.enter_context(patch.object(parent.subprocess, "Popen",
                                                 side_effect=fail_launch))
                with self.assertRaisesRegex(RuntimeError, "launch failed"):
                    parent.run(args)
            snapshot = state.snapshot()
            self.assertIsNone(snapshot["active_cycle"])
            self.assertIn(adapter.ATTEMPT_ID, snapshot["completed_cycles"])
            failure = json.loads((root / "failure.json").read_text())
            self.assertFalse(failure["automatic_retry"])

    def test_authoritative_path_mismatch_rejects_before_popen(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            root, binding, state, budget, args = self.live_fixture(base)
            args.global_state_root = base / "attacker-state"
            with ExitStack() as stack:
                self.live_patches(stack, root, binding, state, budget, args)
                with patch.object(parent.subprocess, "Popen") as popen:
                    with self.assertRaisesRegex(ValueError, "authoritative"):
                        parent.run(args)
                popen.assert_not_called()

    def test_runtime_requires_pinned_executable_and_exact_canary_subset(self):
        current = {name: "1" * 64
                   for name in parent.bridge_canary_runner._SOURCE_FILES}
        value = {
            "schema": parent.canary_receipt.RUNTIME_SCHEMA,
            "python_executable": str(adapter.PINNED_PYTHON.resolve()),
            "python_version": parent.sys.version, "source_hashes": current,
            "source_hashes_sha256": digest(current),
            "provider_modules_loaded": False,
            "public_fetch_modules_loaded": False,
            "watched_fetch_modules_loaded": False,
            "network_modules_loaded_by_canary": False,
        }
        with patch.object(parent.protocol_source_release, "source_hashes",
                          return_value=current), patch.object(
                parent.sys, "executable", str(adapter.PINNED_PYTHON)):
            self.assertEqual(parent._runtime_receipt(value), value)
            changed = deepcopy(value)
            changed["source_hashes"].pop(next(iter(current)))
            changed["source_hashes_sha256"] = digest(changed["source_hashes"])
            with self.assertRaises(ValueError):
                parent._runtime_receipt(changed)

    def test_cleanup_reaps_popen_even_before_command_identity_stabilizes(self):
        class Process:
            pid = 4321
            returncode = None
            def poll(self): return self.returncode
            def terminate(self): self.returncode = -15
            def kill(self): self.returncode = -9
            def wait(self, timeout=None): return self.returncode
        with patch.object(parent, "container_identity",
                          return_value=(None, False)):
            cleanup = parent._terminal_cleanup(Process(), "")
        self.assertTrue(cleanup["cleanup_verified"])
        self.assertTrue(cleanup["process_absent"])

    def test_live_identity_container_and_budget_drift_are_terminal(self):
        for cause in ("identity", "container", "budget"):
            with self.subTest(cause=cause), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary).resolve()
                root, binding, state, budget, args = self.live_fixture(base)
                class Process:
                    pid = 4321
                    returncode = None
                    def poll(self): return self.returncode
                    def wait(self, timeout=None): return self.returncode
                    def terminate(self): self.returncode = -15
                    def kill(self): self.returncode = -9
                process = Process()
                with ExitStack() as stack:
                    self.live_patches(stack, root, binding, state, budget, args)
                    stack.enter_context(patch.object(parent.subprocess, "Popen",
                                                     return_value=process))
                    if cause != "identity":
                        stack.enter_context(patch.object(
                            parent, "process_command_sha256",
                            side_effect=lambda pid: (
                                ("a" * 64, True) if pid == os.getpid()
                                else ((COMMAND_SHA, True)
                                      if process.poll() is None
                                      else (None, False)))))
                    if cause == "container":
                        observations = iter(((parent.CONTAINER_LABEL, True),
                                             (parent.CONTAINER_LABEL, True),
                                             (None, False)))
                        stack.enter_context(patch.object(
                            parent, "container_identity",
                            side_effect=lambda _name: next(observations)))
                        stack.enter_context(patch.object(
                            parent.subprocess, "run",
                            return_value=SimpleNamespace(returncode=0)))
                    if cause == "budget":
                        class DriftControl:
                            def __init__(self, **_kwargs): pass
                            def evidence(self, *_args):
                                raise ValueError("budget drift")
                        stack.enter_context(patch.object(
                            parent, "LocalProcessDockerControl", DriftControl))
                    with self.assertRaises((RuntimeError, ValueError)):
                        parent.run(args)
                snapshot = state.snapshot()
                self.assertIsNone(snapshot["active_cycle"])
                self.assertIn(adapter.ATTEMPT_ID,
                              snapshot["completed_cycles"])
                failure = json.loads((root / "failure.json").read_text())
                self.assertFalse(failure["same_id_retry_allowed"])

    def test_cleanup_stops_only_exact_task_label(self):
        class Process:
            pid = 4321
            returncode = 0
            def poll(self): return self.returncode
        exact = iter(((parent.CONTAINER_LABEL, True), (None, False)))
        with patch.object(parent, "process_command_sha256",
                          return_value=(None, False)), patch.object(
                parent, "container_identity",
                side_effect=lambda _name: next(exact)), patch.object(
                parent.subprocess, "run",
                return_value=SimpleNamespace(returncode=0)) as stop:
            receipt = parent._terminal_cleanup(Process(), COMMAND_SHA)
        self.assertTrue(receipt["cleanup_verified"])
        stop.assert_called_once_with(
            ["docker", "stop", "--time", "2", parent.CONTAINER_NAME],
            capture_output=True, text=True, timeout=8, check=False)

        with patch.object(parent, "process_command_sha256",
                          return_value=(None, False)), patch.object(
                parent, "container_identity",
                return_value=("wrong-task", True)), patch.object(
                parent.subprocess, "run") as stop:
            receipt = parent._terminal_cleanup(Process(), COMMAND_SHA)
        self.assertFalse(receipt["cleanup_verified"])
        self.assertIn("container_identity_mismatch", receipt["errors"])
        stop.assert_not_called()
    def test_parent_claims_before_fake_fetch_child_does_not_close_parent_does(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            root = base / adapter.ATTEMPT_ID
            with patch.object(adapter, "RUN_ROOT", root):
                binding, _, _ = make_binding(base)
                result = offline(binding, fake_runner)
            self.assertTrue(result["passed"])
            records = [json.loads(line) for line in
                       (root / "watchdog" / "journal.jsonl").read_text().splitlines()]
            self.assertEqual([item["event"] for item in records],
                             ["initialize", "task_claim", "heartbeat",
                              "heartbeat", "task_close"])
            self.assertEqual(records[2]["payload"]["progress_sha256"],
                             digest({"task": binding["task"],
                                     "admission": binding["admission"]}))
            self.assertEqual(records[-1]["payload"]["result_sha256"],
                             result["receipt_file_sha256"])

    def test_child_requires_exact_preexisting_claim_and_never_self_claims(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            root = base / adapter.ATTEMPT_ID
            with patch.object(adapter, "RUN_ROOT", root):
                binding, _, _ = make_binding(base)
                root.mkdir(mode=0o700)
                watchdog = SupervisorWatchdog(root / "watchdog")
                watchdog.initialize()
                calls = []
                def observed(**kwargs):
                    calls.append(True)
                    if kwargs["watchdog"].snapshot()["active_task"] is None:
                        raise ValueError("missing claim")
                    return fake_runner(**kwargs)
                with self.assertRaises(ValueError):
                    with patch.object(child, "_shared_preclaimed_runner",
                                      return_value=observed):
                        child.execute(
                            binding=binding, output=root / "snapshot",
                            watchdog=watchdog, pid=os.getpid(),
                            process_command_sha256=COMMAND_SHA,
                            budget_snapshot_sha256=BUDGET_SHA)
                self.assertEqual(calls, [True])
                self.assertIsNone(watchdog.snapshot()["active_task"])

    def test_mutated_receipt_rejects_before_parent_close(self):
        def attacked(**kwargs):
            receipt = fake_runner(**kwargs)
            receipt["redirects_followed"] = 1
            return receipt
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            root = base / adapter.ATTEMPT_ID
            with patch.object(adapter, "RUN_ROOT", root):
                binding, _, _ = make_binding(base)
                with self.assertRaises(ValueError):
                    offline(binding, attacked)
            state = SupervisorWatchdog(root / "watchdog").snapshot()
            self.assertEqual(state["active_task"]["status"], "repair_pending")
            self.assertEqual(len(state["incidents"]), 1)

    def test_live_cli_has_no_transport_and_child_env_is_sanitized(self):
        destinations = {action.dest for action in parent.parser()._actions}
        self.assertNotIn("transport", destinations)
        self.assertNotIn("url", destinations)
        environment = parent._child_environment()
        forbidden = {
            "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
            "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE",
            "CURL_CA_BUNDLE", "PYTHONPATH", "PYTHONHOME",
            "TINKER_API_KEY", "OPENAI_API_KEY",
        }
        self.assertTrue(forbidden.isdisjoint(environment))
        command = parent._child_command(
            binding_path=Path("/tmp/binding"), binding_sha256="1" * 64,
            output=Path("/tmp/output"), watchdog_root=Path("/tmp/watchdog"),
            claim_path=Path("/tmp/claim"), budget_snapshot_sha256="2" * 64)
        self.assertEqual(command[1:3], ["-I", "-B"])
        self.assertEqual(Path(command[3]), parent.CHILD_ENTRY)
        self.assertNotIn("-m", command)
        child_source = Path(child.__file__).read_text()
        self.assertIn("if __package__ in {None, \"\"}", child_source)
        self.assertIn("Path(__file__).resolve().parents[1]", child_source)

    def test_live_constants_are_home_derived_and_authoritative(self):
        self.assertNotIn(str(Path.home()), Path(parent.__file__).read_text())
        expected = (adapter.MARKET_RSI_ROOT / "self-evolving-v18-local" /
                    "research" / "market_rsi" / "artifacts" /
                    "supervisor-global-state-20260917-01")
        self.assertEqual(parent.GLOBAL_STATE_ROOT, expected)
        self.assertEqual(parent.DECISION_DOC,
                         adapter.MARKET_RSI_ROOT / "control" /
                         "RESEARCH_STATE.md")
        self.assertEqual(parent.BUDGET_ROOT,
                         adapter.MARKET_RSI_ROOT /
                         "budget-authoritative-20260916-01")

    def test_binding_and_claim_mutations_fail_closed(self):
        for section in ("task", "admission"):
            with self.subTest(section=section), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary).resolve()
                root = base / adapter.ATTEMPT_ID
                with patch.object(adapter, "RUN_ROOT", root):
                    binding, _, _ = make_binding(base)
                    changed = deepcopy(binding)
                    changed[section]["extra"] = False
                    changed[section + "_canonical_sha256"] = digest(
                        changed[section])
                    with self.assertRaises(ValueError):
                        offline(changed, fake_runner)


if __name__ == "__main__":
    unittest.main()
