"""Deterministic, provenance-preserving compression of an own-arm archive."""
from __future__ import annotations

from market_rsi import canonical, digest


def _records_by_id(records):
    return {f"{record['index']:04d}": record for record in records}


def _interpretations(records):
    return {record["args"]["trial_id"]: record["args"]
            for record in records
            if record.get("tool") == "interpret_result" and record.get("error") is None}


def compact_round(item):
    """Keep decisions and measured evidence; omit raw browsing/tool transcript."""
    records = item["records"]
    by_id = _records_by_id(records)
    interpreted = _interpretations(records)
    candidates = []
    for record in records:
        if record.get("tool") != "train_candidate":
            continue
        args = record["args"]
        research = by_id.get(args["research_record"], {})
        candidates.append({
            "trial_id": args["trial_id"],
            "parent_trial_id": args["parent_trial_id"],
            "question": args["question"],
            "hypothesis": args["hypothesis"],
            "support_criterion": args["support_criterion"],
            "refute_criterion": args["refute_criterion"],
            "research_note": research.get("args", {}).get("note"),
            "outcome": record.get("result"),
            "error": record.get("error"),
            "interpretation": interpreted.get(args["trial_id"]),
            "record_sha256": record["sha256"],
        })
    protocol_errors = [record["args"]["message"] for record in records
                       if record.get("tool") == "report_protocol_error"
                       and record.get("error") is None]
    compact = {
        "round": item["round"],
        "submission": item["submission"],
        "own_dev": item["own_dev"],
        "common_baseline_dev": item["common_baseline_dev"],
        "cost": item["cost"],
        "candidates": candidates,
        "protocol_errors": protocol_errors,
        "full_round_sha256": digest(item),
        "terminal_record_sha256": records[-1]["sha256"] if records else None,
    }
    return compact


def compact_archive(history):
    result = {
        "schema": "controller_compact_archive_v1",
        "rounds": [compact_round(item) for item in history],
        "compression": "deterministic; decisions and measured evidence only",
        "raw_external_pages_retained": False,
        "hidden_reasoning_retained": False,
    }
    result["archive_sha256"] = digest(result)
    return result


def memory_payload(mode, history):
    if mode == "fresh":
        return []
    if mode == "archive":
        return history
    if mode == "compact":
        return compact_archive(history)
    raise ValueError("unknown memory mode")


def payload_size(mode, history):
    return len(canonical(memory_payload(mode, history)))
