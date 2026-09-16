"""Prepare a frozen aggregate-only sports controller workspace; do not dispatch it.

The adapter exposes compact summaries of two completed opened-Train studies.  It
does not expose raw rows, Route-Dev labels/results, Final, or a training entrypoint.
"""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data_scientist_harness.store import create
from market_rsi import file_hash, fresh_json, load_json
from paid_budget import PaidBudget


ROOT = Path(__file__).resolve().parents[1]
GRID = ROOT / "artifacts/nfl-open-train-target-grid-screen-20260916-02"
SAME = ROOT / "artifacts/nfl-open-train-target-same-support-20260916-01"
BUDGET = ROOT / "artifacts/kalshi-research-glm53-20260907-01/budget"

EXPECTED = {
    "grid": {
        "root": GRID,
        "result": "238429415eab87e44882bc2b6e2de82064885889fcf5e50416334afb7b1f0003",
        "manifest": "8b3c370369d696258e5cc875066cc7529e3d6faa429eb69eefebd10b2048a2eb",
        "lock": "49531efebaa24b2641c30b4e9b4875c4630c37b55b9906b72f44a6dbb0436508",
        "result_schema": "nfl_open_train_target_grid_screen_result_v1",
        "manifest_schema": "nfl_open_train_target_grid_screen_manifest_v1",
        "lock_schema": "nfl_open_train_target_grid_screen_lock_v1",
    },
    "same": {
        "root": SAME,
        "result": "573a4bcfd86599556c43dad6abf43ffcba6ce226a4cc41297ed4e74483145b92",
        "manifest": "1f232b36dc518bcb4d55bf4b8ff28f1c4f0ca3e3a85d62f86656a9d68b62d3b1",
        "lock": "e984cf60e451d193adb06ce71a2969ffca8f60dfeb9cdd99e239aab338e324fb",
        "result_schema": "nfl_open_train_target_same_support_result_v1",
        "manifest_schema": "nfl_open_train_target_same_support_manifest_v1",
        "lock_schema": "nfl_open_train_target_same_support_lock_v1",
    },
}


def load_frozen_run(spec):
    root = Path(spec["root"]).resolve()
    paths = {"result": root / "result.json", "manifest": root / "manifest.json",
             "lock": root / "pre_score_lock.json"}
    for name, path in paths.items():
        if file_hash(path) != spec[name]:
            raise ValueError(f"{name} receipt changed")
    bodies = {name: load_json(path) for name, path in paths.items()}
    if (bodies["result"].get("schema") != spec["result_schema"]
            or bodies["manifest"].get("schema") != spec["manifest_schema"]
            or bodies["lock"].get("schema") != spec["lock_schema"]):
        raise ValueError("sports aggregate schema changed")
    if (bodies["manifest"].get("result_sha256") != spec["result"]
            or bodies["manifest"].get("pre_score_lock_sha256") != spec["lock"]
            or bodies["result"].get("pre_score_lock_sha256") != spec["lock"]):
        raise ValueError("sports aggregate cross-receipts differ")
    for body in (bodies["result"], bodies["lock"]):
        if (body.get("route_dev_opened") is not False
                or body.get("sealed_final_opened") is not False
                or str(body.get("provider_cost_usd")) != "0"):
            raise ValueError("aggregate adapter accepts only zero-cost Train-only studies")
    if (bodies["lock"].get("discovery_only") is not True
            and bodies["lock"].get("opened_train_discovery_only") is not True):
        raise ValueError("aggregate adapter accepts discovery-only inputs")
    return {**bodies, "receipts": [
        {"path": str(paths[name]), "sha256": spec[name]}
        for name in ("result", "manifest", "lock")
    ]}


def method_summary(target):
    top_level_folds = target.get("fold_relative_mse_improvements", {})
    return {
        "coverage": target["profile"]["full_population_coverage"],
        "exact_zero_fraction": target["profile"]["exact_zero_fraction"],
        "methods": {
            method: {
                "relative_mse_improvement": values["relative_mse_improvement"],
                "minimum_fold_relative_improvement": min(
                    values.get("fold_relative_mse_improvements",
                               top_level_folds.get(method, []))),
                "calibration_slope": values["equal_game_calibration_slope"],
                "positive_game_fraction": values["positive_game_fraction"],
            }
            for method, values in target["methods"].items()
        },
    }


def build_findings(grid, same, budget):
    grid_result, grid_lock = grid["result"], grid["lock"]
    same_result = same["result"]
    target_table = {
        name: method_summary(values)
        for name, values in grid_result["public_summary"].items()
    }
    same_table = {
        name: method_summary(values)
        for name, values in same_result["public_summary"].items()
    }
    budget_public = {key: value for key, value in budget.items() if key != "jobs"}
    return [
        {
            "id": "target-grid-result",
            "scope": "opened Train discovery only; 163 games and 25,957 source plays; no Route-Dev or Final",
            "question": grid_lock["question"],
            "features": {"numeric": grid_lock["numeric_features"],
                         "categorical": grid_lock["categorical_features"]},
            "fixed_methods": grid_lock["methods"],
            "rolling_design": grid_lock["rolling_design"],
            "target_results": target_table,
            "shortlist": grid_result["opened_train_shortlist"],
            "observed": "16 of 24 target-method pairs met the predeclared opened-Train support rule; the three-target shortlist was 30s, 20s and 45s with Random Forest.",
            "boundary": "This is adaptive Train discovery, not target promotion or an external score. Each target is compared only with its own zero-change baseline.",
        },
        {
            "id": "same-support-result",
            "scope": "16,632 full-population plays simultaneously labeled at 15/20/30/45/60s; 7,368 rolling-check rows",
            "question": same["lock"]["question"],
            "same_rows_for_every_target": True,
            "target_results": same_table,
            "rankings": same_result["rankings"],
            "observed": "30s and 45s ranked in the top two by weakest-fold skill for both Ridge and Random Forest.",
            "boundary": "This reduces the eligible-population explanation for the 30-45s result, but it reuses the same opened Train games and is not independent confirmation.",
        },
        {
            "id": "representation-and-algorithm-gap",
            "observed": "The new horizon studies used only pre-play price, clock/game state, score changes and play type. They did not test the previously implemented current-event end-state representation at 20/30/45s, nor a new algorithm beyond fixed Ridge and Random Forest.",
            "prior_opened_train_context": "At the old 60s definition, adding current-event state_wp_delta improved opened-Train Ridge MSE by 13.31%; that number is context, not evidence at the new horizons.",
            "decision_needed": "Choose one next changed stage: representation, trainer/algorithm, or target formulation. Do not change multiple stages in one A/B.",
        },
        {
            "id": "event-time-candidate",
            "observed": target_table["event_5trades_delta"],
            "interpretation_limit": "Event-time and clock-time targets answer different questions. Event-time may reduce sparse-clock censoring, but transaction intensity can itself select market regimes.",
            "decision_needed": "Keep event-time as a real alternative if research supports it; do not promote it by comparing raw MSE with clock-time targets.",
        },
        {
            "id": "evaluation-boundary",
            "rules": [
                "No Route-Dev result or label is included in this workspace.",
                "A previously used Route-Dev cohort remains consumed and is not reusable for tuning.",
                "The next candidate must freeze target, support, features, trainer and primary metric before any new untouched confirmation.",
                "Prediction skill does not prove executable PnL; live clock, latency, fills, fees and decision policy remain separate stages.",
            ],
        },
        {
            "id": "next-controller-decision",
            "budget": budget_public,
            "instructions": "Inspect the sports method library and read relevant primary sources. Propose the single highest-value next opened-Train experiment, including unchanged parent, changed causal stage, hypothesis, same-row baselines, ablations, failure modes and evidence needed before a new untouched confirmation. You may propose a new algorithm or capability instead of choosing the installed library. This workspace cannot train; archive the supported proposal and defer.",
        },
    ]


def prepare(output, release, expected=EXPECTED, budget_path=BUDGET):
    output, release = Path(output).resolve(), Path(release).resolve()
    if output.exists():
        raise ValueError("fresh workspace required")
    grid, same = load_frozen_run(expected["grid"]), load_frozen_run(expected["same"])
    budget = PaidBudget(Path(budget_path).resolve()).snapshot()
    if any(value["state"] == "dispatched" and "-turn-" in job
           for job, value in budget["jobs"].items()):
        raise ValueError("active or unresolved model dispatch; never duplicate")
    findings = build_findings(grid, same, budget)
    receipts = grid["receipts"] + same["receipts"]
    manifest = create(output, quality=None, findings=findings, allowed_dates=[],
        purpose="aggregate_research", network=True, release_path=release,
        aggregate_receipts=receipts)
    receipt = {
        "schema": "sports_aggregate_controller_preparation_v1",
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
