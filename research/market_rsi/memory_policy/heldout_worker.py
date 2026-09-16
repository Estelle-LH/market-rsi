"""Materialize one preflight-bound later source without exposing raw rows."""
import json
import os
from pathlib import Path
import resource
import signal
import time

from memory_materialize import CacheProfile, write_cache
from sealed_jsonl_integrity import verify_materialization_transport
from single_object_stream import stream_object
from market_rsi import fresh_json


def run(spec):
    resource.setrlimit(resource.RLIMIT_AS, (768 * 1024**2, 768 * 1024**2))

    def stop(*_):
        raise TimeoutError("held-out materialization deadline")

    signal.signal(signal.SIGALRM, stop)
    signal.signal(signal.SIGTERM, stop)
    signal.alarm(590)
    start = time.monotonic()
    failure = None
    transport = header = None
    profile = CacheProfile(spec["contract"], spec["day_start_ms"])
    output = Path(spec["output"])
    output.parent.mkdir(parents=True, exist_ok=True)
    fresh_json(output.with_suffix(".claim.json"), {"spec": spec, "pid": os.getpid()})

    def emit(value):
        print(json.dumps(value, sort_keys=True, allow_nan=False), flush=True)

    emit({"stage": "started", "pid": os.getpid(), "date": spec["date"],
          "role": spec["role"]})

    def consume(line, ordinal):
        profile.consume(line, ordinal)
        if ordinal % 100000 == 0:
            emit({"stage": "decode", "records": ordinal,
                  "elapsed_seconds": time.monotonic() - start})

    try:
        transport = stream_object(
            spec["path"], advertised_bytes=spec["compressed_bytes"],
            max_input_bytes=spec["compressed_bytes"], max_decoded_bytes=3 * 1024**3,
            wall_seconds=570, consume=consume, decoder_memory_bytes=256 * 1024**2,
        )
        verify_materialization_transport(spec["source_integrity_receipt"], transport)
        header = write_cache(profile, output,
            lambda done, total: emit({"stage": "samples", "entities_done": done,
                                      "entities_total": total}))
    except BaseException as error:
        failure = {"type": type(error).__name__}
    finally:
        signal.alarm(0)
    emit({"stage": "terminal", "report": {
        "schema": "memory_policy_heldout_materialize_v1",
        "complete": failure is None,
        "failure": failure,
        "transport": transport,
        "header": header,
        "spec": spec,
        "elapsed_seconds": time.monotonic() - start,
        "fits": 0,
        "provider_calls": 0,
        "raw_rows_exported": 0,
        "role": spec["role"],
        "controller_access": False,
        "preflight_receipt_reproduced": failure is None,
    }})


if __name__ == "__main__":
    run(SPEC)
