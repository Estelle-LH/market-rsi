"""Adversarial tests for the immutable source-scope fetch verifier."""
from __future__ import annotations

from pathlib import Path
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from market_rsi import digest, file_hash, fresh_json
from paid_budget import PaidBudget
from supervisor_harness.global_state_gate import SupervisorGlobalState
from supervisor_harness import p0_gate1_source_scope_fetch_adapter as adapter
from supervisor_harness import p0_gate1_source_scope_watched_fetch_child as child
from supervisor_harness import run_p0_gate1_source_scope_watched_fetch as parent
from supervisor_harness import source_scope_fetch_receipt as verifier
from supervisor_harness.supervisor_watchdog import SupervisorWatchdog
from supervisor_harness.test_p0_gate1_source_scope_fetch_adapter import (
    RELEASE, RUNTIME, RUNTIME_SHA256, bundle, make_binding,
)
from supervisor_harness.test_run_p0_gate1_source_scope_watched_fetch import (
    BUDGET_SHA, COMMAND_SHA, fake_runner,
)


def tree(base: Path):
    root = base / adapter.ATTEMPT_ID
    binding, _, _ = make_binding(base)
    decision = base / "decision.md"
    decision.write_text("# fixture decision\n")
    state_root = base / "global-state"
    state = SupervisorGlobalState(state_root, decision)
    before = state.initialize()
    claimed = state.claim(
        adapter.ATTEMPT_ID, expected_head_sha256=before["head_sha256"],
        source_sha256=binding["current_source_sha256"],
        prior_canary_sha256=binding["task"]["prior_canary_receipt_sha256"])
    budget_root = base / "budget"
    budget = PaidBudget.create(budget_root, {
        "experiment_id": "fixture-budget", "cap_usd": "0",
        "target_usd": "0", "buckets_usd": {"free": "0"},
        "authority": "fixture",
    })
    budget_sha = digest(budget.snapshot())
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
        command_sha256=COMMAND_SHA, budget_snapshot_sha256=budget_sha,
        claim_path=root / "supervisor-claim.json", parent_pid=os.getpid(),
        parent_command_sha256="a" * 64,
        global_state_head_sha256=claimed["head_sha256"],
        decision_doc_sha256=claimed["decision_doc_sha256"],
        global_state_root=state.root, decision_doc=decision,
        budget_root=budget_root)
    with patch.object(child, "_shared_preclaimed_runner",
                      return_value=fake_runner):
        child.execute(
            binding=binding, output=root / "snapshot", watchdog=watchdog,
            pid=os.getpid(), process_command_sha256=COMMAND_SHA,
            budget_snapshot_sha256=budget_sha)
    result = parent._finish_success(
        binding=binding, watchdog=watchdog, pid=os.getpid(),
        command_sha256=COMMAND_SHA, child_exit_code=0,
        terminal_process_absent=True, terminal_container_absent=True,
        global_state_head_sha256=claimed["head_sha256"],
        global_state_status="active_pending_independent_review",
        budget_snapshot_sha256=budget_sha, global_state=state,
        budget_root=budget_root)
    return root, binding, state, decision, budget_root, budget_sha, result


def verify(root, binding, decision, state, budget_root, budget_sha):
    result_path = root / "result.json"
    with patch.object(adapter, "RUN_ROOT", root), patch.object(
            parent, "RUN_ROOT", root), patch.object(
            parent, "GLOBAL_STATE_ROOT", state.root), patch.object(
            parent, "DECISION_DOC", decision), patch.object(
            parent, "BUDGET_ROOT", budget_root), patch.object(
            verifier, "_verify_canary_receipt",
            return_value=binding["canary_verification"]):
        return verifier.verify_fetch_receipt(
            result_path, expected_result_sha256=file_hash(result_path),
            expected_source_sha256=binding["current_source_sha256"],
            expected_runtime_sha256=RUNTIME_SHA256,
            expected_release_tag=RELEASE["tag"],
            expected_release_commit=RELEASE["commit"],
            expected_release_tag_object=RELEASE["tag_object"],
            expected_authorization_sha256=
                binding["authorization_file_sha256"],
            expected_prior_canary_receipt_sha256=
                binding["task"]["prior_canary_receipt_sha256"],
            expected_budget_snapshot_sha256=budget_sha)


class SourceScopeFetchReceiptTests(unittest.TestCase):
    def fixture(self, base):
        root = base / adapter.ATTEMPT_ID
        with patch.object(adapter, "RUN_ROOT", root):
            return tree(base)

    def test_complete_tree_passes_and_keeps_global_claim_pending_review(self):
        with tempfile.TemporaryDirectory() as temporary:
            values = self.fixture(Path(temporary).resolve())
            root, binding, state, decision, budget_root, budget_sha, _ = values
            record = verify(root, binding, decision, state, budget_root, budget_sha)
            self.assertTrue(record["passed"])
            self.assertEqual(record["requests_made"], 1)
            self.assertEqual(record["provider_calls"], 0)
            self.assertEqual(record["global_state_status"],
                             "active_pending_independent_review")
            self.assertEqual(state.snapshot()["active_cycle"],
                             adapter.ATTEMPT_ID)

    def test_result_counter_bool_extra_and_snapshot_mutations_reject(self):
        mutations = (
            lambda result: result.__setitem__("requests_made", True),
            lambda result: result.__setitem__("automatic_retries", 1),
            lambda result: result.__setitem__("extra", False),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as temporary:
                values = self.fixture(Path(temporary).resolve())
                root, binding, state, decision, budget_root, budget_sha, result = values
                mutate(result)
                (root / "result.json").unlink()
                fresh_json(root / "result.json", result)
                with self.assertRaises(ValueError):
                    verify(root, binding, decision, state, budget_root, budget_sha)
        with tempfile.TemporaryDirectory() as temporary:
            values = self.fixture(Path(temporary).resolve())
            root, binding, state, decision, budget_root, budget_sha, _ = values
            with (root / "snapshot" / "public-source.snapshot").open("ab") as handle:
                handle.write(b"attack")
            with self.assertRaises(ValueError):
                verify(root, binding, decision, state, budget_root, budget_sha)

    def test_global_close_or_wrong_authoritative_roots_reject(self):
        with tempfile.TemporaryDirectory() as temporary:
            values = self.fixture(Path(temporary).resolve())
            root, binding, state, decision, budget_root, budget_sha, _ = values
            state.close(adapter.ATTEMPT_ID, outcome="failed")
            with self.assertRaises(ValueError):
                verify(root, binding, decision, state, budget_root, budget_sha)
        with tempfile.TemporaryDirectory() as temporary:
            values = self.fixture(Path(temporary).resolve())
            root, binding, state, decision, budget_root, budget_sha, result = values
            result["budget_root"] = str(Path(temporary) / "attacker-budget")
            (root / "result.json").unlink()
            fresh_json(root / "result.json", result)
            with self.assertRaises(ValueError):
                verify(root, binding, decision, state, budget_root, budget_sha)

    def test_watchdog_first_and_last_progress_are_exact(self):
        for index in (2, -2):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as temporary:
                values = self.fixture(Path(temporary).resolve())
                root, binding, state, decision, budget_root, budget_sha, result = values
                journal = root / "watchdog" / "journal.jsonl"
                records = [json.loads(line) for line in journal.read_text().splitlines()]
                records[index]["payload"]["progress_sha256"] = "9" * 64
                # Rechain to prove the verifier checks semantic endpoints, not
                # only the generic journal hash chain.
                prior = "0" * 64
                for seq, event in enumerate(records, start=1):
                    event["seq"] = seq
                    event["prev_sha256"] = prior
                    body = {name: value for name, value in event.items()
                            if name != "sha256"}
                    event["sha256"] = digest(body)
                    prior = event["sha256"]
                journal.write_text("".join(
                    json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n"
                    for item in records))
                result["watchdog_journal_file_sha256"] = file_hash(journal)
                (root / "result.json").unlink()
                fresh_json(root / "result.json", result)
                with self.assertRaises(ValueError):
                    verify(root, binding, decision, state, budget_root, budget_sha)

    def test_symlinked_result_and_global_journal_alias_reject(self):
        with tempfile.TemporaryDirectory() as temporary:
            values = self.fixture(Path(temporary).resolve())
            root, binding, state, decision, budget_root, budget_sha, _ = values
            result_path = root / "result.json"
            real = root / "real-result.json"
            result_path.rename(real)
            result_path.symlink_to(real)
            with self.assertRaises(ValueError):
                verify(root, binding, decision, state, budget_root, budget_sha)
        with tempfile.TemporaryDirectory() as temporary:
            values = self.fixture(Path(temporary).resolve())
            root, binding, state, decision, budget_root, budget_sha, result = values
            alias = state.root / "alias.jsonl"
            alias.write_bytes(state.journal.path.read_bytes())
            result["global_state_journal_path"] = str(alias)
            result["global_state_journal_file_sha256"] = file_hash(alias)
            (root / "result.json").unlink()
            fresh_json(root / "result.json", result)
            with self.assertRaises(ValueError):
                verify(root, binding, decision, state, budget_root, budget_sha)


if __name__ == "__main__":
    unittest.main()
