"""Strict settlement-probability rows and label-safe candidate projections.

This module validates already-materialized rows.  It does not establish source
provenance or prove that a timestamp supplied by a collector is truthful.  The
trusted caller must do that before using this structural contract.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable


ROW_FIELDS = frozenset({
    "event_id",
    "market_id",
    "cutoff_ms",
    "feature_available_ms",
    "market_probability",
    "outcome_available_ms",
    "outcome",
})
PUBLIC_ROW_FIELDS = frozenset({
    "event_id",
    "market_id",
    "cutoff_ms",
    "feature_available_ms",
    "market_probability",
})
PREDICTION_FIELDS = frozenset({
    "event_id", "market_id", "cutoff_ms", "probability",
})
RAW_SIGNAL_FIELDS = frozenset({
    "event_id", "market_id", "cutoff_ms", "raw_signal",
})

_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")


@dataclass(frozen=True)
class ProbabilityPolicy:
    """Open-endpoint policy shared by rows, predictions and log loss.

    Values in ``[epsilon, 1 - epsilon]`` are admitted.  Exact zero/one and
    values closer to an endpoint are rejected rather than silently clipped.
    Thus the maximum possible per-row log loss is explicitly
    ``-log(epsilon)``.
    """

    epsilon: float = 1e-6

    def __post_init__(self) -> None:
        epsilon = _finite_number(self.epsilon, "probability epsilon")
        if not 0 < epsilon < 0.5:
            raise ValueError("probability epsilon must be strictly between zero and one half")
        object.__setattr__(self, "epsilon", epsilon)

    @property
    def maximum_log_loss(self) -> float:
        return -math.log(self.epsilon)


@dataclass(frozen=True)
class SettlementProbabilityRow:
    event_id: str
    market_id: str
    cutoff_ms: int
    feature_available_ms: int
    market_probability: float
    outcome_available_ms: int
    outcome: int

    @property
    def key(self) -> tuple[str, str, int]:
        return (self.event_id, self.market_id, self.cutoff_ms)

    @property
    def utc_date(self) -> str:
        return utc_date(self.cutoff_ms)

    def public_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "market_id": self.market_id,
            "cutoff_ms": self.cutoff_ms,
            "feature_available_ms": self.feature_available_ms,
            "market_probability": self.market_probability,
        }

    def trusted_dict(self) -> dict:
        return {**self.public_dict(),
                "outcome_available_ms": self.outcome_available_ms,
                "outcome": self.outcome}


def utc_date(timestamp_ms: int) -> str:
    _timestamp(timestamp_ms, "timestamp_ms")
    try:
        return datetime.fromtimestamp(timestamp_ms / 1000, timezone.utc).date().isoformat()
    except (OverflowError, OSError, ValueError) as exc:
        raise ValueError("timestamp_ms is outside the supported UTC range") from exc


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be a finite number")
    return result


DEFAULT_PROBABILITY_POLICY = ProbabilityPolicy()


def _timestamp(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer millisecond timestamp")
    return value


def _identifier_value(value: object, label: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{label} must be a nonempty conservative identifier")
    return value


def validate_probability(value: object, policy: ProbabilityPolicy, label: str) -> float:
    if not isinstance(policy, ProbabilityPolicy):
        raise ValueError("explicit ProbabilityPolicy required")
    probability = _finite_number(value, label)
    if not policy.epsilon <= probability <= 1 - policy.epsilon:
        raise ValueError(
            f"{label} violates epsilon policy; require epsilon <= p <= 1-epsilon"
        )
    return probability


def _row_from_dict(row: object, policy: ProbabilityPolicy) -> SettlementProbabilityRow:
    if not isinstance(row, dict) or set(row) != ROW_FIELDS:
        raise ValueError("exact settlement-probability row schema required")
    event_id = _identifier_value(row["event_id"], "event_id")
    market_id = _identifier_value(row["market_id"], "market_id")
    cutoff = _timestamp(row["cutoff_ms"], "cutoff_ms")
    feature_available = _timestamp(row["feature_available_ms"], "feature_available_ms")
    outcome_available = _timestamp(row["outcome_available_ms"], "outcome_available_ms")
    if feature_available > cutoff:
        raise ValueError("future feature is unavailable at the prediction cutoff")
    if outcome_available <= cutoff:
        raise ValueError("outcome must be unavailable and strictly future at the prediction cutoff")
    outcome = row["outcome"]
    if type(outcome) is not int or outcome not in (0, 1):
        raise ValueError("outcome must be the binary integer zero or one")
    return SettlementProbabilityRow(
        event_id=event_id,
        market_id=market_id,
        cutoff_ms=cutoff,
        feature_available_ms=feature_available,
        market_probability=validate_probability(
            row["market_probability"], policy, "market_probability"
        ),
        outcome_available_ms=outcome_available,
        outcome=outcome,
    )


def validate_probability_rows(
    rows: object, *, policy: ProbabilityPolicy = DEFAULT_PROBABILITY_POLICY
) -> tuple[SettlementProbabilityRow, ...]:
    """Validate and canonically order nonempty trusted settlement rows."""
    if not isinstance(rows, list) or not rows:
        raise ValueError("nonempty settlement-probability row list required")
    parsed = [_row_from_dict(row, policy) for row in rows]
    seen: set[tuple[str, str, int]] = set()
    market_events: dict[str, str] = {}
    resolutions: dict[tuple[str, str], tuple[int, int]] = {}
    for row in parsed:
        if row.key in seen:
            raise ValueError("duplicate event/market/cutoff probability row")
        seen.add(row.key)
        previous_event = market_events.setdefault(row.market_id, row.event_id)
        if previous_event != row.event_id:
            raise ValueError("market_id is relabelled under another event_id")
        resolution_key = (row.event_id, row.market_id)
        resolution = (row.outcome_available_ms, row.outcome)
        if resolutions.setdefault(resolution_key, resolution) != resolution:
            raise ValueError("one event/market has inconsistent resolution facts")
    return tuple(sorted(parsed, key=lambda item: (
        item.cutoff_ms, item.event_id, item.market_id
    )))


def validate_train_evaluation_rows(
    train_rows: object,
    evaluation_rows: object,
    *,
    policy: ProbabilityPolicy = DEFAULT_PROBABILITY_POLICY,
) -> tuple[tuple[SettlementProbabilityRow, ...], tuple[SettlementProbabilityRow, ...]]:
    """Enforce whole-event split isolation and label availability chronology."""
    train = validate_probability_rows(train_rows, policy=policy)
    evaluation = validate_probability_rows(evaluation_rows, policy=policy)
    # Revalidate global market->event identity across both independently valid sets.
    market_events: dict[str, str] = {}
    for row in (*train, *evaluation):
        if market_events.setdefault(row.market_id, row.event_id) != row.event_id:
            raise ValueError("market_id is relabelled across Train and evaluation")
    train_events = {row.event_id for row in train}
    evaluation_events = {row.event_id for row in evaluation}
    if train_events & evaluation_events:
        raise ValueError("same underlying event cannot appear in more than one split")
    first_evaluation_cutoff = min(row.cutoff_ms for row in evaluation)
    if max(row.outcome_available_ms for row in train) >= first_evaluation_cutoff:
        raise ValueError("every training label must be available before evaluation cutoffs")
    return train, evaluation


def build_candidate_views(
    train_rows: object,
    evaluation_rows: object,
    *,
    policy: ProbabilityPolicy = DEFAULT_PROBABILITY_POLICY,
) -> dict[str, list[dict]]:
    """Return labelled Train and label-free evaluation views after split checks."""
    train, evaluation = validate_train_evaluation_rows(
        train_rows, evaluation_rows, policy=policy
    )
    return {
        "train": [row.trusted_dict() for row in train],
        "evaluation": [row.public_dict() for row in evaluation],
    }


def validate_public_probability_rows(
    rows: object, *, policy: ProbabilityPolicy = DEFAULT_PROBABILITY_POLICY
) -> tuple[dict, ...]:
    """Validate that candidate-facing evaluation rows contain no outcomes."""
    if not isinstance(rows, list) or not rows:
        raise ValueError("nonempty public probability row list required")
    result = []
    seen = set()
    market_events: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != PUBLIC_ROW_FIELDS:
            raise ValueError("exact label-free public probability row schema required")
        event_id = _identifier_value(row["event_id"], "event_id")
        market_id = _identifier_value(row["market_id"], "market_id")
        cutoff = _timestamp(row["cutoff_ms"], "cutoff_ms")
        feature_available = _timestamp(row["feature_available_ms"], "feature_available_ms")
        if feature_available > cutoff:
            raise ValueError("future feature is unavailable at the prediction cutoff")
        key = (event_id, market_id, cutoff)
        if key in seen:
            raise ValueError("duplicate public event/market/cutoff row")
        seen.add(key)
        if market_events.setdefault(market_id, event_id) != event_id:
            raise ValueError("market_id is relabelled under another event_id")
        result.append({
            "event_id": event_id,
            "market_id": market_id,
            "cutoff_ms": cutoff,
            "feature_available_ms": feature_available,
            "market_probability": validate_probability(
                row["market_probability"], policy, "market_probability"
            ),
        })
    return tuple(sorted(result, key=lambda item: (
        item["cutoff_ms"], item["event_id"], item["market_id"]
    )))


def _validate_keyed_values(
    records: object,
    expected_rows: Iterable[SettlementProbabilityRow],
    *,
    fields: frozenset[str],
    value_field: str,
    bounded_probability: bool,
    policy: ProbabilityPolicy,
) -> dict[tuple[str, str, int], float]:
    if not isinstance(records, list):
        raise ValueError(f"{value_field} records must be a list")
    values: dict[tuple[str, str, int], float] = {}
    for record in records:
        if not isinstance(record, dict) or set(record) != fields:
            raise ValueError(f"exact keyed {value_field} record schema required")
        key = (
            _identifier_value(record["event_id"], "event_id"),
            _identifier_value(record["market_id"], "market_id"),
            _timestamp(record["cutoff_ms"], "cutoff_ms"),
        )
        if key in values:
            raise ValueError(f"duplicate keyed {value_field} record")
        values[key] = (
            validate_probability(record[value_field], policy, value_field)
            if bounded_probability
            else _finite_number(record[value_field], value_field)
        )
    expected = {row.key for row in expected_rows}
    if set(values) != expected:
        raise ValueError(
            f"{value_field} mask must exactly match every complete market row"
        )
    return values


def validate_prediction_records(
    records: object,
    expected_rows: Iterable[SettlementProbabilityRow],
    *,
    policy: ProbabilityPolicy = DEFAULT_PROBABILITY_POLICY,
) -> dict[tuple[str, str, int], float]:
    return _validate_keyed_values(
        records,
        expected_rows,
        fields=PREDICTION_FIELDS,
        value_field="probability",
        bounded_probability=True,
        policy=policy,
    )


def validate_raw_signal_records(
    records: object,
    expected_rows: Iterable[SettlementProbabilityRow],
) -> dict[tuple[str, str, int], float]:
    return _validate_keyed_values(
        records,
        expected_rows,
        fields=RAW_SIGNAL_FIELDS,
        value_field="raw_signal",
        bounded_probability=False,
        policy=DEFAULT_PROBABILITY_POLICY,
    )
