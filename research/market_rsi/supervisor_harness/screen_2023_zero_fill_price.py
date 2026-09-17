"""Source discrepancy canary: one predeclared zero-fill diagnostic market.

The market is selected from the already frozen 12-game fill-count diagnostic,
not from prices or scores. This cannot be used as model training/evaluation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from supervisor_harness.screen_2023_archive_catalog import encoded, sha
from supervisor_harness.screen_2023_price_history_canary import fetch, summarize
from supervisor_harness.screen_2023_stratified_fills import check_plan


def zero_fill_game(rows: list[dict]) -> str:
    eligible = sorted(row["game_id"] for row in rows
                      if row["stratum"] != "weeks_19_22"
                      and row["window_fills"] == 0)
    if not eligible:
        raise ValueError("frozen regular-season sample has no zero-window-fill case")
    return eligible[0]


def screen(plan_dir: Path, mapping_dir: Path, fill_dir: Path, output: Path) -> dict:
    if output.exists():
        raise FileExistsError(output)
    selection = check_plan(plan_dir, mapping_dir)
    fill_raw = (fill_dir / "results.json").read_bytes()
    fill_manifest = json.loads((fill_dir / "manifest.json").read_text())
    if (fill_manifest.get("schema") != "market_p0_2023_stratified_fill_density_v1"
            or fill_manifest.get("result_sha256") != sha(fill_raw)
            or fill_manifest.get("completed_games") != 12
            or fill_manifest.get("plan_selection_sha256_verified")
               != sha((plan_dir / "selection.json").read_bytes())):
        raise ValueError("fixed stratified fill evidence changed")
    rows = json.loads(fill_raw)
    if {row["game_id"] for row in rows} != {row["game_id"] for row in selection}:
        raise ValueError("fill result is not the frozen sample")
    game_id = zero_fill_game(rows)
    choice = next(row for row in selection if row["game_id"] == game_id)
    observation = next(row for row in rows if row["game_id"] == game_id)
    kickoff = observation["kickoff_epoch_utc"]
    lower, upper = kickoff - 12 * 3600, kickoff + 5 * 3600
    token = sorted(choice["token_ids"])[0]
    raw, url = fetch(token, lower, upper)
    metrics = summarize(raw, lower, kickoff, upper)
    report = {"schema": "market_p0_2023_zero_fill_price_discrepancy_v1",
              "selection_rule": "lowest game ID among frozen regular-season games with zero full-window fills",
              "game_id": game_id, "source_url": url,
              "fill_result_sha256_verified": sha(fill_raw),
              "price_response_sha256": sha(raw),
              "fixed_window_fills": observation["window_fills"], **metrics,
              "source_discrepancy_not_resolved": True,
              "price_type_or_executability_verified": False,
              "archive_completeness_verified": False,
              "training_or_evaluation_data_admitted": False,
              "provider_cost_usd": "0"}
    output.mkdir(parents=True, exist_ok=False)
    (output / "price.raw.json").write_bytes(raw)
    (output / "manifest.json").write_bytes(encoded(report))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--fills", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute-public-price-request", action="store_true")
    args = parser.parse_args()
    if not args.execute_public_price_request:
        parser.error("refusing price request without explicit flag")
    print(json.dumps(screen(args.plan, args.mapping, args.fills, args.output),
                     indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
