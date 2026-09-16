"""Verify quote-repair receipts and export aggregate-only controller findings.

No model calls or source admission. This is the runner's handoff into the
existing Data Scientist Harness prepare.py --findings interface.
"""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market_rsi import digest, file_hash, fresh_json, load_json
from validate_quote_repair import RAW_CASE_HASHES, CASE_ROW_SHA

RAW_SHA = "27621845de8cc31ca2055235b2a4b69e11a0c6116f3d316f3eda84e647bb4255"
DECODED_SHA = "9dc75c1814796f226e55801cb0ecb662ad1727c05ae3de78f09b8a3ffef22c31"
CSV_SHA = "45c0fbe9de206fce28dd58d7ae37789dfa488f2a1596f799464af1e87af5e050"


def validate(report, claim, claim_sha, packets):
    if report.get("result_sha256") != digest({k: v for k, v in report.items() if k != "result_sha256"}):
        raise ValueError("report hash mismatch")
    if report.get("claim_sha256") != claim_sha:
        raise ValueError("claim hash mismatch")
    if (claim.get("day"), claim.get("hour"), claim.get("source_tag")) != ("2026-08-21", 0, "pm-source-quotes-v0.1.0"):
        raise ValueError("source scope changed")
    if report.get("adapter_sha256") != claim.get("sources", {}).get("quote_source/reconstruct.py"):
        raise ValueError("adapter source mismatch")
    if (report.get("raw_sha256"), report.get("decoded_sha256"), report.get("csv_sha256"),
            report.get("csv_case_sha256"), report.get("raw_records")) != (RAW_SHA, DECODED_SHA, CSV_SHA, CASE_ROW_SHA, 4328805):
        raise ValueError("frozen data differs")
    if any(report.get(k) is not True for k in ("ssh_reaped", "decoder_reaped")) or any(report.get(k) != 0 for k in
            ("exit_code", "decoder_exit_code", "fits", "new_tinker_cost_usd", "raw_frames_exported", "identifiers_exported")):
        raise ValueError("incomplete cleanup or scope expanded")
    if any(report.get(k) is not False for k in
            ("source_mutated", "source_admitted", "new_test_opened", "source_clock_attested", "coverage_admitted")):
        raise ValueError("repair cannot grant source admission")
    terminal = [p.get("report") for p in packets if p.get("stage") == "complete"]
    body = {k: v for k, v in report.items() if k not in ("claim_sha256", "ssh_reaped", "exit_code", "result_sha256")}
    if terminal != [body]:
        raise ValueError("missing or inconsistent terminal packet")
    analysis = report["analysis"]; counts = analysis["counts"]
    if (counts["target_raw_records"] != 65401 or counts["observations"] <= 0
            or sum(analysis["source_status_counts"].values()) != counts["observations"]
            or sum(analysis["same_record_depth_to_source_status"].values()) != counts["observations"]
            or counts["price_candidates"] > counts["observations"]):
        raise ValueError("inconsistent denominators")
    case = analysis["case"]
    if ([c["key"][0] for c in case] != list(RAW_CASE_HASHES)
            or [c["record_sha256"] for c in case] != list(RAW_CASE_HASHES.values())
            or [c["depth_status"] for c in case] != ["crossed", "locked", "uncrossed"]
            or any(c["source_status"] != "uncrossed" or c["price_candidate"] is not True
                   or c["source_size_present"] is not False for c in case)
            or analysis.get("known_cross_record_case_fixed") is not True):
        raise ValueError("known-case repair not verified")
    return analysis


def audit(root):
    report, claim = load_json(root/"report.json"), load_json(root/"claim.json")
    packets = [load_json(p) for p in sorted(root.glob("progress-*.json"))]
    analysis = validate(report, claim, file_hash(root/"claim.json"), packets)
    findings = [
        {"id": "quote-repair-implemented-and-measured", "source_version": claim["source_tag"],
         "source_commit": claim["source_commit"], "report_sha256": file_hash(root/"report.json"),
         "scope": "One previously opened diagnostic hour and one failure-selected token; NOT a population or prediction result.",
         "counts": analysis["counts"], "source_status_counts": analysis["source_status_counts"],
         "depth_to_source_status": analysis["same_record_depth_to_source_status"],
         "issue_counts": analysis["issue_counts"], "snapshot_checks": analysis["full_snapshot_comparisons"],
         "known_case": "Three distinct records reconstruct crossed/locked/uncrossed; all three original source BBO pairs are uncrossed. "
            "New adapter keeps source BBO separate and never borrows stale depth sizes. Case fixed without future backfill or same-time coalescing.",
         "not_proven": ["executable liquidity", "capture-clock semantics", "complete feed", "all CSV crossings explained", "predictive improvement"],
         "source_admitted": False},
        {"id": "remaining-source-work-not-an-algorithm-choice",
         "boundaries": ["Do not repeat the already-completed forensic work as a missing prerequisite.",
            "No interpretation of file mtime as receive-time provenance, absent files as proven outages, or current metadata as historical identity.",
            "No raw rows, keys or hidden tests in controller input. Runner-owned reconstruction is not an external-model tool.",
            "Previously opened Aug21..25 and Sep07..09 are diagnostics; Aug26..Sep06 remains protected.",
            "0/1 best-price boundary semantics are unknown, not invented executable quotes.",
            "price_candidate is only a local syntactic check. Remaining clock/continuity/identity/coverage/feature/objective gates are separate.",
            "No selected target, horizon, split, trainer or model fit is established by this engineering report."]}]
    receipt = {"schema": "quote_repair_handoff_v1", "report_file_sha256": file_hash(root/"report.json"),
        "claim_file_sha256": file_hash(root/"claim.json"), "receipt_integrity_passed": True,
        "known_case_fixed": True, "findings_sha256": digest(findings), "source_admitted": False,
        "fits": 0, "provider_calls": 0}
    receipt["result_sha256"] = digest(receipt)
    return receipt, findings


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True); p.add_argument("--output", type=Path, required=True)
    a = p.parse_args(); receipt, findings = audit(a.run.resolve())
    a.output.mkdir(parents=True, exist_ok=False)
    fresh_json(a.output/"audit.json", receipt); fresh_json(a.output/"findings.json", findings)
    print({"output": str(a.output), "receipt_integrity_passed": True, "new_provider_calls": 0})
