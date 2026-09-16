"""Fresh D10 diagnostic QA, never an inherited Vantage admission report.

Runner-side adapter v0.1.0; the released DSH policy is unchanged. The diagnostic
manifest is NOT a controller-selected training plan or an admitted input cache.
"""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data_science_tools import pipeline as p
from market_rsi import digest, file_hash, fresh_json, load_json
from audit_population_quote_profile import audit

VERSION = "pm-source-review-v0.1.0"
RAW_PATH = "/opt/d10/raw/data/polymarket/polymarket-20260821T00.jsonl.zst"
RAW_SHA = "27621845de8cc31ca2055235b2a4b69e11a0c6116f3d316f3eda84e647bb4255"
ROOT = Path(__file__).resolve().parents[1]


def diagnostic_manifest(report):
    if (report.get("mode") != "hour" or report.get("full_hour_decoded") is not True
            or report.get("source_sha256") != RAW_SHA or report.get("source_bytes") != 331091663
            or report.get("raw_records") != 4328805 or report.get("source_admitted") is not False):
        raise ValueError("completed exact D10 hour required; pilot is not current full-hour QA")
    return {"schema": "source_diagnostic_manifest_v1", "source_id": "d10_polymarket_raw",
        "purpose": "opened_source_diagnostic_only", "controller_training_plan": False,
        "objects": [{"host": "173.255.231.4", "path": RAW_PATH, "sha256": RAW_SHA,
                     "bytes": report["source_bytes"], "records": report["raw_records"],
                     "decoded_sha256": report["decoded_sha256"]}],
        "opened_dates": ["2026-08-21"], "complete_sessions_proven": False,
        "broader_inventory_complete": False, "formal_source_admitted": False}


def review_values(scope_id, raw_manifest_sha, audit_ref):
    bindings = dict.fromkeys(p.BINDINGS)
    # No source_plan is fabricated on the controller's behalf. A source-research
    # work order and a diagnostic raw object do not constitute a training plan.
    bindings["raw_manifest"] = raw_manifest_sha
    spec = {"schema": p.SCHEMA, "scope_id": scope_id, "bindings": bindings,
            "controls": dict(p.CONTROLS), "controller_owns": ["source", "sampling", "features", "objective", "model"],
            "pipeline_policy_sha256": p.policy_sha256()}
    spec["spec_sha256"] = p.digest(spec)
    reasons = {
        "selected_objects_accounted": "The exact opened D10 hour is accounted for, not a complete controller-selected source inventory.",
        "immutable_raw_and_provenance": "Raw and decoded hashes verified for this one D10 file; no formal source plan is frozen.",
        "download_backup_disk_accounting": "This scan exported aggregates only; full D10 backup and source-plan accounting remain outside this review.",
        "actual_day_market_coverage": "One complete raw hourly object was scanned across all observed tokens. This is not a full day or proof of 20 untouched sessions. Old Vantage six-date coverage is not a D10 measurement.",
        "quiet_vs_outage": "Observed minute/gap tables do not prove heartbeat coverage, quiet periods or outages.",
        "independent_sample_breadth": "Tokens, quote events and one hourly file are not independent predictive samples; no target, dependence analysis or final cohort is established.",
        "source_scoped_event_keys": "Raw ordinals and inner indices were preserved; unroutable/unknown messages remain counted. Historical source semantics are not fully attested.",
        "market_token_identity": "Observed asset/market hashes describe source messages, not an attested historical Gamma mapping.",
        "quote_trade_units": "Source BBO and reconstructed depth were separated; no trade-target or execution-size validity is certified.",
        "anomalies_traceable": "Known three-record case and per-token anomaly counts were reproduced; broader source conformance remains unverified.",
        "source_and_receipt_clock": "Observed source regressions and clock fields do not establish receipt/availability time; file mtime is not a clock attestation.",
        "reconnect_snapshot_state": "Snapshot and unanchored-delta counts are descriptive; broader reconnect and gap rules are not a frozen replay contract.",
        "train_target_activity_and_noise": "Adjacent repeated midpoints are not fixed-horizon labels. No target was selected and no future-movement filtering was performed.",
        "opened_periods_not_fresh": "This Aug21 hour was already opened. No new Test was accessed; no formal split has been selected.",
    }
    checks = [{"check_id": name, "status": "unknown", "scope_id": scope_id,
        "bindings": {k: bindings[k] for k in p.CHECK_STAGE[name][2]}, "reason": reason,
        "evidence_refs": [audit_ref], "reviewer_role": "trusted_runner_review"}
        for name, reason in reasons.items()]
    return spec, checks


def verify_current_quality(quality, *, expected_scope, expected_raw_manifest_sha):
    """Reject even internally valid QA if it belongs to another source/scope."""
    report = p.verify_review_files(**quality)
    if (report["scope_id"] != expected_scope
            or report["component_bindings"]["raw_manifest"] != expected_raw_manifest_sha):
        raise ValueError("quality belongs to a different source/scope; never inherit parent QA")
    if any(v is not None for k, v in report["component_bindings"].items() if k != "raw_manifest"):
        raise ValueError("source diagnostic cannot import scientific contracts")
    if report["data_science_ready"] or report["execution_admitted"]:
        raise ValueError("diagnostic is not admission")
    return report


def build(output, run):
    output, run = Path(output).resolve(), Path(run).resolve()
    if output.exists(): raise ValueError("fresh source-specific QA directory required")
    result = audit(run)
    report = load_json(run/"report.json")
    manifest = diagnostic_manifest(report)
    output.mkdir(parents=True, exist_ok=False)
    fresh_json(output/"raw-manifest.json", manifest)
    fresh_json(output/"population-audit.json", result)
    ref = {"path": str(output/"population-audit.json"), "sha256": file_hash(output/"population-audit.json")}
    spec, checks = review_values(output.name, file_hash(output/"raw-manifest.json"), ref)
    fresh_json(output/"spec.json", spec); fresh_json(output/"reviewed-checks.json", checks)
    quality = {"spec_path": str(output/"spec.json"), "spec_sha256": file_hash(output/"spec.json"),
               "review_path": str(output/"reviewed-checks.json"), "review_sha256": file_hash(output/"reviewed-checks.json")}
    readiness = verify_current_quality(quality, expected_scope=output.name,
                                      expected_raw_manifest_sha=file_hash(output/"raw-manifest.json"))
    fresh_json(output/"readiness.json", readiness)
    old = ROOT/"artifacts/data-science-review-20260910-02"
    history = {"source_id": "vantage_oraclemangle_source_plan", "history_not_current_qa": True,
        "spec_path": str(old/"spec.json"), "spec_sha256": file_hash(old/"spec.json"),
        "review_path": str(old/"reviewed-checks.json"), "review_sha256": file_hash(old/"reviewed-checks.json")}
    receipt = {"schema": "source_scoped_qa_bundle_v1", "version": VERSION, "quality": quality,
        "scope_id": output.name, "source_id": manifest["source_id"],
        "raw_manifest": {"path": str(output/"raw-manifest.json"), "sha256": file_hash(output/"raw-manifest.json")},
        "audit": ref, "report": {"path": str(run/"report.json"), "sha256": file_hash(run/"report.json")},
        "historical_source_review": history, "review_adapter_sha256": file_hash(__file__),
        "source_admitted": False, "provider_calls": 0, "fits": 0,
        "warning": "Current D10 diagnostic QA replaces stale Vantage QA in the next fresh workspace only. Prior workspaces and failures remain unchanged. Unknown is not pass."}
    receipt["result_sha256"] = digest(receipt)
    fresh_json(output/"bundle.json", receipt)
    return receipt


def read_bundle(path, expected_sha):
    path = Path(path).resolve()
    if file_hash(path) != expected_sha: raise ValueError("QA bundle bytes changed")
    bundle = load_json(path)
    if (bundle.get("schema") != "source_scoped_qa_bundle_v1" or bundle.get("version") != VERSION
            or bundle.get("result_sha256") != digest({k: v for k, v in bundle.items() if k != "result_sha256"})
            or bundle.get("source_id") != "d10_polymarket_raw" or bundle.get("source_admitted") is not False):
        raise ValueError("source-scoped QA bundle changed")
    for name in ("raw_manifest", "audit", "report"):
        ref = bundle[name]
        if file_hash(ref["path"]) != ref["sha256"]: raise ValueError("QA evidence changed: "+name)
    raw = load_json(bundle["raw_manifest"]["path"])
    report = load_json(bundle["report"]["path"])
    if raw != diagnostic_manifest(report): raise ValueError("raw scope differs from diagnostic")
    rebuilt = audit(Path(bundle["report"]["path"]).parent)
    if rebuilt != load_json(bundle["audit"]["path"]): raise ValueError("QA audit no longer reproducible")
    verify_current_quality(bundle["quality"], expected_scope=bundle["scope_id"],
                           expected_raw_manifest_sha=bundle["raw_manifest"]["sha256"])
    return bundle


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True); parser.add_argument("--output", type=Path, required=True)
    a = parser.parse_args(); print(build(a.output, a.run))
