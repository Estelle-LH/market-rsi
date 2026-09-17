"""One real zero-paid subprocess through the proposed cycle provenance gate.

The controller output is scripted, so success is infrastructure evidence only.
This must never be reported as GLM research, E2B isolation or model improvement.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from market_rsi import digest, file_hash, fresh_json
from supervisor_harness.global_state_gate import SupervisorGlobalState
from supervisor_harness.research_cycle_gate import (
    ZERO, bind_fixture_decision, fixture_source_manifest, open_fixture_cycle,
    record_fixture_execution, require_new_recursive_round, review_fixture_cycle,
    verify_fixture_canary,
)


HERE = Path(__file__).resolve().parent
CODE_ROOT = HERE.parent


def run(root: Path, *, global_state_root: Path, decision_doc: Path,
        prior_canary: Path | None = None, bootstrap_canary: bool = False) -> dict:
    root = Path(root).resolve()
    if root.exists():
        raise FileExistsError("fresh cycle directory required")
    if bootstrap_canary:
        if prior_canary is not None:
            raise ValueError("bootstrap cannot also cite an earlier canary")
        prior_canary_sha256 = ZERO
    elif prior_canary is None:
        raise ValueError("every non-bootstrap cycle requires a current exact-code canary")
    else:
        prior_receipt = require_new_recursive_round(prior_canary, evidence_mode="synthetic_fixture")
        prior_canary_sha256 = prior_receipt["review_sha256"]
    state = SupervisorGlobalState(global_state_root, decision_doc)
    snapshot = state.snapshot()
    source_hash = digest(fixture_source_manifest())
    state.claim(root.name, expected_head_sha256=snapshot["head_sha256"],
                source_sha256=source_hash, prior_canary_sha256=prior_canary_sha256)
    try:
        review = _run_claimed_fixture(root)
        state.close(root.name, outcome="passed", review_sha256=file_hash(root / "review.json"))
        return review
    except BaseException:
        state.close(root.name, outcome="failed")
        raise


def _run_claimed_fixture(root: Path) -> dict:
    facts = {"scope": "synthetic_fixture", "message": "public canary"}
    sources = fixture_source_manifest()
    packet = open_fixture_cycle(root, {
        "cycle_id": root.name, "parent_feedback_sha256": ZERO,
        "harness_sha256": digest(sources),
        "facts_sha256": digest(facts),
        "allowed_data_roles": ["synthetic_fixture"], "p0_passed": False,
        "cost_cap_usd": "0", "evidence_mode": "synthetic_fixture",
    })
    fresh_json(root / "source-manifest.json", sources)
    fresh_json(root / "facts.json", facts)
    raw = {
        "schema": "market_research_decision_v1", "cycle_id": root.name,
        "input_sha256": packet["record_sha256"], "task_id": "public-hash-canary",
        "task_type": "code_canary", "data_role": "synthetic_fixture",
        "question": "Can the worker preserve the exact public input hash?",
        "hypothesis": "The output hash equals the frozen input hash.",
        "expected_evidence": "A subprocess trace and its JSON output.",
        "stop_rule": "One subprocess, at most 30 seconds, no retry.",
        "max_seconds": 30, "cost_bound_usd": "0",
    }
    fresh_json(root / "raw-decision.json", raw)
    decision = bind_fixture_decision(root, root / "raw-decision.json",
                                     {**raw, "raw_decision_sha256": file_hash(root / "raw-decision.json")})
    command = [sys.executable, str(HERE / "fixture_researcher_worker.py"), "--root", str(root)]
    environment = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                   "PYTHONPATH": str(CODE_ROOT), "TMPDIR": os.environ.get("TMPDIR", "/tmp")}
    process = subprocess.run(command, cwd=root, env=environment, capture_output=True,
                             text=True, timeout=30, check=False)
    fresh_json(root / "worker-process.json", {"schema": "research_fixture_process_v1",
                                               "command": command, "exit_code": process.returncode,
                                               "worker_source_sha256": sources["sources"]["fixture_researcher_worker.py"],
                                               "stdout": process.stdout[-4096:],
                                               "stderr": process.stderr[-4096:],
                                               "automatic_retry": False})
    if process.returncode != 0:
        raise RuntimeError("fixture worker failed; preserve run directory")
    execution = record_fixture_execution(root, {
        "schema": "market_researcher_receipt_v1", "cycle_id": root.name,
        "decision_sha256": decision["record_sha256"], "task_id": raw["task_id"],
        "backend": "local_fixture", "status": "completed", "exit_code": process.returncode,
        "trace_path": "trace.json", "trace_sha256": file_hash(root / "trace.json"),
        "output_path": "output.json", "output_sha256": file_hash(root / "output.json"),
        "worker_process_sha256": file_hash(root / "worker-process.json"),
        "cost_usd": "0", "cleanup_passed": True,
    })
    output = json.loads((root / "output.json").read_text())
    if output["observed_sha256"] != file_hash(root / "facts.json"):
        raise ValueError("fixture worker output does not match independent file hash")
    review = review_fixture_cycle(root, {
        "schema": "market_supervisor_review_v1", "cycle_id": root.name,
        "decision_sha256": decision["record_sha256"],
        "execution_sha256": execution["record_sha256"], "verdict": "accept",
        "reason": "Independent input/output hash comparison passed for fixture only.",
        "feedback_summary": "Provenance fixture passed; no model decision or market score.",
        "protected_data_opened": False, "budget_ok": True,
    })
    verify_fixture_canary(root)
    return review


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--global-state-root", type=Path, required=True)
    parser.add_argument("--decision-doc", type=Path, default=HERE / "RESEARCH_STATE.md")
    parser.add_argument("--prior-canary", type=Path)
    parser.add_argument("--bootstrap-canary", action="store_true")
    args = parser.parse_args()
    result = run(args.output, global_state_root=args.global_state_root,
                 decision_doc=args.decision_doc, prior_canary=args.prior_canary,
                 bootstrap_canary=args.bootstrap_canary)
    print(json.dumps(result, sort_keys=True))
