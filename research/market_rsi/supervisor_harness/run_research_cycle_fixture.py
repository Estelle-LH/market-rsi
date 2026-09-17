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
from supervisor_harness.research_cycle_gate import (
    ZERO, bind_fixture_decision, open_fixture_cycle, record_fixture_execution,
    review_fixture_cycle,
)


HERE = Path(__file__).resolve().parent
CODE_ROOT = HERE.parent


def run(root: Path) -> dict:
    root = Path(root).resolve()
    facts = {"scope": "synthetic_fixture", "message": "public canary"}
    packet = open_fixture_cycle(root, {
        "cycle_id": root.name, "parent_feedback_sha256": ZERO,
        "harness_sha256": file_hash(HERE / "research_cycle_gate.py"),
        "facts_sha256": digest(facts),
        "allowed_data_roles": ["synthetic_fixture"], "p0_passed": False,
        "cost_cap_usd": "0", "evidence_mode": "synthetic_fixture",
    })
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
        "cost_usd": "0", "cleanup_passed": True,
    })
    output = json.loads((root / "output.json").read_text())
    if output["observed_sha256"] != file_hash(root / "facts.json"):
        raise ValueError("fixture worker output does not match independent file hash")
    return review_fixture_cycle(root, {
        "schema": "market_supervisor_review_v1", "cycle_id": root.name,
        "decision_sha256": decision["record_sha256"],
        "execution_sha256": execution["record_sha256"], "verdict": "accept",
        "reason": "Independent input/output hash comparison passed for fixture only.",
        "feedback_summary": "Provenance fixture passed; no model decision or market score.",
        "protected_data_opened": False, "budget_ok": True,
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    result = run(parser.parse_args().output)
    print(json.dumps(result, sort_keys=True))
