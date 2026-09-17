"""Offline fake-SDK checks only; no real E2B, GLM or budget call."""
from __future__ import annotations

import hashlib
import json
import queue
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from market_rsi import canonical, digest
from supervisor_harness import directional_guest_worker as guest_worker
from supervisor_harness import one_b_live_adapter as adapter
from supervisor_harness.directional_handoff import B_ACK_DIR, B_EVENT_DIR, B_ORDER_DIR
from supervisor_harness.global_state_gate import SupervisorGlobalState


GUEST_SOURCE = Path(__file__).with_name("directional_guest_worker.py")


class FakeClock:
    def __init__(self):
        self.now = 1_000_000_000

    def __call__(self):
        self.now += 10_000_000
        return self.now


class FakeSession:
    def __init__(self, sandbox, command):
        self.sandbox = sandbox
        self.command = command
        self.messages = []

    def next_message(self, _timeout_seconds):
        return self.messages.pop(0) if self.messages else None

    def wait(self, _timeout_seconds):
        return {"exit_code": 0, "stdout_bytes": 0, "stderr_bytes": 0,
                "stdout_sha256": "0" * 64, "stderr_sha256": "0" * 64}


class FakeFiles:
    def __init__(self, sandbox):
        self.sandbox = sandbox
        self.contents = {}
        self.writes = []
        self.renames = []
        self.dirs = set()

    def write(self, path, value, *, request_timeout):
        assert request_timeout == adapter.FILE_REQUEST_TIMEOUT_SECONDS
        if path in self.contents:
            raise ValueError("fake file overwritten")
        self.contents[path] = value
        self.writes.append(path)

    def read(self, path, *, request_timeout):
        assert request_timeout == adapter.FILE_REQUEST_TIMEOUT_SECONDS
        return self.contents[path]

    def make_dir(self, path, *, request_timeout):
        assert request_timeout == adapter.FILE_REQUEST_TIMEOUT_SECONDS
        if path in self.dirs:
            return False
        self.dirs.add(path)
        return True

    def rename(self, source, destination, *, request_timeout):
        assert request_timeout == adapter.FILE_REQUEST_TIMEOUT_SECONDS
        if destination in self.contents or source not in self.contents:
            raise ValueError("fake rename would overwrite or lose source")
        self.contents[destination] = self.contents.pop(source)
        self.renames.append((source, destination))
        self.sandbox.publish(destination)


class FakeSandbox:
    def __init__(self, mode="ok"):
        self.sandbox_id = "one-persistent-B"
        self.files = FakeFiles(self)
        self.mode = mode
        self.session = None
        self.kill_calls = 0
        self.killed = False
        self.ttl_seconds = 180
        self.cycle_id = "cycle-one-b-01"

    def get_info(self, *, request_timeout):
        assert request_timeout == adapter.FILE_REQUEST_TIMEOUT_SECONDS
        return SimpleNamespace(
            sandbox_id=self.sandbox_id,
            end_at=datetime.now(timezone.utc) + timedelta(seconds=self.ttl_seconds),
            lifecycle=adapter.LIFECYCLE, network=adapter.NETWORK,
            allow_internet_access=False,
            metadata={"experiment_id": "market-rsi-directional-one-b",
                      "job_id": self.cycle_id, "role": "researcher"},
            cpu_count=2, memory_mb=2048, volume_mounts=[])

    def publish(self, path):
        assert self.session is not None
        assert path.startswith(B_ORDER_DIR + "/")
        sequence = int(Path(path).stem)
        order = json.loads(self.files.contents[path])
        text_sha = hashlib.sha256(order["public_text"].encode()).hexdigest()
        ack = {"schema": "market_directional_ack_v1",
               "cycle_id": order["cycle_id"], "sequence": sequence,
               "order_sha256": digest(order)}
        event = {"schema": "market_directional_tool_event_v1",
                 "cycle_id": order["cycle_id"], "sequence": sequence,
                 "task_id": order["task_id"], "order_sha256": digest(order),
                 "tool_name": "hash_public_text", "input_sha256": text_sha,
                 "output_sha256": text_sha, "status": "ok"}
        if self.mode == "wrong_ack" and sequence == 0:
            ack["order_sha256"] = "0" * 64
        if self.mode == "wrong_event" and sequence == 0:
            event["output_sha256"] = "0" * 64
        self.files.contents[f"{B_ACK_DIR}/{sequence:03d}.json"] = canonical(ack)
        self.files.contents[f"{B_EVENT_DIR}/{sequence:03d}.json"] = canonical(event)
        milestone = lambda kind: {"schema": adapter.MILESTONE_SCHEMA,
                                  "sequence": sequence, "kind": kind}
        self.session.messages.append(milestone("ack"))
        if self.mode == "duplicate_ack" and sequence == 0:
            self.session.messages.append(milestone("ack"))
        if self.mode != "missing_event" or sequence != 0:
            self.session.messages.append(milestone("event"))
        if self.mode == "extra_milestone" and sequence == 19:
            self.session.messages.append(milestone("event"))

    def kill(self):
        self.kill_calls += 1
        self.killed = True
        return self.mode != "kill_false"


class BridgeFiles:
    """Map fake SDK guest paths into a local temporary filesystem."""

    def __init__(self, sandbox, root):
        self.sandbox = sandbox
        self.root = root
        self.script_text = None
        self.renames = []

    def _path(self, path):
        assert path.startswith(adapter.GUEST_ROOT + "/")
        return self.root / path[len(adapter.GUEST_ROOT) + 1:]

    def write(self, path, value, *, request_timeout):
        assert request_timeout == adapter.FILE_REQUEST_TIMEOUT_SECONDS
        if path == adapter.GUEST_SCRIPT:
            self.script_text = value
            return
        target = self._path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value)

    def read(self, path, *, request_timeout):
        assert request_timeout == adapter.FILE_REQUEST_TIMEOUT_SECONDS
        if path == adapter.GUEST_SCRIPT:
            return self.script_text
        value = self._path(path).read_text()
        if self.sandbox.mode == "bad_ack_read" and path == f"{B_ACK_DIR}/000.json":
            ack = json.loads(value)
            ack["order_sha256"] = "0" * 64
            return canonical(ack)
        return value

    def make_dir(self, path, *, request_timeout):
        assert request_timeout == adapter.FILE_REQUEST_TIMEOUT_SECONDS
        target = self._path(path)
        existed = target.exists()
        target.mkdir(parents=True, exist_ok=True)
        return not existed

    def rename(self, source, destination, *, request_timeout):
        assert request_timeout == adapter.FILE_REQUEST_TIMEOUT_SECONDS
        old, new = self._path(source), self._path(destination)
        new.parent.mkdir(parents=True, exist_ok=True)
        if new.exists():
            raise ValueError("bridge destination already exists")
        old.rename(new)
        self.renames.append((source, destination))


class LocalGuestSession:
    """One actual guest run in a local thread, without an E2B call."""

    def __init__(self, sandbox, command):
        assert "--total-timeout 120" in command
        self.sandbox = sandbox
        self.messages = queue.Queue()
        self.done = threading.Event()
        self.stop_requested = threading.Event()
        self.error = None
        self.patcher = patch.object(guest_worker, "_milestone", self._emit)
        self.patcher.start()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _emit(self, sequence, kind):
        self.messages.put({"schema": adapter.MILESTONE_SCHEMA,
                           "sequence": sequence, "kind": kind})

    def _sleep(self, seconds):
        if self.stop_requested.is_set():
            raise RuntimeError("local guest stopped")
        time.sleep(seconds)

    def _run(self):
        try:
            guest_worker.run(self.sandbox.files.root, poll_interval=.001,
                             per_order_timeout=5, total_timeout=30,
                             sleep=self._sleep)
        except Exception as exc:
            self.error = exc
        finally:
            self.done.set()

    def next_message(self, timeout_seconds):
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                return self.messages.get_nowait()
            except queue.Empty:
                if self.done.is_set():
                    if self.error is not None:
                        raise self.error
                    return None
                if time.monotonic() >= deadline:
                    return None
                time.sleep(.001)

    def wait(self, timeout_seconds):
        if not self.done.wait(timeout_seconds):
            raise TimeoutError("local guest did not finish")
        self.patcher.stop()
        if self.error is not None:
            raise self.error
        return {"exit_code": 0, "stdout_bytes": 0, "stderr_bytes": 0,
                "stdout_sha256": "0" * 64, "stderr_sha256": "0" * 64}

    def stop(self):
        self.stop_requested.set()
        self.done.wait(2)
        self.patcher.stop()
        return self.done.is_set()


class BridgeSandbox(FakeSandbox):
    def __init__(self, root, mode="ok"):
        super().__init__(mode)
        self.files = BridgeFiles(self, root)
        self.cycle_id = "cycle-bridge-01"

    def kill(self):
        self.kill_calls += 1
        self.killed = True
        return self.session is None or self.session.stop()


class OneBAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        decision = self.root / "decision.md"
        decision.write_text("fixed synthetic decision\n")
        self.state = SupervisorGlobalState(self.root / "state", decision)
        snapshot = self.state.initialize()
        self.state.claim("cycle-one-b-01",
                         expected_head_sha256=snapshot["head_sha256"],
                         source_sha256="b" * 64, prior_canary_sha256="c" * 64)
        self.clock = FakeClock()
        self.sandbox = FakeSandbox()
        self.creates = 0
        self.account_checks = []

    def _create(self):
        self.creates += 1
        return self.sandbox

    def _account(self, expected_id):
        self.account_checks.append(expected_id)
        clear = (expected_id is None and self.creates == 0) or self.sandbox.killed
        if self.sandbox.mode == "post_account_false" and expected_id is not None:
            clear = False
        return {"clear": clear, "checked_sandbox_id": expected_id,
                "active_market_rsi_ids": [] if clear else [self.sandbox.sandbox_id]}

    def _launch(self, sandbox, command):
        self.assertIs(sandbox, self.sandbox)
        self.assertIn("--total-timeout 120", command)
        session = FakeSession(sandbox, command)
        sandbox.session = session
        return session

    def _run(self):
        return adapter.run_one_b_transport(
            state=self.state, cycle_id="cycle-one-b-01",
            input_sha256="a" * 64, public_source="fixed public synthetic source",
            guest_source_path=GUEST_SOURCE, receipt_root=self.root / "transport",
            create_sandbox=self._create, check_account_clear=self._account,
            launch_guest=self._launch, clock_ns=self.clock)

    def test_twenty_same_source_tasks_one_b_exact_cleanup(self):
        receipt = self._run()
        self.assertTrue(receipt["friction_criterion_passed"])
        self.assertFalse(receipt["provider_latency_proven"])
        self.assertEqual(self.creates, 1)
        self.assertEqual(self.sandbox.kill_calls, 1)
        self.assertEqual(self.account_checks, [None, "one-persistent-B"])
        self.assertEqual(len(self.sandbox.files.renames), 20)
        self.assertEqual([dst for _, dst in self.sandbox.files.renames], [
            f"{B_ORDER_DIR}/{n:03d}.json" for n in range(20)])
        self.assertEqual(len({json.loads(self.sandbox.files.contents[
            f"{B_ORDER_DIR}/{n:03d}.json"])["input_sha256"]
            for n in range(20)}), 1)
        self.assertEqual(len({json.loads(self.sandbox.files.contents[
            f"{B_ORDER_DIR}/{n:03d}.json"])["public_text"]
            for n in range(20)}), 20)
        summary = json.loads((self.root / "transport/handoff/summary.json").read_text())
        self.assertEqual(summary["sample_count"], 20)
        self.assertEqual(len(json.loads((self.root / "transport/milestones.json").read_text())[
            "items"]), 40)
        self.assertTrue(json.loads((self.root / "transport/cleanup.json").read_text())[
            "account_clear"])

    def test_wrong_ack_hash_fails_before_event_read_and_kills_b(self):
        self.sandbox.mode = "wrong_ack"
        with self.assertRaises(ValueError):
            self._run()
        self.assertEqual(self.sandbox.kill_calls, 1)
        self.assertFalse((self.root / "transport/handoff/000-event.json").exists())

    def test_wrong_event_hash_never_reaches_a(self):
        self.sandbox.mode = "wrong_event"
        with self.assertRaises(ValueError):
            self._run()
        self.assertFalse((self.root / "transport/handoff/000-a-read.json").exists())
        self.assertEqual(self.sandbox.kill_calls, 1)

    def test_duplicate_ack_hint_is_terminal(self):
        self.sandbox.mode = "duplicate_ack"
        with self.assertRaisesRegex(ValueError, "duplicate, out of order"):
            self._run()
        self.assertEqual(len(self.sandbox.files.renames), 1)
        self.assertEqual(self.sandbox.kill_calls, 1)

    def test_missing_event_hint_times_out_and_kills(self):
        self.sandbox.mode = "missing_event"
        with self.assertRaises(TimeoutError):
            self._run()
        self.assertEqual(self.sandbox.kill_calls, 1)
        failure = json.loads((self.root / "transport/failure.json").read_text())
        self.assertEqual(failure["error_type"], "TimeoutError")

    def test_extra_milestone_after_twenty_fails(self):
        self.sandbox.mode = "extra_milestone"
        with self.assertRaisesRegex(ValueError, "extra guest milestone"):
            self._run()
        self.assertEqual(self.sandbox.kill_calls, 1)

    def test_callback_to_a_delay_fails_even_when_file_read_summary_passes(self):
        real_milestone = adapter._milestone

        def delayed_callback(session, sequence, kind, clock_ns):
            value = real_milestone(session, sequence, kind, clock_ns)
            if kind == "event" and sequence == 19:
                value["host_callback_ns"] -= 5_000_000_001
            return value

        with patch.object(adapter, "_milestone", side_effect=delayed_callback):
            with self.assertRaisesRegex(RuntimeError, "callback-to-A"):
                self._run()
        summary = json.loads((self.root / "transport/handoff/summary.json").read_text())
        self.assertTrue(summary["friction_criterion_passed"])
        self.assertFalse((self.root / "transport/result.json").exists())
        self.assertEqual(self.sandbox.kill_calls, 1)

    def test_unacknowledged_kill_fails_even_if_account_says_clear(self):
        self.sandbox.mode = "kill_false"
        with self.assertRaisesRegex(RuntimeError, "cleanup"):
            self._run()
        self.assertEqual(self.sandbox.kill_calls, 1)
        self.assertFalse((self.root / "transport/result.json").exists())

    def test_negative_account_clear_fails_after_kill(self):
        self.sandbox.mode = "post_account_false"
        with self.assertRaisesRegex(RuntimeError, "cleanup"):
            self._run()
        self.assertEqual(self.sandbox.kill_calls, 1)
        self.assertFalse((self.root / "transport/result.json").exists())

    def test_short_ttl_fails_before_guest_launch(self):
        self.sandbox.ttl_seconds = 100
        with self.assertRaises(ValueError):
            self._run()
        self.assertIsNone(self.sandbox.session)
        self.assertEqual(self.sandbox.kill_calls, 1)

    def test_missing_network_echo_fails_before_guest_launch(self):
        original = self.sandbox.get_info

        def missing_echo(*, request_timeout):
            info = original(request_timeout=request_timeout)
            info.network = None
            return info

        self.sandbox.get_info = missing_echo
        with self.assertRaises(ValueError):
            self._run()
        self.assertIsNone(self.sandbox.session)
        self.assertEqual(self.sandbox.kill_calls, 1)

    def test_missing_optional_allow_out_is_diagnostic_not_isolation_pass(self):
        original = self.sandbox.get_info

        def omitted_allow_out(*, request_timeout):
            info = original(request_timeout=request_timeout)
            info.network = {"deny_out": ["0.0.0.0/0"],
                            "allow_public_traffic": False}
            return info

        self.sandbox.get_info = omitted_allow_out
        result = self._run()
        self.assertTrue(result["friction_criterion_passed"])
        self.assertFalse(result["policy_echo_accepted"])
        self.assertTrue(result["synthetic_transport_diagnostic_only"])
        self.assertFalse(result["isolation_proven"])
        policy = json.loads((self.root / "transport/sandbox-ttl.json").read_text())
        self.assertEqual(policy["missing_policy_fields"], ["allow_out"])
        self.assertIsNone(policy["network_observed"]["allow_out"])

    def test_explicit_opposite_allow_out_rejected_before_guest_launch(self):
        original = self.sandbox.get_info

        def contradictory_allow_out(*, request_timeout):
            info = original(request_timeout=request_timeout)
            info.network = {"allow_out": ["1.1.1.1/32"],
                            "deny_out": ["0.0.0.0/0"],
                            "allow_public_traffic": False}
            return info

        self.sandbox.get_info = contradictory_allow_out
        with self.assertRaises(ValueError):
            self._run()
        self.assertIsNone(self.sandbox.session)
        self.assertEqual(self.sandbox.kill_calls, 1)

    def test_pre_account_failure_prevents_create(self):
        def denied(_expected_id):
            return {"clear": False, "checked_sandbox_id": None,
                    "active_market_rsi_ids": ["prior-B"]}

        with self.assertRaises(RuntimeError):
            adapter.run_one_b_transport(
                state=self.state, cycle_id="cycle-one-b-01",
                input_sha256="a" * 64, public_source="public source",
                guest_source_path=GUEST_SOURCE, receipt_root=self.root / "transport",
                create_sandbox=self._create, check_account_clear=denied,
                launch_guest=self._launch, clock_ns=self.clock)
        self.assertEqual(self.creates, 0)


class ActualGuestBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        decision = self.root / "decision.md"
        decision.write_text("fixed bridge decision\n")
        self.state = SupervisorGlobalState(self.root / "state", decision)
        snapshot = self.state.initialize()
        self.state.claim("cycle-bridge-01",
                         expected_head_sha256=snapshot["head_sha256"],
                         source_sha256="b" * 64, prior_canary_sha256="c" * 64)
        self.sandbox = BridgeSandbox(self.root / "fake-guest")
        self.creates = 0

    def _run(self):
        def create():
            self.creates += 1
            return self.sandbox

        def account(expected_id):
            clear = expected_id is None or self.sandbox.killed
            return {"clear": clear, "checked_sandbox_id": expected_id,
                    "active_market_rsi_ids": [] if clear else [self.sandbox.sandbox_id]}

        def launch(sandbox, command):
            self.assertIs(sandbox, self.sandbox)
            session = LocalGuestSession(sandbox, command)
            sandbox.session = session
            return session

        return adapter.run_one_b_transport(
            state=self.state, cycle_id="cycle-bridge-01",
            input_sha256="a" * 64, public_source="one fixed public source",
            guest_source_path=GUEST_SOURCE, receipt_root=self.root / "transport",
            create_sandbox=create, check_account_clear=account,
            launch_guest=launch)

    def test_actual_guest_processes_all_twenty_orders_in_one_local_session(self):
        result = self._run()
        self.assertTrue(result["friction_criterion_passed"])
        self.assertFalse(result["provider_latency_proven"])
        self.assertEqual(self.creates, 1)
        self.assertEqual(self.sandbox.kill_calls, 1)
        self.assertEqual(self.sandbox.files.script_text, GUEST_SOURCE.read_text())
        self.assertEqual(len(self.sandbox.files.renames), 20)
        self.assertEqual(len(json.loads((self.root / "transport/milestones.json").read_text())[
            "items"]), 40)
        summary = json.loads((self.root / "transport/handoff/summary.json").read_text())
        self.assertEqual(summary["sample_count"], 20)
        self.assertTrue((self.root / "fake-guest/events/019.json").is_file())

    def test_actual_guest_ack_read_tamper_stops_before_a_visibility(self):
        self.sandbox.mode = "bad_ack_read"
        with self.assertRaises(ValueError):
            self._run()
        self.assertEqual(self.creates, 1)
        self.assertEqual(self.sandbox.kill_calls, 1)
        self.assertFalse((self.root / "transport/handoff/000-a-read.json").exists())
        failure = json.loads((self.root / "transport/failure.json").read_text())
        self.assertEqual(failure["stage"], "task_000")


class GuestStdoutParserTests(unittest.TestCase):
    def test_split_chunks_are_reassembled(self):
        line = canonical({"schema": adapter.MILESTONE_SCHEMA,
                          "sequence": 0, "kind": "ack"}) + "\n"

        class Commands:
            def run(self, _command, *, on_stdout, on_stderr, timeout):
                self.timeout = timeout
                on_stdout(line[:17])
                on_stdout(line[17:])
                on_stderr("diagnostic")
                return SimpleNamespace(exit_code=0)

        sandbox = SimpleNamespace(commands=Commands())
        session = adapter.E2BGuestSession(sandbox, "fake guest")
        self.assertEqual(session.next_message(1)["kind"], "ack")
        self.assertEqual(session.wait(1)["exit_code"], 0)
        self.assertIsNone(session.next_message(0))
        self.assertEqual(sandbox.commands.timeout,
                         adapter.PROCESS_STREAM_TIMEOUT_SECONDS)

    def test_duplicate_json_member_is_rejected(self):
        class Commands:
            def run(self, _command, *, on_stdout, on_stderr, timeout):
                on_stdout('{"schema":"x","schema":"y","sequence":0,"kind":"ack"}\n')
                return SimpleNamespace(exit_code=0)

        session = adapter.E2BGuestSession(SimpleNamespace(commands=Commands()), "fake")
        with self.assertRaisesRegex(ValueError, "duplicate guest milestone"):
            session.wait(1)


class PinnedFactoryTests(unittest.TestCase):
    def test_exact_create_kwargs_keep_key_on_host(self):
        class SandboxClass:
            calls = []

            @classmethod
            def create(cls, **kwargs):
                cls.calls.append(kwargs)
                return "fake sandbox"

        with patch.object(adapter, "_require_local_sdk_runtime") as runtime:
            result = adapter.create_one_b_sandbox(
                SandboxClass, key="HOST-ONLY-KEY", cycle_id="cycle-one-b-01")
        self.assertEqual(result, "fake sandbox")
        runtime.assert_called_once()
        self.assertEqual(len(SandboxClass.calls), 1)
        kwargs = SandboxClass.calls[0]
        self.assertEqual(kwargs["timeout"], 180)
        self.assertIs(kwargs["secure"], True)
        self.assertIs(kwargs["allow_internet_access"], False)
        self.assertEqual(kwargs["network"], adapter.NETWORK)
        self.assertEqual(kwargs["lifecycle"], adapter.LIFECYCLE)
        self.assertEqual(kwargs["envs"], {})
        self.assertEqual(kwargs["volume_mounts"], {})
        self.assertEqual(kwargs["metadata"], {
            "experiment_id": "market-rsi-directional-one-b",
            "job_id": "cycle-one-b-01", "role": "researcher"})
        self.assertNotIn("HOST-ONLY-KEY", canonical(kwargs["envs"]))


if __name__ == "__main__":
    unittest.main()
