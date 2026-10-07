"""Read-only publication gate for the Market RSI A/B protocol source.

This module never creates a tag, pushes code, reads credentials or dispatches
a sandbox. A current source snapshot and an annotated tag on the user's origin
are both required. It is not a substitute for a passing live isolation canary.
"""
from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
from urllib.parse import urlsplit

from market_rsi import digest, file_hash
from data_scientist_harness import release as data_harness_release


REPO = Path(__file__).resolve().parents[3]
PREFIX = "research/market_rsi"
ORIGIN = "https://github.com/Estelle-LH/market-rsi.git"
PROTOCOL_FILES = (
    "market_rsi.py", "paid_budget.py",
    "supervisor_harness/global_state_gate.py",
    "supervisor_harness/research_cycle_gate.py",
    "supervisor_harness/run_research_cycle_fixture.py",
    "supervisor_harness/controller_tool_adapter.py",
    "supervisor_harness/controller_mailbox.py",
    "supervisor_harness/broker_handoff.py",
    "supervisor_harness/researcher_guest_worker.py",
    "supervisor_harness/e2b_researcher_execution.py",
    "supervisor_harness/protocol_network_probe.py",
    "supervisor_harness/peer_marker_server.py",
    "supervisor_harness/e2b_role_network_component.py",
    "supervisor_harness/protocol_source_release.py",
    "supervisor_harness/protocol_canary_entry.py",
    "supervisor_harness/protocol_canary_runner.py",
    # The old two-E2B CLI is retired. A new protocol release must attest the
    # executable one-B transport and its parent-owned admission/accounting.
    "supervisor_harness/directional_handoff.py",
    "supervisor_harness/directional_guest_worker.py",
    "supervisor_harness/one_b_live_adapter.py",
    "supervisor_harness/one_b_canary_entry.py",
    "supervisor_harness/one_b_canary_runner.py",
    # The later user-directed local B backend supersedes new E2B dispatch.
    "supervisor_harness/local_b_container.py",
    "supervisor_harness/local_b_canary.py",
    # The offline controller-to-B admission path must be bound to the same
    # immutable release before a live adapter can be reviewed. These modules
    # currently accept fake backends only; inclusion is not live admission.
    "supervisor_harness/frozen_glm_first_response.py",
    "supervisor_harness/offline_a_to_b_driver.py",
    "supervisor_harness/local_b_containment_canary.py",
    "supervisor_harness/local_b_containment_guest.py",
    "supervisor_harness/bottleneck_gate.py",
    "supervisor_harness/bounded_live_adapter_v2.py",
    "supervisor_harness/bounded_live_entry_v1.py",
    "supervisor_harness/live_runtime_requirements_v1.txt",
    "supervisor_harness/bounded_live_outer_runner_v3.py",
    # Outer liveness and exact-cleanup enforcement is part of the executable
    # paid boundary, not an optional dashboard concern.
    "supervisor_harness/supervisor_watchdog.py",
    "supervisor_harness/supervisor_watchdog_monitor.py",
    "supervisor_harness/supervisor_watchdog_local_control.py",
    "supervisor_harness/bounded_live_supervisor_parent_v1.py",
    # Both terminal outcomes need immutable acceptance executables.  Otherwise
    # published production bytes could be admitted by an unversioned canary.
    "supervisor_harness/run_bounded_live_supervisor_parent_canary.py",
    "supervisor_harness/run_bounded_live_supervisor_parent_success_canary.py",
    # Gate 1 data-source selection is a separate immutable decision boundary.
    # The model sees aggregate evidence only and returns one terminal choice:
    # a bounded existing plan or a non-executable novel proposal. Trusted code
    # alone resolves URLs and controls any later public snapshot.
    "supervisor_harness/build_p0_gate1_controller_packet.py",
    "supervisor_harness/p0_gate1_research_contract.py",
    "supervisor_harness/p0_data_gap_proposal.py",
    "supervisor_harness/prospective_source_scope_decision.py",
    "supervisor_harness/test_prospective_source_scope_decision.py",
    # The reviewed D0-to-request bridge is offline and non-executing, but its
    # exact registry mapping and adversarial tests must share release bytes.
    "supervisor_harness/p0_gate1_source_scope_request_plan.py",
    "supervisor_harness/test_p0_gate1_source_scope_request_plan.py",
    # The v0.1.26 bridge canary executes the exact immutable D0 compilation
    # without importing fetch/network/provider code.  Its parent, verifier and
    # adversarial tests are controlled source, not private run evidence.
    "supervisor_harness/p0_gate1_source_scope_request_plan_canary_child.py",
    "supervisor_harness/run_p0_gate1_source_scope_request_plan_canary.py",
    "supervisor_harness/source_scope_request_plan_canary_receipt.py",
    "supervisor_harness/test_p0_gate1_source_scope_request_plan_canary_child.py",
    "supervisor_harness/test_run_p0_gate1_source_scope_request_plan_canary.py",
    "supervisor_harness/test_source_scope_request_plan_canary_receipt.py",
    "supervisor_harness/gate1_canary_receipt.py",
    "supervisor_harness/test_gate1_canary_receipt.py",
    "supervisor_harness/p0_gate1_controller_adapter.py",
    "supervisor_harness/p0_gate1_controller_outer.py",
    "supervisor_harness/p0_gate1_controller_live_entry.py",
    "supervisor_harness/p0_gate1_controller_supervisor_parent.py",
    "supervisor_harness/run_p0_gate1_controller_adapter_canary.py",
    "supervisor_harness/run_p0_gate1_controller_outer_canary.py",
    "supervisor_harness/run_p0_gate1_packet_preflight_canary.py",
    "supervisor_harness/p0_gate1_controller_cli_canary_child.py",
    "supervisor_harness/run_p0_gate1_controller_production_cli_canary.py",
    "supervisor_harness/p0_gate1_public_fetch.py",
    "supervisor_harness/p0_gate1_watched_fetch.py",
    # The only live source-scope path is a distinct task/admission language
    # bound to the reviewed release, runtime, bridge canary, dual authority,
    # permanent global claim and outer watchdog.  Include pure terminal replay
    # plus every fake-transport/adversarial test; exclude plans/logs/run bytes.
    "supervisor_harness/p0_gate1_source_scope_fetch_adapter.py",
    "supervisor_harness/p0_gate1_source_scope_watched_fetch_child.py",
    "supervisor_harness/run_p0_gate1_source_scope_watched_fetch.py",
    "supervisor_harness/source_scope_fetch_receipt.py",
    "supervisor_harness/test_p0_gate1_source_scope_fetch_adapter.py",
    "supervisor_harness/test_run_p0_gate1_source_scope_watched_fetch.py",
    "supervisor_harness/test_source_scope_fetch_receipt.py",
    "supervisor_harness/test_p0_gate1_source_scope_fetch_integration.py",
    "supervisor_harness/test_p0_gate1_public_fetch.py",
    "supervisor_harness/test_p0_gate1_watched_fetch.py",
    "supervisor_harness/test_protocol_source_release.py",
    # The bounded existing-plan lane is executable only when its compiler,
    # Train-only materializer and request builder share the published bytes.
    # Include the corresponding zero-network canary and fixtures as well.
    "supervisor_harness/p0_gate1_sample_materializer.py",
    "supervisor_harness/p0_gate1_trade_query.py",
    "supervisor_harness/p0_gate1_plan_compiler.py",
    "supervisor_harness/p0_gate1_executable_plan_canary_fixtures.py",
    "supervisor_harness/run_p0_gate1_executable_plan_canary.py",
    # Reviewed P0 candidate-admission components are controlled together.
    # Their inclusion changes the next source manifest only; it does not move
    # published v0.1.21, authorize a provider call, or admit Train data.
    "supervisor_harness/build_2024_train_candidate_ledger.py",
    "supervisor_harness/test_build_2024_train_candidate_ledger.py",
    "supervisor_harness/p0_2024_outcome_orientation.py",
    "supervisor_harness/test_p0_2024_outcome_orientation.py",
    "supervisor_harness/formal_train_admission.py",
    "supervisor_harness/test_formal_train_admission.py",
    "supervisor_harness/test_supervisor_watchdog.py",
    "supervisor_harness/p0_polymarket_v2_cursor_acquisition.py",
    "supervisor_harness/test_p0_polymarket_v2_cursor_acquisition.py",
    "supervisor_harness/p0_candidate_admission_integration.py",
    "supervisor_harness/test_p0_candidate_admission_integration.py",
)
DATA_HARNESS_FILES = tuple(str(path.relative_to(REPO / PREFIX))
                           for path in data_harness_release.source_files(REPO / PREFIX))
FILES = tuple(sorted(set(PROTOCOL_FILES) | set(DATA_HARNESS_FILES)))


def _git(*args: str) -> bytes:
    env = {
        **os.environ,
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
    }
    try:
        completed = subprocess.run(
            ["git", "-c", "core.fsmonitor=false", "-C", str(REPO), *args],
            capture_output=True, timeout=20, env=env, check=False)
    except subprocess.TimeoutExpired as exc:
        raise ValueError("publication check timed out") from exc
    if completed.returncode:
        # Remote errors may contain sensitive URL material; do not echo them.
        raise ValueError("Git publication check failed")
    return completed.stdout


def _remote_transport(origin: str) -> str:
    """Return the one transport that a literal publication origin needs."""
    if (not isinstance(origin, str) or not origin
            or "\0" in origin or "\n" in origin):
        raise ValueError("invalid publication origin")
    parsed = urlsplit(origin)
    if (parsed.scheme == "https" and parsed.netloc and not parsed.username
            and not parsed.password and not parsed.query and not parsed.fragment):
        return "https"
    if not parsed.scheme and Path(origin).is_absolute():
        return "file"
    raise ValueError("unsupported publication origin transport")


def _git_remote(*refs: str) -> bytes:
    """Read literal remote refs without repository or ambient Git config.

    Private-origin authentication belongs to the outer Supervisor release
    operation.  This verifier intentionally inherits neither credential
    helpers nor repository/global/system/environment URL rewrites.
    """
    transport = _remote_transport(ORIGIN)
    git_binary = shutil.which("git", path=os.defpath)
    if not git_binary:
        raise ValueError("Git publication check failed")
    outside_repo = Path(os.devnull).resolve().parent
    env = {
        "PATH": os.defpath,
        "LANG": "C",
        "LC_ALL": "C",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CEILING_DIRECTORIES": str(outside_repo),
        "GIT_TERMINAL_PROMPT": "0",
        "GCM_INTERACTIVE": "never",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_NO_REPLACE_OBJECTS": "1",
    }
    command = [
        git_binary,
        "-c", "credential.helper=",
        "-c", "credential.interactive=never",
        "-c", "core.askPass=",
        "-c", "http.followRedirects=false",
        "-c", "protocol.allow=never",
        "-c", f"protocol.{transport}.allow=always",
        "ls-remote", "--exit-code", "--", ORIGIN, *refs,
    ]
    try:
        completed = subprocess.run(
            command, cwd=outside_repo, capture_output=True, timeout=20,
            env=env, check=False)
    except subprocess.TimeoutExpired as exc:
        raise ValueError("publication check timed out") from exc
    if completed.returncode:
        raise ValueError("Git publication check failed")
    return completed.stdout


def source_hashes() -> dict[str, str]:
    root = REPO / PREFIX
    hashes = {}
    for name in FILES:
        path = root / name
        if path.is_symlink() or not path.is_file() or path.resolve() != path:
            raise ValueError("missing or noncanonical protocol source")
        hashes[name] = file_hash(path)
    return hashes


def verify_published(*, tag: str, expected_source_sha256: str) -> dict:
    """Verify exact current protocol bytes against one published annotated tag.

    Repository HEAD may contain later documentation-only commits.  Admission is
    bound to the tagged protocol bytes, not to unrelated repository history.
    Any change to a controlled protocol file still fails closed.
    """
    if (not isinstance(tag, str) or not tag.startswith("market-rsi-protocol-v")
            or len(tag) > 96 or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789.-"
                                     for c in tag)):
        raise ValueError("exact protocol release tag required")
    hashes = source_hashes()
    if digest(hashes) != expected_source_sha256:
        raise ValueError("current protocol source differs from expected manifest")
    raw_origins = _git(
        "config", "--local", "--no-includes", "--get-all",
        "remote.origin.url").decode().splitlines()
    if raw_origins != [ORIGIN]:
        raise ValueError("origin is not the authorized standalone repository")
    paths = [f"{PREFIX}/{name}" for name in FILES]
    if _git("status", "--porcelain", "--untracked-files=all", "--", *paths).strip():
        raise ValueError("uncommitted protocol source")
    head = _git("rev-parse", "HEAD").decode().strip()
    if len(head) != 40 or any(c not in "0123456789abcdef" for c in head):
        raise ValueError("full current commit required")
    ref = "refs/tags/" + tag
    if _git("cat-file", "-t", ref).decode().strip() != "tag":
        raise ValueError("annotated release tag required")
    release_commit = _git("rev-parse", ref + "^{commit}").decode().strip()
    if (len(release_commit) != 40
            or any(c not in "0123456789abcdef" for c in release_commit)):
        raise ValueError("full release commit required")
    tagged = {}
    for start in range(0, len(paths), 16):
        archive = _git(
            "archive", "--format=tar", release_commit,
            "--", *paths[start:start + 16])
        with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
            for member in stream:
                if member.isfile():
                    name = member.name.removeprefix(PREFIX + "/")
                    if name in tagged:
                        raise ValueError("duplicate Git source")
                    tagged[name] = hashlib.sha256(
                        stream.extractfile(member).read()).hexdigest()
    if tagged != hashes:
        raise ValueError("release tag differs from current protocol source")
    tag_object = _git("rev-parse", ref).decode().strip()
    remote = _git_remote(ref, ref + "^{}").decode().splitlines()
    observed = {parts[1]: parts[0] for line in remote if len(parts := line.split()) == 2}
    if observed != {ref: tag_object, ref + "^{}": release_commit}:
        raise ValueError("release tag is not published on the authorized origin")
    return {"schema": "market_rsi_protocol_publication_v1", "origin": ORIGIN,
            "tag": tag, "commit": release_commit, "tag_object": tag_object,
            "source_sha256": digest(hashes), "source_hashes": hashes,
            "isolation_proven": False, "model_authorship_proven": False}
