"""Positive canary for the exact v2 refit that exceeded the old 2 GiB cap."""
from __future__ import annotations

import argparse
from pathlib import Path

from market_rsi import digest, file_hash, fresh_json, load_json
from memory_policy.broker_v3 import (
    REFIT_MAX_RSS_GIB, REFIT_TIMEOUT_SECONDS, refit_worker,
)


FAILED_REQUEST_SHA256 = (
    "11fc3a0624ac9c9939138a8ef727631e25fb8167c3748160751f2456a7d87abf")


def source_hashes():
    root = Path(__file__).resolve().parents[1]
    paths = (
        "memory_pilot/learning.py",
        "memory_policy/broker.py",
        "memory_policy/broker_v3.py",
        "memory_policy/trainer_canary_v3.py",
    )
    return {path: file_hash(root / path) for path in paths}


def run(failed_directory, output):
    failed_directory = Path(failed_directory).resolve()
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("fresh trainer canary ID required")
    request_path = failed_directory / "request.json"
    failure_path = failed_directory / "failure.json"
    cleanup_path = failed_directory / "cleanup.json"
    request = load_json(request_path)
    failure = load_json(failure_path)
    cleanup = load_json(cleanup_path)
    if (file_hash(request_path) != FAILED_REQUEST_SHA256
            or request.get("check") != []
            or failure != {"type": "MemoryError",
                           "message": "trainer RSS exceeds 2 GiB; no silent subsampling"}
            or cleanup.get("peak_rss_kib", 0) <= 2 * 1024**2
            or cleanup.get("process_reaped") is not True):
        raise ValueError("exact negative resource canary required")
    output.mkdir()
    fresh_json(output / "claim.json", {
        "schema": "memory_policy_trainer_canary_claim_v3",
        "failed_request_sha256": file_hash(request_path),
        "failed_failure_sha256": file_hash(failure_path),
        "failed_cleanup_sha256": file_hash(cleanup_path),
        "source_hashes": source_hashes(),
        "changed_stage": "trainer_resource_envelope",
        "scientific_plan_or_rows_changed": False,
        "model_may_be_reused_for_training": False,
        "provider_calls_allowed": 0,
    })
    result = refit_worker(request, output / "positive-refit")
    if not result["success"]:
        raise RuntimeError("v3 positive trainer canary failed")
    fit = result["result"]["fit"]
    positive_cleanup = load_json(output / "positive-refit/cleanup.json")
    if (fit["fit_rows"] != 6_105_040
            or result["result"]["scores"] != []
            or result["result"]["provider_calls"] != 0
            or positive_cleanup.get("process_reaped") is not True
            or positive_cleanup.get("max_rss_gib") != REFIT_MAX_RSS_GIB
            or positive_cleanup.get("timeout_seconds") != REFIT_TIMEOUT_SECONDS
            or positive_cleanup.get("peak_rss_kib", 0) > REFIT_MAX_RSS_GIB * 1024**2):
        raise ValueError("positive trainer canary evidence differs")
    value = {
        "schema": "memory_policy_trainer_canary_v3",
        "passed": True,
        "negative_canary": {
            "request_sha256": file_hash(request_path),
            "failure_sha256": file_hash(failure_path),
            "cleanup_sha256": file_hash(cleanup_path),
            "old_max_rss_gib": 2,
            "observed_peak_rss_kib": cleanup["peak_rss_kib"],
        },
        "positive_canary": {
            "result_sha256": result["result_sha256"],
            "fit_rows": fit["fit_rows"],
            "peak_rss_kib": positive_cleanup["peak_rss_kib"],
            "max_rss_gib": REFIT_MAX_RSS_GIB,
            "timeout_seconds": REFIT_TIMEOUT_SECONDS,
            "provider_calls": 0,
            "scores_opened": 0,
        },
        "source_hashes": source_hashes(),
        "model_may_be_reused_for_training": False,
    }
    value["result_sha256"] = digest(value)
    fresh_json(output / "canary.json", value)
    return value


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--failed-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = run(args.failed_directory, args.output)
    print({"passed": value["passed"],
           "fit_rows": value["positive_canary"]["fit_rows"],
           "provider_calls": 0, "scores_opened": 0})
