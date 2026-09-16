"""Audit the already-defined 60-second NFL candidate with the generic clock contract.

This audit verifies the historical event-clock semantics of the same-event
state representation.  It deliberately does not claim live feed arrival time,
predictive improvement, profitability, Route-Dev evidence, or Final evidence.
The 60-second horizon belongs only to the experiment being replayed here.  The
generic Harness contract does not choose or freeze a horizon during discovery.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path

from data_scientist_harness.feature_availability_contract import (
    REQUIRED_ORDER,
    audit_feature_availability,
    freeze_feature_availability,
)
from market_rsi import digest, file_hash, fresh_json
from sports_event_research.run_state_surprise_discovery import same_event_post_states
from sports_event_research.run_train_method_screen import TARGET, load_rows


NANOSECONDS = 1_000_000_000


def collect_time_rows(rows: list[dict], receipts: list[dict]) -> list[dict]:
    expected = {(row["game"], row["play_id"]) for row in rows}
    result = []
    for receipt in receipts:
        game = receipt["game"]
        with Path(receipt["panel_path"]).open(newline="") as stream:
            reader = csv.DictReader(stream)
            required = {"play_id", "play_timestamp", "home_price_60s_timestamp", TARGET}
            if not required.issubset(reader.fieldnames or ()):
                raise ValueError("Train panel lacks frozen feature-time fields")
            for raw in reader:
                if raw[TARGET] == "":
                    continue
                key = (game, raw["play_id"])
                if key not in expected:
                    raise ValueError("feature-time row differs from the frozen Train population")
                decision = int(raw["play_timestamp"]) * NANOSECONDS
                label_end = int(raw["home_price_60s_timestamp"]) * NANOSECONDS
                result.append({
                    "row_id": f"{game}/{raw['play_id']}",
                    "feature_event_ns": decision,
                    "feature_available_ns": decision,
                    "decision_ns": decision,
                    # The frozen target is the last eligible trade observed by
                    # the t+60 endpoint, not the first trade after t+60.
                    "label_start_ns": label_end,
                    "label_end_ns": decision + 60 * NANOSECONDS,
                })
    observed = {tuple(row["row_id"].split("/", 1)) for row in result}
    if observed != expected or len(result) != len(expected):
        raise ValueError("feature-time audit did not cover the exact Train population")
    return result


def run(panel_root: Path, selection_root: Path, summary_manifest: Path, output: Path) -> dict:
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("fresh feature-availability audit output required")
    output.mkdir(parents=True)
    try:
        rows, receipts = load_rows(panel_root, selection_root)
        # This replays the corrected same-event binding against the exact PBP files.
        # The returned values are not scored; only the receipts enter the source commitment.
        _, same_event_receipts = same_event_post_states(rows, receipts)
        source_receipt = {
        "schema": "same_event_state_feature_source_receipt_v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "train_games": len(receipts),
        "eligible_rows": len(rows),
        "summary_manifest_sha256": file_hash(summary_manifest),
        "panel_hashes": {row["game"]: row["panel_sha256"] for row in receipts},
        "same_event_receipts": same_event_receipts,
        "clock_boundary": "historical provider event time; live arrival time is not observed",
        "target_horizon_seconds": 60,
        "target_origin": "existing_experiment_replay_not_global_harness_rule",
        "predictive_scores_computed": False,
        "route_dev_opened": False,
        "sealed_final_opened": False,
        }
        source_receipt["record_sha256"] = digest(source_receipt)
        frozen = freeze_feature_availability({
        "contract_id": "same-event-state-wp-delta-historical-clock-v1",
        "feature_names": ["state_wp_delta"],
        "clock_domain": "historical_sportsradar_event_seconds_not_live_arrival",
        "row_id_field": "row_id",
        "feature_event_time_field": "feature_event_ns",
        "feature_available_time_field": "feature_available_ns",
        "decision_time_field": "decision_ns",
        "label_start_time_field": "label_start_ns",
        "label_end_time_field": "label_end_ns",
        "required_order": REQUIRED_ORDER,
        "missing_time_policy": "fail_closed",
        "source_receipt_sha256": source_receipt["record_sha256"],
        })
        audit = audit_feature_availability(frozen, collect_time_rows(rows, receipts))
        fresh_json(output / "source-receipt.json", source_receipt)
        fresh_json(output / "availability-contract.json", frozen)
        fresh_json(output / "audit.json", audit)
        complete = {
        "schema": "same_event_feature_availability_complete_v1",
        "source_receipt_sha256": file_hash(output / "source-receipt.json"),
        "contract_sha256": file_hash(output / "availability-contract.json"),
        "audit_sha256": file_hash(output / "audit.json"),
        "status": audit["status"],
        "train_games": len(receipts),
        "eligible_rows": len(rows),
        "target_horizon_seconds": 60,
        "horizon_selected_by_harness": False,
        "predictive_scores_computed": False,
        "provider_cost_usd": 0,
        "route_dev_opened": False,
        "sealed_final_opened": False,
        }
        fresh_json(output / "complete.json", complete)
        return complete
    except Exception as error:
        fresh_json(output / "failure.json", {
            "schema": "same_event_feature_availability_failure_v1",
            "error_type": type(error).__name__,
            "error": str(error),
            "predictive_scores_computed": False,
            "provider_cost_usd": 0,
            "route_dev_opened": False,
            "sealed_final_opened": False,
        })
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel-root", type=Path, required=True)
    parser.add_argument("--selection-root", type=Path, required=True)
    parser.add_argument("--summary-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(run(args.panel_root, args.selection_root, args.summary_manifest, args.output))


if __name__ == "__main__":
    main()
