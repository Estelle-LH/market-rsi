#!/usr/bin/env python3
"""Opened-Train Discovery runner for MarketRecencyWeightedCompositeDispersion-v5.

This retains Attempt 3's exact recent weighted path composite and adds one
fit-only market/path-orthogonal probability-dispersion family.  All controls
are read only from the completed Attempt-4 artifact.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Sequence

import numpy as np

from experiments import nfl_market_all_prior_decay_composite_path_train_diagnostic as parent


incumbent = parent.parent
recent = incumbent.parent
base = parent.base
offset = parent.offset
calibration = parent.calibration
prior = parent.prior
SOURCE_ROOT = parent.SOURCE_ROOT
PERSISTENT_ARTIFACT_ROOT = parent.PERSISTENT_ARTIFACT_ROOT
EXPECTED_EVENTS = parent.EXPECTED_EVENTS
EXPECTED_DATES = parent.EXPECTED_DATES
EXPECTED_MATERIALIZED_KEY_SHA256 = parent.EXPECTED_MATERIALIZED_KEY_SHA256
EXPECTED_CHECK_MASK_SHA256 = parent.EXPECTED_CHECK_MASK_SHA256
MAX_STALENESS_SECONDS = parent.MAX_STALENESS_SECONDS
STRICT_WIN_TOLERANCE = parent.STRICT_WIN_TOLERANCE
MINIMUM_RECENT_ROWS = parent.MINIMUM_RECENT_ROWS
EXPECTED_REAL_RECENT = incumbent.EXPECTED_REAL_RECENT

EXPECTED_PARENT_RUNNER_SHA256 = "c9fc5b9d01a28181382ca47d9545ca7ce06c769b6165b482b84fc26df4537139"
EXPECTED_PARENT_TEST_SHA256 = "7183c64040bba0e02ae583b34050e87f6f4f15a42183e18eccba7a76626da2e7"
CONTROLLER_PROPOSAL_PATH = (
    Path(__file__).resolve().parents[1] / "supervisor_harness"
    / "AGENT_LOG_DISCOVERY_ATTEMPT5_CONTROLLER_2026-09-29.md"
)
EXPECTED_CONTROLLER_PROPOSAL_SHA256 = "29bd05297afca88a6949aa1e75241cf88da458be7018862317deb74618758436"
PARENT_RESULT_REVIEW_PATH = (
    Path(__file__).resolve().parents[1] / "supervisor_harness"
    / "AGENT_LOG_MARKET_ALL_PRIOR_DECAY_COMPOSITE_PATH_V4_RESULT_INDEPENDENT_REVIEW_2026-09-29.md"
)
EXPECTED_PARENT_RESULT_REVIEW_SHA256 = (
    "c5b706e474af4ef1fac34eab1c19567f03c300f0c77f03bafcd129d09913f882"
)

ARCHIVED_PARENT_ROOT = PERSISTENT_ARTIFACT_ROOT / (
    "first-real-train-diagnostic-market-all-prior-decay-composite-path-20260929-01"
)
ARCHIVED_PARENT_SHA256 = MappingProxyType({
    "exclusions.json": "5a024887952e3876ad8f7e4dc03fc0c343193074d97bc8025a622d08b3aeb4ed",
    "input_receipts.json": "cced501566428aa3011d6e301b3fdb18c5368a2318840ec3f766d87bb91094f4",
    "manifest.json": "74569b89cc3497d732f0fabb1a2236584999d4a7e704955db7102ef5c62d831b",
    "pre_score_lock.json": "c42702a47b4a181349edceeb493265097c9766d827447a8cae798dd3aec7e173",
    "predictions.csv": "ba9885f8d67c9c20838dabd251354d4803afb9ff90c39f990f3c0521d7c8c128",
    "scorecard.json": "407cf8f393a0196a3893b1d574e714a2a3b6a448084cd7b42dcd4fd63b000643",
    "staleness_inventory.json": "3b545bd2542b4a4102ed0aa0f2adaed435322fc58bea06b599ebee765abea10e",
})
ARCHIVED_FIELDS = (*parent.ARCHIVED_FIELDS, "all_prior_decay_candidate_probability")
DISPERSION_FEATURES = tuple(
    f"trailing_{minutes}m_weighted_std_home_probability"
    for minutes in (15, 60, 240)
)
INACTIVE_STD_THRESHOLD = 1e-8

CANDIDATE_SPEC = MappingProxyType({
    "name": "MarketRecencyWeightedCompositeDispersion-v5",
    "parent_representation": dict(recent.CANDIDATE_SPEC),
    "candidate_fit_support": "Attempt-3 exact selected three-week rows",
    "event_weights_oldest_middle_newest": (0.25, 0.50, 1.00),
    "dispersion_raw": "mean(weighted_std_home_probability_15m_60m_240m)",
    "dispersion_residualization": "selected-fit-only OLS against [1,z_market,z_composite]",
    "lstsq_rcond": 1e-12,
    "rank_required": 3,
    "inactive_fit_population_std_at_most": INACTIVE_STD_THRESHOLD,
    "linear_predictor": "eta=market_logit+w_composite*z_composite+w_dispersion*z_dispersion",
    "objective": "event-weighted mean Bernoulli NLL plus 0.5*(w_composite^2+w_dispersion^2)",
    "lambda": 1.0,
    "intercept": False,
    "market_recalibration_coefficient": False,
    "coefficient_constraint": "unconstrained",
    "initial_parameters": "two zeros",
    "optimizer": "L-BFGS-B analytic gradient maxiter=1000 gtol=1e-8 ftol=1e-12",
    "dtype": "float64",
    "hyperparameter_search": False,
})
EXPECTED_CANDIDATE_SPEC_SHA256 = (
    "b8473e60a211228186d62e41e8443d89040f1cfa582dae966767ddaf6db54b6a"
)


def execution_identity() -> dict:
    return {
        "parent_runner_sha256": base._sha256(Path(parent.__file__)),
        "parent_test_sha256": base._sha256(
            Path(__file__).resolve().parents[1] / "tests"
            / "test_nfl_market_all_prior_decay_composite_path_train_diagnostic.py"
        ),
        "controller_proposal_sha256": base._sha256(CONTROLLER_PROPOSAL_PATH),
        "parent_result_review_sha256": base._sha256(PARENT_RESULT_REVIEW_PATH),
        "runtime_and_deeper_dependencies": parent._validate_execution_identity(),
    }


def _validate_execution_identity() -> dict:
    identity = execution_identity()
    expected = {
        "parent_runner_sha256": EXPECTED_PARENT_RUNNER_SHA256,
        "parent_test_sha256": EXPECTED_PARENT_TEST_SHA256,
        "controller_proposal_sha256": EXPECTED_CONTROLLER_PROPOSAL_SHA256,
        "parent_result_review_sha256": EXPECTED_PARENT_RESULT_REVIEW_SHA256,
    }
    if any(identity[key] != value for key, value in expected.items()):
        raise RuntimeError(f"frozen execution identity changed: {identity}")
    return identity


def _validate_frozen_specs() -> None:
    parent._validate_frozen_specs()
    observed = base._digest(dict(CANDIDATE_SPEC))
    if observed != EXPECTED_CANDIDATE_SPEC_SHA256:
        raise RuntimeError(f"dispersion candidate spec changed: {observed}")
    _feature_indices(DISPERSION_FEATURES)


def validate_archived_parent_artifact(root: Path, *, verify_frozen_hashes: bool) -> dict:
    root = Path(root).resolve()
    observed = {path.name for path in root.iterdir() if path.is_file()}
    if observed != set(ARCHIVED_PARENT_SHA256):
        raise ValueError("archived Attempt-4 artifact file set differs")
    hashes = {name: base._sha256(root / name) for name in sorted(observed)}
    if verify_frozen_hashes and hashes != dict(ARCHIVED_PARENT_SHA256):
        raise ValueError("archived Attempt-4 artifact hash changed")
    manifest = base._strict_json(root / "manifest.json")
    if (not isinstance(manifest, dict)
            or manifest.get("schema") != "nfl_market_all_prior_decay_composite_path_train_manifest_v1"
            or manifest.get("complete") is not True
            or manifest.get("status") != "COMPLETE"
            or manifest.get("model_fits") != 4
            or manifest.get("control_refits") != 0
            or manifest.get("provider_cost_usd") != "0"
            or manifest.get("route_dev_opened") is not False
            or manifest.get("sealed_final_opened") is not False
            or manifest.get("external_fetch") is not False
            or manifest.get("paid_provider") is not False):
        raise ValueError("archived Attempt-4 manifest boundary failed")
    bindings = {
        "pre_score_lock.json": manifest.get("pre_score_lock_sha256"),
        "input_receipts.json": manifest.get("input_receipts_sha256"),
        "exclusions.json": manifest.get("exclusions_sha256"),
        "staleness_inventory.json": manifest.get("staleness_inventory_sha256"),
        "predictions.csv": manifest.get("predictions_sha256"),
        "scorecard.json": manifest.get("scorecard_sha256"),
    }
    if any(hashes[name] != value for name, value in bindings.items()):
        raise ValueError("archived Attempt-4 manifest hash binding failed")
    return {"artifact_root": str(root), "artifact_hashes": hashes}


def _feature_indices(names: Sequence[str]) -> tuple[int, ...]:
    indices = []
    for name in names:
        matches = [index for index, observed in enumerate(base.FEATURE_NAMES)
                   if observed == name]
        if len(matches) != 1:
            raise RuntimeError(f"frozen feature name missing or duplicated: {name}")
        indices.append(matches[0])
    return tuple(indices)


def dispersion_raw(rows: Sequence[base.DiagnosticRow]) -> np.ndarray:
    if not rows:
        return np.asarray([], dtype=np.float64)
    matrix = np.asarray([row.features for row in rows], dtype=np.float64)
    if (matrix.shape != (len(rows), len(base.FEATURE_NAMES))
            or not np.all(np.isfinite(matrix))):
        recent._invalid_recent("dispersion_feature_matrix_shape_or_nonfinite")
    values = np.mean(matrix[:, _feature_indices(DISPERSION_FEATURES)], axis=1)
    if not np.all(np.isfinite(values)):
        recent._invalid_recent("nonfinite_raw_dispersion")
    return values


def fit_dispersion_transform(
        transformed: dict, selected: Sequence[base.DiagnosticRow],
        older: Sequence[base.DiagnosticRow],
        check: Sequence[base.DiagnosticRow]) -> dict:
    params = dict(transformed["parameters"])
    market_mean = float(params["market_scaler_mean"])
    market_scale = float(params["market_scaler_scale"])
    z_market = {
        name: (transformed[name]["logits"] - market_mean) / market_scale
        for name in ("selected", "older", "check")
    }
    rows = {"selected": selected, "older": older, "check": check}
    raw = {name: dispersion_raw(group_rows) for name, group_rows in rows.items()}
    design_fit = np.column_stack((
        np.ones(len(selected)), z_market["selected"],
        transformed["selected"]["z_composite"],
    ))
    gamma, _, rank, singular = np.linalg.lstsq(
        design_fit, raw["selected"], rcond=1e-12
    )
    if int(rank) != 3:
        recent._invalid_recent(
            "dispersion_residualization_rank_failure", observed_rank=int(rank),
            required_rank=3, singular_values=[float(value) for value in singular],
        )
    residual = {}
    for name in ("selected", "older", "check"):
        design = np.column_stack((
            np.ones(len(rows[name])), z_market[name],
            transformed[name]["z_composite"],
        ))
        residual[name] = raw[name] - design @ gamma
    mean = float(np.mean(residual["selected"]))
    scale = float(np.std(residual["selected"], ddof=0))
    inactive = bool(scale <= INACTIVE_STD_THRESHOLD)
    if (not math.isfinite(mean) or not math.isfinite(scale)
            or any(not np.all(np.isfinite(value)) for value in (*raw.values(), *residual.values()))):
        recent._invalid_recent("nonfinite_dispersion_transform")
    for name in ("selected", "older", "check"):
        transformed[name]["dispersion_raw"] = raw[name]
        transformed[name]["dispersion_residual"] = residual[name]
        transformed[name]["z_dispersion"] = (
            np.zeros_like(residual[name]) if inactive
            else (residual[name] - mean) / scale
        )
    params.update({
        "dispersion_feature_names": DISPERSION_FEATURES,
        "dispersion_formula": "mean(weighted_std_15m,weighted_std_60m,weighted_std_240m)",
        "dispersion_lstsq_rcond": 1e-12,
        "dispersion_rank": int(rank),
        "dispersion_singular_values": [float(value) for value in singular],
        "dispersion_gamma_intercept_market_composite": [float(value) for value in gamma],
        "dispersion_residual_fit_mean": mean,
        "dispersion_residual_fit_population_std": scale,
        "dispersion_inactive": inactive,
        "dispersion_inactive_threshold_inclusive": INACTIVE_STD_THRESHOLD,
        "dispersion_selected_fit_orthogonality": {
            "absolute_residual_mean": abs(float(np.mean(residual["selected"]))),
            "absolute_mean_z_market_times_residual": abs(float(np.mean(
                z_market["selected"] * residual["selected"]
            ))),
            "absolute_mean_z_composite_times_residual": abs(float(np.mean(
                transformed["selected"]["z_composite"] * residual["selected"]
            ))),
        },
    })
    transformed["parameters"] = params
    return transformed


def weighted_objective_gradient(
        parameter: object, design: object, outcomes: object,
        market_logits: object, weights: object) -> tuple[float, np.ndarray]:
    coefficients = np.asarray(parameter, dtype=np.float64)
    matrix = np.asarray(design, dtype=np.float64)
    labels = np.asarray(outcomes, dtype=np.float64)
    logits = np.asarray(market_logits, dtype=np.float64)
    event_weights = np.asarray(weights, dtype=np.float64)
    if coefficients.shape != (2,) or not np.all(np.isfinite(coefficients)):
        raise ValueError("coefficients must be two finite values")
    if (matrix.ndim != 2 or matrix.shape[1] != 2 or not len(matrix)
            or labels.shape != (len(matrix),) or logits.shape != labels.shape
            or event_weights.shape != labels.shape
            or not np.all(np.isfinite(matrix)) or not np.all(np.isfinite(labels))
            or not np.all(np.isfinite(logits)) or not np.all(np.isfinite(event_weights))
            or not np.all(np.isin(labels, (0, 1))) or np.any(event_weights <= 0)):
        raise ValueError("weighted dispersion objective inputs must align and be finite")
    eta = logits + matrix @ coefficients
    probabilities = incumbent.expit(eta)
    weight_sum = float(np.sum(event_weights))
    losses = np.logaddexp(0.0, eta) - labels * eta
    objective = float(np.sum(event_weights * losses) / weight_sum)
    objective += 0.5 * float(coefficients @ coefficients)
    gradient = (
        matrix.T @ (event_weights * (probabilities - labels)) / weight_sum
        + coefficients
    )
    if not math.isfinite(objective) or not np.all(np.isfinite(gradient)):
        raise FloatingPointError("weighted dispersion objective or gradient is nonfinite")
    return objective, np.asarray(gradient, dtype=np.float64)


def fit_weighted_dispersion(
        design: object, outcomes: object, market_logits: object,
        weights: object) -> tuple[np.ndarray, dict]:
    matrix = np.asarray(design, dtype=np.float64)
    labels = np.asarray(outcomes, dtype=np.float64)
    logits = np.asarray(market_logits, dtype=np.float64)
    event_weights = np.asarray(weights, dtype=np.float64)

    def objective(value: np.ndarray) -> tuple[float, np.ndarray]:
        return weighted_objective_gradient(
            value, matrix, labels, logits, event_weights
        )

    result = incumbent.minimize(
        objective, np.zeros(2, dtype=np.float64), method="L-BFGS-B", jac=True,
        options={"maxiter": 1000, "gtol": 1e-8, "ftol": 1e-12},
    )
    parameter = np.asarray(result.x, dtype=np.float64)
    final_objective, final_gradient = objective(parameter)
    grad_inf = float(np.max(np.abs(final_gradient)))
    if (not bool(result.success) or not math.isfinite(final_objective)
            or not np.all(np.isfinite(parameter)) or grad_inf > 1e-6):
        raise RuntimeError(
            "weighted dispersion optimizer failed frozen convergence checks: "
            f"success={result.success}, objective={final_objective}, grad_inf={grad_inf}"
        )
    return parameter, {
        "success": True, "status": int(result.status),
        "message": str(result.message)[:300], "iterations": int(result.nit),
        "function_evaluations": int(result.nfev), "objective": final_objective,
        "gradient_infinity_norm": grad_inf,
        "parameters": [float(value) for value in parameter],
    }


def dispersion_probabilities(
        parameter: object, design: object, market_logits: object,
        market_probabilities: object) -> np.ndarray:
    coefficients = np.asarray(parameter, dtype=np.float64)
    matrix = np.asarray(design, dtype=np.float64)
    logits = np.asarray(market_logits, dtype=np.float64)
    market = np.asarray(market_probabilities, dtype=np.float64)
    if (coefficients.shape != (2,) or matrix.shape != (len(market), 2)
            or logits.shape != market.shape):
        raise ValueError("dispersion prediction inputs have wrong shape")
    if (not np.all(np.isfinite(coefficients)) or not np.all(np.isfinite(matrix))
            or not np.all(np.isfinite(logits)) or not np.all(np.isfinite(market))
            or np.any(market <= 0) or np.any(market >= 1)):
        raise ValueError("dispersion prediction inputs are nonfinite or invalid")
    expected_logits = np.log(market / (1.0 - market))
    if not np.allclose(logits, expected_logits, rtol=0.0, atol=1e-12):
        raise ValueError("market probabilities and logits differ")
    epsilon = float(base.DEFAULT_PROBABILITY_POLICY.epsilon)
    if np.any(market < epsilon) or np.any(market > 1.0 - epsilon):
        raise ValueError("market probabilities violate frozen epsilon policy")
    if np.array_equal(coefficients, np.zeros(2, dtype=np.float64)):
        return market.copy()
    values = incumbent.expit(logits + matrix @ coefficients)
    if values.shape != market.shape or not np.all(np.isfinite(values)):
        raise FloatingPointError("dispersion probabilities are invalid")
    if np.any(values < epsilon) or np.any(values > 1.0 - epsilon):
        raise ValueError("dispersion probabilities violate frozen epsilon policy")
    return values


def dispersion_diagnostics(group: Mapping[str, np.ndarray],
                           rows: Sequence[base.DiagnosticRow]) -> dict:
    if not rows:
        return {
            "events": 0,
            "raw_population_variance": None,
            "residual_population_variance": None,
            "residual_variance_fraction": None,
            "raw_market_logit_pearson": prior._correlation(
                np.asarray([]), np.asarray([])
            ),
            "raw_market_logit_spearman": prior._correlation(
                np.asarray([]), np.asarray([]), rank=True
            ),
            "raw_composite_pearson": prior._correlation(
                np.asarray([]), np.asarray([])
            ),
            "raw_composite_spearman": prior._correlation(
                np.asarray([]), np.asarray([]), rank=True
            ),
            "residual_market_logit_pearson": prior._correlation(
                np.asarray([]), np.asarray([])
            ),
            "residual_market_logit_spearman": prior._correlation(
                np.asarray([]), np.asarray([]), rank=True
            ),
            "residual_composite_pearson": prior._correlation(
                np.asarray([]), np.asarray([])
            ),
            "residual_composite_spearman": prior._correlation(
                np.asarray([]), np.asarray([]), rank=True
            ),
            "mean_z_times_y_minus_market": None,
        }
    outcomes = np.asarray([row.trusted["outcome"] for row in rows], dtype=np.float64)
    market = np.asarray([row.trusted["market_probability"] for row in rows], dtype=np.float64)
    raw = np.asarray(group["dispersion_raw"], dtype=np.float64)
    residual = np.asarray(group["dispersion_residual"], dtype=np.float64)
    standardized = np.asarray(group["z_dispersion"], dtype=np.float64)
    return {
        "events": len(rows),
        "raw_population_variance": float(np.var(raw)),
        "residual_population_variance": float(np.var(residual)),
        "residual_variance_fraction": (
            None if float(np.var(raw)) == 0.0
            else float(np.var(residual) / np.var(raw))
        ),
        "raw_market_logit_pearson": prior._correlation(raw, group["logits"]),
        "raw_market_logit_spearman": prior._correlation(raw, group["logits"], rank=True),
        "raw_composite_pearson": prior._correlation(raw, group["z_composite"]),
        "raw_composite_spearman": prior._correlation(raw, group["z_composite"], rank=True),
        "residual_market_logit_pearson": prior._correlation(residual, group["logits"]),
        "residual_market_logit_spearman": prior._correlation(
            residual, group["logits"], rank=True
        ),
        "residual_composite_pearson": prior._correlation(residual, group["z_composite"]),
        "residual_composite_spearman": prior._correlation(
            residual, group["z_composite"], rank=True
        ),
        "mean_z_times_y_minus_market": float(np.mean(
            standardized * (outcomes - market)
        )) if len(rows) else None,
    }


def _fit_and_predict(
        plan: Sequence[dict], *, minimum_recent_rows: int,
        enforce_real_counts: bool,
        phase_state: dict[str, bool]) -> tuple[list[dict], list[dict]]:
    predictions: list[dict] = []
    reports: list[dict] = []
    for fold in plan:
        expected_recent = EXPECTED_REAL_RECENT[fold["fold"]] if enforce_real_counts else None
        selection = recent.select_recent_candidate_rows(
            fold["fit_rows"], fold["check_rows"], minimum_rows=minimum_recent_rows,
            expected=expected_recent,
        )
        selected = selection["selected_rows"]
        older = selection["older_rows"]
        transformed = recent.fit_recent_composite_transform(
            selected, older, fold["check_rows"]
        )
        transformed = fit_dispersion_transform(
            transformed, selected, older, fold["check_rows"]
        )
        expected_sum = (
            incumbent.EXPECTED_REAL_WEIGHT_SUMS[fold["fold"]]
            if enforce_real_counts else None
        )
        weights, weight_report = incumbent.recency_weights(
            selected, selection["report"]["selected_week_labels"],
            expected_total=expected_sum,
        )
        labels = np.asarray([row.trusted["outcome"] for row in selected], dtype=np.float64)
        market = np.asarray(
            [row.trusted["market_probability"] for row in selected], dtype=np.float64
        )
        design = np.column_stack((
            transformed["selected"]["z_composite"],
            transformed["selected"]["z_dispersion"],
        ))
        logits = transformed["selected"]["logits"]
        residual_products = design * (labels - market)[:, None]
        weighted_moments = np.sum(
            weights[:, None] * residual_products, axis=0
        ) / np.sum(weights)
        gradient_at_zero = float(weighted_objective_gradient(
            np.zeros(2), design, labels, logits, weights
        )[1][1])
        if not np.allclose(
                weighted_objective_gradient(
                    np.zeros(2), design, labels, logits, weights
                )[1], -weighted_moments, rtol=0.0, atol=1e-15):
            raise RuntimeError("gradient at zero is not negative weighted moments")
        weight_report.update({
            "weighted_mean_design_times_y_minus_market": [
                float(value) for value in weighted_moments
            ],
            "unweighted_mean_design_times_y_minus_market": [
                float(value) for value in np.mean(residual_products, axis=0)
            ],
            "dispersion_gradient_at_zero": gradient_at_zero,
            "gradient_at_zero_equals_negative_weighted_moments": True,
            "dispersion_signed_moments_by_week": [],
        })
        row_weeks = [offset.game_week(row.game_id) for row in selected]
        for week in weight_report["week_weight_mapping"]:
            mask = np.asarray([label == week for label in row_weeks], dtype=bool)
            products = residual_products[mask, 1]
            week_weights = weights[mask]
            weight_report["dispersion_signed_moments_by_week"].append({
                "week": week,
                "events": int(np.sum(mask)),
                "unweighted_mean_z_dispersion_times_y_minus_market": float(np.mean(products)),
                "weighted_mean_z_dispersion_times_y_minus_market": float(
                    np.sum(week_weights * products) / np.sum(week_weights)
                ),
            })
        phase_state["fit_started"] = True
        parameter, optimizer = fit_weighted_dispersion(
            design, labels, logits, weights
        )
        check_design = np.column_stack((
            transformed["check"]["z_composite"],
            transformed["check"]["z_dispersion"],
        ))
        candidate_values = dispersion_probabilities(
            parameter, check_design,
            transformed["check"]["logits"],
            [row.trusted["market_probability"] for row in fold["check_rows"]],
        )
        candidate_records = base._prediction_records(
            list(fold["check_rows"]), candidate_values
        )
        outcomes = [row.trusted["outcome"] for row in fold["check_rows"]]
        market_values = [row.trusted["market_probability"] for row in fold["check_rows"]]
        market_metrics = base._simple_metrics(outcomes, market_values)
        candidate_metrics = base._simple_metrics(
            outcomes, [item["probability"] for item in candidate_records]
        )
        reports.append({
            "fold": fold["fold"], "fit_dates": fold["fit_dates"],
            "check_dates": fold["check_dates"],
            "expanding_fit_events": len(fold["fit_rows"]),
            "check_events": len(fold["check_rows"]),
            "fit_label_unavailable_events": fold["fit_label_unavailable_events"],
            "recent_selection": selection["report"],
            "breadth": {
                "selected_recent_candidate_fit": recent._breadth(selected),
                "older_eligible_fit": recent._breadth(older),
                "ineligible_same_or_later_week_fit": recent._breadth(
                    selection["ineligible_same_or_later_week_rows"]
                ),
                "check": recent._breadth(fold["check_rows"]),
            },
            "transform_parameters": transformed["parameters"],
            "selected_recent_fit_information": recent.information_diagnostics(
                transformed["selected"], selected
            ),
            "older_fit_information": recent.information_diagnostics(
                transformed["older"], older
            ),
            "check_information": recent.information_diagnostics(
                transformed["check"], fold["check_rows"]
            ),
            "dispersion_information": {
                "selected": dispersion_diagnostics(transformed["selected"], selected),
                "older": dispersion_diagnostics(transformed["older"], older),
                "check": dispersion_diagnostics(
                    transformed["check"], fold["check_rows"]
                ),
            },
            "recency_weighting": weight_report,
            "market": market_metrics, "candidate": candidate_metrics,
            "candidate_minus_market_brier": candidate_metrics["brier"] - market_metrics["brier"],
            "candidate_minus_market_log_loss": candidate_metrics["log_loss"] - market_metrics["log_loss"],
            "optimizer": optimizer,
            "w_composite": float(parameter[0]),
            "w_dispersion": float(parameter[1]),
            "candidate_probability_correction": {
                "minimum": float(np.min(candidate_values - np.asarray(market_values))),
                "mean": float(np.mean(candidate_values - np.asarray(market_values))),
                "maximum": float(np.max(candidate_values - np.asarray(market_values))),
            },
        })
        for row, record in zip(fold["check_rows"], candidate_records, strict=True):
            predictions.append({"fold": fold["fold"], "row": row, "candidate": record})
    keys = [item["row"].key for item in predictions]
    if len(keys) != len(set(keys)):
        raise ValueError("an event appears in multiple check folds")
    return predictions, reports


def bind_archived_controls(
        predictions: Sequence[dict], fold_reports: Sequence[dict],
        predictions_csv: Path, *, verify_frozen_hash: bool) -> dict:
    if (verify_frozen_hash and base._sha256(predictions_csv)
            != ARCHIVED_PARENT_SHA256["predictions.csv"]):
        raise ValueError("archived Attempt-4 predictions hash changed")
    with Path(predictions_csv).open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != ARCHIVED_FIELDS:
            raise ValueError("archived Attempt-4 prediction schema changed")
        archived = list(reader)
    if len(archived) != len(predictions):
        raise ValueError("archived Attempt-4 row count differs")
    arm_columns = {
        "ordinary": "ordinary_probability",
        "market_only_calibration": "market_only_calibration_probability",
        "archived_full_offset": "archived_full_offset_probability",
        "archived_attempt1": "candidate_probability",
        "archived_attempt2": "recent_composite_candidate_probability",
        "archived_attempt3": "recency_weighted_candidate_probability",
        "archived_attempt4": "all_prior_decay_candidate_probability",
    }
    for item, control in zip(predictions, archived, strict=True):
        row = item["row"]
        identity = (
            str(item["fold"]), row.game_id, row.split_date,
            offset.game_week(row.game_id), row.trusted["event_id"],
            row.trusted["market_id"], str(row.trusted["cutoff_ms"]),
            str(row.trusted["outcome_available_ms"]), str(row.trusted["outcome"]),
        )
        if identity != tuple(control[name] for name in ARCHIVED_FIELDS[:9]):
            raise ValueError("archived Attempt-4 identity/order/outcome differs")
        if row.trusted["market_probability"] != float(control["market_probability"]):
            raise ValueError("archived Attempt-4 market probability differs")
        for arm, column in arm_columns.items():
            item[arm] = base._prediction_records([row], [float(control[column])])[0]
    for report in fold_reports:
        items = [item for item in predictions if item["fold"] == report["fold"]]
        outcomes = [item["row"].trusted["outcome"] for item in items]
        for arm in arm_columns:
            metrics = base._simple_metrics(
                outcomes, [item[arm]["probability"] for item in items]
            )
            report[arm] = metrics
            report[f"candidate_minus_{arm}_brier"] = report["candidate"]["brier"] - metrics["brier"]
            report[f"candidate_minus_{arm}_log_loss"] = report["candidate"]["log_loss"] - metrics["log_loss"]
    return {
        "archived_predictions_sha256": base._sha256(predictions_csv),
        "rows": len(predictions), "identity_order_outcomes_exact": True,
        "market_probability_exact": True, "control_refits": 0,
        "control_probability_source": "immutable archived Attempt-4 predictions",
    }


CONTROL_NAMES = (
    "ordinary", "market_only_calibration", "archived_full_offset",
    "archived_attempt1", "archived_attempt2", "archived_attempt3",
    "archived_attempt4",
)


def corrected_grouped_inference(predictions: Sequence[dict]) -> dict:
    outcomes = [item["row"].trusted["outcome"] for item in predictions]
    arms = {
        "market": [item["row"].trusted["market_probability"] for item in predictions],
        **{name: [item[name]["probability"] for item in predictions]
           for name in (*CONTROL_NAMES, "candidate")},
    }
    comparisons = {
        f"candidate_minus_{right}": ("candidate", right)
        for right in ("market", *CONTROL_NAMES)
    }
    groups = {
        "schedule_day": [item["row"].split_date for item in predictions],
        "observed_game_week": [offset.game_week(item["row"].game_id) for item in predictions],
    }
    result = {
        "primary_estimand": "equal-event Brier and log loss",
        "events": len(predictions), "schedule_dates": len(set(groups["schedule_day"])),
        "game_weeks": len(set(groups["observed_game_week"])),
        "schedule_day_resample": {}, "observed_game_week_cluster_sensitivity": {},
    }
    for group, labels in groups.items():
        target = (result["schedule_day_resample"] if group == "schedule_day"
                  else result["observed_game_week_cluster_sensitivity"])
        for name, (left, right) in comparisons.items():
            target[name] = {
                loss: calibration._group_delta_detail(
                    offset._loss_deltas(outcomes, arms[left], arms[right], loss), labels
                ) for loss in ("brier", "log_loss")
            }
    result["schedule_day_resample"]["unit_definition"] = (
        "complete source schedule dates; resample units then recompute pooled equal-event mean"
    )
    weeks = sorted(set(groups["observed_game_week"]))
    result["observed_game_week_cluster_sensitivity"].update({
        "unit_definition": "observed NFL game-week clusters; not all are complete weeks",
        "right_edge_partial_week": weeks[-1],
        "right_edge_partial_week_events": groups["observed_game_week"].count(weeks[-1]),
        "primary_denominator_changed": False,
    })
    return result


def _write_predictions(path: Path, predictions: Sequence[dict]) -> None:
    fields = (*ARCHIVED_FIELDS, "recency_weighted_composite_dispersion_candidate_probability")
    temporary = path.with_suffix(".csv.tmp")
    with temporary.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for item in predictions:
            row = item["row"]
            writer.writerow({
                "fold": item["fold"], "game_id": row.game_id,
                "split_date": row.split_date, "game_week": offset.game_week(row.game_id),
                "event_id": row.trusted["event_id"], "market_id": row.trusted["market_id"],
                "cutoff_ms": row.trusted["cutoff_ms"],
                "outcome_available_ms": row.trusted["outcome_available_ms"],
                "outcome": row.trusted["outcome"],
                "market_probability": row.trusted["market_probability"],
                "ordinary_probability": item["ordinary"]["probability"],
                "market_only_calibration_probability": item["market_only_calibration"]["probability"],
                "archived_full_offset_probability": item["archived_full_offset"]["probability"],
                "candidate_probability": item["archived_attempt1"]["probability"],
                "recent_composite_candidate_probability": item["archived_attempt2"]["probability"],
                "recency_weighted_candidate_probability": item["archived_attempt3"]["probability"],
                "all_prior_decay_candidate_probability": item["archived_attempt4"]["probability"],
                "recency_weighted_composite_dispersion_candidate_probability": item["candidate"]["probability"],
            })
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def diagnostic_keep(aggregate: Mapping[str, dict], fold_reports: Sequence[dict]
                    ) -> tuple[str, dict]:
    prior_decision, prior_conditions = offset.diagnostic_keep(
        aggregate["candidate"], aggregate["market"], aggregate["ordinary"],
        [fold["market"]["brier"] - fold["candidate"]["brier"] > STRICT_WIN_TOLERANCE
         for fold in fold_reports],
        [fold["ordinary"]["brier"] - fold["candidate"]["brier"] > STRICT_WIN_TOLERANCE
         for fold in fold_reports],
    )
    incumbent_conditions = {
        "beats_attempt3_aggregate_brier": (
            aggregate["archived_attempt3"]["brier"] - aggregate["candidate"]["brier"]
            > STRICT_WIN_TOLERANCE
        ),
        "beats_attempt3_aggregate_log_loss": (
            aggregate["archived_attempt3"]["log_loss"] - aggregate["candidate"]["log_loss"]
            > STRICT_WIN_TOLERANCE
        ),
        "attempt3_fold_brier_wins_at_least_3_of_4": sum(
            fold["archived_attempt3"]["brier"] - fold["candidate"]["brier"]
            > STRICT_WIN_TOLERANCE for fold in fold_reports
        ) >= 3,
    }
    conditions = {**prior_conditions, **incumbent_conditions}
    decision = (
        "KEEP" if prior_decision == "KEEP" and all(incumbent_conditions.values())
        else "REVERT"
    )
    return decision, conditions


def run(
        source_root: Path, output: Path, *, expected_events: int = EXPECTED_EVENTS,
        expected_dates: int = EXPECTED_DATES, allow_test_paths: bool = False,
        generated_utc: str | None = None, archived_parent_root: Path | None = None,
        minimum_recent_rows: int = MINIMUM_RECENT_ROWS) -> dict:
    source_root, output = Path(source_root).resolve(), Path(output).resolve()
    base._validate_roots(source_root, output, allow_test_paths=allow_test_paths)
    output.mkdir(parents=True, exist_ok=False)
    phase_state = {"fit_started": False}
    scoring_started = False
    try:
        if not allow_test_paths and minimum_recent_rows != MINIMUM_RECENT_ROWS:
            raise ValueError("production minimum recent rows is frozen at 30")
        _validate_frozen_specs()
        identity = _validate_execution_identity()
        archive_root = Path(archived_parent_root or ARCHIVED_PARENT_ROOT).resolve()
        archive_binding = validate_archived_parent_artifact(
            archive_root, verify_frozen_hashes=not allow_test_paths
        )
        if not allow_test_paths:
            if base._sha256(source_root / "manifest.json") != base.EXPECTED_MANIFEST_SHA256:
                raise ValueError("frozen source manifest hash changed")
            if base._sha256(source_root / "cohort.csv") != base.EXPECTED_COHORT_SHA256:
                raise ValueError("frozen cohort hash changed")
        source_manifest = base._strict_json(source_root / "manifest.json")
        if (not isinstance(source_manifest, dict)
                or source_manifest.get("schema") != "nfl_2025_train_fresh_source_audit_v1"
                or source_manifest.get("complete") is not True
                or source_manifest.get("source_games") != expected_events
                or source_manifest.get("train_distinct_dates") != expected_dates
                or source_manifest.get("dev_final_opened") is not False
                or source_manifest.get("model_fits") != 0
                or source_manifest.get("provider_cost_usd") != "0"):
            raise ValueError("source manifest scope/completeness boundary failed")
        cohort = base._read_cohort(source_root / "cohort.csv")
        if len(cohort) != expected_events:
            raise ValueError("source denominator differs from frozen event count")
        if set((source_root / "catalog").glob("*.json")) != {
                source_root / "catalog" / f"{row['game_id']}.json" for row in cohort}:
            raise ValueError("normalized catalog population differs from cohort")
        source_file_receipts = [{
            "source_ordinal": ordinal, "game_id": item["game_id"],
            "catalog_meta_sha256": base._sha256(source_root / "catalog" / f"{item['game_id']}.json"),
            "catalog_stored_sha256": base._sha256(source_root / "catalog" / f"{item['game_id']}.raw.json.gz"),
            "trade_manifest_sha256": base._sha256(source_root / "trades" / item["game_id"] / "manifest.json"),
            "trade_window_sha256": base._sha256(source_root / "trades" / item["game_id"] / "trade_window.csv"),
        } for ordinal, item in enumerate(cohort)]
        materialized, exclusions = [], []
        for ordinal, item in enumerate(cohort):
            try:
                materialized.append(base._materialize_event(source_root, item))
            except base.EventExclusion as error:
                exclusions.append({
                    "source_ordinal": ordinal, "game_id": item["game_id"],
                    "game_date": item["game_date"], "reason": error.code,
                    "detail": str(error)[:400],
                })
        if len(materialized) + len(exclusions) != expected_events:
            raise RuntimeError("materialized plus excluded events do not reconcile")
        if not allow_test_paths:
            base.validate_exact_cohort_attrition(expected_events, len(materialized), exclusions)
            offset.validate_exact_real_exclusion(exclusions)
        materialized.sort(key=lambda row: row.key)
        materialized_hash = base._digest([list(row.key) for row in materialized])
        if not allow_test_paths and materialized_hash != EXPECTED_MATERIALIZED_KEY_SHA256:
            raise ValueError("materialized key population differs from frozen parent")
        ordinals = {item["game_id"]: ordinal for ordinal, item in enumerate(cohort)}
        staleness = offset.staleness_inventory(materialized, ordinals)
        base._atomic_json(output / "staleness_inventory.json", staleness)
        offset.require_staleness_gate(
            staleness, expected_binary_rows=194 if not allow_test_paths else len(materialized)
        )
        folds = base.chronological_date_folds(
            [item["game_date"] for item in cohort], expected_dates=expected_dates
        )
        plan = calibration._fold_plan(materialized, folds)
        if not allow_test_paths:
            counts = tuple((len(item["fit_rows"]), len(item["check_rows"])) for item in plan)
            if counts != prior.EXPECTED_REAL_FOLD_COUNTS:
                raise ValueError("fit/check event counts differ from frozen parent")
            if any(item["fit_label_unavailable_events"] for item in plan):
                raise ValueError("frozen parent expects zero unavailable fit labels")
            offset.require_expected_check_mask(
                [row for item in plan for row in item["check_rows"]],
                EXPECTED_CHECK_MASK_SHA256,
            )
        inputs = {
            "schema": "nfl_market_recency_weighted_composite_dispersion_train_inputs_v1",
            "source_dataset_id": source_root.name,
            "source_manifest_sha256": base._sha256(source_root / "manifest.json"),
            "cohort_sha256": base._sha256(source_root / "cohort.csv"),
            "source_events": expected_events, "source_dates": expected_dates,
            "runner_source_sha256": base._sha256(Path(__file__)),
            "execution_identity": identity, "archived_parent_binding": archive_binding,
            "all_source_file_receipts": source_file_receipts,
            "materialized_event_receipts": [row.source_receipt for row in materialized],
            "route_dev_opened": False, "sealed_final_opened": False,
            "provider_cost_usd": "0",
        }
        exclusions_doc = {
            "schema": "nfl_market_recency_weighted_composite_dispersion_train_exclusions_v1",
            "source_events": expected_events, "materialized_events": len(materialized),
            "excluded_events": len(exclusions),
            "reconciles_to_source_denominator": len(materialized) + len(exclusions) == expected_events,
            "exclusions": exclusions,
        }
        base._atomic_json(output / "input_receipts.json", inputs)
        base._atomic_json(output / "exclusions.json", exclusions_doc)
        lock = {
            "schema": "nfl_market_recency_weighted_composite_dispersion_train_pre_score_lock_v1",
            "generated_utc": generated_utc or datetime.now(timezone.utc).isoformat(),
            "problem": "test incremental recent probability dispersion beyond the frozen path composite",
            "domain": "2025 NFL two-outcome moneyline opened Train Discovery",
            "source_manifest_sha256": inputs["source_manifest_sha256"],
            "cohort_sha256": inputs["cohort_sha256"],
            "input_receipts_sha256": base._sha256(output / "input_receipts.json"),
            "exclusions_sha256": base._sha256(output / "exclusions.json"),
            "staleness_inventory_sha256": base._sha256(output / "staleness_inventory.json"),
            "controller_provenance": {
                "proposal_path": str(CONTROLLER_PROPOSAL_PATH),
                "proposal_sha256": EXPECTED_CONTROLLER_PROPOSAL_SHA256,
                "adaptive_discovery_disclosure": (
                    "Attempt 5 was selected after reading label-dependent Attempt-4 aggregate, "
                    "fold, date, week, coefficient and information diagnostics; this is repeatedly "
                    "inspected Train Discovery"
                ),
            },
            "execution_identity": identity, "archived_parent_binding": archive_binding,
            "source_events": expected_events, "source_dates": expected_dates,
            "materialized_key_sha256": materialized_hash,
            "canonical_check_mask_sha256": EXPECTED_CHECK_MASK_SHA256 if not allow_test_paths else None,
            "decision_cutoff": "event_start_utc minus 15 minutes",
            "max_staleness_seconds": MAX_STALENESS_SECONDS,
            "folds": folds, "candidate_spec": dict(CANDIDATE_SPEC),
            "candidate_spec_sha256": base._digest(dict(CANDIDATE_SPEC)),
            "expected_real_recent_candidate_cohorts": {
                str(key): dict(value) for key, value in EXPECTED_REAL_RECENT.items()
            },
            "expected_real_weight_sums": {
                str(key): value for key, value in incumbent.EXPECTED_REAL_WEIGHT_SUMS.items()
            },
            "dispersion_feature_names": DISPERSION_FEATURES,
            "dispersion_formula": "mean(weighted_std_15m,weighted_std_60m,weighted_std_240m)",
            "model_fits": {"candidate": 4, "all_archived_controls": 0},
            "archive_only_controls": [
                "market", "ordinary_reference", "market_only_calibration", "full_offset",
                "MarketOrthogonalPricePath-v1", "MarketRecentCompositePath-v2",
                "MarketRecencyWeightedCompositePath-v3",
                "MarketAllPriorDecayCompositePath-v4",
            ],
            "event_weighting": "evaluation equal-event; trainer exact Attempt-3 0.25/0.50/1.00 recent-week event weights",
            "grouped_inference": {
                "seed": offset.BOOTSTRAP_SEED,
                "replicates": offset.BOOTSTRAP_REPLICATES,
                "per_draw_estimand": "pooled equal-event mean loss delta",
            },
            "keep_rule": (
                "all prior market/ordinary gates plus beats archived Attempt3 aggregate Brier/log "
                "by >1e-12 and Brier in >=3/4 folds"
            ),
            "route_dev_opened": False, "sealed_final_opened": False,
            "external_fetch": False, "paid_provider": False,
            "provider_cost_usd": "0", "promotion_authorized": False,
        }
        base._atomic_json(output / "pre_score_lock.json", lock)
        predictions, fold_reports = _fit_and_predict(
            plan, minimum_recent_rows=minimum_recent_rows,
            enforce_real_counts=not allow_test_paths, phase_state=phase_state,
        )
        parity = bind_archived_controls(
            predictions, fold_reports, archive_root / "predictions.csv",
            verify_frozen_hash=not allow_test_paths,
        )
        check_rows = [item["row"] for item in predictions]
        if not allow_test_paths:
            offset.require_expected_check_mask(check_rows, EXPECTED_CHECK_MASK_SHA256)
        records = {
            name: [item[name] for item in predictions]
            for name in (*CONTROL_NAMES, "candidate")
        }
        scoring_started = True
        pairwise = {}
        for right in ("market", *CONTROL_NAMES):
            pairwise[f"candidate_minus_{right}"] = recent._pair_score(
                check_rows, records["candidate"], "candidate", right,
                right=None if right == "market" else records[right],
            )
        for arm in CONTROL_NAMES:
            pairwise[f"{arm}_minus_market"] = recent._pair_score(
                check_rows, records[arm], arm, "market"
            )
        masks = {
            name: value["proper_scorer_output"]["coverage"]["complete_mask_sha256"]
            for name, value in pairwise.items()
        }
        if len(set(masks.values())) != 1:
            raise RuntimeError("pairwise proper scorers did not receive one common mask")

        def arm_from(pair: str, prefix: str) -> dict:
            score = pairwise[pair]["proper_scorer_output"]
            return {
                "brier": score["primary"][f"equal_event_{prefix}_brier"],
                "log_loss": score["primary"][f"equal_event_{prefix}_log_loss"],
                "calibration": score["calibration"][prefix],
            }

        aggregate = {
            "market": arm_from("candidate_minus_market", "market"),
            "candidate": arm_from("candidate_minus_market", "candidate"),
            **{arm: arm_from(f"{arm}_minus_market", "candidate") for arm in CONTROL_NAMES},
            "pairwise_deltas": {
                name: value["equal_event_delta"] for name, value in pairwise.items()
            },
        }
        decision, conditions = diagnostic_keep(aggregate, fold_reports)
        branch_diagnostics = {}
        for arm in CONTROL_NAMES[1:]:
            branch_diagnostics[f"candidate_vs_{arm}"] = {
                "beats_aggregate_brier": aggregate[arm]["brier"] - aggregate["candidate"]["brier"] > STRICT_WIN_TOLERANCE,
                "beats_aggregate_log_loss": aggregate[arm]["log_loss"] - aggregate["candidate"]["log_loss"] > STRICT_WIN_TOLERANCE,
                "fold_brier_wins": [
                    fold[arm]["brier"] - fold["candidate"]["brier"] > STRICT_WIN_TOLERANCE
                    for fold in fold_reports
                ],
            }
        _write_predictions(output / "predictions.csv", predictions)
        scorecard = {
            "schema": "nfl_market_recency_weighted_composite_dispersion_train_scorecard_v1",
            "diagnostic_decision": decision,
            "decision_scope": "replace current best for further Discovery only",
            "keep_conditions": conditions, "branch_diagnostics": branch_diagnostics,
            "source_denominator": {
                "events": expected_events, "dates": expected_dates,
                "materialized_events": len(materialized), "excluded_events": len(exclusions),
                "check_events": len(check_rows),
                "check_dates": len({row.split_date for row in check_rows}),
                "check_game_weeks": len({offset.game_week(row.game_id) for row in check_rows}),
            },
            "arms": {
                "market": "decision-time market probability",
                "ordinary": "archived ordinary LogisticRegression reference",
                "market_only_calibration": "archived calibration control",
                "archived_full_offset": "archived full-offset control",
                "archived_attempt1": "archived MarketOrthogonalPricePath-v1",
                "archived_attempt2": "archived MarketRecentCompositePath-v2",
                "archived_attempt3": "archived MarketRecencyWeightedCompositePath-v3 incumbent",
                "archived_attempt4": "archived MarketAllPriorDecayCompositePath-v4 branch",
                "candidate": "MarketRecencyWeightedCompositeDispersion-v5",
            },
            "control_parity": parity,
            "identical_masks": {"all_arms_share_one_complete_mask": True, "mask_sha256": masks},
            "aggregate": aggregate, "folds": fold_reports,
            "pairwise_proper_scores": pairwise,
            "corrected_grouped_inference": corrected_grouped_inference(predictions),
            "incumbent_and_branch_semantics": {
                "current_best_before_run": "MarketRecencyWeightedCompositePath-v3",
                "current_best_after_run": (
                    "MarketRecencyWeightedCompositeDispersion-v5" if decision == "KEEP"
                    else "MarketRecencyWeightedCompositePath-v3"
                ),
                "all_research_branches_retained": True,
            },
            "inference_boundary": "reused opened-Train Discovery; not independent OOS",
            "unsupported_claims": [
                "promotion or formal OOS improvement", "profitability",
                "generalization beyond 2025 NFL", "RSI self-evolution",
            ],
            "route_dev_opened": False, "sealed_final_opened": False,
            "provider_cost_usd": "0", "promotion_authorized": False,
        }
        base._atomic_json(output / "scorecard.json", scorecard)
        manifest = {
            "schema": "nfl_market_recency_weighted_composite_dispersion_train_manifest_v1",
            "complete": True, "status": "COMPLETE",
            "completed_utc": generated_utc or datetime.now(timezone.utc).isoformat(),
            "pre_score_lock_sha256": base._sha256(output / "pre_score_lock.json"),
            "input_receipts_sha256": base._sha256(output / "input_receipts.json"),
            "exclusions_sha256": base._sha256(output / "exclusions.json"),
            "staleness_inventory_sha256": base._sha256(output / "staleness_inventory.json"),
            "predictions_sha256": base._sha256(output / "predictions.csv"),
            "scorecard_sha256": base._sha256(output / "scorecard.json"),
            "source_events": expected_events, "materialized_events": len(materialized),
            "excluded_events": len(exclusions), "check_events": len(check_rows),
            "model_fits": 4, "candidate_fits": 4, "control_refits": 0,
            "diagnostic_decision": decision,
            "route_dev_opened": False, "sealed_final_opened": False,
            "external_fetch": False, "paid_provider": False,
            "provider_cost_usd": "0", "promotion_authorized": False,
        }
        base._atomic_json(output / "manifest.json", manifest)
        return manifest
    except Exception as error:
        if output.exists() and not (output / "manifest.json").exists():
            invalid = isinstance(error, offset.InvalidDataQuality)
            failure = {
                "schema": "nfl_market_recency_weighted_composite_dispersion_train_failure_v1",
                "status": "INVALID_DATA_QUALITY" if invalid else "FAILED",
                "error_type": type(error).__name__, "error": str(error)[:1200],
                "fit_started": phase_state["fit_started"],
                "scoring_started": scoring_started,
                "route_dev_opened": False, "sealed_final_opened": False,
                "external_fetch": False, "paid_provider": False,
                "provider_cost_usd": "0",
            }
            if invalid:
                failure["data_quality_report"] = error.report
            base._atomic_json(output / "failure.json", failure)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.source_root, args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
