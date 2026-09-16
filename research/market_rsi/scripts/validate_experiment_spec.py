"""Fail-closed validation for Market RSI experiment specifications."""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from market_rsi import canonical, digest, load_json


def _session(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("session IDs must be strings")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H")
    except ValueError as error:
        raise ValueError("session IDs must use YYYY-MM-DDTHH") from error
    if parsed.strftime("%Y-%m-%dT%H") != value:
        raise ValueError("session IDs must be canonical")
    return parsed


def validate(spec: dict) -> dict:
    required = {
        "schema", "experiment_id", "question", "changed_stage", "arms",
        "component_hashes", "fixed_contract", "initial_train", "dev",
        "final", "rounds", "minimum_final_sessions", "formal_promotion",
        "stop_policy", "budget", "prior_exposure", "claim_limits",
    }
    if not isinstance(spec, dict) or set(spec) != required:
        raise ValueError("unexpected experiment specification fields")
    if spec["schema"] != "market_rsi_memory_replication_v1":
        raise ValueError("wrong experiment schema")
    if spec["changed_stage"] != "controller_memory":
        raise ValueError("this study may change only controller memory")
    arms = spec["arms"]
    if set(arms) != {"fresh", "archive"}:
        raise ValueError("exact archive and fresh arms required")
    fresh = arms["fresh"]
    archive = arms["archive"]
    if (set(fresh) != {"prior_own_round_records"}
            or set(archive) != {"prior_own_round_records"}
            or fresh["prior_own_round_records"] != "hidden"
            or archive["prior_own_round_records"] != "visible"):
        raise ValueError("arms must differ only in prior own-round archive visibility")
    hashes = spec["component_hashes"]
    expected = {name: digest({"arm": name, **value, "all_other_inputs": "identical"})
                for name, value in arms.items()}
    if hashes != expected or hashes["fresh"] == hashes["archive"]:
        raise ValueError("declared arm hashes do not match canonical components")

    fixed = spec["fixed_contract"]
    expected_fixed = {
        "target_contract_sha256", "target", "horizon_seconds", "latency",
        "costs", "row_policy", "controller_model", "harness", "seed",
        "candidate_library", "trainer_selection", "normalizer_selection",
        "final_metric", "pnl_policy",
    }
    if set(fixed) != expected_fixed:
        raise ValueError("incomplete fixed scientific contract")
    if (fixed["horizon_seconds"] != 60 or fixed["seed"] != 23
            or fixed["final_metric"] != "equal-session mean squared error"
            or fixed["pnl_policy"] != "not measured"
            or fixed["trainer_selection"] != "same frozen Train-only library"
            or fixed["normalizer_selection"] != "same frozen Train-only library"):
        raise ValueError("target/evaluation or symmetric search-space contract changed")

    train = spec["initial_train"]
    dev = spec["dev"]
    final = spec["final"]
    if spec["rounds"] != len(dev) or not 8 <= spec["rounds"] <= 12:
        raise ValueError("replication must predeclare eight to twelve rounds")
    if spec["minimum_final_sessions"] < 20 or len(final) < spec["minimum_final_sessions"]:
        raise ValueError("at least twenty final sessions required")
    if spec["formal_promotion"] is not False:
        raise ValueError("hourly expanded pilot is not formal promotion evidence")
    all_rows = train + dev + final
    if any(set(row) != {"session", "compressed_bytes"} for row in all_rows):
        raise ValueError("session manifests require exact identity and byte count")
    names = [row["session"] for row in all_rows]
    if len(names) != len(set(names)) or any(type(row["compressed_bytes"]) is not int
                                            or row["compressed_bytes"] <= 0 for row in all_rows):
        raise ValueError("source sessions must be unique with positive exact bytes")
    parsed_train = [_session(row["session"]) for row in train]
    parsed_dev = [_session(row["session"]) for row in dev]
    parsed_final = [_session(row["session"]) for row in final]
    if (parsed_train != sorted(parsed_train) or parsed_dev != sorted(parsed_dev)
            or parsed_final != sorted(parsed_final)
            or max(parsed_train) >= min(parsed_dev) or max(parsed_dev) >= min(parsed_final)):
        raise ValueError("strict chronological Train, Dev and Final blocks required")
    if any(row["session"] in spec["prior_exposure"]["opened_final_sessions"] for row in final):
        raise ValueError("previously opened final data cannot be reused")
    if len({value.date() for value in parsed_final}) < 20 and spec["formal_promotion"]:
        raise ValueError("formal promotion requires twenty distinct UTC dates")
    if spec["stop_policy"] != {
        "planned_rounds": spec["rounds"],
        "performance_early_stop": False,
        "stop_before_unaffordable_atomic_pair": True,
        "no_score_retry": True,
    }:
        raise ValueError("stop policy must not use opened Final or cherry-pick scores")
    if (spec["budget"].get("existing_global_cap_usd") != "200"
            or spec["budget"].get("new_authorization_usd") != "0"):
        raise ValueError("only the existing two-hundred-dollar authorization is allowed")
    return spec


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    args = parser.parse_args()
    spec = validate(load_json(args.spec.resolve()))
    print(canonical({
        "valid": True,
        "experiment_id": spec["experiment_id"],
        "rounds": spec["rounds"],
        "final_sessions": len(spec["final"]),
        "formal_promotion": spec["formal_promotion"],
        "spec_sha256": digest(spec),
    }))


if __name__ == "__main__":
    main()
