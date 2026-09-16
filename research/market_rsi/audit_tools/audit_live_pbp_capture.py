#!/usr/bin/env python3
"""Audit live play-by-play capture clocks without scoring a prediction model.

The report is aggregate-only. In particular, provider event wallclock to local
receive is named as a descriptive lag, never as publish-to-receive latency.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import gzip
import hashlib
import json
import math
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _open_text(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open("r", encoding="utf-8")


def _milliseconds(value: object) -> int | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)
    except ValueError:
        return None


def _number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _quantile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return float(ordered[lower])
    weight = position - lower
    return float(ordered[lower] * (1 - weight) + ordered[upper] * weight)


def distribution(values: list[float]) -> dict:
    return {
        "n": len(values),
        "minimum": min(values) if values else None,
        "p50": _quantile(values, 0.50),
        "p90": _quantile(values, 0.90),
        "p99": _quantile(values, 0.99),
        "maximum": max(values) if values else None,
    }


def audit(path: Path, expected_sha256: str, evidence_status: str) -> dict:
    actual_sha256 = sha256_file(path)
    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"source SHA256 mismatch: expected {expected_sha256}, got {actual_sha256}"
        )

    record_types: Counter[str] = Counter()
    modes: Counter[str] = Counter()
    row_hashes: set[str] = set()
    games: set[str] = set()
    live_play_ids: set[str] = set()
    duplicate_rows = 0
    duplicate_live_play_ids = 0
    parse_failures = 0
    receive_monotonicity_violations = 0
    previous_receive_ms: int | None = None
    live_lags: list[float] = []
    scoring_lags: list[float] = []
    http_rtts: list[float] = []
    live_provider_clock = 0
    live_local_receive = 0
    live_provider_publish = 0
    live_state_pair = 0
    live_win_probability = 0
    correction_or_overturn_rows = 0
    correction_schema_rows = 0
    raw_rows = 0

    with _open_text(path) as handle:
        for line in handle:
            raw_rows += 1
            encoded = line.rstrip("\n").encode("utf-8")
            row_hash = hashlib.sha256(encoded).hexdigest()
            duplicate_rows += row_hash in row_hashes
            row_hashes.add(row_hash)
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                parse_failures += 1
                continue
            if not isinstance(row, dict):
                parse_failures += 1
                continue

            record_types[str(row.get("record_type") or "missing")] += 1
            mode = str(row.get("observation_mode") or "missing")
            modes[mode] += 1
            if row.get("event_id") is not None:
                games.add(str(row["event_id"]))
            receive_ms = _milliseconds(row.get("capture_received_utc"))
            if receive_ms is not None:
                if previous_receive_ms is not None and receive_ms < previous_receive_ms:
                    receive_monotonicity_violations += 1
                previous_receive_ms = receive_ms
            rtt = _number(row.get("http_rtt_ms"))
            if rtt is not None:
                http_rtts.append(rtt)

            if mode != "live_delta":
                continue
            play_id = str(row.get("play_id") or "")
            if play_id:
                duplicate_live_play_ids += play_id in live_play_ids
                live_play_ids.add(play_id)
            event_ms = _milliseconds(row.get("provider_wallclock"))
            live_provider_clock += event_ms is not None
            live_local_receive += receive_ms is not None
            if any(row.get(key) is not None for key in (
                "provider_published_utc", "provider_published_ts_ms", "published_at"
            )):
                live_provider_publish += 1
            if event_ms is not None and receive_ms is not None:
                lag = float(receive_ms - event_ms)
                live_lags.append(lag)
                if bool(row.get("scoring_play")):
                    scoring_lags.append(lag)
            if all(row.get(key) is not None for key in ("start_state", "end_state")):
                live_state_pair += 1
            if any(row.get(key) is not None for key in (
                "home_win_probability", "away_win_probability", "win_probability",
                "start_win_probability", "end_win_probability"
            )):
                live_win_probability += 1
            correction_keys = ("correction", "corrected", "overturn", "overturned")
            correction_schema_rows += any(key in row for key in correction_keys)
            if any(row.get(key) not in (None, False, "", "none") for key in (
                "correction", "corrected", "overturn", "overturned"
            )):
                correction_or_overturn_rows += 1

    live_rows = modes.get("live_delta", 0)
    result = {
        "schema": "live_pbp_capture_audit_v1",
        "evidence_status": evidence_status,
        "source": {
            "basename": path.name,
            "sha256": actual_sha256,
            "immutable_source_verified": True,
        },
        "counts": {
            "raw_rows": raw_rows,
            "parse_failures": parse_failures,
            "duplicate_full_rows": duplicate_rows,
            "record_types": dict(sorted(record_types.items())),
            "observation_modes": dict(sorted(modes.items())),
            "distinct_games": len(games),
            "live_delta_rows": live_rows,
            "distinct_live_play_ids": len(live_play_ids),
            "duplicate_live_play_ids": duplicate_live_play_ids,
            "receive_monotonicity_violations": receive_monotonicity_violations,
        },
        "clock_fields": {
            "live_delta_with_provider_event_start": live_provider_clock,
            "live_delta_with_local_receive": live_local_receive,
            "live_delta_with_provider_publish": live_provider_publish,
            "provider_clock_semantics": "event_start",
            "provider_publish_clock_observed": live_provider_publish > 0,
        },
        "provider_event_start_to_receive_descriptive_ms": distribution(live_lags),
        "scoring_event_start_to_receive_descriptive_ms": distribution(scoring_lags),
        "http_round_trip_descriptive_ms": distribution(http_rtts),
        "feature_fields": {
            "live_delta_with_start_and_end_state": live_state_pair,
            "live_delta_with_win_probability": live_win_probability,
            "live_delta_with_correction_schema": correction_schema_rows,
            "correction_or_overturn_rows": correction_or_overturn_rows,
        },
        "claim_boundaries": {
            "event_start_to_receive_is_publish_to_receive_latency": False,
            "raw_capture_mechanical_integrity_observed": (
                raw_rows > 0 and parse_failures == 0 and live_rows > 0
                and live_local_receive == live_rows
            ),
            "capture_integrity_proven": False,
            "strict_feed_latency_proven": False,
            "state_wp_delta_live_materialization_proven": (
                live_rows > 0 and live_state_pair == live_rows
                and live_win_probability == live_rows
            ),
            "market_lead_proven": False,
            "predictive_improvement_proven": False,
            "independent_confirmation": False,
        },
        "data_access": {
            "train_opened": False,
            "dev_opened": False,
            "final_opened": False,
            "prediction_fit_run": False,
            "provider_cost_usd": 0.0,
        },
        "identifiers_exported": False,
    }
    result["report_sha256"] = hashlib.sha256(json.dumps(
        result, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--evidence-status", choices=(
        "post_hoc_existing_case", "prospective_unopened_capture"
    ), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.input, args.expected_sha256, args.evidence_status)
    args.output.parent.mkdir(parents=True, exist_ok=False)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
