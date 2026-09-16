"""Remote source admission using the exact frozen materializer selection kernel.

This reads one whole JSONL.zst object and applies CacheProfile.consume to every
record.  It deliberately does not call summary() or write_cache(): no labels,
prediction metrics, or model-visible rows are produced before the experiment.
"""
import json
import os
import resource
import signal
import time

try:
    from memory_materialize import CacheProfile
except ModuleNotFoundError:  # Local tests; remote program binds the isolated alias.
    from memory_pilot.materialize import CacheProfile
from single_object_stream import stream_object


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
    "no selected observations",
}


def bounded_failure(error):
    message = str(error)
    return {
        "type": type(error).__name__,
        "reason": message if message in KNOWN_FAILURES else "unexpected_failure",
    }


def validate_policy(policy):
    expected = {
        "parent_address_space_bytes": 4 * 1024**3,
        "decoder_address_space_bytes": 256 * 1024**2,
        "max_decoded_bytes": 4 * 1024**3,
        "max_entities": 10000,
        "max_total_observations": 12000000,
        "max_entity_observations": 200000,
        "remote_wall_seconds": 570,
    }
    if policy != expected:
        raise ValueError("exact semantic preflight policy required")
    return policy


def run(spec):
    policy = validate_policy(spec["resource_policy"])
    resource.setrlimit(resource.RLIMIT_AS, (
        policy["parent_address_space_bytes"], policy["parent_address_space_bytes"]
    ))

    def stop(*_):
        raise TimeoutError("semantic source preflight deadline")

    signal.signal(signal.SIGALRM, stop)
    signal.signal(signal.SIGTERM, stop)
    signal.alarm(policy["remote_wall_seconds"] + 10)
    started = time.monotonic()
    failure = transport = consumer_failure = None
    profile = CacheProfile(
        spec["contract"], spec["day_start_ms"],
        max_entities=policy["max_entities"],
        max_total_rows=policy["max_total_observations"],
        max_entity_rows=policy["max_entity_observations"],
    )

    def emit(value):
        print(json.dumps(value, sort_keys=True, allow_nan=False), flush=True)

    emit({
        "stage": "started", "pid": os.getpid(), "session": spec["session"],
        "role": spec["role"], "target_statistics_computed": 0,
    })

    def consume(line, ordinal):
        nonlocal consumer_failure
        try:
            profile.consume(line, ordinal)
        except BaseException as error:
            consumer_failure = {
                **bounded_failure(error),
                "ordinal": ordinal,
                "selected_observations_before_failure": int(
                    profile.counts.get("selected_observations", 0)),
            }
            raise
        if ordinal % 100000 == 0:
            emit({
                "stage": "decode", "records": ordinal,
                "selected_observations": int(
                    profile.counts.get("selected_observations", 0)),
                "elapsed_seconds": time.monotonic() - started,
            })

    try:
        transport = stream_object(
            spec["path"], advertised_bytes=spec["compressed_bytes"],
            max_input_bytes=spec["compressed_bytes"],
            max_decoded_bytes=policy["max_decoded_bytes"],
            wall_seconds=policy["remote_wall_seconds"], consume=consume,
            decoder_memory_bytes=policy["decoder_address_space_bytes"],
        )
        if not transport["complete"]:
            raise ValueError("incomplete source transport")
        if not profile.counts.get("selected_observations"):
            raise ValueError("no selected observations")
    except BaseException as error:
        failure = bounded_failure(error)
    finally:
        signal.alarm(0)

    regressions = sum(series.gaps.get("negative", 0)
                      for series in profile.entities.values())
    rejected_entities = sum(bool(series.gaps.get("negative", 0))
                            for series in profile.entities.values())
    semantic_receipt = {
        "schema": "memory_policy_semantic_receipt_v1",
        "raw_records": int(profile.counts.get("raw_records", 0)),
        "excluded_kind_messages": int(
            profile.counts.get("excluded_kind_messages", 0)),
        "price_change_messages": int(
            profile.counts.get("price_change_messages", 0)),
        "selected_observations": int(
            profile.counts.get("selected_observations", 0)),
        "entities": len(profile.entities),
        "selected_source_regressions": int(regressions),
        "entities_with_source_regression": int(rejected_entities),
        "last_attempted_record": int(profile.last_ordinal),
        "message_selection_kernel": "CacheProfile.consume",
        "summary_or_cache_called": False,
        "target_statistics_computed": 0,
        "raw_rows_exported": 0,
        "fits": 0,
        "provider_calls": 0,
    }
    emit({"stage": "terminal", "report": {
        "schema": "memory_policy_semantic_preflight_worker_v1",
        "complete": failure is None,
        "failure": failure,
        "consumer_failure": consumer_failure,
        "session": spec["session"],
        "role": spec["role"],
        "advertised_bytes": spec["compressed_bytes"],
        "transport": transport,
        "semantic_receipt": semantic_receipt,
        "resource_policy": policy,
        "elapsed_seconds": time.monotonic() - started,
        "raw_rows_exported": 0,
        "target_statistics_computed": 0,
        "fits": 0,
        "provider_calls": 0,
    }})


if __name__ == "__main__":
    run(SPEC)
