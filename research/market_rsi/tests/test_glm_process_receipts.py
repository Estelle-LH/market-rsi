"""Fabricated local-process records only; no model, network or candidate code."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

from glm_process_receipts import verify_glm_processes
from market_rsi import canonical, digest, file_hash, fresh_json
from worker_receipts import Receipts


class ProcessReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve() / "fixture-job"
        self.root.mkdir()
        self.prepared = {"messages": [{"role": "user", "content": "fixture"}],
            "audit": {"resource_limits": {"max_wall_seconds": 30}}}
        self.request = {"rendered_prompt": "fixture", "token_ids": [1, 2],
            "tokenizer_repo": "fixture", "tokenizer_revision": "fixture", "chat_template_sha256": "a" * 64,
            "max_output_tokens": 10}
        self.response = {"text": "fixture response", "output_tokens": [3], "cached_input_tokens": 0,
            "finish_reason": "stop", "provider": {"fixture": True}}
        here = Path(__file__).resolve().parents[1]
        sources = {n: file_hash(here / n) for n in ("glm_process_worker.py", "researcher_worker.py", "glm_canary.py")}
        for operation in ("encode", "sample"):
            root = self.root / (operation + "-process")
            root.mkdir()
            body = {"operation": operation, "cache_dir": "/fixture-cache", "job_directory": str(self.root), "source_hashes": sources}
            if operation == "encode":
                body["messages"] = self.prepared["messages"]
                result = {k: v for k, v in self.request.items() if k != "max_output_tokens"}
            else:
                body.update(token_ids=[1, 2], max_output=10, timeout_seconds=20)
                result = self.response
            data = {"input": canonical(body).encode(), "stdout": canonical({"operation": operation, "result": result}).encode(),
                    "stderr": b""}
            for name, value in data.items():
                (root / (name + ".bin")).write_bytes(value)
            hashes = {name: hashlib.sha256(value).hexdigest() for name, value in data.items()}
            fresh_json(root / "claim.json", {"command_sha256": digest([sys.executable, "-I", str(here / "glm_process_worker.py")]),
                "input_sha256": hashes["input"], "environment_names": sorted(["PATH", "LANG", "TOKENIZERS_PARALLELISM"]
                    + (["RSI_TINKER_API_KEY"] if operation == "sample" else [])),
                "wall_seconds": 20, "reap_seconds": 2, "max_stdout_bytes": 16*1024*1024, "max_stderr_bytes": 256*1024,
                "supervisor_source_sha256": file_hash(here / "bounded_process.py"), "remote_cancellation_established": False})
            fresh_json(root / "receipt.json", {"pid": 99999, "process_reaped": True, "exit_code": 0, "failure": None,
                "elapsed_seconds": 1, "stdout_bytes": len(data["stdout"]), "stderr_bytes": 0,
                "stdout_sha256": hashes["stdout"], "stderr_sha256": hashes["stderr"],
                "output_complete": True, "input_complete": True, "input_bytes_written": len(data["input"]),
                "remote_request_terminal": None, "remote_cancellation_established": False, "unused_budget_released": False})

    def tearDown(self):
        self.tmp.cleanup()

    def verify(self):
        reads = Receipts()
        verify_glm_processes(self.root, self.prepared, self.request, self.response, reads)
        reads.revalidate()
        return reads

    def mutate(self, relative, **values):
        path = self.root / relative
        content = json.loads(path.read_text())
        content.update(values)
        path.write_text(json.dumps(content))

    def test_two_bound_phases_and_full_output_readset(self):
        self.assertEqual(len(self.verify().files), 10)

    def test_response_must_be_the_childs_exact_saved_response(self):
        self.response = dict(copy.deepcopy(self.response), text="replacement response")
        with self.assertRaisesRegex(ValueError, "sample differs"):
            self.verify()

    def test_missing_local_reap_cannot_be_called_completed(self):
        self.mutate("sample-process/receipt.json", process_reaped=False)
        with self.assertRaisesRegex(ValueError, "closed completion"):
            self.verify()

    def test_local_receipt_cannot_claim_remote_cancellation_or_free_cost(self):
        self.mutate("sample-process/receipt.json", remote_cancellation_established=True, unused_budget_released=True)
        with self.assertRaisesRegex(ValueError, "closed completion"):
            self.verify()

    def test_input_token_ids_cannot_change_between_phases(self):
        self.request["token_ids"] = [5, 6]
        with self.assertRaisesRegex(ValueError, "encoded request differs"):
            self.verify()

    def test_wrong_environment_names_rejected_without_reading_values(self):
        self.mutate("encode-process/claim.json", environment_names=["RSI_TINKER_API_KEY"])
        with self.assertRaisesRegex(ValueError, "command/environment/bounds"):
            self.verify()

    def test_partial_local_output_never_becomes_terminal_research(self):
        self.mutate("sample-process/receipt.json", output_complete=False)
        with self.assertRaises(ValueError):
            self.verify()

    def test_individual_time_limits_cannot_replace_combined_request_allowance(self):
        for op in ("encode", "sample"):
            self.mutate(op + "-process/receipt.json", elapsed_seconds=20)
        with self.assertRaisesRegex(ValueError, "combined GLM process time"):
            self.verify()

    def test_later_output_mutation_invalidates_readset(self):
        reads = self.verify()
        (self.root / "sample-process/stderr.bin").write_bytes(b"later mutation")
        with self.assertRaises(ValueError):
            reads.revalidate()


if __name__ == "__main__":
    unittest.main()
