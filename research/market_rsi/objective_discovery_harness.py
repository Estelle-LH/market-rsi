"""Controller-facing contract for autonomous time-series objective discovery."""
from __future__ import annotations

import copy

from market_rsi import digest


SCHEMA = "market_objective_discovery_harness_v1"


def discovery_harness_contract() -> dict:
    body = {
        "schema": SCHEMA,
        "controller_role": "discover_and_justify_the_forecasting_problem",
        "runs_before": "dev_schedule_creation_and_model_improvement",
        "inputs": [
            "public_literature",
            "opened_train_raw_source_inventory",
            "opened_train_features_and_labels",
            "runner_owned_objective_diagnostics",
            "non_exhaustive_objective_and_operator_catalog",
        ],
        "automatic_first_pass": [
            "inventory_available_quote_trade_event_and_resolution_streams",
            "measure_raw_and_materialized_cadence_by_market_day_and_game",
            "measure_target_coverage_flatness_scale_tails_and_staleness",
            "measure_trivial_baseline_strength_by_day_game_and_regime",
            "check_label_availability_and_feature_leakage",
            "compare_nearby_horizons_windows_and_aggregations_for_stability",
            "search_public_literature_for_the_observed_failure_modes",
        ],
        "tools": [
            "inspect_open_train_source_inventory",
            "run_automatic_time_series_data_diagnostics",
            "profile_open_train_cadence",
            "profile_open_train_target",
            "search_public_literature",
            "list_objective_families",
            "propose_objective_definition",
            "run_open_train_objective_audit",
            "compare_open_train_objective_stability",
            "submit_objective_decision",
        ],
        "proposal_space": {
            "catalog_is_exhaustive": False,
            "controller_may_propose_new_target": True,
            "controller_may_propose_new_required_data_stream": True,
            "controller_may_propose_new_deterministic_train_only_diagnostic": True,
            "allowed_label_sources": [
                "quote_book",
                "confirmed_trade_stream",
                "event_resolution",
            ],
            "allowed_aggregation_families": [
                "point",
                "uniform_window_mean",
                "forward_weighted_window_mean",
                "robust_window_location",
                "trade_vwap",
                "deadband_direction",
                "latent_state_estimate_fitted_on_train",
            ],
            "proposal_must_declare": [
                "research_question",
                "label_formula",
                "source_and_availability_clock",
                "horizon_and_window",
                "minimum_coverage",
                "baseline",
                "raw_and_scale_free_scores",
                "expected_failure_condition",
                "required_materializer_and_validation_tests",
            ],
        },
        "selection_rule": {
            "automatic_lowest_train_error_selection": False,
            "required_evidence": [
                "public_research_support",
                "adequate_train_coverage",
                "nontrivial_but_learnable_baseline_gap",
                "stability_across_days_games_and_nearby_definitions",
                "causal_availability",
                "executable_materializer_with_tests",
            ],
            "first_valid_controller_decision_only": True,
            "no_human_target_choice_after_controller_dispatch": True,
            "runner_validates_constraints_but_does_not_choose_scientific_content": True,
        },
        "external_egress": {
            "destination": "tinker_hosted_glm_5_3",
            "allowed": [
                "aggregate_train_diagnostics",
                "public_literature_catalog",
                "objective_catalog",
                "controller_authored_proposals",
                "runner_audit_summaries",
            ],
            "forbidden_keys": [
                "row_id", "decision_ms", "decision_ns", "event_slug",
                "market_id", "game_id", "features", "target_candidates",
                "input_source", "source_path",
            ],
            "maximum_tool_result_bytes": 262144,
            "raw_rows_released": False,
            "market_identity_released": False,
            "timestamps_released": False,
            "local_paths_released": False,
            "every_released_result_hash_chain_logged": True,
        },
        "forbidden": [
            "create_or_open_dev_before_objective_freeze",
            "read_current_or_future_dev_labels",
            "read_future_test",
            "use_model_candidate_dev_scores_to_choose_target",
            "fill_missing_trades_with_stale_last_trade",
            "silently_change_effective_horizon",
            "discard_failed_or_unselected_objective_attempts",
        ],
        "output": {
            "one_frozen_objective_contract": True,
            "one_hash_bound_materializer": True,
            "one_hash_bound_train_audit": True,
            "archive_all_queries_proposals_runs_failures_and_cost": True,
            "objective_change_after_freeze": (
                "new_experiment_id_and_fresh_unopened_dev_required"
            ),
        },
    }
    return {**body, "contract_sha256": digest(body)}


def validate_discovery_harness(value: dict) -> dict:
    expected = discovery_harness_contract()
    if value != expected:
        raise ValueError("objective discovery harness changed")
    return {
        "valid": True,
        "schema": SCHEMA,
        "contract_sha256": expected["contract_sha256"],
    }


def copy_discovery_harness() -> dict:
    return copy.deepcopy(discovery_harness_contract())
