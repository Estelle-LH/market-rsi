#!/usr/bin/env python3
"""Aggregate verified disjoint closure rows without rerunning model or scorer."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path


def load(path):
    return json.loads(Path(path).read_text())


def binding(path):
    path = Path(path).resolve()
    return {"name": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen", required=True, type=Path)
    parser.add_argument("--historical", required=True, type=Path)
    parser.add_argument("--closure", required=True, action="append", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    frozen, historical = load(args.frozen), load(args.historical)
    closures = [load(path) for path in args.closure]
    if any(c.get("status") != "VERIFIED_SCORED_WINDOW" for c in closures):
        raise ValueError("Every closure must be a verified scored window")
    if any(c.get("pending_count") != 0 or c.get("all_owned_settled") is not True for c in closures):
        raise ValueError("Every closure must have settled fees and zero pending requests")
    rows = [row for c in closures for row in c["window_comparison_rows"]]
    companies = [row["company_id"] for row in rows]
    if companies != frozen["training"] or len(set(companies)) != 25:
        raise ValueError("Closures must cover the frozen 25-company order exactly once")
    if any(c.get("candidate", {}).get("id") != frozen["candidate"]["id"] for c in closures):
        raise ValueError("Candidate mismatch across closures")

    total = Decimal(0)
    for row in rows:
        targets = row["targets"]
        if len(targets) != 5 or {t["target_id"] for t in targets} != {f"T{i:03d}" for i in range(1, 6)}:
            raise ValueError("Each company requires five unique targets")
        points = sum((Decimal(str(t["candidate_award"])) for t in targets), Decimal(0))
        if points != Decimal(str(row["points"])):
            raise ValueError("Target awards do not sum to company points")
        total += points

    old_rows = historical["comparison"]["rows"]
    old_total = sum((Decimal(str(row["points"])) for row in old_rows), Decimal(0))
    old_mean = Decimal(str(historical["comparison"]["candidate_mean"]))
    mean = total / Decimal(25)
    report = {
        "schema": "round17_closure_aggregate_public_v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": frozen["source_commit"],
        "candidate_id": frozen["candidate"]["id"],
        "R_sha256": frozen["candidate"]["R"]["sha256"],
        "H_sha256": frozen["candidate"]["H"]["sha256"],
        "companies": 25,
        "targets": 125,
        "points": float(total),
        "mean": float(mean),
        "historical_points": float(old_total),
        "historical_mean": float(old_mean),
        "delta_points": float(total - old_total),
        "delta_mean": float(mean - old_mean),
        "window_company_counts": [c["window_scored"] for c in closures],
        "total_cost_usd": sum(c["owned_cost_nano_usd"] for c in closures) / 1_000_000_000,
        "closure_bindings": [binding(path) for path in args.closure],
        "privacy": "Company IDs, target predictions and local paths intentionally omitted.",
        "interpretation": "Fresh-provider reproducibility evidence on the same opened-Train panel; not a new candidate gain."
    }
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError("Refusing to overwrite an existing aggregate")
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: report[k] for k in ("companies", "targets", "points", "mean", "delta_mean", "total_cost_usd")}, sort_keys=True))


if __name__ == "__main__":
    main()
