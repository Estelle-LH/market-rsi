from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import minimal_prediction_loop.container_adapter as adapter_module
from minimal_prediction_loop.container_adapter import (
    CANDIDATE_PATH,
    GUEST_PATH,
    ContainerAdapterError,
    DockerClientBinding,
    DockerJSONLTransport,
    TransportLifecycleError,
    _strict_json_object,
    docker_prediction_command,
    freeze_docker_client,
    run_local_candidate_prediction,
    verify_adapter_terminal,
)
from minimal_prediction_loop.prediction_protocol import (
    LabelFreePredictionProtocol,
    PredictionProtocolError,
    prediction_submission,
)


BASE_MS = 1_800_000_000_000


def rows(count: int = 3) -> list[dict]:
    return [
        {
            "event_id": f"synthetic-event-{index}",
            "market_id": f"synthetic-market-{index}",
            "cutoff_ms": BASE_MS + index,
            "feature_available_ms": BASE_MS + index,
            "market_probability": 0.3 + index / 10,
        }
        for index in range(count)
    ]


def absent_control(command, **_kwargs):
    if command[1:3] == ["context", "show"]:
        return subprocess.CompletedProcess(command, 0, stdout="synthetic-context\n", stderr="")
    if command[1:2] == ["info"]:
        return subprocess.CompletedProcess(
            command, 0,
            stdout="synthetic-id|synthetic-daemon|1.0|linux|arm64|/synthetic/docker\n",
            stderr="",
        )
    if command[1:2] == ["inspect"]:
        name = command[-1]
        return subprocess.CompletedProcess(
            command, 1, stdout="", stderr=f"Error: No such object: {name}\n"
        )
    raise AssertionError(f"unexpected control command: {command}")


class FakeTransport:
    def __init__(self, command, artifact_root, *, probability=0.6,
                 process=None, on_exchange=None, on_finish=None,
                 on_quiet=None, response=None):
        self.command = list(command)
        self.artifact_root = Path(artifact_root)
        self.probability = probability
        self.process = process or {
            "process_reaped": True,
            "exit_code": 0,
            "responses": 3,
            "stdout_bytes": 1,
            "stdout_sha256": "a" * 64,
            "stderr_bytes": 0,
            "stderr_sha256": hashlib.sha256(b"").hexdigest(),
        }
        self.on_exchange = on_exchange
        self.on_finish = on_finish
        self.on_quiet = on_quiet
        self.response = response
        self.releases = []
        self.aborted = False

    def exchange(self, release, _timeout):
        self.releases.append(dict(release))
        if self.on_exchange:
            self.on_exchange(release, len(self.releases))
        if self.response is not None:
            return self.response(dict(release))
        return prediction_submission(release, self.probability)

    def finish(self):
        if self.on_finish:
            self.on_finish()
        value = dict(self.process)
        value["responses"] = value.get("responses", len(self.releases))
        return value

    def assert_quiet(self):
        if self.on_quiet:
            self.on_quiet()

    def abort(self):
        self.aborted = True
        return {
            "process_reaped": True,
            "exit_code": -9,
            "wait_timed_out": False,
        }


class AdapterFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.candidate = self.root / "candidate.py"
        self.candidate.write_text(
            "def predict(public_row):\n    return public_row['market_probability']\n"
        )
        self.candidate_hash = hashlib.sha256(self.candidate.read_bytes()).hexdigest()
        self.docker = self.root / "docker-client"
        self.docker.write_text("#!/bin/sh\nexit 99\n")
        self.docker.chmod(0o755)
        self.docker_environment = {
            "PATH": "/synthetic/bin",
            "HOME": str(self.root),
            "DOCKER_HOST": "unix:///synthetic-docker.sock",
        }
        self.docker_binding = freeze_docker_client(
            run=absent_control,
            docker_cli=self.docker,
            environment=self.docker_environment,
            expected_cli_sha256=hashlib.sha256(self.docker.read_bytes()).hexdigest(),
        )
        self.protocol_root = self.root / "protocol"
        self.artifacts = self.root / "artifacts"
        self.artifacts.mkdir()
        self.created = []

    def execute(self, *, run_key="synthetic-adapter-test", public_rows=None,
                control=absent_control, factory=None, artifact_name="run-1",
                candidate=None, candidate_hash=None):
        if factory is None:
            def factory(command, artifact_root):
                transport = FakeTransport(command, artifact_root)
                self.created.append(transport)
                return transport
        return run_local_candidate_prediction(
            protocol_root=self.protocol_root,
            artifact_root=self.artifacts / artifact_name,
            run_key=run_key,
            candidate_source=candidate or self.candidate,
            expected_candidate_sha256=candidate_hash or self.candidate_hash,
            public_rows=rows() if public_rows is None else public_rows,
            allow_temporary=True,
            transport_factory=factory,
            control_run=control,
            docker_binding=self.docker_binding,
        )

    def verify(self, artifact_name: str, run_key: str, *,
               allow_test_mode: bool = True, public_rows=None):
        return verify_adapter_terminal(
            self.artifacts / artifact_name,
            protocol_root=self.protocol_root,
            run_key=run_key,
            candidate_sha256=self.candidate_hash,
            public_rows=rows() if public_rows is None else public_rows,
            allow_test_mode=allow_test_mode,
        )


class AdapterTests(AdapterFixture):
    def test_success_is_synthetic_label_free_and_has_zero_authority(self):
        receipt = self.execute()
        self.assertEqual(receipt["protocol_completion"]["predictions"], 3)
        self.assertTrue(receipt["synthetic_only"])
        self.assertTrue(receipt["test_mode"])
        for field in ("scored", "real_data_admitted", "real_isolation_admitted",
                      "promotion_authorized"):
            self.assertFalse(receipt[field])
        self.assertTrue(receipt["candidate_terminated_before_protocol_completion"])
        self.assertTrue(receipt["exact_container_absent_before_protocol_completion"])
        saved = json.loads((self.artifacts / "run-1/adapter-receipt.json").read_text())
        self.assertEqual(saved, receipt)
        self.assertTrue((self.artifacts / "run-1/adapter-success.json").is_file())
        self.assertEqual(
            self.verify("run-1", "synthetic-adapter-test"),
            receipt,
        )
        with self.assertRaisesRegex(ContainerAdapterError, "test-mode"):
            self.verify(
                "run-1", "synthetic-adapter-test", allow_test_mode=False
            )
        self.assertEqual(len(self.created[0].releases), 3)
        for release in self.created[0].releases:
            self.assertNotIn("outcome", release)
            self.assertNotIn("outcome_available_ms", release)
            self.assertNotIn("evaluator_path", release)

    def test_each_row_is_visible_only_after_prior_durable_commit(self):
        def factory(command, artifact_root):
            def check(release, number):
                run_dirs = list(self.protocol_root.glob("run-*"))
                self.assertEqual(len(run_dirs), 1)
                journal = (run_dirs[0] / "journal.jsonl").read_text().splitlines()
                self.assertEqual(len(journal), 2 * (number - 1) + 1)
                if number > 1:
                    self.assertEqual(json.loads(journal[-2])["event"],
                                     "prediction_committed")
                self.assertEqual(json.loads(journal[-1])["event"], "row_released")
                self.assertEqual(release["sequence"], number - 1)
            transport = FakeTransport(command, artifact_root, on_exchange=check)
            self.created.append(transport)
            return transport
        self.execute(factory=factory)

    def test_forbidden_or_real_rows_fail_before_process_creation(self):
        for variant in ("outcome", "future_alias", "real_identity"):
            candidate_rows = rows()
            if variant == "real_identity":
                candidate_rows[0]["event_id"] = "real-event"
            else:
                candidate_rows[0][variant] = 1
            calls = []
            with self.subTest(variant=variant), self.assertRaises(
                    (ContainerAdapterError, PredictionProtocolError)):
                self.execute(public_rows=candidate_rows,
                             artifact_name=f"bad-{variant}",
                             factory=lambda *args: calls.append(args))
            self.assertEqual(calls, [])

    def test_synthetic_run_key_is_mandatory(self):
        with self.assertRaisesRegex(ContainerAdapterError, "synthetic run key"):
            self.execute(run_key="real-run")
        self.assertEqual(self.created, [])

    def test_candidate_hash_symlink_and_fifo_are_rejected(self):
        with self.assertRaisesRegex(ContainerAdapterError, "hash mismatch"):
            self.execute(candidate_hash="0" * 64, artifact_name="bad-hash")
        link = self.root / "candidate-link.py"
        link.symlink_to(self.candidate)
        with self.assertRaisesRegex(ContainerAdapterError, "non-symlink"):
            self.execute(candidate=link, artifact_name="bad-link")
        fifo = self.root / "candidate-fifo.py"
        os.mkfifo(fifo)
        with self.assertRaisesRegex(ContainerAdapterError, "bounded regular"):
            self.execute(candidate=fifo, artifact_name="bad-fifo")

    def test_command_has_two_read_only_mounts_and_no_host_data_channel(self):
        receipt = self.execute()
        command = self.created[0].command
        self.assertEqual(command[0], self.docker_binding.cli)
        self.assertEqual(command[1:6], ["run", "--rm", "--pull", "never", "--name"])
        for flag, value in (("--network", "none"), ("--cap-drop", "ALL"),
                            ("--security-opt", "no-new-privileges"),
                            ("--ipc", "none"), ("--pids-limit", "32"),
                            ("--memory", "512m"), ("--cpus", "1"),
                            ("--user", "65534:65534"),
                            ("--log-driver", "none")):
            self.assertEqual(command[command.index(flag) + 1], value)
        self.assertIn("--read-only", command)
        self.assertEqual(command.count("--mount"), 2)
        mounts = [command[index + 1] for index, value in enumerate(command)
                  if value == "--mount"]
        self.assertTrue(all(item.endswith(",readonly") for item in mounts))
        self.assertTrue(any(f"dst={GUEST_PATH}" in item for item in mounts))
        self.assertTrue(any(f"dst={CANDIDATE_PATH}" in item for item in mounts))
        joined = "\n".join(command)
        self.assertNotIn(str(self.protocol_root), joined)
        self.assertNotIn("--env-file", command)
        self.assertNotIn("--privileged", command)
        self.assertNotIn("--publish", command)
        staging = self.artifacts / "run-1/staging"
        for name in ("candidate.py", "container_candidate_guest.py"):
            self.assertEqual((staging / name).stat().st_mode & 0o777, 0o444)
        self.assertEqual(receipt["docker_client"],
                         self.docker_binding.public_receipt())
        self.assertEqual(receipt["command_sha256"],
                         hashlib.sha256(json.dumps(command, sort_keys=True,
                                                   separators=(",", ":")).encode()).hexdigest())

    def test_one_exact_docker_client_environment_and_daemon_are_bound(self):
        observed = []
        def control(command, **kwargs):
            observed.append((list(command), dict(kwargs.get("env", {}))))
            return absent_control(command, **kwargs)
        with patch.dict(os.environ, {
            "PATH": "/ambient/hijack",
            "DOCKER_HOST": "tcp://ambient.invalid:2375",
            "DOCKER_CONTEXT": "ambient-context",
        }):
            receipt = self.execute(
                control=control,
                artifact_name="exact-docker-binding",
                run_key="synthetic-exact-docker-binding",
            )
        expected_environment = self.docker_binding.environment_dict()
        self.assertGreater(len(observed), 3)
        self.assertTrue(all(command[0] == self.docker_binding.cli
                            for command, _ in observed))
        self.assertTrue(all(environment == expected_environment
                            for _, environment in observed))
        self.assertEqual(receipt["docker_client"],
                         self.docker_binding.public_receipt())

    def test_unpinned_or_changed_docker_cli_fails_before_artifact(self):
        with self.assertRaisesRegex(ContainerAdapterError, "hash differs"):
            freeze_docker_client(
                run=absent_control,
                docker_cli=self.docker,
                environment=self.docker_environment,
                expected_cli_sha256="0" * 64,
            )
        self.docker.write_text("#!/bin/sh\nexit 98\n")
        self.docker.chmod(0o755)
        with self.assertRaisesRegex(ContainerAdapterError, "identity changed"):
            self.execute(
                artifact_name="changed-docker-cli",
                run_key="synthetic-changed-docker-cli",
            )
        self.assertFalse((self.artifacts / "changed-docker-cli").exists())

    def test_changed_daemon_identity_can_never_verify_cleanup(self):
        info_calls = 0
        def changed(command, **kwargs):
            nonlocal info_calls
            if command[1:2] == ["info"]:
                info_calls += 1
                if info_calls >= 3:
                    return subprocess.CompletedProcess(
                        command, 0,
                        stdout="different-id|different|1.0|linux|arm64|/other\n",
                        stderr="",
                    )
            return absent_control(command, **kwargs)
        with self.assertRaisesRegex(ContainerAdapterError, "absence unverified"):
            self.execute(
                control=changed,
                artifact_name="daemon-changed",
                run_key="synthetic-daemon-changed",
            )
        failure = json.loads(
            (self.artifacts / "daemon-changed/adapter-failure.json").read_text()
        )
        self.assertFalse(failure["cleanup"]["exact_container_cleanup_verified"])

    def test_bad_response_identity_authority_and_probability_fail_closed(self):
        variants = {
            "wrong-row": lambda release: {**prediction_submission(release, 0.5),
                                            "row_id": "row-wrong"},
            "authority": lambda release: {**prediction_submission(release, 0.5),
                                            "real_isolation_admitted": True},
            "old-fit": lambda release: {"type": "fitted"},
            "zero": lambda release: prediction_submission(release, 1e-6) | {"probability": 0},
            "bool": lambda release: prediction_submission(release, 1e-6) | {"probability": True},
        }
        for name, response in variants.items():
            made = []
            def factory(command, artifact_root, response=response):
                transport = FakeTransport(command, artifact_root, response=response)
                made.append(transport)
                return transport
            with self.subTest(name=name), self.assertRaises(Exception):
                self.execute(
                    factory=factory,
                    artifact_name=f"bad-response-{name}",
                    run_key=f"synthetic-bad-response-{name}",
                )
            self.assertEqual(len(made[0].releases), 1)
            self.assertTrue(made[0].aborted)
            self.assertFalse((self.artifacts / f"bad-response-{name}/adapter-receipt.json").exists())
            self.assertTrue((self.artifacts / f"bad-response-{name}/adapter-failure.json").is_file())

    def test_commit_failure_prevents_next_exchange(self):
        made = []
        def factory(command, artifact_root):
            transport = FakeTransport(command, artifact_root)
            made.append(transport)
            return transport
        with patch.object(LabelFreePredictionProtocol, "commit_prediction",
                          side_effect=OSError("synthetic fsync failure")):
            with self.assertRaises(ContainerAdapterError):
                self.execute(factory=factory, artifact_name="commit-failure")
        self.assertEqual(len(made[0].releases), 1)
        self.assertTrue(made[0].aborted)

    def test_nonzero_process_or_cleanup_ambiguity_blocks_completion(self):
        process = {"process_reaped": True, "exit_code": 7, "responses": 3}
        made = []
        def factory(command, artifact_root):
            transport = FakeTransport(command, artifact_root, process=process)
            made.append(transport)
            return transport
        with self.assertRaisesRegex(ContainerAdapterError, "did not end cleanly"):
            self.execute(
                factory=factory,
                artifact_name="nonzero",
                run_key="synthetic-nonzero",
            )
        self.assertFalse((self.artifacts / "nonzero/adapter-receipt.json").exists())

        calls = 0
        def ambiguous(command, **_kwargs):
            nonlocal calls
            if command[1:2] == ["inspect"]:
                calls += 1
                if calls == 1:
                    return absent_control(command)
                return subprocess.CompletedProcess(command, 1, stdout="", stderr="permission denied")
            return absent_control(command, **_kwargs)
        with self.assertRaisesRegex(ContainerAdapterError, "absence unverified"):
            self.execute(
                control=ambiguous,
                artifact_name="ambiguous",
                run_key="synthetic-ambiguous",
            )
        self.assertFalse((self.artifacts / "ambiguous/adapter-receipt.json").exists())

    def test_foreign_container_blocks_before_process(self):
        def foreign(command, **_kwargs):
            if command[1:2] == ["inspect"]:
                return subprocess.CompletedProcess(command, 0,
                    stdout="container-id|wrong|wrong\n", stderr="")
            return absent_control(command, **_kwargs)
        calls = []
        with self.assertRaisesRegex(ContainerAdapterError, "not fresh"):
            self.execute(control=foreign, factory=lambda *args: calls.append(args),
                         artifact_name="foreign")
        self.assertEqual(calls, [])

    def test_staged_source_mutation_is_detected_before_completion(self):
        made = []
        def factory(command, artifact_root):
            def mutate():
                staged = Path(artifact_root) / "staging/candidate.py"
                staged.chmod(0o600)
                staged.write_text("def predict(row):\n    return 0.9\n")
            transport = FakeTransport(command, artifact_root, on_finish=mutate)
            made.append(transport)
            return transport
        with self.assertRaisesRegex(ContainerAdapterError, "staged candidate"):
            self.execute(factory=factory, artifact_name="source-swap")
        self.assertFalse((self.artifacts / "source-swap/adapter-receipt.json").exists())

    def test_delayed_unsolicited_output_blocks_second_row_release(self):
        fixture = (
            "import json,sys,threading,time\n"
            "for raw in sys.stdin:\n"
            " r=json.loads(raw); out={'schema':'minimal_prediction_submission_v1',"
            "'run_id':r['run_id'],'sequence':r['sequence'],'row_id':r['row_id'],"
            "'probability':0.5}; line=json.dumps(out,separators=(',',':'))\n"
            " print(line,flush=True)\n"
            " if r['sequence']==0:\n"
            "  threading.Thread(target=lambda:(time.sleep(0.01),print(line,flush=True))).start()\n"
        )
        def factory(_command, artifact_root):
            return DockerJSONLTransport(
                [sys.executable, "-I", "-u", "-c", fixture], artifact_root,
                {"PATH": os.environ.get("PATH", "/usr/bin"),
                 "HOME": str(artifact_root)},
            )
        original = LabelFreePredictionProtocol.commit_prediction
        def slow_commit(protocol, submission):
            result = original(protocol, submission)
            time.sleep(0.05)
            return result
        with patch.object(LabelFreePredictionProtocol, "commit_prediction", slow_commit):
            with self.assertRaisesRegex(ContainerAdapterError, "unsolicited"):
                self.execute(
                    factory=factory,
                    artifact_name="delayed-extra",
                    run_key="synthetic-delayed-extra",
                )
        run_directory = next(self.protocol_root.glob("run-*"))
        events = [json.loads(line)["event"] for line in
                  (run_directory / "journal.jsonl").read_text().splitlines()]
        self.assertEqual(events, ["row_released", "prediction_committed"])

    def test_post_completion_receipt_failure_records_truth_without_replay(self):
        original = adapter_module._write_once
        def fail_adapter_receipt(path, value):
            if Path(path).name == "adapter-receipt.json":
                raise OSError("synthetic final receipt fsync failure")
            return original(path, value)
        with patch.object(adapter_module, "_write_once", side_effect=fail_adapter_receipt):
            with self.assertRaisesRegex(ContainerAdapterError, "failed closed"):
                self.execute(
                    artifact_name="receipt-failure",
                    run_key="synthetic-receipt-failure",
                )
        failure = json.loads(
            (self.artifacts / "receipt-failure/adapter-failure.json").read_text()
        )
        self.assertTrue(failure["prediction_complete"])
        self.assertIsInstance(failure["protocol_completion"], dict)
        self.assertFalse(failure["adapter_receipt_finalized"])
        self.assertFalse(failure["adapter_receipt_present"])
        calls = []
        with self.assertRaises(PredictionProtocolError):
            self.execute(
                artifact_name="receipt-failure-replay",
                run_key="synthetic-receipt-failure",
                factory=lambda *args: calls.append(args),
            )
        self.assertEqual(calls, [])

    def test_late_success_write_ambiguity_is_failure_dominant(self):
        original = adapter_module._write_once
        for target in ("adapter-receipt.json", "adapter-success.json"):
            artifact_name = "late-" + target.removesuffix(".json")
            run_key = "synthetic-" + artifact_name
            def write_then_fail(path, value, *, target=target):
                result = original(path, value)
                if Path(path).name == target:
                    raise OSError("synthetic post-write directory fsync ambiguity")
                return result
            with self.subTest(target=target), patch.object(
                    adapter_module, "_write_once", side_effect=write_then_fail):
                with self.assertRaisesRegex(ContainerAdapterError, "failed closed"):
                    self.execute(artifact_name=artifact_name, run_key=run_key)
            root = self.artifacts / artifact_name
            self.assertTrue((root / "adapter-receipt.json").is_file())
            self.assertTrue((root / "adapter-failure.json").is_file())
            failure = json.loads((root / "adapter-failure.json").read_text())
            self.assertTrue(failure["prediction_complete"])
            self.assertTrue(failure["adapter_receipt_present"])
            self.assertEqual(failure["adapter_success_present"],
                             target == "adapter-success.json")
            with self.assertRaisesRegex(ContainerAdapterError, "failure evidence"):
                self.verify(artifact_name, run_key)

    def test_terminal_verifier_rechecks_claim_and_protocol_completion(self):
        self.execute(
            artifact_name="claim-mutation",
            run_key="synthetic-claim-mutation",
        )
        claim_path = self.artifacts / "claim-mutation/adapter-claim.json"
        claim = json.loads(claim_path.read_text())
        claim["expected_predictions"] = 999
        claim_path.write_text(json.dumps(
            claim, sort_keys=True, separators=(",", ":")
        ) + "\n")
        with self.assertRaisesRegex(ContainerAdapterError, "claim integrity"):
            self.verify("claim-mutation", "synthetic-claim-mutation")

        completion_receipt = self.execute(
            artifact_name="completion-mutation",
            run_key="synthetic-completion-mutation",
        )
        complete_path = (
            self.protocol_root / completion_receipt["run_id"] / "complete.json"
        )
        completion = json.loads(complete_path.read_text())
        completion["predictions"] = 999
        complete_path.write_text(json.dumps(
            completion, sort_keys=True, separators=(",", ":")
        ) + "\n")
        with self.assertRaisesRegex(ContainerAdapterError, "protocol terminal"):
            self.verify("completion-mutation", "synthetic-completion-mutation")

        journal_receipt = self.execute(
            artifact_name="journal-truncation",
            run_key="synthetic-journal-truncation",
        )
        journal_path = (
            self.protocol_root / journal_receipt["run_id"] / "journal.jsonl"
        )
        journal_path.write_bytes(journal_path.read_bytes()[:-1])
        with self.assertRaisesRegex(ContainerAdapterError, "protocol terminal"):
            self.verify("journal-truncation", "synthetic-journal-truncation")

        self.execute(
            artifact_name="terminal-stage-mutation",
            run_key="synthetic-terminal-stage-mutation",
        )
        staged_candidate = (
            self.artifacts / "terminal-stage-mutation/staging/candidate.py"
        )
        staged_candidate.chmod(0o600)
        staged_candidate.write_text("def predict(row):\n    return 0.7\n")
        with self.assertRaisesRegex(ContainerAdapterError, "staged candidate"):
            self.verify(
                "terminal-stage-mutation", "synthetic-terminal-stage-mutation"
            )

    def test_used_run_id_is_not_replayed_into_a_new_process(self):
        self.execute(artifact_name="first")
        calls = []
        with self.assertRaises(PredictionProtocolError):
            self.execute(artifact_name="second", factory=lambda *args: calls.append(args))
        self.assertEqual(calls, [])

    def test_temporary_paths_require_explicit_test_flag(self):
        with self.assertRaisesRegex(ContainerAdapterError, "persistent local"):
            run_local_candidate_prediction(
                protocol_root=self.protocol_root,
                artifact_root=self.artifacts / "not-allowed",
                run_key="synthetic-persistent-check",
                candidate_source=self.candidate,
                expected_candidate_sha256=self.candidate_hash,
                public_rows=rows(),
            )

    def test_dependency_injection_is_rejected_outside_test_mode(self):
        with self.assertRaisesRegex(ContainerAdapterError, "test hooks"):
            run_local_candidate_prediction(
                protocol_root=self.protocol_root,
                artifact_root=self.artifacts / "injected-production-shape",
                run_key="synthetic-injected-production-shape",
                candidate_source=self.candidate,
                expected_candidate_sha256=self.candidate_hash,
                public_rows=rows(),
                transport_factory=lambda *args: None,
                control_run=absent_control,
                docker_binding=self.docker_binding,
            )


class ParserAndTransportTests(unittest.TestCase):
    def test_strict_parser_rejects_duplicate_nonfinite_invalid_utf8_and_nonobject(self):
        bad = [
            b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}',
            b'[]', b'\xff', b'{',
        ]
        for raw in bad:
            with self.subTest(raw=raw), self.assertRaises(ContainerAdapterError):
                _strict_json_object(raw)

    def test_real_local_transport_handles_one_synthetic_line_and_reaps(self):
        fixture = (
            "import sys,json\n"
            "for line in sys.stdin:\n"
            " r=json.loads(line); print(json.dumps(r,separators=(',',':')),flush=True)\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            transport = DockerJSONLTransport(
                [sys.executable, "-I", "-u", "-c", fixture], Path(directory),
                {"PATH": os.environ.get("PATH", "/usr/bin"), "HOME": directory},
            )
            payload = {"synthetic": True, "sequence": 0}
            self.assertEqual(transport.exchange(payload, 2), payload)
            receipt = transport.finish()
            self.assertTrue(receipt["process_reaped"])
            self.assertEqual(receipt["exit_code"], 0)
            self.assertEqual(receipt["responses"], 1)

    def test_multiple_output_and_timeout_fail_closed(self):
        fixtures = [
            "import sys; sys.stdin.readline(); print('{}\\n{}',flush=True)",
            "import sys,time; sys.stdin.readline(); time.sleep(5)",
        ]
        for index, fixture in enumerate(fixtures):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as directory:
                transport = DockerJSONLTransport(
                    [sys.executable, "-I", "-u", "-c", fixture], Path(directory),
                    {"PATH": os.environ.get("PATH", "/usr/bin"), "HOME": directory},
                )
                with self.assertRaises((ContainerAdapterError, TimeoutError)):
                    transport.exchange({"synthetic": True}, 0.05)
                transport.abort()
                self.assertIsNotNone(transport.process.poll())

    def test_post_popen_initialization_failure_reaps_exact_process(self):
        fixture = "import time; time.sleep(30)"
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(adapter_module.os, "set_blocking",
                              side_effect=OSError("synthetic setup failure")):
                with self.assertRaises(TransportLifecycleError) as raised:
                    DockerJSONLTransport(
                        [sys.executable, "-I", "-u", "-c", fixture],
                        Path(directory),
                        {"PATH": os.environ.get("PATH", "/usr/bin"),
                         "HOME": directory},
                    )
        self.assertTrue(raised.exception.process_evidence["process_reaped"])
        self.assertFalse(raised.exception.process_evidence["wait_timed_out"])

    def test_abort_preserves_unreaped_uncertainty(self):
        class Stream:
            def close(self):
                return None
        class Process:
            pid = 987654321
            stdin = stdout = stderr = Stream()
            def poll(self):
                return None
            def wait(self, timeout):
                raise subprocess.TimeoutExpired("synthetic", timeout)
        transport = DockerJSONLTransport.__new__(DockerJSONLTransport)
        transport.process = Process()
        transport.closed = False
        with patch.object(adapter_module.os, "killpg",
                          side_effect=PermissionError("synthetic denial")):
            evidence = transport.abort()
        self.assertFalse(evidence["process_reaped"])
        self.assertTrue(evidence["wait_timed_out"])
        self.assertEqual(evidence["signal_error_type"], "PermissionError")
        self.assertFalse(transport.closed)


if __name__ == "__main__":
    unittest.main()
