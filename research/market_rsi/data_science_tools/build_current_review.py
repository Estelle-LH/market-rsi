"""Build a traceable, INCOMPLETE review from existing Vantage QA, no model calls.

Past OpenMarket problems are lessons, not claims that the same anomalies were
observed in Vantage. Missing checks remain unknown; this cannot issue a pass.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from data_science_tools import pipeline as p
from audit_tools.vantage_coverage_conclusion import conclude, PLAN_SHA256
from market_rsi import fresh_json


LESSONS = [
    {"problem": "File size and filename span overstate usable history", "source_scope": "Vantage current QA",
     "handling": "Use actual UTC day/market coverage and heartbeat evidence, not GB or first/last timestamps. Missing dates cannot be filled."},
    {"problem": "104836 token/market mismatches; 320 crossed quotes", "source_scope": "OpenMarket archived QA, not a Vantage finding",
     "handling": "Preserve raw identity and ordinals; quarantine derived invalid states. Do not guess replacement identities or resurrect an older good quote."},
    {"problem": "Local IDs recur across different events", "source_scope": "OpenMarket archived QA",
     "handling": "Use source/file/row identity. Remove derived duplicates only after exact event equality is verified; keep both original records."},
    {"problem": "Mixed filename dates and late finalized candles", "source_scope": "OpenMarket archived QA",
     "handling": "Establish event/receipt/availability clocks. As-of joins only; never use final candle values at the interval start."},
    {"problem": "Trade price, book delta and midpoint are not interchangeable", "source_scope": "Both sources require source-specific evidence",
     "handling": "Verify units and semantics against pinned schema and raw fields. Treat unavailable inputs as unavailable, not substitute silently."},
    {"problem": "Quiet labels dominate; small raw MSE can look impressive", "source_scope": "Earlier opened-Train diagnostics",
     "handling": "Measure target activity/noise and persistence error in explicit units on Train. Controller selects sampling/target before Dev; preserve full evaluation population."},
    {"problem": "Repeated use of a few dates is not new validation", "source_scope": "Earlier t7 diagnostics",
     "handling": "Time and whole-market split; purge label overlap; register exposure. Report paired daily uncertainty, not independent-row confidence."},
]


def build(output):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("fresh review directory required")
    base = ROOT / "artifacts/vantage-indexed-metadata-20260910-02"
    conclusion_path = base / "conclusion.json"
    plan_path = ROOT / "artifacts/historical-source-review-v2-controller-20260910-01/workspace/plans/src-cmp-oracle-canary-tape-receiptclock-v2/result.json"
    plan = p._read_pinned(plan_path, PLAN_SHA256)
    raw = conclusion_path.read_bytes()
    conclusion_sha = hashlib.sha256(raw).hexdigest()
    conclusion = p._read_pinned(conclusion_path, conclusion_sha)
    inputs = {str(plan_path): PLAN_SHA256, str(conclusion_path): conclusion_sha}
    loaded = {}
    repo = ROOT.parents[1]
    for name, sha in conclusion["receipt_sha256"].items():
        path = (repo / name).resolve()
        if path.parent != base:
            raise ValueError("unexpected receipt directory")
        loaded[path.name] = p._read_pinned(path, sha)
        inputs[str(path)] = sha
    rebuilt = conclude(plan, loaded["calendar.json"],
                        [v for k, v in loaded.items() if k.startswith("day-")])
    if any(conclusion.get(k) != value for k, value in rebuilt.items()):
        raise ValueError("coverage conclusion differs from source receipts")
    if rebuilt["necessary_calendar_condition_passed"] is not False:
        raise ValueError("this feedback builder is only for the observed failed source gate")
    bindings = dict.fromkeys(p.BINDINGS)
    bindings.update(source_plan=PLAN_SHA256, raw_manifest=p.digest(plan["body"]["objects"]))
    spec = {"schema": p.SCHEMA, "scope_id": output.name, "bindings": bindings,
            "controls": dict(p.CONTROLS), "controller_owns": ["source", "sampling", "features", "objective", "model"],
            "pipeline_policy_sha256": p.policy_sha256()}
    spec["spec_sha256"] = p.digest(spec)
    checks = []
    for name in ("actual_day_market_coverage", "independent_sample_breadth"):
        checks.append({"check_id": name, "status": "fail", "scope_id": spec["scope_id"],
                       "bindings": {k: bindings[k] for k in p.CHECK_STAGE[name][2]},
                       "reason": "Vantage alone has at most 6 candidate dates against the existing controller minimum of 20; 617 event-minutes total. Primary object not inspected.",
                       "evidence_refs": [{"path": str(conclusion_path), "sha256": conclusion_sha}],
                       "reviewer_role": "trusted_runner_review"})
    report = p.evaluate(spec, checks)
    feedback = {"schema": "controller_data_science_feedback_v1", "scope_id": spec["scope_id"],
                "spec_sha256": spec["spec_sha256"], "readiness": report,
                "coverage": {k: rebuilt[k] for k in ("scope", "daily", "controller_minimum_complete_sessions",
                    "possible_session_count_upper_bound", "total_pm_rows_in_controller_window", "total_distinct_utc_event_minutes")},
                "source_plan_still_preserved": True, "pending_primary_not_assumed_bad": True,
                "earlier_source_lessons": LESSONS,
                "instruction": "Complete data-science research before formal experiments. Inspect all stages and existing evidence. Propose the next defensible data action or request genuinely missing metadata; do not self-certify QA, alter t7/target silently, or interpret absent records as no price movement.",
                "existing_frozen_model_and_target_unchanged": True,
                "new_source_component_bindings_pending": [k for k, v in bindings.items() if v is None],
                "project_download_and_backup_accounting_separate": True,
                "raw_download_bytes_recorded": 8173310025,
                "backup_upload_bytes_recorded": 3164694656,
                "legacy_combined_transfer_guard_remaining_bytes": 3661995319,
                "download_only_arithmetic_headroom_bytes": 6826689975,
                "accounting_scope_is_not_provider_allowance_or_new_authority": True,
                "new_raw_download_or_budget_permission": False,
                "data_science_complete": False, "formal_experiment_allowed": False,
                "new_model_calls": 0, "new_prices_or_labels_read": False}
    transfer = ROOT / "artifacts/s3-backup-20260910-01/cumulative-transfer-update.json"
    transfer_bytes = transfer.read_bytes()
    t = json.loads(transfer_bytes)
    if (t["prior_actual_raw_bytes"] != feedback["raw_download_bytes_recorded"]
            or t["new_actual_backup_body_bytes"] != feedback["backup_upload_bytes_recorded"]
            or t["remaining_bytes"] != feedback["legacy_combined_transfer_guard_remaining_bytes"]):
        raise ValueError("transfer evidence changed")
    inputs[str(transfer)] = hashlib.sha256(transfer_bytes).hexdigest()
    feedback["feedback_sha256"] = p.digest(feedback)
    output.mkdir(parents=True, exist_ok=False)
    for name, value in (("spec.json", spec), ("reviewed-checks.json", checks),
                        ("readiness.json", report), ("controller-feedback.json", feedback)):
        fresh_json(output / name, value)
    fresh_json(output / "bindings.json", {"inputs": inputs,
               "source_sha256": {f.name: hashlib.sha256(f.read_bytes()).hexdigest()
                   for f in (Path(__file__), Path(p.__file__))},
               "new_downloads": 0, "new_fits": 0, "old_sources_unchanged": True})
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    result = build(parser.parse_args().output)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
