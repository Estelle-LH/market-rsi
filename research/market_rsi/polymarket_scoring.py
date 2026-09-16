"""Frozen persistence baseline and runner-owned Polymarket midpoint scorer.

The candidate supplies predictions or explicit failure records.  Candidate
code is never imported.  Missing and failed rows remain in coverage and make
the primary result invalid; they are never imputed or silently intersected
away.  Successful rows may still be reported as a diagnostic paired slice.

The public ``score_polymarket`` entry point consumes a filesystem gate before
opening a Test split.  A Test directory can therefore be opened only once,
including when scoring fails.  The outer runner must keep that directory away
from the researcher and preserve it as an immutable experiment artifact.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median


HORIZON_MS = 60_000
SPLITS = {"dev", "test"}
EVIDENCE_CLASSES = {"synthetic", "diagnostic", "formal_learning", "untouched"}


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value):
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("finite numeric value required")
    return float(value)


def _identifier(value, name):
    if not isinstance(value, str) or not value or len(value) > 256:
        raise ValueError(f"nonempty bounded {name} required")
    return value


def _sha256(value, name):
    if (not isinstance(value, str) or len(value) != 64
            or any(c not in "0123456789abcdef" for c in value)):
        raise ValueError(f"lowercase {name} sha256 required")
    return value


@dataclass(frozen=True)
class PolymarketScoreContract:
    """Predeclared numeric score contract.

    ``split='test'`` requires untouched evidence spanning at least 20 distinct
    complete games.  Games, not calendar days, are the independent units.  Its
    scorer call also requires a fresh exclusive Test gate.
    """

    split: str
    evidence_class: str
    horizon_ms: int = HORIZON_MS
    primary_metric: str = "equal_game_mse"
    prediction_min: float = 0.0
    prediction_max: float = 1.0
    test_commitment_sha256: str | None = None
    objective_id: str = "future-midpoint-point-60s-v1"
    objective_contract_sha256: str | None = None
    target_quantity: str = "first_admitted_midpoint_at_or_after_horizon"
    target_aggregation: str = "point"

    def __post_init__(self):
        if self.split not in SPLITS:
            raise ValueError("split must be dev or test")
        if self.evidence_class not in EVIDENCE_CLASSES:
            raise ValueError("explicit evidence class required")
        if type(self.horizon_ms) is not int or not 0 < self.horizon_ms <= 86_400_000:
            raise ValueError("positive bounded frozen label-availability delay required")
        if self.primary_metric != "equal_game_mse":
            raise ValueError("primary metric is frozen to equal-game MSE")
        lo, hi = _finite(self.prediction_min), _finite(self.prediction_max)
        if lo != 0.0 or hi != 1.0:
            raise ValueError("midpoint prediction bounds are frozen to [0, 1]")
        _identifier(self.objective_id, "objective_id")
        _identifier(self.target_quantity, "target_quantity")
        _identifier(self.target_aggregation, "target_aggregation")
        if self.objective_contract_sha256 is None:
            if (self.objective_id != "future-midpoint-point-60s-v1"
                    or self.horizon_ms != HORIZON_MS
                    or self.target_quantity
                    != "first_admitted_midpoint_at_or_after_horizon"
                    or self.target_aggregation != "point"):
                raise ValueError("custom target requires a frozen objective contract")
        else:
            _sha256(self.objective_contract_sha256, "objective contract")
        if self.split == "test":
            if self.evidence_class != "untouched":
                raise ValueError("Test must be untouched")
            _sha256(self.test_commitment_sha256, "Test commitment")
        elif self.test_commitment_sha256 is not None:
            raise ValueError("Dev must not carry a Test commitment")


def score_contract_from_objective(
    value, *, split, evidence_class, test_commitment_sha256=None
):
    """Bind the scorer to the already-frozen research objective."""
    from objective_contract import label_delay_bounds_ms, validate_objective_contract

    objective = validate_objective_contract(value)
    _, maximum_delay_ms = label_delay_bounds_ms(objective)
    label = objective["objective"]["label"]
    return PolymarketScoreContract(
        split=split,
        evidence_class=evidence_class,
        horizon_ms=maximum_delay_ms,
        test_commitment_sha256=test_commitment_sha256,
        objective_id=objective["objective_id"],
        objective_contract_sha256=objective["objective_contract_sha256"],
        target_quantity=label["quantity"],
        target_aggregation=label["aggregation"],
    )


def validate_evaluation_rows(rows, contract):
    """Return chronologically ordered frozen rows after strict validation."""
    if not isinstance(contract, PolymarketScoreContract) or not isinstance(rows, list) or not rows:
        raise ValueError("nonempty rows and explicit score contract required")
    required = {"row_id", "game_id", "market_id", "decision_ms", "target_ms",
                "midpoint", "target_midpoint"}
    checked, seen, last = [], set(), None
    for raw in rows:
        if not isinstance(raw, dict) or set(raw) != required:
            raise ValueError("exact frozen midpoint row schema required")
        row_id = _identifier(raw["row_id"], "row_id")
        if row_id in seen:
            raise ValueError("duplicate row_id")
        seen.add(row_id)
        game_id = _identifier(raw["game_id"], "game_id")
        market_id = _identifier(raw["market_id"], "market_id")
        decision_ms, target_ms = raw["decision_ms"], raw["target_ms"]
        if (type(decision_ms) is not int or type(target_ms) is not int
                or decision_ms < 0 or target_ms != decision_ms + contract.horizon_ms):
            raise ValueError("target availability differs from frozen score contract")
        order_key = (decision_ms, row_id)
        if last is not None and order_key <= last:
            raise ValueError("rows must be in strict chronological identity order")
        last = order_key
        midpoint = _finite(raw["midpoint"])
        target = _finite(raw["target_midpoint"])
        if not 0.0 <= midpoint <= 1.0 or not 0.0 <= target <= 1.0:
            raise ValueError("midpoints must lie in [0, 1]")
        checked.append({"row_id": row_id, "game_id": game_id, "market_id": market_id,
                        "decision_ms": decision_ms, "target_ms": target_ms,
                        "midpoint": midpoint, "target_midpoint": target,
                        "session": datetime.fromtimestamp(decision_ms / 1000, timezone.utc).date().isoformat()})
    if contract.split == "test":
        from time_series_split_policy import POLICY

        if len({row["game_id"] for row in checked}) < 20:
            raise ValueError("final Test requires at least 20 distinct untouched games")
        if len({row["session"] for row in checked}) < (
                POLICY.final_promotion_minimum_untouched_utc_days):
            raise ValueError("final Test requires at least 20 untouched UTC dates")
    if contract.split == "test" and _digest(rows) != contract.test_commitment_sha256:
        raise ValueError("Test rows do not match their predeclared commitment")
    return checked


def persistence_predictions(rows, contract):
    """The fixed baseline predicts no midpoint change over the frozen target."""
    checked = validate_evaluation_rows(rows, contract)
    return {row["row_id"]: row["midpoint"] for row in checked}


def _candidate_outcomes(submissions, rows):
    if not isinstance(submissions, list):
        raise ValueError("candidate submissions must be a list")
    expected = {row["row_id"] for row in rows}
    seen, outcomes = set(), {}
    for record in submissions:
        if not isinstance(record, dict) or record.get("status") not in {"ok", "failed"}:
            raise ValueError("each candidate record must be ok or failed")
        row_id = _identifier(record.get("row_id"), "candidate row_id")
        if row_id not in expected or row_id in seen:
            raise ValueError("candidate row_id is extra or duplicated")
        seen.add(row_id)
        if record["status"] == "ok":
            if set(record) != {"row_id", "status", "prediction"}:
                raise ValueError("exact successful prediction schema required")
            prediction = _finite(record["prediction"])
            if not 0.0 <= prediction <= 1.0:
                raise ValueError("candidate midpoint prediction outside [0, 1]")
            outcomes[row_id] = {"status": "ok", "prediction": prediction}
        else:
            if set(record) != {"row_id", "status", "failure_code"}:
                raise ValueError("exact failure schema required")
            code = _identifier(record["failure_code"], "failure_code")
            outcomes[row_id] = {"status": "failed", "failure_code": code}
    for row_id in expected - seen:
        outcomes[row_id] = {"status": "missing"}
    return outcomes


def _regression_metrics(predictions, targets):
    if not predictions or len(predictions) != len(targets):
        return None
    n = len(predictions)
    mean_p, mean_y = math.fsum(predictions) / n, math.fsum(targets) / n
    variance = math.fsum((p - mean_p) ** 2 for p in predictions)
    slope = (math.fsum((p - mean_p) * (y - mean_y) for p, y in zip(predictions, targets))
             / variance if variance else None)
    return {
        "rows": n,
        "mse": math.fsum((p - y) ** 2 for p, y in zip(predictions, targets)) / n,
        "mae": math.fsum(abs(p - y) for p, y in zip(predictions, targets)) / n,
        "mean_prediction": mean_p,
        "mean_target": mean_y,
        "calibration_slope": slope,
        "calibration_intercept": mean_y - slope * mean_p if slope is not None else None,
        "calibration_bias": mean_p - mean_y,
    }


def _relative_improvement(baseline_mse, candidate_mse):
    if baseline_mse == 0:
        return None
    return (baseline_mse - candidate_mse) / baseline_mse


def _rmse_probability_bps(mse):
    """Express probability RMSE in basis points for human-readable reports."""
    return math.sqrt(mse) * 10_000 if mse is not None else None


def _score(rows, submissions, contract):
    checked = validate_evaluation_rows(rows, contract)
    baseline = {row["row_id"]: row["midpoint"] for row in checked}
    outcomes = _candidate_outcomes(submissions, checked)
    by_game = {}
    row_audit = []
    for row in checked:
        outcome = outcomes[row["row_id"]]
        row_audit.append({"row_id": row["row_id"], "game_id": row["game_id"],
                          "status": outcome["status"],
                          **({"failure_code": outcome["failure_code"]}
                             if outcome["status"] == "failed" else {})})

    for game_id in sorted({row["game_id"] for row in checked}):
        group = [row for row in checked if row["game_id"] == game_id]
        successful = [row for row in group if outcomes[row["row_id"]]["status"] == "ok"]
        failed = [row for row in group if outcomes[row["row_id"]]["status"] == "failed"]
        missing = [row for row in group if outcomes[row["row_id"]]["status"] == "missing"]
        targets = [row["target_midpoint"] for row in successful]
        baseline_metrics = _regression_metrics([baseline[row["row_id"]] for row in successful], targets)
        candidate_metrics = _regression_metrics(
            [outcomes[row["row_id"]]["prediction"] for row in successful], targets)
        by_game[game_id] = {
            "planned_rows": len(group), "scored_rows": len(successful),
            "failed_rows": len(failed), "missing_rows": len(missing),
            "complete": len(successful) == len(group),
            "paired_success_mask": {"baseline": baseline_metrics, "candidate": candidate_metrics,
                "relative_mse_improvement": (_relative_improvement(baseline_metrics["mse"], candidate_metrics["mse"])
                                             if baseline_metrics is not None else None)},
        }

    planned = len(checked)
    ok = sum(outcome["status"] == "ok" for outcome in outcomes.values())
    failed = sum(outcome["status"] == "failed" for outcome in outcomes.values())
    missing = sum(outcome["status"] == "missing" for outcome in outcomes.values())
    failure_codes = Counter(outcome["failure_code"] for outcome in outcomes.values()
                            if outcome["status"] == "failed")
    complete = ok == planned
    scored_games = [game for game in by_game.values() if game["scored_rows"]]
    paired_baseline = (math.fsum(game["paired_success_mask"]["baseline"]["mse"] for game in scored_games)
                       / len(scored_games) if scored_games else None)
    paired_candidate = (math.fsum(game["paired_success_mask"]["candidate"]["mse"] for game in scored_games)
                        / len(scored_games) if scored_games else None)
    paired_relative = (_relative_improvement(paired_baseline, paired_candidate)
                       if paired_baseline is not None else None)

    full_baseline_by_game = {}
    for game_id in sorted(by_game):
        group = [row for row in checked if row["game_id"] == game_id]
        full_baseline_by_game[game_id] = _regression_metrics(
            [baseline[row["row_id"]] for row in group],
            [row["target_midpoint"] for row in group])["mse"]
    full_baseline = math.fsum(full_baseline_by_game.values()) / len(full_baseline_by_game)

    # Keep each game intact when reporting temporal robustness. A game may
    # cross UTC midnight, so assign it to the UTC date of its first decision
    # instead of splitting its rows between dates.
    game_days = {
        game_id: min(row["session"] for row in checked if row["game_id"] == game_id)
        for game_id in by_game
    }
    by_day = {}
    for day in sorted(set(game_days.values())):
        game_ids = [game_id for game_id in sorted(by_game)
                    if game_days[game_id] == day]
        baseline_day = math.fsum(full_baseline_by_game[game_id]
                                 for game_id in game_ids) / len(game_ids)
        candidate_day = (math.fsum(
            by_game[game_id]["paired_success_mask"]["candidate"]["mse"]
            for game_id in game_ids) / len(game_ids) if complete else None)
        relative_day = (_relative_improvement(baseline_day, candidate_day)
                        if candidate_day is not None else None)
        by_day[day] = {
            "games": len(game_ids),
            "baseline_equal_game_mse": baseline_day,
            "candidate_equal_game_mse": candidate_day,
            "relative_mse_improvement": relative_day,
        }
    comparable_days = [item["relative_mse_improvement"] for item in by_day.values()
                       if item["relative_mse_improvement"] is not None]
    robustness_valid = complete and len(comparable_days) == len(by_day)
    temporal_robustness = {
        "unit": "whole_game_assigned_to_first_decision_utc_day",
        "valid": robustness_valid,
        "days": by_day,
        "comparable_days": len(comparable_days),
        "improved_days": sum(value > 0 for value in comparable_days),
        "non_worse_days": sum(value >= 0 for value in comparable_days),
        "worse_days": sum(value < 0 for value in comparable_days),
        "median_relative_mse_improvement": (
            median(comparable_days) if robustness_valid else None),
        "worst_relative_mse_improvement": (
            min(comparable_days) if robustness_valid else None),
        "selection_note": "diagnostic only; primary remains aggregate equal-game MSE",
    }

    successful_rows = [row for row in checked if outcomes[row["row_id"]]["status"] == "ok"]
    candidate_calibration = _regression_metrics(
        [outcomes[row["row_id"]]["prediction"] for row in successful_rows],
        [row["target_midpoint"] for row in successful_rows])
    baseline_calibration = _regression_metrics(
        [baseline[row["row_id"]] for row in successful_rows],
        [row["target_midpoint"] for row in successful_rows])

    # Short-horizon midpoint targets are often unchanged. Keep the full
    # equal-game MSE as the primary score, but expose its readable scale and a
    # target-conditioned diagnostic so a tiny raw MSE cannot hide an easy task.
    moving_rows = [row for row in checked
                   if abs(row["target_midpoint"] - row["midpoint"]) > 1e-12]
    nonzero_moves = [abs(row["target_midpoint"] - row["midpoint"])
                     for row in moving_rows]
    moving_baseline_mse = (
        math.fsum((row["midpoint"] - row["target_midpoint"]) ** 2
                  for row in moving_rows) / len(moving_rows)
        if moving_rows else None
    )
    moving_candidate_mse = (
        math.fsum((outcomes[row["row_id"]]["prediction"]
                   - row["target_midpoint"]) ** 2 for row in moving_rows)
        / len(moving_rows)
        if complete and moving_rows else None
    )

    invalid_reason = None if complete else "candidate has failed or missing rows; primary score withheld"
    return {
        "schema": "polymarket_midpoint_score_v1",
        "contract": asdict(contract),
        "target": {
            "objective_id": contract.objective_id,
            "objective_contract_sha256": contract.objective_contract_sha256,
            "quantity": contract.target_quantity,
            "aggregation": contract.target_aggregation,
            "label_available_after_ms": contract.horizon_ms,
        },
        "baseline": "persistence: prediction equals decision midpoint",
        "population": {"planned_rows": planned, "games": len(by_game),
                       "utc_days": len({row["session"] for row in checked})},
        "coverage": {"ok_rows": ok, "failed_rows": failed, "missing_rows": missing,
                     "coverage_fraction": ok / planned,
                     "failure_codes": dict(sorted(failure_codes.items()))},
        "primary": {
            "metric": "equal_game_mse", "valid": complete,
            "baseline_all_rows_mse": full_baseline,
            "candidate_all_rows_mse": paired_candidate if complete else None,
            "relative_mse_improvement": paired_relative if complete else None,
            "normalized_skill_score_vs_persistence": (
                paired_relative if complete else None),
            "baseline_rmse_probability_bps": _rmse_probability_bps(full_baseline),
            "candidate_rmse_probability_bps": _rmse_probability_bps(
                paired_candidate if complete else None),
            "invalid_reason": invalid_reason,
        },
        "target_difficulty_diagnostic": {
            "planned_rows": planned,
            "unchanged_rows": planned - len(moving_rows),
            "moving_rows": len(moving_rows),
            "moving_fraction": len(moving_rows) / planned,
            "median_nonzero_absolute_move": (
                median(nonzero_moves) if nonzero_moves else None),
            "median_nonzero_absolute_move_probability_bps": (
                median(nonzero_moves) * 10_000 if nonzero_moves else None),
            "baseline_row_weighted_mse_on_moving_rows": moving_baseline_mse,
            "candidate_row_weighted_mse_on_moving_rows": moving_candidate_mse,
            "relative_mse_improvement_on_moving_rows": (
                _relative_improvement(moving_baseline_mse, moving_candidate_mse)
                if moving_candidate_mse is not None else None),
            "selection_eligible": False,
            "note": "Target-conditioned diagnostic only; primary remains all-row equal-game MSE.",
        },
        "paired_success_diagnostic": {
            "rows": ok, "games_with_success": len(scored_games),
            "baseline_equal_game_mse": paired_baseline,
            "candidate_equal_game_mse": paired_candidate,
            "relative_mse_improvement": paired_relative,
            "same_mask": True,
            "not_promotion_evidence_when_incomplete": not complete,
        },
        "calibration_auxiliary": {
            "valid_for_primary": complete,
            "baseline_on_paired_success": baseline_calibration,
            "candidate_on_paired_success": candidate_calibration,
        },
        "temporal_robustness": temporal_robustness,
        "per_game": by_game,
        "row_outcomes": row_audit,
        "test_policy": {"opened_once": contract.split == "test",
                        "reusable_for_tuning": False if contract.split == "test" else None},
        "promotion": False,
        "claim_boundary": "prediction error only; no fill, fee, PnL, or profitability claim",
    }


def _write_exclusive(path, payload):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags, 0o600)
    try:
        data = (_canonical(payload) + "\n").encode()
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)


def score_polymarket(rows, submissions, contract, *, test_gate_dir=None):
    """Score Dev freely or consume a Test gate exactly once.

    The Test claim is created before row validation and scoring.  Bad input or
    a scorer exception therefore consumes the single Test opening instead of
    permitting a score-targeted retry.
    """
    if not isinstance(contract, PolymarketScoreContract):
        raise ValueError("explicit score contract required")
    if contract.split != "test":
        if test_gate_dir is not None:
            raise ValueError("Dev scoring must not use a Test gate")
        return _score(rows, submissions, contract)

    if test_gate_dir is None:
        raise ValueError("Test scoring requires an exclusive runner-owned gate")
    gate = Path(test_gate_dir)
    gate.mkdir(parents=True, exist_ok=False, mode=0o700)
    claim = {"schema": "polymarket_test_opening_v1", "contract_sha256": _digest(asdict(contract)),
             "rows_sha256": _digest(rows), "submissions_sha256": _digest(submissions),
             "opening_consumed": True, "retry_allowed": False}
    _write_exclusive(gate / "opening.json", claim)
    try:
        result = _score(rows, submissions, contract)
    except Exception as error:
        _write_exclusive(gate / "failure.json", {"schema": "polymarket_test_failure_v1",
                         "error_type": type(error).__name__, "opening_consumed": True})
        raise
    _write_exclusive(gate / "result.json", {"schema": "polymarket_test_result_v1",
                     "result_sha256": _digest(result), "opening_consumed": True})
    return result
