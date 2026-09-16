#!/usr/bin/env python3
"""Bounded prospective Sportradar NFL Push Events capture.

The recorder preserves provider bytes and local receive clocks separately.  It
does not call a historical endpoint, infer an SLA, score a model, or claim
market lead.  A preflight checks entitlement without following the signed
stream redirect; capture is a separate explicit action with no auto-retry.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any, Iterable
import urllib.error
import urllib.parse
import urllib.request


BASE = "https://api.sportradar.com/nfl/official/{access}/stream/en/events/subscribe"
SCHEMA = "sportradar_nfl_push_canary_v1"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def utc(ns: int | None = None) -> str:
    value = time.time_ns() if ns is None else ns
    return datetime.fromtimestamp(value / 1e9, timezone.utc).isoformat()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_key(env_file: Path) -> str:
    value = os.environ.get("SPORTRADAR_API_KEY", "").strip()
    if not value and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("SPORTRADAR_API_KEY="):
                value = line.split("=", 1)[1].strip()
                break
    if not value:
        raise RuntimeError("SPORTRADAR_API_KEY unavailable")
    return value


def request(access: str, key: str, status: str = "inprogress") -> urllib.request.Request:
    if access not in {"trial", "production"} or status not in {"inprogress", "created"}:
        raise ValueError("bounded access/status required")
    url = BASE.format(access=access) + "?" + urllib.parse.urlencode({"status": status})
    return urllib.request.Request(url, headers={"accept": "application/json", "x-api-key": key})


def preflight(access: str, key: str, timeout: float = 20.0) -> tuple[dict[str, Any], str | None]:
    """Check stream entitlement once; never persist a signed redirect URL."""
    sent_ns = time.time_ns()
    try:
        response = urllib.request.build_opener(NoRedirect).open(
            request(access, key), timeout=timeout)
        status, headers = response.status, response.headers
        response.close()
    except urllib.error.HTTPError as error:
        status, headers = error.code, error.headers
    received_ns = time.time_ns()
    location = headers.get("Location")
    parsed = urllib.parse.urlparse(location) if location else None
    receipt = {
        "schema": "sportradar_push_entitlement_preflight_v1",
        "access": access,
        "http_status": status,
        "request_sent_utc": utc(sent_ns),
        "response_received_utc": utc(received_ns),
        "round_trip_ms": (received_ns - sent_ns) / 1e6,
        "redirect_present": bool(location),
        "redirect_scheme": parsed.scheme if parsed else "",
        "redirect_host": parsed.hostname if parsed else "",
        "stream_entitlement_observed": bool(
            status in {301, 302, 303, 307, 308} and parsed and parsed.scheme == "https"),
        "api_key_persisted": False,
        "signed_redirect_persisted": False,
        "provider_sla_proven": False,
        "market_lead_proven": False,
    }
    return receipt, location


def objects(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from objects(child)


def payload_summary(value: Any) -> dict[str, Any]:
    rows = list(objects(value))
    plays = [row for row in rows if row.get("type") == "play" or (
        "created_at" in row and "clock" in row and "sequence" in row)]
    timestamps = [str(row["created_at"]) for row in plays if row.get("created_at")]
    return {
        "object_count": len(rows),
        "play_objects": len(plays),
        "play_created_at": len(timestamps),
        "play_updated_at": sum(bool(row.get("updated_at")) for row in plays),
        "play_wall_clock": sum(bool(row.get("wall_clock")) for row in plays),
        "review_fields": sum(any(key in row for key in ("review", "reversed", "official", "overturned"))
                             for row in plays),
        "entry_modes": sorted({str(row["entry_mode"]) for row in rows if row.get("entry_mode")}),
        "game_ids": sorted({str(row["id"]) for row in rows
                            if row.get("id") and row.get("status") in {"inprogress", "created"}}),
        "created_at_values": timestamps,
    }


def capture_lines(lines: Iterable[bytes], raw_path: Path, receipt_path: Path,
                  maximum_messages: int, receive_clock=time.time_ns,
                  monotonic_clock=time.monotonic_ns) -> dict[str, Any]:
    if maximum_messages <= 0:
        raise ValueError("positive message bound required")
    counts, games, entry_modes = Counter(), set(), set()
    prior_monotonic = None
    with raw_path.open("xb") as raw, receipt_path.open("x", encoding="utf-8") as receipts:
        for index, line in enumerate(lines):
            if index >= maximum_messages:
                break
            received_ns, monotonic_ns = receive_clock(), monotonic_clock()
            body = line.rstrip(b"\r\n")
            if not body:
                continue
            raw.write(body + b"\n"); raw.flush(); os.fsync(raw.fileno())
            row = {
                "sequence": counts["messages"] + 1,
                "local_receive_utc": utc(received_ns),
                "local_receive_unix_ns": received_ns,
                "local_monotonic_ns": monotonic_ns,
                "raw_sha256": sha256_bytes(body),
                "raw_bytes": len(body),
                "receive_monotonic": prior_monotonic is None or monotonic_ns >= prior_monotonic,
            }
            prior_monotonic = monotonic_ns
            try:
                summary = payload_summary(json.loads(body))
                row["parse_ok"] = True
                row["summary"] = {key: value for key, value in summary.items()
                                  if key != "created_at_values"}
                counts["play_objects"] += summary["play_objects"]
                counts["play_created_at"] += summary["play_created_at"]
                counts["review_fields"] += summary["review_fields"]
                games.update(summary["game_ids"]); entry_modes.update(summary["entry_modes"])
            except (UnicodeDecodeError, json.JSONDecodeError):
                row["parse_ok"] = False
                counts["parse_errors"] += 1
            receipts.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
            receipts.flush(); os.fsync(receipts.fileno())
            counts["messages"] += 1
            if not row["receive_monotonic"]:
                counts["receive_monotonicity_violations"] += 1
    return {"counts": dict(counts), "distinct_games": len(games),
            "entry_modes": sorted(entry_modes)}


def run_capture(output: Path, access: str, key: str, maximum_messages: int,
                maximum_seconds: int, timeout: float) -> dict[str, Any]:
    if output.exists() or maximum_seconds <= 0:
        raise ValueError("fresh output and positive time bound required")
    output.mkdir(parents=True, mode=0o700)
    entitlement, location = preflight(access, key, timeout)
    (output / "entitlement.json").write_text(json.dumps(entitlement, sort_keys=True) + "\n")
    if not entitlement["stream_entitlement_observed"] or not location:
        return entitlement
    parsed = urllib.parse.urlparse(location)
    if parsed.scheme != "https":
        raise RuntimeError("HTTPS stream redirect required")
    started = time.monotonic()
    stream_request = urllib.request.Request(location, headers={"x-api-key": key})
    with urllib.request.urlopen(stream_request, timeout=min(timeout, maximum_seconds)) as response:
        def bounded_lines():
            for line in response:
                if time.monotonic() - started > maximum_seconds:
                    break
                yield line
        summary = capture_lines(bounded_lines(), output / "raw.ndjson",
                                output / "receipts.jsonl", maximum_messages)
    manifest = {
        "schema": SCHEMA,
        "source": "sportradar_nfl_push_events",
        "access": access,
        "started_utc": entitlement["request_sent_utc"],
        "ended_utc": utc(),
        "bounds": {"maximum_messages": maximum_messages,
                   "maximum_seconds": maximum_seconds, "automatic_retry": False},
        "summary": summary,
        "files": {
            "raw.ndjson": file_sha256(output / "raw.ndjson"),
            "receipts.jsonl": file_sha256(output / "receipts.jsonl"),
            "entitlement.json": file_sha256(output / "entitlement.json"),
        },
        "api_key_persisted": False,
        "signed_redirect_persisted": False,
        "historical_backfill": False,
        "provider_sla_proven": False,
        "market_lead_proven": False,
        "model_score_computed": False,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, sort_keys=True) + "\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--access", choices=("trial", "production"), default="trial")
    parser.add_argument("--maximum-messages", type=int, default=300)
    parser.add_argument("--maximum-seconds", type=int, default=7200)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    key = load_key(args.env_file)
    if args.preflight_only:
        receipt, _ = preflight(args.access, key, args.timeout)
        if args.output.exists():
            raise ValueError("fresh output required")
        args.output.mkdir(parents=True, mode=0o700)
        (args.output / "entitlement.json").write_text(json.dumps(receipt, sort_keys=True) + "\n")
        print(json.dumps(receipt, sort_keys=True))
        return 0 if receipt["stream_entitlement_observed"] else 2
    result = run_capture(args.output, args.access, key, args.maximum_messages,
                         args.maximum_seconds, args.timeout)
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("schema") == SCHEMA else 2


if __name__ == "__main__":
    raise SystemExit(main())
