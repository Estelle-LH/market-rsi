#!/usr/bin/env python3
"""Audit prior-play success alignment by frozen raw-market uncertainty regime.

This zero-fit opened-Train diagnostic reads the exact completed parent event
audit and never recomputes PBP.  It asks whether the parent's conflicting log
and Brier-logit directions are explained by a predeclared low/high market-
uncertainty split.  It emits no probability candidate and cannot change the
incumbent, KEEP/REVERT, promotion, or protected-data boundary.
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
from typing import Mapping, Sequence

import numpy as np


TASK_ID = "InGamePriorPlaySuccessMarketUncertaintyAudit-v3"
QUESTION_ID = "ingame-prior-play-success-market-uncertainty-v3-q1"
QUESTION_DIGEST = "7d9baa1a8e0568f9273811492716400ebc19dfc65d5d77e950e281da85757fe3"
HYPOTHESIS_DIGEST = "6c22574911e625875ef8d97bfc4580d20d82ac2f620adfcbceb85829ee52ff84"
RULE_DIGEST = "23a956a5ffee6d7fe800a67fbf1eb9146d34f367d4a5745d98abbd96537a7e1a"
POOL_PLAN_DIGEST = "c10ed553121ac9c0da123138a4e3d7b2f03979cf7143dc7092b8d8dad513a92c"

CONTROLLER_LOG = Path(__file__).parents[1] / "supervisor_harness" / (
    "AGENT_LOG_INGAME_DISCOVERY_V3_GENERATION2_TWO_MEMBER_POOL_CONTROLLER_2026-09-29.md"
)
CONTROLLER_LOG_SHA256 = "4186a3554b7f7aed50596123c135943dbf986d5e39b84fe507fac91c6e04e986"
PARENT_RESULT_REVIEW = Path(__file__).parents[1] / "supervisor_harness" / (
    "AGENT_LOG_INGAME_PRIOR_PLAY_SUCCESS_RESIDUAL_V2_RESULT_INDEPENDENT_REVIEW_2026-09-29.md"
)
PARENT_RESULT_REVIEW_SHA256 = (
    "0fd2d3dacefe1d7233721076f210710e3ed3e44661e39a325b6f2e0627068c73"
)
PARENT_RUNNER = Path(__file__).with_name("nfl_ingame_prior_play_success_residual_audit.py")
PARENT_RUNNER_SHA256 = "a612371ae77a78441c2d9416d6edc035a916879057fed9ef731de46476a07bcb"
PARENT_ARTIFACT_ROOT = Path(
    "/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/"
    "artifacts/nfl-ingame-prior-play-success-residual-audit-20260929-01"
)
PERSISTENT_ARTIFACT_ROOT = Path(
    "/Users/estelle/Library/Application Support/MarketRSI/"
    "self-evolving-v18-local/artifacts"
)
EXPECTED_PARENT_HASHES = {
    "event_audit.csv": "0b85a96491237edcf1b74e8718db0582bae28d0bf380c0d0f89564edaf20e2f5",
    "input_receipts.json": "0f8902d5aee81a08d5c17c44f2025e10ca650cc6f825c4be150735c0ac7934e0",
    "manifest.json": "addececc96838399be8b9713b85048dba6c449e840aff6f69f099f1779750144",
    "pre_audit_lock.json": "d046d70927f0f29f327b0ed8552e523fbaf3c1955db257af19a225250f9e2929",
    "prior_play_success.csv": "cca09f294f88f19a5cfa05fce294d6ec2a11c6264fed54840460784cbabea764",
    "scorecard.json": "db53da50fecbebce76eb105915d53db51ce44eced92fbf41dd9688ac40e71846",
}
EXPECTED_EVENT_IDENTITY_SHA256 = (
    "92513bfe46e9f023b1afd8ca6218e67ce1810a333424c69e1e3a699d060fae10"
)
EXPECTED_V0_CHECK_KEY_SHA256 = (
    "2e35779fdbb4b83e129758008338b0c778d7f6281682118ad8d26d21293cc9f9"
)
EXPECTED_CHECK_EVENTS = 87
EXPECTED_CHECK_COUNTS = (26, 16, 28, 17)
EXPECTED_CHECK_DATES = 20
EXPECTED_GAME_WEEKS = 7

UNCERTAINTY_THRESHOLD = 0.1875
MIN_REGIME_EVENTS = 12
MIN_VALID_BOOTSTRAP_DRAWS = 9_000
BOOTSTRAP_SEED = 20260929
BOOTSTRAP_REPLICATES = 10_000
MODEL_FITS = 0

SCHEDULER_BRANCH_BINDING = {
    "allocation": "exploitation",
    "attempt_id": "attempt-03",
    "candidate_id": TASK_ID,
    "comparison_incumbent_sha256": (
        "89a8ef92c9cf4844b99e0136c51a1f8b896cdd66afcd23e8b8a23499859ffc7f"
    ),
    "controller_decision_sha256": CONTROLLER_LOG_SHA256,
    "hypothesis_digest_sha256": HYPOTHESIS_DIGEST,
    "method_family": "prior_play_success_market_uncertainty_regime_audit",
    "predeclared_rule_sha256": RULE_DIGEST,
    "question_digest_sha256": QUESTION_DIGEST,
    "question_id": QUESTION_ID,
    "research_parent_sha256": PARENT_RUNNER_SHA256,
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
    "71a1e48c0b82378e17030dbc9045fcd68eb01bcf5ba78ad015c6629bf72804a9"
)

PARENT_EVENT_FIELDS = (
    "fold", "game_id", "game_date", "game_week", "outcome",
    "raw_market_probability", "home_eligible_plays", "home_successes",
    "away_eligible_plays", "away_successes", "home_success_rate",
    "away_success_rate", "home_minus_away_success_rate", "market_residual",
    "log_loss_directional_alignment", "brier_logit_directional_alignment",
)


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


def _read_csv(path: Path) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        fields = tuple(reader.fieldnames or ())
        return fields, list(reader)


def _validate_paths(
    parent_root: Path, output: Path, *, allow_test_paths: bool
) -> None:
    parent_root, output = parent_root.resolve(), output.resolve()
    if output.exists():
        raise FileExistsError("output already exists; the frozen audit has no retry")
    if parent_root == output or parent_root in output.parents:
        raise ValueError("output cannot be inside immutable parent artifact")
    if allow_test_paths:
        return
    if parent_root != PARENT_ARTIFACT_ROOT.resolve():
        raise ValueError("runner is bound to the exact reviewed parent artifact")
    try:
        output.relative_to(PERSISTENT_ARTIFACT_ROOT.resolve())
    except ValueError as error:
        raise ValueError("output must be in persistent local MarketRSI artifacts") from error
    lowered = str(output).lower()
    if any(marker in lowered for marker in (
            "/tmp/", "/private/var/", "icloud", "mobile documents",
            "dropbox", "google drive")):
        raise ValueError("temporary or cloud-looking output is forbidden")


def _finite(row: Mapping[str, str], name: str) -> float:
    try:
        value = float(row[name])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"{name} is missing or nonnumeric") from error
    if not math.isfinite(value):
        raise ValueError(f"{name} is nonfinite")
    return value


def _validate_parent_artifact(
    root: Path,
    *,
    expected_hashes: Mapping[str, str] = EXPECTED_PARENT_HASHES,
    require_exact_population: bool = True,
) -> dict:
    root = Path(root).resolve()
    if set(expected_hashes) != set(EXPECTED_PARENT_HASHES):
        raise ValueError("parent hash map must name every frozen parent file")
    observed_files = {path.name for path in root.iterdir() if path.is_file()}
    if observed_files != set(EXPECTED_PARENT_HASHES):
        raise ValueError("parent artifact file set changed")
    hashes = {}
    for name, expected in expected_hashes.items():
        path = root / name
        hashes[name] = _sha256(path)
        if hashes[name] != expected:
            raise ValueError(f"frozen parent artifact hash changed: {name}")

    manifest = _strict_json(root / "manifest.json")
    scorecard = _strict_json(root / "scorecard.json")
    receipts = _strict_json(root / "input_receipts.json")
    lock = _strict_json(root / "pre_audit_lock.json")
    if not all(isinstance(item, dict) for item in (manifest, scorecard, receipts, lock)):
        raise ValueError("parent JSON roots must be objects")
    if (manifest.get("complete") is not True
            or manifest.get("task_id") != "InGamePriorPlaySuccessResidualAudit-v2"
            or manifest.get("decision") != "PRIOR_PLAY_SUCCESS_RESIDUAL_INCONCLUSIVE"
            or manifest.get("check_events") != EXPECTED_CHECK_EVENTS
            or manifest.get("model_fits") != 0
            or manifest.get("no_prediction_candidate_emitted") is not True
            or manifest.get("incumbent_or_keep_revert_changed") is not False
            or manifest.get("route_dev_opened") is not False
            or manifest.get("sealed_final_opened") is not False
            or manifest.get("external_fetch") is not False
            or manifest.get("paid_provider") is not False
            or manifest.get("provider_cost_usd") != "0"
            or manifest.get("promotion_authorized") is not False):
        raise ValueError("parent manifest completion or boundary changed")
    for name, key in (
        ("pre_audit_lock.json", "pre_audit_lock_sha256"),
        ("input_receipts.json", "input_receipts_sha256"),
        ("prior_play_success.csv", "prior_play_success_sha256"),
        ("event_audit.csv", "event_audit_sha256"),
        ("scorecard.json", "scorecard_sha256"),
    ):
        if manifest.get(key) != hashes[name]:
            raise ValueError(f"parent manifest no longer binds {name}")
    lineage = scorecard.get("source_lineage", {})
    if (scorecard.get("task_id") != "InGamePriorPlaySuccessResidualAudit-v2"
            or scorecard.get("decision") != manifest["decision"]
            or scorecard.get("no_rows_dropped_from_v0_common_mask") is not True
            or scorecard.get("model_fits") != 0
            or scorecard.get("no_prediction_candidate_emitted") is not True
            or scorecard.get("incumbent_or_keep_revert_changed") is not False
            or lineage.get("check_events") != EXPECTED_CHECK_EVENTS
            or lineage.get("check_dates") != EXPECTED_CHECK_DATES
            or lineage.get("check_game_weeks") != EXPECTED_GAME_WEEKS
            or lineage.get("v0_check_key_sha256") != EXPECTED_V0_CHECK_KEY_SHA256):
        raise ValueError("parent scorecard population or zero-fit boundary changed")
    if (receipts.get("runner_sha256") != PARENT_RUNNER_SHA256
            or receipts.get("indicator_sha256") != hashes["prior_play_success.csv"]
            or receipts.get("route_dev_opened") is not False
            or receipts.get("sealed_final_opened") is not False
            or receipts.get("external_fetch") is not False
            or receipts.get("provider_cost_usd") != "0"
            or lock.get("model_fits") != 0
            or lock.get("prediction_candidate") is not False
            or lock.get("one_audit_no_retry") is not True):
        raise ValueError("parent receipts or pre-audit boundary changed")

    fields, raw_rows = _read_csv(root / "event_audit.csv")
    if fields != PARENT_EVENT_FIELDS:
        raise ValueError("parent event-audit schema changed")
    records = []
    identity = []
    for row in raw_rows:
        try:
            fold = int(row["fold"])
            outcome = int(row["outcome"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("parent event identity is nonnumeric") from error
        if fold not in (1, 2, 3, 4) or outcome not in (0, 1):
            raise ValueError("parent fold or outcome changed")
        game_id, game_date, game_week = (
            row.get("game_id", ""), row.get("game_date", ""), row.get("game_week", "")
        )
        if not game_id or not game_date or not game_week:
            raise ValueError("parent event identity is blank")
        probability = _finite(row, "raw_market_probability")
        signal = _finite(row, "home_minus_away_success_rate")
        residual = _finite(row, "market_residual")
        log_alignment = _finite(row, "log_loss_directional_alignment")
        brier_alignment = _finite(row, "brier_logit_directional_alignment")
        if not 0 < probability < 1:
            raise ValueError("parent raw-market probability is outside (0,1)")
        expected_residual = outcome - probability
        expected_log = signal * expected_residual
        expected_brier = expected_log * probability * (1 - probability)
        if (not math.isclose(residual, expected_residual, abs_tol=2e-15)
                or not math.isclose(log_alignment, expected_log, abs_tol=2e-15)
                or not math.isclose(brier_alignment, expected_brier, abs_tol=2e-15)):
            raise ValueError("parent event directional arithmetic changed")
        records.append({
            "fold": fold,
            "game_id": game_id,
            "game_date": game_date,
            "game_week": game_week,
            "outcome": outcome,
            "raw_market_probability": probability,
            "signal": signal,
            "market_residual": residual,
            "log_loss_directional_alignment": log_alignment,
            "brier_logit_directional_alignment": brier_alignment,
        })
        identity.append([
            fold, game_id, game_date, game_week, outcome,
            row["raw_market_probability"],
        ])
    if require_exact_population:
        if (len(records) != EXPECTED_CHECK_EVENTS
                or len({row["game_id"] for row in records}) != EXPECTED_CHECK_EVENTS
                or tuple(sum(row["fold"] == fold for row in records)
                         for fold in (1, 2, 3, 4)) != EXPECTED_CHECK_COUNTS
                or len({row["game_date"] for row in records}) != EXPECTED_CHECK_DATES
                or len({row["game_week"] for row in records}) != EXPECTED_GAME_WEEKS
                or _digest(identity) != EXPECTED_EVENT_IDENTITY_SHA256):
            raise ValueError("parent exact 87-row identity/mask changed")
    return {
        "hashes": hashes,
        "manifest": manifest,
        "scorecard": scorecard,
        "records": records,
        "event_identity_sha256": _digest(identity),
    }


def _market_uncertainty_regime(probability: float) -> tuple[float, str]:
    if isinstance(probability, bool) or not math.isfinite(float(probability)):
        raise ValueError("raw-market probability is nonfinite")
    probability = float(probability)
    if not 0 < probability < 1:
        raise ValueError("raw-market probability must be inside (0,1)")
    uncertainty = probability * (1 - probability)
    return uncertainty, "high" if uncertainty >= UNCERTAINTY_THRESHOLD else "low"


def _assign_regimes(records: Sequence[Mapping[str, object]]) -> list[dict]:
    result = []
    seen = set()
    for row in records:
        game_id = str(row["game_id"])
        if not game_id or game_id in seen:
            raise ValueError("regime audit has blank or duplicate game identity")
        seen.add(game_id)
        uncertainty, regime = _market_uncertainty_regime(
            float(row["raw_market_probability"])
        )
        result.append({**row, "market_uncertainty": uncertainty, "regime": regime})
    if len(result) != len(records):
        raise RuntimeError("regime assignment dropped a row")
    return result


def _mean(rows: Sequence[Mapping[str, object]], field: str) -> float | None:
    if not rows:
        return None
    values = [float(row[field]) for row in rows]
    if not all(math.isfinite(value) for value in values):
        raise ValueError(f"{field} contains nonfinite evidence")
    return math.fsum(values) / len(values)


def _regime_means(records: Sequence[Mapping[str, object]]) -> dict:
    result = {}
    for regime in ("low", "high"):
        rows = [row for row in records if row["regime"] == regime]
        result[regime] = {
            "events": len(rows),
            "schedule_dates": len({str(row["game_date"]) for row in rows}),
            "observed_game_weeks": len({str(row["game_week"]) for row in rows}),
            "mean_log_loss_directional_alignment": _mean(
                rows, "log_loss_directional_alignment"
            ),
            "mean_brier_logit_directional_alignment": _mean(
                rows, "brier_logit_directional_alignment"
            ),
        }
    low = result["low"]["mean_log_loss_directional_alignment"]
    high = result["high"]["mean_log_loss_directional_alignment"]
    result["low_minus_high_log_alignment"] = (
        None if low is None or high is None else float(low) - float(high)
    )
    return result


def _fold_contrasts(records: Sequence[Mapping[str, object]]) -> list[dict]:
    result = []
    for fold in (1, 2, 3, 4):
        rows = [row for row in records if int(row["fold"]) == fold]
        if not rows:
            raise ValueError("one frozen fold has no rows")
        means = _regime_means(rows)
        result.append({
            "fold": fold,
            "events": len(rows),
            "check_dates": len({str(row["game_date"]) for row in rows}),
            "check_game_weeks": len({str(row["game_week"]) for row in rows}),
            "low": means["low"],
            "high": means["high"],
            "low_minus_high_log_alignment": means[
                "low_minus_high_log_alignment"
            ],
        })
    return result


def _group_regime_contrast_bootstrap(
    records: Sequence[Mapping[str, object]],
    group: str,
    *,
    seed: int = BOOTSTRAP_SEED,
    replicates: int = BOOTSTRAP_REPLICATES,
) -> dict:
    if isinstance(replicates, bool) or not isinstance(replicates, int) or replicates < 1:
        raise ValueError("bootstrap replicates must be a positive integer")
    buckets: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in records:
        label = str(row[group])
        if not label:
            raise ValueError("bootstrap group label is blank")
        if row["regime"] not in {"low", "high"}:
            raise ValueError("bootstrap row has invalid regime")
        buckets[label].append(row)
    labels = sorted(buckets)
    if len(labels) < 2:
        raise ValueError("complete-group bootstrap requires at least two groups")
    generator = np.random.default_rng(seed)
    draws = []
    undefined = 0
    for _ in range(replicates):
        sample = generator.choice(labels, size=len(labels), replace=True)
        sampled_rows = [row for label in sample for row in buckets[str(label)]]
        low = [float(row["log_loss_directional_alignment"])
               for row in sampled_rows if row["regime"] == "low"]
        high = [float(row["log_loss_directional_alignment"])
                for row in sampled_rows if row["regime"] == "high"]
        if not low or not high:
            undefined += 1
            continue
        draws.append(math.fsum(low) / len(low) - math.fsum(high) / len(high))
    if not all(math.isfinite(value) for value in draws):
        raise ValueError("bootstrap produced nonfinite contrast")
    point = _regime_means(records)["low_minus_high_log_alignment"]
    interval = None if not draws else [
        float(np.quantile(draws, 0.025, method="linear")),
        float(np.quantile(draws, 0.975, method="linear")),
    ]
    return {
        "group": group,
        "groups": len(labels),
        "events": len(records),
        "point_low_minus_high_log_alignment": point,
        "interval_95": interval,
        "bootstrap_replicates": replicates,
        "valid_draws": len(draws),
        "undefined_draws_missing_one_or_both_regimes": undefined,
        "bootstrap_seed": seed,
        "resampling_rule": (
            "resample complete groups; recompute pooled equal-event low and high "
            "means within each draw; count a draw missing either regime as undefined"
        ),
    }


def market_uncertainty_decision(
    aggregate: Mapping[str, object],
    folds: Sequence[Mapping[str, object]],
    date_bootstrap: Mapping[str, object],
    week_bootstrap: Mapping[str, object],
) -> tuple[str, dict]:
    low = aggregate.get("low")
    high = aggregate.get("high")
    if not isinstance(low, Mapping) or not isinstance(high, Mapping) or len(folds) != 4:
        raise ValueError("regime decision evidence is malformed")
    for item in (date_bootstrap, week_bootstrap):
        if (item.get("bootstrap_replicates") != BOOTSTRAP_REPLICATES
                or int(item.get("valid_draws", -1))
                + int(item.get("undefined_draws_missing_one_or_both_regimes", -1))
                != BOOTSTRAP_REPLICATES):
            raise ValueError("bootstrap accounting changed")
    breadth = {
        "low_events_at_least_12": int(low.get("events", -1)) >= MIN_REGIME_EVENTS,
        "high_events_at_least_12": int(high.get("events", -1)) >= MIN_REGIME_EVENTS,
        "date_valid_draws_at_least_9000": (
            int(date_bootstrap.get("valid_draws", -1)) >= MIN_VALID_BOOTSTRAP_DRAWS
        ),
        "week_valid_draws_at_least_9000": (
            int(week_bootstrap.get("valid_draws", -1)) >= MIN_VALID_BOOTSTRAP_DRAWS
        ),
    }
    fold_values = [fold.get("low_minus_high_log_alignment") for fold in folds]
    if any(
        value is not None and not math.isfinite(float(value))
        for value in fold_values
    ):
        raise ValueError("fold regime contrast is nonfinite")
    positive_folds = sum(
        value is not None and float(value) > 0
        for value in fold_values
    )
    evidence = {
        "breadth_conditions": breadth,
        "positive_fold_contrasts": positive_folds,
        "fold_contrasts": fold_values,
        "support_conditions": {},
        "refute_conditions": {},
    }
    if not all(breadth.values()):
        evidence["decision_stage"] = "insufficient_breadth"
        return "PRIOR_PLAY_SUCCESS_MARKET_UNCERTAINTY_INCONCLUSIVE", evidence

    low_log = float(low["mean_log_loss_directional_alignment"])
    high_log = float(high["mean_log_loss_directional_alignment"])
    high_brier = float(high["mean_brier_logit_directional_alignment"])
    contrast = float(aggregate["low_minus_high_log_alignment"])
    date_interval = date_bootstrap.get("interval_95")
    week_interval = week_bootstrap.get("interval_95")
    if (not isinstance(date_interval, list) or len(date_interval) != 2
            or not isinstance(week_interval, list) or len(week_interval) != 2
            or not all(math.isfinite(value) for value in (
                low_log, high_log, high_brier, contrast,
                *[float(value) for value in date_interval],
                *[float(value) for value in week_interval],
            ))):
        raise ValueError("regime decision evidence is nonfinite or incomplete")
    support = {
        "low_log_alignment_positive": low_log > 0,
        "high_log_alignment_negative": high_log < 0,
        "high_brier_logit_alignment_negative": high_brier < 0,
        "low_minus_high_log_contrast_positive": contrast > 0,
        "date_grouped_contrast_lower_bound_positive": float(date_interval[0]) > 0,
        "week_grouped_contrast_lower_bound_positive": float(week_interval[0]) > 0,
        "positive_fold_contrasts_at_least_3_of_4": positive_folds >= 3,
    }
    refute = {
        "low_minus_high_log_contrast_nonpositive": contrast <= 0,
        "low_nonpositive_while_high_nonnegative": low_log <= 0 and high_log >= 0,
        "positive_fold_contrasts_at_most_1_of_4": positive_folds <= 1,
    }
    evidence["support_conditions"] = support
    evidence["refute_conditions"] = refute
    if all(support.values()):
        decision = "PRIOR_PLAY_SUCCESS_MARKET_UNCERTAINTY_SUPPORTED"
        stage = "support"
    elif any(refute.values()):
        decision = "PRIOR_PLAY_SUCCESS_MARKET_UNCERTAINTY_REFUTED"
        stage = "refute"
    else:
        decision = "PRIOR_PLAY_SUCCESS_MARKET_UNCERTAINTY_INCONCLUSIVE"
        stage = "otherwise_inconclusive"
    evidence["decision_stage"] = stage
    return decision, evidence


def _audit(records: Sequence[Mapping[str, object]]) -> dict:
    assigned = _assign_regimes(records)
    aggregate = _regime_means(assigned)
    folds = _fold_contrasts(assigned)
    date_bootstrap = _group_regime_contrast_bootstrap(assigned, "game_date")
    week_bootstrap = _group_regime_contrast_bootstrap(assigned, "game_week")
    decision, conditions = market_uncertainty_decision(
        aggregate, folds, date_bootstrap, week_bootstrap
    )
    return {
        "decision": decision,
        "conditions": conditions,
        "aggregate_regimes": aggregate,
        "folds": folds,
        "complete_group_contrast_intervals": {
            "schedule_date": date_bootstrap,
            "observed_game_week": week_bootstrap,
        },
        "records": assigned,
    }


def _write_event_audit(path: Path, records: Sequence[Mapping[str, object]]) -> None:
    fields = (
        "fold", "game_id", "game_date", "game_week", "outcome",
        "raw_market_probability", "prior_play_success_signal", "market_residual",
        "log_loss_directional_alignment", "brier_logit_directional_alignment",
        "market_uncertainty", "uncertainty_regime",
    )
    temporary = path.with_suffix(".csv.tmp")
    with temporary.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in records:
            writer.writerow({
                "fold": row["fold"],
                "game_id": row["game_id"],
                "game_date": row["game_date"],
                "game_week": row["game_week"],
                "outcome": row["outcome"],
                "raw_market_probability": row["raw_market_probability"],
                "prior_play_success_signal": row["signal"],
                "market_residual": row["market_residual"],
                "log_loss_directional_alignment": row[
                    "log_loss_directional_alignment"
                ],
                "brier_logit_directional_alignment": row[
                    "brier_logit_directional_alignment"
                ],
                "market_uncertainty": row["market_uncertainty"],
                "uncertainty_regime": row["regime"],
            })
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def run(
    parent_root: Path,
    output: Path,
    *,
    allow_test_paths: bool = False,
    expected_parent_hashes: Mapping[str, str] | None = None,
    generated_utc: str | None = None,
) -> dict:
    parent_root, output = Path(parent_root).resolve(), Path(output).resolve()
    _validate_paths(parent_root, output, allow_test_paths=allow_test_paths)
    if not allow_test_paths:
        if _sha256(CONTROLLER_LOG) != CONTROLLER_LOG_SHA256:
            raise ValueError("frozen generation-2 Controller log hash changed")
        if _sha256(PARENT_RUNNER) != PARENT_RUNNER_SHA256:
            raise ValueError("frozen parent runner hash changed")
        if _sha256(PARENT_RESULT_REVIEW) != PARENT_RESULT_REVIEW_SHA256:
            raise ValueError("frozen parent result review hash changed")
        if _digest(SCHEDULER_BRANCH_BINDING) != SCHEDULER_BRANCH_BINDING_SHA256:
            raise ValueError("scheduler branch binding digest changed")
    parent = _validate_parent_artifact(
        parent_root,
        expected_hashes=(
            EXPECTED_PARENT_HASHES
            if expected_parent_hashes is None else expected_parent_hashes
        ),
        require_exact_population=not allow_test_paths,
    )
    output.mkdir(parents=True, exist_ok=False)
    try:
        now = generated_utc or datetime.now(timezone.utc).isoformat()
        lock = {
            "schema": "nfl_ingame_prior_play_success_market_uncertainty_pre_audit_lock_v3",
            "generated_utc": now,
            "task_id": TASK_ID,
            "question_id": QUESTION_ID,
            "question_digest_sha256": QUESTION_DIGEST,
            "hypothesis_digest_sha256": HYPOTHESIS_DIGEST,
            "predeclared_rule_sha256": RULE_DIGEST,
            "pool_plan_sha256": POOL_PLAN_DIGEST,
            "controller_log_sha256": CONTROLLER_LOG_SHA256,
            "scheduler_branch_binding": SCHEDULER_BRANCH_BINDING,
            "scheduler_branch_binding_sha256": SCHEDULER_BRANCH_BINDING_SHA256,
            "research_parent": "credit-1 attempt-01 prior-play-success residual audit",
            "parent_manifest_sha256": parent["hashes"]["manifest.json"],
            "parent_event_audit_sha256": parent["hashes"]["event_audit.csv"],
            "parent_event_identity_sha256": parent["event_identity_sha256"],
            "comparison_incumbent": "v0 task-local raw market; no prediction comparison",
            "prediction_candidate": False,
            "model_fits": MODEL_FITS,
            "signal": "exact parent home-minus-away prior-play success rate",
            "market_uncertainty": "p_raw * (1 - p_raw)",
            "high_uncertainty_rule": "uncertainty >= 0.1875; p_raw endpoints inclusive",
            "low_uncertainty_rule": "uncertainty < 0.1875",
            "contrast": "low mean log alignment minus high mean log alignment",
            "minimum_events_per_regime": MIN_REGIME_EVENTS,
            "minimum_valid_draws_per_grouping": MIN_VALID_BOOTSTRAP_DRAWS,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "bootstrap_replicates_for_each_of_date_and_week": BOOTSTRAP_REPLICATES,
            "undefined_draw_rule": "count draw; do not impute when either regime is absent",
            "decision_order": [
                "integrity failure", "insufficient-breadth inconclusive",
                "support", "refute", "otherwise inconclusive",
            ],
            "one_bounded_followup_no_retry": True,
            "no_pbp_recomputation": True,
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "external_fetch": False,
            "paid_provider": False,
            "provider_cost_usd": "0",
            "promotion_authorized": False,
        }
        _atomic_json(output / "pre_audit_lock.json", lock)
        analysis = _audit(parent["records"])
        if (len(analysis["records"]) != EXPECTED_CHECK_EVENTS
                or {row["game_id"] for row in analysis["records"]}
                != {row["game_id"] for row in parent["records"]}):
            raise RuntimeError("regime audit changed the exact parent row mask")
        _write_event_audit(output / "regime_event_audit.csv", analysis["records"])
        scorecard = {
            "schema": "nfl_ingame_prior_play_success_market_uncertainty_scorecard_v3",
            "task_id": TASK_ID,
            "question_id": QUESTION_ID,
            "decision": analysis["decision"],
            "conditions": analysis["conditions"],
            "aggregate_regimes": analysis["aggregate_regimes"],
            "folds": analysis["folds"],
            "complete_group_contrast_intervals": analysis[
                "complete_group_contrast_intervals"
            ],
            "source_lineage": {
                "parent_manifest_sha256": parent["hashes"]["manifest.json"],
                "parent_event_audit_sha256": parent["hashes"]["event_audit.csv"],
                "parent_event_identity_sha256": parent["event_identity_sha256"],
                "v0_check_key_sha256": EXPECTED_V0_CHECK_KEY_SHA256,
                "check_events": EXPECTED_CHECK_EVENTS,
                "check_dates": EXPECTED_CHECK_DATES,
                "check_game_weeks": EXPECTED_GAME_WEEKS,
            },
            "no_rows_dropped_from_parent_mask": True,
            "model_fits": MODEL_FITS,
            "no_prediction_candidate_emitted": True,
            "incumbent_or_keep_revert_changed": False,
            "research_credit_awarded": 0,
            "evidence_classification": (
                "raw-signal heterogeneity diagnostic on repeatedly inspected opened Train"
            ),
            "inference_boundary": (
                "historical parent event audit only; no PBP recomputation, realtime claim, "
                "untouched OOS, prediction gain, promotion, PnL, or cross-task comparison"
            ),
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "external_fetch": False,
            "paid_provider": False,
            "provider_cost_usd": "0",
            "promotion_authorized": False,
        }
        _atomic_json(output / "scorecard.json", scorecard)
        receipts = {
            "schema": "nfl_ingame_prior_play_success_market_uncertainty_inputs_v3",
            "task_id": TASK_ID,
            "runner_sha256": _sha256(Path(__file__)),
            "controller_log_sha256": _sha256(CONTROLLER_LOG),
            "parent_runner_sha256": _sha256(PARENT_RUNNER),
            "parent_result_review_sha256": _sha256(PARENT_RESULT_REVIEW),
            "parent_artifact_root": str(parent_root),
            "parent_artifact_hashes": parent["hashes"],
            "parent_event_identity_sha256": parent["event_identity_sha256"],
            "no_pbp_recomputation": True,
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "external_fetch": False,
            "paid_provider": False,
            "provider_cost_usd": "0",
        }
        _atomic_json(output / "input_receipts.json", receipts)
        manifest = {
            "schema": "nfl_ingame_prior_play_success_market_uncertainty_manifest_v3",
            "complete": True,
            "completed_utc": now,
            "task_id": TASK_ID,
            "decision": analysis["decision"],
            "check_events": EXPECTED_CHECK_EVENTS,
            "model_fits": MODEL_FITS,
            "pre_audit_lock_sha256": _sha256(output / "pre_audit_lock.json"),
            "regime_event_audit_sha256": _sha256(output / "regime_event_audit.csv"),
            "scorecard_sha256": _sha256(output / "scorecard.json"),
            "input_receipts_sha256": _sha256(output / "input_receipts.json"),
            "parent_manifest_sha256": parent["hashes"]["manifest.json"],
            "no_rows_dropped_from_parent_mask": True,
            "no_prediction_candidate_emitted": True,
            "incumbent_or_keep_revert_changed": False,
            "historical_parent_event_audit_only": True,
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
                "schema": "nfl_ingame_prior_play_success_market_uncertainty_failure_v3",
                "error_type": type(error).__name__,
                "error": str(error)[:1200],
                "model_fits": MODEL_FITS,
                "route_dev_opened": False,
                "sealed_final_opened": False,
                "external_fetch": False,
                "paid_provider": False,
                "provider_cost_usd": "0",
                "promotion_authorized": False,
            })
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent-artifact", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.parent_artifact, args.output)
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
