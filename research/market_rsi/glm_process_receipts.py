"""Independent readback of the two local GLM worker phases; no provider calls."""
import hashlib
import json
import math
from pathlib import Path
import sys

from market_rsi import digest, file_hash


def verify_glm_processes(directory, prepared, request, response, reads):
    from worker_receipts import read_regular
    directory = Path(directory).absolute()
    cache = None
    total_elapsed = 0
    sources = {name: file_hash(Path(__file__).with_name(name))
        for name in ("glm_process_worker.py", "researcher_worker.py", "glm_canary.py")}
    for operation in ("encode", "sample"):
        root = directory / (operation + "-process")
        claim, receipt = reads.read(root / "claim.json"), reads.read(root / "receipt.json")
        blobs = {}
        for name in ("input", "stdout", "stderr"):
            path = root / (name + ".bin")
            blobs[name] = read_regular(path)
            reads.files[str(path)] = hashlib.sha256(blobs[name]).hexdigest()
        body, answer = json.loads(blobs["input"]), json.loads(blobs["stdout"])
        base_keys = {"operation", "cache_dir", "job_directory", "source_hashes"}
        expected = base_keys | ({"messages"} if operation == "encode" else {"token_ids", "max_output", "timeout_seconds"})
        if (set(body) != expected or body["operation"] != operation or body["source_hashes"] != sources
                or body["job_directory"] != str(directory) or not isinstance(body["cache_dir"], str)
                or set(answer) != {"operation", "result"} or answer["operation"] != operation):
            raise ValueError("GLM process operation/source/input binding changed")
        if cache is not None and cache != body["cache_dir"]:
            raise ValueError("tokenizer cache changed across worker phases")
        cache = body["cache_dir"]
        command = [sys.executable, "-I", str(Path(__file__).with_name("glm_process_worker.py"))]
        env_names = {"PATH", "LANG", "TOKENIZERS_PARALLELISM"} | ({"RSI_TINKER_API_KEY"} if operation == "sample" else set())
        wall, reap = claim.get("wall_seconds"), claim.get("reap_seconds")
        if (claim["command_sha256"] != digest(command) or claim["input_sha256"] != reads.files[str(root / "input.bin")]
                or claim["environment_names"] != sorted(env_names)
                or claim["supervisor_source_sha256"] != file_hash(Path(__file__).with_name("bounded_process.py"))
                or type(wall) not in (int, float) or not math.isfinite(wall)
                or not 0 < wall <= prepared["audit"]["resource_limits"]["max_wall_seconds"] - 2
                or reap != 2 or claim["remote_cancellation_established"] is not False
                or claim["max_stdout_bytes"] != 16 * 1024 * 1024 or claim["max_stderr_bytes"] != 256 * 1024):
            raise ValueError("GLM process command/environment/bounds changed")
        if (receipt["process_reaped"] is not True or receipt["exit_code"] != 0 or receipt["failure"] is not None
                or type(receipt["pid"]) is not int or receipt["pid"] <= 0
                or receipt["output_complete"] is not True or receipt["input_complete"] is not True
                or receipt["input_bytes_written"] != len(blobs["input"])
                or type(receipt["elapsed_seconds"]) not in (int, float) or not math.isfinite(receipt["elapsed_seconds"])
                or not 0 <= receipt["elapsed_seconds"] <= wall + reap
                or receipt["remote_request_terminal"] is not None
                or receipt["remote_cancellation_established"] is not False or receipt["unused_budget_released"] is not False):
            raise ValueError("GLM local process has no independently closed completion")
        total_elapsed += receipt["elapsed_seconds"]
        for name in ("stdout", "stderr"):
            if (receipt[name + "_bytes"] != len(blobs[name])
                    or len(blobs[name]) > claim["max_" + name + "_bytes"]
                    or receipt[name + "_sha256"] != reads.files[str(root / (name + ".bin"))]):
                raise ValueError("GLM process output changed")
        if operation == "encode":
            expected_result = {k: request[k] for k in ("rendered_prompt", "token_ids", "tokenizer_repo",
                                                       "tokenizer_revision", "chat_template_sha256")}
            if body["messages"] != prepared["messages"] or answer["result"] != expected_result:
                raise ValueError("encoded request differs from completed local worker")
        elif (body["token_ids"] != request["token_ids"] or body["max_output"] != request["max_output_tokens"]
                or type(body["timeout_seconds"]) not in (int, float) or not math.isfinite(body["timeout_seconds"])
                or not 0 < body["timeout_seconds"] <= wall or answer["result"] != response):
            raise ValueError("sample differs from completed local worker")
    if total_elapsed > prepared["audit"]["resource_limits"]["max_wall_seconds"]:
        raise ValueError("combined GLM process time exceeds the one request allowance")
