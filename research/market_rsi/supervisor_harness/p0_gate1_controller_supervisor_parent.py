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


CANARY_CHILD_ENTRY = Path(__file__).with_name(
    "p0_gate1_controller_cli_canary_child.py").resolve()
CANARY_RELEASE_TAG = "market-rsi-protocol-v-synthetic-cli-canary"


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
    if child_entry is not None and (
            child_path != CANARY_CHILD_ENTRY
            or args.release_tag != CANARY_RELEASE_TAG):
        raise ValueError("only the exact synthetic Gate 1 canary child is allowed")
    command = [sys.executable, str(child_path)]
    paths = (
        "root", "claim_root", "global_state_root", "decision_doc",
        "budget_root", "packet", "runtime_receipt", "env_file",
        "tokenizer_cache",
    )
    strings = (
        "experiment_id", "budget_cap_usd", "cycle_id",
        "expected_packet_file_sha256", "expected_packet_canonical_sha256",
        "expected_head_sha256",
        "expected_decision_sha256", "prior_canary_sha256",
        "release_tag", "expected_source_sha256",
    )
    for name in paths:
        command.extend(["--" + name.replace("_", "-"),
                        str(getattr(args, name))])
    command.extend(["--supervisor-claim", str(claim)])
    for name in strings:
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


def run(args, *, child_entry: Path | None = None) -> dict:
    identifier(args.cycle_id)
    _preflight_packet(args)
    supervisor_root = Path(args.supervisor_root)
    if supervisor_root.exists() or supervisor_root.is_symlink():
        raise FileExistsError("fresh Gate 1 Supervisor root required")
    supervisor_root.mkdir(parents=True, mode=0o700)
    claim = supervisor_root / "supervisor-claim.json"
    command = _child_command(args, claim, child_entry=child_entry)
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
