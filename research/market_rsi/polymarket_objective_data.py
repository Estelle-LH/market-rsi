"""Dense-label Polymarket materialization for Train-only objective research.

Decision rows may remain sparse, but every future-window objective is computed
from the dense raw quote stream. Features come only from the decision quote.
Future observations are labels and become available only after the full frozen
future window has closed.
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import asdict, dataclass
from statistics import median

from market_rsi import digest
from polymarket_data import NS, Quote, _quote, _source


SCHEMA = "polymarket_objective_labels_v1"


@dataclass(frozen=True)
class ObjectiveTargetSpec:
    """One pre-Dev horizon whose labels can be audited on opened Train."""

    horizon_ns: int
    point_max_lateness_ns: int
    window_start_ns: int
    window_end_ns: int
    forward_ewma_half_life_ns: int
    minimum_window_observations: int = 3

    def __post_init__(self):
        for name, value in asdict(self).items():
            if type(value) is not int or value <= 0:
                raise ValueError(f"positive integer required for {name}")
        if not self.window_start_ns < self.horizon_ns < self.window_end_ns:
            raise ValueError("horizon must be strictly inside its future window")
        if self.horizon_ns + self.point_max_lateness_ns > self.window_end_ns:
            raise ValueError("point lateness must fit inside its future window")


DISCOVERY_TARGET_SPECS = (
    ObjectiveTargetSpec(60 * NS, 5 * NS, 45 * NS, 75 * NS, 10 * NS),
    ObjectiveTargetSpec(300 * NS, 5 * NS, 270 * NS, 330 * NS, 20 * NS),
    ObjectiveTargetSpec(900 * NS, 5 * NS, 840 * NS, 960 * NS, 40 * NS),
)
DEFAULT_TARGET_SPECS = (DISCOVERY_TARGET_SPECS[0],)


def _seconds(value: int) -> int:
    if value % NS:
        raise ValueError("objective times must be whole seconds")
    return value // NS


def _objective_ids(spec: ObjectiveTargetSpec) -> dict[str, str]:
    horizon = _seconds(spec.horizon_ns)
    start = _seconds(spec.window_start_ns)
    end = _seconds(spec.window_end_ns)
    return {
        "point": f"future-midpoint-point-{horizon}s-v1",
        "mean": f"future-midpoint-window-mean-{start}-{end}s-v1",
        "forward_ewma": f"future-midpoint-window-forward-ewma-{start}-{end}s-v1",
        "median": f"future-midpoint-window-median-{start}-{end}s-v1",
    }


@dataclass(frozen=True)
class ObjectiveMaterializationPolicy:
    point_horizon_ns: int = 60 * NS
    point_max_lateness_ns: int = 5 * NS
    window_start_ns: int = 45 * NS
    window_end_ns: int = 75 * NS
    forward_ewma_half_life_ns: int = 10 * NS
    minimum_window_observations: int = 3
    decision_interval_ns: int = 60 * NS
    max_pregame_lead_ns: int = 6 * 60 * 60 * NS
    maximum_clock_disagreement_ns: int = 5 * NS

    def __post_init__(self):
        for name, value in asdict(self).items():
            if type(value) is not int or value <= 0:
                raise ValueError(f"positive integer required for {name}")
        if not self.window_start_ns < self.point_horizon_ns < self.window_end_ns:
            raise ValueError("point horizon must be strictly inside future window")
        if self.point_horizon_ns + self.point_max_lateness_ns > self.window_end_ns:
            raise ValueError("point lateness must fit inside future window")


def _features(decision: Quote) -> dict:
    bid = decision.bid_1e4 / 10_000
    ask = decision.ask_1e4 / 10_000
    bid_size = decision.bid_size_1e2 / 100
    ask_size = decision.ask_size_1e2 / 100
    return {
        "bid": bid,
        "ask": ask,
        "mid": (bid + ask) / 2,
        "spread": ask - bid,
        "bid_size": bid_size,
        "ask_size": ask_size,
        "imbalance": (bid_size - ask_size) / (bid_size + ask_size),
    }


def _finalize(state: dict, closing_quote: Quote, source_sha256: str,
              policy: ObjectiveMaterializationPolicy,
              target_specs: tuple[ObjectiveTargetSpec, ...],
              counts: Counter) -> dict:
    decision = state["decision"]
    targets = {}
    objective_diagnostics = {}
    legacy_metadata = {}
    for spec in target_specs:
        ids = _objective_ids(spec)
        horizon_seconds = _seconds(spec.horizon_ns)
        point: Quote | None = state["points"][horizon_seconds]
        observations: list[Quote] = state["windows"][horizon_seconds]
        point_target = point.mid_2e4 / 20_000 if point is not None else None
        mean_target = ewma_target = median_target = effective_ns = stability = None
        if len(observations) >= spec.minimum_window_observations:
            values = [quote.mid_2e4 / 20_000 for quote in observations]
            offsets = [quote.available_ns - decision.available_ns for quote in observations]
            weights = [
                0.5 ** ((spec.window_end_ns - offset)
                        / spec.forward_ewma_half_life_ns)
                for offset in offsets
            ]
            weight_sum = math.fsum(weights)
            mean_target = math.fsum(values) / len(values)
            ewma_target = math.fsum(
                value * weight for value, weight in zip(values, weights)
            ) / weight_sum
            median_target = median(values)
            effective_ns = math.fsum(
                offset * weight for offset, weight in zip(offsets, weights)
            ) / weight_sum
            early = [value for value, offset in zip(values, offsets)
                     if offset <= spec.horizon_ns]
            late = [value for value, offset in zip(values, offsets)
                    if offset > spec.horizon_ns]
            if early and late:
                stability = abs(
                    math.fsum(early) / len(early) - math.fsum(late) / len(late)
                )
            counts[f"window_labeled_rows_{horizon_seconds}s"] += 1
        else:
            counts[f"window_insufficient_observations_{horizon_seconds}s"] += 1
        if point is None:
            counts[f"point_missing_within_lateness_{horizon_seconds}s"] += 1
        else:
            counts[f"point_labeled_rows_{horizon_seconds}s"] += 1
        targets.update({
            ids["point"]: point_target,
            ids["mean"]: mean_target,
            ids["forward_ewma"]: ewma_target,
            ids["median"]: median_target,
        })
        window_ordinals = [quote.source_ordinal for quote in observations]
        common = {
            "horizon_seconds": horizon_seconds,
            "label_window_start_ns": decision.available_ns + spec.window_start_ns,
            "label_window_end_ns": decision.available_ns + spec.window_end_ns,
            "future_observation_count": len(observations),
            "future_source_ordinal_sha256": digest(window_ordinals),
            "first_future_source": (
                _source(source_sha256, observations[0]) if observations else None
            ),
            "last_future_source": (
                _source(source_sha256, observations[-1]) if observations else None
            ),
            "absolute_early_late_mean_difference": stability,
        }
        objective_diagnostics[ids["point"]] = {
            "horizon_seconds": horizon_seconds,
            "point_source": _source(source_sha256, point) if point is not None else None,
        }
        for name in ("mean", "median"):
            objective_diagnostics[ids[name]] = common
        objective_diagnostics[ids["forward_ewma"]] = {
            **common,
            "forward_ewma_effective_horizon_ms": (
                effective_ns / 1_000_000 if effective_ns is not None else None
            ),
        }
        if horizon_seconds == 60:
            counts["window_labeled_rows"] = counts["window_labeled_rows_60s"]
            counts["window_insufficient_observations"] = counts[
                "window_insufficient_observations_60s"
            ]
            counts["point_labeled_rows"] = counts["point_labeled_rows_60s"]
            counts["point_missing_within_lateness"] = counts[
                "point_missing_within_lateness_60s"
            ]
            legacy_metadata = {
                "future_observation_count": len(observations),
                "future_source_ordinal_sha256": digest(window_ordinals),
                "first_future_source": common["first_future_source"],
                "last_future_source": common["last_future_source"],
                "point_source": objective_diagnostics[ids["point"]]["point_source"],
                "forward_ewma_effective_horizon_ms": (
                    effective_ns / 1_000_000 if effective_ns is not None else None
                ),
                "absolute_early_late_mean_difference": stability,
            }
    return {
        "row_id": digest({
            "source": source_sha256,
            "ordinal": decision.source_ordinal,
            "market": decision.market_slug,
            "objective_materializer": SCHEMA,
        }),
        "game_id": decision.game.game_id,
        "event_slug": decision.game.event_slug,
        "market_id": decision.market_slug,
        "game_start_ms": decision.game.start_ns // 1_000_000,
        "decision_ms": decision.available_ns // 1_000_000,
        "decision_ns": decision.available_ns,
        "feature_available_ms": decision.available_ns // 1_000_000,
        "label_window_start_ns": decision.available_ns + policy.window_start_ns,
        "label_window_end_ns": decision.available_ns + max(
            spec.window_end_ns for spec in target_specs
        ),
        "label_available_ms": closing_quote.available_ns // 1_000_000,
        "input_source": _source(source_sha256, decision),
        "features": _features(decision),
        "target_candidates": targets,
        "target_metadata": {
            **legacy_metadata,
            "objective_diagnostics": objective_diagnostics,
        },
    }


def materialize_objective_books(
    records,
    catalog: dict,
    source_sha256: str,
    policy: ObjectiveMaterializationPolicy = ObjectiveMaterializationPolicy(),
    target_specs: tuple[ObjectiveTargetSpec, ...] = DEFAULT_TARGET_SPECS,
) -> dict:
    """Create sparse decisions and dense future-window label candidates."""
    if not isinstance(catalog, dict) or not catalog:
        raise ValueError("nonempty audited event catalog required")
    if (not isinstance(source_sha256, str) or len(source_sha256) != 64
            or any(character not in "0123456789abcdef" for character in source_sha256)):
        raise ValueError("source SHA-256 required")
    if (not isinstance(target_specs, tuple) or not target_specs
            or any(not isinstance(spec, ObjectiveTargetSpec) for spec in target_specs)
            or len({_seconds(spec.horizon_ns) for spec in target_specs}) != len(target_specs)
            or tuple(sorted(target_specs, key=lambda spec: spec.horizon_ns)) != target_specs):
        raise ValueError("unique chronological objective target specs required")
    maximum_window_end_ns = max(spec.window_end_ns for spec in target_specs)
    counts = Counter()
    pending: dict[str, list[dict]] = {}
    last_decision: dict[str, int] = {}
    last_market_time: dict[str, int] = {}
    rows = []
    for ordinal, record in enumerate(records):
        quote = _quote(record, ordinal, catalog, policy, counts)
        if quote is None:
            continue
        if quote.available_ns <= last_market_time.get(quote.market_slug, -1):
            raise ValueError("duplicate or reversed market availability time")
        last_market_time[quote.market_slug] = quote.available_ns
        waiting = []
        for state in pending.get(quote.market_slug, []):
            decision = state["decision"]
            offset = quote.available_ns - decision.available_ns
            if offset > maximum_window_end_ns:
                rows.append(_finalize(
                    state, quote, source_sha256, policy, target_specs, counts
                ))
                counts["finalized_decisions"] += 1
                continue
            for spec in target_specs:
                horizon_seconds = _seconds(spec.horizon_ns)
                if spec.window_start_ns <= offset <= spec.window_end_ns:
                    state["windows"][horizon_seconds].append(quote)
                if (
                    state["points"][horizon_seconds] is None
                    and spec.horizon_ns <= offset
                    <= spec.horizon_ns + spec.point_max_lateness_ns
                ):
                    state["points"][horizon_seconds] = quote
            waiting.append(state)
        pending[quote.market_slug] = waiting
        previous = last_decision.get(quote.market_slug)
        if previous is None or quote.available_ns - previous >= policy.decision_interval_ns:
            pending[quote.market_slug].append({
                "decision": quote,
                "windows": {_seconds(spec.horizon_ns): [] for spec in target_specs},
                "points": {_seconds(spec.horizon_ns): None for spec in target_specs},
            })
            last_decision[quote.market_slug] = quote.available_ns
            counts["scheduled_decisions"] += 1
    counts["capture_tail_censored"] += sum(map(len, pending.values()))
    rows.sort(key=lambda row: (row["decision_ns"], row["row_id"]))
    return {
        "schema": SCHEMA,
        "policy": asdict(policy),
        "target_specs": [asdict(spec) for spec in target_specs],
        "availability_clock": "observed_at",
        "feature_source": "decision_quote_only",
        "label_source": "dense_future_quotes_only",
        "label_availability_rule": "after_full_future_window_closes",
        "source_sha256": source_sha256,
        "rows": rows,
        "counts": dict(counts),
        "imputation_count": 0,
        "exchange_transact_time_used": False,
        "scoring_ready": False,
        "objective_selection_performed": False,
    }
