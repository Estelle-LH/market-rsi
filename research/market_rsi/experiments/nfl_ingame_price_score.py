"""Paired, game-equal historical price scoring; no data reads or fit operations.

This sibling does not change the settlement or frozen legacy price scorer.
Production identity/fold/source locks belong to the separately named runner.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from itertools import permutations
import math
import random
import re

B0 = "B0-NoPriceChange"


def _number(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"nonfinite or invalid {field}")
    return float(value)


def _mean(values):
    return math.fsum(values) / len(values)


def _squared_error(label, prediction):
    difference = label - prediction
    return _number(difference * difference, "squared prediction error")


def _correlation(rows, values):
    counts = Counter(row["game_id"] for row in rows)
    weights = [1 / counts[row["game_id"]] for row in rows]
    total = math.fsum(weights)
    x = [row["label"] for row in rows]
    y = [values[row["row_id"]] for row in rows]
    mx = math.fsum(w * a for w, a in zip(weights, x)) / total
    my = math.fsum(w * b for w, b in zip(weights, y)) / total
    vx = math.fsum(w * (a - mx) ** 2 for w, a in zip(weights, x))
    vy = math.fsum(w * (b - my) ** 2 for w, b in zip(weights, y))
    if vx == 0 or vy == 0:
        return None
    return math.fsum(w * (a - mx) * (b - my) for w, a, b in zip(weights, x, y)) / math.sqrt(vx * vy)


def _interval(game_delta, games, field, draws, seed):
    clusters = defaultdict(list)
    for game, delta in game_delta.items():
        clusters[games[game][field]].append(delta)
    keys = sorted(clusters)
    if len(keys) < 2:
        return None
    generator = random.Random(seed)
    samples = []
    for _ in range(draws):
        sampled = [generator.choice(keys) for _ in keys]
        samples.append(_mean([v for key in sampled for v in clusters[key]]))
    samples.sort()
    return [samples[int(0.025 * (draws - 1))], samples[int(0.975 * (draws - 1))]]


def _coverage(rows):
    forecastable = [r for r in rows if r["forecastable"]]
    labelled = [r for r in forecastable if r["label"] is not None]
    return {"population_rows": len(rows), "population_games": len({r["game_id"] for r in rows}),
            "population_dates": len({r["game_date"] for r in rows}),
            "population_weeks": len({r["game_week"] for r in rows}),
            "forecastable_rows": len(forecastable), "scorable_rows": len(labelled),
            "scorable_games": len({r["game_id"] for r in labelled}),
            "scorable_dates": len({r["game_date"] for r in labelled}),
            "scorable_weeks": len({r["game_week"] for r in labelled}),
            "zero_label_games": sorted({r["game_id"] for r in rows} - {r["game_id"] for r in labelled}),
            "reason_counts": {"NO_CURRENT_WINDOW_TRADE": len(rows) - len(forecastable),
                              "NO_FUTURE_WINDOW_LABEL": len(forecastable) - len(labelled)}}


def score(rows, predictions, draws=2000, seed=314159):
    """Require exact common check forecasts, including missing-label anchors.

    Week/date intervals are conditional on the fitted predictors and reused Train;
    they do not adjust for discovery selection or prove execution profitability.
    """
    if not isinstance(draws, int) or isinstance(draws, bool) or draws < 100:
        raise ValueError("at least100 integer bootstrap draws required")
    if not rows or not isinstance(predictions, dict) or B0 not in predictions:
        raise ValueError("population and zero-change baseline required")
    ids, games, date_folds = set(), {}, {}
    for row in rows:
        fields = ("row_id", "game_id", "game_date", "game_week", "fold")
        if any(not isinstance(row.get(k), str) or not row[k] for k in fields):
            raise ValueError("missing population identity")
        if row["row_id"] in ids:
            raise ValueError("duplicate row_id")
        ids.add(row["row_id"])
        if date.fromisoformat(row["game_date"]).isoformat() != row["game_date"]:
            raise ValueError("noncanonical game_date")
        if row["fold"] != "initial_fit" and not re.fullmatch(r"check_[1-9][0-9]*", row["fold"]):
            raise ValueError("invalid fold")
        identity = {k: row[k] for k in ("game_date", "game_week", "fold")}
        if row["game_id"] in games and games[row["game_id"]] != identity:
            raise ValueError("game spans date/week/fold identities")
        games[row["game_id"]] = identity
        if row["game_date"] in date_folds and date_folds[row["game_date"]] != row["fold"]:
            raise ValueError("date spans folds")
        date_folds[row["game_date"]] = row["fold"]
        if not isinstance(row.get("forecastable"), bool) or "label" not in row:
            raise ValueError("invalid forecastability/label")
        if row["forecastable"]:
            current = _number(row.get("p_current"), "p_current")
            if not 0 <= current <= 1:
                raise ValueError("current price out of range")
            if row["label"] is not None:
                target = _number(row["label"], "label")
                if not -1 <= target <= 1 or not -1e-12 <= current + target <= 1 + 1e-12:
                    raise ValueError("invalid price-change label")
        elif row["label"] is not None or row.get("p_current") is not None:
            raise ValueError("unforecastable row has current price/label")
    ordered = [0 if date_folds[d] == "initial_fit" else int(date_folds[d][6:]) for d in sorted(date_folds)]
    if ordered != sorted(ordered):
        raise ValueError("folds are not chronological")
    checks = [r for r in rows if r["fold"].startswith("check_")]
    forecast_ids = {r["row_id"] for r in checks if r["forecastable"]}
    for name, values in predictions.items():
        if not isinstance(name, str) or not name or not isinstance(values, dict) or set(values) != forecast_ids:
            raise ValueError("predictions must cover every forecastable check ID exactly")
        for value in values.values():
            _number(value, "prediction")
    if any(value != 0 for value in predictions[B0].values()):
        raise ValueError("B0 must be zero price change")
    labelled = [r for r in checks if r["forecastable"] and r["label"] is not None]
    if not labelled:
        raise ValueError("no scorable checks")
    grouped = defaultdict(list)
    for row in labelled:
        grouped[row["game_id"]].append(row)
    mse, mae = {}, {}
    for game, observations in grouped.items():
        mse[game] = {n: _mean([_squared_error(r["label"], p[r["row_id"]]) for r in observations]) for n, p in predictions.items()}
        mae[game] = {n: _mean([abs(r["label"] - p[r["row_id"]]) for r in observations]) for n, p in predictions.items()}
    aggregate = {n: _mean([m[n] for m in mse.values()]) for n in predictions}
    pairs = {}
    for left, right in permutations(predictions, 2):
        delta = {g: mse[g][left] - mse[g][right] for g in grouped}
        pairs[f"{left}_minus_{right}"] = {"left": left, "right": right, "equal_game_mse_delta": _mean(list(delta.values())),
            "week_block_95pct_interval": _interval(delta, games, "game_week", draws, seed),
            "date_block_95pct_sensitivity": _interval(delta, games, "game_date", draws, seed),
            "better_game_fraction": sum(v < 0 for v in delta.values()) / len(delta)}
    periods = {}
    for field in ("game_id", "game_date", "game_week", "fold"):
        values = sorted({r[field] for r in checks})
        periods[field] = []
        for value in values:
            subset = [r for r in checks if r[field] == value]
            gs = {r["game_id"] for r in subset if r["forecastable"] and r["label"] is not None}
            metric = {n: _mean([mse[g][n] for g in gs]) if gs else None for n in predictions}
            periods[field].append({field: value, "coverage": _coverage(subset), "equal_game_mse": metric,
                "paired_mse_delta": {key: metric[p["left"]] - metric[p["right"]] if gs else None for key, p in pairs.items()}})
    return {"schema": "market_rsi_trade_price_score_v1", "primary_metric": "equal_game_mse",
            "equal_game_mse": aggregate, "equal_game_mae": {n: _mean([m[n] for m in mae.values()]) for n in predictions},
            "equal_game_weighted_pearson": {n: _correlation(labelled, p) for n, p in predictions.items()},
            "prediction_diagnostics": {n: {"implied_price_out_of_range_forecasts": sum(
                not 0 <= r["p_current"] + p[r["row_id"]] <= 1 for r in checks if r["forecastable"])}
                for n, p in predictions.items()},
            "paired": pairs, "primary_best_model": min(aggregate, key=lambda n: (aggregate[n], n)),
            "coverage": {"full_population": _coverage(rows), "checks": _coverage(checks),
                "per_game": [{"game_id": g, **_coverage([r for r in rows if r["game_id"] == g])} for g in sorted(games)]},
            "per_game": periods["game_id"], "per_date": periods["game_date"],
            "per_week": periods["game_week"], "per_fold": periods["fold"],
            "bootstrap": {"draws": draws, "seed": seed, "estimand": "equal game with sampled cluster multiplicity",
                "scope": "observed authorized clusters, not complete outside-cohort schedule",
                "limitations": "few/partial weeks; conditional fitted-predictor uncertainty; reused Train Discovery, not untouched OOS"},
            "claim": "Historical trade-price prediction only; no executable profit, promotion or researcher-superiority claim."}
