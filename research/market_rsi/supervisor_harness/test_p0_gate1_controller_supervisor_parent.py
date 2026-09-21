from pathlib import Path
from types import SimpleNamespace
import unittest

from supervisor_harness import p0_gate1_controller_live_entry as entry
from supervisor_harness.p0_gate1_controller_supervisor_parent import _child_command


class Gate1ControllerSupervisorParentTests(unittest.TestCase):
    def test_child_command_binds_exact_entry_and_claim_without_secrets(self):
        args = SimpleNamespace(
            root=Path("/tmp/out"), claim_root=Path("/tmp/claims"),
            global_state_root=Path("/tmp/state"),
            decision_doc=Path("/tmp/decision"), budget_root=Path("/tmp/budget"),
            packet=Path("/tmp/packet"), runtime_receipt=Path("/tmp/runtime"),
            env_file=Path("/tmp/env"), tokenizer_cache=Path("/tmp/cache"),
            experiment_id="experiment", budget_cap_usd="200",
            cycle_id="gate1-parent-test", expected_packet_sha256="1" * 64,
            expected_head_sha256="2" * 64,
            expected_decision_sha256="3" * 64,
            prior_canary_sha256="4" * 64,
            release_tag="market-rsi-protocol-v0.1.11",
            expected_source_sha256="5" * 64,
        )
        claim = Path("/tmp/supervisor-claim")
        command = _child_command(args, claim)
        self.assertEqual(command[1], str(Path(entry.__file__).resolve()))
        self.assertEqual(command.count("--supervisor-claim"), 1)
        self.assertIn(str(claim), command)
        self.assertNotIn("TINKER_API_KEY", " ".join(command))


if __name__ == "__main__":
    unittest.main()
