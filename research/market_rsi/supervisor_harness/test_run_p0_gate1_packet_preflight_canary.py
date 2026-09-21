import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from market_rsi import digest
from supervisor_harness.p0_gate1_controller_adapter import expected_packet
from supervisor_harness.run_p0_gate1_packet_preflight_canary import execute


class Gate1PacketPreflightCanaryTests(unittest.TestCase):
    def test_pretty_packet_passes_without_child_or_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet = root / "controller-input.json"
            packet.write_text(
                json.dumps(expected_packet(), sort_keys=True, indent=2) + "\n")
            file_sha = hashlib.sha256(packet.read_bytes()).hexdigest()
            receipt = root / "receipt.json"
            receipt.write_text(json.dumps({
                "schema": "market_p0_gate1_packet_receipt_v1",
                "packet_sha256": file_sha,
            }) + "\n")
            result = execute(packet, receipt, root / "result")
            self.assertTrue(result["passed"])
            self.assertEqual(result["packet_file_sha256"], file_sha)
            self.assertEqual(result["packet_canonical_sha256"],
                             digest(expected_packet()))
            self.assertFalse(result["child_started"])
            self.assertEqual(result["provider_calls"], 0)


if __name__ == "__main__":
    unittest.main()
