"""Controller-proposed capacities, independent numeric fixtures, no model fits."""
from copy import deepcopy
import math
import unittest

from supervisor_harness import derived_feature_semantic_contract_v1 as h
from supervisor_harness import hypothesis_differentiation_ledger_v1 as r


def score_time(score, seconds):
    if isinstance(score, bool) or isinstance(seconds, bool): raise ValueError("boolean input")
    if not isinstance(score, (int, float)) or not isinstance(seconds, (int, float)):
        raise ValueError("numeric input required")
    if not math.isfinite(score) or not math.isfinite(seconds): raise ValueError("nonfinite input")
    return max(-1, min(1, score / 14)) * (1 - max(0, min(1, seconds / 3600)))


def candidate(feature="score-time"):
    return {"candidate_id": "candidate-" + feature, "question_id": "test-" + feature,
        "actual_parent_sha256": "a" * 64, "comparison_incumbent_sha256": "b" * 64,
        "recipe": "exact nonexecutable Controller recipe",
        "causal_inputs": ["home_score_diff_pre", "regulation_seconds_remaining"] if feature == "score-time" else [feature],
        "equation": "sigmoid((1+beta)*logit(p)+gamma*x),x=clip(score/14,-1,1)*(1-clip(seconds/3600,0,1))" if feature == "score-time" else feature,
        "loss": "summed unweighted binary NLL+8*(beta^2+gamma^2)",
        "fitting_constants": {"initial_beta": 0, "initial_gamma": 0, "beta_lower": -1,
            "max_iterations": 1000, "gradient_tolerance": 1e-8, "restarts": 0, "fallback": False}}


class SemanticContractTests(unittest.TestCase):
    def test_fixed_correct_feature_passes_independent_oracle(self):
        receipt = h.validate_feature(score_time)
        self.assertTrue(receipt["passed"]); self.assertEqual(receipt["statistical_fits"], 0)
        self.assertEqual(receipt["numeric_fixtures"], 19)
        self.assertEqual(receipt["invalid_input_fixtures"], 6)

    def test_sign_units_and_formula_mutants_fail_before_fit(self):
        mutants = (lambda score, seconds: score_time(-score, seconds),
                   lambda score, seconds: score_time(score, seconds / 60),
                   lambda score, seconds: score_time(score, seconds) * (1 - max(0, min(1, seconds / 3600))))
        for mutant in mutants:
            with self.subTest(mutant=mutant), self.assertRaisesRegex(ValueError, "semantic disagreement"):
                h.validate_feature(mutant)

    def test_current_finite_vector_guard_misses_designated_semantic_mutations(self):
        from experiments.nfl_ingame_market_freshness_interaction_offset import _vector
        builders = [score_time, lambda score, seconds: score_time(-score, seconds),
                    lambda score, seconds: score_time(score, seconds / 60),
                    lambda score, seconds: score_time(score, seconds) ** 3]
        for builder in builders:
            _vector([builder(score, seconds) for score, seconds, _ in h.FIXTURES], "synthetic derived feature")
        h.validate_feature(builders[0])
        for builder in builders[1:]:
            with self.assertRaises(ValueError): h.validate_feature(builder)

    def test_nonfinite_or_missing_input_guards_cannot_be_skipped(self):
        def permissive(score, seconds):
            if not math.isfinite(score) or not math.isfinite(seconds): return 0
            return score_time(float(score), float(seconds))
        with self.assertRaisesRegex(ValueError, "inputs must fail"): h.validate_feature(permissive)


class DifferentiationTests(unittest.TestCase):
    def test_distinct_hypothesis_preserves_actual_parent_and_incumbent(self):
        entry = r.create_entry(candidate(), candidate("uncertainty-possession"),
                               "different causal score/time interaction", ["No paired gain under frozen judge"])
        self.assertFalse(entry["exact_declared_repeat"])
        self.assertNotEqual(entry["research_parent_sha256"], entry["comparison_incumbent_sha256"])
        self.assertEqual(entry["status"], "proposed_unexecuted")

    def test_renamed_exact_repeat_is_not_new_question_by_itself(self):
        original = candidate("consumed-pressure"); renamed = deepcopy(original)
        renamed.update(candidate_id="different-name", question_id="different-name", actual_parent_sha256="c" * 64)
        entry = r.create_entry(renamed, original, "rename only, not new mechanism", ["Already tested"])
        self.assertTrue(entry["exact_declared_repeat"])
        self.assertEqual(r.recipe_signature(original), r.recipe_signature(renamed))

    def test_loss_or_constants_difference_is_visible_without_requiring_gain(self):
        original = candidate(); changed = deepcopy(original)
        changed["fitting_constants"]["max_iterations"] = 800
        self.assertNotEqual(r.recipe_signature(original), r.recipe_signature(changed))
        changed = deepcopy(original); changed["loss"] += "+interceptPenalty"
        self.assertNotEqual(r.recipe_signature(original), r.recipe_signature(changed))

    def test_valid_negative_feedback_retained_without_rewriting_original(self):
        entry = r.create_entry(candidate(), candidate("possession"), "new score interaction", ["No improvement"])
        original = deepcopy(entry)
        feedback = {key: entry[key] for key in ("candidate_id", "research_parent_sha256", "comparison_incumbent_sha256")}
        reviewed = r.with_feedback(entry, {**feedback, "independently_reviewed": True,
            "prediction_decision": "REVERT", "performance_status": "valid_no_leakage"},
            "Exact recipe failed; preserve evidence and test a distinct question")
        self.assertEqual(entry, original); self.assertTrue(reviewed["retained_for_distinct_research"])
        self.assertEqual(reviewed["reviewed_feedback"]["prediction_decision"], "REVERT")

    def test_execution_failure_is_not_valid_performance_evidence(self):
        entry = r.create_entry(candidate(), candidate("possession"), "new score interaction", ["No gain"])
        feedback = {key: entry[key] for key in ("candidate_id", "research_parent_sha256", "comparison_incumbent_sha256")}
        reviewed = r.with_feedback(entry, {**feedback, "independently_reviewed": True,
            "prediction_decision": "REVERT", "performance_status": "invalid"}, "Repair implementation first")
        self.assertFalse(reviewed["valid_performance_evidence"])
        self.assertIn("specification", reviewed)

    def test_foreign_feedback_cannot_be_attached_to_hypothesis(self):
        entry = r.create_entry(candidate(), candidate("possession"), "new interaction", ["No gain"])
        feedback = {key: entry[key] for key in ("candidate_id", "research_parent_sha256", "comparison_incumbent_sha256")}
        feedback.update(independently_reviewed=True, prediction_decision="REVERT", performance_status="valid_no_leakage")
        feedback["research_parent_sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "independently reviewed"):
            r.with_feedback(entry, feedback, "different parent result cannot be attached")

    def test_missing_question_constants_falsification_or_nonfinite_spec_fails(self):
        value = candidate(); del value["fitting_constants"]
        with self.assertRaises(ValueError): r.create_entry(value, candidate(), "difference", ["No gain"])
        with self.assertRaises(ValueError): r.create_entry(candidate(), candidate(), "difference", [])
        value = candidate(); value["fitting_constants"]["gradient_tolerance"] = float("nan")
        with self.assertRaises(ValueError): r.recipe_signature(value)


if __name__ == "__main__": unittest.main()
