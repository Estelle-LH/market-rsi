"""Trusted one-shot CLI for the published Controller -> local-B canary.

This entry performs a read-only duplicate check before loading the paid
credential.  The outer runner repeats every mutable gate after reservation and
immediately before its sole dispatch.  There is deliberately no retry loop.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import time

from dotenv import dotenv_values

from codex_glm_provider import TinkerGLMBackend
from market_rsi import canonical, digest, identifier, load_json
from paid_budget import PaidBudget
from supervisor_harness import bounded_live_adapter_v2 as adapter
from supervisor_harness import bounded_live_outer_runner_v3 as outer
from supervisor_harness.global_state_gate import SupervisorGlobalState
from supervisor_harness.supervisor_watchdog_local_control import (
    process_command_sha256,
)


SUPERVISOR_CLAIM_SCHEMA = "market_bounded_live_supervisor_claim_v1"


def _run(command: list[str]) -> str:
    result = subprocess.run(
        command, check=True, capture_output=True, text=True, timeout=10)
    return result.stdout


def _ancestor_pids(rows: list[tuple[int, int, str]]) -> set[int]:
    parents = {pid: ppid for pid, ppid, _command in rows}
    excluded = {os.getpid()}
    current = os.getpid()
    while current in parents and parents[current] > 0 and parents[current] not in excluded:
        current = parents[current]
        excluded.add(current)
    return excluded


def exact_clear(cycle_id: str) -> dict:
    """Fail closed if another process or the exact local-B container exists."""
    rows = []
    for line in _run(["ps", "-axww", "-o", "pid=,ppid=,command="]).splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) != 3:
            continue
        try:
            rows.append((int(parts[0]), int(parts[1]), parts[2]))
        except ValueError:
            raise RuntimeError("unparseable process inventory")
    excluded = _ancestor_pids(rows)
    process_ids = sorted(
        str(pid) for pid, _ppid, command in rows
        if pid not in excluded and cycle_id in command)

    container_name = "market-rsi-b-" + cycle_id
    container_ids = sorted(filter(None, (
        item.strip() for item in _run([
            "docker", "ps", "-aq", "--filter", f"name=^/{container_name}$",
        ]).splitlines())))
    return {
        "schema": outer.PREFLIGHT_SCHEMA,
        "cycle_id": cycle_id,
        "clear": not process_ids and not container_ids,
        "matching_process_ids": process_ids,
        "matching_container_ids": container_ids,
    }


def _regular_json(path: Path) -> dict:
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ValueError("unsafe or missing JSON input")
    value = load_json(path)
    if not isinstance(value, dict):
        raise ValueError("JSON input must be an object")
    return value


def _supervisor_claim(path: Path, cycle_id: str, *, timeout_seconds: float = 10.0,
                      monotonic=time.monotonic, sleep=time.sleep) -> dict:
    """Require the outer monitor to bind this exact process before secrets."""
    path = Path(path)
    deadline = monotonic() + timeout_seconds
    while not path.exists() and not path.is_symlink() and monotonic() < deadline:
        sleep(0.02)
    if not path.exists() or path.is_symlink():
        raise ValueError("exact outer Supervisor claim is missing or changed")
    claim = _regular_json(path)
    required = {"schema", "cycle_id", "task_id", "pid", "supervisor_pid",
                "process_command_sha256", "watchdog_head_sha256",
                "supervisor_command_sha256", "automatic_retry"}
    observed, present = process_command_sha256(os.getpid())
    supervisor_observed, supervisor_present = process_command_sha256(os.getppid())
    if (set(claim) != required
            or claim.get("schema") != SUPERVISOR_CLAIM_SCHEMA
            or claim.get("cycle_id") != cycle_id
            or claim.get("task_id") != cycle_id
            or claim.get("pid") != os.getpid()
            or claim.get("supervisor_pid") != os.getppid()
            or not present
            or claim.get("process_command_sha256") != observed
            or not supervisor_present
            or claim.get("supervisor_command_sha256") != supervisor_observed
            or not isinstance(claim.get("watchdog_head_sha256"), str)
            or len(claim["watchdog_head_sha256"]) != 64
            or any(c not in "0123456789abcdef"
                   for c in claim["watchdog_head_sha256"])
            or claim.get("automatic_retry") is not False):
        raise ValueError("exact outer Supervisor claim is missing or changed")
    return claim


def _preflight_encoding(backend: TinkerGLMBackend, packet: dict) -> dict:
    """Exercise the complete local tokenizer path before budget dispatch."""
    request = {
        "messages": [
            {"role": "system", "content": adapter.SYSTEM_PROMPT},
            {"role": "user", "content": canonical(packet)},
        ],
        "tools": [],
    }
    encoded = backend.encode(request)
    input_tokens = adapter._validate_encoding(encoded)
    if adapter.cost(input_tokens, adapter.MAX_OUTPUT_TOKENS) > adapter.MAX_COST_UPPER_USD:
        raise ValueError("provider cost upper bound exceeds adapter cap")
    return encoded


def run(args) -> dict:
    """Run exactly one published canary; no credential is read before dry gates."""
    identifier(args.cycle_id)
    outer._sha(args.prior_canary_sha256, "prior canary")
    if (args.root.name != args.cycle_id or args.root.exists()
            or args.root.is_symlink()
            or not args.adapter_claim_root.is_dir()
            or args.adapter_claim_root.is_symlink()
            or args.root.resolve() == args.adapter_claim_root.resolve()):
        raise ValueError("fresh named outer root and separate claim registry required")
    packet = _regular_json(args.packet)
    runtime = _regular_json(args.runtime_receipt)
    state = SupervisorGlobalState(args.global_state_root, args.decision_doc)
    budget = PaidBudget(args.budget_root)

    # Dry admission happens before the credential is read.
    outer._publication(args.release_tag, args.expected_source_sha256)
    outer._runtime(runtime)
    packet = outer._packet(packet, args.cycle_id)
    if digest(packet) != outer._sha(
            args.expected_packet_sha256, "frozen public packet"):
        raise ValueError("public synthetic packet differs from frozen hash")
    outer._state_snapshot(
        state, args.cycle_id, args.expected_head_sha256,
        args.expected_decision_sha256)
    outer._budget_snapshot(
        budget, args.budget_root, args.experiment_id, args.budget_cap_usd,
        args.cycle_id)
    outer._clear(exact_clear, args.cycle_id)
    # The claim is intentionally the last dry gate before credential access.
    # It binds the exact live PID/command to a durable watchdog head.
    _supervisor_claim(args.supervisor_claim, args.cycle_id)
    key = dotenv_values(args.env_file).get("TINKER_API_KEY")
    backend = TinkerGLMBackend(key, args.tokenizer_cache)
    _preflight_encoding(backend, packet)
    return outer.run_outer(
        root=args.root,
        adapter_claim_root=args.adapter_claim_root,
        state=state,
        budget=budget,
        budget_root=args.budget_root,
        experiment_id=args.experiment_id,
        budget_cap_usd=args.budget_cap_usd,
        cycle_id=args.cycle_id,
        packet=packet,
        expected_packet_sha256=args.expected_packet_sha256,
        expected_head_sha256=args.expected_head_sha256,
        expected_decision_sha256=args.expected_decision_sha256,
        prior_canary_sha256=args.prior_canary_sha256,
        release_tag=args.release_tag,
        expected_source_sha256=args.expected_source_sha256,
        expected_runtime=runtime,
        check_clear=exact_clear,
        backend=backend,
        process=adapter.LocalDockerOneTaskProcess(),
        container_control=adapter.LocalDockerContainerControl(),
    )


def parser(*, require_supervisor_claim: bool = True) -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Run one bounded live Controller-to-B canary")
    for name in (
        "root", "adapter-claim-root", "global-state-root", "decision-doc",
        "budget-root", "packet", "runtime-receipt", "env-file",
        "tokenizer-cache",
    ):
        value.add_argument("--" + name, required=True, type=Path)
    if require_supervisor_claim:
        value.add_argument("--supervisor-claim", required=True, type=Path)
    for name in (
        "experiment-id", "budget-cap-usd", "cycle-id",
        "expected-packet-sha256", "expected-head-sha256",
        "expected-decision-sha256", "prior-canary-sha256", "release-tag",
        "expected-source-sha256",
    ):
        value.add_argument("--" + name, required=True)
    return value


def main() -> None:
    result = run(parser().parse_args())
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
