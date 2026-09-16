"""One recovery materialization under an explicit larger total-row envelope."""
import json
import os
from pathlib import Path
import resource
import signal
import time

try:
    from memory_materialize import CacheProfile, write_cache
except ModuleNotFoundError:  # Local tests; remote worker receives the isolated alias.
    from memory_pilot.materialize import CacheProfile, write_cache
from sealed_jsonl_integrity import verify_materialization_transport
from single_object_stream import stream_object
from market_rsi import fresh_json


KNOWN_CONSUMER_FAILURES = {
    "raw order invalid",
    "raw object required",
    "wrapper outside allowed day",
    "message object required",
    "selected source timestamp outside declared day; no silent filtering",
    "changes or market identity missing",
    "change object required",
    "asset identity missing",
    "entity resource limit",
    "asset market identity discontinuity",
    "row resource limit; no silent truncation",
    "spread routing/count parity failure",
}


def safe_failure(error):
    """Return a fixed-category failure without raw source text or identifiers."""
    message = str(error)
    return {
        "type": type(error).__name__,
        "reason": message if message in KNOWN_CONSUMER_FAILURES else "unexpected_failure",
    }


def validate_limits(limits):
    expected = {
        "parent_address_space_bytes": 4 * 1024**3,
        "decoder_address_space_bytes": 256 * 1024**2,
        "max_decoded_bytes": 4 * 1024**3,
        "max_entities": 10000,
        "max_total_observations": 12000000,
        "max_entity_observations": 200000,
        "remote_wall_seconds": 1120,
        "remote_process_seconds": 1200,
        "local_transport_seconds": 1230,
    }
    if limits != expected:
        raise ValueError("exact reviewed recovery resource policy required")
    return limits


def run(spec):
    limits = validate_limits(spec["resource_policy"])
    resource.setrlimit(resource.RLIMIT_AS, (
        limits["parent_address_space_bytes"], limits["parent_address_space_bytes"]
    ))

    def stop(*_):
        raise TimeoutError("recovery materialization deadline")

    signal.signal(signal.SIGALRM, stop)
    signal.signal(signal.SIGTERM, stop)
    signal.alarm(limits["remote_wall_seconds"] + 30)
    start = time.monotonic()
    failure = None
    consume_failure = None
    transport = header = None
    profile = CacheProfile(
        spec["contract"], spec["day_start_ms"],
        max_entities=limits["max_entities"],
        max_total_rows=limits["max_total_observations"],
        max_entity_rows=limits["max_entity_observations"],
    )
    output = Path(spec["output"])
    output.parent.mkdir(parents=True, exist_ok=True)
    fresh_json(output.with_suffix(".claim.json"), {"spec": spec, "pid": os.getpid()})

    def emit(value):
        print(json.dumps(value, sort_keys=True, allow_nan=False), flush=True)

    emit({"stage": "started", "pid": os.getpid(), "date": spec["date"],
          "role": spec["role"]})

    def consume(line, ordinal):
        nonlocal consume_failure
        try:
            profile.consume(line, ordinal)
        except BaseException as error:
            consume_failure = {**safe_failure(error), "ordinal": ordinal,
                "selected_observations_before_failure":
                    int(profile.counts.get("selected_observations", 0))}
            raise
        if ordinal % 100000 == 0:
            emit({"stage": "decode", "records": ordinal,
                  "selected_observations":
                      int(profile.counts.get("selected_observations", 0)),
                  "elapsed_seconds": time.monotonic() - start})

    try:
        transport = stream_object(
            spec["path"], advertised_bytes=spec["compressed_bytes"],
            max_input_bytes=spec["compressed_bytes"],
            max_decoded_bytes=limits["max_decoded_bytes"],
            wall_seconds=limits["remote_wall_seconds"], consume=consume,
            decoder_memory_bytes=limits["decoder_address_space_bytes"],
        )
        verify_materialization_transport(spec["source_integrity_receipt"], transport)
        header = write_cache(profile, output,
            lambda done, total: emit({"stage": "samples", "entities_done": done,
                                      "entities_total": total}))
    except BaseException as error:
        failure = safe_failure(error)
    finally:
        signal.alarm(0)

    emit({"stage": "terminal", "report": {
        "schema": "memory_policy_final_recovery_materialize_v1",
        "complete": failure is None,
        "failure": failure,
        "consumer_failure": consume_failure,
        "last_attempted_record": profile.last_ordinal,
        "selected_observations": int(profile.counts.get("selected_observations", 0)),
        "transport": transport,
        "header": header,
        "spec": spec,
        "elapsed_seconds": time.monotonic() - start,
        "peak_self_rss_kib_linux": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "resource_policy": limits,
        "fits": 0,
        "provider_calls": 0,
        "raw_rows_exported": 0,
        "role": spec["role"],
        "controller_access": False,
        "preflight_receipt_reproduced": failure is None,
    }})


if __name__ == "__main__":
    run(SPEC)
