"""Runner-only numeric scoring on complete, identical evaluation rows.

These functions do not authorize an experiment, validate the original collector
or simulate trading. No candidate code is imported. Mid-price prediction error
is NOT executable net PnL. A future outer worker must admit source provenance,
the pre-score contract and the permitted evaluation phase before calling this
module on real research submissions. There is deliberately no live CLI.
"""
from __future__ import annotations

import json
import hashlib
import math
import random
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from prediction_stream import finite, fingerprint, validate_rows


TARGETS = {"mid_change", "buy_yes_gross_price_change", "buy_no_gross_price_change"}


def utc_date(ms):
    if type(ms) is not int or ms < 0:
        raise ValueError("integer nonnegative timestamp required")
    return datetime.fromtimestamp(ms / 1000, timezone.utc).date().isoformat()


@dataclass(frozen=True)
class NumericScoreSpec:
    target: str
    prediction_min: float
    prediction_max: float
    sessions: tuple[str, ...]
    evidence_class: str
    bootstrap_seed: int
    bootstrap_replicates: int
    block_sessions: int

    def __post_init__(self):
        if self.target not in TARGETS:
            raise ValueError("unsupported numeric target; no inferred settlement labels")
        lo, hi = finite(self.prediction_min), finite(self.prediction_max)
        if not -1 <= lo < hi <= 1:
            raise ValueError("frozen dollar-per-contract prediction bounds required")
        if (not isinstance(self.sessions, tuple) or not self.sessions
                or tuple(sorted(set(self.sessions))) != self.sessions
                or any(date.fromisoformat(s).isoformat() != s for s in self.sessions)):
            raise ValueError("unique chronological UTC sessions required")
        if self.evidence_class not in {"synthetic", "diagnostic", "untouched"}:
            raise ValueError("explicit inspected/untouched evidence class required")
        if (type(self.bootstrap_seed) is not int or self.bootstrap_seed < 0
                or type(self.bootstrap_replicates) is not int or not 100 <= self.bootstrap_replicates <= 10000
                or type(self.block_sessions) is not int or not 1 <= self.block_sessions <= len(self.sessions)):
            raise ValueError("invalid frozen block-bootstrap parameters")


def ranks(values):
    ordered = sorted(range(len(values)), key=values.__getitem__)
    result, i = [0.0] * len(values), 0
    while i < len(values):
        j = i + 1
        while j < len(values) and values[ordered[j]] == values[ordered[i]]:
            j += 1
        for index in ordered[i:j]:
            result[index] = (i + 1 + j) / 2
        i = j
    return result


def correlation(x, y):
    if len(x) != len(y) or not x:
        raise ValueError("nonempty paired vectors required")
    mx, my = math.fsum(x) / len(x), math.fsum(y) / len(y)
    xx, yy = [v - mx for v in x], [v - my for v in y]
    vx, vy = math.fsum(v * v for v in xx), math.fsum(v * v for v in yy)
    if vx == 0 or vy == 0:
        return None  # A constant forecast/target does not have a zero IC.
    return max(-1.0, min(1.0, math.fsum(a * b for a, b in zip(xx, yy)) / math.sqrt(vx * vy)))


def numeric_metrics(prediction, target):
    if not prediction or len(prediction) != len(target):
        raise ValueError("complete paired predictions required")
    p, y = [finite(v) for v in prediction], [finite(v) for v in target]
    n = len(p)
    mp, my = math.fsum(p) / n, math.fsum(y) / n
    variance = math.fsum((v - mp) ** 2 for v in p)
    slope = math.fsum((a - mp) * (b - my) for a, b in zip(p, y)) / variance if variance else None
    return {"rows": n, "mse": math.fsum((a - b) ** 2 for a, b in zip(p, y)) / n,
            "mae": math.fsum(abs(a - b) for a, b in zip(p, y)) / n,
            "pearson_ic": correlation(p, y), "rank_ic": correlation(ranks(p), ranks(y)),
            "calibration_slope": slope, "calibration_intercept": my - slope * mp if slope is not None else None,
            "mean_prediction": mp, "mean_target": my}


def read_predictions(directory, *, train, evaluation, feature_names, candidate_sha256,
                     prediction_min, prediction_max, max_bytes=64 * 1024 * 1024):
    """Independent read-back of PredictionJournal, not caller-supplied scores."""
    validate_rows(train, evaluation, feature_names)
    if (not isinstance(candidate_sha256, str) or len(candidate_sha256) != 64
            or any(c not in "0123456789abcdef" for c in candidate_sha256)):
        raise ValueError("exact candidate source hash required")
    lo, hi = finite(prediction_min), finite(prediction_max)
    if lo >= hi or type(max_bytes) is not int or max_bytes <= 0:
        raise ValueError("invalid output bounds")
    directory = Path(directory)
    names = ("claim.json", "predictions.jsonl", "complete.json")
    for name in names:
        p = directory / name
        if p.is_symlink() or not p.is_file() or p.stat().st_size > max_bytes:
            raise ValueError("missing, symlinked or oversized prediction evidence")
    claim = json.loads((directory / "claim.json").read_text())
    expected = {"train_sha256": fingerprint(train), "evaluation_sha256": fingerprint(evaluation),
                "candidate_sha256": candidate_sha256, "expected_predictions": len(evaluation),
                "scoring_authorized": False}
    if fingerprint(claim) != fingerprint(expected):
        raise ValueError("prediction evidence bound to different inputs/code")
    raw = (directory / "predictions.jsonl").read_bytes()
    if len(raw) > max_bytes or not raw.endswith(b"\n"):
        raise ValueError("oversized or unterminated prediction journal")
    records = [json.loads(line) for line in raw.splitlines()]
    if len(records) != len(evaluation):
        raise ValueError("missing or extra predictions; never silently intersect masks")
    predictions, previous = {}, "0" * 64
    keys = {"sequence", "row_id", "prediction", "feature_row_sha256", "previous", "hash"}
    for i, (record, feature) in enumerate(zip(records, evaluation, strict=True)):
        if (set(record) != keys or type(record["sequence"]) is not int or record["sequence"] != i
                or record["row_id"] != feature["row_id"] or record["previous"] != previous
                or record["feature_row_sha256"] != fingerprint(feature)
                or record["hash"] != fingerprint({k: v for k, v in record.items() if k != "hash"})
                or not lo <= finite(record["prediction"]) <= hi):
            raise ValueError("invalid prediction value, identity, order or chain")
        predictions[record["row_id"]] = record["prediction"]
        previous = record["hash"]
    complete = json.loads((directory / "complete.json").read_text())
    expected_complete = {"predictions": len(evaluation), "last_prediction_hash": previous,
                         "predictions_sha256": hashlib.sha256(raw).hexdigest(), "scored": False}
    if fingerprint(complete) != fingerprint(expected_complete):
        raise ValueError("prediction completion receipt mismatch")
    return predictions


def numeric_rows(materialized, spec):
    """Validate numeric labels against actual stored price endpoints.

    This detects inconsistent artifacts; it cannot prove the raw data clock or
    that the endpoints really were the first observed quotes after latency.
    Those source/materializer claims remain independent outer admission gates.
    """
    if not materialized:
        raise ValueError("nonempty frozen evaluation required")
    rows, seen, markets, last = [], set(), {}, -1
    for r in materialized:
        for key in ("row_id", "game_id", "market_id"):
            if not isinstance(r[key], str) or not r[key]:
                raise ValueError("explicit row/game/market identities required")
        if r["row_id"] in seen or r["decision_ms"] < last:
            raise ValueError("duplicate or reordered evaluation rows")
        seen.add(r["row_id"])
        last = r["decision_ms"]
        session = utc_date(last)
        if session not in spec.sessions:
            raise ValueError("row outside frozen sessions")
        if markets.setdefault(r["market_id"], r["game_id"]) != r["game_id"]:
            raise ValueError("market relabelled as another game")
        for key in ("feature_available_ms", "entry_ms", "label_end_ms", "label_available_ms"):
            utc_date(r[key])
        if not (r["feature_available_ms"] <= last <= r["entry_ms"] < r["label_end_ms"] == r["label_available_ms"]):
            raise ValueError("invalid feature/entry/label chronology")
        ep, feat = r["runner_endpoints"], r["features"]
        for side in ("entry", "exit"):
            b, a = ep[side + "_bid_1e4"], ep[side + "_ask_1e4"]
            if type(b) is not int or type(a) is not int or not 0 < b <= a < 10000:
                raise ValueError("invalid numeric price endpoint")
            for bookside in ("bid", "ask"):
                size = ep[side + "_" + bookside + "_size_1e2"]
                if type(size) is not int or size <= 0:
                    raise ValueError("missing positive endpoint depth")
        bid, ask, mid = finite(feat["bid"]), finite(feat["ask"]), finite(feat["mid"])
        if not 0 < bid <= ask < 1 or abs(mid - (bid + ask) / 2) > 1e-12:
            raise ValueError("invalid decision quote midpoint")
        expected = {"mid_change": (ep["exit_bid_1e4"] + ep["exit_ask_1e4"]) / 20000 - mid,
                    "buy_yes_gross_price_change": (ep["exit_bid_1e4"] - ep["entry_ask_1e4"]) / 10000,
                    "buy_no_gross_price_change": (ep["entry_bid_1e4"] - ep["exit_ask_1e4"]) / 10000}
        if set(r["labels"]) != TARGETS or any(abs(finite(r["labels"][k]) - v) > 1e-12 for k, v in expected.items()):
            raise ValueError("numeric label does not match declared quote endpoints")
        rows.append({"row_id": r["row_id"], "game_id": r["game_id"], "market_id": r["market_id"],
                     "session": session, "target": expected[spec.target]})
    if {r["session"] for r in rows} != set(spec.sessions):
        raise ValueError("missing session coverage; do not impute an empty date")
    return rows


def circular_interval(values, block, replicates, seed):
    rng, n, estimates = random.Random(seed), len(values), []
    for _ in range(replicates):
        sampled = []
        while len(sampled) < n:
            start = rng.randrange(n)
            sampled.extend(values[(start + j) % n] for j in range(block))
        estimates.append(math.fsum(sampled[:n]) / n)
    estimates.sort()
    return [estimates[math.floor(0.025 * (replicates - 1))], estimates[math.ceil(0.975 * (replicates - 1))]]


def score_pair(materialized, baseline, candidate, spec):
    if not isinstance(spec, NumericScoreSpec):
        raise ValueError("explicit frozen numeric score spec required")
    rows = numeric_rows(materialized, spec)
    ids = {r["row_id"] for r in rows}
    for predictions in (baseline, candidate):
        if not isinstance(predictions, dict) or set(predictions) != ids:
            raise ValueError("predictions must cover identical full frozen rows")
        if any(not spec.prediction_min <= finite(p) <= spec.prediction_max for p in predictions.values()):
            raise ValueError("prediction outside frozen limits")

    def paired(group):
        y = [r["target"] for r in group]
        a = numeric_metrics([baseline[r["row_id"]] for r in group], y)
        b = numeric_metrics([candidate[r["row_id"]] for r in group], y)
        delta = {"mse": b["mse"] - a["mse"], "mae": b["mae"] - a["mae"]}
        for metric in ("pearson_ic", "rank_ic"):
            delta[metric] = b[metric] - a[metric] if a[metric] is not None and b[metric] is not None else None
        return {"baseline": a, "candidate": b, "candidate_minus_baseline": delta}

    per_session = {s: paired([r for r in rows if r["session"] == s]) for s in spec.sessions}
    games = sorted({r["game_id"] for r in rows})
    per_game = {g: paired([r for r in rows if r["game_id"] == g]) for g in games}
    daily = [v["candidate_minus_baseline"]["mse"] for v in per_session.values()]
    gamewise = [v["candidate_minus_baseline"]["mse"] for v in per_game.values()]
    enough = len(spec.sessions) >= 20 and spec.evidence_class == "untouched"
    interval = circular_interval(daily, spec.block_sessions, spec.bootstrap_replicates, spec.bootstrap_seed) if enough else None
    return {"row_weighted": paired(rows), "per_session": per_session, "per_game": per_game,
        "equal_session_delta_mse": math.fsum(daily) / len(daily),
        "equal_game_delta_mse": math.fsum(gamewise) / len(gamewise),
        "fraction_sessions_lower_mse": sum(v < 0 for v in daily) / len(daily),
        "fraction_games_lower_mse": sum(v < 0 for v in gamewise) / len(gamewise),
        "frozen_row_ids_sha256": fingerprint([r["row_id"] for r in rows]),
        "missing_predictions": {"baseline": 0, "candidate": 0},
        "interval": {"equal_session_delta_mse_95pct_circular_block": interval,
            "sessions": len(spec.sessions), "block_sessions": spec.block_sessions,
            "replicates": spec.bootstrap_replicates, "seed": spec.bootstrap_seed,
            "unavailable_reason": None if enough else "requires at least 20 untouched sessions"},
        "target": spec.target, "delta_convention": "candidate minus baseline; negative MSE/MAE is better",
        "net_pnl": None, "scientific_admission": False, "promotion": False,
        "claim_boundary": "Numeric arithmetic only; data/source/phase admission and trading simulation remain separate"}
