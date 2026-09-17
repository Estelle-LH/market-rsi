"""One-way admission for a future published two-E2B *operational* canary.

This claims supervisor state and a setup-budget hold only. It cannot dispatch,
read provider credentials, create sandboxes, certify isolation, or admit a
model-authored research round. A separate parent/child runner must own those
later stages and exact terminal cleanup/accounting.
"""
from __future__ import annotations

from pathlib import Path
import sys

from market_rsi import digest, file_hash, fresh_json, identifier
from paid_budget import money
from supervisor_harness import protocol_source_release, research_cycle_gate


UPPER_USD = "0.20"


def begin_protocol_canary(*, root: Path, cycle_id: str, state, budget,
                          expected_head_sha256: str, prior_fixture_root: Path,
                          release_tag: str, expected_source_sha256: str) -> dict:
    """Reject stale/unpublished/over-budget work before claiming or reserving."""
    identifier(cycle_id)
    root = Path(root)
    if root.name != cycle_id or root.exists() or root.is_symlink():
        raise ValueError("fresh exact cycle output directory required")
    prior = research_cycle_gate.verify_fixture_canary(prior_fixture_root)
    # The fixture is only a provenance precursor, never a live-model permit.
    if (prior["controller_led_result"] is not False
            or prior["formal_admission"] is not False):
        raise ValueError("synthetic predecessor changed its claim boundary")
    publication = protocol_source_release.verify_published(
        tag=release_tag, expected_source_sha256=expected_source_sha256)
    snapshot = state.snapshot()
    if (snapshot["head_sha256"] != expected_head_sha256
            or snapshot["active_cycle"] is not None
            or cycle_id in snapshot["claimed_cycles"]):
        raise ValueError("supervisor global state stale or already claimed")
    account = budget.snapshot()
    if (money(account["available_usd"]) < money(UPPER_USD)
            or money(account["buckets"]["setup"]["available_usd"]) < money(UPPER_USD)
            or cycle_id in account["jobs"]):
        raise ValueError("setup budget or job identity unavailable")
    claim = {"schema": "market_rsi_protocol_canary_admission_v1",
             "cycle_id": cycle_id,
             "publication_sha256": digest(publication),
             "published_commit": publication["commit"],
             "source_sha256": publication["source_sha256"],
             "prior_fixture_review_sha256": prior["review_sha256"],
             "prior_fixture_source_sha256": prior["source_manifest_sha256"],
             "expected_global_head_sha256": expected_head_sha256,
             "python_executable": str(Path(sys.executable).absolute()),
             "setup_upper_usd_not_invoice": UPPER_USD,
             "scripted_operational_canary_only": True,
             "model_authorship_proven": False,
             "isolation_proven": False}
    # The state claim serializes this ID before a paid credential or worker.
    state.claim(cycle_id, expected_head_sha256=expected_head_sha256,
                source_sha256=publication["source_sha256"],
                prior_canary_sha256=prior["review_sha256"])
    try:
        root.mkdir(mode=0o700)
        fresh_json(root / "admission.json", claim)
        budget.reserve(cycle_id, "setup", UPPER_USD, "e2b", digest(claim))
        fresh_json(root / "reserved.json", {
            "schema": "market_rsi_protocol_canary_reserved_v1",
            "admission_sha256": file_hash(root / "admission.json"),
            "job_id": cycle_id, "dispatch_permitted_by_this_module": False})
        return claim
    except Exception as exc:
        # If the host crashes before this block, the still-active claim blocks
        # another launch. Do not clear it automatically on a later process.
        if root.is_dir() and not (root / "failure.json").exists():
            fresh_json(root / "failure.json", {
                "schema": "market_rsi_protocol_admission_failure_v1",
                "cycle_id": cycle_id, "error_type": type(exc).__name__})
            # A dispatched or uninspectable job must leave this global claim
            # active until a parent verifies exact terminal cleanup/accounting.
            job = budget.snapshot()["jobs"].get(cycle_id)
            if job is not None and job["state"] == "reserved":
                budget.cancel_before_dispatch(cycle_id)
            elif job is not None and job["state"] != "cancelled_before_dispatch":
                raise RuntimeError("possibly dispatched setup hold needs parent reconciliation") from exc
            state.close(cycle_id, outcome="failed",
                        review_sha256=file_hash(root / "failure.json"))
        raise
