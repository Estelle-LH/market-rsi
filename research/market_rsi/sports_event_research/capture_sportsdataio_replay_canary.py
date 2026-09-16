#!/usr/bin/env python3
"""Terms-gated, bounded capture of an operator-created SportsDataIO Replay.

This recorder is intentionally unable to discover, start, or purchase a Replay
session.  It only polls one operator-supplied HTTPS endpoint after an explicit
authorization receipt confirms that automated Replay polling and local raw
research storage are allowed for that exact endpoint.  It preserves provider
bytes and local clocks without assigning timestamp semantics, scoring a model,
opening protected evaluation data, or making latency/market-lead claims.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
from typing import Any, Callable, Iterable
import urllib.error
import urllib.parse
import urllib.request


SCHEMA = "sportsdataio_replay_capture_v1"
AUTH_SCHEMA = "sportsdataio_replay_authorization_v1"
ENDPOINT_SCHEMA = "sportsdataio_replay_endpoint_v1"
KEY_ENV = "SPORTSDATAIO_API_KEY"
KEY_HEADER = "Ocp-Apim-Subscription-Key"
MINIMUM_POLL_SECONDS = 3.0
MAXIMUM_POLLS = 10_000
MAXIMUM_RESPONSE_BYTES = 16 * 1024 * 1024
MAXIMUM_WORST_CASE_SECONDS = 24 * 60 * 60
MAXIMUM_CAPTURE_BYTES = 1024 * 1024 * 1024
AUTH_CONFIRMATION = (
    "I confirm this SportsDataIO account permits automated Replay polling "
    "and local raw research storage for the bound endpoint."
)
SENSITIVE_QUERY_TOKENS = {
    "apikey", "key", "token", "accesstoken", "authorization", "auth",
    "subscriptionkey", "ocpapimsubscriptionkey", "signature", "sig",
    "password", "credential", "secret",
}
CLOCK_TOKENS = {
    "time", "timestamp", "date", "datetime", "clock", "created", "updated",
    "modified", "published",
}
CORRECTION_TOKENS = {
    "review", "reviewed", "reversal", "reversed", "overturn", "overturned",
    "correction", "corrected", "official", "final", "closed", "updated", "modified",
}


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


def _protected_file(path: Path, label: str) -> bytes:
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{label} must be a regular local file")
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise ValueError(f"{label} must not be readable or writable by group/others")
    return path.read_bytes()


def load_endpoint(path: Path) -> tuple[str, bytes]:
    raw = _protected_file(path, "endpoint input")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("endpoint input must be JSON") from error
    if set(value) != {"schema", "url"} or value.get("schema") != ENDPOINT_SCHEMA:
        raise ValueError("exact endpoint input schema required")
    url = value.get("url")
    if not isinstance(url, str) or not url:
        raise ValueError("non-empty Replay endpoint URL required")
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.fragment or parsed.port not in {None, 443}):
        raise ValueError("bounded HTTPS SportsDataIO endpoint required")
    host = parsed.hostname.lower().rstrip(".")
    if host == "sportsdata.io" or not host.endswith(".sportsdata.io"):
        raise ValueError("endpoint host must be a SportsDataIO subdomain")
    query_keys = {re.sub(r"[^a-z0-9]", "", key.lower()) for key, _ in
                  urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)}
    if query_keys & SENSITIVE_QUERY_TOKENS:
        raise ValueError("credentials and signed authorization are forbidden in endpoint URL")
    return url, raw


def load_authorization(path: Path, endpoint_raw: bytes, host: str) -> tuple[dict[str, Any], str]:
    raw = _protected_file(path, "authorization receipt")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("authorization receipt must be JSON") from error
    required = {
        "schema", "provider", "authorization_source", "operator_confirmation",
        "automated_replay_polling_allowed", "raw_research_storage_allowed",
        "authorized_endpoint_sha256", "approved_hosts", "confirmed_utc",
    }
    if set(value) != required or value.get("schema") != AUTH_SCHEMA:
        raise ValueError("exact SportsDataIO authorization schema required")
    if (value.get("provider") != "SportsDataIO"
            or value.get("authorization_source") not in {
                "provider_account_terms", "provider_written_permission"}
            or value.get("operator_confirmation") != AUTH_CONFIRMATION
            or value.get("automated_replay_polling_allowed") is not True
            or value.get("raw_research_storage_allowed") is not True
            or value.get("authorized_endpoint_sha256") != sha256_bytes(endpoint_raw)):
        raise ValueError("Replay polling/storage authorization not established")
    hosts = value.get("approved_hosts")
    if (not isinstance(hosts, list) or not hosts or any(
            not isinstance(item, str) or item != item.lower().rstrip(".") for item in hosts)
            or host not in hosts or any(
                item == "sportsdata.io" or not item.endswith(".sportsdata.io") for item in hosts)):
        raise ValueError("exact approved SportsDataIO host required")
    try:
        confirmed = datetime.fromisoformat(str(value["confirmed_utc"]).replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("valid authorization confirmation time required") from error
    if confirmed.tzinfo is None:
        raise ValueError("timezone-aware authorization confirmation time required")
    return value, sha256_bytes(raw)


def load_key() -> str:
    key = os.environ.get(KEY_ENV, "").strip()
    if not key:
        raise RuntimeError(f"{KEY_ENV} unavailable")
    return key


def _pointer_token(value: Any) -> str:
    return str(value).replace("~", "~0").replace("/", "~1")


def scalar_fields(value: Any, path: str = "") -> Iterable[tuple[str, str, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            pointer = path + "/" + _pointer_token(key)
            if isinstance(child, (str, int, float, bool)) or child is None:
                yield pointer, str(key), child
            else:
                yield from scalar_fields(child, pointer)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            pointer = path + "/" + str(index)
            if isinstance(child, (str, int, float, bool)) or child is None:
                yield pointer, str(index), child
            else:
                yield from scalar_fields(child, pointer)


def field_tokens(key: str) -> set[str]:
    snake = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)
    return {token for token in re.split(r"[^A-Za-z0-9]+", snake.lower()) if token}


def payload_observations(value: Any) -> dict[str, list[dict[str, Any]]]:
    clock, correction = [], []
    for pointer, key, scalar in scalar_fields(value):
        row = {"json_pointer": pointer, "field_name": key, "value": scalar}
        tokens = field_tokens(key)
        if tokens & CLOCK_TOKENS:
            clock.append(row)
        if tokens & CORRECTION_TOKENS:
            correction.append(row)
    return {"clock_fields_verbatim": clock, "correction_fields_verbatim": correction}


def contains_protected_material(body: bytes, key: str, url: str) -> bool:
    if key.encode("utf-8") in body or url.encode("utf-8") in body:
        return True
    try:
        value = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    if isinstance(value, str):
        values = [value]
    else:
        values = [scalar for _, _, scalar in scalar_fields(value) if isinstance(scalar, str)]
    return any(key in value or url in value for value in values)


def safe_content_type(value: str) -> str:
    media_type = value.split(";", 1)[0].strip().lower()
    if not re.fullmatch(r"[a-z0-9!#$&^_.+-]+/[a-z0-9!#$&^_.+-]+", media_type):
        return ""
    return media_type


def make_request(url: str, key: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers={
        "accept": "application/json",
        KEY_HEADER: key,
        "user-agent": "RSIBench-SportsDataIO-Replay-Canary/1",
    })


def fetch_once(url: str, key: str, timeout: float,
               maximum_response_bytes: int) -> tuple[int, bytes, str]:
    if not 1 <= maximum_response_bytes <= MAXIMUM_RESPONSE_BYTES:
        raise ValueError("bounded response size required")
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(make_request(url, key), timeout=timeout) as response:
            status = int(response.status)
            content_type = response.headers.get("Content-Type", "")
            body = response.read(maximum_response_bytes + 1)
    except urllib.error.HTTPError as error:
        status = int(error.code)
        content_type = error.headers.get("Content-Type", "")
        body = error.read(maximum_response_bytes + 1)
    if len(body) > maximum_response_bytes:
        raise RuntimeError("Replay response exceeds configured byte cap")
    return status, body, content_type


def validate_bounds(poll_seconds: float, maximum_polls: int, timeout: float,
                    maximum_response_bytes: int) -> None:
    if poll_seconds < MINIMUM_POLL_SECONDS or poll_seconds > 3600:
        raise ValueError("poll interval must be between 3 and 3600 seconds")
    if not 1 <= maximum_polls <= MAXIMUM_POLLS:
        raise ValueError("bounded poll count required")
    if not 1 <= timeout <= 60:
        raise ValueError("timeout must be between 1 and 60 seconds")
    if not 1 <= maximum_response_bytes <= MAXIMUM_RESPONSE_BYTES:
        raise ValueError("bounded response size required")
    worst_case_seconds = maximum_polls * timeout + (maximum_polls - 1) * poll_seconds
    if worst_case_seconds > MAXIMUM_WORST_CASE_SECONDS:
        raise ValueError("configured worst-case capture duration exceeds 24 hours")
    if maximum_polls * maximum_response_bytes > MAXIMUM_CAPTURE_BYTES:
        raise ValueError("configured worst-case raw output exceeds 1 GiB")


def capture(output: Path, endpoint_file: Path, authorization_file: Path,
            poll_seconds: float, maximum_polls: int, timeout: float,
            maximum_response_bytes: int = 8 * 1024 * 1024,
            *, fetch: Callable[[str, str, float, int], tuple[int, bytes, str]] = fetch_once,
            sleep: Callable[[float], None] = time.sleep,
            wall_clock: Callable[[], int] = time.time_ns,
            monotonic_clock: Callable[[], int] = time.monotonic_ns) -> dict[str, Any]:
    validate_bounds(poll_seconds, maximum_polls, timeout, maximum_response_bytes)
    output = Path(output)
    if output.exists():
        raise ValueError("fresh output directory required")
    url, endpoint_raw = load_endpoint(endpoint_file)
    parsed = urllib.parse.urlsplit(url)
    host = parsed.hostname.lower().rstrip(".")
    _, authorization_sha = load_authorization(
        authorization_file, endpoint_raw, host)
    key = load_key()
    if key in url:
        raise ValueError("API key is forbidden in endpoint URL")
    output.mkdir(parents=True, mode=0o700)
    raw_root = output / "raw"
    raw_root.mkdir(mode=0o700)
    receipts_path = output / "receipts.jsonl"
    fields_path = output / "field_observations.jsonl"
    counts, first_seen, previous_sha = Counter(), {}, None
    started_ns = wall_clock()
    with receipts_path.open("x", encoding="utf-8") as receipts, fields_path.open(
            "x", encoding="utf-8") as fields:
        for poll_index in range(1, maximum_polls + 1):
            sent_ns, sent_monotonic = wall_clock(), monotonic_clock()
            status, body, content_type = fetch(
                url, key, timeout, maximum_response_bytes)
            received_ns, received_monotonic = wall_clock(), monotonic_clock()
            if contains_protected_material(body, key, url):
                raise RuntimeError("provider response echoed protected request material; nothing persisted")
            body_sha = sha256_bytes(body)
            raw_name = f"{poll_index:06d}.bin"
            raw_path = raw_root / raw_name
            raw_path.write_bytes(body)
            with raw_path.open("rb") as stream:
                os.fsync(stream.fileno())
            duplicate_of = first_seen.get(body_sha)
            first_seen.setdefault(body_sha, poll_index)
            row: dict[str, Any] = {
                "poll_index": poll_index,
                "request_sent_utc": utc(sent_ns),
                "request_sent_unix_ns": sent_ns,
                "response_received_utc": utc(received_ns),
                "response_received_unix_ns": received_ns,
                "round_trip_ms": (received_monotonic - sent_monotonic) / 1e6,
                "receive_monotonic": received_monotonic >= sent_monotonic,
                "http_status": status,
                "content_type": safe_content_type(content_type),
                "raw_file": "raw/" + raw_name,
                "raw_bytes": len(body),
                "raw_sha256": body_sha,
                "exact_duplicate": duplicate_of is not None,
                "duplicate_of_poll": duplicate_of,
                "unchanged_from_previous_poll": previous_sha == body_sha,
                "parse_ok": False,
                "clock_semantics_reviewed": False,
                "provider_publish_latency_computed": False,
            }
            counts["polls"] += 1
            counts["raw_bytes"] += len(body)
            if row["exact_duplicate"]:
                counts["exact_duplicates"] += 1
            if row["unchanged_from_previous_poll"]:
                counts["unchanged_from_previous"] += 1
            if not row["receive_monotonic"]:
                counts["monotonicity_violations"] += 1
            try:
                parsed_body = json.loads(body)
                observations = payload_observations(parsed_body)
                row["parse_ok"] = True
                row["clock_field_count"] = len(observations["clock_fields_verbatim"])
                row["correction_field_count"] = len(
                    observations["correction_fields_verbatim"])
                fields.write(json.dumps({"poll_index": poll_index, **observations},
                    sort_keys=True, separators=(",", ":")) + "\n")
                fields.flush(); os.fsync(fields.fileno())
                counts["json_responses"] += 1
                counts["clock_field_observations"] += row["clock_field_count"]
                counts["correction_field_observations"] += row["correction_field_count"]
            except (UnicodeDecodeError, json.JSONDecodeError):
                counts["parse_errors"] += 1
            receipts.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
            receipts.flush(); os.fsync(receipts.fileno())
            previous_sha = body_sha
            if status < 200 or status >= 300:
                counts["http_failures"] += 1
                break
            if poll_index < maximum_polls:
                sleep(poll_seconds)
    ended_ns = wall_clock()
    manifest = {
        "schema": SCHEMA,
        "source": "SportsDataIO Replay",
        "capture_scope": "operator_created_replay_session",
        "started_utc": utc(started_ns),
        "ended_utc": utc(ended_ns),
        "endpoint": {
            "host": host,
            "path_sha256": sha256_bytes(parsed.path.encode("utf-8")),
            "endpoint_input_sha256": sha256_bytes(endpoint_raw),
            "url_persisted": False,
        },
        "authorization_receipt_sha256": authorization_sha,
        "bounds": {
            "poll_seconds": poll_seconds,
            "maximum_polls": maximum_polls,
            "timeout_seconds": timeout,
            "maximum_response_bytes": maximum_response_bytes,
            "worst_case_seconds": maximum_polls * timeout
                + (maximum_polls - 1) * poll_seconds,
            "worst_case_raw_bytes": maximum_polls * maximum_response_bytes,
            "automatic_retry": False,
            "redirects_followed": False,
        },
        "summary": dict(counts),
        "files": {
            "receipts.jsonl": file_sha256(receipts_path),
            "field_observations.jsonl": file_sha256(fields_path),
            "raw_files": [
                {"name": path.name, "sha256": file_sha256(path), "bytes": path.stat().st_size}
                for path in sorted(raw_root.iterdir())
            ],
        },
        "api_key_persisted": False,
        "session_url_persisted": False,
        "clock_semantics_reviewed": False,
        "provider_publish_latency_computed": False,
        "historical_revision_archive_claimed": False,
        "provider_sla_proven": False,
        "market_lead_proven": False,
        "model_score_computed": False,
        "dev_opened": False,
        "final_opened": False,
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--endpoint-file", type=Path, required=True)
    parser.add_argument("--authorization-file", type=Path, required=True)
    parser.add_argument("--poll-seconds", type=float, default=3.0)
    parser.add_argument("--maximum-polls", type=int, default=100)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--maximum-response-bytes", type=int, default=8 * 1024 * 1024)
    args = parser.parse_args()
    result = capture(args.output, args.endpoint_file, args.authorization_file,
        args.poll_seconds, args.maximum_polls, args.timeout, args.maximum_response_bytes)
    print(json.dumps({"schema": result["schema"], "summary": result["summary"],
        "manifest_sha256": file_sha256(args.output / "manifest.json")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
