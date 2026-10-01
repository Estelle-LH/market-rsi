"""Trusted proper scoring for paired settlement-probability forecasts.

The primary comparison is candidate minus the decision-time market baseline
on identical complete rows, aggregated with equal weight per underlying event.
Negative loss deltas are better.  This module performs arithmetic and
structural leakage checks only; it makes no data-admission, promotion or PnL
claim and never imports candidate code.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import statistics
from dataclasses import dataclass
from typing import Callable, Iterable

from .probability_contract import (
    DEFAULT_PROBABILITY_POLICY,
    ProbabilityPolicy,
    SettlementProbabilityRow,
    validate_prediction_records,
    validate_probability,
    validate_probability_rows,
    validate_raw_signal_records,
)


@dataclass(frozen=True)
class ProperScoreSpec:
    probability_epsilon: float = DEFAULT_PROBABILITY_POLICY.epsilon
    reliability_bins: int = 10
    bootstrap_seed: int = 23
    bootstrap_replicates: int = 1000
    date_block_days: int = 1

    def __post_init__(self) -> None:
        ProbabilityPolicy(self.probability_epsilon)
        if type(self.reliability_bins) is not int or not 2 <= self.reliability_bins <= 100:
            raise ValueError("reliability_bins must be an integer from 2 through 100")
        if type(self.bootstrap_seed) is not int or self.bootstrap_seed < 0:
            raise ValueError("bootstrap_seed must be a nonnegative integer")
        if (type(self.bootstrap_replicates) is not int
                or not 100 <= self.bootstrap_replicates <= 10000):
            raise ValueError("bootstrap_replicates must be from 100 through 10000")
        if type(self.date_block_days) is not int or self.date_block_days <= 0:
            raise ValueError("date_block_days must be a positive integer")

    @property
    def policy(self) -> ProbabilityPolicy:
        return ProbabilityPolicy(self.probability_epsilon)


def brier_loss(probability: float, outcome: int) -> float:
    return (probability - outcome) ** 2


def bounded_log_loss(
    probability: object,
    outcome: int,
    *,
    policy: ProbabilityPolicy = DEFAULT_PROBABILITY_POLICY,
) -> float:
    probability = validate_probability(probability, policy, "probability")
    if type(outcome) is not int or outcome not in (0, 1):
        raise ValueError("outcome must be the binary integer zero or one")
    # log1p retains accuracy near one. No clipping occurs: the contract has
    # already rejected values outside the declared epsilon bounds.
    return -math.log(probability) if outcome else -math.log1p(-probability)


def _mean(values: Iterable[float]) -> float:
    values = list(values)
    if not values:
        raise ValueError("nonempty values required")
    return math.fsum(values) / len(values)


def _fingerprint(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        rank = (start + 1 + end) / 2
        for index in order[start:end]:
            ranks[index] = rank
        start = end
    return ranks


def _correlation(left: list[float], right: list[float]) -> float | None:
    if not left or len(left) != len(right):
        raise ValueError("nonempty paired vectors required")
    left_mean, right_mean = _mean(left), _mean(right)
    left_centered = [value - left_mean for value in left]
    right_centered = [value - right_mean for value in right]
    left_ss = math.fsum(value * value for value in left_centered)
    right_ss = math.fsum(value * value for value in right_centered)
    if left_ss == 0 or right_ss == 0:
        return None
    result = math.fsum(a * b for a, b in zip(left_centered, right_centered, strict=True))
    return max(-1.0, min(1.0, result / math.sqrt(left_ss * right_ss)))


def _residualize(values: list[float], control: list[float]) -> list[float]:
    mean_value, mean_control = _mean(values), _mean(control)
    centered_control = [value - mean_control for value in control]
    denominator = math.fsum(value * value for value in centered_control)
    slope = (math.fsum((value - mean_value) * z for value, z in
                       zip(values, centered_control, strict=True)) / denominator
             if denominator else 0.0)
    return [value - (mean_value + slope * (z - mean_control))
            for value, z in zip(values, control, strict=True)]


def _calibration(probabilities: list[float], outcomes: list[int]) -> dict:
    mean_probability, mean_outcome = _mean(probabilities), _mean(outcomes)
    variance = math.fsum((value - mean_probability) ** 2 for value in probabilities)
    slope = (math.fsum((probability - mean_probability) * (outcome - mean_outcome)
                       for probability, outcome in zip(probabilities, outcomes, strict=True))
             / variance if variance else None)
    return {
        "method": "ols_outcome_on_probability",
        "slope": slope,
        "intercept": mean_outcome - slope * mean_probability if slope is not None else None,
        "mean_probability": mean_probability,
        "outcome_rate": mean_outcome,
    }


def _reliability(
    probabilities: list[float], outcomes: list[int], bin_count: int
) -> dict:
    grouped: list[list[tuple[float, int]]] = [[] for _ in range(bin_count)]
    for probability, outcome in zip(probabilities, outcomes, strict=True):
        grouped[min(bin_count - 1, int(probability * bin_count))].append(
            (probability, outcome)
        )
    bins = []
    total_reliability = 0.0
    for index, values in enumerate(grouped):
        count = len(values)
        mean_probability = _mean(value[0] for value in values) if values else None
        outcome_rate = _mean(value[1] for value in values) if values else None
        component = ((count / len(probabilities)) * (mean_probability - outcome_rate) ** 2
                     if values else 0.0)
        total_reliability += component
        bins.append({
            "bin": index,
            "lower_inclusive": index / bin_count,
            "upper_inclusive": (index + 1) / bin_count if index == bin_count - 1 else None,
            "upper_exclusive": (index + 1) / bin_count if index < bin_count - 1 else None,
            "rows": count,
            "row_fraction": count / len(probabilities),
            "mean_probability": mean_probability,
            "outcome_rate": outcome_rate,
            "brier": (_mean((probability - outcome) ** 2
                            for probability, outcome in values) if values else None),
            "reliability_component": component,
        })
    return {
        "method": "fixed_equal_width_probability_bins",
        "bin_count": bin_count,
        "reliability": total_reliability,
        "bins": bins,
    }


def _losses(
    rows: tuple[SettlementProbabilityRow, ...], probabilities: dict, loss: Callable
) -> dict[tuple[str, str, int], float]:
    return {row.key: loss(probabilities[row.key], row.outcome) for row in rows}


def _group_records(
    rows: tuple[SettlementProbabilityRow, ...],
    candidate_brier: dict,
    market_brier: dict,
    candidate_log: dict,
    market_log: dict,
    group: Callable[[SettlementProbabilityRow], str],
    id_name: str,
) -> list[dict]:
    grouped: dict[str, list[SettlementProbabilityRow]] = {}
    for row in rows:
        grouped.setdefault(group(row), []).append(row)
    records = []
    for group_id in sorted(grouped):
        members = grouped[group_id]
        candidate_brier_mean = _mean(candidate_brier[row.key] for row in members)
        market_brier_mean = _mean(market_brier[row.key] for row in members)
        candidate_log_mean = _mean(candidate_log[row.key] for row in members)
        market_log_mean = _mean(market_log[row.key] for row in members)
        records.append({
            id_name: group_id,
            "rows": len(members),
            "events": len({row.event_id for row in members}),
            "candidate_brier": candidate_brier_mean,
            "market_brier": market_brier_mean,
            "candidate_minus_market_brier": candidate_brier_mean - market_brier_mean,
            "candidate_log_loss": candidate_log_mean,
            "market_log_loss": market_log_mean,
            "candidate_minus_market_log_loss": candidate_log_mean - market_log_mean,
        })
    return records


def _bootstrap_interval(
    values: list[float], *, replicates: int, seed: int
) -> list[float]:
    rng = random.Random(seed)
    draws = [_mean(rng.choices(values, k=len(values))) for _ in range(replicates)]
    return [_quantile(draws, 0.025), _quantile(draws, 0.975)]


def _circular_block_interval(
    values: list[float], *, block: int, replicates: int, seed: int
) -> list[float]:
    rng = random.Random(seed)
    draws = []
    for _ in range(replicates):
        sampled = []
        while len(sampled) < len(values):
            start = rng.randrange(len(values))
            sampled.extend(values[(start + offset) % len(values)] for offset in range(block))
        draws.append(_mean(sampled[:len(values)]))
    return [_quantile(draws, 0.025), _quantile(draws, 0.975)]


def _paired_summary(records: list[dict], *, key: str, interval: list[float]) -> dict:
    deltas = [record[key] for record in records]
    return {
        "units": len(records),
        "mean_delta": _mean(deltas),
        "median_delta": statistics.median(deltas),
        "candidate_better_fraction": _mean(delta < 0 for delta in deltas),
        "candidate_tied_fraction": _mean(delta == 0 for delta in deltas),
        "interval_95pct": interval,
        "delta_convention": "candidate_minus_market; negative loss is better",
    }


def _shares(counts: list[int]) -> dict:
    ordered = sorted(counts, reverse=True)
    total = sum(ordered)
    return {
        "top_1_row_share": ordered[0] / total,
        "top_5_row_share": sum(ordered[:5]) / total,
    }


def _absolute_delta_share(records: list[dict], field: str, top: int) -> float:
    values = sorted((abs(record[field]) for record in records), reverse=True)
    total = math.fsum(values)
    return math.fsum(values[:top]) / total if total else 0.0


def _incremental_diagnostics(
    signal: list[float], market: list[float], outcomes: list[int], *, name: str
) -> dict:
    market_errors = [outcome - probability
                     for outcome, probability in zip(outcomes, market, strict=True)]
    signal_residual = _residualize(signal, market)
    outcome_residual = _residualize([float(value) for value in outcomes], market)
    signal_variance = math.fsum((value - _mean(signal)) ** 2 for value in signal)
    residual_variance = math.fsum(value * value for value in signal_residual)
    signal_ranks, market_ranks = _ranks(signal), _ranks(market)
    outcome_ranks = _ranks([float(value) for value in outcomes])
    return {
        "available": True,
        "signal": name,
        "rows": len(signal),
        "pearson_with_market_error_outcome_minus_probability": _correlation(signal, market_errors),
        "rank_with_market_error_outcome_minus_probability": _correlation(
            _ranks(signal), _ranks(market_errors)
        ),
        "partial_pearson_with_outcome_controlling_market_probability": _correlation(
            signal_residual, outcome_residual
        ),
        "partial_rank_with_outcome_controlling_market_probability": _correlation(
            _residualize(signal_ranks, market_ranks),
            _residualize(outcome_ranks, market_ranks),
        ),
        "pearson_with_market_probability": _correlation(signal, market),
        "residual_variance_fraction_after_market_probability": (
            residual_variance / signal_variance if signal_variance else None
        ),
    }


def score_probability_forecasts(
    materialized_rows: object,
    candidate_records: object,
    *,
    raw_signal_records: object | None = None,
    spec: ProperScoreSpec | None = None,
) -> dict:
    """Score a candidate and market baseline on exactly the same trusted rows."""
    spec = ProperScoreSpec() if spec is None else spec
    if not isinstance(spec, ProperScoreSpec):
        raise ValueError("explicit ProperScoreSpec required")
    policy = spec.policy
    rows = validate_probability_rows(materialized_rows, policy=policy)
    candidate = validate_prediction_records(candidate_records, rows, policy=policy)
    market = {row.key: row.market_probability for row in rows}
    outcomes = [row.outcome for row in rows]
    candidate_values = [candidate[row.key] for row in rows]
    market_values = [market[row.key] for row in rows]

    candidate_brier = _losses(rows, candidate, brier_loss)
    market_brier = _losses(rows, market, brier_loss)
    candidate_log = _losses(
        rows, candidate, lambda probability, outcome: bounded_log_loss(
            probability, outcome, policy=policy
        )
    )
    market_log = _losses(
        rows, market, lambda probability, outcome: bounded_log_loss(
            probability, outcome, policy=policy
        )
    )
    events = _group_records(
        rows, candidate_brier, market_brier, candidate_log, market_log,
        lambda row: row.event_id, "event_id"
    )
    dates = _group_records(
        rows, candidate_brier, market_brier, candidate_log, market_log,
        lambda row: row.utc_date, "utc_date"
    )
    event_brier_deltas = [record["candidate_minus_market_brier"] for record in events]
    event_log_deltas = [record["candidate_minus_market_log_loss"] for record in events]
    date_brier_deltas = [record["candidate_minus_market_brier"] for record in dates]
    date_log_deltas = [record["candidate_minus_market_log_loss"] for record in dates]

    date_blocks = []
    for start in range(0, len(dates), spec.date_block_days):
        members = dates[start:start + spec.date_block_days]
        date_blocks.append({
            "first_utc_date": members[0]["utc_date"],
            "last_utc_date": members[-1]["utc_date"],
            "dates": len(members),
            "candidate_minus_market_brier": _mean(
                member["candidate_minus_market_brier"] for member in members
            ),
            "candidate_minus_market_log_loss": _mean(
                member["candidate_minus_market_log_loss"] for member in members
            ),
        })

    adjustment = [candidate_value - market_value for candidate_value, market_value in
                  zip(candidate_values, market_values, strict=True)]
    if raw_signal_records is None:
        raw_signal = {
            "available": False,
            "unavailable_reason": "no exact-mask raw_signal_records supplied",
        }
        canonical_raw_signals = None
    else:
        raw_map = validate_raw_signal_records(raw_signal_records, rows)
        canonical_raw_signals = [
            {
                "event_id": row.event_id,
                "market_id": row.market_id,
                "cutoff_ms": row.cutoff_ms,
                "raw_signal": raw_map[row.key],
            }
            for row in rows
        ]
        raw_signal = _incremental_diagnostics(
            [raw_map[row.key] for row in rows], market_values, outcomes, name="raw_signal"
        )

    event_counts: dict[str, int] = {}
    date_counts: dict[str, int] = {}
    for row in rows:
        event_counts[row.event_id] = event_counts.get(row.event_id, 0) + 1
        date_counts[row.utc_date] = date_counts.get(row.utc_date, 0) + 1

    equal_event_candidate_brier = _mean(record["candidate_brier"] for record in events)
    equal_event_market_brier = _mean(record["market_brier"] for record in events)
    equal_event_candidate_log = _mean(record["candidate_log_loss"] for record in events)
    equal_event_market_log = _mean(record["market_log_loss"] for record in events)
    complete_mask_sha256 = _fingerprint([list(row.key) for row in rows])
    canonical_candidates = [
        {
            "event_id": row.event_id,
            "market_id": row.market_id,
            "cutoff_ms": row.cutoff_ms,
            "probability": candidate[row.key],
        }
        for row in rows
    ]
    scorer_spec = {
        "probability_epsilon": spec.probability_epsilon,
        "reliability_bins": spec.reliability_bins,
        "bootstrap_seed": spec.bootstrap_seed,
        "bootstrap_replicates": spec.bootstrap_replicates,
        "date_block_days": spec.date_block_days,
    }
    input_commitments = {
        "trusted_rows_sha256": _fingerprint([row.trusted_dict() for row in rows]),
        "public_rows_sha256": _fingerprint([row.public_dict() for row in rows]),
        "candidate_records_sha256": _fingerprint(canonical_candidates),
        "raw_signal_records_sha256": (
            _fingerprint(canonical_raw_signals) if canonical_raw_signals is not None else None
        ),
        "scorer_spec_sha256": _fingerprint(scorer_spec),
        "complete_mask_sha256": complete_mask_sha256,
    }
    aggregate_metrics = {
        "candidate_brier": equal_event_candidate_brier,
        "market_brier": equal_event_market_brier,
        "candidate_minus_market_brier": equal_event_candidate_brier - equal_event_market_brier,
        "candidate_log_loss": equal_event_candidate_log,
        "market_log_loss": equal_event_market_log,
        "candidate_minus_market_log_loss": equal_event_candidate_log - equal_event_market_log,
        "coverage": 1.0,
        "rows": len(rows),
        "events": len(events),
        "dates": len(dates),
    }

    result = {
        "schema": "settlement_probability_proper_score_v1",
        "input_commitments": input_commitments,
        "probability_policy": {
            "epsilon": policy.epsilon,
            "admitted_interval": "closed [epsilon, 1-epsilon]; exact 0/1 rejected",
            "log_loss_clipping": False,
            "maximum_per_row_log_loss": policy.maximum_log_loss,
        },
        "primary": {
            "aggregation": "equal_event_after_equal_row_within_event",
            "equal_event_candidate_brier": equal_event_candidate_brier,
            "equal_event_market_brier": equal_event_market_brier,
            "equal_event_candidate_minus_market_brier": _mean(event_brier_deltas),
            "equal_event_candidate_log_loss": equal_event_candidate_log,
            "equal_event_market_log_loss": equal_event_market_log,
            "equal_event_candidate_minus_market_log_loss": _mean(event_log_deltas),
            "delta_convention": "candidate_minus_market; negative loss is better",
        },
        "aggregate_metrics": aggregate_metrics,
        "row_weighted": {
            "candidate_brier": _mean(candidate_brier.values()),
            "market_brier": _mean(market_brier.values()),
            "candidate_minus_market_brier": _mean(
                candidate_brier[row.key] - market_brier[row.key] for row in rows
            ),
            "candidate_log_loss": _mean(candidate_log.values()),
            "market_log_loss": _mean(market_log.values()),
            "candidate_minus_market_log_loss": _mean(
                candidate_log[row.key] - market_log[row.key] for row in rows
            ),
        },
        "calibration": {
            "candidate": _calibration(candidate_values, outcomes),
            "market": _calibration(market_values, outcomes),
        },
        "reliability": {
            "candidate": _reliability(candidate_values, outcomes, spec.reliability_bins),
            "market": _reliability(market_values, outcomes, spec.reliability_bins),
        },
        "coverage": {
            "expected_complete_rows": len(rows),
            "candidate_rows": len(candidate),
            "market_rows": len(market),
            "common_complete_rows": len(rows),
            "common_complete_fraction": 1.0,
            "candidate_missing": 0,
            "candidate_extra": 0,
            "identical_candidate_market_mask": True,
            "complete_mask_sha256": complete_mask_sha256,
        },
        "breadth": {
            "rows": len(rows),
            "events": len(events),
            "markets": len({row.market_id for row in rows}),
            "utc_dates": len(dates),
            "minimum_rows_per_event": min(event_counts.values()),
            "maximum_rows_per_event": max(event_counts.values()),
            "minimum_rows_per_date": min(date_counts.values()),
            "maximum_rows_per_date": max(date_counts.values()),
        },
        "concentration": {
            "event_rows": _shares(list(event_counts.values())),
            "date_rows": _shares(list(date_counts.values())),
            "top_1_event_absolute_brier_delta_share": _absolute_delta_share(
                events, "candidate_minus_market_brier", 1
            ),
            "top_5_event_absolute_brier_delta_share": _absolute_delta_share(
                events, "candidate_minus_market_brier", 5
            ),
            "top_1_date_absolute_brier_delta_share": _absolute_delta_share(
                dates, "candidate_minus_market_brier", 1
            ),
            "top_5_date_absolute_brier_delta_share": _absolute_delta_share(
                dates, "candidate_minus_market_brier", 5
            ),
        },
        "paired_evidence": {
            "events": events,
            "dates": dates,
            "date_blocks": date_blocks,
            "event_brier": _paired_summary(
                events,
                key="candidate_minus_market_brier",
                interval=_bootstrap_interval(
                    event_brier_deltas,
                    replicates=spec.bootstrap_replicates,
                    seed=spec.bootstrap_seed,
                ),
            ),
            "event_log_loss": _paired_summary(
                events,
                key="candidate_minus_market_log_loss",
                interval=_bootstrap_interval(
                    event_log_deltas,
                    replicates=spec.bootstrap_replicates,
                    seed=spec.bootstrap_seed + 1,
                ),
            ),
            "date_block_brier": _paired_summary(
                dates,
                key="candidate_minus_market_brier",
                interval=_circular_block_interval(
                    date_brier_deltas,
                    block=spec.date_block_days,
                    replicates=spec.bootstrap_replicates,
                    seed=spec.bootstrap_seed,
                ),
            ),
            "date_block_log_loss": _paired_summary(
                dates,
                key="candidate_minus_market_log_loss",
                interval=_circular_block_interval(
                    date_log_deltas,
                    block=spec.date_block_days,
                    replicates=spec.bootstrap_replicates,
                    seed=spec.bootstrap_seed + 1,
                ),
            ),
        },
        "incremental_diagnostics": {
            "candidate_adjustment_vs_market": _incremental_diagnostics(
                adjustment, market_values, outcomes, name="candidate_minus_market_probability"
            ),
            "raw_signal_vs_market": raw_signal,
        },
        "inference_boundary": {
            "minimum_untouched_dates_for_promotion": 20,
            "has_minimum_date_breadth": len(dates) >= 20,
            "promotion_authorized": False,
            "pnl_reported": False,
            "claim": "proper-score arithmetic only; source, phase, selection and promotion remain external gates",
        },
    }
    result["score_receipt_sha256"] = _fingerprint(result)
    return result
