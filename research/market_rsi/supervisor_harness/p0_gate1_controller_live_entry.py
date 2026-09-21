"""Trusted CLI for one published P0 Gate 1 Controller decision.

All dry publication, packet, state, budget, duplicate-process and Supervisor
ownership checks complete before the provider credential is read. The durable
outer transaction then owns the sole dispatch and reconciliation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import dotenv_values

from codex_glm_provider import TinkerGLMBackend
from market_rsi import digest, identifier
from paid_budget import PaidBudget
from supervisor_harness import bounded_live_entry_v1 as shared_entry
from supervisor_harness import bounded_live_outer_runner_v3 as shared_outer
from supervisor_harness import p0_gate1_controller_adapter as adapter
from supervisor_harness import p0_gate1_controller_outer as outer
from supervisor_harness.global_state_gate import SupervisorGlobalState


def run(args) -> dict:
    identifier(args.cycle_id)
    shared_outer._sha(args.prior_canary_sha256, "prior canary")
    if (args.root.name != args.cycle_id or args.root.exists()
            or args.root.is_symlink()
            or not args.claim_root.is_dir() or args.claim_root.is_symlink()
            or args.root.resolve() == args.claim_root.resolve()):
        raise ValueError("fresh exact Gate 1 root and separate claims required")
    packet = shared_entry._regular_json(args.packet)
    runtime = shared_entry._regular_json(args.runtime_receipt)
    state = SupervisorGlobalState(args.global_state_root, args.decision_doc)
    budget = PaidBudget(args.budget_root)

    # Every operation above and below this line is credential-free.
    outer._publication(args.release_tag, args.expected_source_sha256)
    shared_outer._runtime(runtime)
    packet = adapter._packet(packet)
    if digest(packet) != shared_outer._sha(
            args.expected_packet_sha256, "Gate 1 packet"):
        raise ValueError("Gate 1 packet differs from frozen hash")
    shared_outer._state_snapshot(
        state, args.cycle_id, args.expected_head_sha256,
        args.expected_decision_sha256)
    shared_outer._budget_snapshot(
        budget, args.budget_root, args.experiment_id,
        args.budget_cap_usd, args.cycle_id)
    shared_outer._clear(shared_entry.exact_clear, args.cycle_id)
    shared_entry._supervisor_claim(args.supervisor_claim, args.cycle_id)

    # The credential remains local to this exact child and backend object.
    key = dotenv_values(args.env_file).get("TINKER_API_KEY")
    backend = TinkerGLMBackend(key, args.tokenizer_cache)
    return outer.run_outer(
        root=args.root,
        claim_root=args.claim_root,
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
        check_clear=shared_entry.exact_clear,
        backend=backend,
    )


def parser(*, require_supervisor_claim: bool = True) -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="Run one published Gate 1 Controller decision")
    for name in (
        "root", "claim-root", "global-state-root", "decision-doc",
        "budget-root", "packet", "runtime-receipt", "env-file",
        "tokenizer-cache",
    ):
        value.add_argument("--" + name, required=True, type=Path)
    if require_supervisor_claim:
        value.add_argument("--supervisor-claim", required=True, type=Path)
    for name in (
        "experiment-id", "budget-cap-usd", "cycle-id",
        "expected-packet-sha256", "expected-head-sha256",
        "expected-decision-sha256", "prior-canary-sha256",
        "release-tag", "expected-source-sha256",
    ):
        value.add_argument("--" + name, required=True)
    return value


if __name__ == "__main__":
    print(json.dumps(run(parser().parse_args()), sort_keys=True))
