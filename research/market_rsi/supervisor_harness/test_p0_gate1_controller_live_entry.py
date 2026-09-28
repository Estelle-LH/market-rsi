from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from market_rsi import digest, file_hash, fresh_json
from paid_budget import PaidBudget
from supervisor_harness.bounded_live_outer_runner_v3 import runtime_receipt
from supervisor_harness.global_state_gate import SupervisorGlobalState
from supervisor_harness.p0_gate1_controller_adapter import expected_packet
from supervisor_harness.p0_gate1_controller_live_entry import run
from supervisor_harness.p0_gate1_controller_live_entry import _reviewed_catalog
from supervisor_harness.p0_gate1_executable_plan_canary_fixtures import frozen_catalog_bytes
from supervisor_harness.p0_gate1_trade_query import SYNTHETIC_CATALOG_COMMITMENT_ID


class Gate1ControllerLiveEntryTests(unittest.TestCase):
    def test_no_catalog_keeps_review_only_lane_available(self):
        args = SimpleNamespace(catalog=None,
                               expected_catalog_file_sha256=None,
                               catalog_commitment_id=None)
        self.assertEqual(_reviewed_catalog(args), (None, None))
        args.catalog_commitment_id = "one-sided"
        with self.assertRaisesRegex(ValueError, "required together"):
            _reviewed_catalog(args)

    def test_synthetic_catalog_cannot_enter_paid_live_path(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic-catalog.json"
            path.write_bytes(frozen_catalog_bytes())
            args = SimpleNamespace(
                catalog=path,
                expected_catalog_file_sha256=file_hash(path),
                catalog_commitment_id=SYNTHETIC_CATALOG_COMMITMENT_ID,
            )
            with self.assertRaisesRegex(ValueError, "reviewed real Train"):
                _reviewed_catalog(args)
            args.expected_catalog_file_sha256 = "0" * 64
            with self.assertRaisesRegex(ValueError, "differs from frozen hash"):
                _reviewed_catalog(args)

    def test_publication_failure_occurs_before_credential_read(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            packet = parent / "packet.json"
            runtime = parent / "runtime.json"
            decision = parent / "decision.md"
            claims = parent / "claims"
            claims.mkdir()
            decision.write_text("frozen\n")
            fresh_json(packet, expected_packet())
            # This receipt is not reached because publication fails first.
            fresh_json(runtime, {"schema": "unreached"})
            state = SupervisorGlobalState(parent / "state", decision)
            state_snapshot = state.initialize()
            budget = PaidBudget.create(parent / "budget", {
                "experiment_id": "gate1-entry-test",
                "cap_usd": "1", "target_usd": "0.5",
                "buckets_usd": {"setup": "0.5", "repair": "0.5"},
                "authority": "offline unit test",
            })
            self.assertEqual(budget.snapshot()["effective_cost_usd"], "0")
            args = SimpleNamespace(
                root=parent / "gate1-entry-test-001",
                claim_root=claims,
                global_state_root=parent / "state",
                decision_doc=decision,
                budget_root=parent / "budget",
                packet=packet,
                runtime_receipt=runtime,
                env_file=parent / "must-not-read.env",
                tokenizer_cache=parent / "must-not-read-cache",
                supervisor_claim=parent / "must-not-read-claim",
                experiment_id="gate1-entry-test",
                budget_cap_usd="1",
                cycle_id="gate1-entry-test-001",
                expected_packet_file_sha256=file_hash(packet),
                expected_packet_canonical_sha256=digest(expected_packet()),
                expected_head_sha256=state_snapshot["head_sha256"],
                expected_decision_sha256=file_hash(decision),
                prior_canary_receipt=parent / "canary-result.json",
                prior_canary_sha256="1" * 64,
                release_tag="market-rsi-protocol-v-test",
                expected_release_commit="3" * 40,
                expected_release_tag_object="4" * 40,
                expected_source_sha256="2" * 64,
            )
            with (patch(
                    "supervisor_harness.p0_gate1_controller_live_entry.outer._publication",
                    side_effect=ValueError("unpublished source")),
                  patch(
                    "supervisor_harness.p0_gate1_controller_live_entry."
                    "gate1_canary_receipt.verify_gate1_canary_receipt",
                    return_value={"passed": True}),
                  patch(
                    "supervisor_harness.p0_gate1_controller_live_entry.dotenv_values",
                    side_effect=AssertionError("credential read forbidden"))):
                with self.assertRaisesRegex(ValueError, "unpublished source"):
                    run(args)
            self.assertFalse(args.root.exists())
            self.assertEqual(budget.snapshot()["jobs"], {})

    def test_canary_failure_precedes_publication_state_budget_and_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            packet = parent / "packet.json"
            runtime = parent / "runtime.json"
            decision = parent / "decision.md"
            claims = parent / "claims"
            claims.mkdir()
            decision.write_text("frozen\n")
            fresh_json(packet, expected_packet())
            fresh_json(runtime, {"schema": "test-runtime"})
            state = SupervisorGlobalState(parent / "state", decision)
            state_snapshot = state.initialize()
            budget = PaidBudget.create(parent / "budget", {
                "experiment_id": "gate1-entry-test",
                "cap_usd": "1", "target_usd": "0.5",
                "buckets_usd": {"setup": "0.5", "repair": "0.5"},
                "authority": "offline unit test",
            })
            args = SimpleNamespace(
                root=parent / "gate1-entry-canary-failure",
                claim_root=claims,
                global_state_root=parent / "state",
                decision_doc=decision,
                budget_root=parent / "budget",
                packet=packet,
                runtime_receipt=runtime,
                env_file=parent / "must-not-read.env",
                tokenizer_cache=parent / "must-not-read-cache",
                supervisor_claim=parent / "must-not-read-claim",
                experiment_id="gate1-entry-test",
                budget_cap_usd="1",
                cycle_id="gate1-entry-canary-failure",
                expected_packet_file_sha256=file_hash(packet),
                expected_packet_canonical_sha256=digest(expected_packet()),
                expected_head_sha256=state_snapshot["head_sha256"],
                expected_decision_sha256=file_hash(decision),
                prior_canary_receipt=parent / "missing-canary-result.json",
                prior_canary_sha256="1" * 64,
                release_tag="market-rsi-protocol-v-test",
                expected_release_commit="3" * 40,
                expected_release_tag_object="4" * 40,
                expected_source_sha256="2" * 64,
            )
            with (patch(
                    "supervisor_harness.p0_gate1_controller_live_entry."
                    "gate1_canary_receipt.verify_gate1_canary_receipt",
                    side_effect=ValueError("canary evidence rejected")),
                  patch(
                    "supervisor_harness.p0_gate1_controller_live_entry."
                    "outer._publication") as publication,
                  patch(
                    "supervisor_harness.p0_gate1_controller_live_entry."
                    "dotenv_values") as credential):
                with self.assertRaisesRegex(ValueError, "canary evidence rejected"):
                    run(args)
            publication.assert_not_called()
            credential.assert_not_called()
            self.assertFalse(args.root.exists())
            self.assertEqual(budget.snapshot()["jobs"], {})
            self.assertIsNone(state.snapshot()["active_cycle"])


if __name__ == "__main__":
    unittest.main()
