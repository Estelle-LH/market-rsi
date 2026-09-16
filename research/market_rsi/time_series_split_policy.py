"""Frozen time-series split policy for market-forecast research.

The controller may choose a forecasting method, features derived from open
history, and how to train on that history.  The runner owns time boundaries.
It never shuffles future observations into an earlier fit set and never picks
a validation boundary after looking at labels or candidate scores.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from market_rsi import digest


DAY_MS = 86_400_000
FORECAST_HORIZON_MS = 60_000
MAXIMUM_LABEL_LATENESS_MS = 5_000


@dataclass(frozen=True)
class TimeSeriesSplitPolicy:
    schema: str = "market_time_series_split_policy_v1"
    order: str = "past_to_future_only"
    inner_method: str = "expanding_history_single_origin_blocked_holdout"
    formal_train_cv_holdout_utc_days: int = 3
    formal_minimum_train_utc_days: int = 4
    minimum_fit_games: int = 1
    minimum_cv_games: int = 1
    group_key: str = "game_id"
    cross_split_grouping: str = "forbidden"
    purge_rule: str = "fit_labels_strictly_before_first_cv_feature"
    forecast_horizon_seconds: int = 60
    maximum_label_lateness_seconds: int = 5
    embargo_seconds: int = 0
    boundary_selection: str = "fixed_before_candidate_scores"
    boundary_may_use_targets: bool = False
    random_shuffle: bool = False
    outer_dev_method: str = "next_unopened_chronological_whole_game_block"
    outer_dev_may_use_targets_for_selection: bool = False
    outer_dev_selection_receipt_required: bool = True
    outer_dev_minimum_utc_days: int = 3
    outer_dev_minimum_games: int = 8
    outer_dev_openings_per_round: int = 1
    consumed_dev_transition: str = "atomically_promote_to_next_round_train"
    final_promotion_minimum_untouched_utc_days: int = 20


POLICY = TimeSeriesSplitPolicy()


def policy_contract() -> dict:
    body = asdict(POLICY)
    return {**body, "policy_sha256": digest(body)}


def _delay_bounds(value: tuple[int, int] | None) -> tuple[int, int]:
    bounds = ((FORECAST_HORIZON_MS,
               FORECAST_HORIZON_MS + MAXIMUM_LABEL_LATENESS_MS)
              if value is None else value)
    if (not isinstance(bounds, tuple) or len(bounds) != 2
            or any(type(item) is not int for item in bounds)
            or bounds[0] <= 0 or bounds[1] < bounds[0]):
        raise ValueError("valid objective label-delay bounds required")
    return bounds


def _validate_times(
    rows: list[dict], label_delay_bounds_ms: tuple[int, int] | None = None
) -> tuple[int, int]:
    if not isinstance(rows, list) or not rows:
        raise ValueError("nonempty time-series rows required")
    minimum_delay_ms, maximum_delay_ms = _delay_bounds(label_delay_bounds_ms)
    previous = -1
    seen_rows: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("time-series row must be an object")
        for key in ("row_id", "game_id", "decision_ms", "feature_available_ms",
                    "label_available_ms"):
            if key not in row:
                raise ValueError("time-series row is missing split fields")
        if row["row_id"] in seen_rows:
            raise ValueError("duplicate time-series row identity")
        seen_rows.add(row["row_id"])
        if (type(row["decision_ms"]) is not int
                or type(row["feature_available_ms"]) is not int
                or type(row["label_available_ms"]) is not int):
            raise ValueError("integer time-series timestamps required")
        if row["feature_available_ms"] > row["decision_ms"]:
            raise ValueError("future feature in time-series split")
        label_delay = row["label_available_ms"] - row["decision_ms"]
        if not (minimum_delay_ms <= label_delay <= maximum_delay_ms):
            raise ValueError("time-series label availability exceeds frozen window")
        if row["decision_ms"] < previous:
            raise ValueError("nonchronological time-series input")
        previous = row["decision_ms"]
    return minimum_delay_ms, maximum_delay_ms


def train_cv_split(
    rows: list[dict], *, evidence_class: str = "diagnostic",
    label_delay_bounds_ms: tuple[int, int] | None = None,
) -> tuple[list[dict], list[dict], dict]:
    """Create the runner-owned inner split and an auditable receipt.

    A formal run uses every eligible date before a fixed three-day suffix as
    expanding fit history and the entire suffix as one blocked holdout.  This
    is one forecasting origin inside a round, not repeated rolling-origin CV.
    Across rounds, consumed Dev data enters the expanding history and the next
    unopened later block becomes Dev (prequential/rolling-origin evaluation).
    """
    minimum_delay_ms, maximum_delay_ms = _validate_times(
        rows, label_delay_bounds_ms
    )
    dates = sorted({row["decision_ms"] // DAY_MS for row in rows})
    formal = evidence_class in {
        "formal_learning", "formal_prospective_learning", "prospective_diagnostic"
    }
    minimum_dates = (POLICY.formal_minimum_train_utc_days if formal else 2)
    if len(dates) < minimum_dates:
        raise ValueError(
            f"{evidence_class} Train-CV requires at least {minimum_dates} UTC dates"
        )
    holdout_days = (POLICY.formal_train_cv_holdout_utc_days if formal
                    else min(POLICY.formal_train_cv_holdout_utc_days, len(dates) - 1))
    boundary = dates[-holdout_days] * DAY_MS
    games: dict[str, list[dict]] = {}
    for row in rows:
        games.setdefault(row["game_id"], []).append(row)

    fit_games = {
        game_id for game_id, game_rows in games.items()
        if max(row["label_available_ms"] for row in game_rows) < boundary
    }
    cv_games = {
        game_id for game_id, game_rows in games.items()
        if min(row["feature_available_ms"] for row in game_rows) >= boundary
    }
    fit = [row for row in rows if row["game_id"] in fit_games]
    cv = [row for row in rows if row["game_id"] in cv_games]
    if (len(fit_games) < POLICY.minimum_fit_games
            or len(cv_games) < POLICY.minimum_cv_games):
        raise ValueError("fixed multi-day time-series Train-CV has no usable whole-game boundary")
    if fit_games & cv_games:
        raise ValueError("Train-CV game isolation failed")
    latest_fit_label = max(row["label_available_ms"] for row in fit)
    first_cv_feature = min(row["feature_available_ms"] for row in cv)
    if latest_fit_label >= first_cv_feature:
        raise ValueError("Train-CV label purge failed")

    all_games = set(games)
    used_games = fit_games | cv_games
    audit = {
        "schema": "market_time_series_split_audit_v1",
        "split_policy": POLICY.schema,
        "policy_sha256": policy_contract()["policy_sha256"],
        "evidence_class": evidence_class,
        "inner_method": POLICY.inner_method,
        "forecast_origins": 1,
        "configured_holdout_days": POLICY.formal_train_cv_holdout_utc_days,
        "applied_holdout_days": holdout_days,
        "boundary_ms": boundary,
        "fit_utc_dates": sorted({row["decision_ms"] // DAY_MS for row in fit}),
        "cv_utc_dates": sorted({row["decision_ms"] // DAY_MS for row in cv}),
        "fit_rows": len(fit),
        "cv_rows": len(cv),
        "fit_games": len(fit_games),
        "cv_games": len(cv_games),
        "omitted_boundary_games": len(all_games - used_games),
        "purged_gap_ms": first_cv_feature - latest_fit_label,
        "boundary_selected_using_targets": False,
        "boundary_selected_using_candidate_scores": False,
        "random_shuffle": False,
        "label_delay_bounds_ms": [minimum_delay_ms, maximum_delay_ms],
        "label_delay_source": (
            "legacy_60s_default" if label_delay_bounds_ms is None
            else "frozen_objective_contract"
        ),
    }
    return fit, cv, audit


def validate_outer_dev(
    train_rows: list[dict], dev_rows: list[dict], *, evidence_class: str,
    label_delay_bounds_ms: tuple[int, int] | None = None,
) -> dict:
    """Verify that the sealed Dev block is later and group-disjoint.

    This verifies the resulting time boundary.  A prospective materializer must
    separately bind a receipt proving it selected this block before revealing
    targets; target-blind selection cannot be reconstructed after the fact.
    """
    minimum_delay_ms, maximum_delay_ms = _validate_times(
        train_rows, label_delay_bounds_ms
    )
    if _validate_times(dev_rows, label_delay_bounds_ms) != (
            minimum_delay_ms, maximum_delay_ms):
        raise ValueError("Train and Dev use different objective label windows")
    train_games = {row["game_id"] for row in train_rows}
    dev_games = {row["game_id"] for row in dev_rows}
    dev_dates = {row["decision_ms"] // DAY_MS for row in dev_rows}
    if train_games & dev_games:
        raise ValueError("outer Dev shares a game with Train")
    latest_train_label = max(row["label_available_ms"] for row in train_rows)
    first_dev_feature = min(row["feature_available_ms"] for row in dev_rows)
    if (latest_train_label >= first_dev_feature
            or latest_train_label // DAY_MS >= first_dev_feature // DAY_MS):
        raise ValueError("outer Dev is not on a strictly later UTC date")
    # Legacy fixed-H0 studies used one-day Dev blocks.  The stricter population
    # gate applies only to the new prospectively scheduled design, so historical
    # receipts remain auditable without being mislabeled as compliant.
    if evidence_class in {"formal_prospective_learning", "prospective_diagnostic"}:
        if len(dev_dates) < POLICY.outer_dev_minimum_utc_days:
            raise ValueError(
                "formal outer Dev has too few distinct UTC dates"
            )
        if len(dev_games) < POLICY.outer_dev_minimum_games:
            raise ValueError("formal outer Dev has too few whole games")
    return {
        "schema": "market_time_series_split_audit_v1",
        "split_policy": POLICY.schema,
        "policy_sha256": policy_contract()["policy_sha256"],
        "evidence_class": evidence_class,
        "outer_method": POLICY.outer_dev_method,
        "train_rows": len(train_rows),
        "dev_rows": len(dev_rows),
        "train_games": len(train_games),
        "dev_games": len(dev_games),
        "train_utc_dates": sorted({row["decision_ms"] // DAY_MS for row in train_rows}),
        "dev_utc_dates": sorted(dev_dates),
        "purged_gap_ms": first_dev_feature - latest_train_label,
        "boundary_selected_using_targets": False,
        "dev_openings_allowed": POLICY.outer_dev_openings_per_round,
        "random_shuffle": False,
        "label_delay_bounds_ms": [minimum_delay_ms, maximum_delay_ms],
        "label_delay_source": (
            "legacy_60s_default" if label_delay_bounds_ms is None
            else "frozen_objective_contract"
        ),
    }
