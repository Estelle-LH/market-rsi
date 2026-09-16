"""Frozen research workflow for market time-series experiments.

The controller may search literature and propose models, features, or training
transforms, but it cannot quietly redefine the forecasting problem after seeing
Dev.  Objective discovery happens first on public literature and opened Train;
the runner then freezes one objective before allocating unopened Dev.
"""
from __future__ import annotations

import copy

from market_rsi import digest
from objective_contract import discovery_policy, objective_catalog
from objective_discovery_harness import discovery_harness_contract
from time_series_split_policy import policy_contract as split_policy_contract
from training_population_policy import policy_contract as population_policy_contract


SCHEMA = "market_time_series_research_harness_v1"


def harness_contract() -> dict:
    body = {
        "schema": SCHEMA,
        "research_unit": "whole_market_game_with_time_ordered_observations",
        "objective_discovery_controller": discovery_harness_contract(),
        "phase_order": [
            "inspect_public_literature_and_open_train",
            "audit_candidate_objectives_on_open_train",
            "freeze_one_objective_and_baseline",
            "freeze_unopened_dev_schedule",
            "research_models_features_and_training_transforms_on_train_cv",
            "freeze_one_round_submission",
            "score_once_on_current_dev",
            "promote_consumed_dev_to_next_round_train",
        ],
        "objective_research": {
            "catalog": objective_catalog(),
            "candidate_families": [
                {
                    "family": "point_future_price",
                    "purpose": "unsmoothed_reference",
                    "main_risk": "single_quote_noise_and_flat_labels",
                },
                {
                    "family": "uniform_future_window_mean",
                    "purpose": "low_assumption_label_smoothing",
                    "main_risk": "blurs_short_real_information_jumps",
                },
                {
                    "family": "forward_weighted_future_window_mean",
                    "purpose": "weight_later_future_quotes_more",
                    "main_risk": "changes_effective_horizon_and_adds_a_tunable_parameter",
                },
                {
                    "family": "robust_future_window_location",
                    "purpose": "limit_isolated_quote_outliers",
                    "main_risk": "can_remove_real_short_jumps",
                },
                {
                    "family": "future_trade_vwap",
                    "purpose": "measure_confirmed_executed_prices",
                    "main_risk": "sparse_endogenous_trades_bid_ask_bounce_and_volume_concentration",
                    "required_status": "only_after_trade_capture_provenance_and_coverage_pass",
                },
                {
                    "family": "latent_state_filter",
                    "purpose": "estimate_an_unobserved_efficient_price_or_state",
                    "main_risk": "stronger_model_assumptions_and_train_fitted_parameters",
                    "default_status": "research_only_not_first_formal_default",
                },
            ],
            "selection_inputs": ["public_literature", "opened_train_only"],
            "required_diagnostics": discovery_policy()[
                "required_train_only_diagnostics"
            ],
            "runner_must_freeze": [
                "label_quantity",
                "horizon",
                "future_window",
                "smoothing_or_robustness_rule",
                "deadband_if_any",
                "primary_baseline",
                "raw_metric",
                "scale_free_comparison_metric",
            ],
            "controller_may_not_select_objective_using_dev": True,
            "objective_change_requires_fresh_experiment_and_unopened_dev": True,
        },
        "data_contract": {
            "decision_rows": "may_be_sparse_but_fixed_before_labels",
            "label_source": "dense_raw_quotes_covering_the_full_future_window",
            "trade_label_source": (
                "separate_confirmed_trade_stream_with_price_size_side_market_and_time"
            ),
            "minimum_future_observations": "defined_by_the_frozen_objective",
            "feature_availability": "known_by_decision_time_only",
            "label_availability": "not_before_the_end_of_the_frozen_future_window",
            "group_boundary": "whole_game_or_market_never_split_across_train_and_dev",
            "time_order": "past_to_future_only",
            "random_row_split": False,
            "training_population_policy": population_policy_contract(),
        },
        "model_research": {
            "controller_can_change": [
                "feature_set",
                "model_family",
                "loss_or_training_transform",
                "regularization",
                "train_only_hyperparameters",
            ],
            "controller_cannot_change": [
                "frozen_objective",
                "frozen_baseline",
                "split_or_score_policy",
                "current_dev_or_future_test",
            ],
            "reusable_feedback": "blocked_or_expanding_time_ordered_train_cv_only",
            "minimum_reporting": [
                "raw_error",
                "skill_relative_to_frozen_baseline",
                "error_by_independent_day_and_game",
                "coverage",
                "prediction_dispersion",
                "trade_coverage_staleness_and_volume_concentration_if_applicable",
                "failure_and_runtime_counts",
            ],
        },
        "evaluation": {
            "split_policy": split_policy_contract(),
            "dev_openings_per_round": 1,
            "dev_score_enters_controller_context": "next_round_archive_only",
            "consumed_dev_becomes": "next_round_train_and_never_dev_again",
            "future_test": "untouched_until_all_final_submissions_are_frozen",
            "profit_claim_requires_separate_execution_simulation": True,
        },
        "archive": {
            "required": [
                "literature_queries_and_sources",
                "objective_candidates_and_train_diagnostics",
                "frozen_objective_hash",
                "data_and_split_hashes",
                "candidate_code_features_and_hyperparameters",
                "train_cv_and_one_time_dev_results",
                "failures_runtime_and_cost",
            ],
            "is_controller_memory": True,
            "prescriptive_learn_mode": False,
        },
    }
    return {**body, "contract_sha256": digest(body)}


def validate_harness_contract(value: dict) -> dict:
    expected = harness_contract()
    if value != expected:
        raise ValueError("time-series research harness changed")
    return {
        "valid": True,
        "schema": SCHEMA,
        "contract_sha256": expected["contract_sha256"],
    }


def copy_harness_contract() -> dict:
    return copy.deepcopy(harness_contract())
