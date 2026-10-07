#!/usr/bin/env python3
"""Offline 2025 NFL Train-only settlement-probability diagnostic.

One row is materialized per event at 15 minutes before scheduled start.  The
ordinary and candidate models receive the exact same causal feature matrix,
folds and row masks; only the trainer changes.  This runner has no network or
provider client and cannot open Route-Dev or Final.  Its result is diagnostic
Train evidence only and cannot authorize promotion.
"""
from __future__ import annotations

import argparse
import copy
import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
from types import MappingProxyType
from typing import Iterable

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from minimal_prediction_loop.probability_contract import (
    DEFAULT_PROBABILITY_POLICY,
    validate_probability,
    validate_train_evaluation_rows,
)
from minimal_prediction_loop.proper_scoring import (
    ProperScoreSpec,
    bounded_log_loss,
    brier_loss,
    score_probability_forecasts,
)


SOURCE_ROOT = Path(
    "/Users/estelle/Library/Application Support/MarketRSI/"
    "self-evolving-v18-local/artifacts/nfl-2025-train-refresh-20260922-01"
)
PERSISTENT_ARTIFACT_ROOT = Path(
    "/Users/estelle/Library/Application Support/MarketRSI/"
    "self-evolving-v18-local/artifacts"
)
EXPECTED_MANIFEST_SHA256 = (
    "429a0ef100ade70f7e7b7f5862c39f42adffd7dcdaaddf35c73c88b60f80074f"
)
EXPECTED_COHORT_SHA256 = (
    "ba07b5535917f6ccfd4ddb5eadb53f6428b02bcc238595adac42894643d37885"
)
EXPECTED_EVENTS = 195
EXPECTED_DATES = 42
INITIAL_FIT_DATES = 22
CHECK_FOLDS = 4
CHECK_DATES_PER_FOLD = 5
CUTOFF_LEAD_SECONDS = 15 * 60
WINDOW_SECONDS = (15 * 60, 60 * 60, 240 * 60)
TRADE_FIELDS = (
    "side", "token_id", "condition_id", "size", "price", "timestamp",
    "event_slug", "outcome", "outcome_index", "transaction_hash",
)
FEATURE_NAMES = (
    "market_logit", "staleness_seconds",
    *(f"trailing_{seconds // 60}m_{name}"
      for seconds in WINDOW_SECONDS
      for name in (
          "log1p_trade_count", "log1p_total_size", "weighted_mean_home_probability",
          "weighted_std_home_probability", "last_minus_first_home_probability",
      )),
)
ORDINARY_SPEC = MappingProxyType({
    "class": "sklearn.linear_model.LogisticRegression",
    "C": 1.0,
    "solver": "lbfgs",
    "max_iter": 500,
    "random_state": 23,
})
CANDIDATE_SPEC = MappingProxyType({
    "class": "sklearn.ensemble.HistGradientBoostingClassifier",
    "max_iter": 150,
    "learning_rate": 0.05,
    "max_leaf_nodes": 15,
    "min_samples_leaf": 20,
    "l2_regularization": 1.0,
    "early_stopping": False,
    "random_state": 23,
})

# Exact, deliberately narrow vocabulary already used by the reviewed NFL
# alignment path.  In particular, LAR/LA/Rams is explicit and never fuzzy.
TEAM_NAMES = MappingProxyType({
    "ARI": ("ARI", "Cardinals"), "ATL": ("ATL", "Falcons"),
    "BAL": ("BAL", "Ravens"), "BUF": ("BUF", "Bills"),
    "CAR": ("CAR", "Panthers"), "CHI": ("CHI", "Bears"),
    "CIN": ("CIN", "Bengals"), "CLE": ("CLE", "Browns"),
    "DAL": ("DAL", "Cowboys"), "DEN": ("DEN", "Broncos"),
    "DET": ("DET", "Lions"), "GB": ("GB", "Packers"),
    "HOU": ("HOU", "Texans"), "IND": ("IND", "Colts"),
    "JAC": ("JAC", "JAX", "Jaguars"), "KC": ("KC", "Chiefs"),
    "LAC": ("LAC", "Chargers"), "LAR": ("LA", "LAR", "Rams"),
    "LV": ("LV", "Raiders"), "MIA": ("MIA", "Dolphins"),
    "MIN": ("MIN", "Vikings"), "NE": ("NE", "Patriots"),
    "NO": ("NO", "Saints"), "NYG": ("NYG", "Giants"),
    "NYJ": ("NYJ", "Jets"), "PHI": ("PHI", "Eagles"),
    "PIT": ("PIT", "Steelers"), "SEA": ("SEA", "Seahawks"),
    "SF": ("SF", "49ers"), "TB": ("TB", "Buccaneers"),
    "TEN": ("TEN", "Titans"), "WAS": ("WAS", "Commanders"),
})
GAME_TEAM_ALIASES = MappingProxyType({"LA": "LAR", "JAX": "JAC", "WSH": "WAS"})
_GAME_ID = re.compile(r"2025_[0-9]{2}_([A-Z]{2,3})_([A-Z]{2,3})\Z")


class EventExclusion(ValueError):
    """A declared per-event exclusion, retained in the 195-event ledger."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code


@dataclass(frozen=True)
class DiagnosticRow:
    game_id: str
    game_date: str
    split_date: str
    trusted: dict
    features: tuple[float, ...]
    source_receipt: dict

    @property
    def key(self) -> tuple[str, str, int]:
        return (
            self.trusted["event_id"], self.trusted["market_id"],
            self.trusted["cutoff_ms"],
        )


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _sha256(path: Path) -> str:
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def _atomic_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _strict_json(path: Path) -> object:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant forbidden: {value}")

    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=reject_constant)


def _json_array(value: object, label: str) -> list:
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except json.JSONDecodeError as error:
        raise EventExclusion("invalid_binary_market", f"{label} is invalid JSON") from error
    if not isinstance(parsed, list) or len(parsed) != 2:
        raise EventExclusion("invalid_binary_market", f"{label} must have exactly two items")
    return parsed


def _utc(value: object, label: str) -> datetime:
    if isinstance(value, bool):
        raise EventExclusion("invalid_timestamp", f"{label} must be a UTC timestamp")
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)) or float(value) <= 0:
            raise EventExclusion("invalid_timestamp", f"{label} epoch is invalid")
        # Provider epoch fields are seconds unless they are unambiguously ms.
        seconds = float(value) / 1000 if float(value) >= 10**12 else float(value)
        try:
            return datetime.fromtimestamp(seconds, timezone.utc)
        except (OverflowError, OSError, ValueError) as error:
            raise EventExclusion("invalid_timestamp", f"{label} epoch is invalid") from error
    if not isinstance(value, str):
        raise EventExclusion("invalid_timestamp", f"{label} must be a UTC timestamp")
    if value.isdigit():
        return _utc(int(value), label)
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise EventExclusion("invalid_timestamp", f"{label} is not ISO-8601") from error
    if result.tzinfo is None:
        raise EventExclusion("invalid_timestamp", f"{label} lacks timezone")
    return result.astimezone(timezone.utc)


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool):
        raise EventExclusion("invalid_trade", f"{label} must be numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise EventExclusion("invalid_trade", f"{label} must be numeric") from error
    if not math.isfinite(result):
        raise EventExclusion("invalid_trade", f"{label} must be finite")
    return result


def _team_pair(game_id: str) -> tuple[str, str]:
    match = _GAME_ID.fullmatch(game_id)
    if match is None:
        raise EventExclusion("ambiguous_orientation", "game ID does not prove away/home order")
    away, home = (GAME_TEAM_ALIASES.get(value, value) for value in match.groups())
    if away not in TEAM_NAMES or home not in TEAM_NAMES or away == home:
        raise EventExclusion("ambiguous_orientation", "game ID uses unknown or duplicate teams")
    return away, home


def orient_market(game_id: str, market: dict, expected_tokens: Iterable[str]) -> dict:
    """Return exact home/away token orientation or fail closed."""
    away, home = _team_pair(game_id)
    outcomes = _json_array(market.get("outcomes"), "outcomes")
    tokens = [str(value) for value in _json_array(
        market.get("clobTokenIds"), "clobTokenIds"
    )]
    if len(set(tokens)) != 2 or sorted(tokens) != sorted(map(str, expected_tokens)):
        raise EventExclusion("ambiguous_orientation", "source token identity is ambiguous")
    reverse: dict[str, str] = {}
    for team, names in TEAM_NAMES.items():
        for name in names:
            if name in reverse and reverse[name] != team:
                raise RuntimeError("code-owned NFL alias table is ambiguous")
            reverse[name] = team
    if any(not isinstance(value, str) or value not in reverse for value in outcomes):
        raise EventExclusion("ambiguous_orientation", "outcome name is outside exact aliases")
    teams = [reverse[value] for value in outcomes]
    if len(set(teams)) != 2 or set(teams) != {away, home}:
        raise EventExclusion("ambiguous_orientation", "outcomes do not exactly name game teams")
    return {
        "away_team": away,
        "home_team": home,
        "away_index": teams.index(away),
        "home_index": teams.index(home),
        "away_token": tokens[teams.index(away)],
        "home_token": tokens[teams.index(home)],
        "outcomes": outcomes,
        "tokens": tokens,
    }


def resolved_home_outcome(event: dict, market: dict, home_index: int,
                          event_start: datetime) -> tuple[int, int, str]:
    """Read the target and an explicit source close timestamp, never features."""
    prices = _json_array(market.get("outcomePrices"), "outcomePrices")
    try:
        numeric = [float(value) for value in prices]
    except (TypeError, ValueError) as error:
        raise EventExclusion("unresolved_outcome", "outcomePrices are not numeric") from error
    if numeric not in ([0.0, 1.0], [1.0, 0.0]):
        raise EventExclusion("unresolved_outcome", "outcomePrices are not exact [0,1]/[1,0]")
    if market.get("closed") is not True or event.get("closed") is not True:
        raise EventExclusion("unresolved_outcome", "source market/event is not closed")
    # Use the maximum of the resolution-relevant source clocks that are
    # present.  Scheduled endDate and generic updatedAt are intentionally not
    # admitted.  Taking the maximum is conservative when the source records
    # market closure, UMA completion and game-finished publication separately.
    clocks = []
    for field, raw in (
        ("market.closedTime", market.get("closedTime")),
        ("market.umaEndDate", market.get("umaEndDate")),
        ("event.finishedTimestamp", event.get("finishedTimestamp")),
    ):
        if raw is not None and raw != "":
            clocks.append((_utc(raw, field), field))
    if not clocks:
        raise EventExclusion(
            "missing_outcome_availability",
            "resolved source lacks closedTime/umaEndDate/finishedTimestamp",
        )
    available = max(value for value, _ in clocks)
    fields = ",".join(sorted(field for _, field in clocks))
    if available <= event_start:
        raise EventExclusion(
            "invalid_outcome_availability", "closedTime does not follow event start"
        )
    return int(numeric[home_index]), int(available.timestamp() * 1000), f"max({fields})"


def _weighted_probability(rows: list[dict]) -> tuple[float, float]:
    total_size = math.fsum(row["size"] for row in rows)
    if total_size <= 0:
        raise EventExclusion("invalid_trade", "nonpositive total trade size")
    mean = math.fsum(row["size"] * row["home_probability"] for row in rows) / total_size
    return mean, total_size


def build_features(trades: list[dict], cutoff_s: int) -> tuple[float, tuple[float, ...], int]:
    """Build the frozen causal feature row from trades at or before cutoff."""
    eligible = [row for row in trades if row["timestamp"] <= cutoff_s]
    if not eligible:
        raise EventExclusion("no_trade_at_or_before_cutoff", "no causal market baseline")
    latest_second = max(row["timestamp"] for row in eligible)
    latest = [row for row in eligible if row["timestamp"] == latest_second]
    market_probability, _ = _weighted_probability(latest)
    try:
        market_probability = validate_probability(
            market_probability, DEFAULT_PROBABILITY_POLICY, "market_probability"
        )
    except ValueError as error:
        raise EventExclusion("invalid_endpoint_baseline", str(error)) from error
    values = [
        math.log(market_probability / (1.0 - market_probability)),
        float(cutoff_s - latest_second),
    ]
    for seconds in WINDOW_SECONDS:
        window = [
            row for row in eligible
            if cutoff_s - seconds <= row["timestamp"] <= cutoff_s
        ]
        if not window:
            raise EventExclusion(
                f"empty_trailing_{seconds // 60}m_window",
                "frozen feature window has no trades; no imputation permitted",
            )
        mean, total_size = _weighted_probability(window)
        variance = math.fsum(
            row["size"] * (row["home_probability"] - mean) ** 2 for row in window
        ) / total_size
        first_second = min(row["timestamp"] for row in window)
        last_second = max(row["timestamp"] for row in window)
        first, _ = _weighted_probability(
            [row for row in window if row["timestamp"] == first_second]
        )
        last, _ = _weighted_probability(
            [row for row in window if row["timestamp"] == last_second]
        )
        values.extend((
            math.log1p(len(window)), math.log1p(total_size), mean,
            math.sqrt(max(0.0, variance)), last - first,
        ))
    if len(values) != len(FEATURE_NAMES) or any(not math.isfinite(value) for value in values):
        raise EventExclusion("invalid_features", "frozen feature matrix is nonfinite")
    return market_probability, tuple(values), latest_second * 1000


def _load_trades(path: Path, meta: dict, orientation: dict,
                 event_slug: str) -> list[dict]:
    rows = []
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != TRADE_FIELDS:
            raise ValueError("trade CSV differs from exact safe schema")
        for ordinal, raw in enumerate(reader):
            if (raw["condition_id"] != meta["condition_id"]
                    or raw["event_slug"] != event_slug):
                raise ValueError("trade identity differs from selected market")
            try:
                index = int(raw["outcome_index"])
                timestamp = int(raw["timestamp"])
            except ValueError as error:
                raise EventExclusion("invalid_trade", "trade index/time is invalid") from error
            if index not in (0, 1):
                raise EventExclusion("invalid_trade", "trade outcome index is not binary")
            token = str(raw["token_id"])
            if (token != orientation["tokens"][index]
                    or raw["outcome"] != orientation["outcomes"][index]):
                raise EventExclusion("ambiguous_orientation", "trade outcome/token pair changed")
            price = _finite(raw["price"], "trade price")
            size = _finite(raw["size"], "trade size")
            if not 0.0 <= price <= 1.0 or size <= 0 or timestamp <= 0:
                raise EventExclusion("invalid_trade", "trade price/size/time is outside bounds")
            home_probability = price if token == orientation["home_token"] else 1.0 - price
            rows.append({
                "source_ordinal": ordinal,
                "timestamp": timestamp,
                "size": size,
                "home_probability": home_probability,
            })
    if not rows:
        raise EventExclusion("empty_trade_tape", "trade tape is empty")
    return rows


def _selected_market(event: dict, meta: dict) -> dict:
    markets = event.get("markets")
    if not isinstance(markets, list):
        raise ValueError("source event markets is not a list")
    selected = [
        market for market in markets if isinstance(market, dict)
        and str(market.get("id")) == str(meta["market_id"])
        and str(market.get("conditionId")) == meta["condition_id"]
        and market.get("sportsMarketType") == "moneyline"
    ]
    if len(selected) != 1:
        raise ValueError("exact selected raw moneyline is missing or ambiguous")
    return selected[0]


def _materialize_event(source_root: Path, cohort: dict) -> DiagnosticRow:
    game_id = cohort["game_id"]
    meta_path = source_root / "catalog" / f"{game_id}.json"
    raw_path = source_root / "catalog" / f"{game_id}.raw.json.gz"
    trade_root = source_root / "trades" / game_id
    trade_manifest_path = trade_root / "manifest.json"
    trade_path = trade_root / "trade_window.csv"
    meta = _strict_json(meta_path)
    if (not isinstance(meta, dict)
            or any(meta.get(key) != cohort[key]
                   for key in ("game_id", "game_date", "event_slug"))):
        raise ValueError("normalized catalog identity differs from cohort")
    compressed = raw_path.read_bytes()
    if hashlib.sha256(compressed).hexdigest() != meta.get("stored_sha256"):
        raise ValueError("raw catalog stored hash mismatch")
    raw = gzip.decompress(compressed)
    if hashlib.sha256(raw).hexdigest() != meta.get("raw_sha256"):
        raise ValueError("raw catalog source hash mismatch")
    event = json.loads(raw)
    if (str(event.get("id")) != str(meta.get("event_id"))
            or event.get("slug") != cohort["event_slug"]):
        raise ValueError("raw event identity differs from normalized catalog")
    market = _selected_market(event, meta)
    orientation = orient_market(game_id, market, meta["tokens"])
    start = _utc(meta["event_start_utc"], "event_start_utc")
    cutoff = start - timedelta(seconds=CUTOFF_LEAD_SECONDS)
    cutoff_s = int(cutoff.timestamp())
    outcome, outcome_available_ms, outcome_clock = resolved_home_outcome(
        event, market, orientation["home_index"], start
    )

    trade_manifest = _strict_json(trade_manifest_path)
    if (not isinstance(trade_manifest, dict)
            or trade_manifest.get("game_id") != game_id
            or trade_manifest.get("condition_id") != meta["condition_id"]
            or sorted(map(str, trade_manifest.get("tokens", []))) != sorted(meta["tokens"])
            or trade_manifest.get("complete") is not True
            or trade_manifest.get("dev_final_opened") is not False
            or trade_manifest.get("trade_window_sha256") != _sha256(trade_path)):
        raise ValueError("trade manifest identity/hash/boundary check failed")
    trades = _load_trades(trade_path, meta, orientation, cohort["event_slug"])
    market_probability, features, feature_available_ms = build_features(trades, cutoff_s)
    trusted = {
        "event_id": str(meta["event_id"]),
        "market_id": str(meta["market_id"]),
        "cutoff_ms": cutoff_s * 1000,
        "feature_available_ms": feature_available_ms,
        "market_probability": market_probability,
        "outcome_available_ms": outcome_available_ms,
        "outcome": outcome,
    }
    # Structural validation also proves outcome is unavailable at the decision.
    from minimal_prediction_loop.probability_contract import validate_probability_rows
    validate_probability_rows([trusted])
    return DiagnosticRow(
        game_id=game_id,
        game_date=cohort["game_date"],
        split_date=cohort["game_date"],
        trusted=trusted,
        features=features,
        source_receipt={
            "game_id": game_id,
            "catalog_meta_sha256": _sha256(meta_path),
            "catalog_stored_sha256": _sha256(raw_path),
            "catalog_raw_sha256": meta["raw_sha256"],
            "trade_manifest_sha256": _sha256(trade_manifest_path),
            "trade_window_sha256": _sha256(trade_path),
            "condition_id": meta["condition_id"],
            "home_team": orientation["home_team"],
            "home_token_id": orientation["home_token"],
            "outcome_availability_field": outcome_clock,
        },
    )


def chronological_date_folds(dates: Iterable[str], *, expected_dates: int = EXPECTED_DATES
                             ) -> list[dict]:
    ordered = sorted(set(dates))
    required = INITIAL_FIT_DATES + CHECK_FOLDS * CHECK_DATES_PER_FOLD
    if len(ordered) != expected_dates or expected_dates != required:
        raise ValueError("exact 22-date fit plus four 5-date checks requires 42 dates")
    folds = []
    for index in range(CHECK_FOLDS):
        check_start = INITIAL_FIT_DATES + index * CHECK_DATES_PER_FOLD
        check_end = check_start + CHECK_DATES_PER_FOLD
        folds.append({
            "fold": index + 1,
            "fit_dates": ordered[:check_start],
            "check_dates": ordered[check_start:check_end],
        })
    if folds[-1]["check_dates"][-1] != ordered[-1]:
        raise RuntimeError("frozen folds do not consume all dates")
    return folds


def diagnostic_keep(candidate_brier: float, ordinary_brier: float,
                    candidate_log_loss: float, ordinary_log_loss: float,
                    fold_brier_wins: Iterable[bool]) -> tuple[str, dict]:
    wins = list(fold_brier_wins)
    conditions = {
        "candidate_aggregate_brier_below_ordinary": candidate_brier < ordinary_brier,
        "candidate_aggregate_log_loss_below_ordinary": candidate_log_loss < ordinary_log_loss,
        "candidate_brier_fold_wins_at_least_3_of_4": sum(wins) >= 3,
        "fold_brier_wins": wins,
    }
    return ("KEEP" if all(value for key, value in conditions.items()
                           if key != "fold_brier_wins") else "REVERT", conditions)


def validate_exact_cohort_attrition(source_events: int, materialized_events: int,
                                    exclusions: list[dict]) -> None:
    observed = [(row.get("game_id"), row.get("reason")) for row in exclusions]
    if (source_events != 195 or materialized_events != 194
            or observed != [("2025_04_GB_DAL", "unresolved_outcome")]):
        raise ValueError(
            "exact cohort must materialize 194/195 with only the GB-DAL tie excluded"
        )


def _prediction_records(rows: list[DiagnosticRow], values: Iterable[float]) -> list[dict]:
    result = []
    for row, value in zip(rows, values, strict=True):
        probability = validate_probability(
            float(value), DEFAULT_PROBABILITY_POLICY, "model probability"
        )
        result.append({
            "event_id": row.trusted["event_id"],
            "market_id": row.trusted["market_id"],
            "cutoff_ms": row.trusted["cutoff_ms"],
            "probability": probability,
        })
    return result


def _score(rows: list[DiagnosticRow], predictions: list[dict], *,
           reference: list[dict] | None = None) -> dict:
    trusted = [dict(row.trusted) for row in rows]
    if reference is not None:
        if len(reference) != len(rows):
            raise ValueError("reference prediction mask differs")
        for row, record, expected in zip(trusted, reference, rows, strict=True):
            key = (record.get("event_id"), record.get("market_id"), record.get("cutoff_ms"))
            if key != expected.key:
                raise ValueError("reference prediction order/mask differs")
            row["market_probability"] = validate_probability(
                record.get("probability"), DEFAULT_PROBABILITY_POLICY,
                "reference probability",
            )
    return score_probability_forecasts(
        trusted, predictions,
        spec=ProperScoreSpec(
            probability_epsilon=DEFAULT_PROBABILITY_POLICY.epsilon,
            reliability_bins=10,
            bootstrap_seed=23,
            bootstrap_replicates=1000,
            date_block_days=1,
        ),
    )


def _direct_candidate_ordinary_view(score: dict) -> dict:
    """Relabel the generic scorer's reference fields without recomputing deltas."""
    convention = "candidate_minus_ordinary; negative loss is better"

    def records(values: list[dict], identity: str) -> list[dict]:
        result = []
        for value in values:
            result.append({
                identity: value[identity],
                "events": value["events"],
                "candidate_brier": value["candidate_brier"],
                "ordinary_brier": value["market_brier"],
                "candidate_minus_ordinary_brier": value["candidate_minus_market_brier"],
                "candidate_log_loss": value["candidate_log_loss"],
                "ordinary_log_loss": value["market_log_loss"],
                "candidate_minus_ordinary_log_loss": (
                    value["candidate_minus_market_log_loss"]
                ),
            })
        return result

    def summary(value: dict) -> dict:
        result = copy.deepcopy(value)
        result["delta_convention"] = convention
        return result

    paired = score["paired_evidence"]
    return {
        "delta_convention": convention,
        "events": records(paired["events"], "event_id"),
        "dates": records(paired["dates"], "utc_date"),
        "event_brier_summary": summary(paired["event_brier"]),
        "event_log_loss_summary": summary(paired["event_log_loss"]),
        "date_block_brier_summary": summary(paired["date_block_brier"]),
        "date_block_log_loss_summary": summary(paired["date_block_log_loss"]),
        "arithmetic_source": (
            "trusted proper scorer with ordinary predictions bound as the exact reference"
        ),
    }


def _simple_metrics(outcomes: list[int], predictions: list[float]) -> dict:
    if not outcomes or len(outcomes) != len(predictions):
        raise ValueError("nonempty same-mask outcomes/predictions required")
    mean_p = math.fsum(predictions) / len(predictions)
    mean_y = math.fsum(outcomes) / len(outcomes)
    variance = math.fsum((value - mean_p) ** 2 for value in predictions)
    slope = (math.fsum((p - mean_p) * (y - mean_y)
                       for p, y in zip(predictions, outcomes, strict=True)) / variance
             if variance else None)
    return {
        "rows": len(outcomes),
        "brier": math.fsum(brier_loss(p, y)
                            for p, y in zip(predictions, outcomes, strict=True)) / len(outcomes),
        "log_loss": math.fsum(bounded_log_loss(p, y)
                               for p, y in zip(predictions, outcomes, strict=True)) / len(outcomes),
        "calibration_slope": slope,
        "calibration_intercept": mean_y - slope * mean_p if slope is not None else None,
    }


def _fit_and_predict(rows: list[DiagnosticRow], folds: list[dict]) -> tuple[list[dict], list[dict]]:
    by_date: dict[str, list[DiagnosticRow]] = {}
    for row in rows:
        by_date.setdefault(row.split_date, []).append(row)
    all_predictions = []
    fold_reports = []
    for fold in folds:
        check_rows = sorted(
            [row for date in fold["check_dates"] for row in by_date.get(date, [])],
            key=lambda row: row.key,
        )
        if not check_rows:
            raise ValueError(f"fold {fold['fold']} has no eligible check rows")
        first_check_cutoff = min(row.trusted["cutoff_ms"] for row in check_rows)
        fit_candidates = [
            row for date in fold["fit_dates"] for row in by_date.get(date, [])
        ]
        fit_rows = sorted(
            [row for row in fit_candidates
             if row.trusted["outcome_available_ms"] < first_check_cutoff],
            key=lambda row: row.key,
        )
        label_unavailable = sorted(
            row.game_id for row in fit_candidates
            if row.trusted["outcome_available_ms"] >= first_check_cutoff
        )
        if not fit_rows or len({row.trusted["outcome"] for row in fit_rows}) != 2:
            raise ValueError(f"fold {fold['fold']} fit rows lack both outcome classes")
        validate_train_evaluation_rows(
            [row.trusted for row in fit_rows], [row.trusted for row in check_rows]
        )
        x_fit = np.asarray([row.features for row in fit_rows], dtype=np.float64)
        x_check = np.asarray([row.features for row in check_rows], dtype=np.float64)
        y_fit = np.asarray([row.trusted["outcome"] for row in fit_rows], dtype=np.int64)
        y_check = [row.trusted["outcome"] for row in check_rows]
        scaler = StandardScaler()
        standardized_fit = scaler.fit_transform(x_fit)
        standardized_check = scaler.transform(x_check)
        ordinary = LogisticRegression(
            C=1.0, solver="lbfgs", max_iter=500, random_state=23
        )
        candidate = HistGradientBoostingClassifier(
            max_iter=150, learning_rate=0.05, max_leaf_nodes=15,
            min_samples_leaf=20, l2_regularization=1.0,
            early_stopping=False, random_state=23,
        )
        ordinary.fit(standardized_fit, y_fit)
        candidate.fit(standardized_fit, y_fit)
        ordinary_values = [float(value) for value in ordinary.predict_proba(
            standardized_check
        )[:, 1]]
        candidate_values = [float(value) for value in candidate.predict_proba(
            standardized_check
        )[:, 1]]
        market_values = [row.trusted["market_probability"] for row in check_rows]
        ordinary_records = _prediction_records(check_rows, ordinary_values)
        candidate_records = _prediction_records(check_rows, candidate_values)
        market_metrics = _simple_metrics(y_check, market_values)
        ordinary_metrics = _simple_metrics(y_check, ordinary_values)
        candidate_metrics = _simple_metrics(y_check, candidate_values)
        fold_reports.append({
            "fold": fold["fold"],
            "fit_dates": fold["fit_dates"],
            "check_dates": fold["check_dates"],
            "fit_events": len(fit_rows),
            "check_events": len(check_rows),
            "fit_label_unavailable_events": label_unavailable,
            "identical_fit_feature_matrix": True,
            "identical_check_feature_matrix": True,
            "market": market_metrics,
            "ordinary": ordinary_metrics,
            "candidate": candidate_metrics,
            "candidate_minus_ordinary_brier": (
                candidate_metrics["brier"] - ordinary_metrics["brier"]
            ),
            "candidate_minus_ordinary_log_loss": (
                candidate_metrics["log_loss"] - ordinary_metrics["log_loss"]
            ),
        })
        for row, ordinary_record, candidate_record in zip(
                check_rows, ordinary_records, candidate_records, strict=True):
            all_predictions.append({
                "fold": fold["fold"],
                "row": row,
                "ordinary": ordinary_record,
                "candidate": candidate_record,
            })
    keys = [item["row"].key for item in all_predictions]
    if len(keys) != len(set(keys)):
        raise ValueError("an event appears in multiple check folds")
    return all_predictions, fold_reports


def _read_cohort(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != ("game_id", "game_date", "event_slug"):
            raise ValueError("cohort CSV differs from exact schema")
        rows = list(reader)
    if len({row["game_id"] for row in rows}) != len(rows):
        raise ValueError("cohort has duplicate game IDs")
    for row in rows:
        try:
            parsed = datetime.strptime(row["game_date"], "%Y-%m-%d").date()
        except (TypeError, ValueError) as error:
            raise ValueError("cohort game_date is not canonical YYYY-MM-DD") from error
        if parsed.isoformat() != row["game_date"]:
            raise ValueError("cohort game_date is not canonical YYYY-MM-DD")
    return rows


def _validate_roots(source_root: Path, output: Path, *, allow_test_paths: bool) -> None:
    source_root, output = source_root.resolve(), output.resolve()
    if output.exists():
        raise FileExistsError("output already exists; use a fresh diagnostic ID")
    if source_root == output or source_root in output.parents:
        raise ValueError("output cannot be inside immutable source root")
    if not allow_test_paths:
        if source_root != SOURCE_ROOT.resolve():
            raise ValueError("runner is bound to the exact frozen 2025 Train root")
        try:
            output.relative_to(PERSISTENT_ARTIFACT_ROOT.resolve())
        except ValueError as error:
            raise ValueError("output must be under persistent local MarketRSI artifacts") from error
        lowered = str(output).lower()
        if any(marker in lowered for marker in (
                "/tmp/", "/private/var/", "icloud", "mobile documents", "dropbox")):
            raise ValueError("temporary or cloud-looking output is forbidden")


def run(source_root: Path, output: Path, *, expected_events: int = EXPECTED_EVENTS,
        expected_dates: int = EXPECTED_DATES, allow_test_paths: bool = False,
        generated_utc: str | None = None) -> dict:
    """Run the fixed diagnostic.  Test-only path/count overrides are not CLI exposed."""
    source_root, output = Path(source_root).resolve(), Path(output).resolve()
    _validate_roots(source_root, output, allow_test_paths=allow_test_paths)
    if not allow_test_paths:
        if _sha256(source_root / "manifest.json") != EXPECTED_MANIFEST_SHA256:
            raise ValueError("frozen source manifest hash changed")
        if _sha256(source_root / "cohort.csv") != EXPECTED_COHORT_SHA256:
            raise ValueError("frozen cohort hash changed")
    manifest = _strict_json(source_root / "manifest.json")
    if (not isinstance(manifest, dict)
            or manifest.get("schema") != "nfl_2025_train_fresh_source_audit_v1"
            or manifest.get("complete") is not True
            or manifest.get("source_games") != expected_events
            or manifest.get("train_distinct_dates") != expected_dates
            or manifest.get("dev_final_opened") is not False
            or manifest.get("model_fits") != 0
            or manifest.get("provider_cost_usd") != "0"):
        raise ValueError("source manifest scope/completeness boundary failed")
    cohort_path = source_root / "cohort.csv"
    cohort = _read_cohort(cohort_path)
    if len(cohort) != expected_events:
        raise ValueError("source denominator differs from frozen event count")
    if set((source_root / "catalog").glob("*.json")) != {
            source_root / "catalog" / f"{row['game_id']}.json" for row in cohort}:
        raise ValueError("normalized catalog population differs from cohort")
    output.mkdir(parents=True, exist_ok=False)
    try:
        source_file_receipts = [{
            "game_id": item["game_id"],
            "catalog_meta_sha256": _sha256(
                source_root / "catalog" / f"{item['game_id']}.json"
            ),
            "catalog_stored_sha256": _sha256(
                source_root / "catalog" / f"{item['game_id']}.raw.json.gz"
            ),
            "trade_manifest_sha256": _sha256(
                source_root / "trades" / item["game_id"] / "manifest.json"
            ),
            "trade_window_sha256": _sha256(
                source_root / "trades" / item["game_id"] / "trade_window.csv"
            ),
        } for item in cohort]
        materialized = []
        exclusions = []
        for ordinal, item in enumerate(cohort):
            try:
                materialized.append(_materialize_event(source_root, item))
            except EventExclusion as error:
                exclusions.append({
                    "source_ordinal": ordinal,
                    "game_id": item["game_id"],
                    "game_date": item["game_date"],
                    "reason": error.code,
                    "detail": str(error)[:400],
                })
        if len(materialized) + len(exclusions) != expected_events:
            raise RuntimeError("materialized plus excluded events do not reconcile")
        if not allow_test_paths:
            validate_exact_cohort_attrition(expected_events, len(materialized), exclusions)
        cohort_dates = [item["game_date"] for item in cohort]
        folds = chronological_date_folds(cohort_dates, expected_dates=expected_dates)
        if not materialized:
            raise ValueError("all source events were excluded")
        materialized.sort(key=lambda row: row.key)
        input_receipts = {
            "schema": "nfl_settlement_probability_train_inputs_v1",
            "source_dataset_id": source_root.name,
            "source_manifest_sha256": _sha256(source_root / "manifest.json"),
            "cohort_sha256": _sha256(cohort_path),
            "source_events": expected_events,
            "source_dates": expected_dates,
            "runner_source_sha256": _sha256(Path(__file__)),
            "all_source_file_receipts": source_file_receipts,
            "materialized_event_receipts": [row.source_receipt for row in materialized],
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "provider_cost_usd": "0",
        }
        exclusions_artifact = {
            "schema": "nfl_settlement_probability_train_exclusions_v1",
            "source_events": expected_events,
            "materialized_events": len(materialized),
            "excluded_events": len(exclusions),
            "reconciles_to_source_denominator": (
                len(materialized) + len(exclusions) == expected_events
            ),
            "exclusions": exclusions,
        }
        _atomic_json(output / "input_receipts.json", input_receipts)
        _atomic_json(output / "exclusions.json", exclusions_artifact)
        lock = {
            "schema": "nfl_settlement_probability_train_pre_score_lock_v1",
            "generated_utc": generated_utc or datetime.now(timezone.utc).isoformat(),
            "problem": "test whether a nonlinear trainer improves settlement probability on a fixed causal representation",
            "hypothesis": "the fixed HistGradientBoosting candidate clears the diagnostic KEEP rule against fixed logistic regression",
            "changed_stage": "prediction_trainer_only",
            "domain": "2025 NFL two-outcome moneyline opened Train",
            "source_manifest_sha256": input_receipts["source_manifest_sha256"],
            "cohort_sha256": input_receipts["cohort_sha256"],
            "input_receipts_sha256": _sha256(output / "input_receipts.json"),
            "exclusions_sha256": _sha256(output / "exclusions.json"),
            "source_events": expected_events,
            "source_dates": expected_dates,
            "decision_cutoff": "event_start_utc minus 15 minutes",
            "chronological_grouping": (
                "exact cohort/catalog game_date; one whole schedule date per fold; "
                "never cutoff UTC calendar date"
            ),
            "outcome_availability": (
                "maximum of present selected-market closedTime, selected-market "
                "umaEndDate, and event finishedTimestamp; no other clock admitted"
            ),
            "same_second_baseline": "size-weighted home-win probability at latest eligible integer second",
            "feature_names": list(FEATURE_NAMES),
            "feature_spec_sha256": _digest({
                "names": FEATURE_NAMES,
                "windows_seconds": WINDOW_SECONDS,
                "missing": "exclude_without_imputation",
                "orientation": {key: list(value) for key, value in TEAM_NAMES.items()},
            }),
            "folds": folds,
            "ordinary_spec": dict(ORDINARY_SPEC),
            "ordinary_spec_sha256": _digest(dict(ORDINARY_SPEC)),
            "candidate_spec": dict(CANDIDATE_SPEC),
            "candidate_spec_sha256": _digest(dict(CANDIDATE_SPEC)),
            "shared_preprocessing": "fold-fit StandardScaler",
            "event_weighting": "one row per event; equal event weight",
            "keep_rule": (
                "candidate aggregate Brier < ordinary AND candidate aggregate log loss "
                "< ordinary AND candidate Brier wins at least 3/4 folds"
            ),
            "materialized_key_sha256": _digest([list(row.key) for row in materialized]),
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "external_fetch": False,
            "paid_provider": False,
            "provider_cost_usd": "0",
            "promotion_authorized": False,
        }
        _atomic_json(output / "pre_score_lock.json", lock)

        predictions, fold_reports = _fit_and_predict(materialized, folds)
        check_rows = [item["row"] for item in predictions]
        if not allow_test_paths and len({row.split_date for row in check_rows}) != 20:
            raise ValueError("exact cohort must retain all 20 frozen OOF check dates")
        ordinary_records = [item["ordinary"] for item in predictions]
        candidate_records = [item["candidate"] for item in predictions]
        ordinary_vs_market = _score(check_rows, ordinary_records)
        candidate_vs_market = _score(check_rows, candidate_records)
        candidate_vs_ordinary = _score(
            check_rows, candidate_records, reference=ordinary_records
        )
        ordinary_primary = ordinary_vs_market["primary"]
        candidate_primary = candidate_vs_market["primary"]
        decision, conditions = diagnostic_keep(
            candidate_primary["equal_event_candidate_brier"],
            ordinary_primary["equal_event_candidate_brier"],
            candidate_primary["equal_event_candidate_log_loss"],
            ordinary_primary["equal_event_candidate_log_loss"],
            [fold["candidate"]["brier"] < fold["ordinary"]["brier"]
             for fold in fold_reports],
        )

        prediction_path = output / "predictions.csv"
        fields = (
            "fold", "game_id", "split_date", "event_id", "market_id", "cutoff_ms",
            "outcome_available_ms", "outcome", "market_probability",
            "ordinary_probability", "candidate_probability",
        )
        temporary = prediction_path.with_suffix(".csv.tmp")
        with temporary.open("x", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for item in predictions:
                row = item["row"]
                writer.writerow({
                    "fold": item["fold"], "game_id": row.game_id,
                    "split_date": row.split_date,
                    "event_id": row.trusted["event_id"],
                    "market_id": row.trusted["market_id"],
                    "cutoff_ms": row.trusted["cutoff_ms"],
                    "outcome_available_ms": row.trusted["outcome_available_ms"],
                    "outcome": row.trusted["outcome"],
                    "market_probability": row.trusted["market_probability"],
                    "ordinary_probability": item["ordinary"]["probability"],
                    "candidate_probability": item["candidate"]["probability"],
                })
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(prediction_path)

        scorecard = {
            "schema": "nfl_settlement_probability_train_scorecard_v1",
            "diagnostic_decision": decision,
            "keep_conditions": conditions,
            "source_denominator": {
                "events": expected_events,
                "dates": expected_dates,
                "materialized_events": len(materialized),
                "excluded_events": len(exclusions),
                "check_events": len(check_rows),
                "check_dates": len({row.split_date for row in check_rows}),
                "materialization_coverage": len(materialized) / expected_events,
                "check_fraction_of_source_events": len(check_rows) / expected_events,
            },
            "identical_masks": {
                "market_ordinary_candidate_check_keys_identical": True,
                "complete_mask_sha256": candidate_vs_market["coverage"]["complete_mask_sha256"],
                "ordinary_complete_mask_sha256": ordinary_vs_market["coverage"]["complete_mask_sha256"],
                "candidate_vs_ordinary_complete_mask_sha256": candidate_vs_ordinary["coverage"]["complete_mask_sha256"],
            },
            "aggregate": {
                "market": {
                    "brier": candidate_primary["equal_event_market_brier"],
                    "log_loss": candidate_primary["equal_event_market_log_loss"],
                    "calibration": candidate_vs_market["calibration"]["market"],
                },
                "ordinary": {
                    "brier": ordinary_primary["equal_event_candidate_brier"],
                    "log_loss": ordinary_primary["equal_event_candidate_log_loss"],
                    "calibration": ordinary_vs_market["calibration"]["candidate"],
                },
                "candidate": {
                    "brier": candidate_primary["equal_event_candidate_brier"],
                    "log_loss": candidate_primary["equal_event_candidate_log_loss"],
                    "calibration": candidate_vs_market["calibration"]["candidate"],
                },
                "candidate_minus_ordinary": {
                    "brier": candidate_vs_ordinary["primary"]["equal_event_candidate_minus_market_brier"],
                    "log_loss": candidate_vs_ordinary["primary"]["equal_event_candidate_minus_market_log_loss"],
                },
                "candidate_minus_market": {
                    "brier": candidate_primary["equal_event_candidate_minus_market_brier"],
                    "log_loss": candidate_primary["equal_event_candidate_minus_market_log_loss"],
                },
            },
            "folds": fold_reports,
            "paired_candidate_minus_ordinary": _direct_candidate_ordinary_view(
                candidate_vs_ordinary
            ),
            "paired_candidate_minus_market": candidate_vs_market["paired_evidence"],
            "paired_ordinary_minus_market": ordinary_vs_market["paired_evidence"],
            "inference_boundary": (
                "opened-Train chronological diagnostic only; not independent OOS, "
                "promotion, publication, deployment, or a tradable-price claim"
            ),
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "provider_cost_usd": "0",
            "promotion_authorized": False,
        }
        masks = scorecard["identical_masks"]
        if len(set((masks["complete_mask_sha256"], masks["ordinary_complete_mask_sha256"],
                    masks["candidate_vs_ordinary_complete_mask_sha256"]))) != 1:
            raise RuntimeError("proper scorers did not receive identical check masks")
        _atomic_json(output / "scorecard.json", scorecard)
        final = {
            "schema": "nfl_settlement_probability_train_manifest_v1",
            "complete": True,
            "completed_utc": generated_utc or datetime.now(timezone.utc).isoformat(),
            "pre_score_lock_sha256": _sha256(output / "pre_score_lock.json"),
            "input_receipts_sha256": _sha256(output / "input_receipts.json"),
            "exclusions_sha256": _sha256(output / "exclusions.json"),
            "predictions_sha256": _sha256(output / "predictions.csv"),
            "scorecard_sha256": _sha256(output / "scorecard.json"),
            "source_events": expected_events,
            "materialized_events": len(materialized),
            "excluded_events": len(exclusions),
            "check_events": len(check_rows),
            "model_fits": CHECK_FOLDS * 2,
            "diagnostic_decision": decision,
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "external_fetch": False,
            "paid_provider": False,
            "provider_cost_usd": "0",
            "promotion_authorized": False,
        }
        _atomic_json(output / "manifest.json", final)
        return final
    except Exception as error:
        if output.exists() and not (output / "manifest.json").exists():
            _atomic_json(output / "failure.json", {
                "schema": "nfl_settlement_probability_train_failure_v1",
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
        "source_events": result["source_events"],
        "materialized_events": result["materialized_events"],
        "excluded_events": result["excluded_events"],
        "check_events": result["check_events"],
        "diagnostic_decision": result["diagnostic_decision"],
        "provider_cost_usd": result["provider_cost_usd"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
