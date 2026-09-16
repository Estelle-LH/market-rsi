"""Trusted subprocess entrypoint. No tools, alternate model, retries or scoring."""
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from market_rsi import file_hash
from researcher_worker import GLMTransport


def main():
    data = sys.stdin.buffer.read(16 * 1024 * 1024 + 1)
    if len(data) > 16 * 1024 * 1024:
        raise ValueError("bounded worker input exceeded")
    request = json.loads(data)
    if request.get("source_hashes") != {name: file_hash(Path(__file__).with_name(name))
            for name in ("glm_process_worker.py", "researcher_worker.py", "glm_canary.py")}:
        raise ValueError("trusted provider worker source changed")
    common = {"operation", "cache_dir", "job_directory", "source_hashes"}
    operation = request["operation"]
    expected = common | ({"messages"} if operation == "encode" else {"token_ids", "max_output", "timeout_seconds"})
    if operation not in {"encode", "sample"} or set(request) != expected:
        raise ValueError("unexpected worker operation")
    # This entrypoint is not an alternate route around the outer admission gate.
    import development_harbor
    development_harbor.require_admission(request["job_directory"])
    key = os.environ.get("RSI_TINKER_API_KEY") if operation == "sample" else None
    if operation == "sample" and not key:
        raise ValueError("scoped provider key unavailable")
    transport = GLMTransport(key, request["cache_dir"])
    if operation == "encode":
        value = transport._encode_unbounded(request["messages"])
    else:
        transport._load_tokenizer()
        value = transport._sample_unbounded(request["token_ids"], request["max_output"], request["timeout_seconds"])
    print(json.dumps({"operation": operation, "result": value}, allow_nan=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Do not emit SDK exception bodies, credentials or a host traceback.
        print(json.dumps({"error_type": type(error).__name__}), file=sys.stderr)
        raise SystemExit(1)
