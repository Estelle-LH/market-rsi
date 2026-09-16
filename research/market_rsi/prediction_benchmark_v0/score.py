"""Score complete, paired price-change forecasts without opening any data itself.

The caller owns the one-shot sealed-label gate. This module is a development
scorer, not a substitute for a frozen cohort or an access-control boundary.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from datetime import date as calendar_date
import hashlib
import json
import math
from pathlib import Path
import random
import re


MODEL_NAMES = ("b0", "b1", "b2", "strong", "candidate")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")


def valid_date(value: object) -> bool:
    if not isinstance(value, str) or not DATE_RE.fullmatch(value):
        return False
    try:
        calendar_date.fromisoformat(value)
    except ValueError:
        return False
    return True


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def finite_number(value: str, field: str, *, bound: bool = True) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"invalid {field}") from error
    if not math.isfinite(number) or (bound and not -1 <= number <= 1):
        raise ValueError(f"invalid {field}")
    return number


def read_csv(path: Path, fields: tuple[str, ...]) -> dict[str, dict[str, str]]:
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != list(fields):
            raise ValueError(f"wrong fields in {path.name}")
        rows: dict[str, dict[str, str]] = {}
        for row in reader:
            key = row["row_id"]
            if not key or key in rows or any(value is None for value in row.values()):
                raise ValueError(f"empty or duplicate row in {path.name}")
            rows[key] = row
    return rows


def validate_manifest(manifest: dict) -> dict[str, dict]:
    if manifest.get("schema") != "prediction_benchmark_v0" or manifest.get("horizon_seconds") != 60:
        raise ValueError("unsupported benchmark contract")
    for field in ("source_sha256", "label_rule_sha256", "baseline_sha256", "candidate_sha256"):
        value = manifest.get(field)
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError(f"missing frozen {field}")
    fit_through = manifest.get("fit_through_date")
    if not valid_date(fit_through):
        raise ValueError("missing fit-through date")
    floor = manifest.get("min_label_coverage")
    if isinstance(floor, bool) or not isinstance(floor, (int, float)) or not 0 <= floor <= 1:
        raise ValueError("missing coverage gate")
    rows = manifest.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("missing complete cohort")
    checked: dict[str, dict] = {}
    games: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"row_id", "game_id", "date"}:
            raise ValueError("invalid cohort row")
        key, game, date = row["row_id"], row["game_id"], row["date"]
        if not all(isinstance(value, str) and value for value in (key, game, date)):
            raise ValueError("invalid cohort key")
        if not valid_date(date) or key in checked:
            raise ValueError("duplicate row or invalid date")
        if date <= fit_through:
            raise ValueError("scored game overlaps training dates")
        if game in games and games[game] != date:
            raise ValueError("one game spans multiple dates")
        games[game] = date
        checked[key] = row
    return checked


def date_block_interval(deltas: dict[str, list[float]], *, draws: int, seed: int) -> list[float] | None:
    dates = sorted(deltas)
    if len(dates) < 2:
        return None
    generator = random.Random(seed)
    samples = []
    for _ in range(draws):
        sampled = [generator.choice(dates) for _ in dates]
        values = [value for date in sampled for value in deltas[date]]
        samples.append(sum(values) / len(values))
    samples.sort()
    return [samples[int(0.025 * (draws - 1))], samples[int(0.975 * (draws - 1))]]


def score(manifest_path: Path, labels_path: Path, baselines_path: Path,
          candidate_path: Path, *, draws: int = 10_000, seed: int = 23) -> dict:
    """Return a scorecard; never changes its inputs or creates an output file."""
    if draws < 100:
        raise ValueError("at least 100 bootstrap draws required")
    manifest = json.loads(manifest_path.read_text())
    cohort = validate_manifest(manifest)
    if digest(baselines_path) != manifest["baseline_sha256"]:
        raise ValueError("baseline forecasts changed after freeze")
    if digest(candidate_path) != manifest["candidate_sha256"]:
        raise ValueError("candidate forecasts changed after freeze")
    labels = read_csv(labels_path, ("row_id", "target"))
    baselines = read_csv(baselines_path, ("row_id", "b0", "b1", "b2", "strong"))
    candidates = read_csv(candidate_path, ("row_id", "candidate"))
    for name, rows in (("labels", labels), ("baselines", baselines), ("candidate", candidates)):
        if set(rows) != set(cohort):
            raise ValueError(f"{name} must cover every frozen row exactly once")

    game_rows: dict[str, list[tuple[float, dict[str, float]]]] = defaultdict(list)
    game_dates = {row["game_id"]: row["date"] for row in cohort.values()}
    game_cohort_sizes: dict[str, int] = defaultdict(int)
    for row in cohort.values():
        game_cohort_sizes[row["game_id"]] += 1
    labelled = 0
    for key, row in cohort.items():
        predictions = {
            name: finite_number((candidates if name == "candidate" else baselines)[key][name], name)
            for name in MODEL_NAMES
        }
        if predictions["b0"] != 0:
            raise ValueError("B0 must be the zero-change forecast")
        if labels[key]["target"] == "":
            continue
        target = finite_number(labels[key]["target"], "target")
        labelled += 1
        game_rows[row["game_id"]].append((target, predictions))
    if not labelled or set(game_rows) != set(game_dates):
        raise ValueError("empty label population or a game with no observed labels")

    per_game = []
    date_deltas: dict[str, list[float]] = defaultdict(list)
    for game in sorted(game_dates):
        rows = game_rows[game]
        errors = {
            name: sum((target - prediction[name]) ** 2 for target, prediction in rows) / len(rows)
            for name in MODEL_NAMES
        }
        delta = errors["candidate"] - errors["strong"]
        date_deltas[game_dates[game]].append(delta)
        per_game.append({"game_id": game, "date": game_dates[game], "labelled_rows": len(rows),
                         "cohort_rows": game_cohort_sizes[game],
                         "label_coverage": len(rows) / game_cohort_sizes[game],
                         "mse": errors, "candidate_minus_strong_mse": delta})
    mse = {name: sum(game["mse"][name] for game in per_game) / len(per_game)
           for name in MODEL_NAMES}
    paired = mse["candidate"] - mse["strong"]
    interval = date_block_interval(date_deltas, draws=draws, seed=seed)
    coverage = labelled / len(cohort)
    weighted_pairs = [
        (target, prediction["candidate"], 1 / (len(game_rows) * len(rows)))
        for rows in game_rows.values() for target, prediction in rows
    ]
    mean_target = sum(target * weight for target, _, weight in weighted_pairs)
    mean_prediction = sum(prediction * weight for _, prediction, weight in weighted_pairs)
    variance = sum(weight * (prediction - mean_prediction) ** 2
                   for _, prediction, weight in weighted_pairs)
    slope = (sum(weight * (prediction - mean_prediction) * (target - mean_target)
                 for target, prediction, weight in weighted_pairs) / variance
             if variance > 0 else None)
    min_dates = 20
    gates = {
        "at_least_20_dates": len(date_deltas) >= min_dates,
        "label_coverage": coverage >= manifest["min_label_coverage"],
        "paired_mse_lower": paired < 0,
        "interval_upper_below_zero": interval is not None and interval[1] < 0,
    }
    return {
        "schema": "prediction_benchmark_score_v0",
        "input_sha256": {"manifest": digest(manifest_path), "labels": digest(labels_path),
                         "baselines": digest(baselines_path), "candidate": digest(candidate_path)},
        "target": "home_price_change_60s", "games": len(per_game), "dates": len(date_deltas),
        "cohort_rows": len(cohort), "labelled_rows": labelled, "label_coverage": coverage,
        "equal_game_mse": mse,
        "equal_game_rmse_probability_points": {name: 100 * math.sqrt(value) for name, value in mse.items()},
        "candidate_minus_strong_equal_game_mse": paired,
        "candidate_gain_vs_strong": 1 - mse["candidate"] / mse["strong"] if mse["strong"] else None,
        "paired_date_block_95pct_interval": interval,
        "equal_game_calibration_slope": slope,
        "equal_game_calibration_intercept": mean_target - slope * mean_prediction if slope is not None else None,
        "positive_game_fraction": sum(game["candidate_minus_strong_mse"] < 0 for game in per_game) / len(per_game),
        "positive_date_fraction": sum(sum(values) / len(values) < 0 for values in date_deltas.values()) / len(date_deltas),
        "gates": gates, "beat_benchmark": all(gates.values()),
        "per_date": [{"date": date, "games": len(date_deltas[date]),
                      "candidate_minus_strong_mse": sum(date_deltas[date]) / len(date_deltas[date])}
                     for date in sorted(date_deltas)],
        "per_game": per_game,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--baselines", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(score(args.manifest, args.labels, args.baselines, args.candidate), indent=2))


if __name__ == "__main__":
    main()
