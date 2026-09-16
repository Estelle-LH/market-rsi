"""Read-only audit of this pilot's existing evidence, NOT scientific admission.

No network, provider invocation, source repair, candidate execution or hidden
evaluation. An optional fresh output records this report check without changing
the original receipts. This runner-only file must never become agent experience.
"""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path

from market_harbor import verify_fixture_outputs
from market_rsi import file_hash, fresh_json, identifier
from paid_budget import PaidBudget
from worker_receipts import Receipts, read_regular


ROOT = Path(__file__).resolve().parent
RUN = ROOT / "artifacts/kalshi-research-glm53-20260907-01"
RAW = {
    "kalshi-20260904T23.jsonl.zst": "8a47283c7152161e30e0a85aab55c85223886013267bd500b47c86a855b9c4cc",
    "kalshi-20260905T00.jsonl.zst": "68a29a410cdc7267d786674a4f91a86603c7a4c7badcfa5e54320b66b37ccdaf",
}


def audit():
    reads = Receipts()
    checked = {}

    def require(condition, name):
        if not condition:
            raise ValueError("report evidence check failed: " + name)
        checked[name] = True

    common = reads.read(RUN / "common-initialization.json")
    require(file_hash(RUN / "common-initialization.json") ==
        "e794a73d36ddc6bde7c0337837b61f5070a1bd9ece9c88f26ca29d21132d4f99", "frozen_common_manifest")
    require(hashlib.sha256(common["system_prompt"].encode()).hexdigest() == common["common_sha256"] ==
        "2cfbecbb97021eac19e3c159d1c7050a98b0b4d9f6de6e57f5e6b76d9aa57430", "frozen_common_text")
    source_archive = reads.read(RUN / "phase-deadline-sources-01.json")
    for name, item in source_archive["files"].items():
        require(hashlib.sha256(item["source"].encode()).hexdigest() == item["sha256"] == file_hash(ROOT / name),
            "latest_source:" + name)
    raw_hashes = {name: file_hash(ROOT / "data" / name) for name in RAW}
    require(raw_hashes == RAW, "two_closed_raw_file_hashes")
    complete = reads.read(RUN / "labels-diagnostic-01/complete.json")
    readback = reads.read(RUN / "labels-diagnostic-01/independent-readback-audit.json")
    labels_path = RUN / "labels-diagnostic-01/runner-labels.jsonl.gz"
    require(file_hash(labels_path) == complete["labels_sha256"] == readback["labels_sha256"], "diagnostic_label_file_hash")
    require(complete["code_sha256"] == file_hash(ROOT / "label_materializer.py"), "diagnostic_materializer_source")
    rows, games, contracts = 0, set(), set()
    with gzip.open(labels_path, "rt") as stream:
        for line in stream:
            row = json.loads(line)
            rows += 1
            games.add(row["game_id"])
            contracts.add(row["market_id"])
    require((rows, len(games), len(contracts)) == (readback["label_rows"], readback["games"], readback["markets"]),
        "recounted_diagnostic_rows_and_groups")
    excluded = sum(complete["counts"][key] for key in (
        "capture_tail_censored", "continuity_break", "entry_endpoint_late", "label_endpoint_late", "quote_gap"))
    require(rows + excluded == complete["counts"]["scheduled_decisions"] and excluded == readback["excluded"],
        "diagnostic_count_conservation")
    require(complete["scoring_ready"] is False and readback["clock_provenance_verified"] is False,
        "diagnostic_is_not_scored_evidence")
    metadata = reads.read(RUN / "historical-metadata-breadth-01.json")["result"]
    family = metadata["family_summary"]
    overlap = len(family["event_keys_in_both_provisional_file_partitions"])
    require(metadata["scoring_ready"] is False and overlap == 44 and family["candidate_events"] == 209,
        "stored_metadata_breadth_not_usable_task_count")
    fixture = verify_fixture_outputs(RUN / "harbor-stream-integration-01")
    require(fixture == reads.read(RUN / "harbor-stream-integration-01/assessment.json"), "old_harbor_fixture_readback")
    require(file_hash(ROOT / "glm_canary.py") == file_hash(RUN / "glm-canary-01/glm_canary.source.py"),
        "old_glm_canary_source_unchanged")
    cleanup = []
    for name, receipt_name in [("e2b-coder-preflight-0" + str(i), "cleanup.json") for i in (1, 2, 3)] + [
            ("harbor-stream-integration-01", "cleanup-01.json")]:
        receipt = reads.read(RUN / name / receipt_name)
        original = reads.read(RUN / name / "sandbox.json")
        require(receipt["kill_acknowledged"] is True and receipt["sandbox_id"] == original["sandbox_id"],
            "exact_cleanup:" + name)
        cleanup.append({"job_id": name, "sandbox_id": receipt["sandbox_id"], "kill_acknowledged": True})
    budget = PaidBudget(RUN / "budget").snapshot()  # Independently replays its append-only hash chain.
    journal = [json.loads(line) for line in read_regular(RUN / "budget/journal.jsonl").splitlines()]
    dispatches = [{"time": row["time"], "job_id": row["payload"]["job_id"]}
        for row in journal if row["event"] == "dispatched"]
    require(len(dispatches) == len({row["job_id"] for row in dispatches}) == 5, "five_unique_budget_dispatches")
    # This verifies the report's absence claim only in the authorized pilot root,
    # not in unrelated repositories, older SWE runs or historical fixture roots.
    studies = []
    for path in RUN.rglob("config.json"):
        if path.is_symlink():
            raise ValueError("symlink config in pilot report audit")
        value = json.loads(read_regular(path))
        if value.get("schema") == "market_study_runner_v1":
            studies.append(str(path.relative_to(RUN)))
    require(not studies, "no_real_study_runner_config_in_pilot_root")
    reads.revalidate()
    require(file_hash(labels_path) == complete["labels_sha256"], "diagnostic_labels_unchanged_during_audit")
    return {"schema": "market_pilot_report_evidence_audit_v1", "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "audit_source_sha256": file_hash(__file__), "checks": checked, "read_set": reads.commitment(),
        "raw_hashes": raw_hashes, "diagnostic": {"rows": rows, "games": len(games), "contracts": len(contracts),
            "excluded": excluded, "scheduled": rows + excluded, "scoring_ready": False},
        "metadata": {"candidate_events": family["candidate_events"], "cross_partition_game_ids": overlap,
            "usable_task_count": None}, "old_harbor_fixture": fixture, "cleanup_receipts": cleanup,
        "budget": budget, "budget_dispatches": dispatches, "budget_journal_sha256": file_hash(RUN / "budget/journal.jsonl"),
        "real_study_configs": studies, "scientific_admission": False, "research_result": False,
        "live_inventory_checked": False, "new_provider_calls": 0,
        "limitations": ["Stored metadata audit is not a fresh remote recount.",
            "Label hash/count readback is not original collector clock/session proof.",
            "Old synthetic cloud fixture does not verify the revised general live path.",
            "Cleanup receipts are historical; current inventory must be checked separately.",
            "Token estimate, unresolved holds, invoices and subscription allocation remain distinct."]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-name")
    args = parser.parse_args()
    result = audit()
    if args.output_name:
        name = Path(args.output_name)
        if name.name != args.output_name or name.suffix != ".json":
            raise ValueError("one fresh JSON report filename required")
        identifier(name.stem)
        fresh_json(RUN / args.output_name, result)
    print(json.dumps({k: result[k] for k in ("checked_at_utc", "checks", "diagnostic", "metadata",
        "budget_dispatches", "real_study_configs", "scientific_admission", "new_provider_calls")}, sort_keys=True))
