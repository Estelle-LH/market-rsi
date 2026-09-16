"""Controller contract for choosing how to obtain adequate real history."""
from __future__ import annotations

from market_rsi import digest


SCHEMA = "market_data_discovery_harness_v3"


def data_discovery_harness_contract() -> dict:
    body = {
        "schema": SCHEMA,
        "controller_role": "research_and_freeze_the_next_data_acquisition_plan",
        "runs_before": "objective_selection_train_dev_split_and_model_search",
        "research_order": [
            "audit_current_real_history",
            "research_real_historical_sources",
            "resolve_terms_and_reuse_before_any_source_data_request",
            "compare_at_least_two_acquisition_plans",
            "freeze_one_bounded_sample_canary",
            "only_after_canary_consider_full_ingest",
        ],
        "controller_can_decide": [
            "which_real_sources_to_canary",
            "whether_to_combine_compatible_real_sources",
            "required_time_span_markets_games_and_cadence",
            "which_raw_streams_are_required",
            "storage_and_download_caps",
            "source_rejection_conditions",
        ],
        "hard_rules": {
            "real_history_is_primary": True,
            "simulator_is_primary_train_source": False,
            "simulator_is_dev_or_test_source": False,
            "simulator_requires_real_holdout_validation": True,
            "full_download_before_sample_canary": False,
            "source_data_request_before_terms_and_reuse_gate": False,
            "objective_choice_before_data_clock_and_streams_are_known": False,
            "dev_creation_before_data_and_objective_freeze": False,
            "rows_are_not_independent_samples": True,
            "claim_units": ["utc_day", "whole_market_or_game", "regime"],
        },
        "source_canary_must_verify": [
            "access_and_terms_status", "exact_version_or_endpoint", "schema",
            "event_and_ingest_timestamp_semantics", "duplicates", "gaps",
            "market_identity_and_resolution_linkage", "causal_replayability",
            "sample_row_day_market_counts", "compressed_and_uncompressed_bytes",
        ],
        "acceptance_scope": {
            "terms_gate": "must_pass_before_requesting_any_source_market_data",
            "canary": "verifies_access_schema_clocks_linkage_and_bounded_replay_only",
            "full_ingest": "verifies_required_days_markets_streams_and_storage_after_a_separate_authorization",
            "canary_cannot_claim_full_dataset_sufficiency": True,
        },
        "tools": [
            "inspect_current_data_audit", "inspect_source_canary_evidence",
            "list_historical_data_sources",
            "inspect_historical_data_source", "search_historical_data_sources",
            "search_public_literature", "propose_data_plan",
            "run_data_plan_feasibility_audit", "compare_data_plans",
            "submit_data_decision",
        ],
        "output": {
            "one_frozen_plan": True,
            "first_valid_controller_decision_only": True,
            "runner_validates_but_does_not_pick_source": True,
            "next_action_is_bounded_canary_not_full_download": True,
            "archive_every_query_plan_failure_and_decision": True,
        },
        "external_egress": {
            "aggregate_only": True,
            "forbidden_keys": [
                "row_id", "decision_ms", "decision_ns", "event_slug", "game_id",
                "market_id", "features", "target", "source_path", "input_source",
            ],
            "maximum_tool_result_bytes": 262144,
        },
    }
    return {**body, "contract_sha256": digest(body)}


def validate_data_discovery_harness(value: dict) -> dict:
    expected = data_discovery_harness_contract()
    if value != expected:
        raise ValueError("data discovery harness changed")
    return {"valid": True, "schema": SCHEMA,
            "contract_sha256": expected["contract_sha256"]}
