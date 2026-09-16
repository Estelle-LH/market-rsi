#!/usr/bin/env python3
"""Package source-only evidence for the next controller review; no paid calls."""
import argparse
from pathlib import Path

from market_rsi import digest, file_hash, fresh_json, load_json


def build(artifacts: Path, output: Path):
    sources = {
        "acquisition": artifacts / "historical-raw-ingest-20260909-01/completion.json",
        "clock": artifacts / "historical-all-stream-clock-qa-20260909-02/result.json",
        "keys": artifacts / "historical-global-key-qa-20260909-01/result.json",
        "key_examples": artifacts / "historical-key-collision-examples-20260909-01/result.json",
        "coverage": artifacts / "historical-market-coverage-20260909-01/result.json",
    }
    loaded = {k: load_json(v) for k, v in sources.items()}
    acq, clock, keys, examples, coverage = (loaded[k] for k in sources)
    plan_hash = acq["source_plan_sha256"]
    if (not acq["raw_acquisition_complete"] or clock["source_plan_sha256"] != plan_hash
            or keys["source_plan_sha256"] != plan_hash or clock["failures"]
            or coverage["rows"] != acq["pm_tick_rows"]):
        raise ValueError("completed source evidence does not reconcile")
    for key, filename in (("clock", "snapshot.json"), ("keys", "claim.json"),
                          ("key_examples", "claim.json"), ("coverage", "claim.json")):
        bound = load_json(sources[key].parent / filename)
        if bound.get("source_plan_sha256", bound.get("plan_sha256")) != plan_hash:
            raise ValueError("source evidence claim is bound to another manifest")
    markets = coverage["markets"]
    feedback = {
        "schema": "historical_source_readiness_feedback_v1",
        "source_plan_sha256": plan_hash,
        "scope": "public_raw_source_quality_only_not_prediction_or_objective_results",
        "acquisition": {k: acq[k] for k in ("selected_files", "raw_bytes", "new_payload_bytes", "pm_tick_rows",
            "identity_mismatch_rows", "crossed_quote_rows")},
        "new_historical_download_cap_bytes": 5_000_000_000,
        "remaining_new_download_bytes": 5_000_000_000 - acq["new_payload_bytes"],
        "remaining_download_bytes_is_this_ingest_only_not_global_authority": True,
        "conservative_headroom_after_all_selected_raw_bytes": 5_000_000_000 - acq["raw_bytes"],
        "additional_downloads_admitted": False,
        "before_any_more_downloads": "reconcile_prior_canary_and_failed_transfer_bytes_against_same_global_cap",
        "source_key_checks": keys["streams"],
        "source_key_example_checks": examples["streams"],
        "coverage": {
            "observed_markets": coverage["observed_markets"],
            "actual_utc_dates_with_any_events": len(coverage["actual_utc_receipt_day_event_bins"]),
            "full_utc_days_with_an_event_in_every_minute": coverage["full_utc_days_with_an_event_in_every_minute"],
            "nominal_15m_markets_with_two_sided_events_for_both_tokens_every_second": sum(
                m["seconds_with_two_sided_quotes_for_both_tokens"] == 900 for m in markets),
            "nominal_15m_markets_with_no_same_second_two_token_quotes": sum(
                m["seconds_with_two_sided_quotes_for_both_tokens"] == 0 for m in markets),
            "continuous_executable_quotes_verified": False,
            "independent_samples_equal_row_count": False,
            "absence_of_event_is_not_proof_quote_changed_or_market_was_untradable": True,
        },
        "known_source_contract_issues": [
            "Filename date conventions are mixed; derive research clocks from verified epoch timestamps, not paths.",
            "Synthetic tick IDs reset/recur across different events; never dedup or join globally on id alone.",
            "PM price_change is a book-level change, not a trade execution; price is not automatically midpoint.",
            "Publisher normalizer takes Binance trade messages; no verified Binance BBO stream in these files.",
            "Some final candles were received over a day after close; close value cannot be available at candle_start.",
            "Identity-mismatched and crossed quotes remain flagged; raw acquisition does not admit training.",
            "Smallest-file date selection is size-biased and did not yield 40 verified full sessions.",
        ],
        "research_controls": {
            "runner_chooses_objective": False, "future_labels_used_for_source_QA": False,
            "dev_or_future_test_opened": False, "quiet_raw_rows_deleted": False,
            "source_readiness_is_not_model_progress": True,
            "new_paid_calls_or_purchases": False, "training_admitted": False,
        },
        "pending_before_objective_scoring": [
            "versioned_semantic_field_and_causal_replay_contract_with_tests",
            "explicit_source_key_vs_event_identity_policy_not_id_based_row_deletion",
            "controller_revision_of_data_use_plan_based_on_measured_coverage",
            "controller_selected_open_train_materialization_and_past_only_objective_diagnostics",
            "precommitted_roles_and_unopened_evaluation_windows",
        ],
        "documentation": [
            "https://docs.polymarket.com/api-reference/wss/market",
            "https://github.com/gregyoung14/openmarket/blob/6e6cc240f32ab9fd2f8fa602bd0aba823b24bfee/crates/recorder/src/normalize.rs",
        ],
        "historical_deployed_collector_commit_verified": False,
        "source_artifact_sha256": {k: file_hash(p) for k, p in sources.items()},
    }
    if feedback["remaining_new_download_bytes"] < 0:
        raise ValueError("new historical download cap exceeded")
    output.mkdir(exist_ok=False)
    fresh_json(output / "source-binding.json", {"paths": {k: str(v.absolute()) for k, v in sources.items()},
        "hashes": feedback["source_artifact_sha256"], "builder_sha256": file_hash(__file__)})
    fresh_json(output / "controller-feedback.json", {**feedback, "feedback_sha256": digest(feedback)})
    return feedback


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    value = build(args.artifacts, args.output)
    print({"feedback_built": True, "new_model_calls": False,
           "remaining_new_download_bytes": value["remaining_new_download_bytes"]})
