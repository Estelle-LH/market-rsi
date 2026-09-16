"""Bind materialization to a complete semantic-preflight receipt."""
from __future__ import annotations

from sealed_jsonl_integrity import verify_materialization_transport


SEMANTIC_FIELDS = (
    "raw_records",
    "excluded_kind_messages",
    "price_change_messages",
    "selected_observations",
    "entities",
    "selected_source_regressions",
    "entities_with_source_regression",
    "last_attempted_record",
)
SEMANTIC_KEYS = set(SEMANTIC_FIELDS) | {
    "schema",
    "message_selection_kernel",
    "summary_or_cache_called",
    "target_statistics_computed",
    "raw_rows_exported",
    "fits",
    "provider_calls",
}


def structural_receipt(report):
    """Convert the semantic scan transport into the frozen structural identity."""
    transport = report.get("transport") or {}
    semantic = report.get("semantic_receipt") or {}
    if (report.get("complete") is not True
            or transport.get("complete") is not True
            or set(semantic) != SEMANTIC_KEYS
            or semantic.get("schema") != "memory_policy_semantic_receipt_v1"
            or semantic.get("message_selection_kernel") != "CacheProfile.consume"
            or semantic.get("summary_or_cache_called") is not False
            or semantic.get("target_statistics_computed") != 0
            or semantic.get("raw_rows_exported") != 0
            or semantic.get("fits") != 0
            or semantic.get("provider_calls") != 0
            or any(type(semantic.get(field)) is not int
                   or semantic[field] < 0 for field in SEMANTIC_FIELDS)
            or semantic["selected_observations"] <= 0
            or semantic["entities"] <= 0
            or semantic["last_attempted_record"] != transport.get("decoded_records")):
        raise ValueError("complete score-free semantic receipt required")
    return {
        "schema": "sealed_jsonl_integrity_v1",
        "complete": True,
        "failure_type": None,
        "compressed_bytes": transport["compressed_bytes_read"],
        "compressed_sha256": transport["compressed_sha256"],
        "decoded_bytes": transport["decoded_bytes"],
        "decoded_sha256": transport["decoded_sha256"],
        "json_object_records": transport["decoded_records"],
        "source_initial_stat": transport["source_initial_stat"],
        "source_unchanged_verified": transport["source_unchanged_verified"],
        "decoder_exit_code": transport["decoder_exit_code"],
        "decoder_reaped": transport["decoder_reaped"],
        "feeder_reaped": transport["feeder_reaped"],
        "raw_rows_exported": 0,
        "target_statistics_computed": 0,
        "fits": 0,
        "provider_calls": 0,
        "partial_diagnostic_only": False,
    }


def observed_semantics(profile):
    regressions = sum(series.gaps.get("negative", 0)
                      for series in profile.entities.values())
    rejected = sum(bool(series.gaps.get("negative", 0))
                   for series in profile.entities.values())
    return {
        "raw_records": int(profile.counts.get("raw_records", 0)),
        "excluded_kind_messages": int(
            profile.counts.get("excluded_kind_messages", 0)),
        "price_change_messages": int(
            profile.counts.get("price_change_messages", 0)),
        "selected_observations": int(
            profile.counts.get("selected_observations", 0)),
        "entities": len(profile.entities),
        "selected_source_regressions": int(regressions),
        "entities_with_source_regression": int(rejected),
        "last_attempted_record": int(profile.last_ordinal),
    }


def verify_semantic_materialization(report, transport, profile):
    """Require both byte identity and exact selection-state reproduction."""
    verify_materialization_transport(structural_receipt(report), transport)
    expected = report["semantic_receipt"]
    observed = observed_semantics(profile)
    if observed != {field: expected.get(field) for field in SEMANTIC_FIELDS}:
        raise ValueError("materialization differs from semantic preflight")
    return True
