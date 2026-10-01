#!/usr/bin/env python3
"""Audit a strictly-prior play-success signal on the frozen in-game v0 mask.

The runner emits no candidate probability and performs zero prediction-model
fits.  It measures whether a home-minus-away eligible-play success-rate signal
aligns with the frozen raw-market residual on the exact 87 opened-Train check
games.  This is historical Discovery evidence only, not realtime, untouched
OOS, promotion, PnL, or cross-task evidence.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
from typing import Mapping, Sequence

import numpy as np

from experiments import nfl_ingame_win_probability_train_diagnostic as v0


V0_ARTIFACT_ROOT = Path(
    "/Users/estelle/Library/Application Support/MarketRSI/"
    "self-evolving-v18-local/artifacts/"
    "nfl-ingame-win-probability-train-diagnostic-20260929-01"
)
PERSISTENT_ARTIFACT_ROOT = v0.PERSISTENT_ARTIFACT_ROOT
SOURCE_ROOT = v0.SOURCE_ROOT
EXTRACTOR = Path(__file__).with_name("extract_nfl_prior_play_success.R")
CONTROLLER_LOG = Path(__file__).parents[1] / "supervisor_harness" / (
    "AGENT_LOG_INGAME_DISCOVERY_V3_TWO_MEMBER_POOL_CONTROLLER_2026-09-29.md"
)
CONTROLLER_LOG_SHA256 = (
    "a2c1c060b3ddf63ee3c0e1b6f7baebdba08b550c91be0a7d5585ead9b5dac18f"
)
V0_RUNNER_SHA256 = (
    "e61668c7e29cf4dda95f6cc315b248dbe6744a9dcc0ae0cd6077d880ca6265b7"
)
EXPECTED_V0_HASHES = {
    "manifest.json": "9c6ab11fc553a13e35b410c8763d87a85b535a5ab9b47df8c8dc0d10ac922fc7",
    "pre_score_lock.json": "dc3a8bf1a27795750c44193000480c9279dd47de5d115d6cfad829e5b81d6ef2",
    "input_receipts.json": "0fa0a2444beaddd0a51efd2024c5e6d7c09158db7d6488a59421a99866fdbf18",
    "exclusions.json": "db5b535d261f1e6676beafebeb7aee70833ea1d7988aba25a95c905a9955eaf1",
    "checkpoint_state.csv": "235510db382de2e4b321f11db80b9f5b969c094eb2d122b18ab373e6d31ae96e",
    "predictions.csv": "505e11a4ceb3ae569397bbbc11c6a0be6e9f04a494c9ecb1f4ca40dc06d76d56",
    "scorecard.json": "74c2f23de2ae129ead4d7def1a692d69240ac799582e54db3623865c3525de87",
}

TASK_ID = "InGamePriorPlaySuccessResidualAudit-v2"
QUESTION_ID = "ingame-prior-play-success-residual-v2-q1"
QUESTION_DIGEST = "402ccc0147784eedf540918028d297b2d645d9f374e515bf403e9930682e14f5"
HYPOTHESIS_DIGEST = "53f74d1204bf3c991b68f01455ca4234d86dcd832c01fe7f512970587291b5c3"
RULE_DIGEST = "96c92f3ce51d779412e3953392eb037c2190ef0522fc8454a4f4f6701424b40e"
POOL_PLAN_DIGEST = "415c47dd6f8a6ca99df78a03f102256ba981923b8bfb0992a8f6aea02b87e0a8"
SCHEDULER_BRANCH_BINDING = {
    "allocation": "exploration",
    "attempt_id": "attempt-01",
    "candidate_id": TASK_ID,
    "comparison_incumbent_sha256": "89a8ef92c9cf4844b99e0136c51a1f8b896cdd66afcd23e8b8a23499859ffc7f",
    "controller_decision_sha256": CONTROLLER_LOG_SHA256,
    "hypothesis_digest_sha256": HYPOTHESIS_DIGEST,
    "method_family": "prior_play_success_residual_audit",
    "predeclared_rule_sha256": RULE_DIGEST,
    "question_digest_sha256": QUESTION_DIGEST,
    "question_id": QUESTION_ID,
    "research_parent_sha256": "c40b1df57588b296e72ffe5b220c91aa0dd16d31ef1c573bdb4b0e7c0d72f79d",
    "resource_hint": {
        "authority_granted": False,
        "max_attempts": 1,
        "max_bytes": 0,
        "max_cost_usd": 0.0,
        "max_time_seconds": 180,
        "resource_class": "local_analysis",
    },
}
SCHEDULER_BRANCH_BINDING_SHA256 = (
    "5c9bb22d34b1e950883c2396d653451990f940d4d2fe4cf78bff55a55e64996f"
)
SCHEDULER_SELECTION_SNAPSHOT_SHA256 = (
    "359fb5e57814a745bb81e265db0fe400fcee3cb4ba169d2882ebb0fce8c113ca"
)
SCHEDULER_SELECTION_STATE_SHA256 = (
    "d40e848bfceabeeb47915f1cc0d9e2ee4f1a71653818d2054c494b707d6d4f93"
)
SCHEDULER_SELECTION_JOURNAL_HEAD_SHA256 = (
    "ebc3225a811e7cc12b130b12366ac0f6a2e4f723d44e7cfb7bd54a1cc319130d"
)

EXPECTED_SOURCE_EVENTS = 195
EXPECTED_MATERIALIZED_EVENTS = 193
EXPECTED_CHECK_EVENTS = 87
EXPECTED_CHECK_COUNTS = (26, 16, 28, 17)
EXPECTED_EXCLUSIONS = {
    "2025_04_GB_DAL": "unresolved_outcome",
    "2025_05_TEN_ARI": "market_trade_too_stale",
}
EXPECTED_CHECK_KEY_SHA256 = (
    "2e35779fdbb4b83e129758008338b0c778d7f6281682118ad8d26d21293cc9f9"
)
BOOTSTRAP_SEED = 20260929
BOOTSTRAP_REPLICATES = 10_000
MODEL_FITS = 0


def _sha256(path: Path) -> str:
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def _digest(value: object) -> str:
    body = json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    return hashlib.sha256(body).hexdigest()


def _strict_json(path: Path) -> object:
    def reject_constant(value: str) -> None:
        raise ValueError(f"nonfinite JSON constant forbidden: {value}")

    return json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)


def _atomic_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def _validate_paths(
    source_root: Path, v0_root: Path, output: Path, *, allow_test_paths: bool
) -> None:
    source_root, v0_root, output = (
        source_root.resolve(), v0_root.resolve(), output.resolve()
    )
    if output.exists():
        raise FileExistsError("output already exists; the frozen audit has no retry")
    if source_root == output or source_root in output.parents:
        raise ValueError("output cannot be inside immutable opened-Train source")
    if v0_root == output or v0_root in output.parents:
        raise ValueError("output cannot be inside immutable v0 artifact")
    if allow_test_paths:
        return
    if source_root != SOURCE_ROOT.resolve() or v0_root != V0_ARTIFACT_ROOT.resolve():
        raise ValueError("runner is bound to exact opened Train and reviewed v0 roots")
    try:
        output.relative_to(PERSISTENT_ARTIFACT_ROOT.resolve())
    except ValueError as error:
        raise ValueError("output must be in persistent local MarketRSI artifacts") from error
    lowered = str(output).lower()
    if any(marker in lowered for marker in (
            "/tmp/", "/private/var/", "icloud", "mobile documents",
            "dropbox", "google drive")):
        raise ValueError("temporary or cloud-looking output is forbidden")


def _validate_folds(value: object) -> list[dict]:
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError("exact four v0 folds required")
    result = []
    prior_fit: list[str] | None = None
    prior_check: list[str] = []
    for number, raw in enumerate(value, 1):
        if not isinstance(raw, Mapping) or raw.get("fold") != number:
            raise ValueError("v0 fold identity changed")
        fit, check = raw.get("fit_dates"), raw.get("check_dates")
        if (not isinstance(fit, list) or not isinstance(check, list)
                or len(check) != 5 or fit != sorted(fit) or check != sorted(check)
                or len(set(fit + check)) != len(fit) + len(check)
                or max(fit) >= min(check)):
            raise ValueError("v0 folds are not exact chronological date blocks")
        if prior_fit is not None and fit != prior_fit + prior_check:
            raise ValueError("v0 expanding chronology changed")
        result.append({"fold": number, "fit_dates": fit, "check_dates": check})
        prior_fit, prior_check = list(fit), list(check)
    return result


def _validate_v0_artifact(
    root: Path, *, expected_hashes: dict[str, str] = EXPECTED_V0_HASHES,
    require_exact_counts: bool = True,
) -> dict:
    if set(expected_hashes) != set(EXPECTED_V0_HASHES):
        raise ValueError("v0 hash map must name every frozen input")
    hashes = {}
    for name, expected in expected_hashes.items():
        path = root / name
        if not path.is_file():
            raise ValueError(f"frozen v0 file missing: {name}")
        hashes[name] = _sha256(path)
        if hashes[name] != expected:
            raise ValueError(f"frozen v0 file hash changed: {name}")
    manifest = _strict_json(root / "manifest.json")
    lock = _strict_json(root / "pre_score_lock.json")
    receipts = _strict_json(root / "input_receipts.json")
    exclusions = _strict_json(root / "exclusions.json")
    scorecard = _strict_json(root / "scorecard.json")
    if not all(isinstance(item, dict) for item in (
            manifest, lock, receipts, exclusions, scorecard)):
        raise ValueError("frozen v0 JSON roots must be objects")
    if (manifest.get("complete") is not True
            or manifest.get("task_id") != "InGameWinProbabilityTrainDiagnostic-v0"
            or manifest.get("source_events") != EXPECTED_SOURCE_EVENTS
            or manifest.get("materialized_events") != EXPECTED_MATERIALIZED_EVENTS
            or manifest.get("excluded_events") != len(EXPECTED_EXCLUSIONS)
            or manifest.get("check_events") != EXPECTED_CHECK_EVENTS
            or manifest.get("route_dev_opened") is not False
            or manifest.get("sealed_final_opened") is not False
            or manifest.get("external_fetch") is not False
            or manifest.get("provider_cost_usd") != "0"
            or manifest.get("promotion_authorized") is not False):
        raise ValueError("v0 lineage or protected-data boundary changed")
    for name, key in (
        ("pre_score_lock.json", "pre_score_lock_sha256"),
        ("input_receipts.json", "input_receipts_sha256"),
        ("exclusions.json", "exclusions_sha256"),
        ("predictions.csv", "predictions_sha256"),
        ("scorecard.json", "scorecard_sha256"),
    ):
        if manifest.get(key) != hashes[name]:
            raise ValueError(f"v0 manifest no longer binds {name}")
    if receipts.get("checkpoint_state_sha256") != hashes["checkpoint_state.csv"]:
        raise ValueError("v0 receipt no longer binds checkpoint state")
    folds = _validate_folds(lock.get("folds"))

    excluded_rows = exclusions.get("exclusions")
    if not isinstance(excluded_rows, list) or {
        str(row.get("game_id")): str(row.get("reason")) for row in excluded_rows
    } != EXPECTED_EXCLUSIONS:
        raise ValueError("v0 exact two named exclusions changed")
    anchors = _read_csv(root / "checkpoint_state.csv")
    predictions = _read_csv(root / "predictions.csv")
    if (len({row.get("game_id") for row in anchors}) != len(anchors)
            or len({row.get("game_id") for row in predictions}) != len(predictions)):
        raise ValueError("v0 anchor or prediction game identity is duplicated")
    if require_exact_counts and (
            len(anchors) != EXPECTED_SOURCE_EVENTS
            or len(predictions) != EXPECTED_CHECK_EVENTS):
        raise ValueError("v0 source/check population changed")
    if any(row.get("status") != "eligible" for row in anchors):
        raise ValueError("every frozen v0 checkpoint anchor must be eligible")
    counts = tuple(sum(int(row["fold"]) == number for row in predictions)
                   for number in (1, 2, 3, 4))
    if require_exact_counts and counts != EXPECTED_CHECK_COUNTS:
        raise ValueError("v0 fold check counts changed")
    for row in predictions:
        fold_number = int(row["fold"])
        if row["game_date"] not in folds[fold_number - 1]["check_dates"]:
            raise ValueError("v0 prediction is outside its frozen check-date fold")
        outcome = int(row["outcome"])
        probability = float(row["raw_market_probability"])
        if outcome not in (0, 1) or not math.isfinite(probability) or not 0 < probability < 1:
            raise ValueError("v0 label or raw market probability is invalid")
    check_key = _digest([
        [row["event_id"], row["market_id"], int(row["cutoff_ms"])]
        for row in predictions
    ])
    if (check_key != EXPECTED_CHECK_KEY_SHA256
            or scorecard.get("identical_masks", {}).get("check_key_sha256") != check_key):
        raise ValueError("v0 exact 87-game common mask changed")
    return {
        "hashes": hashes,
        "manifest": manifest,
        "lock": lock,
        "receipts": receipts,
        "folds": folds,
        "anchors": anchors,
        "predictions": predictions,
        "excluded_game_ids": set(EXPECTED_EXCLUSIONS),
        "check_key_sha256": check_key,
    }


def _validate_source_and_receipts(source_root: Path, frozen: dict) -> dict:
    cohort = v0._validate_source(
        source_root, expected_events=EXPECTED_SOURCE_EVENTS,
        expected_dates=v0.EXPECTED_DATES, allow_test_paths=False,
    )
    observed = v0._validate_pbp_receipts(source_root, cohort)
    if observed != frozen["receipts"].get("pbp_receipts"):
        raise ValueError("opened-Train PBP receipt set differs from frozen v0 inputs")
    if (frozen["receipts"].get("source_manifest_sha256")
            != _sha256(source_root / "manifest.json")
            or frozen["receipts"].get("cohort_sha256")
            != _sha256(source_root / "cohort.csv")):
        raise ValueError("opened-Train source/cohort differs from frozen v0 inputs")
    return {
        "source_manifest_sha256": _sha256(source_root / "manifest.json"),
        "cohort_sha256": _sha256(source_root / "cohort.csv"),
        "pbp_receipts_sha256": _digest(observed),
        "pbp_games": len(observed),
    }


def _extract_indicator(source_root: Path, anchor_path: Path, output: Path) -> None:
    if not EXTRACTOR.is_file():
        raise ValueError("prior-play success extractor is missing")
    subprocess.run(
        ["Rscript", str(EXTRACTOR), str(source_root), str(anchor_path), str(output)],
        check=True, capture_output=True, text=True, timeout=180,
    )


def _finite(row: Mapping[str, str], name: str) -> float:
    try:
        value = float(row[name])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"{name} is missing or nonnumeric") from error
    if not math.isfinite(value):
        raise ValueError(f"{name} is nonfinite")
    return value


def _load_indicators(path: Path, frozen: dict) -> dict[str, dict]:
    rows = _read_csv(path)
    if (len(rows) != EXPECTED_SOURCE_EVENTS
            or len({row.get("game_id") for row in rows}) != len(rows)):
        raise ValueError("indicator extraction did not preserve the 195-game denominator")
    anchors = {row["game_id"]: row for row in frozen["anchors"]}
    result = {}
    for row in rows:
        game_id = row.get("game_id")
        if game_id not in anchors:
            raise ValueError("indicator row is not bound to a frozen v0 anchor")
        anchor = anchors[game_id]
        if (row.get("anchor_play_id") != anchor["play_id"]
                or _finite(row, "anchor_order_sequence")
                != _finite(anchor, "order_sequence")):
            raise ValueError("indicator anchor identity/order differs from v0")
        if game_id in frozen["excluded_game_ids"]:
            continue
        if row.get("status") != "eligible":
            raise ValueError(
                f"materialized game lacks both-side prior eligible plays: {game_id}"
            )
        home_count = _finite(row, "home_eligible_plays")
        away_count = _finite(row, "away_eligible_plays")
        home_successes = _finite(row, "home_successes")
        away_successes = _finite(row, "away_successes")
        home_rate = _finite(row, "home_success_rate")
        away_rate = _finite(row, "away_success_rate")
        signal = _finite(row, "home_minus_away_success_rate")
        if (home_count < 1 or away_count < 1
                or home_count != int(home_count) or away_count != int(away_count)
                or not 0 <= home_successes <= home_count
                or not 0 <= away_successes <= away_count
                or not math.isclose(home_rate, home_successes / home_count, abs_tol=1e-15)
                or not math.isclose(away_rate, away_successes / away_count, abs_tol=1e-15)
                or not math.isclose(signal, home_rate - away_rate, abs_tol=1e-15)):
            raise ValueError(f"prior-play success arithmetic failed: {game_id}")
        result[game_id] = {
            "signal": signal,
            "home_eligible_plays": int(home_count),
            "home_successes": int(home_successes),
            "away_eligible_plays": int(away_count),
            "away_successes": int(away_successes),
            "home_success_rate": home_rate,
            "away_success_rate": away_rate,
        }
    if len(result) != EXPECTED_MATERIALIZED_EVENTS:
        raise ValueError("indicator extraction introduced an undeclared exclusion")
    return result


def _directional_terms(
    outcome: int, probability: float, signal: float
) -> tuple[float, float, float]:
    if outcome not in (0, 1) or not all(
            math.isfinite(value) for value in (probability, signal)):
        raise ValueError("directional term inputs are invalid or nonfinite")
    if not 0 < probability < 1:
        raise ValueError("raw market probability must be strictly inside (0,1)")
    residual = outcome - probability
    return (
        residual,
        signal * residual,
        signal * residual * probability * (1 - probability),
    )


def _event_records(frozen: dict, indicators: Mapping[str, dict]) -> list[dict]:
    records = []
    for raw in frozen["predictions"]:
        game_id = raw["game_id"]
        if game_id not in indicators:
            raise ValueError("exact v0 check row lacks a prior-play signal")
        outcome = int(raw["outcome"])
        probability = float(raw["raw_market_probability"])
        signal = indicators[game_id]["signal"]
        residual, log_alignment, brier_logit_alignment = _directional_terms(
            outcome, probability, signal
        )
        values = (signal, residual, log_alignment, brier_logit_alignment)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("nonfinite residual audit evidence")
        records.append({
            "fold": int(raw["fold"]),
            "game_id": game_id,
            "game_date": raw["game_date"],
            "game_week": raw["game_week"],
            "outcome": outcome,
            "raw_market_probability": probability,
            **indicators[game_id],
            "market_residual": residual,
            "log_loss_directional_alignment": log_alignment,
            "brier_logit_directional_alignment": brier_logit_alignment,
        })
    if (len(records) != EXPECTED_CHECK_EVENTS
            or len({row["game_id"] for row in records}) != len(records)):
        raise ValueError("audit did not preserve the exact 87 unique v0 check games")
    return records


def _average_ranks(values: Sequence[float]) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.ndim != 1 or len(array) < 2 or not np.isfinite(array).all():
        raise ValueError("rank input must be a finite one-dimensional sample")
    order = np.argsort(array, kind="mergesort")
    ranks = np.empty(len(array), dtype=float)
    start = 0
    while start < len(array):
        stop = start + 1
        while stop < len(array) and array[order[stop]] == array[order[start]]:
            stop += 1
        ranks[order[start:stop]] = (start + 1 + stop) / 2
        start = stop
    return ranks


def _pearson(left: Sequence[float], right: Sequence[float]) -> float:
    x, y = np.asarray(left, dtype=float), np.asarray(right, dtype=float)
    if x.shape != y.shape or x.ndim != 1 or len(x) < 2:
        raise ValueError("Pearson inputs must be paired nonempty vectors")
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("Pearson inputs are nonfinite")
    x_centered, y_centered = x - x.mean(), y - y.mean()
    denominator = float(np.linalg.norm(x_centered) * np.linalg.norm(y_centered))
    if denominator == 0:
        raise ValueError("Pearson association is undefined for a constant vector")
    return float(np.dot(x_centered, y_centered) / denominator)


def _association_metrics(records: Sequence[dict]) -> dict:
    signals = [row["signal"] for row in records]
    residuals = [row["market_residual"] for row in records]
    return {
        "events": len(records),
        "pearson_signal_vs_market_residual": _pearson(signals, residuals),
        "spearman_signal_vs_market_residual": _pearson(
            _average_ranks(signals), _average_ranks(residuals)
        ),
        "mean_log_loss_directional_alignment": math.fsum(
            row["log_loss_directional_alignment"] for row in records
        ) / len(records),
        "mean_brier_logit_directional_alignment": math.fsum(
            row["brier_logit_directional_alignment"] for row in records
        ) / len(records),
    }


def _group_bootstrap(
    records: Sequence[dict], group: str, value: str, *,
    seed: int = BOOTSTRAP_SEED, replicates: int = BOOTSTRAP_REPLICATES,
) -> dict:
    buckets: dict[str, list[float]] = defaultdict(list)
    for row in records:
        buckets[str(row[group])].append(float(row[value]))
    labels = sorted(buckets)
    if len(labels) < 2:
        raise ValueError("complete-group bootstrap requires at least two groups")
    generator = np.random.default_rng(seed)
    draws = []
    for _ in range(replicates):
        sample = generator.choice(labels, size=len(labels), replace=True)
        values = [item for label in sample for item in buckets[str(label)]]
        draws.append(math.fsum(values) / len(values))
    point = math.fsum(row[value] for row in records) / len(records)
    return {
        "group": group,
        "groups": len(labels),
        "events": len(records),
        "value": value,
        "point_equal_event_mean": point,
        "interval_95": [
            float(np.quantile(draws, 0.025, method="linear")),
            float(np.quantile(draws, 0.975, method="linear")),
        ],
        "bootstrap_replicates": replicates,
        "bootstrap_seed": seed,
        "resampling_rule": (
            "resample complete groups and recompute the pooled equal-event mean "
            "within every draw"
        ),
    }


def audit_decision(
    aggregate: Mapping[str, float], folds: Sequence[Mapping[str, float]],
    date_log_alignment_interval: Mapping[str, object],
    week_log_alignment_interval: Mapping[str, object],
) -> tuple[str, dict]:
    positive_folds = sum(
        fold["mean_log_loss_directional_alignment"] > 0 for fold in folds
    )
    date_interval = date_log_alignment_interval["interval_95"]
    week_interval = week_log_alignment_interval["interval_95"]
    if (not isinstance(date_interval, list) or len(date_interval) != 2
            or not isinstance(week_interval, list) or len(week_interval) != 2):
        raise ValueError("grouped log-alignment intervals are malformed")
    values = [
        aggregate["pearson_signal_vs_market_residual"],
        aggregate["spearman_signal_vs_market_residual"],
        aggregate["mean_log_loss_directional_alignment"],
        aggregate["mean_brier_logit_directional_alignment"],
        *date_interval, *week_interval,
    ]
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("decision evidence is nonfinite")
    support = {
        "pearson_positive": aggregate["pearson_signal_vs_market_residual"] > 0,
        "spearman_positive": aggregate["spearman_signal_vs_market_residual"] > 0,
        "log_loss_alignment_positive": (
            aggregate["mean_log_loss_directional_alignment"] > 0
        ),
        "brier_logit_alignment_positive": (
            aggregate["mean_brier_logit_directional_alignment"] > 0
        ),
        "date_grouped_log_alignment_lower_bound_positive": date_interval[0] > 0,
        "week_grouped_log_alignment_lower_bound_positive": week_interval[0] > 0,
        "positive_log_alignment_folds_at_least_3_of_4": positive_folds >= 3,
    }
    refute = {
        "both_associations_nonpositive": (
            aggregate["pearson_signal_vs_market_residual"] <= 0
            and aggregate["spearman_signal_vs_market_residual"] <= 0
        ),
        "both_directional_alignments_nonpositive": (
            aggregate["mean_log_loss_directional_alignment"] <= 0
            and aggregate["mean_brier_logit_directional_alignment"] <= 0
        ),
        "positive_log_alignment_folds_at_most_1_of_4": positive_folds <= 1,
    }
    if all(support.values()):
        decision = "PRIOR_PLAY_SUCCESS_RESIDUAL_SUPPORTED"
    elif any(refute.values()):
        decision = "PRIOR_PLAY_SUCCESS_RESIDUAL_REFUTED"
    else:
        decision = "PRIOR_PLAY_SUCCESS_RESIDUAL_INCONCLUSIVE"
    return decision, {
        "positive_log_alignment_folds": positive_folds,
        "support_conditions": support,
        "refute_conditions": refute,
    }


def _audit(records: Sequence[dict]) -> dict:
    aggregate = _association_metrics(records)
    folds = []
    for number in (1, 2, 3, 4):
        fold_records = [row for row in records if row["fold"] == number]
        folds.append({
            "fold": number,
            "check_dates": len({row["game_date"] for row in fold_records}),
            "check_game_weeks": len({row["game_week"] for row in fold_records}),
            **_association_metrics(fold_records),
        })
    intervals = {}
    for metric in (
        "log_loss_directional_alignment", "brier_logit_directional_alignment"
    ):
        intervals[metric] = {
            "schedule_date": _group_bootstrap(records, "game_date", metric),
            "observed_game_week": _group_bootstrap(records, "game_week", metric),
        }
    decision, conditions = audit_decision(
        aggregate, folds,
        intervals["log_loss_directional_alignment"]["schedule_date"],
        intervals["log_loss_directional_alignment"]["observed_game_week"],
    )
    return {
        "decision": decision,
        "conditions": conditions,
        "aggregate": aggregate,
        "folds": folds,
        "complete_group_intervals": intervals,
    }


def _write_event_audit(path: Path, records: Sequence[dict]) -> None:
    fields = (
        "fold", "game_id", "game_date", "game_week", "outcome",
        "raw_market_probability", "home_eligible_plays", "home_successes",
        "away_eligible_plays", "away_successes", "home_success_rate",
        "away_success_rate", "home_minus_away_success_rate", "market_residual",
        "log_loss_directional_alignment", "brier_logit_directional_alignment",
    )
    temporary = path.with_suffix(".csv.tmp")
    with temporary.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in records:
            writer.writerow({
                **{key: row[key] for key in fields if key not in {
                    "home_minus_away_success_rate"
                }},
                "home_minus_away_success_rate": row["signal"],
            })
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def run(
    source_root: Path,
    v0_root: Path,
    output: Path,
    *,
    allow_test_paths: bool = False,
    expected_v0_hashes: dict[str, str] | None = None,
    generated_utc: str | None = None,
) -> dict:
    source_root, v0_root, output = (
        Path(source_root).resolve(), Path(v0_root).resolve(), Path(output).resolve()
    )
    _validate_paths(
        source_root, v0_root, output, allow_test_paths=allow_test_paths
    )
    if not allow_test_paths:
        if _sha256(CONTROLLER_LOG) != CONTROLLER_LOG_SHA256:
            raise ValueError("frozen v3 Controller log hash changed")
        if _sha256(Path(v0.__file__)) != V0_RUNNER_SHA256:
            raise ValueError("frozen v0 dependency hash changed")
        if _digest(SCHEDULER_BRANCH_BINDING) != SCHEDULER_BRANCH_BINDING_SHA256:
            raise ValueError("scheduler branch binding digest changed")
    frozen = _validate_v0_artifact(
        v0_root,
        expected_hashes=(
            EXPECTED_V0_HASHES if expected_v0_hashes is None else expected_v0_hashes
        ),
        require_exact_counts=not allow_test_paths,
    )
    source_receipt = (
        _validate_source_and_receipts(source_root, frozen)
        if not allow_test_paths else {}
    )
    output.mkdir(parents=True, exist_ok=False)
    try:
        indicator_path = output / "prior_play_success.csv"
        _extract_indicator(
            source_root, v0_root / "checkpoint_state.csv", indicator_path
        )
        indicators = _load_indicators(indicator_path, frozen)
        records = _event_records(frozen, indicators)
        analysis = _audit(records)
        lock = {
            "schema": "nfl_ingame_prior_play_success_residual_pre_audit_lock_v2",
            "generated_utc": generated_utc or datetime.now(timezone.utc).isoformat(),
            "task_id": TASK_ID,
            "question_id": QUESTION_ID,
            "question_digest_sha256": QUESTION_DIGEST,
            "hypothesis_digest_sha256": HYPOTHESIS_DIGEST,
            "predeclared_rule_sha256": RULE_DIGEST,
            "pool_plan_sha256": POOL_PLAN_DIGEST,
            "controller_log_sha256": CONTROLLER_LOG_SHA256,
            "scheduler_branch_binding": SCHEDULER_BRANCH_BINDING,
            "scheduler_branch_binding_sha256": SCHEDULER_BRANCH_BINDING_SHA256,
            "scheduler_selection_snapshot_sha256": SCHEDULER_SELECTION_SNAPSHOT_SHA256,
            "scheduler_selection_state_sha256": SCHEDULER_SELECTION_STATE_SHA256,
            "scheduler_selection_journal_head_sha256": SCHEDULER_SELECTION_JOURNAL_HEAD_SHA256,
            "research_parent": "archived v0 market-plus-state negative branch",
            "comparison_incumbent": "v0 task-local raw market",
            "prediction_candidate": False,
            "model_fits": MODEL_FITS,
            "success_definition": {
                "down_1": "yards >= 0.45 * yardsToGo",
                "down_2": "yards >= 0.60 * yardsToGo",
                "down_3_or_4": "yards >= yardsToGo",
            },
            "eligible_play_rule": (
                "nondeleted, valid timed and typed play, orderSequence strictly below "
                "the exact v0 anchor, down 1-4, finite yards/yardsToGo, and possession "
                "identified exactly as home or away"
            ),
            "indicator": "home eligible-play success rate minus away eligible-play success rate",
            "missing_side_rule": "integrity failure; no row drop or imputation",
            "metrics": [
                "Pearson(signal,y-p_raw)", "Spearman(signal,y-p_raw)",
                "mean signal*(y-p_raw)",
                "mean signal*(y-p_raw)*p_raw*(1-p_raw)",
            ],
            "bootstrap_seed": BOOTSTRAP_SEED,
            "bootstrap_replicates_each_for_date_and_week": BOOTSTRAP_REPLICATES,
            "one_audit_no_retry": True,
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "external_fetch": False,
            "paid_provider": False,
            "provider_cost_usd": "0",
            "promotion_authorized": False,
        }
        _atomic_json(output / "pre_audit_lock.json", lock)
        _write_event_audit(output / "event_audit.csv", records)
        scorecard = {
            "schema": "nfl_ingame_prior_play_success_residual_scorecard_v2",
            "task_id": TASK_ID,
            "question_id": QUESTION_ID,
            **analysis,
            "source_lineage": {
                "source_events": EXPECTED_SOURCE_EVENTS,
                "materialized_events": EXPECTED_MATERIALIZED_EVENTS,
                "excluded_events": len(EXPECTED_EXCLUSIONS),
                "check_events": len(records),
                "check_dates": len({row["game_date"] for row in records}),
                "check_game_weeks": len({row["game_week"] for row in records}),
                "v0_check_key_sha256": frozen["check_key_sha256"],
            },
            "no_rows_dropped_from_v0_common_mask": True,
            "model_fits": MODEL_FITS,
            "no_prediction_candidate_emitted": True,
            "incumbent_or_keep_revert_changed": False,
            "research_credit_eligibility_after_independent_review": (
                2 if analysis["decision"]
                != "PRIOR_PLAY_SUCCESS_RESIDUAL_INCONCLUSIVE" else 1
            ),
            "research_credit_awarded": 0,
            "evidence_classification": "raw temporal-data directional-increment diagnostic; no model or mechanism gain tested",
            "inference_boundary": (
                "repeatedly inspected opened-Train historical PBP order; publish/receive "
                "latency is unobserved; not realtime, untouched OOS, prediction gain, "
                "promotion, PnL, or cross-task evidence"
            ),
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "external_fetch": False,
            "paid_provider": False,
            "provider_cost_usd": "0",
            "promotion_authorized": False,
        }
        _atomic_json(output / "scorecard.json", scorecard)
        input_receipts = {
            "schema": "nfl_ingame_prior_play_success_residual_inputs_v2",
            "task_id": TASK_ID,
            "runner_sha256": _sha256(Path(__file__)),
            "extractor_sha256": _sha256(EXTRACTOR),
            "v0_runner_sha256": _sha256(Path(v0.__file__)),
            "v0_artifact_hashes": frozen["hashes"],
            **source_receipt,
            "indicator_sha256": _sha256(indicator_path),
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "external_fetch": False,
            "provider_cost_usd": "0",
        }
        _atomic_json(output / "input_receipts.json", input_receipts)
        manifest = {
            "schema": "nfl_ingame_prior_play_success_residual_manifest_v2",
            "complete": True,
            "completed_utc": generated_utc or datetime.now(timezone.utc).isoformat(),
            "task_id": TASK_ID,
            "decision": analysis["decision"],
            "source_events": EXPECTED_SOURCE_EVENTS,
            "materialized_events": EXPECTED_MATERIALIZED_EVENTS,
            "excluded_events": len(EXPECTED_EXCLUSIONS),
            "check_events": len(records),
            "model_fits": MODEL_FITS,
            "prior_play_success_sha256": _sha256(indicator_path),
            "pre_audit_lock_sha256": _sha256(output / "pre_audit_lock.json"),
            "event_audit_sha256": _sha256(output / "event_audit.csv"),
            "scorecard_sha256": _sha256(output / "scorecard.json"),
            "input_receipts_sha256": _sha256(output / "input_receipts.json"),
            "v0_manifest_sha256": frozen["hashes"]["manifest.json"],
            "v0_predictions_sha256": frozen["hashes"]["predictions.csv"],
            "no_prediction_candidate_emitted": True,
            "incumbent_or_keep_revert_changed": False,
            "historical_event_order_only": True,
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
                "schema": "nfl_ingame_prior_play_success_residual_failure_v2",
                "error_type": type(error).__name__,
                "error": str(error)[:1200],
                "model_fits": MODEL_FITS,
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
    parser.add_argument("--v0-artifact", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.source_root, args.v0_artifact, args.output)
    print(json.dumps({
        "complete": result["complete"],
        "task_id": result["task_id"],
        "decision": result["decision"],
        "check_events": result["check_events"],
        "model_fits": result["model_fits"],
        "provider_cost_usd": result["provider_cost_usd"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
