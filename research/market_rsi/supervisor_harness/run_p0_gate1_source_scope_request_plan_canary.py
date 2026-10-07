"""Run the sole permanent-ID, zero-effect v0.1.26 D0 bridge canary.

The parent verifies a pre-existing publication receipt and immutable D0 files,
claims the exact ID once, supervises one local child, and records exact process,
container, watchdog and cleanup evidence.  It never imports or calls public
fetch, watched fetch, provider, credential, budget, data, or training code.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import subprocess
import sys
import time

from market_rsi import canonical, digest, file_hash, fresh_json
from supervisor_harness import p0_gate1_source_scope_request_plan_canary_child as child_entry
from supervisor_harness.supervisor_watchdog import SupervisorWatchdog
from supervisor_harness.supervisor_watchdog_local_control import (
    LocalProcessDockerControl,
    container_identity,
    process_command_sha256,
    stable_process_command_sha256,
)


CANARY_SCHEMA = "market_p0_gate1_source_scope_request_plan_canary_v1"
SUPERVISOR_RESULT_SCHEMA = (
    "market_p0_gate1_source_scope_request_plan_canary_supervisor_v1"
)
PERMANENT_CLAIM_SCHEMA = (
    "market_p0_gate1_source_scope_request_plan_canary_permanent_claim_v1"
)
RUNTIME_SCHEMA = "market_p0_gate1_source_scope_request_plan_canary_runtime_v1"
TERMINAL_CLEAR_SCHEMA = (
    "market_p0_gate1_source_scope_request_plan_canary_terminal_clear_v1"
)
CANARY_ID = child_entry.CANARY_ID
RELEASE_TAG = child_entry.RELEASE_TAG
PLAN_SHA256 = child_entry.REQUEST_PLAN_CANONICAL_SHA256
BUNDLE_SHA256 = child_entry.REQUEST_BUNDLE_CANONICAL_SHA256
CONTAINER_NAME = "market-rsi-b-" + CANARY_ID
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_SOURCE_ROOT = Path(__file__).resolve().parents[1]
_SOURCE_FILES = (
    "supervisor_harness/p0_gate1_source_scope_request_plan.py",
    "supervisor_harness/p0_gate1_source_scope_request_plan_canary_child.py",
    "supervisor_harness/run_p0_gate1_source_scope_request_plan_canary.py",
    "supervisor_harness/source_scope_request_plan_canary_receipt.py",
)
_ACCOUNT_HOME = Path(pwd.getpwuid(os.geteuid()).pw_dir)
_MARKET_RSI_HOME = _ACCOUNT_HOME / "Library/Application Support/MarketRSI"
RUN_ROOT = _MARKET_RSI_HOME / "runs" / CANARY_ID
CLAIM_ROOT = (
    _MARKET_RSI_HOME / "self-evolving-v18-local/artifacts/"
    "p0-gate1-source-scope-request-canary-claims-v1"
)
_D0_ROOT = (
    _MARKET_RSI_HOME / "runs" /
    "market-rsi-v0125-gate1-controller-d0-20260928-01"
)
_D0_ADAPTER = _D0_ROOT / "adapter" / child_entry.bridge.D0_CYCLE_ID
D0_PATHS = {
    "decision": _D0_ADAPTER / "decision.json",
    "submission": _D0_ADAPTER / "submission.json",
    "provenance": _D0_ADAPTER / "decision-provenance.json",
    "raw_response": _D0_ADAPTER / "raw-response.txt",
    "packet": (
        _MARKET_RSI_HOME / "runs" /
        "market-rsi-v0125-gate1-first-current-source-20260928-01" /
        "controller-input.json"
    ),
    "publication": _D0_ROOT / "publication.json",
    "result": _D0_ROOT / "result.json",
    "review": _D0_ROOT / "review.json",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _json_file_sha256(value: dict) -> str:
    return hashlib.sha256((canonical(value) + "\n").encode()).hexdigest()


def _load_json(path: Path, label: str) -> dict:
    return child_entry._parse_json(child_entry._read_regular(path, label), label)


def _validate_publication(
    path: Path, *, expected_source_sha256: str,
    expected_release_commit: str, expected_release_tag_object: str,
) -> dict:
    publication = _load_json(path, "v0.1.26 publication receipt")
    _require(set(publication) == {
        "schema", "origin", "tag", "commit", "tag_object", "source_sha256",
        "source_hashes", "isolation_proven", "model_authorship_proven",
    }, "invalid publication receipt fields")
    hashes = publication.get("source_hashes")
    _require(
        publication["schema"] == "market_rsi_protocol_publication_v1"
        and publication["origin"] == child_entry.PUBLISHED_ORIGIN
        and publication["tag"] == RELEASE_TAG
        and publication["commit"] == expected_release_commit
        and publication["tag_object"] == expected_release_tag_object
        and publication["source_sha256"] == expected_source_sha256
        and type(hashes) is dict and bool(hashes)
        and digest(hashes) == expected_source_sha256
        and publication["isolation_proven"] is False
        and publication["model_authorship_proven"] is False,
        "publication receipt does not bind the exact v0.1.26 release",
    )
    from supervisor_harness.protocol_source_release import source_hashes
    current_hashes = source_hashes()
    _require(hashes == current_hashes and digest(current_hashes) == expected_source_sha256,
             "current complete controlled source differs from the release")
    for name in _SOURCE_FILES:
        source = (_SOURCE_ROOT / name).resolve()
        _require(source == _SOURCE_ROOT / name and source.is_file()
                 and not source.is_symlink(), "missing canonical canary source")
        _require(hashes.get(name) == file_hash(source),
                 f"published canary source changed: {name}")
    return publication


def _validate_inputs(args: argparse.Namespace) -> tuple[dict, dict[str, Path]]:
    _require(args.release_tag == RELEASE_TAG, "exact v0.1.26 release tag required")
    _require(_SHA256.fullmatch(args.expected_source_sha256) is not None,
             "lowercase source SHA256 required")
    _require(_SHA1.fullmatch(args.expected_release_commit) is not None,
             "full release commit required")
    _require(_SHA1.fullmatch(args.expected_release_tag_object) is not None,
             "full annotated tag object required")
    _require(args.expected_request_plan_canonical_sha256 == PLAN_SHA256,
             "exact request-plan canonical commitment required")
    for name, expected in child_entry.D0_FILE_SHA256.items():
        _require(getattr(args, "expected_d0_" + name + "_sha256") == expected,
                 f"exact D0 {name} file commitment required")
    root = Path(args.root)
    _require(root == RUN_ROOT,
             "output must be the predeclared durable non-cloud canary path")
    _require(root.parent.resolve(strict=True) == root.parent,
             "root parent must be canonical and persistent")
    _require(not root.exists() and not root.is_symlink(), "fresh output root required")
    publication = _validate_publication(
        args.publication,
        expected_source_sha256=args.expected_source_sha256,
        expected_release_commit=args.expected_release_commit,
        expected_release_tag_object=args.expected_release_tag_object,
    )
    paths = {
        "decision": args.d0_decision,
        "submission": args.d0_submission,
        "provenance": args.d0_provenance,
        "raw_response": args.d0_raw_response,
        "packet": args.d0_packet,
        "publication": args.d0_publication,
        "result": args.d0_result,
        "review": args.d0_review,
    }
    for name, path in paths.items():
        _require(path == D0_PATHS[name], f"exact persistent D0 {name} path required")
        raw = child_entry._read_regular(path, f"D0 {name}")
        _require(hashlib.sha256(raw).hexdigest() == child_entry.D0_FILE_SHA256[name],
                 f"D0 {name} file commitment changed")
    return publication, paths


def _runtime() -> dict:
    hashes = {name: file_hash(_SOURCE_ROOT / name) for name in _SOURCE_FILES}
    return {
        "schema": RUNTIME_SCHEMA,
        "python_executable": str(Path(sys.executable).resolve()),
        "python_version": sys.version,
        "source_hashes": hashes,
        "source_hashes_sha256": digest(hashes),
        "provider_modules_loaded": False,
        "public_fetch_modules_loaded": False,
        "watched_fetch_modules_loaded": False,
        "network_modules_loaded_by_canary": False,
    }


def _ancestor_pids() -> set[int]:
    result = {os.getpid()}
    current = os.getppid()
    while current > 1 and current not in result:
        result.add(current)
        observed = subprocess.run(
            ["ps", "-p", str(current), "-o", "ppid="],
            capture_output=True, text=True, timeout=5, check=False,
        )
        if observed.returncode or not observed.stdout.strip().isdigit():
            break
        current = int(observed.stdout.strip())
    return result


def _exact_clear(*, run=subprocess.run) -> dict:
    observed = run(
        ["ps", "-axww", "-o", "pid=,command="], capture_output=True,
        text=True, timeout=10, check=False,
    )
    _require(observed.returncode == 0, "cannot inspect exact process state")
    ancestors = _ancestor_pids() if run is subprocess.run else set()
    pattern = re.compile(
        r"(?:^|\s)--cycle-id(?:=|\s+)" + re.escape(CANARY_ID) + r"(?:\s|$)"
    )
    matches = []
    for line in observed.stdout.splitlines():
        parts = line.strip().split(maxsplit=1)
        if len(parts) == 2 and parts[0].isdigit() and int(parts[0]) not in ancestors:
            if pattern.search(parts[1]):
                matches.append({"pid": int(parts[0]),
                                "command_sha256": hashlib.sha256(
                                    parts[1].encode()).hexdigest()})
    label, present = container_identity(CONTAINER_NAME, run=run)
    _require(not matches and not present,
             "exact canary process or container is already present")
    return {
        "schema": TERMINAL_CLEAR_SCHEMA,
        "canary_id": CANARY_ID,
        "exact_processes": [],
        "exact_containers": [],
        "container_label": label,
    }


def _claim_root(path: Path) -> Path:
    path = Path(path)
    _require(path.is_absolute(), "claim root must be absolute")
    if not path.exists():
        _require(path.parent.resolve(strict=True) == path.parent,
                 "claim root parent must be canonical")
        path.mkdir(mode=0o700)
    _require(path.resolve(strict=True) == path and path.is_dir() and not path.is_symlink(),
             "claim root must be a canonical non-symlink directory")
    return path


def _child_command(args: argparse.Namespace, artifacts: Path, claim: Path,
                   runtime_sha256: str) -> list[str]:
    command = [
        sys.executable, "-I", "-B", str(Path(child_entry.__file__).resolve()),
        "--artifacts", str(artifacts),
        "--supervisor-claim", str(claim),
        "--cycle-id", CANARY_ID,
        "--release-tag", RELEASE_TAG,
        "--release-commit", args.expected_release_commit,
        "--release-tag-object", args.expected_release_tag_object,
        "--source-sha256", args.expected_source_sha256,
        "--runtime-sha256", runtime_sha256,
    ]
    for name in ("decision", "submission", "provenance", "raw_response",
                 "packet", "publication", "result", "review"):
        command.extend(["--d0-" + name.replace("_", "-"),
                        str(getattr(args, "d0_" + name))])
    return command


def _budget_evidence(_task_id: str) -> dict:
    snapshot = {"schema": "market_zero_provider_canary_budget_v1", "state": "none"}
    return {"checked": True, "task_id": CANARY_ID, "state": "none",
            "snapshot_sha256": digest(snapshot)}


def _data_evidence(_task_id: str) -> dict:
    return {"gate_status": "not_applicable", "evidence_sha256": None}


def _supervise(
    *, child: subprocess.Popen, command_sha256: str, artifact_root: Path,
    supervisor_root: Path, release: dict, runtime_sha256: str,
    permanent_claim_sha256: str, log_handle,
) -> dict:
    watchdog = SupervisorWatchdog(supervisor_root / "watchdog")
    watchdog.initialize()
    watchdog.claim_task(
        task_id=CANARY_ID, task_kind="research", stage="bridge_canary",
        owner="outer_supervisor", heartbeat_timeout_seconds=10,
        progress_timeout_seconds=20,
        input_sha256=digest({
            "canary_id": CANARY_ID, "release": release,
            "runtime_sha256": runtime_sha256,
            "request_plan_canonical_sha256": PLAN_SHA256,
            "request_bundle_canonical_sha256": BUNDLE_SHA256,
            "d0_evidence_sha256": child_entry.D0_FILE_SHA256,
        }),
        process_identity={"pid": child.pid, "command_sha256": command_sha256},
        container_identity={"name": CONTAINER_NAME, "label": CONTAINER_NAME},
    )
    parent_sha, parent_present = process_command_sha256(os.getpid())
    _require(parent_present and parent_sha is not None,
             "cannot bind supervisor process identity")
    claim = {
        "schema": child_entry.SUPERVISOR_CLAIM_SCHEMA,
        "cycle_id": CANARY_ID,
        "task_id": CANARY_ID,
        "pid": child.pid,
        "process_command_sha256": command_sha256,
        "supervisor_pid": os.getpid(),
        "supervisor_command_sha256": parent_sha,
        "watchdog_head_sha256": watchdog.snapshot()["head_sha256"],
        "release": release,
        "runtime_sha256": runtime_sha256,
        "request_plan_canonical_sha256": PLAN_SHA256,
        "request_bundle_canonical_sha256": BUNDLE_SHA256,
        "permanent_claim_sha256": permanent_claim_sha256,
        "automatic_retry": False,
    }
    claim_path = supervisor_root / "supervisor-claim.json"
    fresh_json(claim_path, claim)
    watchdog.heartbeat(
        CANARY_ID, material_progress=True,
        progress_sha256=digest({
            "phase": "pre_child_compile",
            "supervisor_claim_sha256": file_hash(claim_path),
        }),
    )
    control = LocalProcessDockerControl(
        budget_evidence=_budget_evidence, data_evidence=_data_evidence)
    deadline = time.monotonic() + 30
    failure: Exception | None = None
    try:
        while child.poll() is None:
            observed, present = process_command_sha256(child.pid)
            _require(present and observed == command_sha256,
                     "child process identity changed while active")
            label, container_present = container_identity(CONTAINER_NAME)
            _require(not container_present and label is None,
                     "zero-provider canary created an exact Docker container")
            _require(time.monotonic() < deadline, "canary child exceeded deadline")
            progress = None
            if artifact_root.exists():
                progress = digest({
                    path.name: file_hash(path)
                    for path in sorted(artifact_root.glob("*.json"))
                    if path.is_file() and not path.is_symlink()
                })
            watchdog.heartbeat(
                CANARY_ID, material_progress=progress is not None,
                progress_sha256=progress,
            )
            time.sleep(0.05)
        exit_code = child.wait(timeout=5)
    except Exception as exc:  # durable failure path; never retry
        failure = exc
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=2)
        exit_code = child.returncode
    log_handle.flush()
    os.fsync(log_handle.fileno())
    state = watchdog.snapshot()
    evidence = control.evidence(state["active_task"], file_hash(supervisor_root / "child.log"))
    terminal = (
        evidence["process"]["present"] is False
        and evidence["container"]["present"] is False
        and evidence["budget"]["state"] == "none"
        and evidence["data"]["gate_status"] == "not_applicable"
    )
    passed = (failure is None and exit_code == 0
              and (artifact_root / "result.json").is_file() and terminal)
    incident_id = None
    if passed:
        watchdog.heartbeat(
            CANARY_ID, material_progress=True,
            progress_sha256=digest({
                "phase": "post_child_compile",
                "child_result_sha256": file_hash(artifact_root / "result.json"),
            }),
        )
        watchdog.close_success(
            CANARY_ID, result_sha256=file_hash(artifact_root / "result.json"))
    else:
        packet = watchdog.report_failure(
            CANARY_ID, classification="worker_error", evidence=evidence)
        incident_id = packet["incident_id"]
        cleanup = control.stop_exact(state["active_task"])
        fresh_json(supervisor_root / "terminal-cleanup.json", cleanup)
        _require(cleanup.get("cleanup_verified") is True,
                 "terminal cleanup was not independently verified")
    final = watchdog.snapshot()
    result = {
        "schema": SUPERVISOR_RESULT_SCHEMA,
        "cycle_id": CANARY_ID,
        "passed": passed,
        "child_exit_code": exit_code,
        "incident_created": incident_id is not None,
        "incident_id": incident_id,
        "budget_state": "none",
        "data_gate_status": "not_applicable",
        "automatic_retry": False,
        "watchdog_head_sha256": final["head_sha256"],
    }
    fresh_json(supervisor_root / "result.json", result)
    return result


def run(args: argparse.Namespace) -> dict:
    publication, _ = _validate_inputs(args)
    _exact_clear()
    _require(Path(args.claim_root) == CLAIM_ROOT,
             "claim root must be the predeclared durable non-cloud path")
    claim_root = _claim_root(args.claim_root)
    claim_path = claim_root / f"{CANARY_ID}.json"
    _require(not claim_path.exists() and not claim_path.is_symlink(),
             "permanent canary ID was already consumed")
    release = {
        "tag": RELEASE_TAG,
        "commit": args.expected_release_commit,
        "tag_object": args.expected_release_tag_object,
        "source_sha256": args.expected_source_sha256,
    }
    runtime = _runtime()
    runtime_sha256 = digest(runtime)
    permanent_claim = {
        "schema": PERMANENT_CLAIM_SCHEMA,
        "canary_id": CANARY_ID,
        "output_root": str(args.root),
        "release": release,
        "runtime_sha256": runtime_sha256,
        "d0_evidence_sha256": dict(child_entry.D0_FILE_SHA256),
        "request_plan_canonical_sha256": PLAN_SHA256,
        "request_bundle_canonical_sha256": BUNDLE_SHA256,
        "automatic_retry": False,
        "same_id_retry_allowed": False,
    }
    fresh_json(claim_path, permanent_claim)
    permanent_claim_sha256 = file_hash(claim_path)

    root = Path(args.root)
    root.mkdir(mode=0o700)
    fresh_json(root / "publication.json", publication)
    fresh_json(root / "runtime.json", runtime)
    supervisor_root = root / "supervisor"
    supervisor_root.mkdir(mode=0o700)
    artifact_root = root / "artifacts"
    supervisor_claim = supervisor_root / "supervisor-claim.json"
    command = _child_command(args, artifact_root, supervisor_claim, runtime_sha256)
    log_handle = (supervisor_root / "child.log").open("xb")
    canary_child = subprocess.Popen(
        command, stdout=log_handle, stderr=subprocess.STDOUT,
        env={"PATH": os.defpath, "LANG": "C", "LC_ALL": "C"},
    )
    try:
        command_sha256 = stable_process_command_sha256(canary_child.pid)
        supervisor_result = _supervise(
            child=canary_child, command_sha256=command_sha256,
            artifact_root=artifact_root, supervisor_root=supervisor_root,
            release=release, runtime_sha256=runtime_sha256,
            permanent_claim_sha256=permanent_claim_sha256,
            log_handle=log_handle,
        )
    except Exception as exc:
        if canary_child.poll() is None:
            canary_child.kill()
            canary_child.wait()
        try:
            terminal = _exact_clear()
            cleanup_verified = True
        except Exception as cleanup_exc:
            terminal = {"cleanup_error_type": type(cleanup_exc).__name__}
            cleanup_verified = False
        fresh_json(supervisor_root / "outer-failure.json", {
            "schema": "market_p0_gate1_source_scope_request_plan_canary_outer_failure_v1",
            "canary_id": CANARY_ID,
            "failure_type": type(exc).__name__,
            "child_exit_code": canary_child.returncode,
            "terminal_evidence": terminal,
            "cleanup_verified": cleanup_verified,
            "id_consumed": True,
            "automatic_retry": False,
        })
        raise
    finally:
        if canary_child.poll() is None:
            canary_child.kill()
            canary_child.wait()
        log_handle.close()
    _require(supervisor_result["passed"] is True,
             "zero-provider bridge canary did not pass")
    terminal_clear = _exact_clear()
    terminal_clear["terminal_cleanup_verified"] = True
    fresh_json(root / "terminal-clear.json", terminal_clear)

    child_result_path = artifact_root / "result.json"
    child_result = _load_json(child_result_path, "child result")
    _require(child_result.get("passed") is True, "child result did not pass")
    snapshot = _load_json(supervisor_root / "watchdog" / "snapshot.json",
                          "watchdog snapshot")
    receipt = {
        "schema": CANARY_SCHEMA,
        "canary_id": CANARY_ID,
        "passed": True,
        "release": release,
        "publication_path": str(root / "publication.json"),
        "publication_sha256": file_hash(root / "publication.json"),
        "runtime_path": str(root / "runtime.json"),
        "runtime_sha256": runtime_sha256,
        "runtime_file_sha256": file_hash(root / "runtime.json"),
        "d0_evidence_sha256": dict(child_entry.D0_FILE_SHA256),
        "request_plan_canonical_sha256": PLAN_SHA256,
        "request_bundle_canonical_sha256": BUNDLE_SHA256,
        "request_bundle_path": str(artifact_root / "request-plan-bundle.json"),
        "request_bundle_file_sha256": file_hash(
            artifact_root / "request-plan-bundle.json"),
        "permanent_claim_path": str(claim_path),
        "permanent_claim_sha256": permanent_claim_sha256,
        "child_result_path": str(child_result_path),
        "child_result_sha256": file_hash(child_result_path),
        "supervisor_claim_path": str(supervisor_claim),
        "supervisor_claim_sha256": file_hash(supervisor_claim),
        "supervisor_result_path": str(supervisor_root / "result.json"),
        "supervisor_result_sha256": file_hash(supervisor_root / "result.json"),
        "watchdog_journal_path": str(supervisor_root / "watchdog" / "journal.jsonl"),
        "watchdog_journal_sha256": file_hash(
            supervisor_root / "watchdog" / "journal.jsonl"),
        "watchdog_snapshot_path": str(supervisor_root / "watchdog" / "snapshot.json"),
        "watchdog_snapshot_sha256": file_hash(
            supervisor_root / "watchdog" / "snapshot.json"),
        "watchdog_head_sha256": snapshot["head_sha256"],
        "terminal_clear_path": str(root / "terminal-clear.json"),
        "terminal_clear_sha256": file_hash(root / "terminal-clear.json"),
        "provider_calls": 0,
        "network_requests": 0,
        "actual_provider_cost_usd": "0",
        "external_bytes_received": 0,
        "public_fetch_performed": False,
        "snapshot_retained": False,
        "data_admitted": False,
        "train_dev_final_read": False,
        "training_or_evaluation_performed": False,
        "automatic_retry": False,
        "terminal_cleanup_verified": True,
    }
    fresh_json(root / "receipt.json", receipt)
    return receipt


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--output", dest="root", required=True, type=Path)
    value.add_argument("--claim-root", required=True, type=Path)
    value.add_argument("--publication", required=True, type=Path)
    value.add_argument("--release-tag", required=True)
    value.add_argument("--expected-source-sha256", required=True)
    value.add_argument("--expected-release-commit", required=True)
    value.add_argument("--expected-release-tag-object", required=True)
    value.add_argument("--expected-request-plan-canonical-sha256", required=True)
    value.add_argument("--d0-decision", required=True, type=Path)
    value.add_argument("--d0-submission", required=True, type=Path)
    value.add_argument("--d0-provenance", required=True, type=Path)
    value.add_argument("--d0-raw-response", required=True, type=Path)
    value.add_argument("--d0-packet", required=True, type=Path)
    value.add_argument("--d0-publication", required=True, type=Path)
    value.add_argument("--d0-result", required=True, type=Path)
    value.add_argument("--d0-review", required=True, type=Path)
    expected_options = {
        "decision": "--expected-d0-decision-file-sha256",
        "submission": "--expected-d0-submission-file-sha256",
        "provenance": "--expected-d0-provenance-file-sha256",
        "raw_response": "--expected-d0-raw-response-sha256",
        "packet": "--expected-d0-packet-file-sha256",
        "publication": "--expected-d0-publication-file-sha256",
        "result": "--expected-d0-result-file-sha256",
        "review": "--expected-d0-review-file-sha256",
    }
    for name, option in expected_options.items():
        value.add_argument(option, dest="expected_d0_" + name + "_sha256",
                           required=True)
    return value


def main() -> None:
    print(json.dumps(run(parser().parse_args()), sort_keys=True))


if __name__ == "__main__":
    main()
