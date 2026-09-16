"""Fail-closed contract for adding historical sports-market data to Train.

This module does not download, purchase, open, or admit data.  It turns a
data-shortage observation into an executable acquisition/alignment plan and
requires a machine receipt before a batch can enter a versioned Train candidate.
Previously opened periods remain diagnostic/Train; they cannot become a fresh
Dev or Final split after inspection.
"""
from __future__ import annotations

from market_rsi import digest


PLAN_FIELDS = {
    "plan_id",
    "parent_harness_version",
    "evidence_refs",
    "current_independent_units",
    "independent_unit",
    "minimum_total_units",
    "minimum_seasons",
    "candidate_sources",
    "required_fields",
    "immutable_row_key",
    "timestamp_policy",
    "alignment_policy",
    "minimum_target_coverage",
    "regime_minimums",
    "learning_curve_units",
    "opened_periods",
    "reserved_periods",
    "maximum_cost_usd",
    "external_actions_authorized",
    "train_only_admission",
}

SOURCE_FIELDS = {
    "source_id",
    "venue",
    "coverage_start",
    "coverage_end",
    "access_path",
    "license_status",
    "sample_status",
}

BATCH_FIELDS = {
    "batch_id",
    "plan_sha256",
    "source_id",
    "source_object_hashes",
    "license_allows_research_storage",
    "independent_units",
    "season_count",
    "row_count",
    "immutable_row_key_unique",
    "timestamps_utc",
    "timestamps_monotonic_within_unit",
    "duplicate_rate",
    "missing_required_field_rate",
    "target_coverage",
    "alignment_success_rate",
    "regime_counts",
    "opened_period_overlap_only",
    "reserved_period_overlap",
    "route_dev_opened",
    "sealed_final_opened",
    "raw_objects_preserved",
    "derived_rows_hash",
    "cost_usd",
}


def current_nfl_history_plan() -> dict:
    """Concrete first outer-harness work order; it grants no external authority."""
    return {
        "plan_id": "nfl-multiseason-train-strengthening-20260915-v1",
        "parent_harness_version": "co-evolving-strong-harness-dev-h0",
        "evidence_refs": [
            "artifacts/nfl-train-method-screen-20260915-02/result.json",
            "artifacts/nfl-train-rsi-trajectory-20260915-01/trajectory.json",
        ],
        "current_independent_units": 163,
        "independent_unit": "game",
        "minimum_total_units": 600,
        "minimum_seasons": 3,
        "candidate_sources": [
            {
                "source_id": "public-polymarket-history",
                "venue": "polymarket",
                "coverage_start": "2021-01-01",
                "coverage_end": "2025-12-31",
                "access_path": "public archive plus verified official/on-chain reconstruction",
                "license_status": "needs_review",
                "sample_status": "received",
            },
            {
                "source_id": "vendor-historical-slice",
                "venue": "polymarket_or_kalshi",
                "coverage_start": "2021-01-01",
                "coverage_end": "2025-12-31",
                "access_path": "licensed sample and written quote",
                "license_status": "sample_only",
                "sample_status": "not_requested",
            },
            {
                "source_id": "official-exchange-history",
                "venue": "kalshi",
                "coverage_start": "2021-01-01",
                "coverage_end": "2025-12-31",
                "access_path": "official public API or written research access",
                "license_status": "needs_review",
                "sample_status": "not_requested",
            },
        ],
        "required_fields": [
            "game_id", "play_id", "play_observed_at", "trade_price", "trade_timestamp"
        ],
        "immutable_row_key": [
            "venue", "market_id", "game_id", "play_id", "trade_timestamp", "source_ordinal"
        ],
        "timestamp_policy": (
            "UTC observed timestamps; immutable same-timestamp ordinal; prediction features use "
            "only records observed at or before the decision"
        ),
        "alignment_policy": (
            "last valid trade at/before the play decision; 60-second forward label with a frozen "
            "maximum lookup tolerance; no future record enters a feature"
        ),
        "minimum_target_coverage": 0.90,
        "regime_minimums": {
            "scoring_play": 300,
            "late_game": 300,
            "non_scoring_play": 300,
        },
        "learning_curve_units": [163, 300, 600],
        "opened_periods": ["2021", "2022", "2023", "2024", "2025"],
        "reserved_periods": ["future-2026-holdout"],
        "maximum_cost_usd": 200.0,
        "external_actions_authorized": False,
        "train_only_admission": True,
    }


def validate_plan(plan: dict) -> None:
    if set(plan) != PLAN_FIELDS:
        raise ValueError("data-strengthening plan must use the exact schema")
    if not plan["plan_id"] or not plan["parent_harness_version"] or not plan["evidence_refs"]:
        raise ValueError("plan id, parent and trajectory evidence are required")
    if plan["independent_unit"] != "game":
        raise ValueError("sports data strength must be measured in independent games")
    if type(plan["current_independent_units"]) is not int or plan["current_independent_units"] <= 0:
        raise ValueError("positive current game count required")
    if (
        type(plan["minimum_total_units"]) is not int
        or plan["minimum_total_units"] <= plan["current_independent_units"]
    ):
        raise ValueError("new data must increase independent games")
    if type(plan["minimum_seasons"]) is not int or plan["minimum_seasons"] < 2:
        raise ValueError("at least two seasons are required for a strengthened candidate")
    if not 0 < plan["minimum_target_coverage"] <= 1:
        raise ValueError("target coverage must be in (0,1]")
    if plan["maximum_cost_usd"] < 0:
        raise ValueError("negative data cost cap")
    if plan["external_actions_authorized"] is not False:
        raise ValueError("a plan cannot authorize download, purchase or messages")
    if plan["train_only_admission"] is not True:
        raise ValueError("new historical data must enter a Train candidate only")
    required = {"game_id", "play_id", "play_observed_at", "trade_price", "trade_timestamp"}
    if not required.issubset(set(plan["required_fields"])):
        raise ValueError("plan lacks fields needed for play/trade alignment")
    if not plan["immutable_row_key"] or not plan["timestamp_policy"] or not plan["alignment_policy"]:
        raise ValueError("row key, timestamp and alignment policies are required")
    if not plan["regime_minimums"] or any(
        type(value) is not int or value <= 0 for value in plan["regime_minimums"].values()
    ):
        raise ValueError("positive regime coverage requirements are required")
    units = plan["learning_curve_units"]
    if (
        not isinstance(units, list)
        or len(units) < 3
        or any(type(value) is not int or value <= 0 for value in units)
        or units != sorted(set(units))
        or units[-1] > plan["minimum_total_units"]
        or units[0] < plan["current_independent_units"]
    ):
        raise ValueError("learning curve needs increasing game-count checkpoints")
    if set(plan["opened_periods"]) & set(plan["reserved_periods"]):
        raise ValueError("opened and reserved periods must be disjoint")
    if not plan["candidate_sources"]:
        raise ValueError("at least one concrete source candidate is required")
    source_ids = set()
    for source in plan["candidate_sources"]:
        if set(source) != SOURCE_FIELDS:
            raise ValueError("source candidate must use the exact schema")
        if not all(source[key] for key in ("source_id", "venue", "coverage_start", "coverage_end", "access_path")):
            raise ValueError("source identity and coverage are required")
        if source["source_id"] in source_ids:
            raise ValueError("duplicate source id")
        source_ids.add(source["source_id"])
        if source["license_status"] not in {"public_confirmed", "needs_review", "sample_only"}:
            raise ValueError("unknown license status")
        if source["sample_status"] not in {"not_requested", "requested", "received", "validated"}:
            raise ValueError("unknown sample status")


def plan_receipt(plan: dict) -> dict:
    validate_plan(plan)
    result = {
        "schema": "sports_data_strengthening_plan_v1",
        "plan": plan,
        "opened_periods_remain_nonfresh": True,
        "download_authorized": False,
        "purchase_authorized": False,
        "admission_authorized": False,
        "selection_uses_predictive_dev_score": False,
    }
    result["plan_sha256"] = digest(result)
    return result


def admission_readiness(plan: dict, batch: dict) -> dict:
    receipt = plan_receipt(plan)
    if set(batch) != BATCH_FIELDS:
        raise ValueError("data batch must use the exact schema")
    if batch["plan_sha256"] != receipt["plan_sha256"]:
        raise ValueError("batch is not bound to this data plan")
    source_ids = {source["source_id"] for source in plan["candidate_sources"]}
    if batch["source_id"] not in source_ids:
        raise ValueError("batch source is not in the frozen plan")
    if not batch["source_object_hashes"] or not batch["derived_rows_hash"]:
        raise ValueError("raw and derived data hashes are required")
    for key in ("duplicate_rate", "missing_required_field_rate", "target_coverage", "alignment_success_rate"):
        if not 0 <= batch[key] <= 1:
            raise ValueError("data quality rates must be in [0,1]")
    if batch["cost_usd"] < 0:
        raise ValueError("negative data cost")
    checks = {
        "license": batch["license_allows_research_storage"] is True,
        "enough_games": batch["independent_units"] >= plan["minimum_total_units"],
        "enough_seasons": batch["season_count"] >= plan["minimum_seasons"],
        "nonempty_rows": batch["row_count"] > 0,
        "unique_row_key": batch["immutable_row_key_unique"] is True,
        "utc_timestamps": batch["timestamps_utc"] is True,
        "monotonic_within_game": batch["timestamps_monotonic_within_unit"] is True,
        "no_duplicates": batch["duplicate_rate"] == 0,
        "complete_required_fields": batch["missing_required_field_rate"] == 0,
        "target_coverage": batch["target_coverage"] >= plan["minimum_target_coverage"],
        "alignment_coverage": batch["alignment_success_rate"] >= plan["minimum_target_coverage"],
        "regime_coverage": all(
            batch["regime_counts"].get(name, 0) >= minimum
            for name, minimum in plan["regime_minimums"].items()
        ),
        "opened_scope_only": batch["opened_period_overlap_only"] is True,
        "reserved_scope_untouched": batch["reserved_period_overlap"] is False,
        "route_dev_untouched": batch["route_dev_opened"] is False,
        "final_untouched": batch["sealed_final_opened"] is False,
        "raw_objects_preserved": batch["raw_objects_preserved"] is True,
        "within_cost_cap": batch["cost_usd"] <= plan["maximum_cost_usd"],
    }
    return {
        "schema": "sports_data_admission_readiness_v1",
        "plan_sha256": receipt["plan_sha256"],
        "batch_id": batch["batch_id"],
        "checks": checks,
        "ready_for_versioned_train_candidate": all(checks.values()),
        "automatically_admitted": False,
        "route_dev_opened": False,
        "sealed_final_opened": False,
        "note": "Passing allows a versioned Train candidate; it does not prove prediction improvement.",
    }
