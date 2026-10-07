#!/usr/bin/env python3
"""Prior-only support-geometry audit of the frozen NFL in-game v0 result.

This runner does not fit or emit a prediction model.  It reads the exact,
already-scored v0 opened-Train artifact and asks whether the frozen
state-minus-market-model Brier harm is concentrated in check games that are
far from prior fit-game state vectors.  The result is a repeatedly inspected
historical Discovery diagnostic, not realtime, untouched OOS, promotion, or
cross-task evidence.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Iterable, Sequence
from zoneinfo import ZoneInfo

import numpy as np
from sklearn.preprocessing import StandardScaler


V0_ARTIFACT_ROOT = Path(
    "/Users/estelle/Library/Application Support/MarketRSI/"
    "self-evolving-v18-local/artifacts/"
    "nfl-ingame-win-probability-train-diagnostic-20260929-01"
)
PERSISTENT_ARTIFACT_ROOT = Path(
    "/Users/estelle/Library/Application Support/MarketRSI/"
    "self-evolving-v18-local/artifacts"
)
CONTROLLER_LOG = Path(__file__).parents[1] / "supervisor_harness" / (
    "AGENT_LOG_INGAME_DISCOVERY_V2_TWO_MEMBER_POOL_CONTROLLER_2026-09-29.md"
)
CONTROLLER_LOG_SHA256 = (
    "d8a28ecce7e46f2ccebc2280d4e425bf0674325351d4f55c1b923d7b6b49108f"
)
QUESTION_RULE_DIGEST = (
    "bd0f59c86735a2f20175b9b0784ecfe33fc51468ca3614edbdea07f454c2b8ae"
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

TASK_ID = "InGameStateSupportGeometryAudit-v1"
QUESTION_ID = "ingame-v0-state-support-geometry-v1-q1"
EXPECTED_SOURCE_EVENTS = 195
EXPECTED_MATERIALIZED_EVENTS = 193
EXPECTED_EXCLUSIONS = {
    "2025_04_GB_DAL": "unresolved_outcome",
    "2025_05_TEN_ARI": "market_trade_too_stale",
}
EXPECTED_CHECK_EVENTS = 87
EXPECTED_CHECK_COUNTS = (26, 16, 28, 17)
EXPECTED_FIT_COUNTS = (106, 132, 148, 176)
K_NEIGHBORS = 5
SUPPORT_QUANTILE = 0.95
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
CONTINUOUS_INDICES = (0, 1, 7, 8)
BINARY_INDICES = (2, 3, 4, 5, 6)
BOOTSTRAP_SEED = 20260929
BOOTSTRAP_REPLICATES = 10_000
MODEL_FITS = 0


def _sha256(path: Path) -> str:
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _strict_json(path: Path) -> object:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant forbidden: {value}")

    return json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)


def _atomic_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _validate_paths(v0_root: Path, output: Path, *, allow_test_paths: bool) -> None:
    v0_root, output = v0_root.resolve(), output.resolve()
    if output.exists():
        raise FileExistsError("output already exists; one frozen audit requires a fresh ID")
    if v0_root == output or v0_root in output.parents:
        raise ValueError("audit output cannot be inside the immutable v0 artifact")
    if allow_test_paths:
        return
    if v0_root != V0_ARTIFACT_ROOT.resolve():
        raise ValueError("runner is bound to the exact reviewed in-game v0 artifact")
    try:
        output.relative_to(PERSISTENT_ARTIFACT_ROOT.resolve())
    except ValueError as error:
        raise ValueError("output must be in persistent local MarketRSI artifacts") from error
    lowered = str(output).lower()
    if any(marker in lowered for marker in (
            "/tmp/", "/private/var/", "icloud", "mobile documents",
            "dropbox", "google drive")):
        raise ValueError("temporary or cloud-looking output is forbidden")


def _validate_hashes(root: Path, expected_hashes: dict[str, str]) -> dict[str, str]:
    if set(expected_hashes) != set(EXPECTED_V0_HASHES):
        raise ValueError("expected hash map must name every frozen v0 artifact")
    observed = {}
    for name, expected in expected_hashes.items():
        path = root / name
        if not path.is_file():
            raise ValueError(f"frozen v0 artifact file is missing: {name}")
        observed[name] = _sha256(path)
        if observed[name] != expected:
            raise ValueError(f"frozen v0 artifact hash changed: {name}")
    return observed


def _finite_float(row: dict[str, str], name: str) -> float:
    try:
        value = float(row[name])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"{name} is missing or nonnumeric") from error
    if not math.isfinite(value):
        raise ValueError(f"{name} is nonfinite")
    return value


def _state_vector(row: dict[str, str]) -> tuple[float, ...]:
    down_value = _finite_float(row, "down")
    down = int(down_value)
    if down_value != down or down not in (1, 2, 3, 4):
        raise ValueError("down is not exactly one of 1,2,3,4")
    possession = _finite_float(row, "possession_is_home")
    if possession not in (0.0, 1.0):
        raise ValueError("possession_is_home is not binary")
    values = (
        _finite_float(row, "home_score_diff_pre"),
        _finite_float(row, "regulation_seconds_remaining"),
        possession,
        *(1.0 if down == candidate else 0.0 for candidate in (1, 2, 3, 4)),
        _finite_float(row, "yards_to_go"),
        _finite_float(row, "home_possession_field_advantage"),
    )
    if len(values) != len(STATE_FEATURE_NAMES) or not np.isfinite(values).all():
        raise ValueError("state vector differs from the frozen nine-column representation")
    return values


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def _validate_folds(folds: object) -> list[dict]:
    if not isinstance(folds, list) or len(folds) != 4:
        raise ValueError("v0 must contain exactly four chronological folds")
    result = []
    prior_checks: list[str] = []
    prior_fit: list[str] | None = None
    for expected_number, raw in enumerate(folds, 1):
        if not isinstance(raw, dict) or raw.get("fold") != expected_number:
            raise ValueError("fold numbering changed")
        fit = raw.get("fit_dates")
        check = raw.get("check_dates")
        if (not isinstance(fit, list) or not isinstance(check, list)
                or len(check) != 5 or len(set(fit + check)) != len(fit) + len(check)):
            raise ValueError("fold date sets are malformed or overlap")
        if fit != sorted(fit) or check != sorted(check) or max(fit) >= min(check):
            raise ValueError("folds are not strictly chronological")
        if prior_fit is not None and fit != prior_fit + prior_checks:
            raise ValueError("expanding fit dates do not equal prior fit plus prior check")
        result.append({"fold": expected_number, "fit_dates": fit, "check_dates": check})
        prior_fit, prior_checks = list(fit), list(check)
    return result


def _schedule_date_from_checkpoint(value: str, frozen_dates: set[str]) -> str:
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as error:
        raise ValueError("checkpoint decision_time_utc is invalid") from error
    if moment.tzinfo is None:
        raise ValueError("checkpoint decision_time_utc lacks a timezone")
    eastern_date = moment.astimezone(ZoneInfo("America/New_York")).date()
    if eastern_date.isoformat() in frozen_dates:
        return eastern_date.isoformat()
    # A Monday-night game can cross midnight Eastern before the Q3 checkpoint;
    # the frozen schedule date remains the prior day.  This fallback is allowed
    # only when the same frozen fold calendar names that prior day.
    prior = (eastern_date - timedelta(days=1)).isoformat()
    if prior not in frozen_dates:
        raise ValueError("checkpoint cannot be assigned to a frozen schedule date")
    return prior


def _load_frozen_inputs(
    v0_root: Path,
    *,
    expected_hashes: dict[str, str],
    require_exact_counts: bool,
) -> dict:
    hashes = _validate_hashes(v0_root, expected_hashes)
    manifest = _strict_json(v0_root / "manifest.json")
    lock = _strict_json(v0_root / "pre_score_lock.json")
    receipts = _strict_json(v0_root / "input_receipts.json")
    exclusions = _strict_json(v0_root / "exclusions.json")
    scorecard = _strict_json(v0_root / "scorecard.json")
    if not all(isinstance(value, dict) for value in (
            manifest, lock, receipts, exclusions, scorecard)):
        raise ValueError("v0 JSON roots must be objects")
    if (manifest.get("schema") != "nfl_ingame_win_probability_train_manifest_v0"
            or manifest.get("complete") is not True
            or manifest.get("task_id") != "InGameWinProbabilityTrainDiagnostic-v0"
            or manifest.get("route_dev_opened") is not False
            or manifest.get("sealed_final_opened") is not False
            or manifest.get("external_fetch") is not False
            or manifest.get("provider_cost_usd") != "0"
            or manifest.get("promotion_authorized") is not False):
        raise ValueError("v0 completion or protected-data boundary changed")
    for name, manifest_key in (
        ("pre_score_lock.json", "pre_score_lock_sha256"),
        ("input_receipts.json", "input_receipts_sha256"),
        ("exclusions.json", "exclusions_sha256"),
        ("predictions.csv", "predictions_sha256"),
        ("scorecard.json", "scorecard_sha256"),
    ):
        if manifest.get(manifest_key) != hashes[name]:
            raise ValueError(f"v0 manifest no longer binds {name}")
    if receipts.get("checkpoint_state_sha256") != hashes["checkpoint_state.csv"]:
        raise ValueError("v0 input receipt no longer binds checkpoint_state.csv")
    folds = _validate_folds(lock.get("folds"))
    scored_folds = scorecard.get("folds")
    if not isinstance(scored_folds, list) or len(scored_folds) != 4:
        raise ValueError("v0 scored fold records are malformed")
    for expected_number, scored in enumerate(scored_folds, 1):
        if (not isinstance(scored, dict)
                or scored.get("fold") != expected_number
                or scored.get("fit_label_unavailable_game_ids") != []):
            raise ValueError("v0 fit-label availability or scored fold identity changed")
        if require_exact_counts and (
                scored.get("fit_events") != EXPECTED_FIT_COUNTS[expected_number - 1]
                or scored.get("check_events") != EXPECTED_CHECK_COUNTS[expected_number - 1]):
            raise ValueError("v0 scored fold population changed")

    exclusion_rows = exclusions.get("exclusions")
    if not isinstance(exclusion_rows, list):
        raise ValueError("v0 exclusions are malformed")
    observed_exclusions = {
        str(row.get("game_id")): str(row.get("reason")) for row in exclusion_rows
    }
    if observed_exclusions != EXPECTED_EXCLUSIONS:
        raise ValueError("v0 exact two-event exclusion lineage changed")

    state_rows = _read_csv(v0_root / "checkpoint_state.csv")
    prediction_rows = _read_csv(v0_root / "predictions.csv")
    if len({row.get("game_id") for row in state_rows}) != len(state_rows):
        raise ValueError("checkpoint_state contains duplicate game IDs")
    if len({row.get("game_id") for row in prediction_rows}) != len(prediction_rows):
        raise ValueError("predictions contains duplicate game IDs")
    if require_exact_counts and (
            len(state_rows) != EXPECTED_SOURCE_EVENTS
            or len(prediction_rows) != EXPECTED_CHECK_EVENTS):
        raise ValueError("v0 source/check denominator changed")

    frozen_dates = {
        value for fold in folds for key in ("fit_dates", "check_dates")
        for value in fold[key]
    }
    prediction_by_game = {row["game_id"]: row for row in prediction_rows}
    materialized = []
    for raw in state_rows:
        game_id = raw.get("game_id")
        if not game_id or raw.get("status") != "eligible":
            raise ValueError("checkpoint_state contains a noneligible or unnamed row")
        derived_date = _schedule_date_from_checkpoint(
            raw.get("decision_time_utc", ""), frozen_dates
        )
        if game_id in prediction_by_game:
            predicted_date = prediction_by_game[game_id].get("game_date")
            if derived_date != predicted_date:
                raise ValueError("checkpoint/prediction schedule-date identity changed")
        if game_id not in observed_exclusions:
            materialized.append({
                "game_id": game_id,
                "game_date": derived_date,
                "game_week": game_id.split("_")[1],
                "features": _state_vector(raw),
            })
    if require_exact_counts and len(materialized) != EXPECTED_MATERIALIZED_EVENTS:
        raise ValueError("v0 195 -> 193 + 2 lineage changed")

    checks = []
    for raw in prediction_rows:
        try:
            fold_number = int(raw["fold"])
            outcome = int(raw["outcome"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("prediction fold/outcome is invalid") from error
        if fold_number not in (1, 2, 3, 4) or outcome not in (0, 1):
            raise ValueError("prediction fold/outcome is outside the frozen contract")
        market_probability = _finite_float(raw, "market_model_probability")
        state_probability = _finite_float(raw, "market_plus_state_probability")
        if not (0 < market_probability < 1 and 0 < state_probability < 1):
            raise ValueError("frozen prediction probability is outside (0,1)")
        market_loss = (market_probability - outcome) ** 2
        state_loss = (state_probability - outcome) ** 2
        checks.append({
            "fold": fold_number,
            "game_id": raw["game_id"],
            "game_date": raw["game_date"],
            "game_week": raw["game_week"],
            "outcome": outcome,
            "delta": state_loss - market_loss,
        })

    state_by_game = {row["game_id"]: row for row in materialized}
    check_ids = {row["game_id"] for row in checks}
    if not check_ids.issubset(state_by_game):
        raise ValueError("prediction mask is not a subset of materialized checkpoint rows")
    for fold in folds:
        expected_ids = {
            row["game_id"] for row in materialized
            if row["game_date"] in fold["check_dates"]
        }
        observed_ids = {
            row["game_id"] for row in checks if row["fold"] == fold["fold"]
        }
        if observed_ids != expected_ids:
            raise ValueError(f"fold {fold['fold']} check mask differs from frozen predictions")
        fit_count = sum(
            row["game_date"] in fold["fit_dates"] for row in materialized
        )
        if require_exact_counts and fit_count != EXPECTED_FIT_COUNTS[fold["fold"] - 1]:
            raise ValueError(f"fold {fold['fold']} fit mask differs from v0")
    observed_check_counts = tuple(
        sum(row["fold"] == fold for row in checks) for fold in (1, 2, 3, 4)
    )
    if require_exact_counts and observed_check_counts != EXPECTED_CHECK_COUNTS:
        raise ValueError("v0 per-fold check counts changed")

    check_key_digest = _canonical_digest([
        [raw["event_id"], raw["market_id"], int(raw["cutoff_ms"])]
        for raw in prediction_rows
    ])
    expected_check_digest = scorecard.get("identical_masks", {}).get("check_key_sha256")
    if check_key_digest != expected_check_digest:
        raise ValueError("v0 scorecard and prediction check-key masks differ")
    score_delta = scorecard.get("deltas", {}).get(
        "state_minus_market_model", {}
    ).get("brier")
    recomputed_delta = math.fsum(row["delta"] for row in checks) / len(checks)
    if (not isinstance(score_delta, (float, int))
            or not math.isclose(recomputed_delta, score_delta, abs_tol=1e-15)):
        raise ValueError("frozen per-event Brier deltas do not reproduce the v0 scorecard")

    return {
        "hashes": hashes,
        "manifest": manifest,
        "folds": folds,
        "materialized": materialized,
        "checks": checks,
        "state_by_game": state_by_game,
        "check_key_sha256": check_key_digest,
        "recomputed_mean_delta": recomputed_delta,
    }


def _scale_state_fit_only(
    fit: np.ndarray, check: np.ndarray
) -> tuple[np.ndarray, np.ndarray, dict]:
    if (fit.ndim != 2 or check.ndim != 2
            or fit.shape[1] != len(STATE_FEATURE_NAMES)
            or check.shape[1] != len(STATE_FEATURE_NAMES)):
        raise ValueError("fit/check state matrices have the wrong shape")
    if fit.shape[0] <= K_NEIGHBORS or check.shape[0] == 0:
        raise ValueError("support geometry needs >5 fit rows and nonempty check rows")
    if not np.isfinite(fit).all() or not np.isfinite(check).all():
        raise ValueError("support geometry received nonfinite state data")
    fit_result, check_result = fit.copy(), check.copy()
    scaler = StandardScaler().fit(fit[:, CONTINUOUS_INDICES])
    fit_result[:, CONTINUOUS_INDICES] = scaler.transform(fit[:, CONTINUOUS_INDICES])
    check_result[:, CONTINUOUS_INDICES] = scaler.transform(check[:, CONTINUOUS_INDICES])
    if not np.array_equal(fit_result[:, BINARY_INDICES], fit[:, BINARY_INDICES]):
        raise RuntimeError("binary state columns were unexpectedly scaled")
    if not np.array_equal(check_result[:, BINARY_INDICES], check[:, BINARY_INDICES]):
        raise RuntimeError("check binary state columns were unexpectedly scaled")
    return fit_result, check_result, {
        "continuous_feature_names": [STATE_FEATURE_NAMES[index] for index in CONTINUOUS_INDICES],
        "mean": [float(value) for value in scaler.mean_],
        "scale": [float(value) for value in scaler.scale_],
    }


def _mean_k_distances(
    query: np.ndarray, reference: np.ndarray, *, leave_self_out: bool
) -> np.ndarray:
    if query.ndim != 2 or reference.ndim != 2 or query.shape[1] != reference.shape[1]:
        raise ValueError("query/reference matrices must have matching feature widths")
    distances = np.linalg.norm(query[:, None, :] - reference[None, :, :], axis=2)
    if leave_self_out:
        if query.shape != reference.shape or not np.array_equal(query, reference):
            raise ValueError("leave-one-out requires the same query/reference matrix")
        np.fill_diagonal(distances, np.inf)
    finite_per_row = np.isfinite(distances).sum(axis=1)
    if np.any(finite_per_row < K_NEIGHBORS):
        raise ValueError("fewer than five finite neighbors are available")
    nearest = np.partition(distances, K_NEIGHBORS - 1, axis=1)[:, :K_NEIGHBORS]
    means = nearest.mean(axis=1)
    if not np.isfinite(means).all():
        raise ValueError("nearest-neighbor mean distance is nonfinite")
    return means


def _feature_range_violations(fit: np.ndarray, check: np.ndarray) -> list[list[str]]:
    lower, upper = np.min(fit, axis=0), np.max(fit, axis=0)
    result = []
    for row in check:
        result.append([
            name for index, name in enumerate(STATE_FEATURE_NAMES)
            if row[index] < lower[index] or row[index] > upper[index]
        ])
    return result


def _fold_geometry(fit: np.ndarray, check: np.ndarray) -> dict:
    scaled_fit, scaled_check, scaler = _scale_state_fit_only(fit, check)
    fit_distances = _mean_k_distances(scaled_fit, scaled_fit, leave_self_out=True)
    threshold = float(np.quantile(fit_distances, SUPPORT_QUANTILE, method="linear"))
    check_distances = _mean_k_distances(
        scaled_check, scaled_fit, leave_self_out=False
    )
    unsupported = check_distances > threshold
    violations = _feature_range_violations(fit, check)
    return {
        "threshold": threshold,
        "fit_leave_one_out_mean_distances": fit_distances,
        "check_mean_distances": check_distances,
        "unsupported": unsupported,
        "feature_range_violations": violations,
        "scaler": scaler,
    }


def _mean(values: Sequence[float]) -> float | None:
    return math.fsum(values) / len(values) if values else None


def _stratum_summary(
    records: Sequence[dict], *, require_positive_total: bool = False
) -> dict:
    supported = [record["delta"] for record in records if not record["unsupported"]]
    unsupported = [record["delta"] for record in records if record["unsupported"]]
    total_sum = math.fsum(record["delta"] for record in records)
    unsupported_sum = math.fsum(unsupported)
    if require_positive_total and total_sum <= 0:
        raise ValueError("frozen total state-minus-market-model Brier harm is not positive")
    supported_mean, unsupported_mean = _mean(supported), _mean(unsupported)
    contrast = (
        unsupported_mean - supported_mean
        if supported_mean is not None and unsupported_mean is not None else None
    )
    return {
        "events": len(records),
        "supported_events": len(supported),
        "unsupported_events": len(unsupported),
        "unsupported_share": len(unsupported) / len(records),
        "supported_mean_delta": supported_mean,
        "unsupported_mean_delta": unsupported_mean,
        "supported_signed_sum": math.fsum(supported),
        "unsupported_signed_sum": unsupported_sum,
        "all_signed_sum": total_sum,
        "unsupported_signed_contribution": (
            unsupported_sum / total_sum if total_sum != 0 else None
        ),
        "unsupported_minus_supported_mean_delta": contrast,
    }


def support_decision(records: Sequence[dict]) -> tuple[str, dict]:
    if len(records) != EXPECTED_CHECK_EVENTS:
        raise ValueError("decision requires the exact 87-row v0 check mask")
    aggregate = _stratum_summary(records, require_positive_total=True)
    fold_summaries = []
    positive_contrasts = 0
    for fold_number in (1, 2, 3, 4):
        fold_records = [row for row in records if row["fold"] == fold_number]
        summary = _stratum_summary(fold_records)
        contrast = summary["unsupported_minus_supported_mean_delta"]
        if contrast is not None and contrast > 0:
            positive_contrasts += 1
        fold_summaries.append({"fold": fold_number, **summary})
    support_conditions = {
        "unsupported_share_at_least_10_percent": aggregate["unsupported_share"] >= 0.10,
        "unsupported_signed_contribution_at_least_50_percent": (
            aggregate["unsupported_signed_contribution"] >= 0.50
        ),
        "unsupported_mean_delta_exceeds_supported": (
            aggregate["unsupported_minus_supported_mean_delta"] is not None
            and aggregate["unsupported_minus_supported_mean_delta"] > 0
        ),
        "positive_fold_contrast_at_least_3_of_4": positive_contrasts >= 3,
    }
    refute_conditions = {
        "unsupported_share_below_5_percent": aggregate["unsupported_share"] < 0.05,
        "unsupported_signed_contribution_nonpositive": (
            aggregate["unsupported_signed_contribution"] <= 0
        ),
        "aggregate_contrast_nonpositive": (
            aggregate["unsupported_minus_supported_mean_delta"] is not None
            and aggregate["unsupported_minus_supported_mean_delta"] <= 0
        ),
        "positive_fold_contrast_at_most_1_of_4": positive_contrasts <= 1,
    }
    if all(support_conditions.values()):
        decision = "SAMPLE_SUPPORT_EXPLANATION_SUPPORTED"
    elif any(refute_conditions.values()):
        decision = "SAMPLE_SUPPORT_EXPLANATION_REFUTED"
    else:
        decision = "SAMPLE_SUPPORT_EXPLANATION_INCONCLUSIVE"
    return decision, {
        "aggregate": aggregate,
        "folds": fold_summaries,
        "positive_fold_contrasts": positive_contrasts,
        "support_conditions": support_conditions,
        "refute_conditions": refute_conditions,
    }


def _group_contrast_bootstrap(
    records: Sequence[dict], group: str, *, seed: int = BOOTSTRAP_SEED,
    replicates: int = BOOTSTRAP_REPLICATES,
) -> dict:
    buckets: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        buckets[str(record[group])].append(record)
    labels = sorted(buckets)
    if len(labels) < 2:
        raise ValueError("complete-group interval requires at least two groups")
    generator = np.random.default_rng(seed)
    draws = []
    undefined_draws = 0
    for _ in range(replicates):
        sampled = generator.choice(labels, size=len(labels), replace=True)
        selected = [record for label in sampled for record in buckets[str(label)]]
        supported = [row["delta"] for row in selected if not row["unsupported"]]
        unsupported = [row["delta"] for row in selected if row["unsupported"]]
        if not supported or not unsupported:
            undefined_draws += 1
            continue
        draws.append(_mean(unsupported) - _mean(supported))
    point = _stratum_summary(records)["unsupported_minus_supported_mean_delta"]
    if point is None or len(draws) < max(100, replicates // 2):
        return {
            "group": group, "groups": len(labels), "events": len(records),
            "point_unsupported_minus_supported_mean_delta": point,
            "interval_95": None, "valid_draws": len(draws),
            "undefined_draws": undefined_draws,
            "bootstrap_replicates": replicates, "bootstrap_seed": seed,
            "status": "insufficient_stratified_complete-group_draws",
        }
    return {
        "group": group,
        "groups": len(labels),
        "events": len(records),
        "point_unsupported_minus_supported_mean_delta": point,
        "interval_95": [
            float(np.quantile(draws, 0.025, method="linear")),
            float(np.quantile(draws, 0.975, method="linear")),
        ],
        "valid_draws": len(draws),
        "undefined_draws": undefined_draws,
        "bootstrap_replicates": replicates,
        "bootstrap_seed": seed,
        "status": "complete",
        "resampling_rule": (
            "resample complete schedule groups, preserve every event in each selected "
            "group, then recompute the equal-event unsupported-minus-supported contrast"
        ),
    }


def _audit(inputs: dict) -> tuple[list[dict], dict]:
    materialized = inputs["materialized"]
    state_by_game = inputs["state_by_game"]
    records = []
    fold_geometry = []
    for fold in inputs["folds"]:
        fit_rows = sorted(
            [row for row in materialized if row["game_date"] in fold["fit_dates"]],
            key=lambda row: row["game_id"],
        )
        checks = sorted(
            [row for row in inputs["checks"] if row["fold"] == fold["fold"]],
            key=lambda row: row["game_id"],
        )
        check_states = [state_by_game[row["game_id"]] for row in checks]
        fit_matrix = np.asarray([row["features"] for row in fit_rows], dtype=float)
        check_matrix = np.asarray([row["features"] for row in check_states], dtype=float)
        geometry = _fold_geometry(fit_matrix, check_matrix)
        range_counter: Counter[str] = Counter()
        for check, distance, unsupported, violations in zip(
                checks, geometry["check_mean_distances"], geometry["unsupported"],
                geometry["feature_range_violations"], strict=True):
            range_counter.update(violations)
            records.append({
                **check,
                "mean_5nn_distance": float(distance),
                "fit_only_support_cutoff": geometry["threshold"],
                "unsupported": bool(unsupported),
                "feature_range_violations": violations,
            })
        fold_geometry.append({
            "fold": fold["fold"],
            "fit_events": len(fit_rows),
            "check_events": len(checks),
            "k": K_NEIGHBORS,
            "fit_leave_one_out": True,
            "fit_only_quantile": SUPPORT_QUANTILE,
            "quantile_interpolation": "linear",
            "fit_only_support_cutoff": geometry["threshold"],
            "unsupported_events": int(np.sum(geometry["unsupported"])),
            "feature_range_violation_events": sum(
                bool(value) for value in geometry["feature_range_violations"]
            ),
            "feature_range_violation_counts": dict(sorted(range_counter.items())),
            "scaler": geometry["scaler"],
        })
    if len(records) != EXPECTED_CHECK_EVENTS or len({row["game_id"] for row in records}) != len(records):
        raise RuntimeError("audit did not preserve the exact 87 unique check games")
    decision, decision_evidence = support_decision(records)
    scorecard = {
        "schema": "nfl_ingame_state_support_geometry_scorecard_v1",
        "task_id": TASK_ID,
        "question_id": QUESTION_ID,
        "question_rule_digest": QUESTION_RULE_DIGEST,
        "decision": decision,
        "no_prediction_candidate_emitted": True,
        "incumbent_or_keep_revert_changed": False,
        "model_fits": MODEL_FITS,
        "preprocessing_fits": len(inputs["folds"]),
        "source_lineage": {
            "source_events": EXPECTED_SOURCE_EVENTS,
            "materialized_events": EXPECTED_MATERIALIZED_EVENTS,
            "excluded_events": len(EXPECTED_EXCLUSIONS),
            "check_events": len(records),
            "check_dates": len({row["game_date"] for row in records}),
            "check_game_weeks": len({row["game_week"] for row in records}),
            "v0_check_key_sha256": inputs["check_key_sha256"],
            "v0_mean_state_minus_market_model_brier": inputs["recomputed_mean_delta"],
        },
        "method": {
            "state_feature_names": list(STATE_FEATURE_NAMES),
            "continuous_standardized_on_fold_fit_rows_only": [
                STATE_FEATURE_NAMES[index] for index in CONTINUOUS_INDICES
            ],
            "binary_columns_unchanged": [STATE_FEATURE_NAMES[index] for index in BINARY_INDICES],
            "fit_distance": "mean Euclidean distance to five nearest other fit rows",
            "check_distance": "mean Euclidean distance to five nearest fit rows",
            "support_cutoff": "fit-only 95th percentile with linear interpolation",
            "unsupported_rule": "check distance strictly greater than the fit-only cutoff",
        },
        "fold_geometry": fold_geometry,
        "decision_evidence": decision_evidence,
        "complete_group_intervals": {
            "schedule_date": _group_contrast_bootstrap(records, "game_date"),
            "observed_game_week": _group_contrast_bootstrap(records, "game_week"),
        },
        "feature_range_violations": {
            "events": sum(bool(row["feature_range_violations"]) for row in records),
            "counts_by_feature": dict(sorted(Counter(
                name for row in records for name in row["feature_range_violations"]
            ).items())),
        },
        "research_credit_eligibility_after_independent_review": (
            2 if decision != "SAMPLE_SUPPORT_EXPLANATION_INCONCLUSIVE" else 1
        ),
        "research_credit_awarded": 0,
        "research_credit_note": "Supervisor independent review is required before credit is awarded.",
        "evidence_classification": "sample-support/data-representation diagnostic; research mechanism not tested",
        "inference_boundary": (
            "repeatedly inspected opened-Train historical diagnostic using frozen v0 "
            "predictions; PBP publish/receive latency is unobserved; not realtime, "
            "untouched OOS, promotion, PnL, or a new prediction candidate"
        ),
        "cross_task_numeric_comparison_forbidden": True,
        "route_dev_opened": False,
        "sealed_final_opened": False,
        "external_fetch": False,
        "paid_provider": False,
        "provider_cost_usd": "0",
        "promotion_authorized": False,
    }
    return records, scorecard


def _write_event_audit(path: Path, records: Sequence[dict]) -> None:
    fields = (
        "fold", "game_id", "game_date", "game_week", "outcome",
        "state_minus_market_model_brier_delta", "mean_5nn_distance",
        "fit_only_support_cutoff", "unsupported", "feature_range_violations",
    )
    temporary = path.with_suffix(".csv.tmp")
    with temporary.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for record in sorted(records, key=lambda row: (row["fold"], row["game_id"])):
            writer.writerow({
                "fold": record["fold"], "game_id": record["game_id"],
                "game_date": record["game_date"], "game_week": record["game_week"],
                "outcome": record["outcome"],
                "state_minus_market_model_brier_delta": record["delta"],
                "mean_5nn_distance": record["mean_5nn_distance"],
                "fit_only_support_cutoff": record["fit_only_support_cutoff"],
                "unsupported": str(record["unsupported"]).lower(),
                "feature_range_violations": "|".join(record["feature_range_violations"]),
            })
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def run(
    v0_root: Path,
    output: Path,
    *,
    allow_test_paths: bool = False,
    expected_hashes: dict[str, str] | None = None,
    generated_utc: str | None = None,
) -> dict:
    v0_root, output = Path(v0_root).resolve(), Path(output).resolve()
    _validate_paths(v0_root, output, allow_test_paths=allow_test_paths)
    if not allow_test_paths and _sha256(CONTROLLER_LOG) != CONTROLLER_LOG_SHA256:
        raise ValueError("frozen Controller selection log hash changed")
    hashes = EXPECTED_V0_HASHES if expected_hashes is None else expected_hashes
    inputs = _load_frozen_inputs(
        v0_root, expected_hashes=hashes, require_exact_counts=not allow_test_paths
    )
    output.mkdir(parents=True, exist_ok=False)
    try:
        lock = {
            "schema": "nfl_ingame_state_support_geometry_pre_audit_lock_v1",
            "generated_utc": generated_utc or datetime.now(timezone.utc).isoformat(),
            "task_id": TASK_ID,
            "question_id": QUESTION_ID,
            "question_rule_digest": QUESTION_RULE_DIGEST,
            "controller_log_sha256": CONTROLLER_LOG_SHA256,
            "research_parent": "archived v0 market_plus_state_model negative branch",
            "comparison_incumbent": "v0 raw_market arm",
            "prediction_candidate": False,
            "k": K_NEIGHBORS,
            "support_quantile": SUPPORT_QUANTILE,
            "quantile_interpolation": "linear",
            "unsupported_comparison": "strictly above cutoff",
            "model_fits": MODEL_FITS,
            "one_audit_no_retry": True,
            "v0_hashes": inputs["hashes"],
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "external_fetch": False,
            "paid_provider": False,
            "provider_cost_usd": "0",
            "promotion_authorized": False,
        }
        _atomic_json(output / "pre_audit_lock.json", lock)
        records, scorecard = _audit(inputs)
        _write_event_audit(output / "support_geometry.csv", records)
        _atomic_json(output / "scorecard.json", scorecard)
        manifest = {
            "schema": "nfl_ingame_state_support_geometry_manifest_v1",
            "complete": True,
            "completed_utc": generated_utc or datetime.now(timezone.utc).isoformat(),
            "task_id": TASK_ID,
            "decision": scorecard["decision"],
            "source_events": EXPECTED_SOURCE_EVENTS,
            "materialized_events": EXPECTED_MATERIALIZED_EVENTS,
            "excluded_events": len(EXPECTED_EXCLUSIONS),
            "check_events": len(records),
            "model_fits": MODEL_FITS,
            "pre_audit_lock_sha256": _sha256(output / "pre_audit_lock.json"),
            "support_geometry_sha256": _sha256(output / "support_geometry.csv"),
            "scorecard_sha256": _sha256(output / "scorecard.json"),
            "v0_manifest_sha256": inputs["hashes"]["manifest.json"],
            "v0_checkpoint_state_sha256": inputs["hashes"]["checkpoint_state.csv"],
            "v0_predictions_sha256": inputs["hashes"]["predictions.csv"],
            "historical_event_clock_only": True,
            "no_prediction_candidate_emitted": True,
            "incumbent_or_keep_revert_changed": False,
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
                "schema": "nfl_ingame_state_support_geometry_failure_v1",
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
    parser.add_argument("--v0-artifact", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.v0_artifact, args.output)
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
