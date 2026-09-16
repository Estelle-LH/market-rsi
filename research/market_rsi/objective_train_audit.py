#!/usr/bin/env python3
"""Audit candidate objectives using only explicitly opened Train dates."""
from __future__ import annotations

import argparse
from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from statistics import median

from market_rsi import digest, file_hash, fresh_json
from objective_contract import discovery_policy, objective_catalog


SCHEMA = "market_objective_train_audit_v1"
WINDOW_START_MS = 45_000
WINDOW_CENTER_MS = 60_000
WINDOW_END_MS = 75_000


def _date(milliseconds: int) -> str:
    return datetime.fromtimestamp(milliseconds / 1000, timezone.utc).date().isoformat()


def _quantile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = round((len(ordered) - 1) * probability)
    return ordered[index]


def _equal_game_mse(records: list[dict], target_key: str) -> float:
    by_game: dict[str, list[float]] = defaultdict(list)
    for record in records:
        by_game[record["game_id"]].append(
            (record[target_key] - record["midpoint"]) ** 2
        )
    return math.fsum(
        math.fsum(errors) / len(errors) for errors in by_game.values()
    ) / len(by_game)


def _diagnostics(records: list[dict], target_key: str) -> dict:
    changes = [record[target_key] - record["midpoint"] for record in records]
    absolute = [abs(value) for value in changes]
    nonzero = [value for value in absolute if value > 1e-12]
    mse = _equal_game_mse(records, target_key)
    by_day = {}
    for day in sorted({record["utc_date"] for record in records}):
        day_records = [record for record in records if record["utc_date"] == day]
        by_day[day] = {
            "rows": len(day_records),
            "games": len({record["game_id"] for record in day_records}),
            "persistence_equal_game_mse": _equal_game_mse(day_records, target_key),
        }
    return {
        "rows": len(records),
        "games": len({record["game_id"] for record in records}),
        "utc_dates": len({record["utc_date"] for record in records}),
        "unchanged_fraction": sum(value <= 1e-12 for value in absolute) / len(records),
        "moving_fraction": sum(value > 1e-12 for value in absolute) / len(records),
        "absolute_move_probability": {
            "p50": _quantile(absolute, 0.50),
            "p90": _quantile(absolute, 0.90),
            "p99": _quantile(absolute, 0.99),
            "median_nonzero": median(nonzero) if nonzero else None,
        },
        "persistence_equal_game_mse": mse,
        "persistence_rmse_probability_bps": math.sqrt(mse) * 10_000,
        "by_utc_day": by_day,
    }


def audit(source: dict, *, train_utc_dates: list[str]) -> dict:
    if (not isinstance(source, dict)
            or source.get("schema") not in {
                "polymarket_midpoint_labels_v1",
                "polymarket_objective_labels_v1",
            }
            or not isinstance(source.get("rows"), list)):
        raise ValueError("Polymarket objective materialization required")
    if (not isinstance(train_utc_dates, list) or len(train_utc_dates) < 4
            or train_utc_dates != sorted(set(train_utc_dates))):
        raise ValueError("at least four unique chronological Train dates required")
    train_dates = set(train_utc_dates)
    eligible_rows = []
    for row in source["rows"]:
        if not isinstance(row, dict) or _date(row["decision_ms"]) not in train_dates:
            continue
        midpoint = row.get("features", {}).get("mid")
        if (isinstance(midpoint, bool) or not isinstance(midpoint, (int, float))
                or not math.isfinite(midpoint)):
            raise ValueError("finite decision midpoint required")
        eligible_rows.append(row)
    if not eligible_rows:
        raise ValueError("no rows on selected Train dates")

    point_records = []
    window_records = []
    stability_differences = []
    candidate_records: dict[str, list[dict]] = defaultdict(list)
    candidate_stability: dict[str, list[float]] = defaultdict(list)
    candidate_effective_horizon_ms: dict[str, list[float]] = defaultdict(list)
    if source["schema"] == "polymarket_objective_labels_v1":
        for row in eligible_rows:
            targets = row.get("target_candidates")
            metadata = row.get("target_metadata")
            if not isinstance(targets, dict) or not isinstance(metadata, dict):
                raise ValueError("dense objective targets and metadata required")
            objective_metadata = metadata.get("objective_diagnostics", {})
            if not isinstance(objective_metadata, dict):
                raise ValueError("objective-specific metadata must be an object")
            for objective_id, target in targets.items():
                if target is None:
                    continue
                if (isinstance(target, bool) or not isinstance(target, (int, float))
                        or not math.isfinite(target)):
                    raise ValueError("target candidates must be finite or null")
                candidate_records[objective_id].append({
                    "game_id": row["game_id"],
                    "utc_date": _date(row["decision_ms"]),
                    "midpoint": float(row["features"]["mid"]),
                    "target": float(target),
                })
                details = objective_metadata.get(objective_id, {})
                if not isinstance(details, dict):
                    raise ValueError("objective-specific metadata entry must be an object")
                stability = details.get("absolute_early_late_mean_difference")
                if stability is not None:
                    if (isinstance(stability, bool)
                            or not isinstance(stability, (int, float))
                            or not math.isfinite(stability) or stability < 0):
                        raise ValueError("nonnegative finite window stability required")
                    candidate_stability[objective_id].append(float(stability))
                effective = details.get("forward_ewma_effective_horizon_ms")
                if effective is not None:
                    if (isinstance(effective, bool)
                            or not isinstance(effective, (int, float))
                            or not math.isfinite(effective) or effective <= 0):
                        raise ValueError("positive finite EWMA effective horizon required")
                    candidate_effective_horizon_ms[objective_id].append(float(effective))
    else:
        grouped: dict[str, list[dict]] = defaultdict(list)
        for row in eligible_rows:
            point = row.get("target")
            if (isinstance(point, bool) or not isinstance(point, (int, float))
                    or not math.isfinite(point)):
                raise ValueError("finite point target required")
            grouped[row["market_id"]].append(row)
        for market_rows in grouped.values():
            market_rows.sort(key=lambda row: (row["decision_ms"], row["row_id"]))
            times = [row["decision_ms"] for row in market_rows]
            for row in market_rows:
                point_records.append({
                    "game_id": row["game_id"],
                    "utc_date": _date(row["decision_ms"]),
                    "midpoint": float(row["features"]["mid"]),
                    "point_target": float(row["target"]),
                })
                start = bisect_left(times, row["decision_ms"] + WINDOW_START_MS)
                stop = bisect_right(times, row["decision_ms"] + WINDOW_END_MS)
                future = [candidate for candidate in market_rows[start:stop]
                          if _date(candidate["decision_ms"]) in train_dates]
                if len(future) < 3:
                    continue
                future_midpoints = [float(candidate["features"]["mid"])
                                    for candidate in future]
                future_offsets = [candidate["decision_ms"] - row["decision_ms"]
                                  for candidate in future]
                ewma_weights = [0.5 ** ((WINDOW_END_MS - offset) / 10_000)
                                for offset in future_offsets]
                weight_sum = math.fsum(ewma_weights)
                forward_ewma = math.fsum(
                    value * weight for value, weight in zip(future_midpoints, ewma_weights)
                ) / weight_sum
                effective_horizon_ms = math.fsum(
                    offset * weight for offset, weight in zip(future_offsets, ewma_weights)
                ) / weight_sum
                record = {
                    "game_id": row["game_id"],
                    "utc_date": _date(row["decision_ms"]),
                    "midpoint": float(row["features"]["mid"]),
                    "window_target": math.fsum(future_midpoints) / len(future_midpoints),
                    "forward_ewma_target": forward_ewma,
                    "median_target": median(future_midpoints),
                    "forward_ewma_effective_horizon_ms": effective_horizon_ms,
                }
                window_records.append(record)
                early = [float(candidate["features"]["mid"]) for candidate in future
                         if candidate["decision_ms"]
                         <= row["decision_ms"] + WINDOW_CENTER_MS]
                late = [float(candidate["features"]["mid"]) for candidate in future
                        if candidate["decision_ms"]
                        > row["decision_ms"] + WINDOW_CENTER_MS]
                if early and late:
                    stability_differences.append(abs(
                        math.fsum(early) / len(early)
                        - math.fsum(late) / len(late)
                    ))
    if source["schema"] == "polymarket_objective_labels_v1":
        if not candidate_records:
            raise ValueError("no objective target coverage on selected Train dates")
        candidate_diagnostics = {}
        for objective_id, records in sorted(candidate_records.items()):
            diagnostic = {
                "coverage_fraction": len(records) / len(eligible_rows),
                **_diagnostics(records, "target"),
            }
            if candidate_stability.get(objective_id):
                values = candidate_stability[objective_id]
                diagnostic["window_half_stability"] = {
                    "comparable_rows": len(values),
                    "mean_absolute_early_late_difference": math.fsum(values) / len(values),
                    "median_absolute_early_late_difference": median(values),
                }
            if candidate_effective_horizon_ms.get(objective_id):
                values = candidate_effective_horizon_ms[objective_id]
                diagnostic["effective_horizon_seconds"] = math.fsum(values) / len(values) / 1000
            candidate_diagnostics[objective_id] = diagnostic
    else:
        if not point_records:
            raise ValueError("no point target coverage on selected Train dates")
        if not window_records:
            raise ValueError("source is too sparse for the proposed future window")
        candidate_diagnostics = {
            "future-midpoint-point-60s-v1": {
                "coverage_fraction": len(point_records) / len(eligible_rows),
                **_diagnostics(point_records, "point_target"),
            },
            "future-midpoint-window-mean-45-75s-v1": {
                "coverage_fraction": len(window_records) / len(eligible_rows),
                **_diagnostics(window_records, "window_target"),
                "window_half_stability": {
                    "comparable_rows": len(stability_differences),
                    "mean_absolute_early_late_difference": (
                        math.fsum(stability_differences) / len(stability_differences)
                        if stability_differences else None
                    ),
                    "median_absolute_early_late_difference": (
                        median(stability_differences) if stability_differences else None
                    ),
                },
            },
            "future-midpoint-window-forward-ewma-45-75s-v1": {
                "coverage_fraction": len(window_records) / len(eligible_rows),
                **_diagnostics(window_records, "forward_ewma_target"),
                "effective_horizon_seconds": math.fsum(
                    record["forward_ewma_effective_horizon_ms"]
                    for record in window_records
                ) / len(window_records) / 1000,
            },
            "future-midpoint-window-median-45-75s-v1": {
                "coverage_fraction": len(window_records) / len(eligible_rows),
                **_diagnostics(window_records, "median_target"),
            },
        }

    result = {
        "schema": SCHEMA,
        "evidence_class": "opened_train_only",
        "train_utc_dates": train_utc_dates,
        "dev_labels_used": False,
        "future_test_used": False,
        "candidate_model_scores_used": False,
        "discovery_policy": discovery_policy(),
        "objective_catalog": objective_catalog(),
        "candidate_diagnostics": candidate_diagnostics,
        "selection": {
            "objective_selected": None,
            "automatic_selection": False,
            "note": "Diagnostics inform a later frozen choice; this audit does not open Dev or select an objective.",
        },
    }
    body = {**result, "audit_sha256": digest(result)}
    return body


def run(source_path: Path, output: Path, *, train_utc_dates: list[str]) -> dict:
    source_path = Path(source_path).resolve()
    if source_path.is_symlink() or not source_path.is_file():
        raise ValueError("regular source materialization required")
    source = json.loads(source_path.read_bytes())
    result = audit(source, train_utc_dates=train_utc_dates)
    result["source_path"] = str(source_path)
    result["source_sha256"] = file_hash(source_path)
    # Bind source identity outside audit_sha256 so the numerical audit remains
    # reusable for an identical materialization at another location.
    result["receipt_sha256"] = digest(result)
    fresh_json(Path(output), result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--train-date", action="append", required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.source, args.output,
                         train_utc_dates=args.train_date), sort_keys=True))


if __name__ == "__main__":
    main()
