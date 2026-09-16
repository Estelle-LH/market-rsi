import unittest

from memory_policy.retry_policy import decide


def event(**changes):
    value = {
        "phase": "preflight",
        "cause": "unknown",
        "manifest_frozen": False,
        "valid_scores_written": 0,
        "target_statistics_computed": False,
        "valid_controller_response_written": False,
        "scientific_inputs_unchanged": True,
        "causal_fix_tested": False,
        "idempotent_checkpoint": False,
    }
    value.update(changes)
    return value


class RetryPolicyTests(unittest.TestCase):
    def test_bad_source_can_only_be_skipped_before_freeze(self):
        self.assertEqual(decide(event(cause="source_semantics"))["decision"],
                         "skip_source_before_freeze")
        self.assertEqual(decide(event(cause="source_semantics", manifest_frozen=True))
                         ["decision"], "invalidate_run_and_redesign")

    def test_first_no_score_resource_failure_allows_fresh_recovery(self):
        self.assertEqual(decide(event(
            phase="final_evaluation", cause="resource_envelope",
            manifest_frozen=True, causal_fix_tested=True))["decision"],
            "fresh_id_recovery")
        self.assertEqual(decide(event(
            phase="final_evaluation", cause="resource_envelope",
            manifest_frozen=True, causal_fix_tested=False))["decision"],
            "stop_and_investigate")

    def test_current_four_score_source_failure_invalidates_run(self):
        result = decide(event(
            phase="final_evaluation", cause="source_semantics",
            manifest_frozen=True, valid_scores_written=4))
        self.assertEqual(result["decision"], "invalidate_run_and_redesign")
        self.assertTrue(result["fresh_id_required"])

    def test_exact_idempotent_checkpoint_can_resume(self):
        result = decide(event(
            phase="training", cause="transient_transport", manifest_frozen=True,
            causal_fix_tested=True, idempotent_checkpoint=True))
        self.assertEqual(result["decision"], "resume_same_run")
        self.assertEqual(decide(event(
            phase="training", cause="transient_transport", manifest_frozen=True,
            causal_fix_tested=False, idempotent_checkpoint=True))["decision"],
            "stop_and_investigate")

    def test_saved_controller_plan_can_resume_but_not_be_resampled(self):
        self.assertEqual(decide(event(
            phase="training", cause="runtime_dependency", manifest_frozen=True,
            valid_controller_response_written=True, causal_fix_tested=True,
            idempotent_checkpoint=True))["decision"], "resume_same_run")
        self.assertEqual(decide(event(
            phase="training", cause="runtime_dependency", manifest_frozen=True,
            valid_controller_response_written=True, causal_fix_tested=True,
            idempotent_checkpoint=False))["decision"],
            "invalidate_run_and_redesign")

    def test_results_are_not_retried_for_score(self):
        self.assertEqual(decide(event(
            phase="training", cause="valid_scientific_outcome",
            valid_controller_response_written=True))["decision"],
            "accept_outcome_and_stop")
        self.assertEqual(decide(event(
            phase="final_evaluation", cause="transient_transport",
            valid_scores_written=1, causal_fix_tested=True))["decision"],
            "invalidate_run_and_redesign")

    def test_budget_and_unknown_stop(self):
        self.assertEqual(decide(event(cause="budget_gate"))["decision"],
                         "stop_before_spend")
        self.assertEqual(decide(event())["decision"], "stop_and_investigate")


if __name__ == "__main__":
    unittest.main()
