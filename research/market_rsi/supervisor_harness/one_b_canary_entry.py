"""Fail-closed admission for one scripted, single-B E2B transport canary.

This module cannot create a sandbox or call GLM. A fixture predecessor proves
only provenance, not live isolation or model authorship. The trusted parent
must own child execution, exact cleanup, account readback and accounting.
"""
from __future__ import annotations

from pathlib import Path

from market_rsi import digest, file_hash, fresh_json, identifier
from paid_budget import money
from supervisor_harness import protocol_source_release, research_cycle_gate


UPPER_USD = "0.20"
DECISION_MARKER = "market_one_b_canary_decision_v1"


def _sha(value: str) -> str:
    if (not isinstance(value, str) or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)):
        raise ValueError("lowercase SHA256 required")
    return value


def begin_one_b_canary(*, root: Path, cycle_id: str, state, budget,
                       expected_head_sha256: str, prior_fixture_root: Path,
                       release_tag: str, expected_source_sha256: str,
                       input_sha256: str) -> dict:
    """Claim one new operational test only after source/state/budget gates."""
    identifier(cycle_id)
    _sha(input_sha256)
    _sha(expected_head_sha256)
    _sha(expected_source_sha256)
    root = Path(root)
    if root.name != cycle_id or root.exists() or root.is_symlink():
        raise ValueError("fresh exact one-B output directory required")
    prior = research_cycle_gate.verify_fixture_canary(prior_fixture_root)
    if (prior["controller_led_result"] is not False
            or prior["formal_admission"] is not False):
        raise ValueError("synthetic predecessor changed its claim boundary")
    publication = protocol_source_release.verify_published(
        tag=release_tag, expected_source_sha256=expected_source_sha256)
    supervisor = state.snapshot()
    # A hash-valid but obsolete two-E2B decision is not authority to dispatch
    # the new topology. The marker must be in the *journal-pinned* document,
    # after an explicit idle revision; adding it to this source is not enough.
    decision_doc = getattr(state, "decision_doc", None)
    if (decision_doc is None or Path(decision_doc).is_symlink()
            or DECISION_MARKER not in Path(decision_doc).read_text(encoding="utf-8")):
        raise ValueError("one-B supervisor decision not recorded")
    if (supervisor["head_sha256"] != expected_head_sha256
            or supervisor["active_cycle"] is not None
            or cycle_id in supervisor["claimed_cycles"]):
        raise ValueError("stale or duplicate supervisor cycle")
    ledger = budget.snapshot()
    if (cycle_id in ledger["jobs"]
            or money(ledger["available_usd"]) < money(UPPER_USD)
            or money(ledger["buckets"]["setup"]["available_usd"]) < money(UPPER_USD)):
        raise ValueError("one-B setup budget or job identity unavailable")
    claim = {
        "schema": "market_one_b_canary_admission_v1", "cycle_id": cycle_id,
        "input_sha256": input_sha256,
        "publication_sha256": digest(publication),
        "published_commit": publication["commit"],
        "source_sha256": publication["source_sha256"],
        "prior_fixture_review_sha256": prior["review_sha256"],
        "prior_fixture_source_sha256": prior["source_manifest_sha256"],
        "expected_global_head_sha256": expected_head_sha256,
        "setup_upper_usd_not_invoice": UPPER_USD,
        "one_b_synthetic_transport_only": True,
        "model_authorship_proven": False, "isolation_proven": False,
    }
    state.claim(cycle_id, expected_head_sha256=expected_head_sha256,
                source_sha256=publication["source_sha256"],
                prior_canary_sha256=prior["review_sha256"])
    try:
        root.mkdir(mode=0o700)
        fresh_json(root / "admission.json", claim)
        budget.reserve(cycle_id, "setup", UPPER_USD, "e2b", digest(claim))
        fresh_json(root / "reserved.json", {
            "schema": "market_one_b_canary_reserved_v1",
            "admission_sha256": file_hash(root / "admission.json"),
            "job_id": cycle_id, "dispatch_permitted_by_this_module": False,
        })
        return claim
    except Exception as exc:
        # A crash or unknown budget state must not permit a second attempt.
        if root.is_dir() and not (root / "failure.json").exists():
            fresh_json(root / "failure.json", {
                "schema": "market_one_b_admission_failure_v1",
                "cycle_id": cycle_id, "error_type": type(exc).__name__,
            })
            job = budget.snapshot()["jobs"].get(cycle_id)
            if job is not None and job["state"] == "reserved":
                budget.cancel_before_dispatch(cycle_id)
            elif job is not None and job["state"] != "cancelled_before_dispatch":
                raise RuntimeError("possibly dispatched hold needs parent reconciliation") from exc
            state.close(cycle_id, outcome="failed",
                        review_sha256=file_hash(root / "failure.json"))
        raise
