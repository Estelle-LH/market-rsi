from pathlib import Path
from types import SimpleNamespace
import json
import tempfile
import unittest
from unittest.mock import patch

from market_rsi import digest, file_hash
from supervisor_harness import p0_gate1_controller_live_entry as entry
from supervisor_harness.p0_gate1_controller_adapter import expected_packet
from supervisor_harness.p0_gate1_controller_supervisor_parent import (
    CANARY_CHILD_ENTRY, CANARY_RELEASE_TAG, _child_command,
    _preflight_packet, run,
)


class Gate1ControllerSupervisorParentTests(unittest.TestCase):
    def test_child_command_binds_exact_entry_and_claim_without_secrets(self):
        args = SimpleNamespace(
            root=Path("/tmp/out"), claim_root=Path("/tmp/claims"),
            global_state_root=Path("/tmp/state"),
            decision_doc=Path("/tmp/decision"), budget_root=Path("/tmp/budget"),
            packet=Path("/tmp/packet"), runtime_receipt=Path("/tmp/runtime"),
            env_file=Path("/tmp/env"), tokenizer_cache=Path("/tmp/cache"),
            experiment_id="experiment", budget_cap_usd="200",
            cycle_id="gate1-parent-test",
            expected_packet_file_sha256="1" * 64,
            expected_packet_canonical_sha256="2" * 64,
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

    def test_canary_child_override_is_programmatic_and_exact(self):
        args = SimpleNamespace(
            root=Path("/tmp/out"), claim_root=Path("/tmp/claims"),
            global_state_root=Path("/tmp/state"),
            decision_doc=Path("/tmp/decision"), budget_root=Path("/tmp/budget"),
            packet=Path("/tmp/packet"), runtime_receipt=Path("/tmp/runtime"),
            env_file=Path("/tmp/env"), tokenizer_cache=Path("/tmp/cache"),
            experiment_id="experiment", budget_cap_usd="200",
            cycle_id="gate1-parent-test",
            expected_packet_file_sha256="1" * 64,
            expected_packet_canonical_sha256="2" * 64,
            expected_head_sha256="2" * 64,
            expected_decision_sha256="3" * 64,
            prior_canary_sha256="4" * 64,
            release_tag=CANARY_RELEASE_TAG,
            expected_source_sha256="5" * 64,
        )
        command = _child_command(
            args, Path("/tmp/claim"), child_entry=CANARY_CHILD_ENTRY)
        self.assertEqual(command[1], str(CANARY_CHILD_ENTRY))
        self.assertEqual(command.count("--supervisor-claim"), 1)
        self.assertNotIn("--child-entry", command)

    def test_arbitrary_programmatic_child_override_is_rejected(self):
        args = SimpleNamespace(release_tag=CANARY_RELEASE_TAG)
        with self.assertRaisesRegex(ValueError, "exact synthetic"):
            _child_command(
                args, Path("/tmp/claim"), child_entry=Path(__file__).resolve())

    def test_real_pretty_packet_binds_file_and_canonical_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            packet = Path(directory) / "controller-input.json"
            packet.write_text(
                json.dumps(expected_packet(), sort_keys=True, indent=2) + "\n")
            args = SimpleNamespace(
                packet=packet,
                expected_packet_file_sha256=file_hash(packet),
                expected_packet_canonical_sha256=digest(expected_packet()),
            )
            result = _preflight_packet(args)
            self.assertEqual(result["packet_file_sha256"], file_hash(packet))
            self.assertEqual(
                result["packet_canonical_sha256"], digest(expected_packet()))

    def test_file_hash_mismatch_stops_parent_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            packet = Path(directory) / "controller-input.json"
            packet.write_text(
                json.dumps(expected_packet(), sort_keys=True, indent=2) + "\n")
            args = SimpleNamespace(
                packet=packet,
                expected_packet_file_sha256="1" * 64,
                expected_packet_canonical_sha256=digest(expected_packet()),
            )
            with self.assertRaisesRegex(ValueError, "packet file differs"):
                _preflight_packet(args)

    def test_canonical_hash_mismatch_stops_parent_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            packet = Path(directory) / "controller-input.json"
            packet.write_text(
                json.dumps(expected_packet(), sort_keys=True, indent=2) + "\n")
            args = SimpleNamespace(
                packet=packet,
                expected_packet_file_sha256=file_hash(packet),
                expected_packet_canonical_sha256="2" * 64,
            )
            with self.assertRaisesRegex(ValueError, "canonical packet differs"):
                _preflight_packet(args)

    def test_mismatch_stops_before_parent_root_or_child_process(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            packet = parent / "controller-input.json"
            packet.write_text(
                json.dumps(expected_packet(), sort_keys=True, indent=2) + "\n")
            supervisor_root = parent / "must-not-exist"
            args = SimpleNamespace(
                cycle_id="gate1-prelaunch-mismatch",
                packet=packet,
                expected_packet_file_sha256="3" * 64,
                expected_packet_canonical_sha256=digest(expected_packet()),
                supervisor_root=supervisor_root,
            )
            with patch(
                    "supervisor_harness.p0_gate1_controller_supervisor_parent."
                    "subprocess.Popen") as popen:
                with self.assertRaisesRegex(ValueError, "packet file differs"):
                    run(args)
            popen.assert_not_called()
            self.assertFalse(supervisor_root.exists())


if __name__ == "__main__":
    unittest.main()
