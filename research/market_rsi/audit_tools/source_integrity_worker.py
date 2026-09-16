"""Remote, content-blind structural check for one frozen JSONL.zst object."""
import json
import os
from pathlib import Path
import resource
import signal
import time

from sealed_jsonl_integrity import inspect_jsonl_zst


def run(spec):
    resource.setrlimit(resource.RLIMIT_AS, (768 * 1024**2, 768 * 1024**2))

    def stop(*_):
        raise TimeoutError("source-integrity deadline")

    signal.signal(signal.SIGALRM, stop)
    signal.signal(signal.SIGTERM, stop)
    signal.alarm(590)
    start = time.monotonic()
    failure = None
    receipt = None

    def emit(value):
        print(json.dumps(value, sort_keys=True, allow_nan=False), flush=True)

    emit({"stage": "started", "pid": os.getpid(), "session": spec["session"],
          "role": spec["role"], "content_blind": True})
    try:
        receipt = inspect_jsonl_zst(
            Path(spec["path"]),
            advertised_bytes=spec["compressed_bytes"],
            max_input_bytes=spec["compressed_bytes"],
            max_decoded_bytes=spec["max_decoded_bytes"],
            wall_seconds=570,
            decoder_memory_bytes=256 * 1024**2,
        )
        if not receipt["complete"]:
            raise ValueError("source failed structural integrity")
    except BaseException as error:
        failure = {"type": type(error).__name__}
    finally:
        signal.alarm(0)
    emit({"stage": "terminal", "report": {
        "schema": "sealed_source_preflight_worker_v1",
        "complete": failure is None,
        "failure": failure,
        "session": spec["session"],
        "role": spec["role"],
        "path": spec["path"],
        "advertised_bytes": spec["compressed_bytes"],
        "receipt": receipt,
        "elapsed_seconds": time.monotonic() - start,
        "raw_rows_exported": 0,
        "target_statistics_computed": 0,
        "fits": 0,
        "provider_calls": 0,
    }})


if __name__ == "__main__":
    run(SPEC)
