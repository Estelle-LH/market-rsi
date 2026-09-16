import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import development_harbor as worker
from harbor.models.task.config import NetworkMode, NetworkPolicy
from inspection_stream import inspect_once
from market_rsi import canonical, fresh_json
from prediction_stream import PredictionJournal, encoded, fingerprint, predict_stream
from trial_inputs import prepare_development_trial
import test_trial_inputs as input_fixtures
from test_researcher_worker import task


class DevelopmentTests(unittest.TestCase):
    def setUp(self):
        # Reuse fixture construction without inheriting/recounting its test cases.
        self.fixture = input_fixtures.TrialInputsTests()
        self.fixture.setUp()
        self.root = self.fixture.root / "development-01"

    def tearDown(self):
        self.fixture.tearDown()

    def prepare(self, action="experiment"):
        args = self.fixture.jobs(action=action)
        bundle = prepare_development_trial(**args)
        worker.prepare_job(bundle, self.root)
        return bundle

    def mutate(self, name, update):
        path = self.root / name
        value = json.loads(path.read_text())
        update(value)
        path.write_text(canonical(value))

    def environment(self):
        env = object.__new__(worker.DevelopmentE2B)
        env.control_root, env.budget_path, env.env_file = self.root, self.fixture.budget.root, "/nonexistent-test-env"
        env.creation_attempted, env.cleanup_calls, env._sandbox = False, 0, None
        env._network_policy = NetworkPolicy(network_mode=NetworkMode.NO_NETWORK)
        env.ensure_dirs = AsyncMock()
        env._mount_targets = lambda **kwargs: []
        return env

    def outputs(self, bundle):
        """Fabricate trusted-runner receipts for read-back unit tests, not scores."""
        collected = self.root / "collected"
        collected.mkdir()
        claim = worker.verify_job(self.root)[0]
        events = []
        def exchange(request, timeout):
            if request["type"] == "inspect":
                response = {"type": "inspection", "request_id": request["request_id"],
                            "diagnostic": {"fixture": True, "passed": True}}
            elif request["type"] == "fit":
                response = {"type": "fitted", "request_id": request["request_id"]}
            else:
                response = {"type": "prediction", "request_id": request["request_id"],
                            "row_id": request["row"]["row_id"], "prediction": 0.0}
            events.extend([{"type": "request", "request_sha256": fingerprint(request), "request_bytes": len(encoded(request)) + 1},
                           {"type": "response", "raw": canonical(response) + "\n"}])
            return response
        packet = bundle["packet"]
        if bundle["binding"]["mode"] == "inspect":
            execution = {"inspection": inspect_once(exchange, packet), "scored": False}
        else:
            journal = PredictionJournal(collected / "predictions", train_sha256=fingerprint(packet["train"]),
                evaluation_sha256=fingerprint(packet["evaluation"]), candidate_sha256=bundle["binding"]["candidate_sha256"],
                expected_predictions=len(packet["evaluation"]))
            stream = predict_stream(exchange, journal.commit, packet["train"], packet["evaluation"],
                                    packet["feature_names"], **packet["limits"])
            execution = {"stream": stream, "complete": journal.finish(), "scored": False}
        fresh_json(collected / "execution.json", execution)
        fresh_json(collected / "protocol.json", {"events": events})
        from diagnostic_channel import stderr_receipt
        (collected / "candidate-stderr.log").write_bytes(b"")
        fresh_json(collected / "candidate-diagnostic.json", stderr_receipt(collected / "candidate-stderr.log"))
        fresh_json(collected / "isolation.json", {"checks": {k: True for k in worker.ISOLATION_CHECKS},
            "exit_code": 0, "probe_sha256": claim["deployed_hashes"]["public/isolation_probe.py"]})
        libraries = bundle["runtime"]["libraries"]
        fresh_json(self.root / "libraries.json", {"expected": libraries, "actual": libraries, "exit_code": 0})
        fresh_json(self.root / "command.json", {"exit_code": 0})
        fresh_json(self.root / "collection.json", {"missing_or_failed": {"failure.json": "NotFound"}})

    def test_exclusive_preparation_is_not_live_admission(self):
        bundle = self.prepare()
        claim, packet, _, sources = worker.verify_job(self.root)
        self.assertFalse(claim["scientific_admission"])
        self.assertEqual(packet, bundle["packet"])
        self.assertEqual(sources["public/candidate.py"], bundle["candidate_source"])
        with self.assertRaises(FileExistsError):
            worker.prepare_job(bundle, self.root)

    def test_production_entrypoint_fails_before_harbor_or_paid_calls(self):
        self.prepare()
        with patch.object(worker.Trial, "create", AsyncMock()) as create:
            with self.assertRaisesRegex(RuntimeError, "scientific admission"):
                asyncio.run(worker.run_development(self.root, self.fixture.budget.root, "/nonexistent"))
        create.assert_not_called()
        self.assertFalse((self.root / "harbor-config.json").exists())

    def test_direct_environment_start_cannot_bypass_admission(self):
        env = self.environment()
        with patch("e2b.AsyncSandbox.create", AsyncMock()) as create:
            with self.assertRaises(RuntimeError):
                asyncio.run(env.start(False))
        create.assert_not_called()
        self.assertFalse(env.creation_attempted)

    def test_build_and_duplicate_start_rejected(self):
        env = self.environment()
        with self.assertRaises(ValueError):
            asyncio.run(env.start(True))
        env.creation_attempted = True
        with self.assertRaises(ValueError):
            asyncio.run(env.start(False))

    def test_mutated_deployment_source_rejected(self):
        self.prepare()
        self.mutate("sources.json", lambda x: x["deployed"].update({"public/candidate.py": "swapped code"}))
        with self.assertRaises(ValueError):
            worker.verify_job(self.root)

    def test_omitted_task_hashes_rejected(self):
        self.prepare()
        self.mutate("claim.json", lambda x: x.update(task_hashes={}))
        with self.assertRaises(ValueError):
            worker.verify_job(self.root)

    def test_upstream_worker_mutation_stops_execution(self):
        self.prepare()
        p = self.fixture.root / "coder-learn" / "response.json"
        p.write_text("{}")
        with self.assertRaises(ValueError):
            worker.verify_job(self.root)

    def test_bound_packet_cannot_be_replaced_with_only_new_claim_hash(self):
        self.prepare()
        self.mutate("packet.json", lambda x: x["train"][0].update(target=.9))
        new = json.loads((self.root / "packet.json").read_text())
        self.mutate("claim.json", lambda x: x.update(packet_sha256=fingerprint(new)))
        with self.assertRaises(ValueError):
            worker.verify_job(self.root)

    def test_independent_prediction_readback_no_market_score(self):
        bundle = self.prepare()
        self.outputs(bundle)
        result = worker.verify_outputs(self.root)
        self.assertEqual(len(result["predictions"]), 3)
        self.assertTrue(result["execution_verified"])
        self.assertFalse(result["scientific_admission"])
        self.assertIsNone(result["market_score"])

    def test_independent_inspection_readback_stays_untrusted(self):
        bundle = self.prepare("inspect")
        self.outputs(bundle)
        result = worker.verify_outputs(self.root)
        self.assertTrue(result["diagnostic"]["diagnostic"]["passed"])
        self.assertEqual(result["diagnostic"]["origin"], "candidate_code_untrusted_diagnostic")
        self.assertFalse(result["scored"])

    def test_missing_prediction_protocol_rejected(self):
        bundle = self.prepare()
        self.outputs(bundle)
        self.mutate("collected/protocol.json", lambda x: x.update(events=x["events"][:-1]))
        with self.assertRaises(ValueError):
            worker.verify_outputs(self.root)

    def test_changed_inspection_request_hash_rejected(self):
        bundle = self.prepare("inspect")
        self.outputs(bundle)
        self.mutate("collected/protocol.json", lambda x: x["events"][0].update(request_sha256="0" * 64))
        with self.assertRaises(ValueError):
            worker.verify_outputs(self.root)

    def test_diagnostic_cannot_self_promote_to_scientific_result(self):
        bundle = self.prepare("inspect")
        self.outputs(bundle)
        self.mutate("collected/execution.json", lambda x: x["inspection"].update(scientific_admission=True))
        with self.assertRaises(ValueError):
            worker.verify_outputs(self.root)

    def test_runtime_version_mismatch_rejected(self):
        bundle = self.prepare()
        self.outputs(bundle)
        self.mutate("libraries.json", lambda x: x.update(actual={"python": "different"}))
        with self.assertRaises(ValueError):
            worker.verify_outputs(self.root)

    def test_incomplete_collection_rejected(self):
        bundle = self.prepare()
        self.outputs(bundle)
        self.mutate("collection.json", lambda x: x["missing_or_failed"].update({"protocol.json": "TimeoutError"}))
        with self.assertRaises(ValueError):
            worker.verify_outputs(self.root)

    def test_isolation_requires_all_checks_not_candidate_assertion(self):
        bundle = self.prepare()
        self.outputs(bundle)
        self.mutate("collected/isolation.json", lambda x: x.update(checks={"unprivileged": True}))
        with self.assertRaises(ValueError):
            worker.verify_outputs(self.root)

    def test_nonzero_command_and_failure_receipts_cannot_be_scores(self):
        bundle = self.prepare()
        self.outputs(bundle)
        self.mutate("command.json", lambda x: x.update(exit_code=1))
        with self.assertRaises(ValueError):
            worker.verify_outputs(self.root)
        fresh_json(self.root / "collected/failure.json", {"error_type": "TimeoutError"})
        with self.assertRaises(ValueError):
            worker.verify_outputs(self.root)

    def test_e2b_nonzero_exception_is_preserved_as_terminal_command(self):
        from e2b.sandbox.commands.command_handle import CommandExitException
        error = CommandExitException(stderr="candidate error", stdout="partial", exit_code=7, error=None)
        self.assertEqual(worker.terminal_nonzero_result(error), {
            "exit_code": 7, "stdout": "partial", "stderr": "candidate error"})
        self.assertIsNone(worker.terminal_nonzero_result(TimeoutError("ambiguous transport")))

    def test_real_harbor_constructs_custom_types_without_cloud(self):
        self.prepare()
        async def check():
            config = worker.trial_config(self.root, self.fixture.budget.root, "/nonexistent")
            with patch.object(worker.DevelopmentE2B, "start", AsyncMock(side_effect=AssertionError("no cloud"))):
                trial = await worker.Trial.create(config)
            try:
                self.assertIsInstance(trial.agent, worker.DevelopmentAgent)
                self.assertIsInstance(trial.agent_environment, worker.DevelopmentE2B)
                self.assertIsNone(trial.agent_environment._sandbox)
                self.assertEqual(trial.task.config.agent.network_mode, NetworkMode.NO_NETWORK)
            finally:
                trial._close_logger_handler()
        asyncio.run(check())

    def test_mock_cloud_start_reserves_once_with_exact_ttl_no_network_and_cleanup(self):
        self.prepare()
        env = self.environment()
        start = datetime.now(timezone.utc)
        info = SimpleNamespace(template_id=worker.TEMPLATE, cpu_count=2, memory_mb=512,
            started_at=start, end_at=start+timedelta(seconds=worker.TTL), envd_version="fixture", allow_internet_access=False)
        sb = SimpleNamespace(sandbox_id="fixture-sandbox", get_info=AsyncMock(return_value=info), kill=AsyncMock(return_value=True))
        with patch.object(worker, "require_admission", return_value=None), patch("dotenv.dotenv_values", return_value={"E2B_API_KEY": "fixture"}), \
                patch("e2b.AsyncSandbox.create", AsyncMock(return_value=sb)) as create:
            asyncio.run(env.start(False))
            with self.assertRaises(ValueError):
                asyncio.run(env.start(False))
        self.assertEqual(create.await_count, 1)
        self.assertEqual(create.call_args.kwargs["timeout"], 240)
        self.assertFalse(create.call_args.kwargs["allow_internet_access"])
        self.assertEqual(self.fixture.budget.snapshot()["jobs"][self.root.name]["bucket"], "learning")
        asyncio.run(env.stop())
        self.assertIsNone(env._sandbox)
        snapshot = self.fixture.budget.snapshot()
        self.assertEqual(snapshot["reserved_usd"], "0")
        self.assertGreater(float(snapshot["metered_usd"]), 0)

    def test_setup_installs_only_bound_sources_and_checks_runtime_before_candidate(self):
        bundle = self.prepare("inspect")
        agent = object.__new__(worker.DevelopmentAgent)
        agent.control_root = self.root
        commands = []
        async def run(command, **kwargs):
            commands.append(command)
            return SimpleNamespace(exit_code=0, stdout=canonical(bundle["runtime"]["libraries"]) if "-I -c" in command else "", stderr="")
        sb = SimpleNamespace(commands=SimpleNamespace(run=run), files=SimpleNamespace(write=AsyncMock()))
        with patch.object(worker, "require_admission", return_value=None):
            asyncio.run(agent.setup(SimpleNamespace(_sandbox=sb)))
        self.assertFalse(any(c.startswith("python3 -I " + worker.PRIVATE + "/sandbox_") for c in commands))
        writes = {call.args[0]: call.args[1] for call in sb.files.write.call_args_list}
        self.assertEqual(writes[worker.PUBLIC + "/candidate.py"], bundle["candidate_source"])
        self.assertFalse(any("key" in path or "test" in path for path in writes))
        self.assertIn("chmod 600", commands[-1])

    def test_failed_runtime_probe_does_not_launch_candidate(self):
        self.prepare()
        agent = object.__new__(worker.DevelopmentAgent)
        agent.control_root = self.root
        run = AsyncMock(return_value=SimpleNamespace(exit_code=0, stdout="{}", stderr=""))
        sb = SimpleNamespace(commands=SimpleNamespace(run=run), files=SimpleNamespace(write=AsyncMock()))
        with patch.object(worker, "require_admission", return_value=None):
            with self.assertRaisesRegex(ValueError, "libraries not available"):
                asyncio.run(agent.setup(SimpleNamespace(_sandbox=sb)))
        self.assertEqual(run.await_count, 2)

    def test_trial_construction_failure_preserves_new_claim_without_charge(self):
        self.prepare()
        before = self.fixture.budget.snapshot()
        with patch.object(worker, "require_admission", return_value=None), \
                patch.object(worker.Trial, "create", AsyncMock(side_effect=ValueError("fixture construction"))):
            with self.assertRaises(ValueError):
                asyncio.run(worker.run_development(self.root, self.fixture.budget.root, "/nonexistent"))
        self.assertTrue((self.root / "failure.json").exists())
        self.assertEqual(self.fixture.budget.snapshot(), before)

    def test_harbor_failure_still_cleans_exact_created_sandbox(self):
        self.prepare()
        env = self.environment()
        sb = SimpleNamespace(sandbox_id="fixture-owned-sandbox", kill=AsyncMock(return_value=True))
        env._sandbox = sb
        trial = SimpleNamespace(agent_environment=env,
                                run=AsyncMock(return_value=SimpleNamespace(exception_info={"type": "fixture_failure"})))
        with patch.object(worker, "require_admission", return_value=None), \
                patch.object(worker.Trial, "create", AsyncMock(return_value=trial)):
            with self.assertRaises(ValueError):
                asyncio.run(worker.run_development(self.root, self.fixture.budget.root, "/nonexistent"))
        sb.kill.assert_awaited_once()
        self.assertIsNone(env._sandbox)
        self.assertTrue((self.root / "failure.json").exists())
        self.assertEqual(json.loads((self.root / "cleanup-01.json").read_text())["sandbox_id"], "fixture-owned-sandbox")

    def test_exhausted_learning_allocation_stops_before_provider_creation(self):
        self.prepare()
        budget = self.fixture.budget
        available = budget.snapshot()["buckets"]["learning"]["available_usd"]
        budget.reserve("fixture-other-pending", "learning", available, "fixture", "a" * 64)
        env = self.environment()
        with patch.object(worker, "require_admission", return_value=None), \
                patch("dotenv.dotenv_values", return_value={"E2B_API_KEY": "fixture"}), \
                patch("e2b.AsyncSandbox.create", AsyncMock()) as create:
            with self.assertRaises(ValueError):
                asyncio.run(env.start(False))
        create.assert_not_called()
        self.assertEqual(budget.snapshot()["buckets"]["final"]["available_usd"], "1")
        self.assertFalse(env.creation_attempted)

    def test_transfer_reservation_uses_final_allocation(self):
        with patch.object(input_fixtures, "task", return_value=task(phase="transfer")):
            self.prepare()
        env = self.environment()
        # Ambiguous mock create failure preserves its reservation in the correct
        # allocation. No real provider request or invented zero-cost receipt.
        with patch.object(worker, "require_admission", return_value=None), \
                patch("dotenv.dotenv_values", return_value={"E2B_API_KEY": "fixture"}), \
                patch("e2b.AsyncSandbox.create", AsyncMock(side_effect=TimeoutError("fixture"))):
            with self.assertRaises(TimeoutError):
                asyncio.run(env.start(False))
        job = self.fixture.budget.snapshot()["jobs"][self.root.name]
        self.assertEqual(job["bucket"], "final")
        self.assertEqual(job["state"], "dispatched")
        self.assertIsNone(job["metered_usd"])
        self.assertTrue(env.creation_attempted)


if __name__ == "__main__":
    unittest.main()
