"""Local-only peer positive-control tests; not E2B isolation evidence."""
from __future__ import annotations

import hashlib
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest

from supervisor_harness import peer_marker_server as peer


class PeerMarkerServerTests(unittest.TestCase):
    def test_rejects_missing_or_oversized_marker(self):
        with tempfile.TemporaryDirectory() as temp:
            marker = Path(temp) / "marker"
            with self.assertRaises(ValueError):
                peer._marker(marker)
            marker.write_bytes(b"x" * 129)
            with self.assertRaises(ValueError):
                peer._marker(marker)

    def test_real_local_service_and_exact_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            marker = Path(temp) / "marker"
            marker.write_bytes(b"synthetic-peer-marker-01")
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
            process = subprocess.Popen([
                sys.executable, "-I", str(Path(peer.__file__).resolve()),
                "--serve", "--marker", str(marker), "--bind", "127.0.0.1",
                "--port", str(port)], stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL)
            try:
                result = peer.self_check(port=port, marker_path=marker, attempts=10)
                self.assertTrue(result["local_service_responded"])
                self.assertEqual(result["marker_sha256"], hashlib.sha256(
                    marker.read_bytes()).hexdigest())
                self.assertIsNone(process.poll())
            finally:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            self.assertIsNotNone(process.returncode)


if __name__ == "__main__":
    unittest.main()
