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
MAX_COMMAND_OUTPUT = 8192


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
    try:
        target.files.write(PEER_MARKER, marker)
        target.files.write(PEER_SOURCE, server_script)
        handle = target.commands.run(
            f"python3 -I {PEER_SOURCE} --serve --marker {PEER_MARKER} --port {PEER_PORT}",
            background=True, timeout=30)
        if type(handle.pid) is not int or handle.pid <= 0:
            raise ValueError("peer service has no observed process ID")
        cleanup["background_process_started"] = True
        cleanup["pid"] = handle.pid
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
        peer_host = target.get_host(PEER_PORT)
        if not isinstance(peer_host, str) or not peer_host:
            raise ValueError("target sandbox did not provide a peer service host")
        peer_url = protocol_network_probe._url(f"https://{peer_host}/marker")
        source.files.write(PROBE_SOURCE, probe_script)
        command = (f"python3 -I {PROBE_SOURCE} --public-url {shlex.quote(public_url)}"
                   f" --peer-url {shlex.quote(peer_url)} --output {PROBE_RESULT}")
        probed = source.commands.run(command, timeout=25)
        probe_command = _command(probed, label="source application probe")
        raw_report = source.files.read(PROBE_RESULT)
        if not isinstance(raw_report, str) or len(raw_report.encode()) > 16 * 1024:
            raise ValueError("missing or oversized guest network report")
        report = json.loads(raw_report)
        review = protocol_network_probe.review(
            report, public_url=public_url, peer_url=peer_url,
            peer_marker_sha256=marker_sha)
        if state.snapshot()["active_cycle"] != cycle_id:
            raise ValueError("supervisor cycle changed during directional probe")
        fresh_json(root / "raw-report.json", {"raw_utf8": raw_report})
        fresh_json(root / "report.json", report)
        fresh_json(root / "probe-command.json", probe_command)
        fresh_json(root / "review.json", review)
    except Exception as exc:
        error = exc
        fresh_json(root / "failure.json", {"error_type": type(exc).__name__,
                                           "attempt_sha256": digest(claim)})
    finally:
        if handle is not None:
            try:
                cleanup["kill_acknowledged"] = handle.kill() is True
            except Exception as exc:
                cleanup["kill_acknowledged"] = False
                cleanup["kill_error_type"] = type(exc).__name__
        fresh_json(root / "peer-process-cleanup.json", cleanup)
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
    if review["public_http_response_observed"] or review["peer_marker_observed"]:
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
