"""Local guest-worker checks; these are not live E2B execution evidence."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from market_rsi import digest
from supervisor_harness import researcher_guest_worker as worker


def order():
    return {"schema": "market_broker_researcher_order_v1",
            "cycle_id": "cycle-01", "input_sha256": "a" * 64,
            "decision_sha256": "b" * 64, "task_id": "hash-01",
            "task_type": "code_canary", "data_role": "synthetic_fixture",
            "public_text": "public résumé"}


class ResearcherGuestWorkerTests(unittest.TestCase):
    def test_exact_bounded_order_is_hash_bound(self):
        result = worker.execute(order())
        self.assertEqual(result["order_sha256"], digest(order()))
        self.assertEqual(result["decision_sha256"], "b" * 64)

    def test_rejects_noncanary_role_and_unknown_fields(self):
        for change in ({"task_type": "arbitrary_code"},
                       {"data_role": "sealed_final"},
                       {"extra": "instruction"},
                       {"decision_sha256": "not-a-hash"},
                       {"public_text": "x" * 4097}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                worker.execute({**order(), **change})

    def test_subprocess_writes_once_and_preserves_existing_result(self):
        with tempfile.TemporaryDirectory() as temp:
            source, output = Path(temp) / "order.json", Path(temp) / "result.json"
            source.write_text(json.dumps(order()))
            command = [sys.executable, "-I", str(Path(worker.__file__).resolve()),
                       "--order", str(source), "--result", str(output)]
            first = subprocess.run(command, capture_output=True, text=True,
                                   timeout=5, check=False)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(json.loads(output.read_text())["order_sha256"], digest(order()))
            existing = output.read_bytes()
            second = subprocess.run(command, capture_output=True, text=True,
                                    timeout=5, check=False)
            self.assertNotEqual(second.returncode, 0)
            self.assertEqual(output.read_bytes(), existing)


if __name__ == "__main__":
    unittest.main()
