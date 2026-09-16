"""Freeze aggregate-only 2024 coverage feedback for one new controller decision.

This adapter copies no game identifiers, trade rows, PBP rows, Dev outcomes or
Final data. A completed old controller archive is context, not current QA.
Preparation does not call a model or admit training data.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit_tools.prepare_nfl_60s_baseline_feedback_controller import load_baseline
from data_scientist_harness.store import create
from market_rsi import file_hash, fresh_json, load_json
from paid_budget import PaidBudget


ROOT = Path(__file__).resolve().parents[1]
SUPPORT = ROOT.parents[1] / "artifacts/nfl-2024-full-cohort-support-20260916-01"
SUPPORT_HASHES = {
    "pre_analysis_lock.json": "17bbea60716110ce73f682b0eb4d9f54757c3996218d02a7f4ba792060101708",
    "result.json": "f5bd4c5f0da9a234ac7c4f69e8bf9b405d19708d09986c98f0c62bf30df9ae38",
    "manifest.json": "e802623cd4bcfc4a7ba1005aa57dda3bb364f34a32728a20d2755b079c5a5ec9",
}
ARCHIVE = ROOT / "artifacts/nfl-60s-baseline-controller-20260916-01/round-archive.json"
ARCHIVE_HASH = "b6b92370428b3ebb5ab4768d1ffa7ec8241e7213e6f6a15fbd8bb47aa1cf8bea"
BUDGET = ROOT / "artifacts/kalshi-research-glm53-20260907-01/budget"


def load_support(root: Path = SUPPORT, expected: dict = SUPPORT_HASHES) -> dict:
    root = Path(root).resolve()
    for name, sha256 in expected.items():
        if file_hash(root / name) != sha256:
            raise ValueError(f"frozen full-cohort {name} changed")
    lock, result, manifest = (load_json(root / name) for name in
                              ("pre_analysis_lock.json", "result.json", "manifest.json"))
    if (lock.get("schema") != "nfl_2024_full_cohort_support_lock_v1"
            or result.get("schema") != "nfl_2024_full_cohort_support_result_v1"
            or manifest.get("schema") != "nfl_2024_full_cohort_support_manifest_v1"
            or manifest.get("complete") is not True
            or manifest.get("result_sha256") != expected["result.json"]
            or manifest.get("pre_analysis_lock_sha256") != expected["pre_analysis_lock.json"]
            or result.get("pre_analysis_lock_sha256") != expected["pre_analysis_lock.json"]
            or lock.get("mapped_games") != 284 or result.get("games") != 284
            or result.get("games_with_trades") != 284
            or result.get("timed_typed_plays") != 47875
            or result.get("reasons_by_horizon", {}).get("60") != {
                "covered": 32384, "no_prior_trade": 0,
                "stale_prior_trade": 2583, "no_new_trade": 12908}
            or result.get("reasons_by_horizon", {}).get("300") != {
                "covered": 43506, "no_prior_trade": 0,
                "stale_prior_trade": 2583, "no_new_trade": 1786}
            or lock.get("denominator") !=
            "all timed, typed PBP plays in all 284 mapped games; quiet games retained"
            or result.get("interpretation_boundary") !=
            "historical event-clock/trade-print support only; not provider publish/local receive, model score, Train admission or tradable edge"):
        raise ValueError("full-cohort scope or totals changed")
    for body in (lock, result, manifest):
        if (body.get("train_admitted") is not False
                or body.get("route_dev_opened") is not False
                or body.get("sealed_final_opened") is not False
                or str(body.get("provider_cost_usd")) != "0"):
            raise ValueError("full-cohort must remain an unadmitted zero-cost source audit")
    if lock.get("model_fits") != 0 or result.get("model_fits") != 0 or manifest.get("model_fits") != 0:
        raise ValueError("full-cohort source audit unexpectedly fitted a model")
    return {"result": result, "receipts": [
        {"path": str(root / name), "sha256": expected[name]}
        for name in ("result.json", "manifest.json")]}


def build_findings(baseline: dict, support: dict, budget: dict) -> list[dict]:
    methods = baseline["result"]["methods"]
    if set(methods) != {"ridge", "random_forest", "hist_gradient_boosting"}:
        raise ValueError("baseline trainer slate changed")
    result = support["result"]
    if sum(result["reasons_by_horizon"]["60"].values()) != result["timed_typed_plays"]:
        raise ValueError("60-second denominator changed")
    if sum(result["reasons_by_horizon"]["300"].values()) != result["timed_typed_plays"]:
        raise ValueError("300-second denominator changed")
    public_budget = {key: value for key, value in budget.items() if key != "jobs"}
    return [
        {"id": "existing-60-second-train-screen",
         "scope": "opened 2025 Train; 163 games, 3 chronological 21-game checks, same 60s rows/features",
         "equal_game_mse": {name: methods[name]["equal_game_candidate_mse"] for name in sorted(methods)},
         "provisional_fixed_baseline": baseline["result"]["train_only_selected_method"],
         "boundary": "18.9% HGB-vs-Ridge gap is Train-only fixed-method screening, not self-iteration or independent confirmation."},
        {"id": "complete-2024-source-and-target-support",
         "source_scope": "all 284 mapped 2024 NFL moneyline games; quiet games retained; no outcome selection",
         "trade_rows": result["trade_rows"], "timed_typed_plays": result["timed_typed_plays"],
         "historical_target_support": {
             str(h): {"count": result["reasons_by_horizon"][str(h)],
                      "fraction": result["coverage_by_horizon"][str(h)],
                      "median_game_fraction": result["median_game_coverage_by_horizon"][str(h)]}
             for h in (60, 300)},
         "boundary": ("Source/timing audit, not Train admission or model score. Historical event clock is not "
                      "provider publish/local receive time. Longer horizon defines a different target; "
                      "do not compare its MSE with the old 60s task.")},
        {"id": "research-decision-and-protected-evaluation",
         "budget": public_budget,
         "prior_archive": "The previous controller's full archive is available via read_archive; its unimplemented half-split HGB suggestion is not a validated CatBoost algorithm and called NFL basketball.",
         "instruction": ("Investigate the causal bottleneck and choose one next opened-Train research stage: "
                         "objective/coverage, time-available features, deterministic strong baseline, or a sourced "
                         "new algorithm. You may propose another defensible option. Compare alternatives, specify "
                         "the unchanged parent, one changed stage, hypothesis, support/refutation rule, same-row "
                         "or matched-population comparison, cost bound, and evidence needed to execute. "
                         "If proposing a new horizon, freeze its objective, population and reward before scoring and "
                         "rebuild every baseline; do not select it by looking at Dev/Final. The 2024 cohort is not "
                         "admitted training data. This session can research and archive/defer only: no fit, new "
                         "Dev/Final, purchase, or benchmark claim. Final confirmation needs at least 20 untouched "
                         "dates; old Route-Dev was consumed and sealed 40-game Final has only 11 dates.")},
    ]


def prepare(output: Path, release: Path, *, budget_path: Path = BUDGET,
            support_root: Path = SUPPORT, support_hashes: dict = SUPPORT_HASHES,
            archive_path: Path = ARCHIVE, archive_hash: str = ARCHIVE_HASH) -> dict:
    output, release = Path(output).resolve(), Path(release).resolve()
    if output.exists():
        raise ValueError("fresh controller workspace required")
    baseline = load_baseline()
    support = load_support(support_root, support_hashes)
    if file_hash(archive_path) != archive_hash:
        raise ValueError("prior controller archive changed")
    budget = PaidBudget(Path(budget_path).resolve()).snapshot()
    if any(value["state"] == "dispatched" and "-turn-" in job
           for job, value in budget["jobs"].items()):
        raise ValueError("unresolved paid controller dispatch")
    receipts = baseline["receipts"] + support["receipts"]
    findings = build_findings(baseline, support, budget)
    manifest = create(output, quality=None, findings=findings, allowed_dates=[],
                      purpose="aggregate_research", network=True, release_path=release,
                      aggregate_receipts=receipts,
                      prior_archives=[{"path": str(Path(archive_path).resolve()), "sha256": archive_hash}])
    record = {"schema": "nfl_full_cohort_feedback_preparation_v1",
              "manifest_sha256": manifest, "preparer_sha256": file_hash(__file__),
              "aggregate_receipts": receipts, "prior_archive_sha256": archive_hash,
              "finding_count": len(findings), "raw_rows_admitted": 0,
              "route_dev_opened": False, "sealed_final_opened": False,
              "provider_calls": 0, "fits": 0, "prepared_not_dispatched": True}
    fresh_json(output / "preparation.json", record)
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--release", type=Path, required=True)
    args = parser.parse_args()
    print(prepare(args.output, args.release))
