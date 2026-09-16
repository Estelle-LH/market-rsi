import unittest

from data_scientist_harness.evaluation_evidence_contract import (
    validate_evaluation_evidence_output,
)


class EvaluationEvidenceContractTests(unittest.TestCase):
    def test_non_prediction_confirmation_can_use_scalar_terminal_evidence(self):
        validate_evaluation_evidence_output({
            "kind": "scalar_terminal_v1",
            "metric": "second_view_rejected",
            "persist_terminal_record_runner_private": True,
            "public_visibility": "aggregate_only",
        })

    def test_unknown_or_identity_visible_evidence_fails(self):
        with self.assertRaisesRegex(ValueError, "known"):
            validate_evaluation_evidence_output({"kind": "future_unknown"})
        with self.assertRaisesRegex(ValueError, "aggregate-only"):
            validate_evaluation_evidence_output({
                "kind": "scalar_terminal_v1",
                "metric": "pass",
                "persist_terminal_record_runner_private": True,
                "public_visibility": "raw_units",
            })


if __name__ == "__main__":
    unittest.main()

