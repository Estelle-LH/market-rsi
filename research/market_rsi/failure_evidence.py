"""Preserve terminal invalid worker responses in the researcher's own memory.

Only independently bound terminal responses are accepted here. Ambiguous paid
dispatch, missing usage, forbidden tool events, unexplained process termination,
and failed sandbox execution remain blocked for separate runner investigation.
No automatic retries, replacement responses, fabricated scores, or hold release.
Live study admission is still closed. Mock paths are fixture-only.
"""
from __future__ import annotations

import copy

import development_harbor
from coder_worker import prepare_code_request
from market_rsi import file_hash
from worker_receipts import read_code_terminal, read_research_terminal


def build_worker_failure(study, *, research_directory, budget, expected_live,
                         coding_directory=None, frozen_runtime=None, frozen_coder_limits=None,
                         expected_coder_identity=None):
    active = study.snapshot()["active"]
    if active is None or type(expected_live) is not bool:
        raise ValueError("exact active step and explicit worker mode required")
    prepared = active["prepared"]
    if expected_live:
        development_harbor.require_admission(research_directory)
    elif not prepared["audit"]["experiment_id"].startswith("fixture-"):
        raise ValueError("mock failure cannot enter a real experiment")
    research = read_research_terminal(research_directory, prepared, budget, expected_live=expected_live)
    reads = [research["receipts"]]
    trace = {"research_response": research["raw_response"]}
    usage = {"research_token_metered_estimate_usd": research["metered_usd"],
             "coding": None, "sandbox": None,
             "note": "No execution score. Reservation, token estimate, invoice and subscription allocation remain distinct."}
    source = None
    if research["valid"]:
        if coding_directory is None or any(v is None for v in
                (frozen_runtime, frozen_coder_limits, expected_coder_identity)):
            raise ValueError("valid proposal is not a failed step; exact coder receipts required")
        coding_prepared = prepare_code_request(prepared, research["raw_response"], frozen_runtime, frozen_coder_limits)
        coding = read_code_terminal(coding_directory, research, coding_prepared,
                                   expected_live=expected_live, expected_identity=expected_coder_identity)
        if coding["valid"]:
            raise ValueError("valid code must proceed to execution, not be discarded as a failure")
        reads.append(coding["receipts"])
        trace.update(coding_events=coding["events"], coding_response=coding["response_body"])
        source = coding["source"] if isinstance(coding["source"], str) else None
        usage["coding"] = coding["subscription_usage"]
        stage, kind = "coding", coding["failure_kind"]
    else:
        if coding_directory is not None:
            raise ValueError("invalid proposal must not have dispatched coding")
        stage, kind = "research", research["failure_kind"]
    completed = {"trial_id": active["trial_id"], "research_packet_sha256": prepared["packet_sha256"],
        "raw_research_response": research["raw_response"], "eligible_submission": False,
        "evidence_commitments": {"failure_producer_source": file_hash(__file__),
                                 **{f"worker_receipts_{i}": r.commitment()["sha256"] for i, r in enumerate(reads)}},
        "payload": {"proposal": research["proposal"], "candidate_code": source,
            "train_dev_results": {}, "usage": usage,
            "failure": {"stage": stage, "kind": kind, "terminal": True,
                "automatic_retry": False, "available_trace": trace,
                "independent_score": None, "scientific_admission": False}}}
    for receipt in reads:
        receipt.revalidate()
    return {"completion": copy.deepcopy(completed), "read_sets": reads, "scientific_admission": False}
