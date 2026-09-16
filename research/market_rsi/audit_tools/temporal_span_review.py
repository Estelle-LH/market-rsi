"""Read-only edge-case review using the published temporal implementation.

A lookup tolerance is not a fixed prediction duration. This does not change
the controller's contract, choose a better tolerance, or admit real data.
"""
import argparse
from pathlib import Path
from market_rsi import digest, file_hash, fresh_json, load_json
from data_scientist_harness.store import Store
from data_scientist_harness.temporal_contract import bound_probe, evaluate, validate


def edge_case(contract):
    validate(contract)
    if contract["endpoint_rule"] != "backward_asof":
        raise ValueError("this review is scoped to backward lookup")
    grouped = contract["decision_rule"] == "after_timestamp_group"
    decision_ms = int(grouped)
    h, tolerance = contract["horizon_ms"], contract["endpoint_tolerance_ms"]
    prefix = [(0, .25), (0, .5), (1, .25)] if grouped else [(0, .25)]
    items = prefix + [(decision_ms + h - tolerance, .75), (decision_ms + h + 1, .5)]
    rows = [{"key": [0, i, 0, 0], "source_ms": t, "wrapper_ms": t,
             "value": v, "valid": True} for i, (t, v) in enumerate(items)]
    result = evaluate(rows, contract)
    return {"contract": contract, "synthetic_rows": rows, "result": result,
        "earliest_permitted_span_ms": h - tolerance,
        "nominal_horizon_ms": h, "exact_horizon_required_by_lookup": tolerance == 0,
        "interpretation": "This demonstrates a permitted recorded-observation span, not its frequency in real data. "
            "With backward lookup, a tolerance approaching the horizon permits much shorter observed spans. "
            "It cannot be described as a measured price at exactly the nominal horizon without more evidence. "
            "The controller must justify a different tolerance or explicitly define the variable-span target; "
            "the reviewer chooses neither.",
        "market_rows_read": 0, "fits": 0, "provider_calls": 0,
        "source_admitted": False, "policy_changed": False}


def review(workspace, record_id):
    root = Path(workspace).resolve()
    store = Store(root, file_hash(root / "workspace.json"))
    record = store.get(record_id, "probe_temporal_contract")
    contract = record["arguments"]["contract"]
    binding = bound_probe(store, record_id, contract["horizon_ms"])
    value = {"schema": "temporal_observation_span_review_v1",
        "workspace_manifest_sha256": store.expected, "passing_probe": binding,
        "review_source_sha256": file_hash(__file__), **edge_case(contract),
        "review_is_not_controller_authored": True, "proposal_prose_independently_checked": False}
    value["result_sha256"] = digest(value)
    return value


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--workspace", type=Path, required=True)
    p.add_argument("--record", required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.exists(): raise ValueError("fresh review output required")
    value = review(a.workspace, a.record)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    fresh_json(a.output, value)
    print({k: value[k] for k in ("result_sha256", "nominal_horizon_ms", "earliest_permitted_span_ms", "result")})
