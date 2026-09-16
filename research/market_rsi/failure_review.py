"""Runner-only causal review of a closed failed candidate under unchanged code.

No provider calls, paid retries, model advice, cost release or source migration.
Independent judgment is supplied by the trusted infrastructure reviewer, NOT
inferred from a candidate's own stderr or made true by this validator. This
module checks the original terminal receipts again and records the judgment
without editing the failure. Uncertain causes and source-changing repairs must
remain blocked; this is deliberately not an automatic repair mechanism.
"""
import copy
import json
from pathlib import Path

from market_rsi import digest, file_hash, identifier
from paid_budget import money
from researcher_worker import hash_string
from sandbox_failure_evidence import build_sandbox_failure
from worker_receipts import Receipts, read_regular


DISPOSITION = "candidate_outcome_under_unchanged_contract"


def validate_review(review):
    fields = {"schema", "review_id", "trial_id", "study_manifest_sha256", "completion_sha256",
              "disposition", "reviewer_origin", "rationale", "evidence_citations",
              "verified_receipt_commitments", "review_source_sha256", "accounting_at_review"}
    if (not isinstance(review, dict) or set(review) != fields
            or review["schema"] != "market_failure_review_v1"
            or review["disposition"] != DISPOSITION
            or review["reviewer_origin"] != "trusted_runner_causal_review"
            or not isinstance(review["rationale"], str) or not 40 <= len(review["rationale"]) <= 4000
            or not isinstance(review["evidence_citations"], dict) or len(review["evidence_citations"]) < 2
            or not isinstance(review["verified_receipt_commitments"], list)
            or not review["verified_receipt_commitments"]):
        raise ValueError("explicit runner judgment under unchanged contract required; not automatic repair")
    identifier(review["review_id"])
    identifier(review["trial_id"])
    for name in ("study_manifest_sha256", "completion_sha256", "review_source_sha256"):
        hash_string(review[name])
    if review["review_source_sha256"] != file_hash(__file__):
        raise ValueError("review implementation changed")
    for path, sha in review["evidence_citations"].items():
        if not isinstance(path, str) or not Path(path).is_absolute():
            raise ValueError("runner-only exact evidence paths required")
        hash_string(sha)
    for sha in review["verified_receipt_commitments"]:
        hash_string(sha)
    usage = review["accounting_at_review"]
    if (not isinstance(usage, dict) or set(usage) != {"job_state", "metered_usd", "invoiced_usd",
            "unresolved_hold_usd", "exact_cleanup_acknowledged"}
            or usage["job_state"] not in {"dispatched", "metered_terminal"}
            or usage["exact_cleanup_acknowledged"] is not True):
        raise ValueError("exact current sandbox accounting snapshot required")
    for key in ("metered_usd", "invoiced_usd", "unresolved_hold_usd"):
        if usage[key] is not None:
            money(usage[key])


class _HistoricalClaim:
    """Read-only adapter for independently replaying a recorded completion."""
    def __init__(self, active):
        self.active = active

    def snapshot(self):
        return {"active": copy.deepcopy(self.active)}


def build_failure_review(study, development_directory, *, trial_id, review_id,
                         rationale, evidence_paths, **trial_arguments):
    identifier(trial_id)
    identifier(review_id)
    with study.journal.locked():
        manifest, state = study._load()
        if state["active"] is not None or trial_id not in study._causal_review_ids(state):
            raise ValueError("only a completed unresolved failure may be reviewed")
        matches = [r for records in state["records"].values() for r in records if r["trial_id"] == trial_id]
        if len(matches) != 1 or state["eligible"][trial_id]:
            raise ValueError("one ineligible original candidate required")
        record = copy.deepcopy(matches[0])
    own_reads = Receipts()
    directory = study.root / "steps" / trial_id
    prepared = own_reads.read(directory / "request.json")
    saved = own_reads.read(directory / "completion.json")
    if (saved["payload"] != record["payload"] or prepared["audit"]["arm"] != record["arm"]
            or saved["trial_id"] != trial_id):
        raise ValueError("original completed step differs from its journal")
    active = {"trial_id": trial_id, "arm": record["arm"], "prepared": prepared}
    built = build_sandbox_failure(_HistoricalClaim(active), development_directory, **trial_arguments)
    # Invoices may legitimately arrive after the original failure was recorded.
    # Preserve the historical usage, independently read today's append-only
    # ledger, and permit ONLY that sandbox accounting snapshot to advance.
    accounting = copy.deepcopy(built["completion"]["payload"]["usage"]["sandbox"])
    comparable = copy.deepcopy(built["completion"])
    comparable["payload"]["usage"]["sandbox"] = saved["payload"]["usage"]["sandbox"]
    if comparable != saved:
        raise ValueError("reverified failure differs from the original; cannot rewrite history")
    read_sets = built["read_sets"] + [own_reads]
    available = {p: sha for reads in read_sets for p, sha in reads.files.items()}
    if not isinstance(evidence_paths, list) or len(evidence_paths) < 2:
        raise ValueError("cite at least two independently reverified runner evidence files")
    citations = {}
    root = Path(development_directory).absolute()
    # Candidate-controlled output alone can never supply this review. Require
    # observed runner protocol plus another verified runtime/setup/command file.
    required_protocol = str(root / "collected/protocol.json")
    runner_files = {str(root / n) for n in ("command.json", "runtime.json", "libraries.json", "collected/isolation.json")}
    for path in evidence_paths:
        path = str(Path(path).absolute())
        if path not in available or path in citations:
            raise ValueError("review citation is absent, unverified or duplicated")
        citations[path] = available[path]
    if required_protocol not in citations or not set(citations) & runner_files:
        raise ValueError("candidate stderr alone cannot establish the cause")
    review = {"schema": "market_failure_review_v1", "review_id": review_id, "trial_id": trial_id,
        "study_manifest_sha256": digest(manifest), "completion_sha256": digest(saved),
        "disposition": DISPOSITION, "reviewer_origin": "trusted_runner_causal_review",
        "rationale": rationale, "evidence_citations": citations,
        "accounting_at_review": accounting,
        "verified_receipt_commitments": [r.commitment()["sha256"] for r in read_sets],
        "review_source_sha256": file_hash(__file__)}
    validate_review(review)
    for reads in read_sets:
        reads.revalidate()
    return {"review": review, "read_sets": read_sets, "automatic_causal_diagnosis": False}


def commit_failure_review(study, built):
    """No dispatch. Retain the failure and proceed only to the next normal ID."""
    review = built["review"]
    validate_review(review)
    for reads in built["read_sets"]:
        reads.revalidate()
    pending = study.root / "failure-reviews" / review["review_id"] / "review.json"
    if pending.exists():
        if json.loads(read_regular(pending)) != review:
            raise ValueError("interrupted review differs from the reverified original")
        study.recover_failure_review(review["review_id"])
    else:
        study.complete_failure_review(review)
