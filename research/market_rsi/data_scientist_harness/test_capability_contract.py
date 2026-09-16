from pathlib import Path
import tempfile
import unittest

from data_scientist_harness import fixtures
from data_scientist_harness.broker import Broker
class CapabilityContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "work"
        self.broker = Broker(
            self.root, fixtures.workspace(self.root, network=True),
            transport=fixtures.fake_transport,
        )
        status = self.broker.call("inspect_harness", {})
        self.broker.call("acknowledge_current_findings", {
            "finding_sha256": status["finding_sha256"],
            "responses": [{
                "id": "fixture-only",
                "handling": "Synthetic contract test",
                "next_evidence": "No empirical claim",
            }],
        })
        self.read = self.broker.call("read_public_source", {
            "url": "https://example.org/capability-contract", "offset": 0,
        })
        self.research_args = {
            "layer": "data_quality",
            "question": "Which exact clock fields are observed?",
            "read_records": [self.read["record_id"]],
            "applicability": "Synthetic contract test only",
            "limitations": "No provider data were read",
            "alternatives": "Do not implement the capability",
            "proposed_test": "Validate exact evidence binding",
        }
        self.research = self.broker.call("record_research", self.research_args)

    def tearDown(self):
        self.tmp.cleanup()

    def proposal(self):
        return {
            "name": "typed_clock_capture",
            "problem": "The capture needs an explicit observed-time contract.",
            "research_record": self.research["record_id"],
            "evidence_refs": [{
                "record_id": self.read["record_id"],
                "json_pointer": "/result/read_level",
                "observed_value_json": '"delivered_text_range_not_proof_of_understanding"',
                "claim": "The source result is only a delivered text range.",
                "inference_limit": "It is not proof of understanding or provider behavior.",
            }],
            "proposed_interface": "Parse declared timestamps and preserve raw bytes plus receive time.",
            "verification_needed": "Unit fixtures plus one legally accessible prospective canary.",
            "unsupported_assumptions": ["Provider field availability is not established."],
        }

    def test_exact_ledger_value_archives_without_activation(self):
        result = self.broker.call("request_capability", self.proposal())
        self.assertFalse(result["activated"])
        self.assertEqual(result["verified_evidence"][0]["observed_value"],
                         "delivered_text_range_not_proof_of_understanding")
        self.assertTrue(result["unsupported_assumptions_preserved"])

    def test_invented_measurement_fails_closed(self):
        proposal = self.proposal()
        proposal["evidence_refs"][0]["observed_value_json"] = "1433"
        with self.assertRaisesRegex(ValueError, "differs"):
            self.broker.call("request_capability", proposal)

    def test_missing_evidence_fails_closed(self):
        proposal = self.proposal()
        proposal["evidence_refs"] = []
        with self.assertRaisesRegex(ValueError, "at least one exact evidence"):
            self.broker.call("request_capability", proposal)

    def test_controller_authored_argument_is_not_evidence(self):
        proposal = self.proposal()
        proposal["evidence_refs"][0].update({
            "record_id": self.research["record_id"],
            "json_pointer": "/arguments/question",
            "observed_value_json": '"Which exact clock fields are observed?"',
        })
        with self.assertRaisesRegex(ValueError, "within /result|controller-authored"):
            self.broker.call("request_capability", proposal)

    def test_defer_must_bind_latest_capability_name(self):
        self.broker.call("request_capability", self.proposal())
        with self.assertRaisesRegex(ValueError, "typed_clock_capture"):
            self.broker.call("submit_research_decision", {
                "action": "defer", "trial_id": "", "reason": "Generic next step"
            })
        result = self.broker.call("submit_research_decision", {
            "action": "defer", "trial_id": "",
            "reason": "typed_clock_capture is the exact unimplemented next work order.",
        })
        self.assertTrue(result["submitted"])


if __name__ == "__main__":
    unittest.main()
