#!/usr/bin/env python3
"""Historical in-game win-probability diagnostic on opened 2025 NFL Train.

The task is deliberately separate from the pregame settlement task.  One
pre-play checkpoint is selected per game without using a score, market price,
or outcome.  On the exact same chronological check rows it compares the raw
market probability, a fixed logistic model using market history, and the same
logistic model with contemporaneous game-state/PBP fields added.

The PBP source has historical event wall clocks but no provider-publish or
local-receive timestamps.  Results therefore diagnose historical incremental
information only; they cannot establish a live lead, executable quote, PnL,
promotion result, or untouched OOS evidence.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
from typing import Iterable, Sequence
import warnings

import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from minimal_prediction_loop import probability_contract, proper_scoring
from experiments import nfl_settlement_probability_train_diagnostic as settlement
from minimal_prediction_loop.probability_contract import (
    DEFAULT_PROBABILITY_POLICY,
    validate_probability,
    validate_probability_rows,
    validate_train_evaluation_rows,
)
from minimal_prediction_loop.proper_scoring import bounded_log_loss, brier_loss


SOURCE_ROOT = settlement.SOURCE_ROOT
PERSISTENT_ARTIFACT_ROOT = settlement.PERSISTENT_ARTIFACT_ROOT
EXPECTED_MANIFEST_SHA256 = settlement.EXPECTED_MANIFEST_SHA256
EXPECTED_COHORT_SHA256 = settlement.EXPECTED_COHORT_SHA256
EXPECTED_EVENTS = settlement.EXPECTED_EVENTS
EXPECTED_DATES = settlement.EXPECTED_DATES
MAX_TRADE_STALENESS_SECONDS = 300
CHECKPOINT_QUARTER = 3
CHECKPOINT_CLOCK_AT_MOST_SECONDS = 8 * 60
SEED = 23
BOOTSTRAP_SEED = 20260929
BOOTSTRAP_REPLICATES = 10_000

EXTRACTOR = Path(__file__).with_name("extract_nfl_ingame_checkpoint.R")
MARKET_FEATURE_NAMES = ("market_logit",)
STATE_FEATURE_NAMES = (
    "home_score_diff_pre",
    "regulation_seconds_remaining",
    "possession_is_home",
    "down_1",
    "down_2",
    "down_3",
    "down_4",
    "yards_to_go",
    "home_possession_field_advantage",
)
MODEL_SPEC = {
    "class": "sklearn.linear_model.LogisticRegression",
    "penalty": "l2",
    "C": 1.0,
    "solver": "lbfgs",
    "fit_intercept": True,
    "max_iter": 1000,
    "tol": 1e-10,
}
MARKET_CONTINUOUS_INDICES = (0,)
COMBINED_CONTINUOUS_INDICES = (0, 1, 2, 8, 9)


@dataclass(frozen=True)
class InGameRow:
    game_id: str
    game_date: str
    game_week: str
    trusted: dict
    market_features: tuple[float, ...]
    state_features: tuple[float, ...]
    source_receipt: dict

    @property
    def key(self) -> tuple[str, str, int]:
        return (
            self.trusted["event_id"],
            self.trusted["market_id"],
            self.trusted["cutoff_ms"],
        )


def _atomic_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _validate_roots(source_root: Path, output: Path, *, allow_test_paths: bool) -> None:
    source_root, output = source_root.resolve(), output.resolve()
    if output.exists():
        raise FileExistsError("output already exists; use a fresh diagnostic ID")
    if source_root == output or source_root in output.parents:
        raise ValueError("output cannot be inside immutable source root")
    if not allow_test_paths:
        if source_root != SOURCE_ROOT.resolve():
            raise ValueError("runner is bound to the exact opened 2025 Train root")
        try:
            output.relative_to(PERSISTENT_ARTIFACT_ROOT.resolve())
        except ValueError as error:
            raise ValueError("output must be in persistent local MarketRSI artifacts") from error
        lowered = str(output).lower()
        if any(marker in lowered for marker in (
                "/tmp/", "/private/var/", "icloud", "mobile documents",
                "dropbox", "google drive")):
            raise ValueError("temporary or cloud-looking output is forbidden")


def _validate_source(source_root: Path, *, expected_events: int,
                     expected_dates: int, allow_test_paths: bool) -> list[dict[str, str]]:
    if not allow_test_paths:
        if settlement._sha256(source_root / "manifest.json") != EXPECTED_MANIFEST_SHA256:
            raise ValueError("frozen source manifest hash changed")
        if settlement._sha256(source_root / "cohort.csv") != EXPECTED_COHORT_SHA256:
            raise ValueError("frozen cohort hash changed")
    manifest = settlement._strict_json(source_root / "manifest.json")
    if (not isinstance(manifest, dict)
            or manifest.get("schema") != "nfl_2025_train_fresh_source_audit_v1"
            or manifest.get("complete") is not True
            or manifest.get("source_games") != expected_events
            or manifest.get("train_distinct_dates") != expected_dates
            or manifest.get("dev_final_opened") is not False
            or manifest.get("model_fits") != 0
            or manifest.get("provider_cost_usd") != "0"):
        raise ValueError("source completeness or protected-data boundary failed")
    cohort = settlement._read_cohort(source_root / "cohort.csv")
    if len(cohort) != expected_events:
        raise ValueError("source denominator differs from frozen event count")
    return cohort


def _validate_pbp_receipts(source_root: Path, cohort: Sequence[dict]) -> list[dict]:
    receipts = []
    for item in cohort:
        game_id = item["game_id"]
        receipt_path = source_root / "pbp" / f"{game_id}.json"
        rds_path = source_root / "pbp" / f"{game_id}.rds"
        receipt = settlement._strict_json(receipt_path)
        if (not isinstance(receipt, dict)
                or receipt.get("game_id") != game_id
                or receipt.get("game_date") != item["game_date"]
                or receipt.get("event_slug") != item["event_slug"]
                or receipt.get("bytes") != rds_path.stat().st_size
                or receipt.get("sha256") != settlement._sha256(rds_path)):
            raise ValueError(f"raw PBP receipt changed: {game_id}")
        receipts.append({
            "game_id": game_id,
            "pbp_receipt_sha256": settlement._sha256(receipt_path),
            "pbp_rds_sha256": receipt["sha256"],
            "pbp_bytes": receipt["bytes"],
        })
    return receipts


def _extract_state_rows(source_root: Path, path: Path) -> dict[str, dict[str, str]]:
    if not EXTRACTOR.is_file():
        raise ValueError("frozen R checkpoint extractor is missing")
    subprocess.run(
        ["Rscript", str(EXTRACTOR), str(source_root), str(path)],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
    if len(rows) != EXPECTED_EVENTS or len({row.get("game_id") for row in rows}) != len(rows):
        raise ValueError("checkpoint extractor did not preserve the 195-game denominator")
    return {row["game_id"]: row for row in rows}


def _finite_field(row: dict[str, str], name: str) -> float:
    try:
        value = float(row[name])
    except (KeyError, TypeError, ValueError) as error:
        raise settlement.EventExclusion(
            "invalid_checkpoint_state", f"{name} is missing or nonnumeric"
        ) from error
    if not math.isfinite(value):
        raise settlement.EventExclusion("invalid_checkpoint_state", f"{name} is nonfinite")
    return value


def _state_feature_vector(state: dict[str, str]) -> tuple[float, ...]:
    down_value = _finite_field(state, "down")
    down = int(down_value)
    if down_value != down or down not in (1, 2, 3, 4):
        raise settlement.EventExclusion(
            "invalid_checkpoint_state", "down must be exactly one of 1,2,3,4"
        )
    score = _finite_field(state, "home_score_diff_pre")
    seconds = _finite_field(state, "regulation_seconds_remaining")
    possession = _finite_field(state, "possession_is_home")
    yards_to_go = _finite_field(state, "yards_to_go")
    field = _finite_field(state, "home_possession_field_advantage")
    if (possession not in (0.0, 1.0) or not 900 <= seconds <= 1380
            or not -100 <= score <= 100 or not 0 <= yards_to_go <= 100
            or not -1 <= field <= 1):
        raise settlement.EventExclusion(
            "invalid_checkpoint_state", "state feature is outside frozen physical bounds"
        )
    values = (
        score,
        seconds,
        possession,
        *(1.0 if down == value else 0.0 for value in (1, 2, 3, 4)),
        yards_to_go,
        field,
    )
    if len(values) != len(STATE_FEATURE_NAMES):
        raise RuntimeError("state feature vector differs from frozen whitelist")
    return values


def _market_snapshot(trades: Sequence[dict], cutoff_s: int) -> tuple[float, int]:
    eligible = [row for row in trades if row["timestamp"] <= cutoff_s]
    if not eligible:
        raise settlement.EventExclusion(
            "no_trade_at_or_before_checkpoint", "no strictly preceding market fill"
        )
    latest_second = max(row["timestamp"] for row in eligible)
    latest = [row for row in eligible if row["timestamp"] == latest_second]
    probability, _ = settlement._weighted_probability(latest)
    try:
        probability = validate_probability(
            probability, DEFAULT_PROBABILITY_POLICY, "market_probability"
        )
    except ValueError as error:
        raise settlement.EventExclusion("invalid_endpoint_baseline", str(error)) from error
    return probability, latest_second * 1000


def _staleness_seconds(decision_time: datetime, latest_trade_ms: int) -> float:
    value = decision_time.timestamp() - latest_trade_ms / 1000
    if value < 0:
        raise settlement.EventExclusion(
            "post_checkpoint_trade", "market snapshot follows the checkpoint"
        )
    if value > MAX_TRADE_STALENESS_SECONDS:
        raise settlement.EventExclusion(
            "market_trade_too_stale", f"latest preceding trade is {value}s old"
        )
    return value


def _load_dynamic_market(source_root: Path, cohort: dict,
                         state: dict[str, str]) -> InGameRow:
    game_id = cohort["game_id"]
    if state.get("status") != "eligible":
        raise settlement.EventExclusion(
            state.get("status") or "invalid_checkpoint_state",
            state.get("detail") or "fixed checkpoint unavailable",
        )

    # Reuse the reviewed source identity, outcome-availability, orientation,
    # trade-receipt, and protected-boundary checks.  Its pregame features are
    # discarded; this task rebuilds all market features at the in-game clock.
    base = settlement._materialize_event(source_root, cohort)
    meta_path = source_root / "catalog" / f"{game_id}.json"
    raw_path = source_root / "catalog" / f"{game_id}.raw.json.gz"
    meta = settlement._strict_json(meta_path)
    compressed = raw_path.read_bytes()
    if settlement._sha256(raw_path) != meta.get("stored_sha256"):
        raise ValueError("raw catalog stored hash mismatch")
    raw = gzip.decompress(compressed)
    if hashlib.sha256(raw).hexdigest() != meta.get("raw_sha256"):
        raise ValueError("raw catalog source hash mismatch")
    event = json.loads(raw)
    market = settlement._selected_market(event, meta)
    orientation = settlement.orient_market(game_id, market, meta["tokens"])
    normalized_state_home = settlement.GAME_TEAM_ALIASES.get(
        state.get("home_team", ""), state.get("home_team", "")
    )
    normalized_state_away = settlement.GAME_TEAM_ALIASES.get(
        state.get("away_team", ""), state.get("away_team", "")
    )
    if (normalized_state_home != orientation["home_team"]
            or normalized_state_away != orientation["away_team"]):
        raise settlement.EventExclusion(
            "ambiguous_orientation", "PBP and market home/away identity differ"
        )
    trade_root = source_root / "trades" / game_id
    trade_path = trade_root / "trade_window.csv"
    trade_manifest = settlement._strict_json(trade_root / "manifest.json")
    if (not isinstance(trade_manifest, dict)
            or trade_manifest.get("complete") is not True
            or trade_manifest.get("dev_final_opened") is not False
            or trade_manifest.get("trade_window_sha256") != settlement._sha256(trade_path)):
        raise ValueError("trade manifest boundary/hash check failed")
    trades = settlement._load_trades(
        trade_path, meta, orientation, cohort["event_slug"]
    )

    decision_time = settlement._utc(state["decision_time_utc"], "PBP checkpoint")
    # Trade stamps have only integer-second resolution.  Excluding the event's
    # integer second prevents a print later in that same second from leaking.
    market_cutoff_s = math.floor(decision_time.timestamp()) - 1
    market_probability, latest_trade_ms = _market_snapshot(trades, market_cutoff_s)
    market_features = (math.log(market_probability / (1.0 - market_probability)),)
    staleness_seconds = _staleness_seconds(decision_time, latest_trade_ms)
    state_features = _state_feature_vector(state)
    cutoff_ms = math.floor(decision_time.timestamp() * 1000)
    trusted = dict(base.trusted)
    trusted.update({
        "cutoff_ms": cutoff_ms,
        # This is a historical event-clock boundary, not proof of live receipt.
        "feature_available_ms": cutoff_ms,
        "market_probability": market_probability,
    })
    validate_probability_rows([trusted])
    return InGameRow(
        game_id=game_id,
        game_date=cohort["game_date"],
        game_week=game_id.split("_")[1],
        trusted=trusted,
        market_features=market_features,
        state_features=state_features,
        source_receipt={
            **base.source_receipt,
            "pbp_play_id": state["play_id"],
            "pbp_order_sequence": state["order_sequence"],
            "pbp_checkpoint_event_time_utc": state["decision_time_utc"],
            "market_feature_cutoff_epoch_s": market_cutoff_s,
            "latest_trade_epoch_ms": latest_trade_ms,
            "market_staleness_seconds": staleness_seconds,
            "availability_class": "historical_event_clock_only",
        },
    )


def _probabilities(model: LogisticRegression, matrix: np.ndarray) -> list[float]:
    return [
        validate_probability(float(value), DEFAULT_PROBABILITY_POLICY, "model probability")
        for value in model.predict_proba(matrix)[:, 1]
    ]


def _scale_continuous(fit: np.ndarray, check: np.ndarray,
                      indices: Sequence[int]) -> tuple[np.ndarray, np.ndarray]:
    if fit.ndim != 2 or check.ndim != 2 or fit.shape[1] != check.shape[1]:
        raise ValueError("fit/check matrices must have the same feature width")
    selected = tuple(indices)
    if len(set(selected)) != len(selected) or any(
            index < 0 or index >= fit.shape[1] for index in selected):
        raise ValueError("continuous feature indices are invalid")
    fit_result, check_result = fit.copy(), check.copy()
    scaler = StandardScaler().fit(fit[:, selected])
    fit_result[:, selected] = scaler.transform(fit[:, selected])
    check_result[:, selected] = scaler.transform(check[:, selected])
    return fit_result, check_result


def _fit_logistic(matrix: np.ndarray, outcomes: np.ndarray) -> LogisticRegression:
    model = LogisticRegression(**{
        key: value for key, value in MODEL_SPEC.items() if key != "class"
    })
    with warnings.catch_warnings():
        warnings.simplefilter("error", ConvergenceWarning)
        model.fit(matrix, outcomes)
    if any(int(value) >= MODEL_SPEC["max_iter"] for value in model.n_iter_):
        raise RuntimeError("logistic optimizer reached the iteration ceiling")
    return model


def _fit_and_predict(rows: Sequence[InGameRow], folds: Sequence[dict]) -> tuple[list[dict], list[dict]]:
    by_date: dict[str, list[InGameRow]] = defaultdict(list)
    for row in rows:
        by_date[row.game_date].append(row)
    predictions: list[dict] = []
    fold_reports = []
    for fold in folds:
        check_rows = sorted(
            [row for date in fold["check_dates"] for row in by_date.get(date, [])],
            key=lambda row: row.key,
        )
        first_check_cutoff = min(row.trusted["cutoff_ms"] for row in check_rows)
        fit_candidates = [
            row for date in fold["fit_dates"] for row in by_date.get(date, [])
        ]
        fit_rows = sorted(
            [row for row in fit_candidates
             if row.trusted["outcome_available_ms"] < first_check_cutoff],
            key=lambda row: row.key,
        )
        fit_label_unavailable = sorted(
            row.game_id for row in fit_candidates
            if row.trusted["outcome_available_ms"] >= first_check_cutoff
        )
        if not fit_rows or len({row.trusted["outcome"] for row in fit_rows}) != 2:
            raise ValueError(f"fold {fold['fold']} fit rows lack both outcome classes")
        validate_train_evaluation_rows(
            [row.trusted for row in fit_rows], [row.trusted for row in check_rows]
        )
        y_fit = np.asarray([row.trusted["outcome"] for row in fit_rows], dtype=np.int64)
        y_check = [row.trusted["outcome"] for row in check_rows]
        market_x_fit = np.asarray([row.market_features for row in fit_rows], dtype=float)
        market_x_check = np.asarray([row.market_features for row in check_rows], dtype=float)
        state_x_fit = np.asarray([
            row.market_features + row.state_features for row in fit_rows
        ], dtype=float)
        state_x_check = np.asarray([
            row.market_features + row.state_features for row in check_rows
        ], dtype=float)
        market_fit, market_check = _scale_continuous(
            market_x_fit, market_x_check, MARKET_CONTINUOUS_INDICES
        )
        state_fit, state_check = _scale_continuous(
            state_x_fit, state_x_check, COMBINED_CONTINUOUS_INDICES
        )
        market_model = _fit_logistic(market_fit, y_fit)
        state_model = _fit_logistic(state_fit, y_fit)
        raw_market = [row.trusted["market_probability"] for row in check_rows]
        market_values = _probabilities(
            market_model, market_check
        )
        state_values = _probabilities(state_model, state_check)
        arm_metrics = {
            "raw_market": settlement._simple_metrics(y_check, raw_market),
            "market_model": settlement._simple_metrics(y_check, market_values),
            "market_plus_state_model": settlement._simple_metrics(y_check, state_values),
        }
        fold_reports.append({
            "fold": fold["fold"],
            "fit_dates": fold["fit_dates"],
            "check_dates": fold["check_dates"],
            "fit_events": len(fit_rows),
            "check_events": len(check_rows),
            "fit_label_unavailable_game_ids": fit_label_unavailable,
            "fit_label_unavailable_game_ids_sha256": settlement._digest(
                fit_label_unavailable
            ),
            "arms": arm_metrics,
            "state_minus_market_model_brier": (
                arm_metrics["market_plus_state_model"]["brier"]
                - arm_metrics["market_model"]["brier"]
            ),
            "same_rows_labels_trainer_and_budget": True,
        })
        for row, market_value, state_value in zip(
                check_rows, market_values, state_values, strict=True):
            predictions.append({
                "fold": fold["fold"],
                "row": row,
                "raw_market": row.trusted["market_probability"],
                "market_model": market_value,
                "market_plus_state_model": state_value,
            })
    keys = [item["row"].key for item in predictions]
    if len(keys) != len(set(keys)):
        raise ValueError("an event appears in more than one check fold")
    return predictions, fold_reports


def _loss(outcome: int, probability: float, name: str) -> float:
    if name == "brier":
        return brier_loss(probability, outcome)
    if name == "log_loss":
        return bounded_log_loss(probability, outcome)
    raise ValueError("unknown loss")


def _paired_records(predictions: Sequence[dict]) -> list[dict]:
    records = []
    for item in predictions:
        row = item["row"]
        record = {
            "game_id": row.game_id,
            "game_date": row.game_date,
            "game_week": row.game_week,
            "outcome": row.trusted["outcome"],
        }
        for loss_name in ("brier", "log_loss"):
            values = {
                arm: _loss(row.trusted["outcome"], item[arm], loss_name)
                for arm in ("raw_market", "market_model", "market_plus_state_model")
            }
            record.update({f"{arm}_{loss_name}": value for arm, value in values.items()})
            record[f"state_minus_market_model_{loss_name}"] = (
                values["market_plus_state_model"] - values["market_model"]
            )
            record[f"market_model_minus_raw_market_{loss_name}"] = (
                values["market_model"] - values["raw_market"]
            )
        records.append(record)
    return records


def _group_means(records: Sequence[dict], group: str, value: str) -> list[dict]:
    buckets: dict[str, list[float]] = defaultdict(list)
    for record in records:
        buckets[record[group]].append(record[value])
    return [
        {group: key, "events": len(values), value: math.fsum(values) / len(values)}
        for key, values in sorted(buckets.items())
    ]


def _group_bootstrap(records: Sequence[dict], group: str, value: str,
                     *, seed: int = BOOTSTRAP_SEED,
                     replicates: int = BOOTSTRAP_REPLICATES) -> dict:
    buckets: dict[str, list[float]] = defaultdict(list)
    for record in records:
        buckets[record[group]].append(record[value])
    labels = sorted(buckets)
    if len(labels) < 2:
        raise ValueError("grouped interval requires at least two groups")
    generator = np.random.default_rng(seed)
    draws = []
    for _ in range(replicates):
        sample = generator.choice(labels, size=len(labels), replace=True)
        values = [value for label in sample for value in buckets[str(label)]]
        draws.append(math.fsum(values) / len(values))
    point = math.fsum(record[value] for record in records) / len(records)
    return {
        "group": group,
        "groups": len(labels),
        "events": len(records),
        "point_equal_event_mean": point,
        "interval_95": [float(np.quantile(draws, 0.025)), float(np.quantile(draws, 0.975))],
        "bootstrap_replicates": replicates,
        "bootstrap_seed": seed,
        "resampling_rule": (
            "resample complete groups, then recompute the equal-event mean within each draw"
        ),
    }


def _aggregate(predictions: Sequence[dict]) -> dict:
    outcomes = [item["row"].trusted["outcome"] for item in predictions]
    result = {}
    for arm in ("raw_market", "market_model", "market_plus_state_model"):
        values = [item[arm] for item in predictions]
        result[arm] = settlement._simple_metrics(outcomes, values)
        result[arm]["reliability_table"] = _reliability_table(outcomes, values)
    return result


def _reliability_table(outcomes: Sequence[int], probabilities: Sequence[float],
                       bins: int = 10) -> list[dict]:
    if len(outcomes) != len(probabilities) or not outcomes:
        raise ValueError("reliability table requires nonempty paired rows")
    result = []
    for index in range(bins):
        lower, upper = index / bins, (index + 1) / bins
        selected = []
        for outcome, probability in zip(outcomes, probabilities, strict=True):
            inside = (
                lower <= probability <= upper
                if index == bins - 1 else lower <= probability < upper
            )
            if inside:
                selected.append((outcome, probability))
        result.append({
            "bin": index,
            "lower_inclusive": lower,
            "upper_inclusive_only_for_last_bin": upper,
            "events": len(selected),
            "mean_probability": (
                math.fsum(value[1] for value in selected) / len(selected)
                if selected else None
            ),
            "observed_rate": (
                math.fsum(value[0] for value in selected) / len(selected)
                if selected else None
            ),
        })
    return result


def increment_decision(aggregate: dict, folds: Sequence[dict]) -> tuple[str, dict]:
    market = aggregate["market_model"]
    state = aggregate["market_plus_state_model"]
    wins = [
        fold["arms"]["market_plus_state_model"]["brier"]
        < fold["arms"]["market_model"]["brier"]
        for fold in folds
    ]
    conditions = {
        "state_aggregate_brier_below_market_model": state["brier"] < market["brier"],
        "state_aggregate_log_loss_below_market_model": state["log_loss"] < market["log_loss"],
        "state_brier_fold_wins_at_least_3_of_4": sum(wins) >= 3,
        "fold_brier_wins": wins,
    }
    passed = all(value for key, value in conditions.items() if key != "fold_brier_wins")
    return ("PBP_INCREMENT_SUPPORTED" if passed else "PBP_INCREMENT_NOT_SUPPORTED"), conditions


def _write_predictions(path: Path, predictions: Sequence[dict]) -> None:
    fields = (
        "fold", "game_id", "game_date", "game_week", "event_id", "market_id",
        "cutoff_ms", "outcome_available_ms", "outcome", "raw_market_probability",
        "market_model_probability", "market_plus_state_probability",
    )
    temporary = path.with_suffix(".csv.tmp")
    with temporary.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for item in predictions:
            row = item["row"]
            writer.writerow({
                "fold": item["fold"], "game_id": row.game_id,
                "game_date": row.game_date, "game_week": row.game_week,
                "event_id": row.trusted["event_id"],
                "market_id": row.trusted["market_id"],
                "cutoff_ms": row.trusted["cutoff_ms"],
                "outcome_available_ms": row.trusted["outcome_available_ms"],
                "outcome": row.trusted["outcome"],
                "raw_market_probability": item["raw_market"],
                "market_model_probability": item["market_model"],
                "market_plus_state_probability": item["market_plus_state_model"],
            })
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def run(source_root: Path, output: Path, *, expected_events: int = EXPECTED_EVENTS,
        expected_dates: int = EXPECTED_DATES, allow_test_paths: bool = False,
        generated_utc: str | None = None) -> dict:
    source_root, output = Path(source_root).resolve(), Path(output).resolve()
    _validate_roots(source_root, output, allow_test_paths=allow_test_paths)
    cohort = _validate_source(
        source_root, expected_events=expected_events,
        expected_dates=expected_dates, allow_test_paths=allow_test_paths,
    )
    pbp_receipts = _validate_pbp_receipts(source_root, cohort)
    output.mkdir(parents=True, exist_ok=False)
    try:
        state_path = output / "checkpoint_state.csv"
        states = _extract_state_rows(source_root, state_path)
        materialized = []
        exclusions = []
        for ordinal, item in enumerate(cohort):
            try:
                materialized.append(_load_dynamic_market(
                    source_root, item, states[item["game_id"]]
                ))
            except settlement.EventExclusion as error:
                exclusions.append({
                    "source_ordinal": ordinal,
                    "game_id": item["game_id"],
                    "game_date": item["game_date"],
                    "reason": error.code,
                    "detail": str(error)[:400],
                })
        if len(materialized) + len(exclusions) != expected_events:
            raise RuntimeError("materialized and excluded events do not reconcile")
        if not allow_test_paths:
            observed = [(row["game_id"], row["reason"]) for row in exclusions]
            expected = [
                ("2025_04_GB_DAL", "unresolved_outcome"),
                ("2025_05_TEN_ARI", "market_trade_too_stale"),
            ]
            if len(materialized) != 193 or observed != expected:
                raise ValueError("exact in-game attrition must be 193/195 with two declared exclusions")
        materialized.sort(key=lambda row: row.key)
        folds = settlement.chronological_date_folds(
            [item["game_date"] for item in cohort], expected_dates=expected_dates
        )
        input_receipts = {
            "schema": "nfl_ingame_win_probability_train_inputs_v0",
            "task_id": "InGameWinProbabilityTrainDiagnostic-v0",
            "source_dataset_id": source_root.name,
            "source_manifest_sha256": settlement._sha256(source_root / "manifest.json"),
            "cohort_sha256": settlement._sha256(source_root / "cohort.csv"),
            "checkpoint_extractor_sha256": settlement._sha256(EXTRACTOR),
            "runner_source_sha256": settlement._sha256(Path(__file__)),
            "settlement_dependency_sha256": settlement._sha256(Path(settlement.__file__)),
            "probability_contract_sha256": settlement._sha256(Path(probability_contract.__file__)),
            "proper_scoring_dependency_sha256": settlement._sha256(Path(proper_scoring.__file__)),
            "checkpoint_state_sha256": settlement._sha256(state_path),
            "pbp_receipts": pbp_receipts,
            "materialized_receipts": [row.source_receipt for row in materialized],
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "external_fetch": False,
            "provider_cost_usd": "0",
        }
        exclusions_record = {
            "schema": "nfl_ingame_win_probability_train_exclusions_v0",
            "source_events": expected_events,
            "materialized_events": len(materialized),
            "excluded_events": len(exclusions),
            "reconciles_to_source_denominator": (
                len(materialized) + len(exclusions) == expected_events
            ),
            "exclusions": exclusions,
        }
        _atomic_json(output / "input_receipts.json", input_receipts)
        _atomic_json(output / "exclusions.json", exclusions_record)
        lock = {
            "schema": "nfl_ingame_win_probability_train_pre_score_lock_v0",
            "generated_utc": generated_utc or datetime.now(timezone.utc).isoformat(),
            "task_id": "InGameWinProbabilityTrainDiagnostic-v0",
            "separate_from_pregame_task": True,
            "question": (
                "On identical historical in-game rows, does adding contemporaneous game state "
                "to the same fixed logistic model add settlement information beyond the "
                "decision-time market logit?"
            ),
            "population": "complete opened 195-game 2025 NFL Train cohort",
            "checkpoint_rule": (
                "first nondeleted Q3 pre-play row with clockTime<=08:00, down 1-4, "
                "and complete causal state fields; independent of prices and outcomes"
            ),
            "maximum_trade_staleness_seconds": MAX_TRADE_STALENESS_SECONDS,
            "same_second_trade_rule": "market trades must be from an integer second strictly before the PBP event second",
            "availability_boundary": (
                "historical PBP event wall clock only; provider publish and local receive times are absent"
            ),
            "market_feature_names": list(MARKET_FEATURE_NAMES),
            "state_feature_names": list(STATE_FEATURE_NAMES),
            "forbidden_feature_families": [
                "future plays", "current-play result", "terminal score", "final outcome",
                "post-checkpoint market trades", "root gameDetail terminal totals",
            ],
            "arms": {
                "raw_market": "latest causal home-win trade probability",
                "market_model": {"features": "decision-time market logit only", "model": MODEL_SPEC},
                "market_plus_state_model": {
                    "features": "same market logit plus fixed pre-play state",
                    "model": MODEL_SPEC,
                },
            },
            "preprocessing": (
                "fold-fit StandardScaler on continuous columns only; possession and down "
                "one-hot columns remain unscaled"
            ),
            "folds": folds,
            "primary_metric": "equal-event Brier on one checkpoint per game",
            "secondary": [
                "log loss", "calibration slope/intercept", "per-date paired deltas",
                "schedule-date grouped interval", "observed-game-week grouped sensitivity",
            ],
            "increment_rule": (
                "state model aggregate Brier and log loss both below market-only model, "
                "with Brier wins in at least 3/4 chronological folds"
            ),
            "rule_scope": "project-chosen Discovery diagnostic; not a literature consensus or promotion gate",
            "bootstrap_seed": BOOTSTRAP_SEED,
            "bootstrap_replicates": BOOTSTRAP_REPLICATES,
            "materialized_key_sha256": settlement._digest([list(row.key) for row in materialized]),
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "external_fetch": False,
            "paid_provider": False,
            "provider_cost_usd": "0",
            "promotion_authorized": False,
        }
        _atomic_json(output / "pre_score_lock.json", lock)

        predictions, fold_reports = _fit_and_predict(materialized, folds)
        if not allow_test_paths and (
                fold_reports[0]["fit_events"] != 106
                or [fold["check_events"] for fold in fold_reports] != [26, 16, 28, 17]
                or any(fold["fit_label_unavailable_game_ids"] for fold in fold_reports)):
            raise ValueError("frozen chronological population or label availability changed")
        aggregate = _aggregate(predictions)
        decision, conditions = increment_decision(aggregate, fold_reports)
        records = _paired_records(predictions)
        evidence = {}
        for comparison in (
                "state_minus_market_model", "market_model_minus_raw_market"):
            evidence[comparison] = {}
            for loss_name in ("brier", "log_loss"):
                value = f"{comparison}_{loss_name}"
                evidence[comparison][loss_name] = {
                    "delta_convention": f"{comparison}; negative loss is better",
                    "equal_event_mean": math.fsum(row[value] for row in records) / len(records),
                    "by_event": [
                        {"game_id": row["game_id"], "game_date": row["game_date"],
                         "game_week": row["game_week"], value: row[value]}
                        for row in records
                    ],
                    "by_schedule_date": _group_means(records, "game_date", value),
                    "schedule_date_interval": _group_bootstrap(records, "game_date", value),
                    "observed_game_week_interval": _group_bootstrap(records, "game_week", value),
                }
        scorecard = {
            "schema": "nfl_ingame_win_probability_train_scorecard_v0",
            "task_id": "InGameWinProbabilityTrainDiagnostic-v0",
            "data_increment_decision": decision,
            "increment_conditions": conditions,
            "source_denominator": {
                "events": expected_events,
                "dates": expected_dates,
                "materialized_events": len(materialized),
                "excluded_events": len(exclusions),
                "materialization_coverage": len(materialized) / expected_events,
                "check_events": len(predictions),
                "check_dates": len({item["row"].game_date for item in predictions}),
                "check_game_weeks": len({item["row"].game_week for item in predictions}),
            },
            "identical_masks": {
                "all_three_arms_same_rows_labels_and_checkpoints": True,
                "check_key_sha256": settlement._digest([
                    list(item["row"].key) for item in predictions
                ]),
                "one_checkpoint_per_game": len(predictions) == len({
                    item["row"].game_id for item in predictions
                }),
            },
            "aggregate": aggregate,
            "deltas": {
                "state_minus_market_model": {
                    metric: aggregate["market_plus_state_model"][metric]
                    - aggregate["market_model"][metric]
                    for metric in ("brier", "log_loss")
                },
                "market_model_minus_raw_market": {
                    metric: aggregate["market_model"][metric]
                    - aggregate["raw_market"][metric]
                    for metric in ("brier", "log_loss")
                },
                "state_minus_raw_market": {
                    metric: aggregate["market_plus_state_model"][metric]
                    - aggregate["raw_market"][metric]
                    for metric in ("brier", "log_loss")
                },
            },
            "folds": fold_reports,
            "paired_grouped_evidence": evidence,
            "evidence_classification": {
                "raw_market_vs_market_model": "model/calibration evidence",
                "market_model_vs_market_plus_state": "data-increment evidence with trainer controlled",
                "research_mechanism": "not tested by this experiment",
            },
            "inference_boundary": (
                "repeatedly inspected opened-Train historical diagnostic; PBP publish/receive "
                "latency is unobserved; not realtime edge, untouched OOS, promotion, or PnL"
            ),
            "cross_task_comparison_forbidden": "do not compare numeric scores with the pregame task",
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "provider_cost_usd": "0",
            "promotion_authorized": False,
        }
        _write_predictions(output / "predictions.csv", predictions)
        _atomic_json(output / "scorecard.json", scorecard)
        manifest = {
            "schema": "nfl_ingame_win_probability_train_manifest_v0",
            "complete": True,
            "completed_utc": generated_utc or datetime.now(timezone.utc).isoformat(),
            "task_id": "InGameWinProbabilityTrainDiagnostic-v0",
            "pre_score_lock_sha256": settlement._sha256(output / "pre_score_lock.json"),
            "input_receipts_sha256": settlement._sha256(output / "input_receipts.json"),
            "exclusions_sha256": settlement._sha256(output / "exclusions.json"),
            "predictions_sha256": settlement._sha256(output / "predictions.csv"),
            "scorecard_sha256": settlement._sha256(output / "scorecard.json"),
            "source_events": expected_events,
            "materialized_events": len(materialized),
            "excluded_events": len(exclusions),
            "check_events": len(predictions),
            "model_fits": len(folds) * 2,
            "data_increment_decision": decision,
            "historical_event_clock_only": True,
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "external_fetch": False,
            "paid_provider": False,
            "provider_cost_usd": "0",
            "promotion_authorized": False,
        }
        _atomic_json(output / "manifest.json", manifest)
        return manifest
    except Exception as error:
        if output.exists() and not (output / "manifest.json").exists():
            _atomic_json(output / "failure.json", {
                "schema": "nfl_ingame_win_probability_train_failure_v0",
                "error_type": type(error).__name__,
                "error": str(error)[:1200],
                "route_dev_opened": False,
                "sealed_final_opened": False,
                "external_fetch": False,
                "paid_provider": False,
                "provider_cost_usd": "0",
            })
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.source_root, args.output)
    print(json.dumps({
        "complete": result["complete"],
        "task_id": result["task_id"],
        "source_events": result["source_events"],
        "materialized_events": result["materialized_events"],
        "excluded_events": result["excluded_events"],
        "check_events": result["check_events"],
        "data_increment_decision": result["data_increment_decision"],
        "provider_cost_usd": result["provider_cost_usd"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
