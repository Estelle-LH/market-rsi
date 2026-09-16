"""Derive a fail-closed necessary condition from the controller's own plan.

This does not admit a source or call a model. Even sufficient date presence
would not establish quote semantics, full sessions, or a clean holdout.
"""
import argparse
import hashlib
import json
from pathlib import Path


PLAN_SHA256 = "891d810f291a83d2df0adcc1ffcb2f62f98ceb4cc2740a31e497058d77c64bcd"


def conclude(plan, calendar, days):
    if calendar.get("status") != "complete" or calendar.get("prices_payloads_labels_read") is not False:
        raise ValueError("complete metadata-only calendar required")
    expected_identity = calendar.get("unchanged_identity")
    if not isinstance(expected_identity, dict) or not expected_identity:
        raise ValueError("source identity missing")
    minimum = plan["body"]["minimum_complete_sessions"]
    if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 1:
        raise ValueError("invalid controller minimum")
    required = ("pm_events", "cex_trades", "heartbeats")
    tables = calendar["observations"]["tables"]
    # All-symbol/all-event presence is an intentionally optimistic upper bound:
    # a PM/BTC-specific eligibility check can only remove dates, not add them.
    present = {k: set(tables[k]["present_dates_union"]) for k in required}
    possible = sorted(set.intersection(*present.values()))
    reports = {}
    for report in days:
        if report.get("status") != "complete" or report.get("prices_payloads_labels_read") is not False:
            raise ValueError("complete metadata-only day required")
        if report.get("unchanged_identity") != expected_identity:
            raise ValueError("mixed source identities")
        date = report["observations"]["date_utc"]
        if date in reports:
            raise ValueError("duplicate day receipt")
        reports[date] = report
    if set(reports) != set(possible):
        raise ValueError("day receipts must match candidate dates exactly")
    daily = [{"date_utc": date,
              "pm_rows": reports[date]["observations"]["tables"]["pm_events"]["rows"],
              "pm_occupied_minutes": reports[date]["observations"]["tables"]["pm_events"]["occupied_minutes_union"],
              "process_heartbeat_minutes": next((x["occupied_minutes"] for x in
                  reports[date]["observations"]["tables"]["heartbeats"]["partitions"]
                  if x["source"] == "process"), 0)} for date in possible]
    return {"schema": "vantage_metadata_coverage_conclusion_v1",
            "controller_plan_id": plan["body"]["plan_id"],
            "controller_minimum_complete_sessions": minimum,
            "possible_session_count_upper_bound": len(possible),
            "necessary_calendar_condition_passed": len(possible) >= minimum,
            "source_admitted": False, "fresh_validation_claim": False,
            "scope": "Vantage object alone; selected primary object remains uninspected",
            "full_sha256_recomputed": False, "source_identity": expected_identity,
            "daily": daily,
            "total_pm_rows_in_controller_window": sum(d["pm_rows"] for d in daily),
            "total_distinct_utc_event_minutes": sum(d["pm_occupied_minutes"] for d in daily),
            "next_action": "Return observed source-QA failure to controller. Preserve both selected objects "
            "and original transfer cap; no training, source substitution, silent rule relaxation or fresh holdout claim."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-dir", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plan_bytes = args.plan.read_bytes()
    if hashlib.sha256(plan_bytes).hexdigest() != PLAN_SHA256:
        raise ValueError("wrong frozen controller plan")
    receipts = {}
    def read(path):
        raw = path.read_bytes()
        receipts[str(path)] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)
    calendar = read(args.audit_dir / "calendar.json")
    dates = sorted(set.intersection(*(set(calendar["observations"]["tables"][k]["present_dates_union"])
                   for k in ("pm_events", "cex_trades", "heartbeats"))))
    result = conclude(json.loads(plan_bytes), calendar,
                      [read(args.audit_dir / ("day-" + d + ".json")) for d in dates])
    result["receipt_sha256"] = receipts
    result["controller_plan_file_sha256"] = PLAN_SHA256
    result["audit_source_sha256"] = hashlib.sha256(Path(__file__).with_name("vantage_metadata_audit.py").read_bytes()).hexdigest()
    # Exclusive append-only artifact: never overwrite an earlier conclusion.
    with args.output.open("x") as output:
        json.dump(result, output, sort_keys=True, indent=2)
        output.write("\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
