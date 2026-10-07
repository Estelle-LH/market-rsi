"""Opt-in small changes must not reinterpret legacy discovery histories."""
from datetime import timedelta
import unittest
from unittest.mock import patch

from supervisor_harness.continuous_discovery_batch import (
    ContinuousDiscoveryBatch, DiscoveryBatchError, FINAL_SINGLETON_POLICY,
)
from supervisor_harness import test_continuous_discovery_batch as fixtures
from data_scientist_harness import test_micro_evolution as micro_fixtures
from data_scientist_harness.co_evolution_loop import micro_pair_hash

BASE, sha = fixtures.BASE, fixtures.sha


class SmallStepSchedulingTests(unittest.TestCase):
    def setUp(self):
        self.helper = fixtures.ContinuousDiscoveryBatchTests()
        self.helper.setUp()
        self.addCleanup(self.helper.doCleanups)

    def batch(self, attempts=3, **extra):
        policy = extra.pop("scheduling_policy", FINAL_SINGLETON_POLICY)
        value = ContinuousDiscoveryBatch(
            self.helper.root, allow_temporary=True,
            test_clock=lambda: BASE, allow_test_clock=True,
        )
        value.initialize(
            batch_id="small-step", start_utc=BASE,
            deadline_utc=BASE + timedelta(hours=2), max_attempts=attempts,
            initial_incumbent={"candidate_id": "market-baseline",
                "candidate_sha256": sha("market-baseline"),
                "scorecard_sha256": sha("baseline-scorecard"),
                "review_sha256": "0" * 64},
            active_pool_capacity=2, scheduling_policy=policy,
            **extra,
        )
        return value

    def finish(self, batch, attempt, minute, **extra):
        return self.helper.complete_v2(batch, attempt, minute=minute, credit=2, **extra)

    def test_three_attempts_finish_two_then_one_and_restart(self):
        batch = self.batch()
        h = self.helper
        batch.select_controller_pool([
            h.pool_member("a"), h.pool_member("b", allocation="exploration", method_family="tree")
        ], now=BASE + timedelta(minutes=1))
        self.finish(batch, "a", 2)
        self.finish(batch, "b", 3)
        old = batch.snapshot()
        restarted = ContinuousDiscoveryBatch(self.helper.root, allow_temporary=True)
        self.assertEqual(restarted.snapshot(), old)
        self.assertEqual(restarted.pool_selection_hint()["recommended_active_slots"], 1)
        batch.select_controller_pool([h.pool_member("c")], now=BASE + timedelta(minutes=4))
        final = self.finish(batch, "c", 5)
        self.assertEqual(final["attempts_claimed"], 3)
        self.assertEqual(final["active_attempt_ids"], [])
        self.assertEqual(final["stopped_reason"], "max_attempts_reached")
        self.assertEqual(restarted.snapshot(), final)
        replay = batch.claim_execution("c", claim_id="c-claim", now=BASE + timedelta(minutes=6))
        self.assertEqual(replay["attempts_claimed"], 3)
        with self.assertRaises(DiscoveryBatchError):
            batch.select_controller_pool([h.pool_member("d")], now=BASE + timedelta(minutes=7))

    def test_five_attempts_finish_two_two_one(self):
        batch = self.batch(5)
        h = self.helper
        for generation, names in enumerate((("a", "b"), ("c", "d"), ("e",))):
            minute = generation * 4 + 1
            members = [h.pool_member(name, allocation="exploration" if index == len(names)-1 else "exploitation",
                method_family=f"family-{index}") for index, name in enumerate(names)]
            batch.select_controller_pool(members, now=BASE + timedelta(minutes=minute))
            for index, name in enumerate(names):
                self.finish(batch, name, minute + index + 1)
        final = batch.snapshot()
        self.assertEqual(final["attempts_claimed"], 5)
        self.assertEqual(final["stopped_reason"], "max_attempts_reached")

    def test_singleton_only_at_last_slot_and_errors_do_not_claim(self):
        batch = self.batch()
        before = batch.snapshot()
        for selections in ([], [self.helper.pool_member("a")],
                           [self.helper.pool_member(f"x{i}") for i in range(3)]):
            with self.assertRaises(DiscoveryBatchError):
                batch.select_controller_pool(selections, now=BASE + timedelta(minutes=1))
            self.assertEqual(batch.snapshot(), before)

    def test_failed_final_attempt_is_preserved_without_retry(self):
        batch = self.batch(1)
        batch.select_controller_pool([self.helper.pool_member("bad", allocation="exploration")],
            now=BASE + timedelta(minutes=1))
        state = self.helper.complete_v2(batch, "bad", minute=2,
            execution_outcome="failed", credit=0)
        self.assertEqual(state["failed_attempts"], 1)
        self.assertEqual(state["attempts_claimed"], 1)
        self.assertEqual(state["branches"][0]["stage"], "controller_feedback_ready")
        self.assertEqual(state["stopped_reason"], "max_attempts_reached")

    def test_expired_singleton_stays_blocked(self):
        batch = self.batch(1)
        with self.assertRaises(DiscoveryBatchError):
            batch.select_controller_pool([self.helper.pool_member("a", allocation="exploration")],
                now=BASE + timedelta(hours=3))
        self.assertEqual(batch.snapshot()["attempts_claimed"], 0)

    def test_legacy_v2_replays_unchanged_at_stranded_last_attempt(self):
        batch = self.helper.make_v2_batch(max_attempts=3)
        batch.select_controller_pool([self.helper.pool_member("a"), self.helper.pool_member(
            "b", allocation="exploration", method_family="tree")], now=BASE + timedelta(minutes=1))
        self.finish(batch, "a", 2)
        self.finish(batch, "b", 3)
        old = batch.snapshot()
        self.assertNotIn("scheduling_policy", old)
        self.assertEqual(batch.pool_selection_hint()["recommended_active_slots"], 0)
        batch.snapshot_path.unlink()
        self.assertEqual(ContinuousDiscoveryBatch(self.helper.root, allow_temporary=True).snapshot(), old)

    def test_unknown_policy_cannot_initialize(self):
        with self.assertRaisesRegex(DiscoveryBatchError, "known scheduling policy"):
            self.batch(scheduling_policy="unknown")

    def configure(self, batch):
        return batch.record_micro_evolution("initialize", micro_fixtures.config(),
            expected_state_sha256=batch.snapshot()["state_sha256"],
            now=BASE + timedelta(seconds=1))

    def evolve(self, batch, action, arguments, seconds):
        return batch.record_micro_evolution(action, arguments,
            expected_state_sha256=batch.snapshot()["state_sha256"],
            now=BASE + timedelta(seconds=seconds))

    def test_controls_replay_and_parent_research_continues_while_pending(self):
        batch = self.batch(1)
        configured = self.configure(batch)
        pair = micro_pair_hash(configured["micro_evolution"])
        pending = self.evolve(batch, "propose", micro_fixtures.proposal(
            configured["micro_evolution"]), 2)
        batch.select_controller_pool([self.helper.pool_member("a", allocation="exploration")],
            now=BASE + timedelta(minutes=1))
        batch.mark_implementation_ready("a", runner_sha256=sha("runner"), spec_sha256=sha("spec"),
            now=BASE + timedelta(minutes=2))
        before = batch.snapshot()
        for kwargs in ({}, {"runtime_pair_sha256": "9" * 64, "memory_snapshot_sha256": sha("memory")}):
            with self.assertRaises(DiscoveryBatchError):
                batch.claim_execution("a", claim_id="claim-a", now=BASE + timedelta(minutes=3), **kwargs)
            self.assertEqual(batch.snapshot(), before)
        claimed = batch.claim_execution("a", claim_id="claim-a", runtime_pair_sha256=pair,
            memory_snapshot_sha256=sha("memory"), now=BASE + timedelta(minutes=3))
        self.assertEqual(claimed["attempts_claimed"], 1)
        self.assertEqual(claimed["branches"][0]["runtime_pair_sha256"], pair)
        with self.assertRaisesRegex(DiscoveryBatchError, "idle batch"):
            self.evolve(batch, "review", micro_fixtures.review(pending["micro_evolution"]), 181)
        with self.assertRaisesRegex(DiscoveryBatchError, "memory snapshot changed"):
            batch.claim_execution("a", claim_id="claim-a", runtime_pair_sha256=pair,
                memory_snapshot_sha256=sha("different-memory"), now=BASE + timedelta(minutes=4))
        rejected = self.evolve(batch, "review", micro_fixtures.review(
            pending["micro_evolution"], "reject"), 182)
        self.assertEqual(micro_pair_hash(rejected["micro_evolution"]), pair)
        self.assertEqual(rejected["attempts_claimed"], 1)
        batch.snapshot_path.unlink()
        self.assertEqual(ContinuousDiscoveryBatch(self.helper.root, allow_temporary=True).snapshot(), rejected)

    def test_acceptance_and_rollback_are_durable_without_erasing_history(self):
        batch = self.batch()
        configured = self.configure(batch)
        original = configured["micro_evolution"]["active_pair"]
        pending = self.evolve(batch, "propose", micro_fixtures.proposal(
            configured["micro_evolution"]), 2)
        accepted = self.evolve(batch, "review", micro_fixtures.review(pending["micro_evolution"]), 3)
        self.assertNotEqual(accepted["micro_evolution"]["active_pair"], original)
        self.assertEqual(accepted["boundary_flags"], configured["boundary_flags"])
        rolled = self.evolve(batch, "rollback", {"reviewer_id": "trusted-supervisor",
            "reason": "Synthetic downstream regression", "evidence_sha256": "3" * 64}, 4)
        self.assertEqual(rolled["micro_evolution"]["active_pair"], original)
        self.assertEqual(len(rolled["micro_evolution"]["history"]), 2)
        self.assertEqual(rolled["attempts_claimed"], 0)
        self.assertEqual(ContinuousDiscoveryBatch(self.helper.root, allow_temporary=True).snapshot(), rolled)

    def test_evolution_stale_updates_and_invalid_receipts_do_not_poison_journal(self):
        batch = self.batch()
        configured = self.configure(batch)
        pending = self.evolve(batch, "propose", micro_fixtures.proposal(configured["micro_evolution"]), 2)
        with self.assertRaisesRegex(DiscoveryBatchError, "stale batch"):
            batch.record_micro_evolution("review", micro_fixtures.review(pending["micro_evolution"]),
                expected_state_sha256=configured["state_sha256"], now=BASE + timedelta(seconds=3))
        bad = micro_fixtures.review(pending["micro_evolution"])
        bad["checks"]["bounded_trial"]["passed"] = False
        with self.assertRaisesRegex(DiscoveryBatchError, "check failed"):
            self.evolve(batch, "review", bad, 3)
        self.assertEqual(batch.snapshot(), pending)
        with self.assertRaises(DiscoveryBatchError):
            self.evolve(batch, "initialize", micro_fixtures.config(), 3)
        self.assertEqual(batch.snapshot(), pending)

    def test_controls_are_opt_in_not_an_extra_legacy_gate(self):
        batch = self.helper.make_v2_batch()
        before = batch.snapshot()
        with self.assertRaisesRegex(DiscoveryBatchError, "fresh v3"):
            self.configure(batch)
        self.assertEqual(batch.snapshot(), before)
        self.assertNotIn("micro_evolution", before)

    def test_duplicate_singleton_selection_is_idempotent_not_a_new_attempt(self):
        batch = self.batch(1)
        selection = [self.helper.pool_member("a", allocation="exploration")]
        first = batch.select_controller_pool(selection, now=BASE + timedelta(minutes=1))
        second = batch.select_controller_pool(selection, now=BASE + timedelta(minutes=2))
        self.assertEqual(first, second)
        changed = [dict(selection[0], candidate_id="other")]
        with self.assertRaisesRegex(DiscoveryBatchError, "reused"):
            batch.select_controller_pool(changed, now=BASE + timedelta(minutes=2))

    def test_full_pair_change_between_generations_and_rollback_keeps_attempts(self):
        batch = self.batch()
        configured = self.configure(batch)
        original_pair = micro_pair_hash(configured["micro_evolution"])
        h = self.helper
        batch.select_controller_pool([h.pool_member("a"), h.pool_member(
            "b", allocation="exploration", method_family="tree")], now=BASE + timedelta(minutes=1))

        def finish_bound(attempt, minute, pair):
            original_claim = batch.claim_execution
            def bound(*args, **kwargs):
                return original_claim(*args, **kwargs, runtime_pair_sha256=pair,
                                      memory_snapshot_sha256=sha(f"memory-{attempt}"))
            with patch.object(batch, "claim_execution", side_effect=bound):
                return h.complete_v2(batch, attempt, minute=minute, credit=2)

        finish_bound("a", 2, original_pair)
        finish_bound("b", 3, original_pair)
        pending = self.evolve(batch, "propose", micro_fixtures.proposal(
            batch.snapshot()["micro_evolution"]), 241)
        accepted = self.evolve(batch, "review", micro_fixtures.review(pending["micro_evolution"]), 242)
        new_pair = micro_pair_hash(accepted["micro_evolution"])
        batch.select_controller_pool([h.pool_member("c")], now=BASE + timedelta(minutes=5))
        finished = finish_bound("c", 6, new_pair)
        self.assertEqual(finished["attempts_claimed"], 3)
        self.assertEqual(finished["branches"][2]["feedback_packet"]["research_system"], {
            "runtime_pair_sha256": new_pair, "memory_snapshot_sha256": sha("memory-c")})
        rolled = self.evolve(batch, "rollback", {"reviewer_id": "trusted-supervisor",
            "reason": "Revert operational candidate", "evidence_sha256": "3" * 64}, 421)
        self.assertEqual(micro_pair_hash(rolled["micro_evolution"]), original_pair)
        self.assertEqual(rolled["attempts_claimed"], 3)
        self.assertEqual(rolled["branches"], finished["branches"])
        self.assertEqual(rolled["stopped_reason"], "max_attempts_reached")
        batch.snapshot_path.unlink()
        self.assertEqual(ContinuousDiscoveryBatch(self.helper.root, allow_temporary=True).snapshot(), rolled)


if __name__ == "__main__":
    unittest.main()
