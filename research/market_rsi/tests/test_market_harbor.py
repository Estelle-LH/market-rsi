import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import market_harbor as worker
from market_rsi import canonical, file_hash, fresh_json
from paid_budget import PaidBudget
from prediction_stream import PredictionJournal, fingerprint, validate_rows
from harbor.models.task.config import NetworkMode, NetworkPolicy


class HarborFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "fixture-harbor-01"
        self.root.mkdir()
        packet = worker.fixture_packet()
        self.claim = {"job_id": self.root.name, "experiment_id": "fixture-test",
            "evidence_class": "synthetic-worker-integration", "research_result": False,
            "packet_sha256": fingerprint(packet), "ttl_seconds": worker.TTL,
            "template": worker.TEMPLATE, "upper_usd": worker.UPPER_USD,
            "deployed_hashes": {n: file_hash(p) for n, p in worker.SOURCES.items()},
            "worker_sha256": file_hash(worker.__file__)}
        fresh_json(self.root / "claim.json", self.claim)
        fresh_json(self.root / "packet.json", packet)

    def tearDown(self):
        self.temp.cleanup()

    def mutate(self, rel, key, value):
        path = self.root / rel
        obj = json.loads(path.read_text())
        obj[key] = value
        path.write_text(canonical(obj))  # Deliberate tampering of a temporary test fixture.

    def env(self):
        obj = object.__new__(worker.BoundedMarketE2B)
        obj.control_root = self.root
        obj.creation_attempted = False
        obj.cleanup_calls = 0
        obj._sandbox = None
        return obj

    def outputs(self):
        packet = worker.fixture_packet()
        journal = PredictionJournal(self.root / "collected/predictions",
            train_sha256=fingerprint(packet["train"]), evaluation_sha256=fingerprint(packet["evaluation"]),
            candidate_sha256=file_hash(worker.SOURCES["public/candidate.py"]), expected_predictions=3)
        chain = "0" * 64
        for i, features in enumerate(packet["evaluation"]):
            row = {"sequence": i, "row_id": features["row_id"], "prediction": features["features"]["x"],
                   "feature_row_sha256": fingerprint(features), "previous": chain}
            row["hash"] = fingerprint(row)
            journal.commit(row)
            chain = row["hash"]
        complete = journal.finish()
        fresh_json(self.root / "collected/isolation.json", {
            "checks": {k: True for k in worker.ISOLATION_CHECKS}, "exit_code": 0,
            "probe_sha256": file_hash(worker.SOURCES["public/isolation_probe.py"])})
        fresh_json(self.root / "collected/execution.json", {"complete": complete, "scored": False})

    def test_only_prior_train_and_label_free_evaluation(self):
        _, packet = worker.verify_claim(self.root)
        validate_rows(packet["train"], packet["evaluation"], packet["feature_names"])
        self.assertTrue(all("target" not in r for r in packet["evaluation"]))

    def test_deployment_includes_trusted_runner_import_closure(self):
        self.assertIn("private/diagnostic_channel.py", worker.SOURCES)
        self.assertIn("candidate-stderr.json", worker.OUTPUTS)

    def test_packet_cannot_be_replaced_even_with_matching_hash(self):
        packet = worker.fixture_packet()
        packet["train"][0]["target"] = 0.9
        self.mutate("packet.json", "train", packet["train"])
        self.mutate("claim.json", "packet_sha256", fingerprint(packet))
        with self.assertRaises(ValueError):
            worker.verify_claim(self.root)

    def test_research_flag_does_not_admit_real_data(self):
        self.mutate("claim.json", "research_result", True)
        with self.assertRaises(ValueError):
            worker.verify_claim(self.root)

    def test_source_hash_change_rejected(self):
        self.mutate("claim.json", "worker_sha256", "0" * 64)
        with self.assertRaises(ValueError):
            worker.verify_claim(self.root)

    def test_deployed_hash_change_rejected(self):
        self.mutate("claim.json", "deployed_hashes", {k: "0" * 64 for k in worker.SOURCES})
        with self.assertRaises(ValueError):
            worker.verify_claim(self.root)

    def test_no_network_relaxation(self):
        env = self.env()
        asyncio.run(env._apply_network_policy(NetworkPolicy(network_mode=NetworkMode.NO_NETWORK)))
        with self.assertRaises(ValueError):
            asyncio.run(env._apply_network_policy(NetworkPolicy(network_mode=NetworkMode.PUBLIC)))

    def test_no_build_or_second_creation(self):
        env = self.env()
        with self.assertRaises(ValueError):
            asyncio.run(env.start(force_build=True))
        env.creation_attempted = True
        with self.assertRaises(ValueError):
            asyncio.run(env.start(force_build=False))

    def test_stop_retains_exact_reference_on_failed_ack(self):
        env = self.env()
        sb = SimpleNamespace(sandbox_id="fixture-sandbox", kill=AsyncMock(return_value=False))
        env._sandbox = sb
        with self.assertRaises(RuntimeError):
            asyncio.run(env.stop())
        self.assertIs(env._sandbox, sb)
        self.assertFalse(json.loads((self.root / "cleanup-01.json").read_text())["kill_acknowledged"])

    def test_stop_ack_is_recorded_without_metered_spend(self):
        env = self.env()
        sb = SimpleNamespace(sandbox_id="fixture-sandbox", kill=AsyncMock(return_value=True))
        env._sandbox = sb
        asyncio.run(env.stop())
        self.assertIsNone(env._sandbox)
        record = json.loads((self.root / "cleanup-01.json").read_text())
        self.assertTrue(record["kill_acknowledged"])
        self.assertNotIn("metered_usd", record)
        asyncio.run(env.stop())
        self.assertEqual(sb.kill.await_count, 1)

    def test_acknowledged_interval_releases_hold_at_conservative_metered_cost(self):
        budget_path = Path(self.temp.name) / "metered-budget"
        budget = PaidBudget.create(budget_path, {"experiment_id": "fixture-budget", "cap_usd": "200",
            "target_usd": "100", "buckets_usd": {"setup": "10", "learning": "120", "final": "50", "repair": "20"},
            "authority": "offline test"})
        budget.reserve(self.root.name, "setup", "0.10", "e2b", "a" * 64)
        budget.dispatch(self.root.name)
        env = self.env()
        env.budget_path = budget_path
        env._metering_started_monotonic = 100.0
        env._metering_started_utc = "2026-09-08T00:00:00+00:00"
        env._metering_cpu_count = 2
        env._metering_memory_mb = 512
        env._sandbox = SimpleNamespace(sandbox_id="fixture-sandbox",
                                       kill=AsyncMock(return_value=True))
        with patch("market_harbor.time.monotonic", return_value=106.1):
            asyncio.run(env.stop())
        snapshot = budget.snapshot()
        self.assertEqual(snapshot["reserved_usd"], "0")
        self.assertEqual(snapshot["metered_usd"], "0.00021175")
        cleanup = json.loads((self.root / "cleanup-01.json").read_text())
        self.assertEqual(cleanup["metered_usd"], "0.00021175")
        self.assertTrue(cleanup["metering_receipt_sha256"])

    def test_independent_readback_is_not_a_market_score(self):
        self.outputs()
        result = worker.verify_fixture_outputs(self.root)
        self.assertTrue(result["passed"])
        self.assertEqual(result["predictions"], 3)
        self.assertIsNone(result["market_score"])
        self.assertFalse(result["research_result"])

    def test_missing_probe_checks_rejected(self):
        self.outputs()
        self.mutate("collected/isolation.json", "checks", {"unprivileged": True})
        with self.assertRaises(ValueError):
            worker.verify_fixture_outputs(self.root)

    def test_broken_chain_completion_rejected(self):
        self.outputs()
        self.mutate("collected/predictions/complete.json", "last_prediction_hash", "0" * 64)
        with self.assertRaises(ValueError):
            worker.verify_fixture_outputs(self.root)

    def test_relabelled_journal_rejected(self):
        self.outputs()
        self.mutate("collected/predictions/claim.json", "train_sha256", "0" * 64)
        with self.assertRaises(ValueError):
            worker.verify_fixture_outputs(self.root)

    def test_sandbox_runner_refuses_the_mac(self):
        from sandbox_prediction_runner import require_layout
        with patch("sandbox_prediction_runner.sys.platform", "darwin"):
            with self.assertRaises(RuntimeError):
                require_layout()

    def test_trial_construction_uses_custom_adapter_without_cloud(self):
        async def check():
            config = worker.TrialConfig(task=worker.TaskConfig(path=worker.FIXTURE),
                trial_name="offline-fixture", trials_dir=self.root / "harbor",
                agent=worker.AgentConfig(import_path="market_harbor:SequentialFixtureAgent",
                    kwargs={"control_root": str(self.root)}),
                environment=worker.EnvironmentConfig(import_path="market_harbor:BoundedMarketE2B",
                    force_build=False, kwargs={"control_root": str(self.root), "budget_path": "/nonexistent",
                                               "env_file": "/nonexistent"}),
                verifier=worker.VerifierConfig(disable=True))
            with patch.object(worker.BoundedMarketE2B, "start", AsyncMock(side_effect=AssertionError("no cloud"))):
                trial = await worker.Trial.create(config)
            try:
                self.assertIsInstance(trial.agent_environment, worker.BoundedMarketE2B)
                self.assertIsInstance(trial.agent, worker.SequentialFixtureAgent)
                self.assertIsNone(trial.agent_environment._sandbox)
                self.assertEqual(trial.task.config.agent.network_mode, NetworkMode.NO_NETWORK)
            finally:
                trial._close_logger_handler()
        asyncio.run(check())

    def test_preflight_failure_is_preserved_before_paid_dispatch(self):
        budget_path = Path(self.temp.name) / "budget"
        b = PaidBudget.create(budget_path, {"experiment_id": "fixture-budget", "cap_usd": "200",
            "target_usd": "100", "buckets_usd": {"setup": "10", "learning": "120", "final": "50", "repair": "20"},
            "authority": "offline test"})
        output = Path(self.temp.name) / "fixture-construction-failure"
        with patch.object(worker.Trial, "create", AsyncMock(side_effect=ValueError("offline fixture"))):
            with self.assertRaises(ValueError):
                asyncio.run(worker.run_fixture(output, budget_path, "/nonexistent"))
        self.assertTrue((output / "failure.json").exists())
        self.assertEqual(b.snapshot()["reserved_usd"], "0")
        with self.assertRaises(FileExistsError):
            asyncio.run(worker.run_fixture(output, budget_path, "/nonexistent"))


if __name__ == "__main__":
    unittest.main()
