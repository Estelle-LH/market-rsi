"""Fail-closed structural admission for one immutable JSONL.zst source.

This layer deliberately learns nothing about markets.  It fully reads the
compressed object once, hashes both byte streams, and parses every decoded
record as a JSON object.  Its receipt contains identity and completeness
metadata only; it never exports source rows or target statistics.
"""
from __future__ import annotations

import json
from pathlib import Path

from single_object_stream import stream_object


def inspect_jsonl_zst(path, *, advertised_bytes, max_input_bytes,
                      max_decoded_bytes, wall_seconds,
                      expected_compressed_sha256=None,
                      decoder_command=("zstd", "-dc"),
                      decoder_memory_bytes=None):
    """Return a content-blind integrity receipt for one compressed source."""
    parsed_records = 0

    def consume(line, ordinal):
        nonlocal parsed_records
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError("each source record must be a JSON object")
        parsed_records = ordinal

    transport = stream_object(
        Path(path), advertised_bytes=advertised_bytes,
        max_input_bytes=max_input_bytes,
        max_decoded_bytes=max_decoded_bytes,
        wall_seconds=wall_seconds, consume=consume,
        decoder_command=decoder_command,
        decoder_memory_bytes=decoder_memory_bytes,
    )
    failure = transport["failure_type"]
    complete = bool(transport["complete"] and parsed_records > 0)
    if complete and expected_compressed_sha256 is not None:
        if transport["compressed_sha256"] != expected_compressed_sha256:
            complete = False
            failure = "CompressedHashMismatch"
    if transport["complete"] and parsed_records == 0:
        failure = "EmptySource"
    return {
        "schema": "sealed_jsonl_integrity_v1",
        "complete": complete,
        "failure_type": failure,
        "compressed_bytes": transport["compressed_bytes_read"],
        "compressed_sha256": transport["compressed_sha256"],
        "decoded_bytes": transport["decoded_bytes"],
        "decoded_sha256": transport["decoded_sha256"],
        "json_object_records": parsed_records,
        "source_initial_stat": transport["source_initial_stat"],
        "source_unchanged_verified": transport["source_unchanged_verified"],
        "decoder_exit_code": transport["decoder_exit_code"],
        "decoder_reaped": transport["decoder_reaped"],
        "feeder_reaped": transport["feeder_reaped"],
        "raw_rows_exported": 0,
        "target_statistics_computed": 0,
        "fits": 0,
        "provider_calls": 0,
        "partial_diagnostic_only": not complete,
    }


def source_identity(receipt):
    """The fields a later materializer must reproduce before scoring."""
    if receipt.get("schema") != "sealed_jsonl_integrity_v1" or receipt.get("complete") is not True:
        raise ValueError("complete structural receipt required")
    return {
        "compressed_bytes": receipt["compressed_bytes"],
        "compressed_sha256": receipt["compressed_sha256"],
        "decoded_bytes": receipt["decoded_bytes"],
        "decoded_sha256": receipt["decoded_sha256"],
        "json_object_records": receipt["json_object_records"],
        "source_initial_stat": receipt["source_initial_stat"],
    }


def verify_materialization_transport(receipt, transport):
    """Bind the later full materialization pass to the admitted object."""
    expected = source_identity(receipt)
    observed = {
        "compressed_bytes": transport.get("compressed_bytes_read"),
        "compressed_sha256": transport.get("compressed_sha256"),
        "decoded_bytes": transport.get("decoded_bytes"),
        "decoded_sha256": transport.get("decoded_sha256"),
        "json_object_records": transport.get("decoded_records"),
        "source_initial_stat": transport.get("source_initial_stat"),
    }
    if transport.get("complete") is not True or observed != expected:
        raise ValueError("materialized source differs from structural preflight")
    return True
