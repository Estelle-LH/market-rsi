from __future__ import annotations

import os
from pathlib import Path
from subprocess import CompletedProcess
import tempfile
import unittest
from unittest.mock import patch

from supervisor_harness import bounded_live_entry_v1 as entry
from market_rsi import canonical, digest


class LiveEntryClearTests(unittest.TestCase):
    def _run(self, outputs):
        values = iter(outputs)

        def fake(command, **kwargs):
            self.assertTrue(kwargs["check"])
            self.assertEqual(kwargs["timeout"], 10)
            return CompletedProcess(command, 0, stdout=next(values), stderr="")

        return fake

    def test_clear_excludes_entry_and_parent_but_detects_no_peer(self):
        pid = os.getpid()
        rows = f"{pid} 42 python entry --cycle-id fresh-id\n42 1 zsh fresh-id\n"
        with patch.object(entry.subprocess, "run", side_effect=self._run([rows, ""])):
            result = entry.exact_clear("fresh-id")
        self.assertTrue(result["clear"])
        self.assertEqual(result["matching_process_ids"], [])
        self.assertEqual(result["matching_container_ids"], [])

    def test_matching_peer_fails_closed(self):
        pid = os.getpid()
        rows = f"{pid} 1 python entry\n9191 1 python worker fresh-id\n"
        with patch.object(entry.subprocess, "run", side_effect=self._run([rows, ""])):
            result = entry.exact_clear("fresh-id")
        self.assertFalse(result["clear"])
        self.assertEqual(result["matching_process_ids"], ["9191"])

    def test_exact_container_fails_closed(self):
        pid = os.getpid()
        rows = f"{pid} 1 python entry\n"
        with patch.object(entry.subprocess, "run", side_effect=self._run([rows, "abc123\n"])):
            result = entry.exact_clear("fresh-id")
        self.assertFalse(result["clear"])
        self.assertEqual(result["matching_container_ids"], ["abc123"])

    def test_inventory_error_is_not_treated_as_clear(self):
        with patch.object(entry.subprocess, "run", side_effect=TimeoutError("inventory timeout")):
            with self.assertRaises(TimeoutError):
                entry.exact_clear("fresh-id")

    def test_process_inventory_requests_untruncated_commands(self):
        pid = os.getpid()
        rows = f"{pid} 1 python entry\n"
        seen = []

        def fake(command, **kwargs):
            seen.append(command)
            return CompletedProcess(command, 0, stdout=rows if command[0] == "ps" else "", stderr="")

        with patch.object(entry.subprocess, "run", side_effect=fake):
            self.assertTrue(entry.exact_clear("fresh-id")["clear"])
        self.assertEqual(seen[0], ["ps", "-axww", "-o", "pid=,ppid=,command="])

    def test_invalid_identity_fails_before_credential_read(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            args = unittest.mock.Mock(
                cycle_id="INVALID ID", prior_canary_sha256="0" * 64,
                root=root / "INVALID ID", adapter_claim_root=root)
            with patch.object(entry, "dotenv_values") as credential:
                with self.assertRaises(ValueError):
                    entry.run(args)
            credential.assert_not_called()

    def test_root_mismatch_fails_before_credential_read(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            claims = base / "claims"
            claims.mkdir()
            args = unittest.mock.Mock(
                cycle_id="fresh-id", prior_canary_sha256="0" * 64,
                root=base / "wrong-name", adapter_claim_root=claims)
            with patch.object(entry, "dotenv_values") as credential:
                with self.assertRaises(ValueError):
                    entry.run(args)
            credential.assert_not_called()

    def test_bad_prior_hash_fails_before_credential_read(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            args = unittest.mock.Mock(
                cycle_id="fresh-id", prior_canary_sha256="bad",
                root=base / "fresh-id", adapter_claim_root=base)
            with patch.object(entry, "dotenv_values") as credential:
                with self.assertRaises(ValueError):
                    entry.run(args)
            credential.assert_not_called()

    def test_packet_hash_mismatch_fails_before_credential_read(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            claims = base / "claims"
            claims.mkdir()
            text = "public synthetic fixture"
            packet = {
                "schema": "market_glm_first_public_packet_v1",
                "cycle_id": "fresh-id",
                "context_items": [{
                    "role": "synthetic_fixture",
                    "source_id": "synthetic:test",
                    "text": text,
                    "text_sha256": __import__("hashlib").sha256(text.encode()).hexdigest(),
                }],
            }
            packet_path = base / "packet.json"
            packet_path.write_text(canonical(packet))
            runtime_path = base / "runtime.json"
            runtime_path.write_text(canonical({"fixture": True}))
            args = unittest.mock.Mock(
                cycle_id="fresh-id", prior_canary_sha256="0" * 64,
                root=base / "fresh-id", adapter_claim_root=claims,
                packet=packet_path, runtime_receipt=runtime_path,
                global_state_root=base / "state", decision_doc=base / "decision",
                budget_root=base / "budget", release_tag="fixture",
                expected_source_sha256="1" * 64,
                expected_packet_sha256="2" * 64)
            self.assertNotEqual(digest(packet), args.expected_packet_sha256)
            with (patch.object(entry.outer, "_publication"),
                  patch.object(entry.outer, "_runtime"),
                  patch.object(entry, "dotenv_values") as credential):
                with self.assertRaisesRegex(ValueError, "frozen hash"):
                    entry.run(args)
            credential.assert_not_called()

    def test_local_encoding_failure_happens_without_provider_or_outer_dispatch(self):
        class Backend:
            def encode(self, request):
                raise ImportError("missing local template dependency")

            def sample(self, *args, **kwargs):
                raise AssertionError("provider must not be called")

        with patch.object(entry.outer, "run_outer") as dispatch:
            with self.assertRaises(ImportError):
                entry._preflight_encoding(Backend(), {"fixture": True})
        dispatch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
