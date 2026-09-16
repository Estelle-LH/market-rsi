"""Prepare aggregate-only NFL robustness feedback for the next controller.

The workspace receives only result/manifest receipts and compact findings.  It
does not copy pre-score locks because those locks contain game-level split
identifiers that are unnecessary for the controller's next scientific choice.
No raw rows, Route-Dev, Final, or training entrypoint is admitted.
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
from audit_tools.prepare_sports_aggregate_feedback_controller import (
    FEEDBACK_EXPECTED,
    load_feedback_run,
)
from data_scientist_harness.store import create
from market_rsi import file_hash, fresh_json, load_json
from paid_budget import PaidBudget


ROOT = Path(__file__).resolve().parents[1]
ROBUSTNESS = ROOT / "artifacts/nfl-open-train-chronological-robustness-20260916-01"
ROBUSTNESS_EXPECTED = {
    "root": ROBUSTNESS,
    "result": "c2938ec08c26b51fd1e8356ac87875b0b700722909f3ba1173bc9e9609cf9734",
    "manifest": "a1ebb3a87735136a8778468f991fc7479d300a2c5c3db5500977d64126c3ade6",
    "lock": "480213aa75580e8c0d6846bbd0c34a5e3de88d145393d2ecf13922ccd4c9cc39",
    "result_schema": "nfl_chronological_robustness_result_v1",
    "manifest_schema": "nfl_chronological_robustness_manifest_v1",
    "lock_schema": "nfl_chronological_robustness_lock_v1",
}


def load_robustness(spec=ROBUSTNESS_EXPECTED):
    root = Path(spec["root"]).resolve()
    paths = {
        "result": root / "result.json",
        "manifest": root / "manifest.json",
        "lock": root / "pre_score_lock.json",
    }
    for name, path in paths.items():
        if file_hash(path) != spec[name]:
            raise ValueError(f"robustness {name} receipt changed")
    bodies = {name: load_json(path) for name, path in paths.items()}
    if (bodies["result"].get("schema") != spec["result_schema"]
            or bodies["manifest"].get("schema") != spec["manifest_schema"]
            or bodies["lock"].get("schema") != spec["lock_schema"]):
        raise ValueError("robustness schema changed")
    if (bodies["manifest"].get("result_sha256") != spec["result"]
            or bodies["manifest"].get("pre_score_lock_sha256") != spec["lock"]
            or bodies["result"].get("pre_score_lock_sha256") != spec["lock"]):
        raise ValueError("robustness cross-receipts differ")
    for body in (bodies["result"], bodies["lock"]):
        if (body.get("route_dev_opened") is not False
                or body.get("sealed_final_opened") is not False
                or str(body.get("provider_cost_usd")) != "0"):
            raise ValueError("robustness feedback accepts only zero-cost Train-only evidence")
    if bodies["lock"].get(
            "adaptive_opened_train_robustness_not_independent_confirmation") is not True:
        raise ValueError("robustness evidence boundary missing")
    # Deliberately omit the lock from controller inputs: it contains game IDs.
    receipts = [
        {"path": str(paths[name]), "sha256": spec[name]}
        for name in ("result", "manifest")
    ]
    return {**bodies, "receipts": receipts}


def public_receipts(*runs):
    """Return result/manifest only; controller does not need split identifiers."""
    kept = []
    for run in runs:
        for receipt in run["receipts"]:
            if Path(receipt["path"]).name in {"result.json", "manifest.json"}:
                kept.append(receipt)
    return kept


def build_findings(grid, same, representation, trainer, robustness, budget):
    rep = representation["result"]
    train = trainer["result"]
    robust = robustness["result"]
    rf, hgb = robust["parent"], robust["candidate"]
    paired = robust["paired_date_evidence"]
    relative = 1.0 - hgb["equal_game_candidate_mse"] / rf["equal_game_candidate_mse"]
    budget_public = {key: value for key, value in budget.items() if key != "jobs"}
    return [
        {
            "id": "experiment-chain-summary",
            "scope": "adaptive opened-Train only; no Route-Dev or Final",
            "target": robustness["lock"]["target"],
            "representation": "full_k4 including historical event-clock state_wp_delta",
            "parent": {
                "trainer": "Random Forest",
                "equal_game_mse": rf["equal_game_candidate_mse"],
                "calibration_slope": rf["equal_game_calibration_slope"],
            },
            "candidate": {
                "trainer": "HistGradientBoosting",
                "parameters": robustness["lock"]["candidate"]["parameters"],
                "equal_game_mse": hgb["equal_game_candidate_mse"],
                "relative_mse_improvement_vs_parent": relative,
                "calibration_slope": hgb["equal_game_calibration_slope"],
            },
            "prior_mechanism_evidence": {
                "representation_support_rule_satisfied": rep["primary_support_rule_satisfied"],
                "first_trainer_screen_support_rule_satisfied": train["support_rule_satisfied"],
                "chronological_robustness_support_rule_satisfied": robust["support_rule_satisfied"],
            },
            "boundary": "The robustness run was designed after earlier Train findings. It is stronger adaptive evidence, not independent confirmation.",
        },
        {
            "id": "chronological-robustness-result",
            "rolling_design": robustness["lock"]["rolling_design"],
            "check_games": robust["rolling_check_games"],
            "check_rows": robust["rolling_check_rows"],
            "dates": paired["unit_count"],
            "candidate_better_date_fraction": paired["candidate_better_unit_fraction"],
            "canonical_delta": "candidate_minus_baseline; negative means lower candidate loss and therefore better",
            "mean_candidate_minus_parent_date_loss": paired["equal_unit_mean_delta"],
            "paired_date_bootstrap_interval": paired["equal_block_bootstrap_interval"],
            "top_1_absolute_date_delta_share": paired["top_1_absolute_delta_share"],
            "top_5_absolute_date_delta_share": paired["top_5_absolute_delta_share"],
            "leave_one_date_out_mean_delta_range_without_refitting": paired["leave_one_unit_out_mean_delta"],
            "second_moment_upper_crosscheck": robust["second_moment_upper_crosscheck"],
            "support_conditions": robust["support_conditions"],
            "conclusion_status": robust["conclusion_status"],
            "observed": "The fixed HGB beat the fixed RF in every sequential fold and passed all four predeclared aggregate support conditions on wider past-to-future Train coverage.",
        },
        {
            "id": "controller-error-and-harness-repair",
            "prior_controller_errors": [
                "It defined parent minus candidate loss but interpreted negative values as candidate improvement; that sign was reversed.",
                "It proposed leave-one-date-out refitting, which would train on future dates for earlier held-out dates.",
            ],
            "repair": [
                "Harness v1.6.4 accepts only candidate_minus_baseline loss deltas; negative is better.",
                "Forecast evaluation must fit on the past and check later data.",
                "Regrouping already-generated predictions is a robustness diagnostic, not new independent evidence.",
            ],
            "execution_note": "The invalid proposal was preserved but never executed. The corrected chronological experiment was separately frozen before scoring.",
        },
        {
            "id": "remaining-scientific-bottlenecks",
            "facts": [
                "Historical provider event-clock availability is known; live receive-time availability of state_wp_delta is not.",
                "The previously consumed Route-Dev cannot be reopened for tuning this candidate.",
                "A fresh untouched confirmation cohort is still required for an independent claim.",
                "The last HGB fold calibration slope was 1.1109, so late-period drift remains plausible.",
                "No fill, fee, latency, decision-policy, or PnL evidence exists yet.",
            ],
        },
        {
            "id": "decision-contract",
            "rules": [
                "Choose exactly one next changed scientific stage before score: live timing/source validation, target/horizon, representation, fixed algorithm, or future holdout design.",
                "Use chronological past-to-future evaluation. Never use future observations to fit an earlier check period.",
                "Define loss delta as candidate_minus_baseline; negative means candidate improvement.",
                "Freeze one primary candidate, unchanged parent, reward, support rule, refutation rule, and cost bound before running.",
                "Do not reopen consumed Route-Dev or Final, and do not call adaptive Train robustness independent confirmation.",
                "A new algorithm is allowed, but it must answer a stated failure mode rather than widen an unbounded search.",
            ],
        },
        {
            "id": "next-controller-decision",
            "budget": budget_public,
            "instructions": (
                "Research and choose the single highest-information next step. You may request a missing capability or propose a new algorithm. Prefer a step that resolves the largest remaining claim blocker rather than repeatedly tuning HGB. Archive one proposal with the exact unchanged parent, one changed stage, hypothesis, data boundary, chronological design, canonical reward sign, support/refutation rules, cost bound, and what result would change the research direction. This aggregate-only workspace cannot train; submit and defer."
            ),
        },
    ]


def prepare(output, release, original_expected=ORIGINAL_EXPECTED,
            feedback_expected=FEEDBACK_EXPECTED,
            robustness_expected=ROBUSTNESS_EXPECTED, budget_path=BUDGET):
    output, release = Path(output).resolve(), Path(release).resolve()
    if output.exists():
        raise ValueError("fresh workspace required")
    grid = load_frozen_run(original_expected["grid"])
    same = load_frozen_run(original_expected["same"])
    representation = load_feedback_run(feedback_expected["representation"])
    trainer = load_feedback_run(feedback_expected["trainer"])
    robustness = load_robustness(robustness_expected)
    budget = PaidBudget(Path(budget_path).resolve()).snapshot()
    if any(value["state"] == "dispatched" and "-turn-" in job
           for job, value in budget["jobs"].items()):
        raise ValueError("active or unresolved model dispatch; never duplicate")
    findings = build_findings(
        grid, same, representation, trainer, robustness, budget)
    receipts = public_receipts(
        grid, same, representation, trainer, robustness)
    manifest = create(
        output, quality=None, findings=findings, allowed_dates=[],
        purpose="aggregate_research", network=True, release_path=release,
        aggregate_receipts=receipts,
    )
    receipt = {
        "schema": "sports_robustness_feedback_controller_preparation_v1",
        "manifest_sha256": manifest,
        "finding_count": len(findings),
        "aggregate_receipts": receipts,
        "preparer_sha256": file_hash(__file__),
        "raw_rows_admitted": 0,
        "split_identifiers_admitted": 0,
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
