"""Outer Supervisor process for one Gate 1 Controller decision child."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from market_rsi import digest, file_hash, identifier
from supervisor_harness import bounded_live_supervisor_parent_v1 as supervisor
from supervisor_harness import p0_gate1_controller_live_entry as entry
from supervisor_harness import protocol_source_release


CANARY_CHILD_ENTRY = Path(__file__).with_name(
    "p0_gate1_controller_cli_canary_child.py").resolve()
CANARY_RELEASE_TAG = entry.gate1_canary_receipt.LEGACY_SYNTHETIC_RELEASE_TAG
_FIRST_CANARY_BOOTSTRAP_CAPABILITY = object()
_VERIFIED_PUBLICATION_CONSTRUCTOR = object()
# A valid provider sample may use the adapter's complete 60-second deadline.
# Progress supervision must not classify that allowed interval as a stall.
PROGRESS_TIMEOUT_SECONDS = entry.adapter.SAMPLE_TIMEOUT_SECONDS + 30


class _VerifiedFirstCanaryPublication:
    """Process-local evidence returned only after ``verify_published`` passes."""

    __slots__ = ("_raw",)

    def __init__(self, publication: dict, constructor: object):
        if constructor is not _VERIFIED_PUBLICATION_CONSTRUCTOR:
            raise TypeError("verified first-canary publication is factory-only")
        self._raw = json.dumps(
            publication, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False)

    def value(self) -> dict:
        return json.loads(self._raw)


def verified_first_canary_publication(
        *, release_tag: str,
        expected_source_sha256: str) -> _VerifiedFirstCanaryPublication:
    """Perform the credential-free publication check before any run mutation."""
    publication = protocol_source_release.verify_published(
        tag=release_tag, expected_source_sha256=expected_source_sha256)
    publication = entry.gate1_canary_receipt.validate_first_canary_publication(
        publication, expected_tag=release_tag,
        expected_source_sha256=expected_source_sha256,
        child_entry=CANARY_CHILD_ENTRY)
    current = protocol_source_release.source_hashes()
    if (publication["source_hashes"] != current
            or digest(current) != expected_source_sha256):
        raise ValueError("verified publication is stale or forged")
    return _VerifiedFirstCanaryPublication(
        publication, _VERIFIED_PUBLICATION_CONSTRUCTOR)


def _publication_from_token(
        token: object | None) -> dict:
    if type(token) is not _VerifiedFirstCanaryPublication:
        raise ValueError("exact verified first-canary publication required")
    publication = token.value()
    return entry.gate1_canary_receipt.validate_first_canary_publication(
        publication, expected_tag=publication.get("tag"),
        expected_source_sha256=publication.get("source_sha256"),
        child_entry=CANARY_CHILD_ENTRY)


def _child_command(args, claim: Path, *, child_entry: Path | None = None) -> list[str]:
    """Build the exact child CLI; canaries may supply one immutable fake.

    The production parser exposes no child-entry override. The optional
    argument exists only so a zero-provider acceptance can exercise this
    parent's real subprocess and Supervisor-claim boundary.
    """
    child_path = (Path(entry.__file__).resolve() if child_entry is None
                  else Path(child_entry))
    if (child_path.is_symlink() or not child_path.is_file()
            or child_path.resolve() != child_path):
        raise ValueError("Gate 1 child entry must be a regular canonical file")
    if child_entry is not None and child_path != CANARY_CHILD_ENTRY:
        raise ValueError("only the exact Gate 1 canary child is allowed")
    command = [sys.executable, str(child_path)]
    paths = (
        "root", "claim_root", "global_state_root", "decision_doc",
        "budget_root", "packet", "runtime_receipt", "env_file",
        "tokenizer_cache", "prior_canary_receipt",
    )
    strings = (
        "experiment_id", "budget_cap_usd", "cycle_id",
        "expected_packet_file_sha256", "expected_packet_canonical_sha256",
        "expected_head_sha256",
        "expected_decision_sha256", "prior_canary_sha256",
        "release_tag", "expected_release_commit",
        "expected_release_tag_object", "expected_source_sha256",
    )
    for name in paths:
        command.extend(["--" + name.replace("_", "-"),
                        str(getattr(args, name))])
    if getattr(args, "catalog", None) is not None:
        command.extend(["--catalog", str(args.catalog)])
    command.extend(["--supervisor-claim", str(claim)])
    for name in strings:
        command.extend(["--" + name.replace("_", "-"),
                        str(getattr(args, name))])
    for name in ("expected_catalog_file_sha256", "catalog_commitment_id"):
        if getattr(args, name, None) is not None:
            command.extend(["--" + name.replace("_", "-"),
                            str(getattr(args, name))])
    return command


def _preflight_packet(args) -> dict:
    """Verify exact production packet bytes and content before child launch."""
    packet_path = Path(args.packet)
    packet = entry.shared_entry._regular_json(packet_path)
    packet = entry.adapter._packet(packet)
    expected_file = entry.shared_outer._sha(
        args.expected_packet_file_sha256, "Gate 1 packet file")
    expected_canonical = entry.shared_outer._sha(
        args.expected_packet_canonical_sha256, "Gate 1 canonical packet")
    observed_file = file_hash(packet_path)
    observed_canonical = digest(packet)
    if observed_file != expected_file:
        raise ValueError("Gate 1 packet file differs from frozen hash")
    if observed_canonical != expected_canonical:
        raise ValueError("Gate 1 canonical packet differs from frozen hash")
    return {
        "packet_file_sha256": observed_file,
        "packet_canonical_sha256": observed_canonical,
    }


def _preflight_canary(
        args, *, child_entry: Path | None = None,
        bootstrap_capability: object | None = None,
        verified_publication: object | None = None) -> dict:
    """Verify exact current canary evidence before creating a child process."""
    runtime = entry.shared_entry._regular_json(args.runtime_receipt)
    if bootstrap_capability is not None:
        if bootstrap_capability is not _FIRST_CANARY_BOOTSTRAP_CAPABILITY:
            raise ValueError("invalid first-canary bootstrap capability")
        publication = _publication_from_token(verified_publication)
        current = protocol_source_release.source_hashes()
        if (publication["source_hashes"] != current
                or digest(current) != publication["source_sha256"]):
            raise ValueError("verified publication became stale before launch")
        if (child_entry != CANARY_CHILD_ENTRY
                or args.release_tag != publication["tag"]
                or args.expected_release_commit != publication["commit"]
                or args.expected_release_tag_object !=
                publication["tag_object"]
                or args.expected_source_sha256 !=
                publication["source_sha256"]):
            raise ValueError("invalid first-canary bootstrap capability")
        verification = entry.gate1_canary_receipt.verify_first_canary_bootstrap(
            args.prior_canary_receipt,
            expected_bootstrap_sha256=args.prior_canary_sha256,
            expected_source_sha256=args.expected_source_sha256,
            expected_runtime_sha256=digest(runtime),
            expected_release_tag=args.release_tag,
            expected_release_commit=args.expected_release_commit,
            expected_release_tag_object=args.expected_release_tag_object,
            expected_child_entry=CANARY_CHILD_ENTRY,
        )
        if verification.get("publication") != publication:
            raise ValueError("bootstrap proof differs from verified publication")
        return verification
    if verified_publication is not None:
        raise ValueError("verified publication is bootstrap-only")
    return entry.gate1_canary_receipt.verify_gate1_canary_receipt(
        args.prior_canary_receipt,
        expected_receipt_sha256=args.prior_canary_sha256,
        expected_source_sha256=args.expected_source_sha256,
        expected_runtime_sha256=digest(runtime),
        expected_release_tag=args.release_tag,
        expected_release_commit=args.expected_release_commit,
        expected_release_tag_object=args.expected_release_tag_object,
    )


def run(args, *, child_entry: Path | None = None,
        bootstrap_capability: object | None = None,
        verified_publication: object | None = None) -> dict:
    identifier(args.cycle_id)
    _preflight_packet(args)
    if child_entry is None:
        # A supplied catalog must be reviewed and exact before creating a
        # child. No catalog is permitted only for review-only Controller
        # outcomes; the outer review rejects fixed-trade plans without one.
        # The synthetic canary child is never exposed by this production CLI.
        entry._reviewed_catalog(args)
    _preflight_canary(
        args, child_entry=child_entry,
        bootstrap_capability=bootstrap_capability,
        verified_publication=verified_publication)
    supervisor_root = Path(args.supervisor_root)
    if supervisor_root.exists() or supervisor_root.is_symlink():
        raise FileExistsError("fresh Gate 1 Supervisor root required")
    claim = supervisor_root / "supervisor-claim.json"
    command = _child_command(args, claim, child_entry=child_entry)
    supervisor_root.mkdir(parents=True, mode=0o700)
    log_handle = (supervisor_root / "child.log").open("xb")
    child = subprocess.Popen(command, stdout=log_handle,
                             stderr=subprocess.STDOUT)
    try:
        command_sha = supervisor.stable_process_command_sha256(child.pid)
        return supervisor.supervise_started(
            child=child,
            cycle_id=args.cycle_id,
            command_sha256=command_sha,
            # Gate 1 has no B container. This exact, task-derived name must
            # remain absent and gives failure cleanup a bounded target.
            container_name="market-rsi-b-" + args.cycle_id,
            artifact_root=args.root,
            supervisor_root=supervisor_root,
            budget_evidence=lambda task_id: supervisor._budget_reader(
                args.budget_root, task_id),
            data_evidence=lambda _task_id: {
                "gate_status": "not_applicable",
                "evidence_sha256": None,
            },
            progress_timeout_seconds=PROGRESS_TIMEOUT_SECONDS,
            terminal_budget_states=frozenset({"settled"}),
        )
    finally:
        log_handle.close()
        if child.poll() is None:
            child.kill()
            child.wait()


def parser() -> argparse.ArgumentParser:
    value = entry.parser(require_supervisor_claim=False)
    value.description = "Run one Gate 1 Controller decision under Supervisor"
    value.add_argument("--supervisor-root", required=True, type=Path)
    return value


if __name__ == "__main__":
    print(json.dumps(run(parser().parse_args()), sort_keys=True))
