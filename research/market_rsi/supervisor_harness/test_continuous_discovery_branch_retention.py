"""Explicit v3 REVERT research branches never alter prediction decisions."""
from datetime import timedelta
import unittest
from supervisor_harness.continuous_discovery_batch import ContinuousDiscoveryBatch, DiscoveryBatchError
from supervisor_harness import test_continuous_discovery_batch as fixtures


class BranchRetentionTests(unittest.TestCase):
    def setUp(self):
        self.h = fixtures.ContinuousDiscoveryBatchTests(); self.h.setUp()
        self.addCleanup(self.h.doCleanups)

    def batch(self):
        batch = ContinuousDiscoveryBatch(self.h.root, allow_temporary=True,
            test_clock=lambda: fixtures.BASE, allow_test_clock=True)
        batch.initialize(batch_id="retention-v3", start_utc=fixtures.BASE,
            deadline_utc=fixtures.BASE + timedelta(hours=2), max_attempts=3,
            initial_incumbent={"candidate_id":"market-baseline",
                "candidate_sha256":fixtures.sha("market-baseline"),
                "scorecard_sha256":fixtures.sha("baseline-scorecard"),"review_sha256":"0"*64},
            active_pool_capacity=2, scheduling_policy="final-singleton-v1")
        return batch

    def select(self, batch):
        batch.select_controller_pool([self.h.pool_member("a"), self.h.pool_member(
            "b", allocation="exploration", method_family="other")],
            now=fixtures.BASE + timedelta(minutes=1))

    def finish(self, batch):
        self.h.complete_v2(batch, "a", minute=2, credit=2, outcome="refute", route_action="branch")
        self.h.complete_v2(batch, "b", minute=3, credit=0, execution_outcome="failed")

    def test_revert_remains_parent_incumbent_stays_and_restart_replays(self):
        batch = self.batch(); self.select(batch); before = batch.snapshot()["incumbent"]
        self.finish(batch)
        state = batch.snapshot()
        self.assertEqual(state["incumbent"], before)
        self.assertEqual(state["branches"][0]["review_decision"], "REVERT")
        self.assertIn(fixtures.sha("a:runner"), [item["candidate_sha256"]
            for item in batch.pool_selection_hint()["ranked_research_parents"]])
        restarted = ContinuousDiscoveryBatch(self.h.root, allow_temporary=True)
        self.assertEqual(restarted.snapshot(), state)
        selection = self.h.pool_member("c", parent=fixtures.sha("a:runner"))
        batch.select_controller_pool([selection], now=fixtures.BASE + timedelta(minutes=4))
        child = batch.snapshot()["branches"][-1]
        self.assertEqual(child["research_parent_sha256"], fixtures.sha("a:runner"))
        self.assertEqual(child["comparison_incumbent_sha256"], before["candidate_sha256"])

    def test_same_question_cannot_be_retried_as_retained_branch(self):
        batch = self.batch(); self.select(batch); self.finish(batch)
        selection = self.h.pool_member("c", parent=fixtures.sha("a:runner"))
        original = batch.snapshot()["branches"][0]
        selection["question_digest_sha256"] = original["question_digest_sha256"]
        with self.assertRaises(DiscoveryBatchError):
            batch.select_controller_pool([selection], now=fixtures.BASE + timedelta(minutes=4))

    def test_failed_execution_cannot_earn_branch_credit(self):
        batch = self.batch(); self.select(batch)
        with self.assertRaisesRegex(DiscoveryBatchError, "positive research credit"):
            self.h.complete_v2(batch, "a", minute=2, credit=2, outcome="refute",
                               route_action="branch", execution_outcome="failed")

    def test_unreviewed_execution_cannot_earn_branch_credit(self):
        batch = self.batch(); self.select(batch)
        with self.assertRaisesRegex(DiscoveryBatchError, "positive research credit"):
            self.h.complete_v2(batch, "a", minute=2, credit=2, outcome="refute",
                               route_action="branch", independent=False)

    def test_legacy_v2_still_rejects_new_route(self):
        batch = self.h.make_v2_batch(); self.select(batch)
        with self.assertRaisesRegex(DiscoveryBatchError, "route action contract"):
            self.h.complete_v2(batch, "a", minute=2, credit=2, outcome="refute", route_action="branch")

    def test_capacity_not_expanded(self):
        batch = self.batch()
        with self.assertRaises(DiscoveryBatchError):
            batch.select_controller_pool([self.h.pool_member("a"), self.h.pool_member(
                "b", allocation="exploration", method_family="other"), self.h.pool_member("c")],
                now=fixtures.BASE + timedelta(minutes=1))
        self.assertEqual(batch.snapshot()["active_pool_capacity"], 2)


if __name__ == "__main__": unittest.main()
