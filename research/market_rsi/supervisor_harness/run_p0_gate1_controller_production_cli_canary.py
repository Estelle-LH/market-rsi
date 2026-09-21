"""Zero-provider acceptance for the Gate 1 production CLI and Supervisor."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from market_rsi import digest, file_hash, fresh_json
from paid_budget import PaidBudget
from supervisor_harness import bounded_live_outer_runner_v3 as shared_outer
from supervisor_harness import p0_gate1_controller_supervisor_parent as parent
from supervisor_harness import protocol_source_release
from supervisor_harness.global_state_gate import SupervisorGlobalState
from supervisor_harness.p0_gate1_controller_adapter import expected_packet


SCHEMA = "market_p0_gate1_controller_production_cli_canary_v1"
CHILD = parent.CANARY_CHILD_ENTRY


def execute(output: Path) -> dict:
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise FileExistsError("fresh production-CLI canary output required")
    output.mkdir(parents=True, mode=0o700)
    cycle_id = output.name + "-transaction"
    decision = output / "decision.md"
    decision.write_text("synthetic Gate 1 production-CLI canary only\n")
    state = SupervisorGlobalState(output / "global-state", decision)
    state_before = state.initialize()
    budget_root = output / "budget"
    budget = PaidBudget.create(budget_root, {
        "experiment_id": "gate1-production-cli-canary-budget",
        "cap_usd": "1",
        "target_usd": "0.05",
        "buckets_usd": {"setup": "0.5", "repair": "0.5"},
        "authority": "zero-provider production-CLI acceptance canary",
    })
    claims = output / "claims"
    claims.mkdir(mode=0o700)
    packet = output / "controller-input.json"
    packet.write_text(
        json.dumps(expected_packet(), sort_keys=True, indent=2) + "\n")
    runtime = output / "runtime.json"
    fresh_json(runtime, shared_outer.runtime_receipt())
    env_file = output / "offline.env"
    env_file.write_text("TINKER_API_KEY=offline-canary-not-a-secret\n")
    tokenizer_cache = output / "tokenizer-cache"
    tokenizer_cache.mkdir(mode=0o700)
    source_sha = digest(protocol_source_release.source_hashes())
    args = SimpleNamespace(
        root=output / cycle_id,
        claim_root=claims,
        global_state_root=output / "global-state",
        decision_doc=decision,
        budget_root=budget_root,
        packet=packet,
        runtime_receipt=runtime,
        env_file=env_file,
        tokenizer_cache=tokenizer_cache,
        experiment_id="gate1-production-cli-canary-budget",
        budget_cap_usd="1",
        cycle_id=cycle_id,
        expected_packet_file_sha256=file_hash(packet),
        expected_packet_canonical_sha256=digest(expected_packet()),
        expected_head_sha256=state_before["head_sha256"],
        expected_decision_sha256=file_hash(decision),
        prior_canary_sha256=file_hash(Path(__file__)),
        release_tag=parent.CANARY_RELEASE_TAG,
        expected_source_sha256=source_sha,
        supervisor_root=output / "supervisor",
    )
    supervised = parent.run(args, child_entry=CHILD)
    budget_after = budget.snapshot()
    state_after = state.snapshot()
    job = budget_after["jobs"][cycle_id]
    child_result = args.root / "result.json"
    claim = args.supervisor_root / "supervisor-claim.json"
    passed = (
        supervised.get("passed") is True
        and supervised.get("incident_created") is False
        and supervised.get("child_exit_code") == 0
        and child_result.is_file()
        and claim.is_file()
        and job.get("state") == "metered_terminal"
        and state_after.get("active_cycle") is None
        and state_after.get("last_review_sha256") != "0" * 64
    )
    result = {
        "schema": SCHEMA,
        "cycle_id": cycle_id,
        "passed": passed,
        "production_parent_used": True,
        "production_cli_arguments_used": True,
        "supervisor_claim_verified_by_child": True,
        "offline_provider_substituted": True,
        "provider_calls": 0,
        "actual_provider_cost_usd": "0",
        "synthetic_ledger_metered_usd": job["metered_usd"],
        "public_fetch_performed": False,
        "formal_data_admitted": False,
        "automatic_retry": False,
        "packet_file_sha256": file_hash(packet),
        "packet_canonical_sha256": digest(expected_packet()),
        "child_result_sha256": file_hash(child_result),
        "supervisor_claim_sha256": file_hash(claim),
        "supervisor_result_sha256": file_hash(
            args.supervisor_root / "result.json"),
    }
    fresh_json(output / "canary-result.json", result)
    if not passed:
        raise RuntimeError("Gate 1 production-CLI acceptance failed")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    print(json.dumps(execute(parser.parse_args().output), sort_keys=True))
