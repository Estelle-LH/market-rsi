"""Prepare a fresh, aggregate-only controller discovery workspace.

The controller sees the completed opened-Train trainer screen and claim limits,
not game IDs, raw rows, Route-Dev outcomes, or sealed Final labels. Preparation
never dispatches a model or trains a candidate.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data_scientist_harness.store import create
from market_rsi import file_hash, fresh_json, load_json
from paid_budget import PaidBudget


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "artifacts/nfl-deterministic-60s-baseline-20260916-01"
BUDGET = ROOT / "artifacts/kalshi-research-glm53-20260907-01/budget"
DATA_SCREEN = ROOT.parents[1] / "artifacts/pm_2024_nfl_timing_support_20260916_02/manifest.json"
DATA_SCREEN_SHA256 = "0ab1735aaa9245e0780b08f76b4cd1fd1fe9a9e82b4361a139a640414a390e3d"
EXPECTED = {
    "pre_score_lock.json": "c4cfc2813792844bf9d455cbe2219c781442938141a659bfcec78db5ef7ea340",
    "result.json": "208fc04b08c8f63f8d595a2c9621fd4c2dc21af1ee853fd82a724ceb5e2feb80",
    "manifest.json": "80d33dfa6e16b31a8e689916b9cffef23cf1214813ef3d62a5e3ca191978ed8a",
}


def load_baseline(root: Path = BASELINE, expected: dict = EXPECTED) -> dict:
    paths = {name: Path(root).resolve() / name for name in expected}
    for name, path in paths.items():
        if file_hash(path) != expected[name]:
            raise ValueError(f"frozen baseline {name} changed")
    lock, result, manifest = (load_json(paths[name]) for name in
                              ("pre_score_lock.json", "result.json", "manifest.json"))
    if (lock.get("schema") != "nfl_deterministic_60s_baseline_lock_v1"
            or result.get("schema") != "nfl_deterministic_60s_baseline_result_v1"
            or manifest.get("schema") != "nfl_deterministic_60s_baseline_manifest_v1"
            or manifest.get("complete") is not True
            or manifest.get("pre_score_lock_sha256") != expected["pre_score_lock.json"]
            or result.get("pre_score_lock_sha256") != expected["pre_score_lock.json"]
            or manifest.get("result_sha256") != expected["result.json"]
            or lock.get("target") != "home_change_60s"
            or lock.get("train_population") != {"games": 163, "eligible_rows": 23709}
            or len(lock.get("folds", [])) != 3
            or result.get("train_only_selected_method") != "hist_gradient_boosting"
            or result.get("formal_claim") is not False):
        raise ValueError("baseline receipt or scientific scope changed")
    for body in (lock, result, manifest):
        if (body.get("route_dev_opened") is not False
                or body.get("sealed_final_opened") is not False):
            raise ValueError("controller input cannot contain Dev or Final")
    if str(lock.get("provider_cost_usd")) != "0" or str(result.get("provider_cost_usd")) != "0":
        raise ValueError("Train baseline is not the zero-cost frozen screen")
    return {"lock": lock, "result": result, "manifest": manifest,
            "receipts": [{"path": str(paths[name]), "sha256": expected[name]}
                         for name in ("result.json", "manifest.json")]}


def load_data_screen(path: Path = DATA_SCREEN, sha256: str = DATA_SCREEN_SHA256) -> dict:
    if file_hash(path) != sha256:
        raise ValueError("2024 data screen manifest changed")
    value = load_json(path)
    if (value.get("schema") != "nfl_2024_pbp_trade_timing_support_v1"
            or value.get("train_admitted") is not False
            or value.get("scientific_score") is not False
            or value.get("historical_event_clock_only") is not True
            or value.get("totals", {}).get("covered_60s") != 1400
            or value.get("totals", {}).get("timed_typed_play_rows") != 2027):
        raise ValueError("2024 screen scope or coverage changed")
    return value


def build_findings(baseline: dict, budget: dict, data_screen: dict) -> list[dict]:
    result = baseline["result"]
    methods = result["methods"]
    allowed = {"ridge", "random_forest", "hist_gradient_boosting"}
    if set(methods) != allowed:
        raise ValueError("fixed trainer slate changed")
    summary = {
        name: {
            "equal_game_mse": methods[name]["equal_game_candidate_mse"],
            "calibration_slope": methods[name]["equal_game_calibration_slope"],
            "positive_game_fraction": methods[name]["positive_game_fraction"],
        }
        for name in sorted(allowed)
    }
    public_budget = {key: value for key, value in budget.items() if key != "jobs"}
    return [
        {
            "id": "fixed-60s-baseline-screen",
            "scope": "opened 2025 Train only; 163 games, 3 chronological checks of 21 games, 9615 scored rows and 21 UTC dates",
            "target": "home_price(t+60s) - home_price(pre-play)",
            "same_rows_and_representation": True,
            "only_changed_stage": "prediction_trainer",
            "methods": summary,
            "selection_rule": "minimum opened-Train equal-game MSE, fixed before scoring",
            "selected_provisional_fixed_baseline": result["train_only_selected_method"],
            "relative_mse_improvement_vs_ridge": result["relative_mse_improvement_vs_ridge"],
            "per_fold_mse": [fold["method_mse"] for fold in result["folds"]],
            "boundary": "Standard deterministic trainer screen, not self-iteration or independent confirmation; Strong-Baseline-1 is not yet frozen.",
        },
        {
            "id": "data-and-time-blockers",
            "observed": [
                "Only 163 independent 2025 Train games are admitted; the 2024 market archive has a 12-game sample screen, not admitted training rows.",
                f"In the 2024 sample, the historical 60-second play/trade target was present for {data_screen['totals']['covered_60s']} of {data_screen['totals']['timed_typed_play_rows']} plays (69.1%), below the proposed 90% data-admission gate.",
                "state_wp_delta uses historical same-play end_situation; provider publish and local receive times are not proven, so this is an offline event-conditioned response task, not a live tradable signal.",
                "The old 50-game Route-Dev has been consumed. The sealed 40-game Final spans 11 independent dates, below the 20-date formal confirmation threshold.",
            ],
            "needed": "More admissible Train games, defensible feature available_time, and a new untouched future time block before a formal claim.",
        },
        {
            "id": "next-research-decision",
            "budget": public_budget,
            "instruction": (
                "Use opened Train and public primary literature for open-ended discovery. "
                "Decide the single highest-information next changed stage: strengthen the deterministic baseline "
                "(e.g. CatBoost/LightGBM under equal input and search budget), repair data coverage/feature timing, "
                "or propose a mechanism/algorithm not in the installed library. State the unchanged parent, "
                "hypothesis, support/refutation rule, same-row ablation and cost bound. Do not infer an unseen "
                "score from 18.9% Train gain. This aggregate-only workspace cannot fit, open Dev/Final, "
                "purchase data or activate a new tool; archive one supported proposal and defer."
            ),
        },
    ]


def prepare(output: Path, release: Path, *, baseline_root: Path = BASELINE,
            expected: dict = EXPECTED, budget_path: Path = BUDGET) -> dict:
    output, release = Path(output).resolve(), Path(release).resolve()
    if output.exists():
        raise ValueError("fresh controller workspace required")
    baseline = load_baseline(baseline_root, expected)
    data_screen = load_data_screen()
    budget = PaidBudget(Path(budget_path).resolve()).snapshot()
    if any(value["state"] == "dispatched" and "-turn-" in job
           for job, value in budget["jobs"].items()):
        raise ValueError("active or unresolved paid controller dispatch")
    findings = build_findings(baseline, budget, data_screen)
    manifest = create(output, quality=None, findings=findings, allowed_dates=[],
                      purpose="aggregate_research", network=True, release_path=release,
                      aggregate_receipts=baseline["receipts"])
    receipt = {
        "schema": "nfl_60s_baseline_feedback_preparation_v1",
        "manifest_sha256": manifest,
        "preparer_sha256": file_hash(__file__),
        "aggregate_receipts": baseline["receipts"],
        "data_screen_manifest_sha256": DATA_SCREEN_SHA256,
        "finding_count": len(findings),
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
