"""Prepare the next aggregate-only sports controller workspace; do not dispatch.

This adapter returns the completed representation and trainer experiments to
the controller as aggregate evidence.  It exposes no raw rows, game IDs,
Route-Dev, Final labels, or training entrypoint.
"""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit_tools.prepare_sports_aggregate_controller import (
    BUDGET,
    EXPECTED as ORIGINAL_EXPECTED,
    load_frozen_run,
)
from data_scientist_harness.store import create
from market_rsi import file_hash, fresh_json
from paid_budget import PaidBudget


ROOT = Path(__file__).resolve().parents[1]
REPRESENTATION = ROOT / "artifacts/nfl-open-train-representation-ablation-20260916-01"
TRAINER = ROOT / "artifacts/nfl-open-train-representation-trainer-ablation-20260916-01"

FEEDBACK_EXPECTED = {
    "representation": {
        "root": REPRESENTATION,
        "result": "0ae7c8136ddbb83466ff74a1bbe4f660fb0a48ae93029264f0af961f007caaa6",
        "manifest": "d00305225af1651db533fcd9a615f38f54f2cdd72d03a29b4e96571ec4fd3041",
        "lock": "6418d59b57c052bed1420e443b931adc1454fe12d4ab21dde77481cc50e1a7ec",
        "result_schema": "nfl_representation_ablation_result_v1",
        "manifest_schema": "nfl_representation_ablation_manifest_v1",
        "lock_schema": "nfl_representation_ablation_lock_v1",
    },
    "trainer": {
        "root": TRAINER,
        "result": "3089826002ee21b89efa76f3526c605b6a6a97f7339ebe1e2443fe88ce26f7ac",
        "manifest": "fb0933fc9d0410833f350d4da696c88d32371fb2049ee45b1b7a176d5fe21ef0",
        "lock": "7385e9f13358472632fbe2dd6a778ebca493035ff5e4d8ef23c0fbe24f765c35",
        "result_schema": "nfl_representation_trainer_ablation_result_v1",
        "manifest_schema": "nfl_representation_trainer_ablation_manifest_v1",
        "lock_schema": "nfl_representation_trainer_ablation_lock_v1",
    },
}


def load_feedback_run(spec):
    loaded = load_frozen_run(spec)
    lock = loaded["lock"]
    if lock.get("opened_train_discovery_only") is not True:
        raise ValueError("feedback controller accepts opened-Train discovery only")
    return loaded


def build_feedback_findings(grid, same, representation, trainer, budget):
    rep, train = representation["result"], trainer["result"]
    rep_primary = rep["summary"][rep["primary_candidate"]]
    rep_parent = rep["summary"]["parent_raw_state"]
    train_parent, candidate = train["parent"], train["candidate"]
    budget_public = {key: value for key, value in budget.items() if key != "jobs"}
    return [
        {
            "id": "experiment-chain",
            "scope": "opened Train only; 16,632 common-support plays and 7,368 rolling-check rows; no Route-Dev or Final",
            "target": representation["lock"]["target"],
            "rolling_design": representation["lock"]["rolling_design"],
            "stages": [
                {
                    "name": "raw-state Random Forest parent",
                    "equal_game_mse": rep_parent["equal_game_candidate_mse"],
                    "relative_mse_improvement_vs_zero": rep_parent["relative_mse_improvement"],
                    "calibration_slope": rep_parent["equal_game_calibration_slope"],
                },
                {
                    "name": "full_k4 Random Forest",
                    "equal_game_mse": rep_primary["equal_game_candidate_mse"],
                    "relative_mse_improvement_vs_parent": rep_primary["paired_against_parent"]["relative_mse_improvement_vs_parent"],
                    "calibration_slope": rep_primary["equal_game_calibration_slope"],
                    "predeclared_support": rep["primary_support_rule_satisfied"],
                },
                {
                    "name": "full_k4 HistGradientBoosting",
                    "equal_game_mse": candidate["equal_game_candidate_mse"],
                    "relative_mse_improvement_vs_parent": train["paired_against_parent"]["relative_mse_improvement_vs_parent"],
                    "calibration_slope": candidate["equal_game_calibration_slope"],
                    "predeclared_support": train["support_rule_satisfied"],
                },
            ],
            "boundary": "Every result is adaptive opened-Train discovery. A lower MSE here is not Dev/Final confirmation or executable PnL.",
        },
        {
            "id": "representation-attribution",
            "primary": {
                "relative_mse_improvement_vs_raw_parent": rep_primary["paired_against_parent"]["relative_mse_improvement_vs_parent"],
                "minimum_fold_relative_mse_improvement_vs_zero": rep_primary["minimum_fold_relative_mse_improvement"],
                "positive_game_fraction_vs_parent": rep_primary["paired_against_parent"]["positive_game_fraction_vs_parent"],
                "calibration_slope": rep_primary["equal_game_calibration_slope"],
                "support_rule_satisfied": rep["primary_support_rule_satisfied"],
            },
            "ablations": {
                name: {
                    "relative_mse_improvement_vs_raw_parent": values.get("paired_against_parent", {}).get("relative_mse_improvement_vs_parent"),
                    "calibration_slope": values["equal_game_calibration_slope"],
                }
                for name, values in rep["summary"].items()
                if name in {"state_wp_delta_only", "score_time_k4_only",
                            "possession_field_only", "without_state_wp_delta"}
            },
            "observed": "Nearly all representation gain came from historical same-event state_wp_delta; score-time and possession-field additions were negligible. The primary failed only its calibration gate.",
            "timing_limit": "Historical provider event-clock availability is verified; live receive-time availability is not.",
        },
        {
            "id": "trainer-result",
            "parent": {
                "trainer": "Random Forest",
                "equal_game_mse": train_parent["equal_game_candidate_mse"],
                "calibration_slope": train_parent["equal_game_calibration_slope"],
            },
            "candidate": {
                "trainer": "HistGradientBoosting",
                "parameters": trainer["lock"]["candidate"]["parameters"],
                "equal_game_mse": candidate["equal_game_candidate_mse"],
                "relative_mse_improvement_vs_parent": train["paired_against_parent"]["relative_mse_improvement_vs_parent"],
                "positive_game_fraction_vs_parent": train["paired_against_parent"]["positive_game_fraction_vs_parent"],
                "fold_equal_game_candidate_mse": candidate["fold_equal_game_candidate_mse"],
                "calibration_slope": candidate["equal_game_calibration_slope"],
            },
            "support_conditions": train["support_conditions"],
            "paired_date_block_interval": train["paired_against_parent"]["candidate_minus_parent_date_block_interval"],
            "observed": "HGB improved all three folds and fixed aggregate calibration, but the paired date-block interval upper bound was slightly positive; the fixed candidate is therefore not supported by its preregistered conjunctive rule.",
        },
        {
            "id": "remaining-uncertainty",
            "facts": [
                "The HGB gain is positive in every rolling fold and in 49 of 63 games versus the RF parent.",
                "The paired date-block interval still crosses zero, so date-level concentration or insufficient independent date support remains plausible.",
                "The strongest feature is derived from same-event outcome state and may not be available at the same latency in live trading.",
                "Only one frozen HGB configuration was tested; no hyperparameter or algorithm search was performed.",
                "Horizon remains an open discovery variable; 30 seconds is frozen only for this comparison chain.",
            ],
            "anti_hacking_rule": "Do not relax a failed threshold, tune on Route-Dev, or rescore the same candidate under a new post-hoc primary rule.",
        },
        {
            "id": "evaluation-boundary",
            "rules": [
                "No Route-Dev result or label is included in this workspace.",
                "The previously consumed Route-Dev cohort cannot be reused for tuning.",
                "Opened-Train can support mechanism discovery and robustness diagnostics, not formal promotion.",
                "Before scoring the next experiment, freeze one primary candidate, one changed stage, reward, support rule and refutation rule.",
                "Prediction quality remains separate from live timing, fill, fee and PnL evidence.",
            ],
        },
        {
            "id": "next-controller-decision",
            "budget": budget_public,
            "instructions": (
                "Research and choose the single highest-information next opened-Train experiment. You are not limited to the current 30-second horizon, current trainers, or installed features. You may choose an evidence/split robustness study, a target or horizon study, a representation study, a fixed new trainer/algorithm, or request a missing capability. Keep all other stages fixed, name the unchanged parent, predeclare the primary candidate and support/refutation rule, and explain why this is more informative than tuning the borderline HGB. This workspace cannot train; archive one proposal and defer."
            ),
        },
    ]


def prepare(output, release, original_expected=ORIGINAL_EXPECTED,
            feedback_expected=FEEDBACK_EXPECTED, budget_path=BUDGET):
    output, release = Path(output).resolve(), Path(release).resolve()
    if output.exists():
        raise ValueError("fresh workspace required")
    grid = load_frozen_run(original_expected["grid"])
    same = load_frozen_run(original_expected["same"])
    representation = load_feedback_run(feedback_expected["representation"])
    trainer = load_feedback_run(feedback_expected["trainer"])
    budget = PaidBudget(Path(budget_path).resolve()).snapshot()
    if any(value["state"] == "dispatched" and "-turn-" in job
           for job, value in budget["jobs"].items()):
        raise ValueError("active or unresolved model dispatch; never duplicate")
    findings = build_feedback_findings(grid, same, representation, trainer, budget)
    receipts = (
        grid["receipts"] + same["receipts"]
        + representation["receipts"] + trainer["receipts"]
    )
    manifest = create(
        output, quality=None, findings=findings, allowed_dates=[],
        purpose="aggregate_research", network=True, release_path=release,
        aggregate_receipts=receipts,
    )
    receipt = {
        "schema": "sports_aggregate_feedback_controller_preparation_v1",
        "manifest_sha256": manifest,
        "finding_count": len(findings),
        "aggregate_receipts": receipts,
        "preparer_sha256": file_hash(__file__),
        "raw_rows_admitted": 0,
        "route_dev_opened": False,
        "sealed_final_opened": False,
        "provider_calls": 0,
        "fits": 0,
        "prepared_not_dispatched": True,
    }
    fresh_json(output / "preparation.json", receipt)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--release", type=Path, required=True)
    args = parser.parse_args()
    print(prepare(args.output, args.release))
