#!/usr/bin/env python3
"""Project one frozen objective from dense runner labels into formal rows."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from market_rsi import digest, file_hash, fresh_json
from objective_contract import label_delay_bounds_ms, validate_objective_contract


REQUIRED_ROW_FIELDS = {
    "row_id", "game_id", "market_id", "game_start_ms", "decision_ms",
    "feature_available_ms", "label_available_ms", "features", "input_source",
}


def project(inputs: list[Path], objective_contract_path: Path) -> dict:
    if not inputs:
        raise ValueError("at least one dense objective materialization required")
    objective_contract_path = Path(objective_contract_path).resolve()
    objective = validate_objective_contract(
        json.loads(objective_contract_path.read_bytes())
    )
    objective_id = objective["objective_id"]
    minimum_delay_ms, maximum_delay_ms = label_delay_bounds_ms(objective)
    rows, receipts, seen = [], [], set()
    for path in inputs:
        path = Path(path).resolve()
        value = json.loads(path.read_bytes())
        if (value.get("schema") != "polymarket_objective_labels_v1"
                or value.get("scientific_admission") is not False
                or value.get("future_test_used") is not False
                or not isinstance(value.get("rows"), list)):
            raise ValueError("runner-owned dense objective materialization required")
        selected = 0
        for row in value["rows"]:
            if not REQUIRED_ROW_FIELDS <= set(row):
                raise ValueError("dense row identity or causal clock is incomplete")
            if row["row_id"] in seen:
                raise ValueError("duplicate row across objective materializations")
            seen.add(row["row_id"])
            target = row.get("target_candidates", {}).get(objective_id)
            if target is None:
                continue
            if (isinstance(target, bool) or not isinstance(target, (int, float))
                    or not math.isfinite(target) or not 0 <= target <= 1):
                raise ValueError("selected target must be a finite probability")
            projected = {key: row[key] for key in REQUIRED_ROW_FIELDS}
            # Dense discovery rows wait for the largest audited horizon.  A
            # formal projection must instead use the selected objective's own
            # frozen availability time, otherwise a five-minute label inherits
            # the fifteen-minute grid's close time (or the next sparse quote).
            projected["label_available_ms"] = (
                row["decision_ms"] + maximum_delay_ms
            )
            if row["label_available_ms"] < projected["label_available_ms"]:
                raise ValueError("dense source closed before selected objective label")
            projected["target"] = float(target)
            rows.append(projected)
            selected += 1
        receipts.append({
            "path": str(path),
            "sha256": file_hash(path),
            "source_bundle_sha256": value.get("source_bundle_sha256"),
            "source_rows": len(value["rows"]),
            "selected_rows": selected,
        })
    if not rows:
        raise ValueError("selected objective has no executable rows")
    rows.sort(key=lambda row: (row["decision_ms"], row["row_id"]))
    return {
        "schema": "polymarket_midpoint_labels_v1",
        "evidence_class": "historical_diagnostic",
        "scientific_admission": False,
        "test_opened": False,
        "future_test_used": False,
        "objective_id": objective_id,
        "objective_contract_path": str(objective_contract_path),
        "objective_contract_sha256": objective["objective_contract_sha256"],
        "label_delay_bounds_ms": [minimum_delay_ms, maximum_delay_ms],
        "label_availability_rule": "selected_objective_contract",
        "source_materializations": receipts,
        "source_bundle_sha256": digest({
            "objective_contract_sha256": objective["objective_contract_sha256"],
            "source_materializations": receipts,
        }),
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", required=True, type=Path)
    parser.add_argument("--objective-contract", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = project(args.input, args.objective_contract)
    fresh_json(args.output, result)
    print(json.dumps({
        "output": str(args.output),
        "objective_id": result["objective_id"],
        "rows": len(result["rows"]),
        "sources": len(result["source_materializations"]),
    }, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
