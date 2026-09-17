"""Read-only publication gate for a future Market RSI A/B protocol canary.

This module never creates a tag, pushes code, reads credentials or dispatches
E2B. A current source snapshot and an annotated tag on the user's origin are
both required. It is not a substitute for a passing live isolation canary.
"""
from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
import subprocess
import tarfile

from market_rsi import digest, file_hash
from data_scientist_harness import release as data_harness_release


REPO = Path(__file__).resolve().parents[3]
PREFIX = "research/market_rsi"
ORIGIN = "https://github.com/Estelle-LH/RSIBench-Data.git"
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
)
DATA_HARNESS_FILES = tuple(str(path.relative_to(REPO / PREFIX))
                           for path in data_harness_release.source_files(REPO / PREFIX))
FILES = tuple(sorted(set(PROTOCOL_FILES) | set(DATA_HARNESS_FILES)))


def _git(*args: str) -> bytes:
    try:
        completed = subprocess.run(
            ["git", "-C", str(REPO), *args], capture_output=True, timeout=20,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}, check=False)
    except subprocess.TimeoutExpired as exc:
        raise ValueError("publication check timed out") from exc
    if completed.returncode:
        # Remote errors may contain sensitive URL material; do not echo them.
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
    """Verify exact current bytes against one published annotated Git tag."""
    if (not isinstance(tag, str) or not tag.startswith("market-rsi-protocol-v")
            or len(tag) > 96 or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789.-"
                                     for c in tag)):
        raise ValueError("exact protocol release tag required")
    hashes = source_hashes()
    if digest(hashes) != expected_source_sha256:
        raise ValueError("current protocol source differs from expected manifest")
    if _git("remote", "get-url", "origin").decode().strip() != ORIGIN:
        raise ValueError("origin is not the authorized user fork")
    paths = [f"{PREFIX}/{name}" for name in FILES]
    if _git("status", "--porcelain", "--untracked-files=all", "--", *paths).strip():
        raise ValueError("uncommitted protocol source")
    commit = _git("rev-parse", "HEAD").decode().strip()
    if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        raise ValueError("full release commit required")
    committed = {}
    for start in range(0, len(paths), 16):
        archive = _git("archive", "--format=tar", commit, "--", *paths[start:start + 16])
        with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
            for member in stream:
                if member.isfile():
                    name = member.name.removeprefix(PREFIX + "/")
                    if name in committed:
                        raise ValueError("duplicate Git source")
                    committed[name] = hashlib.sha256(stream.extractfile(member).read()).hexdigest()
    if committed != hashes:
        raise ValueError("release commit differs from current protocol source")
    ref = "refs/tags/" + tag
    if _git("cat-file", "-t", ref).decode().strip() != "tag":
        raise ValueError("annotated release tag required")
    if _git("rev-parse", ref + "^{commit}").decode().strip() != commit:
        raise ValueError("release tag points to another commit")
    tag_object = _git("rev-parse", ref).decode().strip()
    remote = _git("ls-remote", "--exit-code", "origin", ref, ref + "^{}").decode().splitlines()
    observed = {parts[1]: parts[0] for line in remote if len(parts := line.split()) == 2}
    if observed != {ref: tag_object, ref + "^{}": commit}:
        raise ValueError("release tag is not published on the authorized origin")
    return {"schema": "market_rsi_protocol_publication_v1", "origin": ORIGIN,
            "tag": tag, "commit": commit, "tag_object": tag_object,
            "source_sha256": digest(hashes), "source_hashes": hashes,
            "isolation_proven": False, "model_authorship_proven": False}
