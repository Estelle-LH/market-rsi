"""Automatic opened-Train diagnostics for objective discovery."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import math

from market_rsi import digest


SCHEMA = "market_time_series_data_diagnostics_v1"


def _date(milliseconds: int) -> str:
    return datetime.fromtimestamp(milliseconds / 1000, timezone.utc).date().isoformat()


def _quantile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * probability)]


def _finite(value) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
    )


def diagnose(source: dict, *, opened_train_utc_dates: list[str]) -> dict:
    """Profile the task without using Dev, Future Test, or candidate scores."""
    if (not isinstance(source, dict)
            or source.get("schema") not in {
                "polymarket_midpoint_labels_v1",
                "polymarket_objective_labels_v1",
            }
            or not isinstance(source.get("rows"), list)):
        raise ValueError("supported Train materialization required")
    if (not isinstance(opened_train_utc_dates, list)
            or not opened_train_utc_dates
            or opened_train_utc_dates != sorted(set(opened_train_utc_dates))):
        raise ValueError("unique chronological opened Train dates required")
    dates = set(opened_train_utc_dates)
    rows = [row for row in source["rows"]
            if isinstance(row, dict) and _date(row.get("decision_ms")) in dates]
    if not rows:
        raise ValueError("no rows in opened Train dates")

    by_market: dict[str, list[int]] = defaultdict(list)
    by_game_error: dict[str, list[float]] = defaultdict(list)
    changes = []
    target_non_null_counts: dict[str, int] = defaultdict(int)
    for row in rows:
        decision_ms = row.get("decision_ms")
        market_id = row.get("market_id")
        game_id = row.get("game_id")
        midpoint = row.get("features", {}).get("mid")
        if (type(decision_ms) is not int or not isinstance(market_id, str)
                or not market_id or not isinstance(game_id, str) or not game_id
                or not _finite(midpoint)):
            raise ValueError("complete finite Train row identity and midpoint required")
        by_market[market_id].append(decision_ms)
        if source["schema"] == "polymarket_midpoint_labels_v1":
            point = row.get("target")
            if not _finite(point):
                raise ValueError("finite point target required")
            target_non_null_counts["future-midpoint-point-60s-v1"] += 1
        else:
            targets = row.get("target_candidates")
            if not isinstance(targets, dict):
                raise ValueError("target candidates required")
            for objective_id, value in targets.items():
                if value is not None:
                    if not _finite(value):
                        raise ValueError("target candidates must be finite or null")
                    target_non_null_counts[objective_id] += 1
            point = targets.get("future-midpoint-point-60s-v1")
        if point is not None:
            change = float(point) - float(midpoint)
            changes.append(change)
            by_game_error[game_id].append(change * change)

    intervals = []
    for times in by_market.values():
        times.sort()
        intervals.extend((right - left) / 1000 for left, right in zip(times, times[1:])
                         if _date(left) == _date(right))
    absolute_changes = [abs(value) for value in changes]
    equal_game_mse = None
    if by_game_error:
        equal_game_mse = math.fsum(
            math.fsum(errors) / len(errors) for errors in by_game_error.values()
        ) / len(by_game_error)
    trade_present = (
        isinstance(source.get("trade_stream_provenance"), dict)
        and source.get("trade_stream_provenance", {}).get("verified") is True
    )
    median_interval = _quantile(intervals, 0.50)
    findings = []
    unchanged_fraction = None
    if absolute_changes:
        unchanged_fraction = sum(value <= 1e-12 for value in absolute_changes) / len(
            absolute_changes
        )
        if unchanged_fraction >= 0.90:
            findings.append("point_target_is_at_least_90_percent_unchanged")
        if equal_game_mse == 0:
            findings.append("persistence_baseline_is_perfect_on_open_train")
    if (source["schema"] == "polymarket_midpoint_labels_v1"
            and median_interval is not None and median_interval > 30):
        findings.append("materialized_decisions_are_too_sparse_for_45_75s_window_labels")
    if not trade_present:
        findings.append("verified_trade_stream_is_absent")
    body = {
        "schema": SCHEMA,
        "evidence_class": "opened_train_only",
        "opened_train_utc_dates": opened_train_utc_dates,
        "dev_labels_used": False,
        "future_test_used": False,
        "candidate_model_scores_used": False,
        "rows": len(rows),
        "games": len({row["game_id"] for row in rows}),
        "markets": len(by_market),
        "decision_cadence_seconds": {
            "intervals": len(intervals),
            "p10": _quantile(intervals, 0.10),
            "p50": median_interval,
            "p90": _quantile(intervals, 0.90),
        },
        "point_target": {
            "covered_rows": len(changes),
            "coverage_fraction": len(changes) / len(rows),
            "unchanged_fraction": unchanged_fraction,
            "absolute_move_p50": _quantile(absolute_changes, 0.50),
            "absolute_move_p90": _quantile(absolute_changes, 0.90),
            "absolute_move_p99": _quantile(absolute_changes, 0.99),
            "persistence_equal_game_mse": equal_game_mse,
        },
        "objective_coverage": {
            objective_id: count / len(rows)
            for objective_id, count in sorted(target_non_null_counts.items())
        },
        "source_inventory": {
            "quote_book_present": True,
            "verified_trade_stream_present": trade_present,
            "event_resolution_present": bool(source.get("resolution_stream_provenance")),
            "raw_quote_cadence_receipt_present": isinstance(
                source.get("raw_quote_cadence"), dict
            ),
        },
        "findings": findings,
        "next_actions_are_controller_decisions": True,
    }
    return {**body, "diagnostic_sha256": digest(body)}
