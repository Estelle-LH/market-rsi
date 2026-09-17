"""One directional A/B protocol observation on already-created E2B objects.

This component cannot create sandboxes or admit a live round. A separate,
published parent runner must own the unique claim, budget, both sandbox IDs,
bidirectional calls, provider isolation, broker-positive control and cleanup.
Even a negative observation here is not an isolation certificate.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import secrets
import shlex

from market_rsi import digest, file_hash, fresh_json, identifier
from supervisor_harness import peer_marker_server, protocol_network_probe


PEER_PORT = 8765
PEER_MARKER = "/tmp/market-peer-marker.txt"
PEER_SOURCE = "/tmp/market-peer-server.py"
PROBE_SOURCE = "/tmp/market-protocol-network-probe.py"
PROBE_RESULT = "/tmp/market-protocol-network-report.json"
PROBE_PROGRESS_PREFIX = "/tmp/market-protocol-progress"
MAX_COMMAND_OUTPUT = 8192
PROBE_COMMAND_TIMEOUT_SECONDS = 60
PROGRESS_READ_TIMEOUT_SECONDS = 2
MAX_PROGRESS_RECEIPT_BYTES = 2048


def _script(path: Path) -> tuple[str, str]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 128 * 1024:
        raise ValueError("missing, symlinked or oversized probe source")
    return path.read_text(encoding="utf-8"), file_hash(path)


def _command(result, *, label: str) -> dict:
    if (type(result.exit_code) is not int or result.exit_code != 0
            or not isinstance(result.stdout, str)
            or not isinstance(result.stderr, str)
            or len(result.stdout.encode()) > MAX_COMMAND_OUTPUT
            or len(result.stderr.encode()) > MAX_COMMAND_OUTPUT):
        raise ValueError(f"{label} command failed or exceeded output bound")
    return {"exit_code": result.exit_code,
            "stdout_sha256": hashlib.sha256(result.stdout.encode()).hexdigest(),
            "stderr_sha256": hashlib.sha256(result.stderr.encode()).hexdigest()}


class _StdoutProgress:
    """Bounded host observation of guest stdout; never an application verdict."""

    def __init__(self, *, public_url: str, peer_url: str, marker_sha: str) -> None:
        self._sha256 = hashlib.sha256()
        self._bytes_seen = 0
        self._captured = bytearray()
        self._public_url = public_url
        self._peer_url = peer_url
        self._marker_sha = marker_sha

    def __call__(self, chunk: str) -> None:
        if not isinstance(chunk, str):
            return
        encoded = chunk.encode("utf-8")
        self._sha256.update(encoded)
        self._bytes_seen += len(encoded)
        remaining = MAX_COMMAND_OUTPUT - len(self._captured)
        if remaining > 0:
            self._captured.extend(encoded[:remaining])

    def receipt(self) -> dict:
        # The SDK may deliver arbitrary chunks, including half of a JSON line.
        # Only complete, well-shaped lines are retained, and even these are
        # untrusted guest statements rather than HTTP/TLS observations.
        data = bytes(self._captured)
        lines = data.split(b"\n")
        trailing = lines.pop()
        milestones = []
        receipts = []
        unrecognized_lines = max(0, len(lines) - 8) + int(bool(trailing))
        for line in lines[:8]:
            try:
                item = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError):
                unrecognized_lines += 1
                continue
            if (isinstance(item, dict)
                    and item.get("schema") == "market_rsi_protocol_probe_progress_v1"
                    and item.get("phase") in {"start", "complete"}
                    and type(item.get("index")) is int
                    and 0 <= item["index"] <= 3
                    and item.get("label") in {"public", "peer"}
                    and item.get("mode") in {"environment_proxy", "direct_no_proxy"}):
                receipts.append(item)
                milestones.append({"index": item["index"], "phase": item["phase"],
                                   "label": item["label"], "mode": item["mode"]})
            else:
                unrecognized_lines += 1
        try:
            review = protocol_network_probe.review_progress(
                receipts, public_url=self._public_url, peer_url=self._peer_url,
                peer_marker_sha256=self._marker_sha)
            review_error = None
        except ValueError as exc:
            review = None
            review_error = type(exc).__name__
        return {"schema": "market_rsi_e2b_source_command_progress_v1",
                "stdout_callback_bytes": self._bytes_seen,
                "stdout_callback_sha256": self._sha256.hexdigest(),
                "stdout_callback_truncated": self._bytes_seen > len(self._captured),
                "guest_claimed_milestones": milestones,
                "guest_progress_receipts": receipts,
                "unrecognized_stdout_lines": unrecognized_lines,
                "partial_review": review,
                "review_error_type": review_error,
                "application_verdict": None}


def _recover_guest_progress(source, *, public_url: str, peer_url: str,
                            marker_sha: str) -> dict:
    """Read only known small receipts; a missing/invalid one is diagnostic."""
    receipts = []
    receipt_hashes = []
    stop = None
    for index in range(4):
        for phase in ("start", "complete"):
            path = str(protocol_network_probe.progress_path(
                Path(PROBE_PROGRESS_PREFIX), index, phase))
            try:
                raw = source.files.read(path, request_timeout=PROGRESS_READ_TIMEOUT_SECONDS)
            except Exception as exc:
                stop = {"index": index, "phase": phase,
                        "reason": "read_error", "error_type": type(exc).__name__}
                break
            if not isinstance(raw, str) or len(raw.encode()) > MAX_PROGRESS_RECEIPT_BYTES:
                stop = {"index": index, "phase": phase,
                        "reason": "nontext_or_oversized"}
                break
            receipt_hashes.append(hashlib.sha256(raw.encode()).hexdigest())
            try:
                receipts.append(json.loads(raw))
            except json.JSONDecodeError:
                stop = {"index": index, "phase": phase,
                        "reason": "invalid_json"}
                break
        if stop is not None:
            break
    try:
        review = protocol_network_probe.review_progress(
            receipts, public_url=public_url, peer_url=peer_url,
            peer_marker_sha256=marker_sha)
        review_error = None
    except ValueError as exc:
        review = None
        review_error = type(exc).__name__
    return {"schema": "market_rsi_e2b_guest_progress_recovery_v1",
            "receipt_sha256": receipt_hashes, "read_receipts": len(receipts),
            "first_unavailable": stop, "partial_review": review,
            "review_error_type": review_error,
            "complete_application_verdict": False}


def observe_direction(*, source, target, state, cycle_id: str,
                      public_url: str, receipt_root: Path) -> dict:
    """Start a synthetic peer service in target and probe it from source."""
    identifier(cycle_id)
    protocol_network_probe._url(public_url)
    if (not isinstance(source.sandbox_id, str) or not source.sandbox_id
            or not isinstance(target.sandbox_id, str) or not target.sandbox_id
            or source.sandbox_id == target.sandbox_id):
        raise ValueError("distinct host-observed sandbox objects required")
    if state.snapshot()["active_cycle"] != cycle_id:
        raise ValueError("supervisor global cycle is not active")
    root = Path(receipt_root)
    if root.exists() or root.is_symlink():
        raise FileExistsError("fresh directional probe receipt required")
    server_script, server_sha = _script(Path(peer_marker_server.__file__))
    probe_script, probe_sha = _script(Path(protocol_network_probe.__file__))
    source_sha = file_hash(__file__)
    marker = secrets.token_hex(24)
    marker_sha = hashlib.sha256(marker.encode()).hexdigest()
    root.mkdir(mode=0o700)
    claim = {"schema": "market_rsi_e2b_direction_attempt_v1",
             "cycle_id": cycle_id, "source_sandbox_id": source.sandbox_id,
             "target_sandbox_id": target.sandbox_id,
             "host_source_sha256": source_sha,
             "peer_source_sha256": server_sha,
             "network_probe_source_sha256": probe_sha,
             "marker_sha256": marker_sha,
             "public_url_sha256": hashlib.sha256(public_url.encode()).hexdigest(),
             "port": PEER_PORT, "isolation_proven": False}
    fresh_json(root / "attempt.json", claim)
    handle = None
    cleanup = {"background_process_started": False, "kill_acknowledged": None}
    error = None
    stage = "target_marker_write"
    progress = None
    try:
        target.files.write(PEER_MARKER, marker)
        stage = "target_server_source_write"
        target.files.write(PEER_SOURCE, server_script)
        stage = "target_server_start"
        handle = target.commands.run(
            f"python3 -I {PEER_SOURCE} --serve --marker {PEER_MARKER} --port {PEER_PORT}",
            background=True, timeout=30)
        if type(handle.pid) is not int or handle.pid <= 0:
            raise ValueError("peer service has no observed process ID")
        cleanup["background_process_started"] = True
        cleanup["pid"] = handle.pid
        stage = "target_local_positive_command"
        checked = target.commands.run(
            f"python3 -I {PEER_SOURCE} --self-check --marker {PEER_MARKER} --port {PEER_PORT}",
            timeout=10)
        check_command = _command(checked, label="peer local positive")
        local = json.loads(checked.stdout)
        if (not isinstance(local, dict)
                or set(local) != {"schema", "port", "marker_sha256", "attempts",
                                      "local_service_responded"}
                or local["schema"] != "market_rsi_peer_local_positive_v1"
                or local["port"] != PEER_PORT
                or local["marker_sha256"] != marker_sha
                or local["local_service_responded"] is not True
                or type(local["attempts"]) is not int
                or not 1 <= local["attempts"] <= 10):
            raise ValueError("peer service positive control did not verify")
        fresh_json(root / "peer-local-positive.json", local)
        fresh_json(root / "peer-local-command.json", check_command)
        stage = "target_peer_host_lookup"
        peer_host = target.get_host(PEER_PORT)
        if not isinstance(peer_host, str) or not peer_host:
            raise ValueError("target sandbox did not provide a peer service host")
        peer_url = protocol_network_probe._url(f"https://{peer_host}/marker")
        stage = "source_probe_write"
        source.files.write(PROBE_SOURCE, probe_script)
        command = (f"python3 -I {PROBE_SOURCE} --public-url {shlex.quote(public_url)}"
                   f" --peer-url {shlex.quote(peer_url)} --output {PROBE_RESULT}"
                   f" --progress-prefix {PROBE_PROGRESS_PREFIX}")
        # This is an SDK streaming-connection deadline for four sequential
        # bounded HTTP attempts, not a per-request timeout. The prior 25s
        # deadline expired before E2B returned any guest report.
        fresh_json(root / "source-command-dispatch.json", {
            "schema": "market_rsi_e2b_source_command_dispatch_v1",
            "command_sha256": hashlib.sha256(command.encode()).hexdigest(),
            "sdk_stream_timeout_seconds": PROBE_COMMAND_TIMEOUT_SECONDS,
            "guest_report_read": False, "application_verdict": None})
        progress = _StdoutProgress(public_url=public_url, peer_url=peer_url,
                                   marker_sha=marker_sha)
        stage = "source_command_run"
        probed = source.commands.run(command, timeout=PROBE_COMMAND_TIMEOUT_SECONDS,
                                     on_stdout=progress)
        fresh_json(root / "source-command-progress.json", progress.receipt())
        stage = "source_command_result_validation"
        probe_command = _command(probed, label="source application probe")
        stage = "source_guest_report_read"
        raw_report = source.files.read(PROBE_RESULT)
        if not isinstance(raw_report, str) or len(raw_report.encode()) > 16 * 1024:
            raise ValueError("missing or oversized guest network report")
        report = json.loads(raw_report)
        # Preserve the bounded raw observation even when independent review
        # rejects a timed-out or otherwise inconclusive request. A saved report
        # is diagnostic evidence, not an accepted network verdict.
        fresh_json(root / "raw-report.json", {"raw_utf8": raw_report})
        fresh_json(root / "report.json", report)
        stage = "source_guest_report_review"
        review = protocol_network_probe.review(
            report, public_url=public_url, peer_url=peer_url,
            peer_marker_sha256=marker_sha)
        if state.snapshot()["active_cycle"] != cycle_id:
            raise ValueError("supervisor cycle changed during directional probe")
        fresh_json(root / "probe-command.json", probe_command)
        fresh_json(root / "review.json", review)
    except Exception as exc:
        error = exc
        fresh_json(root / "failure.json", {"error_type": type(exc).__name__,
                                           "stage": stage,
                                           "failure_domain": (
                                               "sdk_stream_timeout"
                                               if stage == "source_command_run"
                                               and type(exc).__name__ == "TimeoutException"
                                               else "host_or_sdk_command_failure"),
                                           "complete_report_receipt_written": (
                                               root / "review.json").is_file(),
                                           "attempt_sha256": digest(claim)})
    finally:
        if handle is not None:
            try:
                cleanup["kill_acknowledged"] = handle.kill() is True
            except Exception as exc:
                cleanup["kill_acknowledged"] = False
                cleanup["kill_error_type"] = type(exc).__name__
        fresh_json(root / "peer-process-cleanup.json", cleanup)
        if progress is not None and not (root / "source-command-progress.json").exists():
            fresh_json(root / "source-command-progress.json", progress.receipt())
        if progress is not None:
            try:
                recovery = _recover_guest_progress(
                    source, public_url=public_url, peer_url=peer_url, marker_sha=marker_sha)
            except Exception as exc:
                recovery = {"schema": "market_rsi_e2b_guest_progress_recovery_v1",
                            "recovery_error_type": type(exc).__name__,
                            "complete_application_verdict": False}
            fresh_json(root / "guest-progress-recovery.json", recovery)
    if error is not None:
        raise error
    if cleanup["kill_acknowledged"] is not True:
        fresh_json(root / "failure.json", {
            "error_type": "PeerProcessCleanupUnconfirmed",
            "attempt_sha256": digest(claim)})
        raise RuntimeError("exact peer service cleanup was not acknowledged")
    if (file_hash(__file__) != source_sha
            or file_hash(peer_marker_server.__file__) != server_sha
            or file_hash(protocol_network_probe.__file__) != probe_sha):
        fresh_json(root / "failure.json", {
            "error_type": "ProtocolSourceChanged",
            "attempt_sha256": digest(claim)})
        raise RuntimeError("protocol source changed during observation")
    # A completed positive milestone cannot be erased by a contradictory
    # final report. Missing/negative partial milestones never establish a
    # blocked route; they are only diagnostic.
    stdout_progress = progress.receipt()
    unavailable = recovery.get("first_unavailable") or {}
    if (stdout_progress["stdout_callback_truncated"]
            or stdout_progress["review_error_type"] is not None
            or stdout_progress["unrecognized_stdout_lines"]
            or recovery.get("review_error_type") is not None
            or unavailable.get("reason") in {"invalid_json", "nontext_or_oversized"}):
        fresh_json(root / "failure.json", {
            "error_type": "InvalidGuestProgressReceipt",
            "attempt_sha256": digest(claim)})
        raise RuntimeError("guest progress evidence invalid")
    partial_reviews = (stdout_progress["partial_review"],
                       recovery.get("partial_review"))
    positive_partial = any(
        item is not None and (item["public_http_response_observed"]
                              or item["peer_marker_observed"])
        for item in partial_reviews)
    if (review["public_http_response_observed"] or review["peer_marker_observed"]
            or positive_partial):
        fresh_json(root / "failure.json", {
            "error_type": "ForbiddenApplicationChannelObserved",
            "attempt_sha256": digest(claim),
            "review_sha256": file_hash(root / "review.json")})
        raise RuntimeError("forbidden application-level channel observed")
    result = {"schema": "market_rsi_e2b_direction_observation_v1",
              "attempt_sha256": file_hash(root / "attempt.json"),
              "local_positive_sha256": file_hash(root / "peer-local-positive.json"),
              "report_sha256": file_hash(root / "report.json"),
              "review_sha256": file_hash(root / "review.json"),
              "cleanup_sha256": file_hash(root / "peer-process-cleanup.json"),
              "no_forbidden_application_payload_observed": True,
              "isolation_proven": False}
    fresh_json(root / "observation.json", result)
    return result
