"""Run the already-brokered synthetic order in an observed researcher sandbox.

The caller owns sandbox creation, the global cycle claim, source publication,
budget, isolation checks, and terminal cleanup. This module does not call a
model or admit a scientific task. Its fake-object tests are not E2B evidence.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from market_rsi import canonical, digest, file_hash, fresh_json
from supervisor_harness import broker_handoff, researcher_guest_worker


GUEST_WORKER = "/tmp/market-researcher/worker.py"
MAX_OUTPUT_BYTES = 8192


def execute_brokered_canary(*, handoff: broker_handoff.BrokerHandoff,
                            researcher_sandbox, receipt_root: Path) -> dict:
    """Execute once in B and deliver only the host-verified feedback to A."""
    if (researcher_sandbox is not handoff.researcher
            or researcher_sandbox.sandbox_id == handoff.controller.sandbox_id
            or handoff.stage != "await_result"):
        raise ValueError("exact observed researcher and frozen order required")
    handoff._require_active()
    order = handoff._verified_order()
    raw_decision = broker_handoff._owned_json(handoff.root / "raw-decision.json")["raw_utf8"]
    max_seconds = json.loads(raw_decision)["max_seconds"]
    if type(max_seconds) is not int or not 1 <= max_seconds <= 30:
        raise ValueError("frozen decision has no bounded execution time")
    root = Path(receipt_root)
    if root.exists() or root.is_symlink():
        raise FileExistsError("fresh researcher execution receipt required")
    worker_path = Path(researcher_guest_worker.__file__)
    if worker_path.is_symlink() or not worker_path.is_file() or worker_path.stat().st_size > 128 * 1024:
        raise ValueError("missing or unsafe researcher worker source")
    worker_sha = file_hash(worker_path)
    worker_text = worker_path.read_text(encoding="utf-8")
    source_sha = file_hash(__file__)
    root.mkdir(mode=0o700)
    claim = {"schema": "market_rsi_brokered_guest_execution_claim_v1",
             "cycle_id": handoff.cycle_id,
             "researcher_sandbox_id": researcher_sandbox.sandbox_id,
             "controller_sandbox_id": handoff.controller.sandbox_id,
             "order_sha256": digest(order),
             "handoff_source_sha256": handoff.source_sha256,
             "execution_source_sha256": source_sha,
             "worker_source_sha256": worker_sha,
             "task_type": "synthetic_hash_canary", "automatic_retry": False}
    fresh_json(root / "claim.json", claim)
    try:
        if researcher_sandbox.files.read(broker_handoff.B_ORDER) != canonical(order):
            raise ValueError("researcher order changed after broker delivery")
        researcher_sandbox.files.write(GUEST_WORKER, worker_text)
        if researcher_sandbox.files.read(GUEST_WORKER) != worker_text:
            raise ValueError("researcher worker changed during guest transfer")
        command = (f"python3 -I {GUEST_WORKER} --order {broker_handoff.B_ORDER}"
                   f" --result {broker_handoff.B_RESULT}")
        ran = researcher_sandbox.commands.run(command, timeout=max_seconds)
        if (type(ran.exit_code) is not int or ran.exit_code != 0
                or not isinstance(ran.stdout, str) or not isinstance(ran.stderr, str)
                or len(ran.stdout.encode()) > MAX_OUTPUT_BYTES
                or len(ran.stderr.encode()) > MAX_OUTPUT_BYTES):
            raise RuntimeError("researcher command failed or exceeded output bound")
        fresh_json(root / "command.json", {
            "schema": "market_rsi_brokered_guest_command_v1", "exit_code": ran.exit_code,
            "stdout_sha256": hashlib.sha256(ran.stdout.encode()).hexdigest(),
            "stderr_sha256": hashlib.sha256(ran.stderr.encode()).hexdigest(),
            "researcher_sandbox_id": researcher_sandbox.sandbox_id})
        if (file_hash(worker_path) != worker_sha or file_hash(__file__) != source_sha
                or file_hash(broker_handoff.__file__) != handoff.source_sha256):
            raise RuntimeError("executable source changed during researcher execution")
        handoff._require_active()
        result = handoff.receive_result()  # host independently recomputes the hash
        review = {"schema": "market_broker_independent_review_v1",
                  "cycle_id": handoff.cycle_id, "result_sha256": digest(result),
                  "verdict": "accept", "reason": "Host recomputed the bound synthetic text hash.",
                  "protected_data_opened": False}
        feedback = handoff.deliver_reviewed_feedback(review)
        receipt = {"schema": "market_rsi_brokered_guest_execution_v1",
                   "claim_sha256": file_hash(root / "claim.json"),
                   "command_sha256": file_hash(root / "command.json"),
                   "result_sha256": digest(result),
                   "feedback_sha256": digest(feedback),
                   "synthetic_only": True, "model_authorship_proven": False,
                   "isolation_proven": False, "cleanup_verified": False}
        fresh_json(root / "receipt.json", receipt)
        return receipt
    except Exception as exc:
        handoff.stage = "failed"  # no second guest command after any attempted execution
        fresh_json(root / "failure.json", {
            "schema": "market_rsi_brokered_guest_execution_failure_v1",
            "claim_sha256": file_hash(root / "claim.json"),
            "error_type": type(exc).__name__})
        raise
