"""Application-level E2B network observation, not an isolation certificate.

The trusted host supplies harmless public/peer HTTPS URLs and preserves this
exact source hash. The guest performs one bounded GET with environment proxy
settings and one without them for each URL. An HTTP response, including 403,
is evidence that application bytes reached some HTTP endpoint; a mere TCP
handshake is not. Negative observations on two URLs cannot prove that every
possible route is blocked. The host must separately verify E2B policy, both
roles, broker-positive access, peer-marker denial, and exact cleanup.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener


SCHEMA = "market_rsi_protocol_network_probe_v1"
MAX_RESPONSE_BYTES = 2048
TIMEOUT_SECONDS = 3
ATTEMPT_WALL_TIMEOUT_SECONDS = 6
MAX_CHILD_OUTPUT_BYTES = 1024
MODES = ("environment_proxy", "direct_no_proxy")
PROGRESS_SCHEMA = "market_rsi_protocol_probe_progress_v1"
PROGRESS_REVIEW_SCHEMA = "market_rsi_protocol_probe_progress_review_v1"
ATTEMPTS = (("public", "environment_proxy", False),
            ("public", "direct_no_proxy", True),
            ("peer", "environment_proxy", False),
            ("peer", "direct_no_proxy", True))


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _url(value: str) -> str:
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError("bounded HTTPS URL required")
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.fragment or parsed.port not in {None, 443}):
        raise ValueError("public and peer probes require credential-free HTTPS URLs")
    return value


def _one_get(url: str, *, direct: bool) -> dict:
    opener = build_opener(ProxyHandler({}) if direct else ProxyHandler())
    request = Request(url, headers={"User-Agent": "MarketRSI-isolation-canary/1"},
                      method="GET")
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
            return {"http_response": True, "status": response.status,
                    "body_sha256": hashlib.sha256(body).hexdigest(),
                    "body_truncated": len(body) > MAX_RESPONSE_BYTES,
                    "error_type": None}
    except HTTPError as error:
        # A 4xx/5xx is still an application-level response; never count it as
        # proof that the guest could not communicate with a remote endpoint.
        with error:
            body = error.read(MAX_RESPONSE_BYTES + 1)
        return {"http_response": True, "status": error.code,
                "body_sha256": hashlib.sha256(body).hexdigest(),
                "body_truncated": len(body) > MAX_RESPONSE_BYTES,
                "error_type": None}
    except (URLError, OSError, TimeoutError) as error:
        return {"http_response": False, "status": None,
                "body_sha256": None, "body_truncated": False,
                "error_type": type(error).__name__}


def _bounded_get(url: str, *, direct: bool) -> dict:
    """Run one GET in a reapable child; socket timeouts are not wall deadlines."""
    command = [sys.executable, "-I", str(Path(__file__).resolve()),
               "--single-get", _url(url), "direct" if direct else "environment_proxy"]
    try:
        child = subprocess.run(command, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE,
                               timeout=ATTEMPT_WALL_TIMEOUT_SECONDS, check=False)
    except subprocess.TimeoutExpired:
        # The child was killed and reaped by run(). It may have received HTTP
        # headers before stalling, so this is UNKNOWN, not a blocked route.
        return {"http_response": False, "status": None,
                "body_sha256": None, "body_truncated": False,
                "error_type": "AttemptDeadlineExpired"}
    if (child.returncode != 0 or child.stderr
            or not isinstance(child.stdout, bytes)
            or len(child.stdout) > MAX_CHILD_OUTPUT_BYTES):
        raise RuntimeError("bounded protocol child failed")
    try:
        return _validate_observation(json.loads(child.stdout))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError("bounded protocol child returned invalid observation") from exc


def progress_path(prefix: Path, index: int, phase: str) -> Path:
    """Predictable immutable receipt name for a host reading after SDK timeout."""
    if type(index) is not int or not 0 <= index < len(ATTEMPTS):
        raise ValueError("invalid protocol attempt index")
    if phase not in {"start", "complete"}:
        raise ValueError("invalid protocol attempt phase")
    prefix = Path(prefix)
    return prefix.with_name(f"{prefix.name}-{index:02d}-{phase}.json")


def _emit_progress(prefix: Path, record: dict) -> None:
    """Commit a complete receipt before exposing its bounded stdout milestone."""
    path = progress_path(prefix, record["index"], record["phase"])
    if path.exists() or path.is_symlink():
        raise FileExistsError("fresh protocol progress receipt required")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                         dir=path.parent, prefix=f".{path.name}.",
                                         delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(record, stream, sort_keys=True, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        # A hard link publishes complete bytes without replacing an earlier
        # receipt. Readers never treat an in-progress temporary file as evidence.
        os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    print(json.dumps(record, sort_keys=True, separators=(",", ":")), flush=True)


def observe(public_url: str, peer_url: str, *, progress_prefix: Path | None = None) -> dict:
    public_url, peer_url = _url(public_url), _url(peer_url)
    urls = {"public": public_url, "peer": peer_url}
    hashes = {label: _sha(url) for label, url in urls.items()}
    observations = {label: {} for label in urls}
    if progress_prefix is not None:
        progress_prefix = Path(progress_prefix)
        if (not progress_prefix.is_absolute() or not progress_prefix.parent.is_dir()
                or progress_prefix.parent.is_symlink()):
            raise ValueError("absolute progress prefix in a real directory required")
        if any(progress_path(progress_prefix, index, phase).exists()
               or progress_path(progress_prefix, index, phase).is_symlink()
               for index in range(len(ATTEMPTS)) for phase in ("start", "complete")):
            raise FileExistsError("fresh protocol progress receipts required")
    for index, (label, mode, direct) in enumerate(ATTEMPTS):
        receipt = {"schema": PROGRESS_SCHEMA, "phase": "start", "index": index,
                   "label": label, "mode": mode, "url_sha256": hashes}
        if progress_prefix is not None:
            _emit_progress(progress_prefix, receipt)
        item = _bounded_get(urls[label], direct=direct)
        observations[label][mode] = item
        if progress_prefix is not None:
            _emit_progress(progress_prefix, {**receipt, "phase": "complete",
                                             "observation": item})
    return {"schema": SCHEMA, "url_sha256": hashes,
            "observations": observations}


def _validate_observation(item: object) -> dict:
    if (not isinstance(item, dict)
            or set(item) != {"http_response", "status", "body_sha256",
                             "body_truncated", "error_type"}
            or type(item["http_response"]) is not bool
            or type(item["body_truncated"]) is not bool):
        raise ValueError("invalid protocol observation")
    if item["http_response"]:
        if (type(item["status"]) is not int or not 100 <= item["status"] <= 599
                or not isinstance(item["body_sha256"], str)
                or len(item["body_sha256"]) != 64
                or any(c not in "0123456789abcdef" for c in item["body_sha256"])
                or item["error_type"] is not None):
            raise ValueError("invalid HTTP response receipt")
    elif (item["status"] is not None or item["body_sha256"] is not None
          or item["body_truncated"] is not False
          or not isinstance(item["error_type"], str)
          or not 1 <= len(item["error_type"]) <= 64
          or not item["error_type"].isascii()
          or not item["error_type"].isidentifier()):
        raise ValueError("invalid blocked/failed response receipt")
    return item


def review_progress(receipts: list[dict], *, public_url: str, peer_url: str,
                    peer_marker_sha256: str) -> dict:
    """Validate partial receipts without turning absent attempts into negatives."""
    urls = {"public": _url(public_url), "peer": _url(peer_url)}
    hashes = {label: _sha(url) for label, url in urls.items()}
    if (not isinstance(peer_marker_sha256, str) or len(peer_marker_sha256) != 64
            or any(c not in "0123456789abcdef" for c in peer_marker_sha256)):
        raise ValueError("peer marker SHA256 required")
    if not isinstance(receipts, list) or len(receipts) > 2 * len(ATTEMPTS):
        raise ValueError("progress receipts must be a bounded list")
    seen = set()
    started = set()
    completed = {}
    base_keys = {"schema", "phase", "index", "label", "mode", "url_sha256"}
    for receipt in receipts:
        if (not isinstance(receipt, dict)
                or set(receipt) not in (base_keys, base_keys | {"observation"})
                or receipt["schema"] != PROGRESS_SCHEMA
                or type(receipt["index"]) is not int
                or not 0 <= receipt["index"] < len(ATTEMPTS)
                or receipt["phase"] not in {"start", "complete"}
                or receipt["url_sha256"] != hashes):
            raise ValueError("invalid or unbound protocol progress receipt")
        index, phase = receipt["index"], receipt["phase"]
        label, mode, _ = ATTEMPTS[index]
        if (receipt["label"] != label or receipt["mode"] != mode
                or (index, phase) in seen):
            raise ValueError("duplicate or mismatched protocol progress receipt")
        seen.add((index, phase))
        if phase == "start":
            if "observation" in receipt:
                raise ValueError("start receipt cannot contain an observation")
            started.add(index)
        else:
            if "observation" not in receipt:
                raise ValueError("complete receipt requires an observation")
            completed[index] = _validate_observation(receipt["observation"])
    if not set(completed) <= started:
        raise ValueError("completion has no start receipt")
    return {"schema": PROGRESS_REVIEW_SCHEMA,
            "attempts_started": sorted(started),
            "attempts_completed": sorted(completed),
            "attempts_timed_out": sorted(index for index, item in completed.items()
                                         if item["error_type"] == "AttemptDeadlineExpired"),
            "all_four_completed": len(completed) == len(ATTEMPTS),
            "public_http_response_observed": any(
                ATTEMPTS[index][0] == "public" and item["http_response"]
                for index, item in completed.items()),
            "peer_http_response_observed": any(
                ATTEMPTS[index][0] == "peer" and item["http_response"]
                for index, item in completed.items()),
            "peer_marker_observed": any(
                ATTEMPTS[index][0] == "peer" and item["http_response"]
                and item["body_sha256"] == peer_marker_sha256
                and not item["body_truncated"]
                for index, item in completed.items()),
            "isolation_proven": False}


def review(report: dict, *, public_url: str, peer_url: str,
           peer_marker_sha256: str) -> dict:
    """Host checks the shape and reports observations; never certifies isolation."""
    urls = {"public": _url(public_url), "peer": _url(peer_url)}
    if (not isinstance(peer_marker_sha256, str) or len(peer_marker_sha256) != 64
            or any(c not in "0123456789abcdef" for c in peer_marker_sha256)):
        raise ValueError("peer marker SHA256 required")
    if (not isinstance(report, dict) or set(report) != {"schema", "url_sha256", "observations"}
            or report["schema"] != SCHEMA
            or report["url_sha256"] != {label: _sha(url) for label, url in urls.items()}
            or not isinstance(report["observations"], dict)
            or set(report["observations"]) != set(urls)):
        raise ValueError("probe report is not bound to the two host-selected URLs")
    observed = {}
    for label in urls:
        modes = report["observations"][label]
        if not isinstance(modes, dict) or set(modes) != set(MODES):
            raise ValueError("missing protocol probe mode")
        observed[label] = []
        for mode in MODES:
            observed[label].append(_validate_observation(modes[mode]))
    if any(item["error_type"] == "AttemptDeadlineExpired"
           for items in observed.values() for item in items):
        raise ValueError("a wall-deadline attempt cannot establish a blocked route")
    return {"schema": "market_rsi_protocol_network_review_v1",
            "public_http_response_observed": any(
                item["http_response"] for item in observed["public"]),
            "peer_http_response_observed": any(
                item["http_response"] for item in observed["peer"]),
            "peer_marker_observed": any(
                item["http_response"] and item["body_sha256"] == peer_marker_sha256
                and not item["body_truncated"] for item in observed["peer"]),
            "isolation_proven": False}


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--single-get":
        if len(sys.argv) != 4 or sys.argv[3] not in MODES:
            raise ValueError("invalid bounded protocol child arguments")
        item = _one_get(_url(sys.argv[2]), direct=sys.argv[3] == "direct_no_proxy")
        print(json.dumps(item, sort_keys=True, separators=(",", ":")))
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-url", required=True)
    parser.add_argument("--peer-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--progress-prefix", type=Path)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise FileExistsError("fresh protocol probe output required")
    report = observe(args.public_url, args.peer_url,
                     progress_prefix=args.progress_prefix)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, sort_keys=True, separators=(",", ":"))


if __name__ == "__main__":
    main()
