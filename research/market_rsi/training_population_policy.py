"""Frozen rules for learning from sparse, autocorrelated market rows.

Rows are not treated as independent evidence.  Train may use target-aware
curricula because its labels are already open, but the original population is
retained and every Dev/Test membership decision stays target-blind.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import math
from statistics import median

from market_rsi import digest


SCHEMA = "market_training_population_policy_v1"


def policy_contract() -> dict:
    body = {
        "schema": SCHEMA,
        "independent_units": ["utc_day", "whole_game", "market"],
        "row_count_is_not_independent_sample_size": True,
        "source_population": "retain_every_causal_eligible_row",
        "train_options": [
            {
                "method": "uniform_full_population",
                "purpose": "unbiased_reference",
            },
            {
                "method": "causal_activity_sampling",
                "allowed_inputs": "features_available_at_or_before_decision_only",
                "required": ["frozen_rule", "inclusion_probability", "full_population_score"],
            },
            {
                "method": "train_label_stratified_sampling_or_weighting",
                "allowed_split": "opened_train_only",
                "required": ["frozen_bins", "weight_cap", "full_population_score"],
            },
            {
                "method": "activity_head_plus_conditional_move_head",
                "purpose": "learn_when_to_stay_at_persistence_and_how_to_move_when_active",
            },
        ],
        "evaluation_population": {
            "membership": "all_eligible_whole_games_on_predeclared_time_blocks",
            "future_target_based_filtering": False,
            "future_target_magnitude_weighting": False,
            "primary": "unweighted_full_population_equal_game_score",
            "diagnostics": ["flat_rows", "moving_rows", "move_size_bands"],
        },
        "data_sufficiency": {
            "must_report": [
                "rows", "utc_days", "whole_games", "markets",
                "exactly_unchanged_fraction", "move_size_bands_probability_bps",
                "rows_per_game", "persistence_rmse_probability_bps",
            ],
            "enough_to_run_is_not_enough_to_claim": True,
            "claim_requires": [
                "time_ordered_learning_curve",
                "uncertainty_clustered_by_whole_game_and_day",
                "fresh_unopened_evaluation",
            ],
        },
    }
    return {**body, "policy_sha256": digest(body)}


def _date(milliseconds: int) -> str:
    return datetime.fromtimestamp(milliseconds / 1000, timezone.utc).date().isoformat()


def audit_open_train(rows: list[dict]) -> dict:
    """Describe real learning volume without pretending rows are IID samples."""
    if not isinstance(rows, list) or not rows:
        raise ValueError("nonempty opened Train rows required")
    deltas: list[float] = []
    by_game: dict[str, int] = defaultdict(int)
    days: set[str] = set()
    markets: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Train row must be an object")
        try:
            game_id = row["game_id"]
            market_id = row["market_id"]
            decision_ms = row["decision_ms"]
            midpoint = row["features"]["mid"]
            target = row["target"]
        except (KeyError, TypeError) as error:
            raise ValueError("Train row lacks population-audit fields") from error
        if (not isinstance(game_id, str) or not game_id
                or not isinstance(market_id, str) or not market_id
                or type(decision_ms) is not int
                or isinstance(midpoint, bool) or not isinstance(midpoint, (int, float))
                or isinstance(target, bool) or not isinstance(target, (int, float))
                or not math.isfinite(midpoint) or not math.isfinite(target)):
            raise ValueError("invalid Train population-audit value")
        delta = (float(target) - float(midpoint)) * 10_000
        deltas.append(delta)
        by_game[game_id] += 1
        markets.add(market_id)
        days.add(_date(decision_ms))

    absolute = [abs(value) for value in deltas]
    moving = sum(value > 1e-8 for value in absolute)
    counts = {
        f"at_least_{threshold:g}_bps": sum(value >= threshold for value in absolute)
        for threshold in (1.0, 5.0, 10.0, 25.0)
    }
    game_sizes = list(by_game.values())
    body = {
        "schema": "market_open_train_population_audit_v1",
        "rows": len(rows),
        "utc_days": len(days),
        "whole_games": len(by_game),
        "markets": len(markets),
        "rows_are_independent_samples": False,
        "rows_per_game": {
            "minimum": min(game_sizes),
            "median": median(game_sizes),
            "maximum": max(game_sizes),
        },
        "target_activity": {
            "exactly_unchanged_rows": len(rows) - moving,
            "moving_rows": moving,
            "moving_fraction": moving / len(rows),
            "move_size_bands_probability_bps": counts,
            "median_absolute_move_probability_bps": median(absolute),
            "persistence_rmse_probability_bps": math.sqrt(
                math.fsum(value * value for value in deltas) / len(deltas)
            ),
        },
        "sufficiency": {
            "enough_to_execute_pipeline": len(days) >= 4 and len(by_game) >= 8,
            "enough_for_performance_claim": None,
            "why_unknown": (
                "Requires a time-ordered learning curve, game/day-clustered uncertainty, "
                "and a fresh unopened evaluation population."
            ),
        },
        "permitted_train_rebalancing": [
            "causal_activity_sampling",
            "opened_train_label_stratification_with_capped_weights",
            "activity_plus_conditional_move_model",
        ],
        "evaluation_target_filtering_permitted": False,
        "dev_labels_used": False,
        "future_test_used": False,
        "policy_sha256": policy_contract()["policy_sha256"],
    }
    return {**body, "audit_sha256": digest(body)}
