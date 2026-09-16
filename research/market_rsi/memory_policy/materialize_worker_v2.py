"""Materialize one source only if it reproduces its semantic-preflight receipt."""
import json
import os
from pathlib import Path
import resource
import signal
import time

try:
    from memory_materialize import CacheProfile, write_cache
except ModuleNotFoundError:  # Local tests; remote program binds the isolated alias.
    from memory_pilot.materialize import CacheProfile, write_cache
try:
    from semantic_binding import verify_semantic_materialization
except ModuleNotFoundError:  # Local tests; remote program binds the isolated alias.
    from memory_policy.semantic_binding import verify_semantic_materialization
from single_object_stream import stream_object
from market_rsi import fresh_json


KNOWN_FAILURES = {
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
    "materialization differs from semantic preflight",
    "materialized source differs from structural preflight",
}


def bounded_failure(error):
    message = str(error)
    return {"type": type(error).__name__,
            "reason": message if message in KNOWN_FAILURES else "unexpected_failure"}


def validate_policy(policy):
    expected = {
        "parent_address_space_bytes": 4 * 1024**3,
        "decoder_address_space_bytes": 256 * 1024**2,
        "max_decoded_bytes": 4 * 1024**3,
        "max_entities": 10000,
        "max_total_observations": 12000000,
        "max_entity_observations": 200000,
        "remote_wall_seconds": 2100,
        "remote_process_seconds": 2180,
        "local_transport_seconds": 2220,
    }
    if policy != expected:
        raise ValueError("exact v2 materialization policy required")
    return policy


def run(spec):
    policy = validate_policy(spec["resource_policy"])
    resource.setrlimit(resource.RLIMIT_AS, (
        policy["parent_address_space_bytes"], policy["parent_address_space_bytes"]
    ))

    def stop(*_):
        raise TimeoutError("v2 materialization deadline")

    signal.signal(signal.SIGALRM, stop)
    signal.signal(signal.SIGTERM, stop)
    signal.alarm(policy["remote_wall_seconds"] + 30)
    started = time.monotonic()
    failure = consumer_failure = None
    transport = header = None
    profile = CacheProfile(
        spec["contract"], spec["day_start_ms"],
        max_entities=policy["max_entities"],
        max_total_rows=policy["max_total_observations"],
        max_entity_rows=policy["max_entity_observations"],
    )
    output = Path(spec["output"])
    output.parent.mkdir(parents=True, exist_ok=True)
    fresh_json(output.with_suffix(".claim.json"), {"spec": spec, "pid": os.getpid()})

    def emit(value):
        print(json.dumps(value, sort_keys=True, allow_nan=False), flush=True)

    emit({"stage": "started", "pid": os.getpid(), "date": spec["date"],
          "role": spec["role"]})

    def consume(line, ordinal):
        nonlocal consumer_failure
        try:
            profile.consume(line, ordinal)
        except BaseException as error:
            consumer_failure = {
                **bounded_failure(error), "ordinal": ordinal,
                "selected_observations_before_failure": int(
                    profile.counts.get("selected_observations", 0)),
            }
            raise
        if ordinal % 100000 == 0:
            emit({"stage": "decode", "records": ordinal,
                  "selected_observations": int(
                      profile.counts.get("selected_observations", 0)),
                  "elapsed_seconds": time.monotonic() - started})

    try:
        transport = stream_object(
            spec["path"], advertised_bytes=spec["compressed_bytes"],
            max_input_bytes=spec["compressed_bytes"],
            max_decoded_bytes=policy["max_decoded_bytes"],
            wall_seconds=policy["remote_wall_seconds"], consume=consume,
            decoder_memory_bytes=policy["decoder_address_space_bytes"],
        )
        verify_semantic_materialization(
            spec["semantic_preflight_report"], transport, profile)
        header = write_cache(profile, output,
            lambda done, total: emit({"stage": "samples", "entities_done": done,
                                      "entities_total": total}))
    except BaseException as error:
        failure = bounded_failure(error)
    finally:
        signal.alarm(0)

    emit({"stage": "terminal", "report": {
        "schema": "memory_policy_materialize_v2",
        "complete": failure is None,
        "failure": failure,
        "consumer_failure": consumer_failure,
        "last_attempted_record": profile.last_ordinal,
        "selected_observations": int(
            profile.counts.get("selected_observations", 0)),
        "transport": transport,
        "header": header,
        "spec": spec,
        "elapsed_seconds": time.monotonic() - started,
        "peak_self_rss_kib_linux": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "resource_policy": policy,
        "fits": 0,
        "provider_calls": 0,
        "raw_rows_exported": 0,
        "role": spec["role"],
        "semantic_preflight_reproduced": failure is None,
    }})


if __name__ == "__main__":
    run(SPEC)
