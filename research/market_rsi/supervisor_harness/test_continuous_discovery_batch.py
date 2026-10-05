"""Adversarial tests for the zero-authority continuous Discovery recorder."""
from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

import supervisor_harness.continuous_discovery_batch as discovery_module
from supervisor_harness.continuous_discovery_batch import (
    BOUNDARY_FLAGS,
    BatchStoppedError,
    ContinuousDiscoveryBatch,
    DiscoveryBatchError,
    EVIDENCE_SCHEMA,
    EVIDENCE_SCHEMA_V2,
    STAGES,
    TERMINAL_STAGE,
    ZERO_SHA256,
)


BASE = datetime(2026, 9, 29, 18, 3, 21, tzinfo=timezone.utc)


def sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


class ContinuousDiscoveryBatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve() / "discovery"

    def make_batch(
        self,
        *,
        max_attempts: int = 3,
        deadline: datetime | None = None,
        root: Path | None = None,
    ) -> ContinuousDiscoveryBatch:
        batch = ContinuousDiscoveryBatch(
            root or self.root,
            allow_temporary=True,
            test_clock=lambda: BASE,
            allow_test_clock=True,
        )
        batch.initialize(
            batch_id="settlement-probability-discovery-01",
            start_utc=BASE,
            deadline_utc=deadline or BASE + timedelta(hours=2),
            max_attempts=max_attempts,
            initial_incumbent={
                "candidate_id": "market-baseline",
                "candidate_sha256": sha("market-baseline"),
                "scorecard_sha256": sha("baseline-scorecard"),
                "review_sha256": ZERO_SHA256,
            },
        )
        return batch

    def make_v2_batch(
        self,
        *,
        capacity: int = 2,
        max_attempts: int = 10,
        root: Path | None = None,
        reserve: float = 0.30,
        reserve_reason: str | None = None,
        archived_parents: list[dict] | None = None,
    ) -> ContinuousDiscoveryBatch:
        batch = ContinuousDiscoveryBatch(
            root or self.root,
            allow_temporary=True,
            test_clock=lambda: BASE,
            allow_test_clock=True,
        )
        batch.initialize(
            batch_id="settlement-probability-discovery-v2",
            start_utc=BASE,
            deadline_utc=BASE + timedelta(hours=2),
            max_attempts=max_attempts,
            initial_incumbent={
                "candidate_id": "market-baseline",
                "candidate_sha256": sha("market-baseline"),
                "scorecard_sha256": sha("baseline-scorecard"),
                "review_sha256": ZERO_SHA256,
            },
            active_pool_capacity=capacity,
            exploration_reserve_fraction=reserve,
            exploration_reserve_reason=reserve_reason,
            initial_archived_parents=archived_parents,
        )
        return batch

    def archived_parent(self, label: str = "v0-negative") -> dict:
        return {
            "candidate_id": f"market-plus-state-{label}",
            "candidate_sha256": sha(f"{label}:candidate"),
            "source_batch_id": "prior-discovery-batch",
            "source_attempt_id": f"attempt-{label}",
            "archive_manifest_sha256": sha(f"{label}:archive"),
            "independent_review_sha256": sha(f"{label}:review"),
            "authority_snapshot_sha256": sha(f"{label}:authority"),
            "problem_id": "in-game-settlement",
            "question_digest_sha256": sha(f"{label}:question"),
            "evidence_bundle_sha256": sha(f"{label}:evidence"),
            "research_credit": 2,
            "research_outcome": "refute",
            "route_action": "branch",
            "authority_granted": False,
        }

    def complete_v2(
        self,
        batch: ContinuousDiscoveryBatch,
        attempt_id: str,
        *,
        minute: int,
        decision: str = "REVERT",
        credit: int = 1,
        outcome: str | None = None,
        route_action: str | None = None,
        independent: bool = True,
        execution_outcome: str = "succeeded",
    ) -> dict:
        batch.mark_implementation_ready(
            attempt_id,
            runner_sha256=sha(f"{attempt_id}:runner"),
            spec_sha256=sha(f"{attempt_id}:spec"),
            now=BASE + timedelta(minutes=minute),
        )
        batch.claim_execution(
            attempt_id,
            claim_id=f"{attempt_id}-claim",
            now=BASE + timedelta(minutes=minute, seconds=10),
        )
        batch.mark_execution_terminal(
            attempt_id,
            claim_id=f"{attempt_id}-claim",
            outcome=execution_outcome,
            execution_receipt_sha256=sha(f"{attempt_id}:receipt"),
            now=BASE + timedelta(minutes=minute, seconds=20),
        )
        batch.record_result_review(
            attempt_id,
            decision=decision,
            scorecard_sha256=sha(f"{attempt_id}:scorecard"),
            review_sha256=sha(f"{attempt_id}:review"),
            independently_reviewed=independent,
            now=BASE + timedelta(minutes=minute, seconds=30),
        )
        if outcome is None:
            outcome = {0: "invalid", 1: "inconclusive", 2: "support"}[credit]
        if route_action is None:
            route_action = {
                0: "cooldown", 1: "bounded_followup", 2: "continue"
            }[credit]
        batch.record_research_credit(
            attempt_id,
            credit=credit,
            evidence_bundle_sha256=sha(f"{attempt_id}:credit-evidence"),
            problem_id="settlement-probability",
            question_id=f"question-{attempt_id}",
            question_digest_sha256=sha(f"{attempt_id}:question"),
            authority_snapshot_sha256=sha(f"{attempt_id}:authority"),
            predeclared_rule_sha256=sha(f"{attempt_id}:rule"),
            outcome=outcome,
            route_action=route_action,
            credit_review_sha256=sha(f"{attempt_id}:credit-review"),
            reason=f"research value {credit} for {attempt_id}",
            now=BASE + timedelta(minutes=minute, seconds=40),
        )
        return batch.mark_controller_feedback_ready(
            attempt_id, now=BASE + timedelta(minutes=minute, seconds=50)
        )

    def pool_member(
        self,
        attempt_id: str,
        *,
        parent: str | None = None,
        allocation: str = "exploitation",
        method_family: str = "linear",
    ) -> dict:
        return {
            "attempt_id": attempt_id,
            "candidate_id": f"candidate-{attempt_id}",
            "controller_decision_sha256": sha(f"{attempt_id}:controller"),
            "research_parent_sha256": parent or sha("market-baseline"),
            "allocation": allocation,
            "method_family": method_family,
            "hypothesis_digest_sha256": sha(f"{attempt_id}:hypothesis"),
            "question_id": f"question-{attempt_id}",
            "question_digest_sha256": sha(f"{attempt_id}:question"),
            "predeclared_rule_sha256": sha(f"{attempt_id}:rule"),
            "resource_hint": {
                "resource_class": "small_experiment",
                "max_attempts": 1,
                "max_time_seconds": 600,
                "max_bytes": 0,
                "max_cost_usd": 0.0,
                "authority_granted": False,
            },
        }

    def ready(
        self,
        batch: ContinuousDiscoveryBatch,
        attempt_id: str = "attempt-01",
        *,
        candidate_id: str = "candidate-01",
    ) -> tuple[str, str]:
        runner, spec = sha(f"{attempt_id}:runner"), sha(f"{attempt_id}:spec")
        minute = 1 if attempt_id == "attempt-01" else 6
        selected = batch.select_controller_candidate(
            attempt_id,
            candidate_id=candidate_id,
            controller_decision_sha256=sha(f"{attempt_id}:controller"),
            now=BASE + timedelta(minutes=minute),
        )
        self.assertEqual(selected["branches"][-1]["stage"], STAGES[0])
        implemented = batch.mark_implementation_ready(
            attempt_id,
            runner_sha256=runner,
            spec_sha256=spec,
            now=BASE + timedelta(minutes=minute, seconds=30),
        )
        self.assertEqual(implemented["branches"][-1]["stage"], STAGES[1])
        return runner, spec

    def finish(
        self,
        batch: ContinuousDiscoveryBatch,
        attempt_id: str = "attempt-01",
        *,
        outcome: str = "succeeded",
        decision: str = "KEEP",
        independent: bool = True,
    ) -> dict:
        claim_id = f"{attempt_id}-claim"
        batch.claim_execution(
            attempt_id,
            claim_id=claim_id,
            now=BASE + timedelta(minutes=2),
        )
        batch.mark_execution_terminal(
            attempt_id,
            claim_id=claim_id,
            outcome=outcome,
            execution_receipt_sha256=sha(f"{attempt_id}:execution"),
            now=BASE + timedelta(minutes=3),
        )
        batch.record_result_review(
            attempt_id,
            decision=decision,
            scorecard_sha256=sha(f"{attempt_id}:scorecard"),
            review_sha256=sha(f"{attempt_id}:review"),
            independently_reviewed=independent,
            now=BASE + timedelta(minutes=4),
        )
        return batch.mark_controller_feedback_ready(
            attempt_id, now=BASE + timedelta(minutes=5)
        )

    def test_full_stage_chain_keep_updates_separate_incumbent_and_packet(self) -> None:
        batch = self.make_batch()
        runner, spec = self.ready(batch)
        final = self.finish(batch)

        branch = final["branches"][0]
        self.assertEqual(branch["stage"], TERMINAL_STAGE)
        self.assertEqual(final["active_attempt_id"], None)
        self.assertEqual(final["attempts_claimed"], 1)
        self.assertEqual(final["failed_attempts"], 0)
        self.assertEqual(final["incumbent"]["candidate_id"], "candidate-01")
        self.assertEqual(final["incumbent"]["candidate_sha256"], runner)
        self.assertEqual(len(final["incumbent_history"]), 2)
        self.assertEqual(final["incumbent_history"][0]["source"], "batch_start")
        self.assertEqual(
            final["incumbent_history"][1]["source"],
            "independently_reviewed_keep",
        )

        packet = branch["feedback_packet"]
        self.assertEqual(packet["schema"], EVIDENCE_SCHEMA)
        self.assertEqual(packet["runner_sha256"], runner)
        self.assertEqual(packet["spec_sha256"], spec)
        self.assertEqual(
            packet["execution_receipt_sha256"], sha("attempt-01:execution")
        )
        self.assertEqual(packet["scorecard_sha256"], sha("attempt-01:scorecard"))
        self.assertEqual(packet["review_sha256"], sha("attempt-01:review"))
        self.assertEqual(packet["evidence_scope"], "reused_opened_train_discovery_only")
        self.assertIs(packet["authority_granted"], False)
        self.assertNotIn("metrics", packet)
        self.assertNotIn("data", packet)

        self.assertEqual(final["boundary_flags"], BOUNDARY_FLAGS)
        self.assertTrue(final["boundary_flags"]["resident_opened_train_only"])
        self.assertTrue(
            all(
                final["boundary_flags"][name] is False
                for name in (
                    "protected_dev_final_allowed",
                    "network_allowed",
                    "paid_provider_allowed",
                    "publication_allowed",
                    "promotion_allowed",
                    "executes_runners",
                    "scores_results",
                    "opens_data",
                    "grants_authority",
                )
            )
        )

    def test_revert_and_unreviewed_keep_cannot_replace_incumbent(self) -> None:
        batch = self.make_batch()
        self.ready(batch)
        claim_id = "attempt-01-claim"
        batch.claim_execution(
            "attempt-01", claim_id=claim_id, now=BASE + timedelta(minutes=2)
        )
        batch.mark_execution_terminal(
            "attempt-01",
            claim_id=claim_id,
            outcome="failed",
            execution_receipt_sha256=sha("failed-execution"),
            now=BASE + timedelta(minutes=3),
        )
        before = batch.snapshot()
        before_journal = before["journal_length"]
        with self.assertRaisesRegex(DiscoveryBatchError, "successful execution"):
            batch.record_result_review(
                "attempt-01",
                decision="KEEP",
                scorecard_sha256=sha("scorecard"),
                review_sha256=sha("review"),
                independently_reviewed=True,
            )
        self.assertEqual(batch.snapshot()["journal_length"], before_journal)

        reverted = batch.record_result_review(
            "attempt-01",
            decision="REVERT",
            scorecard_sha256=sha("scorecard"),
            review_sha256=sha("review"),
            independently_reviewed=True,
            now=BASE + timedelta(minutes=4),
        )
        self.assertEqual(reverted["failed_attempts"], 1)
        self.assertEqual(reverted["incumbent"], before["incumbent"])
        self.assertEqual(len(reverted["incumbent_history"]), 1)

        second_root = Path(self.temporary.name).resolve() / "unreviewed-keep"
        second = self.make_batch(root=second_root)
        self.ready(second)
        second.claim_execution(
            "attempt-01",
            claim_id="attempt-01-claim",
            now=BASE + timedelta(minutes=2),
        )
        second.mark_execution_terminal(
            "attempt-01",
            claim_id="attempt-01-claim",
            outcome="succeeded",
            execution_receipt_sha256=sha("execution"),
            now=BASE + timedelta(minutes=3),
        )
        with self.assertRaisesRegex(DiscoveryBatchError, "independent review"):
            second.record_result_review(
                "attempt-01",
                decision="KEEP",
                scorecard_sha256=sha("scorecard"),
                review_sha256=sha("review"),
                independently_reviewed=False,
                now=BASE + timedelta(minutes=4),
            )
        self.assertEqual(len(second.snapshot()["incumbent_history"]), 1)

    def test_claim_is_exactly_once_and_valid_prefix_snapshot_recovers(self) -> None:
        batch = self.make_batch()
        self.ready(batch)
        old_snapshot = batch.snapshot_path.read_bytes()
        claimed = batch.claim_execution(
            "attempt-01",
            claim_id="attempt-01-claim",
            now=BASE + timedelta(minutes=2),
        )
        claimed_journal_length = claimed["journal_length"]
        self.assertEqual(claimed["attempts_claimed"], 1)

        # Simulate process loss after the journal fsync and before snapshot replace.
        batch.snapshot_path.write_bytes(old_snapshot)
        recovered = ContinuousDiscoveryBatch(
            self.root, allow_temporary=True
        ).snapshot()
        self.assertEqual(recovered["attempts_claimed"], 1)
        self.assertEqual(recovered["journal_length"], claimed_journal_length)
        self.assertEqual(recovered["branches"][0]["stage"], "execution_claimed")

        replayed = batch.claim_execution(
            "attempt-01",
            claim_id="attempt-01-claim",
            now=BASE + timedelta(minutes=4),
        )
        self.assertEqual(replayed["attempts_claimed"], 1)
        self.assertEqual(replayed["journal_length"], claimed_journal_length)
        with self.assertRaisesRegex(DiscoveryBatchError, "different ID"):
            batch.claim_execution(
                "attempt-01",
                claim_id="different-claim",
                now=BASE + timedelta(minutes=4),
            )
        self.assertEqual(batch.snapshot()["journal_length"], claimed_journal_length)

        batch.snapshot_path.unlink()
        rebuilt = batch.snapshot()
        self.assertEqual(rebuilt["state_sha256"], recovered["state_sha256"])

    def test_failed_terminal_replay_counts_once(self) -> None:
        batch = self.make_batch()
        self.ready(batch)
        batch.claim_execution(
            "attempt-01",
            claim_id="attempt-01-claim",
            now=BASE + timedelta(minutes=2),
        )
        first = batch.mark_execution_terminal(
            "attempt-01",
            claim_id="attempt-01-claim",
            outcome="implementation_failed",
            execution_receipt_sha256=sha("failure-receipt"),
            now=BASE + timedelta(minutes=3),
        )
        second = batch.mark_execution_terminal(
            "attempt-01",
            claim_id="attempt-01-claim",
            outcome="implementation_failed",
            execution_receipt_sha256=sha("failure-receipt"),
            now=BASE + timedelta(minutes=4),
        )
        self.assertEqual(first["attempts_claimed"], 1)
        self.assertEqual(first["failed_attempts"], 1)
        self.assertEqual(second["failed_attempts"], 1)
        self.assertEqual(second["journal_length"], first["journal_length"])

        before = batch.snapshot()["journal_length"]
        with self.assertRaisesRegex(DiscoveryBatchError, "match|changed"):
            batch.mark_execution_terminal(
                "attempt-01",
                claim_id="wrong-claim",
                outcome="implementation_failed",
                execution_receipt_sha256=sha("failure-receipt"),
                now=BASE + timedelta(minutes=4),
            )
        self.assertEqual(batch.snapshot()["journal_length"], before)

    def test_deadline_and_attempt_count_stop_new_claims(self) -> None:
        deadline_batch = self.make_batch(deadline=BASE + timedelta(minutes=10))
        self.ready(deadline_batch)
        with self.assertRaisesRegex(BatchStoppedError, "deadline_reached"):
            deadline_batch.claim_execution(
                "attempt-01",
                claim_id="attempt-01-claim",
                now=BASE + timedelta(minutes=10),
            )
        stopped = deadline_batch.snapshot()
        self.assertEqual(stopped["stopped_reason"], "deadline_reached")
        self.assertEqual(stopped["attempts_claimed"], 0)

        count_root = Path(self.temporary.name).resolve() / "count-stop"
        count_batch = self.make_batch(max_attempts=1, root=count_root)
        self.ready(count_batch)
        finished = self.finish(count_batch)
        self.assertEqual(finished["stopped_reason"], "max_attempts_reached")
        self.assertEqual(finished["attempts_claimed"], 1)
        with self.assertRaisesRegex(BatchStoppedError, "max_attempts_reached"):
            count_batch.select_controller_candidate(
                "attempt-02",
                candidate_id="candidate-02",
                controller_decision_sha256=sha("controller-02"),
                now=BASE + timedelta(minutes=5),
            )

    def test_terminal_branch_is_immutable_and_new_branch_preserves_history(self) -> None:
        batch = self.make_batch()
        self.ready(batch)
        terminal = self.finish(batch)
        terminal_hash = terminal["state_sha256"]
        replay = batch.mark_controller_feedback_ready("attempt-01")
        self.assertEqual(replay["state_sha256"], terminal_hash)

        with self.assertRaises(DiscoveryBatchError):
            batch.record_result_review(
                "attempt-01",
                decision="REVERT",
                scorecard_sha256=sha("different-scorecard"),
                review_sha256=sha("different-review"),
                independently_reviewed=True,
            )

        self.ready(batch, "attempt-02", candidate_id="candidate-02")
        state = batch.snapshot()
        self.assertEqual(len(state["branches"]), 2)
        self.assertEqual(state["branches"][0]["stage"], TERMINAL_STAGE)
        self.assertEqual(
            state["branches"][1]["parent_incumbent_sha256"],
            sha("attempt-01:runner"),
        )

    def test_invalid_initialization_does_not_poison_and_boundaries_are_fixed(self) -> None:
        batch = ContinuousDiscoveryBatch(self.root, allow_temporary=True)
        expanded = dict(BOUNDARY_FLAGS, network_allowed=True)
        with self.assertRaisesRegex(DiscoveryBatchError, "cannot expand"):
            batch.initialize(
                batch_id="bad",
                start_utc=BASE,
                deadline_utc=BASE + timedelta(hours=1),
                max_attempts=1,
                initial_incumbent={
                    "candidate_id": "baseline",
                    "candidate_sha256": sha("baseline"),
                    "scorecard_sha256": sha("scorecard"),
                    "review_sha256": ZERO_SHA256,
                },
                boundary_flags=expanded,
            )
        self.assertFalse(batch.journal_dir.exists())
        valid = self.make_batch()
        self.assertTrue(valid.snapshot()["initialized"])

    def test_nonlocal_paths_and_symlinks_are_rejected(self) -> None:
        with self.assertRaisesRegex(DiscoveryBatchError, "absolute"):
            ContinuousDiscoveryBatch("relative/path")
        with self.assertRaisesRegex(DiscoveryBatchError, "cloud-backed"):
            ContinuousDiscoveryBatch("/Users/example/Google Drive/discovery")
        with self.assertRaisesRegex(DiscoveryBatchError, "temporary"):
            ContinuousDiscoveryBatch(self.root)

        target = Path(self.temporary.name).resolve() / "target"
        target.mkdir()
        link = Path(self.temporary.name).resolve() / "linked"
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError as exc:  # pragma: no cover - platform capability
            self.skipTest(f"symlinks unavailable: {exc}")
        with self.assertRaisesRegex(DiscoveryBatchError, "symlink"):
            ContinuousDiscoveryBatch(link, allow_temporary=True)

    def test_snapshot_and_journal_corruption_fail_closed(self) -> None:
        batch = self.make_batch()
        batch.snapshot_path.write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(DiscoveryBatchError, "hash changed"):
            batch.snapshot()

        other_root = Path(self.temporary.name).resolve() / "journal-corruption"
        other = self.make_batch(root=other_root)
        self.ready(other)
        journal = other.journal_dir / "00000002.json"
        record = json.loads(journal.read_text(encoding="utf-8"))
        record["payload"]["candidate_id"] = "tampered"
        journal.write_text(
            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(DiscoveryBatchError, "hash chain changed"):
            other.snapshot()

    def test_module_has_no_runner_network_provider_or_data_capability(self) -> None:
        source_path = Path(__file__).with_name("continuous_discovery_batch.py")
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        self.assertTrue(
            imports.isdisjoint(
                {
                    "subprocess", "socket", "requests", "urllib", "httpx",
                    "aiohttp", "pandas", "numpy", "duckdb",
                }
            )
        )
        public_methods = {
            name
            for name in vars(ContinuousDiscoveryBatch)
            if not name.startswith("_")
        }
        self.assertTrue(
            public_methods.isdisjoint(
                {"run", "execute", "score", "open_data", "authorize", "publish"}
            )
        )

    def test_production_clock_rejects_caller_time_and_enforces_deadline(self) -> None:
        actual = datetime.now(timezone.utc)
        production_root = Path(self.temporary.name).resolve() / "production-clock"
        production = ContinuousDiscoveryBatch(production_root, allow_temporary=True)
        production.initialize(
            batch_id="production-clock",
            start_utc=actual - timedelta(hours=2),
            deadline_utc=actual - timedelta(hours=1),
            max_attempts=1,
            initial_incumbent={
                "candidate_id": "baseline",
                "candidate_sha256": sha("baseline"),
                "scorecard_sha256": sha("baseline-scorecard"),
                "review_sha256": ZERO_SHA256,
            },
        )
        with self.assertRaisesRegex(DiscoveryBatchError, "only in tests"):
            production.select_controller_candidate(
                "attempt-backdated",
                candidate_id="candidate",
                controller_decision_sha256=sha("decision"),
                now=actual - timedelta(hours=1, minutes=30),
            )
        with self.assertRaisesRegex(BatchStoppedError, "deadline_reached"):
            production.select_controller_candidate(
                "attempt-current",
                candidate_id="candidate",
                controller_decision_sha256=sha("decision"),
            )
        self.assertEqual(production.snapshot()["attempts_claimed"], 0)

        with self.assertRaisesRegex(DiscoveryBatchError, "explicit test-only"):
            ContinuousDiscoveryBatch(
                Path(self.temporary.name).resolve() / "unapproved-clock",
                allow_temporary=True,
                test_clock=lambda: BASE,
            )

    def test_event_times_cannot_move_backward(self) -> None:
        batch = self.make_batch()
        batch.select_controller_candidate(
            "attempt-01",
            candidate_id="candidate-01",
            controller_decision_sha256=sha("controller"),
            now=BASE + timedelta(minutes=5),
        )
        before = batch.snapshot()["journal_length"]
        with self.assertRaisesRegex(DiscoveryBatchError, "moved backward"):
            batch.mark_implementation_ready(
                "attempt-01",
                runner_sha256=sha("runner"),
                spec_sha256=sha("spec"),
                now=BASE + timedelta(minutes=4),
            )
        self.assertEqual(batch.snapshot()["journal_length"], before)

        batch.mark_implementation_ready(
            "attempt-01",
            runner_sha256=sha("runner"),
            spec_sha256=sha("spec"),
            now=BASE + timedelta(minutes=6),
        )
        before = batch.snapshot()["journal_length"]
        with self.assertRaisesRegex(DiscoveryBatchError, "predates|moved backward"):
            batch.claim_execution(
                "attempt-01",
                claim_id="claim-01",
                now=BASE + timedelta(minutes=4),
            )
        self.assertEqual(batch.snapshot()["journal_length"], before)

        batch.claim_execution(
            "attempt-01",
            claim_id="claim-01",
            now=BASE + timedelta(minutes=7),
        )
        before = batch.snapshot()["journal_length"]
        with self.assertRaisesRegex(DiscoveryBatchError, "predates"):
            batch.mark_execution_terminal(
                "attempt-01",
                claim_id="claim-01",
                outcome="succeeded",
                execution_receipt_sha256=sha("receipt"),
                now=BASE + timedelta(minutes=6),
            )
        self.assertEqual(batch.snapshot()["journal_length"], before)

    def test_private_modes_hardlinks_root_replacement_and_read_race_reject(self) -> None:
        unsafe_root = Path(self.temporary.name).resolve() / "unsafe-mode"
        unsafe_root.mkdir(mode=0o700)
        os.chmod(unsafe_root, 0o777)
        unsafe = ContinuousDiscoveryBatch(unsafe_root, allow_temporary=True)
        with self.assertRaisesRegex(DiscoveryBatchError, "group/world writable"):
            unsafe.initialize(
                batch_id="unsafe-mode",
                start_utc=BASE,
                deadline_utc=BASE + timedelta(hours=1),
                max_attempts=1,
                initial_incumbent={
                    "candidate_id": "baseline",
                    "candidate_sha256": sha("baseline"),
                    "scorecard_sha256": sha("scorecard"),
                    "review_sha256": ZERO_SHA256,
                },
            )

        for kind in ("journal", "snapshot", "lock"):
            hard_root = Path(self.temporary.name).resolve() / f"hard-{kind}"
            hard = self.make_batch(root=hard_root)
            if kind == "journal":
                source = hard.journal_dir / "00000001.json"
            elif kind == "snapshot":
                source = hard.snapshot_path
            else:
                source = hard.lock_path
            alias = hard_root / f"{kind}-alias"
            os.link(source, alias)
            with self.subTest(kind=kind), self.assertRaisesRegex(
                DiscoveryBatchError, "exactly one link"
            ):
                hard.snapshot()

        replaced_root = Path(self.temporary.name).resolve() / "replace-root"
        replaced = self.make_batch(root=replaced_root)
        displaced = replaced_root.with_name("replace-root-old")
        replaced_root.rename(displaced)
        replaced_root.mkdir(mode=0o700)
        with self.assertRaisesRegex(DiscoveryBatchError, "identity changed"):
            replaced.snapshot()

        race_root = Path(self.temporary.name).resolve() / "read-race"
        raced = self.make_batch(root=race_root)
        replacement = race_root / "replacement.json"
        replacement.write_bytes(raced.snapshot_path.read_bytes())
        os.chmod(replacement, 0o600)
        original_read = discovery_module.os.read
        swapped = False

        def replace_after_read(fd: int, count: int) -> bytes:
            nonlocal swapped
            data = original_read(fd, count)
            if not swapped:
                swapped = True
                os.replace(replacement, raced.snapshot_path)
            return data

        with mock.patch.object(discovery_module.os, "read", side_effect=replace_after_read):
            with self.assertRaisesRegex(
                DiscoveryBatchError, "identity changed|changed while being read"
            ):
                raced._read_snapshot()

    def test_journal_and_lock_replacements_reject_for_same_object(self) -> None:
        journal_root = Path(self.temporary.name).resolve() / "replace-journal"
        journal_batch = self.make_batch(root=journal_root)
        journal_old = journal_root / "journal-old"
        journal_batch.journal_dir.rename(journal_old)
        shutil.copytree(journal_old, journal_batch.journal_dir)
        os.chmod(journal_batch.journal_dir, 0o700)
        for entry in journal_batch.journal_dir.iterdir():
            os.chmod(entry, 0o600)

        with self.assertRaisesRegex(DiscoveryBatchError, "journal identity changed"):
            journal_batch.snapshot()

        restarted = ContinuousDiscoveryBatch(
            journal_root,
            allow_temporary=True,
            test_clock=lambda: BASE,
            allow_test_clock=True,
        )
        self.assertEqual(restarted.snapshot()["journal_length"], 1)

        lock_root = Path(self.temporary.name).resolve() / "replace-lock"
        lock_batch = self.make_batch(root=lock_root)
        lock_old = lock_root / ".batch.lock-old"
        lock_batch.lock_path.rename(lock_old)
        lock_batch.lock_path.write_bytes(b"")
        os.chmod(lock_batch.lock_path, 0o600)

        with self.assertRaisesRegex(DiscoveryBatchError, "lock identity changed"):
            lock_batch.snapshot()

    def test_journal_swap_between_read_and_append_fails_without_event(self) -> None:
        root = Path(self.temporary.name).resolve() / "swap-during-commit"
        batch = self.make_batch(root=root)
        original_read_records = batch._read_records
        journal_old = root / "journal-old"
        swapped = False

        def read_then_swap() -> list[dict[str, object]]:
            nonlocal swapped
            records = original_read_records()
            if not swapped:
                swapped = True
                batch.journal_dir.rename(journal_old)
                shutil.copytree(journal_old, batch.journal_dir)
                os.chmod(batch.journal_dir, 0o700)
                for entry in batch.journal_dir.iterdir():
                    os.chmod(entry, 0o600)
            return records

        with mock.patch.object(batch, "_read_records", side_effect=read_then_swap):
            with self.assertRaisesRegex(DiscoveryBatchError, "journal identity changed"):
                batch.select_controller_candidate(
                    "attempt-01",
                    candidate_id="candidate-01",
                    controller_decision_sha256=sha("controller"),
                    now=BASE + timedelta(minutes=1),
                )

        restarted = ContinuousDiscoveryBatch(
            root,
            allow_temporary=True,
            test_clock=lambda: BASE,
            allow_test_clock=True,
        )
        self.assertEqual(restarted.snapshot()["journal_length"], 1)
        self.assertEqual(restarted.snapshot()["attempts_claimed"], 0)

    def test_pending_journal_crash_recovery_preserves_chain(self) -> None:
        batch = self.make_batch()
        initial = batch.snapshot()
        pending_unpublished = batch.journal_dir / (
            ".pending-00000002-" + "a" * 32 + ".tmp"
        )
        pending_unpublished.write_bytes(b"{")
        os.chmod(pending_unpublished, 0o600)
        recovered = batch.snapshot()
        self.assertFalse(pending_unpublished.exists())
        self.assertEqual(recovered["journal_length"], 1)
        self.assertEqual(recovered["journal_head_sha256"], initial["journal_head_sha256"])

        pending_linked = batch.journal_dir / (
            ".pending-00000001-" + "b" * 32 + ".tmp"
        )
        os.link(batch.journal_dir / "00000001.json", pending_linked)
        linked_recovery = batch.snapshot()
        self.assertFalse(pending_linked.exists())
        self.assertEqual(linked_recovery["journal_head_sha256"], initial["journal_head_sha256"])
        self.assertEqual((batch.journal_dir / "00000001.json").stat().st_nlink, 1)

        pending_aliased = batch.journal_dir / (
            ".pending-00000002-" + "c" * 32 + ".tmp"
        )
        pending_aliased.write_bytes(b"partial")
        os.chmod(pending_aliased, 0o600)
        os.link(pending_aliased, batch.root / "outside-alias")
        with self.assertRaisesRegex(DiscoveryBatchError, "hard-linked"):
            batch.snapshot()

    def test_atomic_journal_faults_leave_zero_or_one_complete_claim(self) -> None:
        before_root = Path(self.temporary.name).resolve() / "prepublish-fault"
        before = self.make_batch(root=before_root)
        self.ready(before)
        with mock.patch.object(
            discovery_module, "_write_all", side_effect=OSError("write interrupted")
        ):
            with self.assertRaisesRegex(OSError, "write interrupted"):
                before.claim_execution(
                    "attempt-01",
                    claim_id="claim-01",
                    now=BASE + timedelta(minutes=2),
                )
        before_state = before.snapshot()
        self.assertEqual(before_state["attempts_claimed"], 0)
        self.assertEqual(before_state["branches"][0]["stage"], "implementation_ready")
        self.assertFalse(any(name.startswith(".pending-") for name in os.listdir(before.journal_dir)))

        linked_root = Path(self.temporary.name).resolve() / "linked-then-fault"
        linked = self.make_batch(root=linked_root)
        self.ready(linked)
        original_link = discovery_module.os.link

        def publish_then_interrupt(*args, **kwargs):
            original_link(*args, **kwargs)
            raise OSError("interrupted after publish")

        with mock.patch.object(
            discovery_module.os, "link", side_effect=publish_then_interrupt
        ):
            with self.assertRaisesRegex(OSError, "after publish"):
                linked.claim_execution(
                    "attempt-01",
                    claim_id="claim-01",
                    now=BASE + timedelta(minutes=2),
                )
        linked_state = linked.snapshot()
        self.assertEqual(linked_state["attempts_claimed"], 1)
        self.assertEqual(linked_state["branches"][0]["stage"], "execution_claimed")
        replayed = linked.claim_execution(
            "attempt-01",
            claim_id="claim-01",
            now=BASE + timedelta(minutes=3),
        )
        self.assertEqual(replayed["attempts_claimed"], 1)

        fsync_root = Path(self.temporary.name).resolve() / "directory-fsync-fault"
        fsync_batch = self.make_batch(root=fsync_root)
        self.ready(fsync_batch)
        original_fsync = discovery_module.os.fsync
        calls = 0

        def fail_first_directory_fsync(fd: int) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("directory fsync interrupted")
            original_fsync(fd)

        with mock.patch.object(
            discovery_module.os, "fsync", side_effect=fail_first_directory_fsync
        ):
            with self.assertRaisesRegex(OSError, "directory fsync"):
                fsync_batch.claim_execution(
                    "attempt-01",
                    claim_id="claim-01",
                    now=BASE + timedelta(minutes=2),
                )
        fsync_state = fsync_batch.snapshot()
        self.assertEqual(fsync_state["attempts_claimed"], 1)
        self.assertEqual(fsync_state["branches"][0]["claim_id"], "claim-01")

    def test_v2_initial_archived_parent_is_hash_bound_and_not_incumbent(self) -> None:
        archived = self.archived_parent()
        root = Path(self.temporary.name).resolve() / "cross-batch-parent"
        batch = self.make_v2_batch(
            capacity=2, root=root, archived_parents=[archived]
        )
        state = batch.snapshot()
        self.assertEqual(state["incumbent"]["candidate_sha256"], sha("market-baseline"))
        self.assertEqual(state["initial_archived_parents"], [archived])
        self.assertEqual(
            batch.pool_selection_hint()["ranked_research_parents"][0][
                "candidate_sha256"
            ],
            archived["candidate_sha256"],
        )
        selected = batch.select_controller_pool(
            [
                self.pool_member(
                    "cross-batch-child", parent=archived["candidate_sha256"]
                ),
                self.pool_member(
                    "support-geometry-child",
                    parent=archived["candidate_sha256"],
                    allocation="exploration",
                    method_family="tree",
                ),
            ],
            now=BASE + timedelta(minutes=1),
        )
        child = selected["branches"][0]
        self.assertEqual(child["research_parent_sha256"], archived["candidate_sha256"])
        self.assertEqual(
            child["comparison_incumbent_sha256"], sha("market-baseline")
        )
        self.assertNotEqual(
            child["research_parent_sha256"], child["comparison_incumbent_sha256"]
        )
        batch.snapshot_path.unlink()
        recovered = ContinuousDiscoveryBatch(root, allow_temporary=True).snapshot()
        self.assertEqual(recovered, selected)

        unknown = self.make_v2_batch(
            capacity=2,
            root=Path(self.temporary.name).resolve() / "unknown-archive-parent",
        )
        with self.assertRaisesRegex(DiscoveryBatchError, "not an archived branch"):
            unknown.select_controller_pool(
                [
                    self.pool_member("unknown-child", parent=sha("unknown-parent")),
                    self.pool_member(
                        "unknown-control",
                        allocation="exploration",
                        method_family="tree",
                    ),
                ],
                now=BASE + timedelta(minutes=1),
            )

        with self.assertRaisesRegex(DiscoveryBatchError, "duplicate"):
            self.make_v2_batch(
                capacity=2,
                root=Path(self.temporary.name).resolve() / "duplicate-archive-parent",
                archived_parents=[archived, dict(archived)],
            )
        expanded = dict(archived, authority_granted=True)
        with self.assertRaisesRegex(DiscoveryBatchError, "cannot grant authority"):
            self.make_v2_batch(
                capacity=2,
                root=Path(self.temporary.name).resolve() / "authorized-archive-parent",
                archived_parents=[expanded],
            )
        for invalid_credit in (True, False, 1.0, 2.0, 0, 3):
            with self.subTest(invalid_archived_credit=invalid_credit), self.assertRaisesRegex(
                DiscoveryBatchError, "research credit must be 1 or 2"
            ):
                invalid = dict(archived, research_credit=invalid_credit)
                self.make_v2_batch(
                    capacity=2,
                    root=(
                        Path(self.temporary.name).resolve()
                        / f"invalid-archive-credit-{type(invalid_credit).__name__}-{invalid_credit}"
                    ),
                    archived_parents=[invalid],
                )

    def test_v2_revert_branch_can_be_real_parent_separate_from_incumbent(self) -> None:
        batch = self.make_v2_batch(capacity=2)
        baseline = sha("market-baseline")
        batch.select_controller_pool(
            [
                self.pool_member("attempt-01"),
                self.pool_member(
                    "attempt-control",
                    allocation="exploration",
                    method_family="tree",
                ),
            ],
            now=BASE + timedelta(minutes=1),
        )
        reverted = self.complete_v2(
            batch, "attempt-01", minute=2, decision="REVERT", credit=2
        )
        self.complete_v2(
            batch, "attempt-control", minute=3, decision="REVERT", credit=0
        )
        self.assertEqual(reverted["incumbent"]["candidate_sha256"], baseline)
        self.assertEqual(reverted["branches"][0]["review_decision"], "REVERT")

        state = batch.select_controller_pool(
            [
                self.pool_member(
                    "attempt-02", parent=sha("attempt-01:runner")
                ),
                self.pool_member(
                    "attempt-03",
                    allocation="exploration",
                    method_family="calibration",
                ),
            ],
            now=BASE + timedelta(minutes=4),
        )
        child = state["branches"][2]
        self.assertEqual(child["research_parent_sha256"], sha("attempt-01:runner"))
        self.assertEqual(child["comparison_incumbent_sha256"], baseline)
        self.assertNotEqual(
            child["research_parent_sha256"], child["comparison_incumbent_sha256"]
        )
        self.assertEqual(len(state["branches"]), 4)
        self.assertEqual(state["branches"][0]["stage"], TERMINAL_STAGE)

    def test_v2_pool_capacity_two_or_three_is_persistent_and_globally_selected(self) -> None:
        for capacity in (2, 3):
            with self.subTest(capacity=capacity):
                root = Path(self.temporary.name).resolve() / f"pool-{capacity}"
                batch = self.make_v2_batch(capacity=capacity, root=root)
                selections = [
                    self.pool_member(
                        f"attempt-{index}",
                        allocation="exploration" if index == capacity else "exploitation",
                        method_family=f"method-{index}",
                    )
                    for index in range(1, capacity + 1)
                ]
                selected = batch.select_controller_pool(
                    selections, now=BASE + timedelta(minutes=1)
                )
                self.assertEqual(selected["active_pool_capacity"], capacity)
                self.assertEqual(
                    selected["active_attempt_ids"],
                    [item["attempt_id"] for item in selections],
                )
                self.assertEqual(selected["pool_generation"], 1)
                with self.assertRaisesRegex(DiscoveryBatchError, "already active"):
                    batch.select_controller_pool(
                        [
                            self.pool_member("overlapping-1"),
                            self.pool_member(
                                "overlapping-2",
                                allocation="exploration",
                                method_family="tree",
                            ),
                        ],
                        now=BASE + timedelta(minutes=2),
                    )
                batch.snapshot_path.unlink()
                recovered = ContinuousDiscoveryBatch(
                    root, allow_temporary=True
                ).snapshot()
                self.assertEqual(recovered["active_pool_capacity"], capacity)
                self.assertEqual(recovered["active_attempt_ids"], selected[
                    "active_attempt_ids"
                ])
                self.assertEqual(recovered["state_sha256"], selected["state_sha256"])
                self.assertEqual(
                    selected["branches"][0]["resource_hint"]["max_attempts"], 1
                )
                self.assertIs(
                    selected["branches"][0]["resource_hint"]["authority_granted"],
                    False,
                )

                too_small_root = (
                    Path(self.temporary.name).resolve() / f"pool-small-{capacity}"
                )
                too_small = self.make_v2_batch(
                    capacity=capacity, root=too_small_root
                )
                with self.assertRaisesRegex(DiscoveryBatchError, "2 or 3"):
                    too_small.select_controller_pool(
                        [self.pool_member("only-one", allocation="exploration")],
                        now=BASE + timedelta(minutes=1),
                    )

        diversity_root = Path(self.temporary.name).resolve() / "pool-diversity"
        diversity = self.make_v2_batch(capacity=2, root=diversity_root)
        with self.assertRaisesRegex(DiscoveryBatchError, "method-family diversity"):
            diversity.select_controller_pool(
                [
                    self.pool_member("same-method-1"),
                    self.pool_member("same-method-2", allocation="exploration"),
                ],
                now=BASE + timedelta(minutes=1),
            )
        duplicate_hypothesis = self.pool_member(
            "duplicate-hypothesis-2",
            allocation="exploration",
            method_family="tree",
        )
        duplicate_hypothesis["hypothesis_digest_sha256"] = sha(
            "duplicate-hypothesis-1:hypothesis"
        )
        with self.assertRaisesRegex(DiscoveryBatchError, "already scheduled"):
            diversity.select_controller_pool(
                [
                    self.pool_member("duplicate-hypothesis-1"),
                    duplicate_hypothesis,
                ],
                now=BASE + timedelta(minutes=1),
            )
        duplicate_question = self.pool_member(
            "duplicate-question-2",
            allocation="exploration",
            method_family="tree",
        )
        duplicate_question["question_digest_sha256"] = sha(
            "duplicate-question-1:question"
        )
        with self.assertRaisesRegex(DiscoveryBatchError, "question was already"):
            diversity.select_controller_pool(
                [
                    self.pool_member("duplicate-question-1"),
                    duplicate_question,
                ],
                now=BASE + timedelta(minutes=1),
            )

    def test_v2_credit_changes_feedback_and_budget_not_score_or_incumbent(self) -> None:
        hints: dict[int, dict] = {}
        for credit in (0, 2):
            root = Path(self.temporary.name).resolve() / f"credit-{credit}"
            batch = self.make_v2_batch(capacity=3, root=root)
            batch.select_controller_pool(
                [
                    self.pool_member("attempt-01"),
                    self.pool_member(
                        "attempt-02",
                        allocation="exploration",
                        method_family="tree",
                    ),
                    self.pool_member("attempt-03", method_family="calibration"),
                ],
                now=BASE + timedelta(minutes=1),
            )
            batch.mark_implementation_ready(
                "attempt-01",
                runner_sha256=sha("attempt-01:runner"),
                spec_sha256=sha("attempt-01:spec"),
                now=BASE + timedelta(minutes=2),
            )
            batch.claim_execution(
                "attempt-01", claim_id="attempt-01-claim", now=BASE + timedelta(minutes=3)
            )
            batch.mark_execution_terminal(
                "attempt-01",
                claim_id="attempt-01-claim",
                outcome="succeeded",
                execution_receipt_sha256=sha("receipt"),
                now=BASE + timedelta(minutes=4),
            )
            reviewed = batch.record_result_review(
                "attempt-01",
                decision="REVERT",
                scorecard_sha256=sha("scorecard"),
                review_sha256=sha("review"),
                independently_reviewed=True,
                now=BASE + timedelta(minutes=5),
            )
            credited = batch.record_research_credit(
                "attempt-01",
                credit=credit,
                evidence_bundle_sha256=sha(f"credit-evidence-{credit}"),
                problem_id="incremental-information",
                question_id="question-attempt-01",
                question_digest_sha256=sha("attempt-01:question"),
                authority_snapshot_sha256=sha("authority"),
                predeclared_rule_sha256=sha("attempt-01:rule"),
                outcome="invalid" if credit == 0 else "support",
                route_action="cooldown" if credit == 0 else "continue",
                credit_review_sha256=sha("credit-review"),
                reason=f"credit {credit} is diagnostic research value only",
                now=BASE + timedelta(minutes=6),
            )
            self.assertEqual(credited["incumbent"], reviewed["incumbent"])
            self.assertEqual(
                credited["branches"][0]["scorecard_sha256"],
                reviewed["branches"][0]["scorecard_sha256"],
            )
            with self.assertRaisesRegex(DiscoveryBatchError, "already recorded"):
                batch.record_research_credit(
                    "attempt-01",
                    credit=credit,
                    evidence_bundle_sha256=sha(f"credit-evidence-{credit}"),
                    problem_id="incremental-information",
                    question_id="question-attempt-01",
                    question_digest_sha256=sha("attempt-01:question"),
                    authority_snapshot_sha256=sha("authority"),
                    predeclared_rule_sha256=sha("attempt-01:rule"),
                    outcome="invalid" if credit == 0 else "support",
                    route_action="cooldown" if credit == 0 else "continue",
                    credit_review_sha256=sha("credit-review"),
                    reason="duplicate",
                    now=BASE + timedelta(minutes=7),
                )
            final = batch.mark_controller_feedback_ready(
                "attempt-01", now=BASE + timedelta(minutes=7)
            )
            self.complete_v2(batch, "attempt-02", minute=8, credit=0)
            self.complete_v2(batch, "attempt-03", minute=9, credit=0)
            packet = final["branches"][0]["feedback_packet"]
            self.assertEqual(packet["schema"], EVIDENCE_SCHEMA_V2)
            self.assertEqual(packet["research_credit"]["value"], credit)
            self.assertNotIn("metrics", packet)
            self.assertNotIn("prediction_score", packet)
            hints[credit] = batch.pool_selection_hint()

        self.assertEqual(hints[0]["recommended_active_slots"], 2)
        self.assertEqual(hints[2]["recommended_active_slots"], 3)
        self.assertEqual(
            hints[2]["ranked_research_parents"][0]["candidate_sha256"],
            sha("attempt-01:runner"),
        )
        self.assertEqual(hints[2]["ranked_research_parents"][0]["research_credit"], 2)
        self.assertNotIn(
            sha("attempt-01:runner"),
            {
                item["candidate_sha256"]
                for item in hints[0]["ranked_research_parents"]
            },
        )

    def test_v2_credit_dedup_independent_gate_refutation_and_followup_cap(self) -> None:
        batch = self.make_v2_batch(capacity=2)
        batch.select_controller_pool(
            [
                self.pool_member("attempt-01"),
                self.pool_member(
                    "attempt-02", allocation="exploration", method_family="tree"
                ),
            ],
            now=BASE + timedelta(minutes=1),
        )
        self.complete_v2(
            batch,
            "attempt-01",
            minute=2,
            credit=2,
            outcome="refute",
            route_action="stop",
        )

        batch.mark_implementation_ready(
            "attempt-02",
            runner_sha256=sha("attempt-02:runner"),
            spec_sha256=sha("attempt-02:spec"),
            now=BASE + timedelta(minutes=3),
        )
        batch.claim_execution(
            "attempt-02", claim_id="attempt-02-claim", now=BASE + timedelta(minutes=4)
        )
        batch.mark_execution_terminal(
            "attempt-02",
            claim_id="attempt-02-claim",
            outcome="failed",
            execution_receipt_sha256=sha("attempt-02:receipt"),
            now=BASE + timedelta(minutes=5),
        )
        batch.record_result_review(
            "attempt-02",
            decision="REVERT",
            scorecard_sha256=sha("attempt-02:scorecard"),
            review_sha256=sha("attempt-02:review"),
            independently_reviewed=False,
            now=BASE + timedelta(minutes=6),
        )
        with self.assertRaisesRegex(DiscoveryBatchError, "succeeded, independent"):
            batch.record_research_credit(
                "attempt-02",
                credit=2,
                evidence_bundle_sha256=sha("attempt-01:credit-evidence"),
                problem_id="settlement-probability",
                question_id="question-attempt-02",
                question_digest_sha256=sha("attempt-02:question"),
                authority_snapshot_sha256=sha("authority-2"),
                predeclared_rule_sha256=sha("attempt-02:rule"),
                outcome="support",
                route_action="continue",
                credit_review_sha256=sha("credit-review-2"),
                reason="failed execution cannot mint positive credit",
                now=BASE + timedelta(minutes=7),
            )
        with self.assertRaisesRegex(DiscoveryBatchError, "duplicate"):
            batch.record_research_credit(
                "attempt-02",
                credit=0,
                evidence_bundle_sha256=sha("attempt-01:credit-evidence"),
                problem_id="settlement-probability",
                question_id="question-attempt-02",
                question_digest_sha256=sha("attempt-02:question"),
                authority_snapshot_sha256=sha("authority-2"),
                predeclared_rule_sha256=sha("attempt-02:rule"),
                outcome="invalid",
                route_action="cooldown",
                credit_review_sha256=sha("credit-review-2"),
                reason="same problem and evidence cannot mint again",
                now=BASE + timedelta(minutes=7),
            )
        batch.record_research_credit(
            "attempt-02",
            credit=0,
            evidence_bundle_sha256=sha("attempt-01:credit-evidence"),
            problem_id="different-problem",
            question_id="question-attempt-02",
            question_digest_sha256=sha("attempt-02:question"),
            authority_snapshot_sha256=sha("authority-2"),
            predeclared_rule_sha256=sha("attempt-02:rule"),
            outcome="invalid",
            route_action="cooldown",
            credit_review_sha256=sha("credit-review-2"),
            reason="failed or unreviewed work is credit zero",
            now=BASE + timedelta(minutes=7),
        )
        final = batch.mark_controller_feedback_ready(
            "attempt-02", now=BASE + timedelta(minutes=8)
        )
        eligible = {
            item["candidate_sha256"]
            for item in final["branches"][1]["feedback_packet"][
                "next_pool_selection_hint"
            ]["ranked_research_parents"]
        }
        self.assertNotIn(sha("attempt-01:runner"), eligible)
        self.assertNotIn(sha("attempt-02:runner"), eligible)

        with self.assertRaisesRegex(DiscoveryBatchError, "not an archived branch"):
            batch.select_controller_pool(
                [
                    self.pool_member(
                        "attempt-03", parent=sha("attempt-01:runner")
                    ),
                    self.pool_member(
                        "attempt-04",
                        allocation="exploration",
                        method_family="tree",
                    ),
                ],
                now=BASE + timedelta(minutes=9),
            )

        followup_root = Path(self.temporary.name).resolve() / "credit-one-followup"
        followup = self.make_v2_batch(capacity=2, root=followup_root)
        followup.select_controller_pool(
            [
                self.pool_member("narrowing-01"),
                self.pool_member(
                    "narrowing-control",
                    allocation="exploration",
                    method_family="tree",
                ),
            ],
            now=BASE + timedelta(minutes=1),
        )
        self.complete_v2(followup, "narrowing-01", minute=2, credit=1)
        self.complete_v2(followup, "narrowing-control", minute=3, credit=0)
        with self.assertRaisesRegex(DiscoveryBatchError, "one bounded follow-up"):
            followup.select_controller_pool(
                [
                    self.pool_member(
                        "duplicate-route-1", parent=sha("narrowing-01:runner")
                    ),
                    self.pool_member(
                        "duplicate-route-2",
                        parent=sha("narrowing-01:runner"),
                        allocation="exploration",
                        method_family="tree",
                    ),
                ],
                now=BASE + timedelta(minutes=4),
            )
        followup.select_controller_pool(
            [
                self.pool_member(
                    "narrowing-child", parent=sha("narrowing-01:runner")
                ),
                self.pool_member(
                    "orthogonal-child",
                    allocation="exploration",
                    method_family="tree",
                ),
            ],
            now=BASE + timedelta(minutes=4),
        )
        self.assertNotIn(
            sha("narrowing-01:runner"),
            {
                item["candidate_sha256"]
                for item in followup.pool_selection_hint()[
                    "ranked_research_parents"
                ]
            },
        )

    def test_v2_boundaries_and_exploration_reserve_never_grant_capability(self) -> None:
        batch = self.make_v2_batch(capacity=2, reserve=0.30)
        state = batch.snapshot()
        self.assertEqual(state["boundary_flags"], BOUNDARY_FLAGS)
        self.assertEqual(state["exploration_reserve_fraction"], 0.30)
        self.assertTrue(
            all(
                state["boundary_flags"][name] is False
                for name in (
                    "protected_dev_final_allowed", "external_acquisition_allowed",
                    "network_allowed", "paid_provider_allowed", "publication_allowed",
                    "promotion_allowed", "executes_runners", "scores_results",
                    "opens_data", "grants_authority",
                )
            )
        )
        self.assertIs(batch.pool_selection_hint()["authority_granted"], False)
        hint = batch.pool_selection_hint()
        self.assertIn("resource_ceiling_bounds", hint)
        with self.assertRaisesRegex(DiscoveryBatchError, "exploration reserve"):
            batch.select_controller_pool(
                [
                    self.pool_member("all-exploit-1"),
                    self.pool_member("all-exploit-2", method_family="tree"),
                ],
                now=BASE + timedelta(minutes=1),
            )

        adjusted = self.make_v2_batch(
            capacity=2,
            reserve=0.40,
            reserve_reason="recent valid refutations justify a larger diversity reserve",
            root=Path(self.temporary.name).resolve() / "adjusted-reserve",
        ).snapshot()
        self.assertEqual(adjusted["exploration_reserve_fraction"], 0.40)
        self.assertIn("refutations", adjusted["exploration_reserve_reason"])
        for value in (0.0, 1.0):
            with self.subTest(invalid_reserve=value), self.assertRaisesRegex(
                DiscoveryBatchError, r"\[0.20, 0.40\]"
            ):
                self.make_v2_batch(
                    capacity=2,
                    reserve=value,
                    reserve_reason="out of range",
                    root=Path(self.temporary.name).resolve() / f"reserve-{value}",
                )
        with self.assertRaisesRegex(DiscoveryBatchError, "append-only reason"):
            self.make_v2_batch(
                capacity=2,
                reserve=0.20,
                root=Path(self.temporary.name).resolve() / "reserve-no-reason",
            )
        expanded = dict(BOUNDARY_FLAGS, network_allowed=True)
        other = ContinuousDiscoveryBatch(
            Path(self.temporary.name).resolve() / "expanded-v2", allow_temporary=True
        )
        with self.assertRaisesRegex(DiscoveryBatchError, "cannot expand"):
            other.initialize(
                batch_id="expanded-v2",
                start_utc=BASE,
                deadline_utc=BASE + timedelta(hours=1),
                max_attempts=3,
                initial_incumbent={
                    "candidate_id": "baseline",
                    "candidate_sha256": sha("baseline"),
                    "scorecard_sha256": sha("scorecard"),
                    "review_sha256": ZERO_SHA256,
                },
                boundary_flags=expanded,
                active_pool_capacity=2,
            )

    def test_existing_32_record_v1_state_replays_without_v2_migration(self) -> None:
        root = Path(self.temporary.name).resolve() / "legacy-32"
        batch = self.make_batch(max_attempts=10, root=root)
        for index in range(5):
            number = index + 1
            attempt = f"attempt-{number:02d}"
            minute = index * 6 + 1
            batch.select_controller_candidate(
                attempt,
                candidate_id=f"candidate-{number:02d}",
                controller_decision_sha256=sha(f"{attempt}:controller"),
                now=BASE + timedelta(minutes=minute),
            )
            batch.mark_implementation_ready(
                attempt,
                runner_sha256=sha(f"{attempt}:runner"),
                spec_sha256=sha(f"{attempt}:spec"),
                now=BASE + timedelta(minutes=minute + 1),
            )
            batch.claim_execution(
                attempt,
                claim_id=f"{attempt}-claim",
                now=BASE + timedelta(minutes=minute + 2),
            )
            batch.mark_execution_terminal(
                attempt,
                claim_id=f"{attempt}-claim",
                outcome="succeeded",
                execution_receipt_sha256=sha(f"{attempt}:receipt"),
                now=BASE + timedelta(minutes=minute + 3),
            )
            batch.record_result_review(
                attempt,
                decision="REVERT",
                scorecard_sha256=sha(f"{attempt}:scorecard"),
                review_sha256=sha(f"{attempt}:review"),
                independently_reviewed=True,
                now=BASE + timedelta(minutes=minute + 4),
            )
            batch.mark_controller_feedback_ready(
                attempt, now=BASE + timedelta(minutes=minute + 5)
            )
        batch.select_controller_candidate(
            "attempt-06",
            candidate_id="candidate-06",
            controller_decision_sha256=sha("attempt-06:controller"),
            now=BASE + timedelta(minutes=31),
        )
        before = batch.snapshot()
        self.assertEqual(before["journal_length"], 32)
        self.assertNotIn("scheduling_version", before)
        self.assertNotIn("active_attempt_ids", before)
        batch.snapshot_path.unlink()
        after = ContinuousDiscoveryBatch(root, allow_temporary=True).snapshot()
        self.assertEqual(after, before)

    def test_legacy_five_event_journal_replays_without_state_migration(self) -> None:
        legacy_root = Path(self.temporary.name).resolve() / "legacy-five"
        legacy_root.mkdir(mode=0o700)
        journal = legacy_root / "journal"
        journal.mkdir(mode=0o700)
        incumbent = {
            "candidate_id": "market-baseline",
            "candidate_sha256": sha("market-baseline"),
            "scorecard_sha256": sha("baseline-scorecard"),
            "review_sha256": ZERO_SHA256,
        }
        payloads = [
            (
                "initialize",
                {
                    "batch_id": "legacy-live-shape",
                    "start_utc": "2026-09-29T18:03:21Z",
                    "deadline_utc": "2026-09-29T20:03:21Z",
                    "max_attempts": 10,
                    "boundary_flags": dict(BOUNDARY_FLAGS),
                    "initial_incumbent": incumbent,
                },
            ),
            (
                "controller_selected",
                {
                    "attempt_id": "attempt-01",
                    "candidate_id": "candidate-01",
                    "controller_decision_sha256": sha("controller"),
                    "parent_incumbent_sha256": incumbent["candidate_sha256"],
                    "selected_at_utc": "2026-09-29T18:04:21Z",
                },
            ),
            (
                "implementation_ready",
                {
                    "attempt_id": "attempt-01",
                    "runner_sha256": sha("runner"),
                    "spec_sha256": sha("spec"),
                },
            ),
            (
                "execution_claimed",
                {
                    "attempt_id": "attempt-01",
                    "claim_id": "claim-01",
                    "attempt_number": 1,
                    "claimed_at_utc": "2026-09-29T18:05:21Z",
                    "runner_sha256": sha("runner"),
                    "spec_sha256": sha("spec"),
                },
            ),
            (
                "execution_terminal",
                {
                    "attempt_id": "attempt-01",
                    "claim_id": "claim-01",
                    "outcome": "succeeded",
                    "execution_receipt_sha256": sha("receipt"),
                    "terminal_at_utc": "2026-09-29T18:06:21Z",
                },
            ),
        ]
        previous = ZERO_SHA256
        for sequence, (event, payload) in enumerate(payloads, 1):
            body = {
                "schema": discovery_module.EVENT_SCHEMA,
                "sequence": sequence,
                "event": event,
                "payload": payload,
                "previous_sha256": previous,
            }
            event_sha = hashlib.sha256(
                json.dumps(
                    body,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=True,
                    allow_nan=False,
                ).encode("utf-8")
            ).hexdigest()
            record = dict(body, event_sha256=event_sha)
            destination = journal / f"{sequence:08d}.json"
            destination.write_text(
                json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            os.chmod(destination, 0o600)
            previous = event_sha

        legacy = ContinuousDiscoveryBatch(
            legacy_root,
            allow_temporary=True,
            test_clock=lambda: BASE,
            allow_test_clock=True,
        )
        state = legacy.snapshot()
        self.assertEqual(state["journal_length"], 5)
        self.assertEqual(state["journal_head_sha256"], previous)
        self.assertEqual(state["attempts_claimed"], 1)
        self.assertEqual(state["branches"][0]["stage"], "execution_terminal")
        self.assertEqual(state["branches"][0]["execution_outcome"], "succeeded")


class LearningCheckpointRecorderTests(unittest.TestCase):
    """Prospective lifecycle and matched restart fixtures; no experiment execution."""

    def setUp(self):
        from supervisor_harness.test_learning_checkpoint_assessment import checkpoint
        self.checkpoint = checkpoint
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve() / "v4"
        self.helpers = ContinuousDiscoveryBatchTests()

    def make(self, *, root=None, archived=None, maximum=6, capacity=2):
        batch = ContinuousDiscoveryBatch(root or self.root, allow_temporary=True,
                                         test_clock=lambda: BASE, allow_test_clock=True)
        batch.initialize(batch_id="prospective-learning-v4", start_utc=BASE,
                         deadline_utc=BASE + timedelta(hours=1), max_attempts=maximum,
                         initial_incumbent={"candidate_id": "market", "candidate_sha256": sha("market-baseline"),
                                            "scorecard_sha256": sha("market-card"), "review_sha256": ZERO_SHA256},
                         active_pool_capacity=capacity, learning_checkpoint_version=1,
                         initial_archived_parents=archived)
        return batch

    def pool(self, batch, one, two, *, parent=None, minute=1):
        return batch.select_controller_pool([
            self.helpers.pool_member(one, parent=parent),
            self.helpers.pool_member(two, allocation="exploration", method_family="tree")],
            now=BASE + timedelta(minutes=minute))

    def reviewed(self, batch, label, minute, *, outcome="succeeded", independent=True, validity=None):
        batch.mark_implementation_ready(label, runner_sha256=sha(label + ":runner"), spec_sha256=sha(label + ":spec"), now=BASE + timedelta(minutes=minute))
        batch.claim_execution(label, claim_id=label + "-claim", now=BASE + timedelta(minutes=minute, seconds=1))
        batch.mark_execution_terminal(label, claim_id=label + "-claim", outcome=outcome,
                                      execution_receipt_sha256=sha(label + ":execution"), now=BASE + timedelta(minutes=minute, seconds=2))
        return batch.record_result_review(label, decision="REVERT", scorecard_sha256=sha(label + ":card"),
                                          review_sha256=sha(label + ":review"), independently_reviewed=independent,
                                          performance_validity=validity or self.checkpoint(label, status="valid" if outcome == "succeeded" else "invalid")["validity"],
                                          now=BASE + timedelta(minutes=minute, seconds=3))

    def finish(self, batch, label, minute, *, assessment=None, outcome="succeeded"):
        self.reviewed(batch, label, minute, outcome=outcome, validity=(assessment or self.checkpoint(label))["validity"])
        batch.record_learning_checkpoint(label, assessment or self.checkpoint(label), now=BASE + timedelta(minutes=minute, seconds=4))
        return batch.mark_controller_feedback_ready(label, now=BASE + timedelta(minutes=minute, seconds=5))

    def archive(self, source, label, consumed=0):
        branch = next(b for b in source["branches"] if b["attempt_id"] == label)
        return {"candidate_id": branch["candidate_id"], "candidate_sha256": branch["runner_sha256"],
                "source_batch_id": source["batch_id"], "source_attempt_id": label,
                "archive_manifest_sha256": sha(label + ":archive"), "independent_review_sha256": branch["review_sha256"],
                "authority_snapshot_sha256": sha(label + ":authority"), "problem_id": "synthetic-question",
                "question_digest_sha256": branch["question_digest_sha256"], "evidence_bundle_sha256": sha(label + ":evidence"),
                "research_credit": branch["research_credit"], "research_outcome": branch["research_outcome"],
                "route_action": branch["route_action"], "authority_granted": False,
                "learning_checkpoint": branch["learning_checkpoint"], "consumed_followups": consumed,
                "consumption_receipt_sha256": sha(label + ":consumption"),
                "consumed_question_sha256s": [sha(label + ":next-question")] if consumed else []}

    def test_valid_zero_revert_feedback_pool_lineage_consumption_and_restart(self):
        batch = self.make()
        self.pool(batch, "one", "two")
        self.finish(batch, "one", 2)
        state = self.finish(batch, "two", 3, assessment=self.checkpoint("two", action="stop"))
        packet = state["branches"][0]["feedback_packet"]
        self.assertEqual(packet["schema"], discovery_module.EVIDENCE_SCHEMA_V4)
        self.assertEqual(packet["protocol_version"], 4)
        self.assertEqual(packet["learning_checkpoint"]["prediction_decision"], "REVERT")
        self.assertEqual(state["incumbent"]["candidate_sha256"], sha("market-baseline"))
        member = self.helpers.pool_member("three", parent=sha("one:runner"))
        member["question_digest_sha256"] = sha("one:next-question")
        selection = batch.select_controller_pool([member, self.helpers.pool_member("four", allocation="exploration", method_family="tree")], now=BASE + timedelta(minutes=4))
        self.assertEqual(selection["bounded_followups_consumed"][sha("one:allowance")], 1)
        self.assertEqual(selection["branches"][2]["research_parent_sha256"], sha("one:runner"))
        self.assertEqual(selection["branches"][2]["comparison_incumbent_sha256"], sha("market-baseline"))
        batch.snapshot_path.unlink()
        self.assertEqual(ContinuousDiscoveryBatch(self.root, allow_temporary=True).snapshot(), selection)
        self.finish(batch, "three", 5, assessment=self.checkpoint("three", status="invalid", action="stop"), outcome="failed")
        self.finish(batch, "four", 6, assessment=self.checkpoint("four", action="stop"))
        self.assertNotIn(sha("one:runner"), [p["candidate_sha256"] for p in batch.pool_selection_hint()["ranked_research_parents"]])

    def test_checkpoint_dedup_idempotence_reuse_feedback_and_credit_do_not_promote(self):
        batch = self.make()
        self.pool(batch, "one", "two")
        first = self.checkpoint("one", credit=2, action="branch")
        self.finish(batch, "one", 2, assessment=first)
        second = self.checkpoint("two", credit=2)
        second["learning"]["finding_sha256"] = sha("one:finding")
        second["reuse"] = {"finding_sha256": sha("one:finding"), "status": "observed", "action_sha256": sha("reuse-action"),
                          "evidence_sha256": sha("actual-reuse"), "review_sha256": sha("reuse-review"),
                          "benefit": "unmeasured", "benefit_evidence_sha256": None}
        self.reviewed(batch, "two", 3)
        saved = batch.record_learning_checkpoint("two", second, now=BASE + timedelta(minutes=3, seconds=4))
        self.assertEqual(saved["branches"][1]["research_credit"], 0)
        self.assertEqual(batch.record_learning_checkpoint("two", second, now=BASE + timedelta(minutes=3, seconds=4)), saved)
        modified = json.loads(json.dumps(second))
        modified["learning"]["reason"] = "different"
        with self.assertRaises(DiscoveryBatchError):
            batch.record_learning_checkpoint("two", modified, now=BASE + timedelta(minutes=3, seconds=4))
        final = batch.mark_controller_feedback_ready("two", now=BASE + timedelta(minutes=3, seconds=5))
        self.assertEqual(final["accepted_finding_sha256s"], [sha("one:finding")])
        self.assertEqual(final["branches"][1]["feedback_packet"]["learning_checkpoint"]["reuse"]["benefit"], "unmeasured")
        self.assertEqual(final["incumbent"]["candidate_sha256"], sha("market-baseline"))
        self.assertGreaterEqual(batch.pool_selection_hint()["ranked_research_parents"][0]["research_credit"], 2)

    def test_verified_failure_repair_learning_is_not_forecast_parent(self):
        batch = self.make()
        self.pool(batch, "one", "two")
        state = self.finish(batch, "one", 2, outcome="failed", assessment=self.checkpoint("one", credit=2, status="invalid", kind="failure_repair"))
        self.assertEqual(state["branches"][0]["research_credit"], 2)
        self.assertEqual(state["failed_attempts"], 1)
        self.assertNotIn(sha("one:runner"), [p["candidate_sha256"] for p in batch.pool_selection_hint()["ranked_research_parents"]])

    def test_archive_zero_credit_and_consumed_legacy_allowance_cannot_reset(self):
        batch = self.make()
        self.pool(batch, "one", "two")
        self.finish(batch, "one", 2)
        state = self.finish(batch, "two", 3, assessment=self.checkpoint("two", action="stop"))
        archived = self.archive(state, "one")
        fresh = self.make(root=Path(self.temporary.name).resolve() / "archive-open", archived=[archived])
        self.assertIn(sha("one:runner"), [p["candidate_sha256"] for p in fresh.pool_selection_hint()["ranked_research_parents"]])
        consumed = self.make(root=Path(self.temporary.name).resolve() / "archive-consumed", archived=[self.archive(state, "one", 1)])
        self.assertNotIn(sha("one:runner"), [p["candidate_sha256"] for p in consumed.pool_selection_hint()["ranked_research_parents"]])
        member = self.helpers.pool_member("child", parent=sha("one:runner"))
        member["question_digest_sha256"] = sha("one:next-question")
        with self.assertRaises(DiscoveryBatchError):
            consumed.select_controller_pool([member, self.helpers.pool_member("control", allocation="exploration", method_family="tree")], now=BASE + timedelta(minutes=1))
        malformed = dict(archived)
        malformed.pop("consumption_receipt_sha256")
        with self.assertRaises(DiscoveryBatchError):
            self.make(root=Path(self.temporary.name).resolve() / "archive-no-receipt", archived=[malformed])

    def test_specific_followup_pool_bounds_and_no_legacy_path_in_v4(self):
        batch = self.make(maximum=2)
        self.pool(batch, "one", "two")
        self.reviewed(batch, "one", 2)
        with self.assertRaises(DiscoveryBatchError):
            batch.mark_controller_feedback_ready("one", now=BASE + timedelta(minutes=2, seconds=4))
        state = batch.record_learning_checkpoint("one", self.checkpoint("one"), now=BASE + timedelta(minutes=2, seconds=4))
        self.assertEqual(state["attempts_claimed"], 1)
        batch.mark_controller_feedback_ready("one", now=BASE + timedelta(minutes=2, seconds=5))
        self.finish(batch, "two", 3, assessment=self.checkpoint("two", action="stop"))
        with self.assertRaises(BatchStoppedError):
            self.pool(batch, "three", "four", minute=4)
        self.assertEqual(batch.snapshot()["attempts_claimed"], 2)

    def test_leaking_keep_rejects_before_incumbent_and_checkpoint_cannot_reclassify(self):
        batch = self.make()
        self.pool(batch, "one", "two")
        self.reviewed(batch, "one", 2)
        before = batch.snapshot()
        reclassified = self.checkpoint("one")
        reclassified["validity"]["reason"] = "Rewritten original independent classification."
        with self.assertRaisesRegex(DiscoveryBatchError, "original independent"):
            batch.record_learning_checkpoint("one", reclassified, now=BASE + timedelta(minutes=2, seconds=4))
        self.assertEqual(batch.snapshot(), before)
        batch.record_learning_checkpoint("one", self.checkpoint("one"), now=BASE + timedelta(minutes=2, seconds=4))
        batch.mark_controller_feedback_ready("one", now=BASE + timedelta(minutes=2, seconds=5))
        batch.mark_implementation_ready("two", runner_sha256=sha("two:runner"), spec_sha256=sha("two:spec"), now=BASE + timedelta(minutes=3))
        batch.claim_execution("two", claim_id="two-claim", now=BASE + timedelta(minutes=3, seconds=1))
        batch.mark_execution_terminal("two", claim_id="two-claim", outcome="succeeded", execution_receipt_sha256=sha("two:execution"), now=BASE + timedelta(minutes=3, seconds=2))
        before = batch.snapshot()
        leaked = self.checkpoint("two")["validity"]
        leaked["leakage_detected"] = True
        with self.assertRaisesRegex(DiscoveryBatchError, "nonleaking"):
            batch.record_result_review("two", decision="KEEP", scorecard_sha256=sha("two:card"), review_sha256=sha("two:review"),
                                       independently_reviewed=True, performance_validity=leaked, now=BASE + timedelta(minutes=3, seconds=3))
        self.assertEqual(batch.snapshot(), before)
        self.assertEqual(batch.snapshot()["incumbent"]["candidate_sha256"], sha("market-baseline"))

    def test_alias_allowance_and_wrong_question_are_rejected_without_writes(self):
        batch = self.make()
        self.pool(batch, "one", "two")
        self.finish(batch, "one", 2)
        aliased = self.checkpoint("two")
        aliased["exploration"]["allowance_id_sha256"] = sha("one:allowance")
        state = self.finish(batch, "two", 3, assessment=aliased)
        one = self.helpers.pool_member("child-one", parent=sha("one:runner"))
        one["question_digest_sha256"] = sha("one:next-question")
        two = self.helpers.pool_member("child-two", parent=sha("two:runner"), allocation="exploration", method_family="tree")
        two["question_digest_sha256"] = sha("two:next-question")
        before = batch.snapshot()
        with self.assertRaisesRegex(DiscoveryBatchError, "aliased bounded"):
            batch.select_controller_pool([one, two], now=BASE + timedelta(minutes=4))
        self.assertEqual(batch.snapshot(), before)
        one["question_digest_sha256"] = sha("unreviewed-question")
        with self.assertRaisesRegex(DiscoveryBatchError, "reviewed question"):
            batch.select_controller_pool([one, self.helpers.pool_member("control", allocation="exploration", method_family="tree")], now=BASE + timedelta(minutes=4))
        self.assertEqual(batch.snapshot(), before)
        archived_one = self.archive(state, "one", 1)
        archived_two = self.archive(state, "two", 0)
        restored = self.make(root=Path(self.temporary.name).resolve() / "aliased-archive", archived=[archived_one, archived_two])
        self.assertEqual(len(restored.pool_selection_hint()["ranked_research_parents"]), 1)

    def test_credit_influences_budget_hint_not_mandatory_active_membership(self):
        batch = self.make(capacity=3, maximum=9)
        selected = batch.select_controller_pool([
            self.helpers.pool_member("one"), self.helpers.pool_member("two", method_family="tree"),
            self.helpers.pool_member("three", allocation="exploration", method_family="calibration")], now=BASE + timedelta(minutes=1))
        self.assertEqual(len(selected["active_attempt_ids"]), 3)
        self.finish(batch, "one", 2, assessment=self.checkpoint("one", credit=1, action="continue"))
        self.finish(batch, "two", 3, assessment=self.checkpoint("two", action="stop"))
        self.finish(batch, "three", 4, assessment=self.checkpoint("three", action="stop"))
        hint = batch.pool_selection_hint()
        self.assertEqual(hint["recommended_active_slots"], 2)
        self.assertEqual(hint["ranked_research_parents"][0]["research_credit"], 1)
        # Eligibility does not force inclusion: choose two distinct baseline questions.
        selection = self.pool(batch, "four", "five", minute=5)
        self.assertTrue(all(b["research_parent_sha256"] == sha("market-baseline") for b in selection["branches"][-2:]))
        self.finish(batch, "four", 6, assessment=self.checkpoint("four", credit=2, action="branch"))
        final = self.finish(batch, "five", 7, assessment=self.checkpoint("five", action="stop"))
        self.assertEqual(batch.pool_selection_hint()["recommended_active_slots"], 3)
        self.assertEqual(final["incumbent"]["candidate_sha256"], sha("market-baseline"))

    def test_feedback_seal_replay_and_prospective_assessment_do_not_enter_legacy(self):
        batch = self.make()
        self.pool(batch, "one", "two")
        self.finish(batch, "one", 2)
        with batch._locked():
            records = batch._read_records()
        altered = json.loads(json.dumps(records))
        altered[-1]["payload"]["packet"]["learning_checkpoint"]["learning"]["credit"] = 2
        with self.assertRaisesRegex(DiscoveryBatchError, "packet changed"):
            batch._replay(altered)
        legacy_root = Path(self.temporary.name).resolve() / "legacy"
        helper = ContinuousDiscoveryBatchTests()
        helper.root = legacy_root
        legacy = helper.make_v2_batch()
        before = legacy.snapshot()
        self.assertNotIn("learning_checkpoint_version", before)
        with self.assertRaisesRegex(DiscoveryBatchError, "explicit v4"):
            legacy.record_learning_checkpoint("one", self.checkpoint("one"), now=BASE)
        self.assertEqual(legacy.snapshot(), before)

    def test_pending_bounded_question_is_chosen_by_controller_after_feedback(self):
        batch = self.make(maximum=4)
        self.pool(batch, "one", "two")
        pending = self.checkpoint("one")
        pending["exploration"]["next_question_sha256"] = None
        self.finish(batch, "one", 2, assessment=pending)
        state = self.finish(batch, "two", 3, assessment=self.checkpoint("two", action="stop"))
        packet = state["branches"][0]["feedback_packet"]
        self.assertIsNone(packet["learning_checkpoint"]["exploration"]["next_question_sha256"])
        child = self.helpers.pool_member("controller-chosen-child", parent=sha("one:runner"))
        control = self.helpers.pool_member("control", allocation="exploration", method_family="tree")
        repeated = dict(child, question_digest_sha256=sha("one:question"))
        before = batch.snapshot()
        with self.assertRaisesRegex(DiscoveryBatchError, "question was already"):
            batch.select_controller_pool([repeated, control], now=BASE + timedelta(minutes=4))
        self.assertEqual(batch.snapshot(), before)
        selected = batch.select_controller_pool([child, control], now=BASE + timedelta(minutes=4))
        saved = selected["branches"][2]
        self.assertEqual(saved["controller_decision_sha256"], child["controller_decision_sha256"])
        self.assertEqual(saved["question_digest_sha256"], child["question_digest_sha256"])
        self.assertEqual(saved["predeclared_rule_sha256"], child["predeclared_rule_sha256"])
        self.assertEqual(selected["bounded_followups_consumed"][sha("one:allowance")], 1)
        self.finish(batch, "controller-chosen-child", 5, assessment=self.checkpoint("controller-chosen-child", action="stop"))
        self.finish(batch, "control", 6, assessment=self.checkpoint("control", action="stop"))
        with self.assertRaises(BatchStoppedError):
            self.pool(batch, "over-cap-one", "over-cap-two", minute=7)


if __name__ == "__main__":
    unittest.main()
