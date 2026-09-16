"""Use the existing single-response GLM worker for an owned task submission.

No new provider/model route. One preclaimed selection; ambiguous/missing terminal
usage blocks, while a terminal invalid choice uses the common baseline without
another response. Live calls remain blocked by independent scientific admission.
"""
from pathlib import Path

import development_harbor
from market_rsi import digest, file_hash
from researcher_worker import dispatch_once
from worker_receipts import read_research_terminal


def _active(study, directory):
    active = study.snapshot()["active"]
    if (active is None or active.get("kind") != "selection"
            or Path(directory).name != active["trial_id"]):
        raise ValueError("exact permanent selection claim required")
    return active


def dispatch_selection(study, transport, budget, directory, *, deadline_monotonic=None):
    active = _active(study, directory)
    prepared = active["prepared"]

    def admission(audit):
        development_harbor.require_admission(directory)  # Unconditional live block today.
        current = _active(study, directory)
        if current != active or audit != prepared["audit"]:
            raise ValueError("selection claim changed during dispatch")
        return True

    return dispatch_once(prepared, transport, budget, directory, admission_check=admission,
                         deadline_monotonic=deadline_monotonic)


def build_selection_completion(study, directory, budget, *, expected_live):
    active = _active(study, directory)
    if expected_live:
        development_harbor.require_admission(directory)
    terminal = read_research_terminal(directory, active["prepared"], budget, expected_live=expected_live)
    completed = {"trial_id": active["trial_id"], "packet_sha256": active["prepared"]["packet_sha256"],
        "raw_response": terminal["raw_response"], "terminal_worker_valid": terminal["valid"],
        "usage": {"research_token_metered_estimate_usd": terminal["metered_usd"],
                  "invoice_complete": False, "note": "Returned token metering is not an invoice."},
        "evidence_commitments": {"terminal_receipts": terminal["receipts"].commitment()["sha256"],
            "claimed_request": digest(active["prepared"]), "selection_worker_source": file_hash(__file__)}}
    terminal["receipts"].revalidate()
    return {"completion": completed, "read_sets": [terminal["receipts"]], "scientific_admission": False}


def commit_selection(study, built):
    for receipts in built["read_sets"]:
        receipts.revalidate()
    study.complete_selection(built["completion"])
