"""Portable synthetic evidence fixtures: no Train data or predictor fits."""
import copy
import hashlib
import unittest

from supervisor_harness.learning_checkpoint_assessment import (
    SCHEMA, assess_checkpoint, parent_eligibility, validate_saved_checkpoint,
)


def sha(label):
    return hashlib.sha256(label.encode()).hexdigest()


def branch(label="one", *, outcome="succeeded", independent=True, decision="REVERT"):
    return {"execution_outcome": outcome, "independently_reviewed": independent,
            "review_decision": decision, "review_sha256": sha(label + ":review"),
            "question_digest_sha256": sha(label + ":question")}


def checkpoint(label="one", *, credit=0, status="valid", action="bounded_followup", kind=None):
    return {"schema": SCHEMA, "authority_snapshot_sha256": sha(label + ":authority"),
            "validity": {"status": status, "leakage_detected": False,
                         "review_sha256": sha(label + ":review"), "reason": "Reviewed frozen same-row execution."},
            "prediction_decision": "REVERT",
            "learning": {"requested_credit": credit, "kind": kind or {0: "activity", 1: "finding", 2: "hypothesis_test"}[credit],
                         "finding_sha256": sha(label + ":finding") if credit else None,
                         "evidence_sha256": sha(label + ":evidence") if credit else None,
                         "review_sha256": sha(label + ":learning-review") if credit else None,
                         "reason": "Independent evidence of the stated question, not score credit."},
            "exploration": {"action": action, "reason": "First bounded test of a distinct uncertainty at low cost.",
                            "allowance_id_sha256": sha(label + ":allowance") if action == "bounded_followup" else None,
                            "next_question_sha256": sha(label + ":next-question") if action == "bounded_followup" else None,
                            "followup_limit": int(action == "bounded_followup")},
            "reuse": None}


def ranked(label="one", *, assessment=None, remaining=1):
    return {"candidate_id": label, "candidate_sha256": sha(label + ":candidate"),
            "source_batch_id": "batch-one", "source_attempt_id": label,
            "research_credit": 0, "research_outcome": "inconclusive", "route_action": "bounded_followup",
            "followups_remaining": remaining, "learning_checkpoint": assessment or assess_checkpoint(checkpoint(label), branch(label), set()),
            "question_digest_sha256": sha(label + ":question"), "execution_outcome": "succeeded",
            "independently_reviewed": True, "review_sha256": sha(label + ":review")}


class LearningCheckpointAssessmentTests(unittest.TestCase):
    def test_zero_credit_revert_validity_and_prediction_are_independent(self):
        before = checkpoint()
        result = assess_checkpoint(before, branch(), set())
        self.assertEqual(result["learning"]["credit"], 0)
        self.assertEqual(result["prediction_decision"], "REVERT")
        self.assertTrue(parent_eligibility(ranked(assessment=result), 4))
        self.assertFalse(parent_eligibility(ranked(assessment=result, remaining=0), 4))
        self.assertEqual(before, checkpoint())

    def test_failures_and_leaks_never_valid_forecasts_but_repair_can_learn(self):
        for outcome in ("failed", "interrupted"):
            with self.assertRaises(ValueError):
                assess_checkpoint(checkpoint(), branch(outcome=outcome), set())
            repair = checkpoint(credit=2, status="invalid", kind="failure_repair")
            saved = assess_checkpoint(repair, branch(outcome=outcome), set())
            self.assertEqual(saved["learning"]["credit"], 2)
            self.assertFalse(parent_eligibility(ranked(assessment=saved), 4))
        leaked = checkpoint()
        leaked["validity"]["leakage_detected"] = True
        with self.assertRaises(ValueError):
            assess_checkpoint(leaked, branch(), set())
        invalid_score = checkpoint(credit=2, status="invalid")
        with self.assertRaises(ValueError):
            assess_checkpoint(invalid_score, branch(outcome="failed"), set())

    def test_learning_deduplicates_canonical_finding_despite_question_alias(self):
        value = checkpoint("new-question", credit=2)
        value["learning"]["finding_sha256"] = sha("existing-canonical-finding")
        result = assess_checkpoint(value, branch("new-question"), {sha("existing-canonical-finding")})
        self.assertEqual(result["learning"]["credit"], 0)
        self.assertTrue(result["learning"]["duplicate_finding"])
        self.assertEqual(validate_saved_checkpoint(result, branch("new-question")), result)
        inflated = copy.deepcopy(result)
        inflated["learning"]["credit"] = 2
        with self.assertRaises(ValueError):
            validate_saved_checkpoint(inflated, branch("new-question"))

    def test_activity_zero_unreviewed_findings_and_types_fail_closed(self):
        for invalid in (True, 1.0, float("nan"), float("inf"), -1, 3):
            value = checkpoint()
            value["learning"]["requested_credit"] = invalid
            with self.assertRaises(ValueError):
                assess_checkpoint(value, branch(), set())
        with self.assertRaises(ValueError):
            assess_checkpoint(checkpoint(credit=1), branch(independent=False), set())
        value = checkpoint(credit=2)
        value["learning"]["kind"] = "activity"
        with self.assertRaises(ValueError):
            assess_checkpoint(value, branch(), set())

    def test_explicit_review_authority_and_specific_small_question_required(self):
        for path, replacement in (("review", sha("different-review")), ("authority", "0" * 64), ("reason", "")):
            value = checkpoint()
            if path == "review":
                value["validity"]["review_sha256"] = replacement
            elif path == "authority":
                value["authority_snapshot_sha256"] = replacement
            else:
                value["exploration"]["reason"] = replacement
            with self.assertRaises(ValueError):
                assess_checkpoint(value, branch(), set())
        value = checkpoint()
        value["exploration"]["next_question_sha256"] = branch()["question_digest_sha256"]
        with self.assertRaises(ValueError):
            assess_checkpoint(value, branch(), set())

    def test_reuse_is_previous_finding_plus_observed_action_not_assumed_benefit(self):
        value = checkpoint()
        finding = sha("previous-finding")
        value["reuse"] = {"finding_sha256": finding, "status": "proposed", "action_sha256": sha("action"),
                          "evidence_sha256": None, "review_sha256": None, "benefit": "unmeasured", "benefit_evidence_sha256": None}
        with self.assertRaises(ValueError):
            assess_checkpoint(value, branch(), set())
        result = assess_checkpoint(value, branch(), {finding})
        self.assertEqual(result["learning"]["credit"], 0)
        value["reuse"].update(status="observed", evidence_sha256=sha("observed"), review_sha256=sha("review"))
        result = assess_checkpoint(value, branch(), {finding})
        self.assertEqual(result["reuse"]["benefit"], "unmeasured")
        value["reuse"].update(benefit="validated", benefit_evidence_sha256=sha("benefit"))
        with self.assertRaises(ValueError):
            assess_checkpoint(value, branch(), {finding})
        value["reuse"]["status"] = "validated"
        self.assertEqual(assess_checkpoint(value, branch(), {finding})["reuse"]["benefit"], "validated")
        value["validity"]["status"] = "inconclusive"
        with self.assertRaises(ValueError):
            assess_checkpoint(value, branch(independent=False), {finding})

    def test_baseline_shortcut_and_protocol_are_not_forgeable(self):
        baseline = {"candidate_sha256": sha("baseline"), "source_batch_id": "batch-one",
                    "source_attempt_id": None, "research_credit": 0, "research_outcome": "baseline", "route_action": "batch_start"}
        self.assertTrue(parent_eligibility(baseline, 4))
        self.assertTrue(parent_eligibility(dict(baseline, source_batch_id="batch:one"), 4))
        for field, value in (("candidate_sha256", "bad"), ("research_credit", True), ("research_outcome", "invalid"), ("source_attempt_id", "failed")):
            self.assertFalse(parent_eligibility(dict(baseline, **{field: value}), 4))
        for protocol in (0, 5, True, "4"):
            with self.assertRaises(ValueError):
                parent_eligibility(baseline, protocol)

    def test_malformed_saved_evidence_and_unbounded_zero_are_ineligible(self):
        value = checkpoint(action="continue")
        with self.assertRaises(ValueError):
            assess_checkpoint(value, branch(), set())
        result = ranked()
        result["learning_checkpoint"]["learning"]["credit"] = float("nan")
        self.assertFalse(parent_eligibility(result, 4))


if __name__ == "__main__":
    unittest.main()
