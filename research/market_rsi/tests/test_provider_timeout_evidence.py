import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

from glm_canary import MODEL, RATES, cost
from market_rsi import digest, file_hash, fresh_json
from paid_budget import PaidBudget
from provider_timeout_evidence import build_uncertain_timeout, commit_uncertain_timeout
from research_context import freeze_common
from researcher_worker import CONTROLLER_REASONING_EFFORT, CONTROLLER_TEMPERATURE
from study_state import StudyState
from test_researcher_worker import task


class ProviderTimeoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        common = self.root / "common.json"
        freeze_common(common)
        tasks = [task(), task(1, "transfer")]
        self.study = StudyState.create(self.root / "study", common_manifest=common, tasks=tasks,
            baseline_source_hashes={"task-0": "b" * 64, "task-1": "b" * 64},
            max_steps_per_task=2, max_diagnostics_per_task=1, max_research_calls_per_task=4,
            deadline_utc="2099-01-01T00:00:00+00:00", worst_case_step_seconds=300)
        self.prepared = self.study.claim("learn", "timeout-trial")
        self.directory = self.root / "timeout-research"
        self.directory.mkdir()
        self.budget = PaidBudget.create(self.root / "budget", {
            "experiment_id": "fixture-research", "cap_usd": "2", "target_usd": "1",
            "buckets_usd": {"learning": "1", "final": "1"},
            "authority": "fixture uncertain timeout"})
        limits = self.prepared["audit"]["resource_limits"]
        token_ids = [1, 2, 3]
        upper = str(cost(len(token_ids), limits["max_output_tokens"]))
        claim = {"audit": self.prepared["audit"],
            "code_sha256": file_hash(Path(__file__).parents[1] / "researcher_worker.py"),
            "model": MODEL, "num_samples": 1, "sampling_retries": 0, "seed": 23,
            "temperature": CONTROLLER_TEMPERATURE,
            "reasoning_effort": CONTROLLER_REASONING_EFFORT, "tools": [],
            "live_transport": False, "nonce": "a" * 32,
            "max_input_tokens": limits["max_input_tokens"],
            "max_output_tokens": limits["max_output_tokens"]}
        request = {"messages": self.prepared["messages"], "audit": self.prepared["audit"],
            "token_ids": token_ids, "max_output_tokens": limits["max_output_tokens"],
            "upper_usd": upper, "rates": RATES}
        fresh_json(self.directory / "claim.json", claim)
        fresh_json(self.directory / "request.json", request)
        fresh_json(self.directory / "failure.json", {"error_type": "RuntimeError",
            "elapsed_seconds": 29.0, "note": "fixture timeout"})
        self.budget.reserve(self.directory.name, "learning", upper, "tinker", digest(request))
        self.budget.dispatch(self.directory.name)

        process = self.directory / "sample-process"
        process.mkdir()
        body = {"operation": "sample", "cache_dir": "/fixture/cache",
            "job_directory": str(self.directory),
            "source_hashes": {name: file_hash(Path(__file__).parents[1] / name) for name in
                ("glm_process_worker.py", "researcher_worker.py", "glm_canary.py")},
            "token_ids": token_ids, "max_output": limits["max_output_tokens"],
            "timeout_seconds": 28.0}
        raw = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        (process / "input.bin").write_bytes(raw)
        (process / "stdout.bin").write_bytes(b"")
        (process / "stderr.bin").write_bytes(b"")
        fresh_json(process / "claim.json", {
            "command_sha256": digest([sys.executable, "-I",
                str(Path(__file__).parents[1] / "glm_process_worker.py")]),
            "input_sha256": hashlib.sha256(raw).hexdigest(),
            "environment_names": ["LANG", "PATH", "RSI_TINKER_API_KEY", "TOKENIZERS_PARALLELISM"],
            "supervisor_source_sha256": file_hash(Path(__file__).parents[1] / "bounded_process.py"),
            "remote_cancellation_established": False,
            "max_stdout_bytes": 16 * 1024 * 1024, "max_stderr_bytes": 256 * 1024,
            "wall_seconds": 28.0, "reap_seconds": 2})
        empty = hashlib.sha256(b"").hexdigest()
        fresh_json(process / "receipt.json", {"failure": "local_wall_timeout",
            "process_reaped": True, "exit_code": -9, "input_complete": True,
            "input_bytes_written": len(raw), "output_complete": False,
            "remote_request_terminal": None, "remote_cancellation_established": False,
            "unused_budget_released": False, "elapsed_seconds": 28.5,
            "stdout_bytes": 0, "stdout_sha256": empty,
            "stderr_bytes": 0, "stderr_sha256": empty})

    def tearDown(self):
        self.tmp.cleanup()

    def test_timeout_is_terminal_failure_and_upper_bound_cost_not_candidate(self):
        built = build_uncertain_timeout(self.study, self.directory, self.budget,
                                          expected_live=False)
        commit_uncertain_timeout(self.study, self.directory, self.budget, built)
        snap = self.budget.snapshot()
        self.assertEqual(snap["reserved_usd"], "0")
        self.assertEqual(snap["metered_usd"], "0")
        self.assertGreater(float(snap["effective_cost_usd"]), 0)
        state = self.study.snapshot()
        self.assertIsNone(state["active"])
        public = json.loads(self.study.next_request("learn")["messages"][1]["content"])
        self.assertEqual(public["remaining_attempts"]["scoreable_candidates_remaining"], 2)
        self.assertEqual(public["remaining_attempts"]["research_calls_remaining"], 3)
        self.assertEqual(public["records"][0]["payload"]["failure"]["kind"],
                         "provider_timeout_usage_unknown")

    def test_mutated_timeout_receipt_cannot_close_claim(self):
        path = self.directory / "sample-process/receipt.json"
        value = json.loads(path.read_text())
        value["process_reaped"] = False
        path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):
            build_uncertain_timeout(self.study, self.directory, self.budget,
                                    expected_live=False)
        self.assertEqual(self.budget.snapshot()["jobs"][self.directory.name]["state"],
                         "dispatched")
        self.assertIsNotNone(self.study.snapshot()["active"])


if __name__ == "__main__":
    unittest.main()
