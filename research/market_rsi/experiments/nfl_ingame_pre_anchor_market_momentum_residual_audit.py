#!/usr/bin/env python3
"""Zero-fit opened-Train audit of strictly-prior market-logit momentum."""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from experiments import nfl_ingame_prior_play_success_residual_audit as prior
from experiments import nfl_ingame_win_probability_train_diagnostic as v0
from experiments import nfl_settlement_probability_train_diagnostic as settlement


V0_ARTIFACT_ROOT = prior.V0_ARTIFACT_ROOT
SOURCE_ROOT = v0.SOURCE_ROOT
PERSISTENT_ARTIFACT_ROOT = v0.PERSISTENT_ARTIFACT_ROOT
CONTROLLER_LOG = Path(__file__).parents[1] / "supervisor_harness" / (
    "AGENT_LOG_INGAME_DISCOVERY_V3_GENERATION2_TWO_MEMBER_POOL_CONTROLLER_2026-09-29.md"
)
CONTROLLER_LOG_SHA256 = "4186a3554b7f7aed50596123c135943dbf986d5e39b84fe507fac91c6e04e986"
V0_RUNNER_SHA256 = "e61668c7e29cf4dda95f6cc315b248dbe6744a9dcc0ae0cd6077d880ca6265b7"
PRIOR_VALIDATOR_SHA256 = "a612371ae77a78441c2d9416d6edc035a916879057fed9ef731de46476a07bcb"
SETTLEMENT_DEPENDENCY_SHA256 = "1f1bdccd69d799be1af99ece4ee6198ffbd02f3a4550e651936fb3edfa83fb8b"

TASK_ID = "InGamePreAnchorMarketMomentumResidualAudit-v3"
QUESTION_ID = "ingame-pre-anchor-market-momentum-residual-v3-q1"
QUESTION_DIGEST = "f82528a6d379831c10e9d98979d29fc9cb77037fd5749ad9f59f041214b1ddfa"
HYPOTHESIS_DIGEST = "d581adb57a3a6d554bd23248d9325c8fb0d2082db8c73c74fd944f616b5e9d6d"
RULE_DIGEST = "d1a3369bbedc9c9c01848986ecf7c387bfeef6c124e9d1e85343ab19e68f2270"
SELECTION_PLAN_DIGEST = "c10ed553121ac9c0da123138a4e3d7b2f03979cf7143dc7092b8d8dad513a92c"
SCHEDULER_BRANCH_BINDING = {
    "allocation": "exploration",
    "attempt_id": "attempt-04",
    "candidate_id": TASK_ID,
    "comparison_incumbent_sha256": "89a8ef92c9cf4844b99e0136c51a1f8b896cdd66afcd23e8b8a23499859ffc7f",
    "controller_decision_sha256": CONTROLLER_LOG_SHA256,
    "hypothesis_digest_sha256": HYPOTHESIS_DIGEST,
    "method_family": "pre_anchor_market_momentum_residual_audit",
    "pool_generation": 2,
    "predeclared_rule_sha256": RULE_DIGEST,
    "question_digest_sha256": QUESTION_DIGEST,
    "question_id": QUESTION_ID,
    "research_parent_sha256": "c40b1df57588b296e72ffe5b220c91aa0dd16d31ef1c573bdb4b0e7c0d72f79d",
    "resource_hint": {
        "authority_granted": False, "max_attempts": 1, "max_bytes": 0,
        "max_cost_usd": 0.0, "max_time_seconds": 300,
        "resource_class": "local_analysis",
    },
    "selection_hint_sha256": "d5a34817985da019fd14a7f36bec12ed411bed2a983e664a3960a00b491ecd71",
}
SCHEDULER_BRANCH_BINDING_SHA256 = "c033d747aedf039e8d1369ed6fd9ca207d93b18947193f99a62129c76d0e5433"
SCHEDULER_SELECTION_STATE_SHA256 = "69ad82c5938b4b8793cd29e0af22471658315d75737959c77cc6ced48e2b8627"
SCHEDULER_SELECTION_JOURNAL_HEAD_SHA256 = "cb737d39ce98748f0cced47b73fcddff8c9df993a3941e15b4bf6b0047efbb06"

REFERENCE_LAG_SECONDS = 120
MAX_REFERENCE_STALENESS_SECONDS = 300
LOGIT_EPSILON = 1e-6
BOOTSTRAP_SEED = 20260929
BOOTSTRAP_REPLICATES = 10_000
MODEL_FITS = 0


def _sha256(path: Path) -> str:
    return settlement._sha256(Path(path))


def _digest(value: object) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(body).hexdigest()


def _strict_json(path: Path) -> object:
    return prior._strict_json(path)


def _atomic_json(path: Path, value: object) -> None:
    prior._atomic_json(path, value)


def _validate_paths(source_root: Path, v0_root: Path, output: Path, *, allow_test_paths: bool) -> None:
    source_root, v0_root, output = source_root.resolve(), v0_root.resolve(), output.resolve()
    if output.exists():
        raise FileExistsError("output already exists; the frozen audit has no retry")
    if source_root == output or source_root in output.parents or v0_root == output or v0_root in output.parents:
        raise ValueError("output cannot be inside an immutable input")
    if allow_test_paths:
        return
    if source_root != SOURCE_ROOT.resolve() or v0_root != V0_ARTIFACT_ROOT.resolve():
        raise ValueError("runner is bound to exact opened Train and reviewed v0 roots")
    try:
        output.relative_to(PERSISTENT_ARTIFACT_ROOT.resolve())
    except ValueError as error:
        raise ValueError("output must be in persistent local MarketRSI artifacts") from error
    lowered = str(output).lower()
    if any(marker in lowered for marker in ("/tmp/", "/private/var/", "icloud", "mobile documents", "dropbox", "google drive")):
        raise ValueError("temporary or cloud-looking output is forbidden")


def _validate_execution_identity() -> None:
    checks = (
        (CONTROLLER_LOG, CONTROLLER_LOG_SHA256, "Controller"),
        (Path(v0.__file__), V0_RUNNER_SHA256, "v0 runner"),
        (Path(prior.__file__), PRIOR_VALIDATOR_SHA256, "v0 validator"),
        (Path(settlement.__file__), SETTLEMENT_DEPENDENCY_SHA256, "settlement dependency"),
    )
    for path, expected, label in checks:
        if _sha256(path) != expected:
            raise ValueError(f"frozen {label} hash changed")
    if _digest(SCHEDULER_BRANCH_BINDING) != SCHEDULER_BRANCH_BINDING_SHA256:
        raise ValueError("scheduler branch binding digest changed")


def _clipped_logit(probability: float) -> float:
    if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
        raise ValueError("market probability is nonfinite or outside [0,1]")
    clipped = min(1.0 - LOGIT_EPSILON, max(LOGIT_EPSILON, probability))
    return math.log(clipped / (1.0 - clipped))


def _latest_fill_second(trades: Sequence[dict], exclusive_cutoff_s: int) -> tuple[float, int]:
    eligible = [row for row in trades if int(row["timestamp"]) < exclusive_cutoff_s]
    if not eligible:
        raise ValueError("no trade strictly before frozen cutoff")
    latest_second = max(int(row["timestamp"]) for row in eligible)
    latest = [row for row in eligible if int(row["timestamp"]) == latest_second]
    probability, _ = settlement._weighted_probability(latest)
    if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
        raise ValueError("latest fill-second probability is invalid")
    return probability, latest_second


def market_momentum_signal(trades: Sequence[dict], decision_floor_s: int) -> dict:
    """Compute the frozen signal without reading an outcome or check label."""
    if isinstance(decision_floor_s, bool) or not isinstance(decision_floor_s, int):
        raise ValueError("decision floor must be an integer epoch second")
    p_now, current_second = _latest_fill_second(trades, decision_floor_s)
    reference_cutoff = decision_floor_s - REFERENCE_LAG_SECONDS
    p_ref, reference_second = _latest_fill_second(trades, reference_cutoff)
    reference_age = reference_cutoff - reference_second
    if reference_age <= 0 or reference_age > MAX_REFERENCE_STALENESS_SECONDS:
        raise ValueError("reference fill is outside frozen (0,300] second age gate")
    signal = _clipped_logit(p_now) - _clipped_logit(p_ref)
    if not math.isfinite(signal):
        raise ValueError("market momentum signal is nonfinite")
    return {
        "p_now": p_now, "p_ref": p_ref, "signal": signal,
        "decision_floor_epoch_s": decision_floor_s,
        "current_latest_trade_epoch_s": current_second,
        "reference_cutoff_epoch_s": reference_cutoff,
        "reference_latest_trade_epoch_s": reference_second,
        "reference_age_seconds": reference_age,
    }


def _load_oriented_trades(source_root: Path, cohort: Mapping[str, str],
                          anchor: Mapping[str, str], receipt: Mapping[str, object]) -> tuple[list[dict], dict]:
    game_id = str(cohort["game_id"])
    meta_path = source_root / "catalog" / f"{game_id}.json"
    raw_path = source_root / "catalog" / f"{game_id}.raw.json.gz"
    trade_root = source_root / "trades" / game_id
    manifest_path, trade_path = trade_root / "manifest.json", trade_root / "trade_window.csv"
    meta = _strict_json(meta_path)
    if not isinstance(meta, dict) or any(meta.get(key) != cohort[key] for key in ("game_id", "game_date", "event_slug")):
        raise ValueError("catalog identity differs from cohort")
    compressed = raw_path.read_bytes()
    if _sha256(meta_path) != receipt.get("catalog_meta_sha256") or _sha256(raw_path) != receipt.get("catalog_stored_sha256"):
        raise ValueError("catalog receipt changed")
    raw = gzip.decompress(compressed)
    if hashlib.sha256(raw).hexdigest() != receipt.get("catalog_raw_sha256"):
        raise ValueError("raw catalog receipt changed")
    event = json.loads(raw)
    market = settlement._selected_market(event, meta)
    orientation = settlement.orient_market(game_id, market, meta["tokens"])
    home = settlement.GAME_TEAM_ALIASES.get(anchor.get("home_team", ""), anchor.get("home_team", ""))
    away = settlement.GAME_TEAM_ALIASES.get(anchor.get("away_team", ""), anchor.get("away_team", ""))
    if home != orientation["home_team"] or away != orientation["away_team"]:
        raise ValueError("PBP and market home/away orientation differ")
    trade_manifest = _strict_json(manifest_path)
    if (not isinstance(trade_manifest, dict) or trade_manifest.get("complete") is not True
            or trade_manifest.get("dev_final_opened") is not False
            or trade_manifest.get("trade_window_sha256") != _sha256(trade_path)
            or _sha256(manifest_path) != receipt.get("trade_manifest_sha256")
            or _sha256(trade_path) != receipt.get("trade_window_sha256")):
        raise ValueError("trade receipt or protected boundary changed")
    trades = settlement._load_trades(trade_path, meta, orientation, str(cohort["event_slug"]))
    return trades, {
        "game_id": game_id, "catalog_meta_sha256": _sha256(meta_path),
        "catalog_stored_sha256": _sha256(raw_path),
        "catalog_raw_sha256": hashlib.sha256(raw).hexdigest(),
        "trade_manifest_sha256": _sha256(manifest_path),
        "trade_window_sha256": _sha256(trade_path),
        "home_team": orientation["home_team"], "home_token_id": orientation["home_token"],
    }


def _extract_market_signals(source_root: Path, frozen: dict, cohort: Sequence[dict]) -> tuple[list[dict], list[dict]]:
    cohort_by_id = {row["game_id"]: row for row in cohort}
    anchor_by_id = {row["game_id"]: row for row in frozen["anchors"]}
    materialized = frozen["receipts"].get("materialized_receipts")
    if not isinstance(materialized, list) or len(materialized) != prior.EXPECTED_MATERIALIZED_EVENTS:
        raise ValueError("v0 materialized receipt population changed")
    receipt_by_id = {str(row.get("game_id")): row for row in materialized}
    if len(receipt_by_id) != len(materialized):
        raise ValueError("v0 materialized receipt identity is duplicated")
    rows, receipts = [], []
    for prediction in frozen["predictions"]:
        game_id = prediction["game_id"]
        if game_id not in cohort_by_id or game_id not in anchor_by_id or game_id not in receipt_by_id:
            raise ValueError("check game lacks frozen cohort/anchor/materialized receipt")
        anchor, old_receipt = anchor_by_id[game_id], receipt_by_id[game_id]
        decision_time = settlement._utc(anchor["decision_time_utc"], "v0 decision time")
        decision_floor = math.floor(decision_time.timestamp())
        if int(prediction["cutoff_ms"]) // 1000 != decision_floor:
            raise ValueError("v0 decision timestamp and check cutoff differ")
        if int(old_receipt["market_feature_cutoff_epoch_s"]) != decision_floor - 1:
            raise ValueError("v0 strictly-prior current-market cutoff changed")
        trades, source_receipt = _load_oriented_trades(
            source_root, cohort_by_id[game_id], anchor, old_receipt
        )
        momentum = market_momentum_signal(trades, decision_floor)
        expected_now = float(prediction["raw_market_probability"])
        if momentum["p_now"] != expected_now:
            raise ValueError("reconstructed p_now differs from exact v0 raw market")
        if momentum["current_latest_trade_epoch_s"] * 1000 != int(old_receipt["latest_trade_epoch_ms"]):
            raise ValueError("reconstructed current fill second differs from v0 receipt")
        rows.append({
            "fold": int(prediction["fold"]), "game_id": game_id,
            "game_date": prediction["game_date"], "game_week": prediction["game_week"],
            "event_id": prediction["event_id"], "market_id": prediction["market_id"],
            "cutoff_ms": int(prediction["cutoff_ms"]), "outcome": int(prediction["outcome"]),
            **momentum,
        })
        receipts.append({**source_receipt, **{
            key: momentum[key] for key in (
                "decision_floor_epoch_s", "current_latest_trade_epoch_s",
                "reference_cutoff_epoch_s", "reference_latest_trade_epoch_s",
                "reference_age_seconds",
            )
        }})
    if len(rows) != len(frozen["predictions"]) or len({row["game_id"] for row in rows}) != len(rows):
        raise ValueError("reference coverage failed; no check row may be dropped")
    return rows, receipts


def _event_records(signal_rows: Sequence[dict]) -> list[dict]:
    records = []
    for row in signal_rows:
        p, y, signal = float(row["p_now"]), int(row["outcome"]), float(row["signal"])
        if y not in (0, 1) or not 0.0 < p < 1.0 or not math.isfinite(signal):
            raise ValueError("check label, p_now, or signal is invalid")
        residual = y - p
        log_alignment = signal * residual
        brier_alignment = log_alignment * p * (1.0 - p)
        values = (residual, log_alignment, brier_alignment)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("directional diagnostic is nonfinite")
        records.append({
            **row, "market_residual": residual,
            "log_loss_directional_alignment": log_alignment,
            "brier_logit_directional_alignment": brier_alignment,
        })
    return records


def _association_metrics(records: Sequence[dict]) -> dict:
    signals = [row["signal"] for row in records]
    residuals = [row["market_residual"] for row in records]
    return {
        "events": len(records),
        "pearson_signal_vs_market_residual": prior._pearson(signals, residuals),
        "spearman_signal_vs_market_residual": prior._pearson(
            prior._average_ranks(signals), prior._average_ranks(residuals)
        ),
        "mean_log_loss_directional_alignment": math.fsum(
            row["log_loss_directional_alignment"] for row in records
        ) / len(records),
        "mean_brier_logit_directional_alignment": math.fsum(
            row["brier_logit_directional_alignment"] for row in records
        ) / len(records),
    }


def _group_bootstrap(records: Sequence[dict], group: str, value: str, *,
                     seed: int = BOOTSTRAP_SEED, replicates: int = BOOTSTRAP_REPLICATES) -> dict:
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
        "group": group, "groups": len(labels), "events": len(records), "value": value,
        "point_equal_event_mean": point,
        "interval_95": [
            float(np.quantile(draws, 0.025, method="linear")),
            float(np.quantile(draws, 0.975, method="linear")),
        ],
        "bootstrap_replicates": replicates, "bootstrap_seed": seed,
        "valid_draws": len(draws), "undefined_draws": 0,
        "resampling_rule": "resample complete groups and recompute the pooled equal-event mean within every draw",
    }


def audit_decision(aggregate: Mapping[str, float], folds: Sequence[Mapping[str, float]],
                   date_interval: Mapping[str, object], week_interval: Mapping[str, object]) -> tuple[str, dict]:
    positive_folds = sum(fold["mean_log_loss_directional_alignment"] > 0 for fold in folds)
    date_low = float(date_interval["interval_95"][0])
    week_low = float(week_interval["interval_95"][0])
    support = {
        "pearson_positive": aggregate["pearson_signal_vs_market_residual"] > 0,
        "spearman_positive": aggregate["spearman_signal_vs_market_residual"] > 0,
        "log_loss_alignment_positive": aggregate["mean_log_loss_directional_alignment"] > 0,
        "brier_logit_alignment_positive": aggregate["mean_brier_logit_directional_alignment"] > 0,
        "date_grouped_log_alignment_lower_bound_positive": date_low > 0,
        "week_grouped_log_alignment_lower_bound_positive": week_low > 0,
        "positive_log_alignment_folds_at_least_3_of_4": positive_folds >= 3,
    }
    refute = {
        "both_associations_nonpositive": aggregate["pearson_signal_vs_market_residual"] <= 0 and aggregate["spearman_signal_vs_market_residual"] <= 0,
        "both_directional_alignments_nonpositive": aggregate["mean_log_loss_directional_alignment"] <= 0 and aggregate["mean_brier_logit_directional_alignment"] <= 0,
        "positive_log_alignment_folds_at_most_1_of_4": positive_folds <= 1,
    }
    if all(support.values()):
        decision = "PRE_ANCHOR_MARKET_MOMENTUM_RESIDUAL_SUPPORTED"
    elif any(refute.values()):
        decision = "PRE_ANCHOR_MARKET_MOMENTUM_RESIDUAL_REFUTED"
    else:
        decision = "PRE_ANCHOR_MARKET_MOMENTUM_RESIDUAL_INCONCLUSIVE"
    return decision, {"positive_log_alignment_folds": positive_folds, "support_conditions": support, "refute_conditions": refute}


def _audit(records: Sequence[dict]) -> dict:
    aggregate = _association_metrics(records)
    folds = []
    for number in (1, 2, 3, 4):
        selected = [row for row in records if row["fold"] == number]
        if not selected:
            raise ValueError("all four frozen folds must be present")
        folds.append({
            "fold": number, "check_dates": len({row["game_date"] for row in selected}),
            "check_game_weeks": len({row["game_week"] for row in selected}),
            **_association_metrics(selected),
        })
    intervals = {}
    for metric in ("log_loss_directional_alignment", "brier_logit_directional_alignment"):
        intervals[metric] = {
            "schedule_date": _group_bootstrap(records, "game_date", metric),
            "observed_game_week": _group_bootstrap(records, "game_week", metric),
        }
    decision, conditions = audit_decision(
        aggregate, folds, intervals["log_loss_directional_alignment"]["schedule_date"],
        intervals["log_loss_directional_alignment"]["observed_game_week"],
    )
    return {"decision": decision, "conditions": conditions, "aggregate": aggregate,
            "folds": folds, "complete_group_intervals": intervals}


def _write_event_audit(path: Path, records: Sequence[dict]) -> None:
    fields = (
        "fold", "game_id", "game_date", "game_week", "event_id", "market_id", "cutoff_ms",
        "outcome", "decision_floor_epoch_s", "current_latest_trade_epoch_s",
        "reference_cutoff_epoch_s", "reference_latest_trade_epoch_s", "reference_age_seconds",
        "p_now", "p_ref", "signal", "market_residual",
        "log_loss_directional_alignment", "brier_logit_directional_alignment",
    )
    temporary = path.with_suffix(".csv.tmp")
    with temporary.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in records:
            writer.writerow({key: row[key] for key in fields})
        stream.flush(); os.fsync(stream.fileno())
    temporary.replace(path)


def run(source_root: Path, v0_root: Path, output: Path, *, allow_test_paths: bool = False,
        expected_v0_hashes: dict[str, str] | None = None,
        generated_utc: str | None = None) -> dict:
    source_root, v0_root, output = map(lambda value: Path(value).resolve(), (source_root, v0_root, output))
    _validate_paths(source_root, v0_root, output, allow_test_paths=allow_test_paths)
    output.mkdir(parents=True, exist_ok=False)
    try:
        if not allow_test_paths:
            _validate_execution_identity()
        frozen = prior._validate_v0_artifact(
            v0_root,
            expected_hashes=prior.EXPECTED_V0_HASHES if expected_v0_hashes is None else expected_v0_hashes,
            require_exact_counts=not allow_test_paths,
        )
        source_receipt = prior._validate_source_and_receipts(source_root, frozen) if not allow_test_paths else {}
        cohort = settlement._read_cohort(source_root / "cohort.csv")
        signal_rows, trade_receipts = _extract_market_signals(source_root, frozen, cohort)
        if not allow_test_paths and len(signal_rows) != prior.EXPECTED_CHECK_EVENTS:
            raise ValueError("exact 87 check rows require complete reference coverage")
        input_receipts = {
            "schema": "nfl_ingame_pre_anchor_market_momentum_inputs_v3", "task_id": TASK_ID,
            "runner_sha256": _sha256(Path(__file__)), "controller_log_sha256": CONTROLLER_LOG_SHA256,
            "v0_runner_sha256": V0_RUNNER_SHA256, "prior_validator_sha256": PRIOR_VALIDATOR_SHA256,
            "settlement_dependency_sha256": SETTLEMENT_DEPENDENCY_SHA256,
            "v0_artifact_hashes": frozen["hashes"], "source_receipt": source_receipt,
            "trade_receipts": trade_receipts, "route_dev_opened": False,
            "sealed_final_opened": False, "external_fetch": False, "provider_cost_usd": "0",
        }
        _atomic_json(output / "input_receipts.json", input_receipts)
        lock = {
            "schema": "nfl_ingame_pre_anchor_market_momentum_pre_audit_lock_v3",
            "generated_utc": generated_utc or datetime.now(timezone.utc).isoformat(),
            "task_id": TASK_ID, "question_id": QUESTION_ID,
            "question_digest_sha256": QUESTION_DIGEST, "hypothesis_digest_sha256": HYPOTHESIS_DIGEST,
            "predeclared_rule_sha256": RULE_DIGEST, "selection_plan_sha256": SELECTION_PLAN_DIGEST,
            "controller_log_sha256": CONTROLLER_LOG_SHA256,
            "scheduler_branch_binding": SCHEDULER_BRANCH_BINDING,
            "scheduler_branch_binding_sha256": SCHEDULER_BRANCH_BINDING_SHA256,
            "scheduler_selection_state_sha256": SCHEDULER_SELECTION_STATE_SHA256,
            "scheduler_selection_journal_head_sha256": SCHEDULER_SELECTION_JOURNAL_HEAD_SHA256,
            "reference_lag_seconds": REFERENCE_LAG_SECONDS,
            "maximum_reference_staleness_seconds": MAX_REFERENCE_STALENESS_SECONDS,
            "reference_rule": "latest home-oriented size-weighted fill second strictly before floor(decision_epoch)-120",
            "current_rule": "exact v0 latest home-oriented size-weighted fill second strictly before floor(decision_epoch)",
            "signal": "logit_clip_1e-6(p_now)-logit_clip_1e-6(p_ref)",
            "no_row_drop_or_imputation": True, "model_fits": MODEL_FITS,
            "prediction_candidate": False, "bootstrap_seed": BOOTSTRAP_SEED,
            "bootstrap_replicates_each_metric_group": BOOTSTRAP_REPLICATES,
            "route_dev_opened": False, "sealed_final_opened": False, "external_fetch": False,
            "paid_provider": False, "provider_cost_usd": "0", "promotion_authorized": False,
        }
        _atomic_json(output / "pre_audit_lock.json", lock)
        records = _event_records(signal_rows)
        analysis = _audit(records)
        _write_event_audit(output / "event_audit.csv", records)
        scorecard = {
            "schema": "nfl_ingame_pre_anchor_market_momentum_scorecard_v3",
            "task_id": TASK_ID, "question_id": QUESTION_ID, **analysis,
            "source_lineage": {
                "source_events": prior.EXPECTED_SOURCE_EVENTS,
                "materialized_events": prior.EXPECTED_MATERIALIZED_EVENTS,
                "excluded_events": len(prior.EXPECTED_EXCLUSIONS),
                "check_events": len(records), "check_dates": len({row["game_date"] for row in records}),
                "check_game_weeks": len({row["game_week"] for row in records}),
                "v0_check_key_sha256": frozen["check_key_sha256"],
            },
            "no_rows_dropped_from_v0_common_mask": len(records) == len(frozen["predictions"]),
            "model_fits": MODEL_FITS, "no_prediction_candidate_emitted": True,
            "incumbent_or_keep_revert_changed": False,
            "research_credit_awarded": 0,
            "research_credit_eligibility_after_independent_review": 2 if analysis["decision"].endswith(("SUPPORTED", "REFUTED")) else 1,
            "inference_boundary": "repeatedly inspected opened-Train historical trades; not realtime, untouched OOS, prediction gain, promotion, or PnL",
            "route_dev_opened": False, "sealed_final_opened": False, "external_fetch": False,
            "paid_provider": False, "provider_cost_usd": "0", "promotion_authorized": False,
        }
        _atomic_json(output / "scorecard.json", scorecard)
        manifest = {
            "schema": "nfl_ingame_pre_anchor_market_momentum_manifest_v3", "complete": True,
            "completed_utc": generated_utc or datetime.now(timezone.utc).isoformat(),
            "task_id": TASK_ID, "decision": analysis["decision"],
            "pre_audit_lock_sha256": _sha256(output / "pre_audit_lock.json"),
            "input_receipts_sha256": _sha256(output / "input_receipts.json"),
            "event_audit_sha256": _sha256(output / "event_audit.csv"),
            "scorecard_sha256": _sha256(output / "scorecard.json"),
            "source_events": prior.EXPECTED_SOURCE_EVENTS,
            "materialized_events": prior.EXPECTED_MATERIALIZED_EVENTS,
            "excluded_events": len(prior.EXPECTED_EXCLUSIONS), "check_events": len(records),
            "model_fits": MODEL_FITS, "no_prediction_candidate_emitted": True,
            "incumbent_or_keep_revert_changed": False, "historical_event_clock_only": True,
            "route_dev_opened": False, "sealed_final_opened": False, "external_fetch": False,
            "paid_provider": False, "provider_cost_usd": "0", "promotion_authorized": False,
        }
        _atomic_json(output / "manifest.json", manifest)
        return manifest
    except Exception as error:
        if output.exists() and not (output / "manifest.json").exists():
            _atomic_json(output / "failure.json", {
                "schema": "nfl_ingame_pre_anchor_market_momentum_failure_v3",
                "task_id": TASK_ID, "error_type": type(error).__name__, "error": str(error)[:1200],
                "model_fits": MODEL_FITS, "route_dev_opened": False,
                "sealed_final_opened": False, "external_fetch": False,
                "paid_provider": False, "provider_cost_usd": "0",
            })
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--v0-artifact-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.source_root, args.v0_artifact_root, args.output)
    print(json.dumps({key: result[key] for key in (
        "complete", "task_id", "source_events", "materialized_events",
        "excluded_events", "check_events", "decision", "model_fits", "provider_cost_usd",
    )}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
